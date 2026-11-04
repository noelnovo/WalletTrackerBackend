"""Canonical preservation proof. Receipts contain digests/counts, never row values.

Run by a protected migration coordinator; SQL transport returns stay in memory.
Each original user field (including password verifier/salt, keys and tenant
credentials) is covered, as are every main/tenant row and existing SQL account.
"""
import hashlib,json
def proof(query):
    schemas=[x for x in query("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='wallet_tracker' OR SCHEMA_NAME LIKE 'wallet\\_tracker\\_u%' ORDER BY SCHEMA_NAME").decode().splitlines() if x]
    out={'schemas':{},'noel':None}
    for schema in schemas:
        tables=query("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='"+schema+"' AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME").decode().splitlines();out['schemas'][schema]={}
        for table in tables:
            cols=query("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='"+schema+"' AND TABLE_NAME='"+table+"' ORDER BY ORDINAL_POSITION").decode().splitlines()
            # Identifiers come from native metadata, quoted without interpolation
            # into credentials/argv. JSON returns are never printed or retained.
            fields=','.join("'"+c.replace("'","''")+"',`"+c.replace('`','``')+'`' for c in cols)
            rows=query('SELECT JSON_OBJECT('+fields+') FROM `'+schema+'`.`'+table+'`').splitlines()
            digests=sorted(hashlib.sha256(r).hexdigest() for r in rows)
            out['schemas'][schema][table]={'rows':len(rows),'digest':hashlib.sha256(json.dumps(digests).encode()).hexdigest()}
            if schema=='wallet_tracker' and table=='User':
                noel=query('SELECT JSON_OBJECT('+fields+") FROM `wallet_tracker`.`User` WHERE username='noel'").splitlines()
                if len(noel)!=1:raise RuntimeError('Exactly one noel account required')
                data=json.loads(noel[0]);out['noel']={'id':data['id'],'username':'noel','complete_original_record_digest':hashlib.sha256(noel[0]).hexdigest()}
    accounts=query("SELECT JSON_OBJECT('Host',Host,'User',User,'Priv',Priv) FROM mysql.global_priv ORDER BY Host,User").splitlines()
    out['existing_account_digests']={json.loads(r)['User']+'@'+json.loads(r)['Host']:hashlib.sha256(r).hexdigest() for r in accounts}
    if not out['noel']:raise RuntimeError('Original noel account absent')
    return out
def compare(original,current):
    return {'all_main_and_tenant_rows_equal':original['schemas']==current['schemas'],'noel_complete_record_equal':original['noel']==current['noel'],'all_original_accounts_equal':all(current['existing_account_digests'].get(k)==v for k,v in original['existing_account_digests'].items())}
