"""Out-of-band bootstrap contract: protected JSON stdin, never Terraform inputs.

Run only through an authorized root SSH stdin channel. No Vault/network client,
password/DB modification, key generation, service action or secret output.
Existing bootstrap values must match; this is not a credential rotation tool.
"""
import argparse,hashlib,json,os,pathlib,re,subprocess,sys,tempfile
os.umask(0o077)
API='native-wallettracker-api';CF='native-cloudflared-wallettracker'
def run(a):
 p=subprocess.run(a,capture_output=True,text=True,timeout=60)
 if p.returncode:raise RuntimeError('Bootstrap operation failed; diagnostics suppressed')
 return p.stdout
def root(g):return pathlib.Path('/proc')/run(['lxc-info','-n',str(g),'-pH']).strip()/'root'
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--guest',type=int,required=True);args=a.parse_args()
 if os.getuid()!=0:raise RuntimeError('Proxmox root required')
 data=json.load(sys.stdin)
 if set(data)-{'roles','rsa_identity'}:raise RuntimeError('Unknown bootstrap field')
 roles=data.get('roles',{});identity=data.get('rsa_identity',{})
 if set(roles)!={API,CF}:raise RuntimeError('Exact two Wallet native roles required')
 if set(identity)!={'private_key.pem','public_key.pem'} or not all(isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) for v in identity.values()):raise RuntimeError('Private original identity hashes required out of band')
 g=args.guest;r=root(g);app=r/'srv/WalletTrackerAPI/app'
 if not (app/'.venv/bin/uwsgi').is_file():raise RuntimeError('Stage application checkout first; fresh VM intentionally fails closed')
 for name in identity:
  p=app/name;target='/run/vault-agent-'+API+'/rsa/'+name
  if p.is_symlink():
   if os.readlink(p)!=target:raise RuntimeError('Unknown key symlink')
  elif p.exists():raise RuntimeError('App-owned key file exists; separate reviewed native identity cutover required')
 with tempfile.TemporaryDirectory(prefix='wallet-bootstrap-',dir='/run') as td:
  tmp=pathlib.Path(td)
  for id,values in roles.items():
   if set(values)!={'role_id','secret_id'} or not all(isinstance(v,str) and v and len(v)<8192 for v in values.values()):raise RuntimeError('Invalid protected role input')
   for d,mode in [('/etc/vault-agent','700'),('/etc/vault-agent/'+id,'711'),('/etc/vault-agent/'+id+'/auth','700')]:
    run(['pct','exec',str(g),'--','mkdir','-p',d]);run(['pct','exec',str(g),'--','chmod',mode,d])
   for key,value in values.items():
    dest='/etc/vault-agent/'+id+'/auth/'+key;old=r/dest.lstrip('/')
    if old.exists() and old.read_bytes()!=value.encode():raise RuntimeError('Existing role differs; explicit auth rotation required')
    f=tmp/(id+'-'+key);f.write_text(value);f.chmod(0o600);run(['pct','push',str(g),str(f),dest,'--perms','0400'])
  conf='/etc/vault-agent/'+API+'/config';run(['pct','exec',str(g),'--','mkdir','-p',conf]);run(['pct','exec',str(g),'--','chmod','700',conf])
  dest=r/conf.lstrip('/')/'rsa-identity.json'
  if dest.exists() and json.loads(dest.read_text())!=identity:raise RuntimeError('Existing private identity differs')
  f=tmp/'identity';f.write_text(json.dumps(identity));f.chmod(0o600);run(['pct','push',str(g),str(f),conf+'/rsa-identity.json','--perms','0600'])
  # For fresh files only. No private bytes are generated or materialized here.
  for name in identity:
   p=app/name
   if not p.is_symlink():run(['pct','exec',str(g),'--','ln','-s','/run/vault-agent-'+API+'/rsa/'+name,'/srv/WalletTrackerAPI/app/'+name])
 print(json.dumps({'bootstrap_installed':True,'guest':g,'roles':list(roles),'private_identity_manifest_installed':True,'secret_values_printed':False,'service_actions':False,'database_changes':False}))
if __name__=='__main__':
 try:main()
 except Exception as e:
  print(json.dumps({'bootstrap':'failed-closed','error_class':type(e).__name__,'reason':str(e) if isinstance(e,RuntimeError) else 'details suppressed'}));raise SystemExit(1)
