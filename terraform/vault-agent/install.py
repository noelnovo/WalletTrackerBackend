"""Public native deployment helper for Terraform; contains no Vault client.

Run on Proxmox through the existing root provisioner. AppRole bootstrap and the
private RSA identity manifest are out-of-band root-only files, never TF values.
Only official Agent injects app credentials. Fresh DB/account bootstrap is NOT
automated; existing native account state must be established separately.
"""
import argparse,datetime,gzip,hashlib,json,os,pathlib,re,subprocess,time
os.umask(0o077)
HERE=pathlib.Path(__file__).resolve().parent
BIN='/opt/hashicorp/vault/2.1.2/vault'
PIN='39b7c9dd881b50cce481f2ba2365800729a961292724b4ef4f80ff98d34adff6'
API='native-wallettracker-api';CF='native-cloudflared-wallettracker'
def run(a,timeout=120):
 p=subprocess.run(a,capture_output=True,text=True,timeout=timeout,env={k:v for k,v in os.environ.items() if not k.startswith('VAULT_')})
 if p.returncode:raise RuntimeError('Native deployment command failed; diagnostics suppressed')
 return p.stdout
def root(g):return pathlib.Path('/proc')/run(['lxc-info','-n',str(g),'-pH']).strip()/'root'
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def bootstrap_required(g,id):
 for name in ['role_id','secret_id']:
  p='/etc/vault-agent/'+id+'/auth/'+name
  if not (root(g)/p.lstrip('/')).is_file():raise RuntimeError('Out-of-band AppRole bootstrap required; no inline/TF credential fallback')
  if run(['pct','exec',str(g),'--','stat','-c','%u %g %a',p]).split()!=['0','0','400']:raise RuntimeError('Bootstrap must be root:root0400')
 if id==API:
  identity=root(g)/'etc/vault-agent'/API/'config/rsa-identity.json'
  if not identity.is_file():raise RuntimeError('Out-of-band RSA identity manifest and managed links required')
  values=json.loads(identity.read_text())
  if set(values)!={'private_key.pem','public_key.pem'}:raise RuntimeError('Invalid private identity manifest')
  for name in values:
   p=root(g)/'srv/WalletTrackerAPI/app'/name;target='/run/vault-agent-'+API+'/rsa/'+name
   if not p.is_symlink() or os.readlink(p)!=target:raise RuntimeError('Approved managed RSA links required; no app-owned file replacement')
   runtime=root(g)/target.lstrip('/')
   if runtime.exists() and sha(runtime)!=values[name]:raise RuntimeError('Crypto identity changed; refusing stale overwrite')
def binary(g):
 if not pathlib.Path(BIN).is_file() or sha(pathlib.Path(BIN))!=PIN:raise RuntimeError('Pinned official Vault2.1.2 binary required on Proxmox')
 p=root(g)/BIN.lstrip('/')
 if p.exists():
  if sha(p)!=PIN:raise RuntimeError('Existing guest Vault binary differs')
 else:
  run(['pct','exec',str(g),'--','mkdir','-p',str(pathlib.Path(BIN).parent)])
  run(['pct','push',str(g),BIN,BIN+'.new','--perms','0755'],timeout=300)
  if sha(root(g)/(BIN+'.new').lstrip('/'))!=PIN:raise RuntimeError('Transferred vendor checksum mismatch')
  run(['pct','exec',str(g),'--','mv',BIN+'.new',BIN])
def push(g,src,dest,mode='0600'):run(['pct','push',str(g),str(src),dest,'--perms',mode])
def active(g,service):return subprocess.run(['pct','exec',str(g),'--','rc-service',service,'status'],capture_output=True,timeout=20).returncode==0
def install(g,id,db_host):
 bootstrap_required(g,id)
 if id==CF and not (root(g)/'etc/vault-agent'/CF/'allow-start').is_file():raise RuntimeError('Existing tunnel restoration/start marker required; no implicit new-connector bootstrap')
 binary(g);conf='/etc/vault-agent/'+id+'/config';run(['pct','exec',str(g),'--','mkdir','-p',conf]);run(['pct','exec',str(g),'--','chmod','700',conf])
 push(g,HERE/'configs'/id/'agent.hcl',conf+'/agent.hcl')
 if id==API:
  push(g,HERE/'render-rsa.py',conf+'/render-rsa.py');push(g,HERE/'migration.hcl',conf+'/migration.hcl')
  text=(HERE/'init/wallettracker').read_text();text=re.sub(r'^export WALLET_TRACKER_DB_HOST=.*$', 'export WALLET_TRACKER_DB_HOST='+db_host,text,flags=re.M)
  temporary=pathlib.Path('/run')/('wallet-init-'+str(g)+'-'+str(os.getpid()));temporary.write_text(text);temporary.chmod(0o600)
  try:push(g,temporary,'/etc/init.d/wallettracker','0755')
  finally:temporary.unlink()
  service='wallettracker'
 else:
  if not (root(g)/'usr/bin/cloudflared').is_file():raise RuntimeError('Approved cloudflared binary required; never download latest during apply')
  push(g,HERE/'init/cloudflared-wallettracker','/etc/init.d/cloudflared','0755');service='cloudflared'
 run(['pct','exec',str(g),'--','rc-update','add',service,'default'])
 if not active(g,service):run(['pct','exec',str(g),'--','rc-service',service,'start'])
def backup(db_guest):
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');base=pathlib.Path('/var/backups/wallettracker-delivery')/stamp;base.mkdir(parents=True,mode=0o700,exist_ok=False)
 dest=base/'database.sql.gz'
 with dest.open('xb') as f:
  p=subprocess.Popen(['pct','exec',str(db_guest),'--','mariadb-dump','--all-databases','--single-transaction','--routines','--events','--triggers','--hex-blob'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  with gzip.GzipFile(fileobj=f,mode='wb') as zipped:
   for b in iter(lambda:p.stdout.read(1024*1024),b''):zipped.write(b)
  p.stdout.close();diagnostics=p.stderr.read();code=p.wait(timeout=120)
  if code:raise RuntimeError('Read-only native database backup failed; diagnostics suppressed')
 dest.chmod(0o600)
 with gzip.open(dest,'rb') as f:raw=f.read()
 if not all(v in raw for v in [b'Dump completed on',b'wallet_tracker',b'global_priv']):raise RuntimeError('Native database backup validation failed')
 return str(dest)
def migrate(g,db_guest,db_host):
 bootstrap_required(g,API);saved=backup(db_guest)
 # One Agent at a time: API is stopped before the one-shot migration Agent.
 run(['pct','exec',str(g),'--','rc-service','wallettracker','stop'])
 try:
  environment=['HOME=/root','USER=root','DATABASE_NAME=wallet_tracker','WALLET_TRACKER_DB_USER=root','WALLET_TRACKER_DB_HOST='+db_host,'ENABLE_REGISTER=false','PATH=/usr/bin:/bin:/usr/sbin:/sbin']
  run(['pct','exec',str(g),'--','env','-i']+environment+['timeout','-s','TERM','-k','10','240',BIN,'agent','-config=/etc/vault-agent/'+API+'/config/migration.hcl'],timeout=270)
 finally:run(['pct','exec',str(g),'--','rc-service','wallettracker','start'])
 return saved
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('action',choices=['install-api','install-tunnel','migrate']);a.add_argument('--guest',type=int,required=True);a.add_argument('--db-guest',type=int);a.add_argument('--db-host',default='10.2.0.202');args=a.parse_args()
 if os.getuid()!=0 or not re.fullmatch(r'[0-9.]+',args.db_host):raise RuntimeError('Root and validated numeric DB host required')
 if args.action=='migrate':
  if args.db_guest is None:a.error('--db-guest required')
  result={'action':args.action,'native_readonly_backup':migrate(args.guest,args.db_guest,args.db_host),'runtime_secrets_in_tf':False}
 else:install(args.guest,API if args.action=='install-api' else CF,args.db_host);result={'action':args.action,'guest':args.guest,'runtime_secrets_in_tf':False}
 print(json.dumps(result))
if __name__=='__main__':
 try:main()
 except Exception as e:
  print(json.dumps({'native_delivery':'failed-closed','error_class':type(e).__name__,'reason':str(e) if isinstance(e,RuntimeError) else 'details suppressed'}));raise SystemExit(1)
