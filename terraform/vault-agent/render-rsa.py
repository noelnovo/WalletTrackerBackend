"""Thin native startup adapter. No Vault/network client and no key generation.

Agent injects base64 PEM bytes. Existing crypto identity is pinned by a protected
host-local hash manifest, not by source code. Approved cutover must separately
replace the two original application files with exact managed RAM symlinks after
validated durable backups. This adapter never replaces mutable regular app files.
"""
import argparse,base64,hashlib,json,os,pathlib,stat,sys
KEYS={'private_key.pem':'PRIVATE_KEY_BASE64','public_key.pem':'PUBLIC_KEY_BASE64'}
def sha(b):return hashlib.sha256(b).hexdigest()
def inputs(identity):
 data={}
 for name,key in KEYS.items():
  value=os.environ.get(key)
  if not value or len(value)>100000:raise RuntimeError('Missing/oversized injected RSA key')
  raw=base64.b64decode(value,validate=True)
  if len(raw)>65536 or sha(raw)!=identity.get(name):raise RuntimeError('RSA identity differs; explicit identity migration required')
  data[name]=raw
 from cryptography.hazmat.primitives import serialization
 private=serialization.load_pem_private_key(data['private_key.pem'],password=None)
 public=serialization.load_pem_public_key(data['public_key.pem'])
 if private.public_key().public_numbers()!=public.public_numbers():raise RuntimeError('Injected RSA pair does not match')
 return data
def check_app_paths(app,runtime,identity,allow_original):
 for name in KEYS:
  p=app/name;target=runtime/name
  if p.is_symlink():
   if os.readlink(p)!=str(target):raise RuntimeError('Unexpected app key symlink')
   if target.exists() and sha(target.read_bytes())!=identity[name]:raise RuntimeError('Existing runtime key changed unexpectedly')
  elif allow_original and p.is_file():
   if sha(p.read_bytes())!=identity[name]:raise RuntimeError('Original application key changed since capture')
  else:raise RuntimeError('Approved managed RAM symlink required; refusing to overwrite app-owned file')
def atomic_write(path,data):
 temp=path.with_name(path.name+'.new-'+str(os.getpid()))
 fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  os.replace(temp,path)
 finally:
  if temp.exists():temp.unlink()
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--identity-file',type=pathlib.Path,required=True);a.add_argument('--app-dir',type=pathlib.Path,required=True);a.add_argument('--runtime-dir',type=pathlib.Path,required=True);a.add_argument('--verify-only',action='store_true');a.add_argument('--expected',type=pathlib.Path);a.add_argument('--proof',type=pathlib.Path);a.add_argument('command',nargs=argparse.REMAINDER);args=a.parse_args()
 if os.getuid()!=0:raise RuntimeError('Adapter requires original root identity')
 mode=args.identity_file.stat()
 if mode.st_uid!=0 or stat.S_IMODE(mode.st_mode)&0o077:raise RuntimeError('Identity manifest must be root-only')
 identity=json.loads(args.identity_file.read_text())
 if set(identity)!=set(KEYS):raise RuntimeError('Unexpected identity manifest')
 if any(k.startswith('VAULT_') for k in os.environ):raise RuntimeError('Broad Vault environment rejected')
 expected=json.loads(args.expected.read_text()) if args.expected else {}
 for k,want in expected.items():
  if k not in os.environ or sha(os.environ[k].encode())!=want:raise RuntimeError('Preflight environment equality failed')
 data=inputs(identity)
 check_app_paths(args.app_dir,args.runtime_dir,identity,allow_original=args.verify_only)
 if args.verify_only:
  proof={'keys_matched':len(expected),'uid':os.getuid(),'broad_vault_env':False,'rsa_identity_match':True,'rsa_pair_match':True,'application_started':False}
  if args.proof:args.proof.write_text(json.dumps(proof));args.proof.chmod(0o600)
  else:print(json.dumps(proof))
  return
 # All verification completed before touching RAM or executing the application.
 if args.runtime_dir.exists() and args.runtime_dir.is_symlink():raise RuntimeError('Runtime directory must not be a symlink')
 args.runtime_dir.mkdir(parents=True,mode=0o700,exist_ok=True);args.runtime_dir.chmod(0o700)
 if args.runtime_dir.stat().st_uid!=0:raise RuntimeError('Runtime directory must be root-owned')
 for name,raw in data.items():atomic_write(args.runtime_dir/name,raw)
 for key in KEYS.values():os.environ.pop(key,None)
 command=args.command[1:] if args.command[:1]==['--'] else args.command
 if not command or not command[0].startswith('/'):raise RuntimeError('Explicit original foreground command required')
 os.chdir(args.app_dir)
 os.execvpe(command[0],command,dict(os.environ))
if __name__=='__main__':
 try:main()
 except Exception as e:
  print(json.dumps({'rsa_adapter':'refused','error_class':type(e).__name__,'details_suppressed':True}),file=sys.stderr);sys.exit(1)
