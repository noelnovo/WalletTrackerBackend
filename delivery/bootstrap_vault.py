"""OPERATOR ONLY. Plan by default; --apply requires an existing authorized token.

No recovery, root-generation, unseal, auth bypass or production key/password
rotation. Credentials file is protected structured input, not a manifest.
"""
import argparse,base64,json,os,pathlib,secrets,stat,urllib.request,urllib.error
from vault_contract import contract
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');parser.add_argument('--credentials-file',type=pathlib.Path);args=parser.parse_args();desired=contract()
    if not args.apply:
        print(json.dumps({'mode':'plan-only','operator_access_required':True,'recovery_performed':False,'policies':list(desired['policies']),'roles':list(desired['roles']),'input_record_keys':desired['required_input_records']}));return
    token=os.environ.get('VAULT_TOKEN');address=os.environ.get('VAULT_ADDR','https://vault.int.downops.win').rstrip('/')
    if not token or address!='https://vault.int.downops.win':raise RuntimeError('Existing authorized token and verified internal Vault address required')
    if not args.credentials_file:raise RuntimeError('Protected operator credential input is required before any writes')
    st=args.credentials_file.stat()
    if st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)&0o077:raise RuntimeError('Credential input must be owner-only')
    records=json.loads(args.credentials_file.read_text())
    if set(records)!=set(desired['required_input_records']):raise RuntimeError('Unexpected or missing credential input record')
    for path,keys in desired['required_input_records'].items():
        if set(records.get(path,{}))!=set(keys) or not all(records[path].values()):raise RuntimeError('Required credential record/key set missing')
    def api(method,path,data=None,missing=False):
        request=urllib.request.Request(address+'/v1/'+path,data=None if data is None else json.dumps(data).encode(),method=method,headers={'X-Vault-Token':token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=20) as r:
                raw=r.read();return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if missing and e.code==404:return None
            raise RuntimeError('Operator Vault request rejected (HTTP '+str(e.code)+'); response withheld') from None
    mounts=api('GET','sys/mounts')['data'];auth=api('GET','sys/auth')['data']
    if auth.get('jwt/',{}).get('type')!='jwt':raise RuntimeError('Existing Kubernetes JWT trust is absent; operator review required')
    if 'wallettracker/' not in mounts:api('POST','sys/mounts/wallettracker',{'type':'kv','options':{'version':'2'}})
    elif mounts['wallettracker/']['type']!='kv' or mounts['wallettracker/']['options']['version']!='2':raise RuntimeError('Unexpected existing KV engine')
    config=desired['create_auth_mount_if_absent']['gitlab-ci']['config']
    if 'gitlab-ci/' not in auth:
        api('POST','sys/auth/gitlab-ci',{'type':'jwt'});api('POST','auth/gitlab-ci/config',config)
    else:
        current=api('GET','auth/gitlab-ci/config')['data']
        if any(current.get(k)!=v for k,v in config.items()):raise RuntimeError('Existing GitLab auth trust differs; will not overwrite shared configuration')
    def ensure(path,data):
        existing=api('GET','wallettracker/data/'+path,missing=True)
        if existing:
            if existing['data']['data']!=data:raise RuntimeError('Existing credential differs; rotation is not authorized')
        else:api('POST','wallettracker/data/'+path,{'options':{'cas':0},'data':data})
    for path,data in records.items():ensure(path,data)
    # Generate dev-only identities once. Existing values are never replaced.
    for path,key in [('dev/database','DATABASE_ROOT_PASSWORD'),('dev/signing','SIGN_SECRET_WORD')]:
        if not api('GET','wallettracker/data/'+path,missing=True):ensure(path,{key:secrets.token_urlsafe(36)})
    if not api('GET','wallettracker/data/dev/rsa',missing=True):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        ensure('dev/rsa',{'PRIVATE_KEY_BASE64':base64.b64encode(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())).decode(),'PUBLIC_KEY_BASE64':base64.b64encode(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)).decode()})
    for name,policy in desired['policies'].items():api('PUT','sys/policies/acl/'+name,{'policy':policy})
    for path,role in desired['roles'].items():
        mount,name=path.split('/',1);api('POST','auth/'+mount+'/role/'+name,role)
    print(json.dumps({'operator_bootstrap_applied':True,'production_values_rotated':False,'recovery_performed':False,'shared_kubernetes_jwt_trust_changed':False,'caller_token_revoked':False,'note':'Operator owns its login/token lifecycle; this script does not retain or revoke that existing credential'}))
if __name__=='__main__':
    try:main()
    except Exception as e:
        print(json.dumps({'success':False,'error_class':type(e).__name__,'safe_error':str(e) if isinstance(e,RuntimeError) else 'details withheld'}));raise SystemExit(1)
