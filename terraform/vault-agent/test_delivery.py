"""Offline source/lifecycle regression tests. No Terraform apply/Vault/DB access."""
import importlib.util,json,pathlib,re,tempfile,unittest,sys
from unittest import mock
sys.dont_write_bytecode=True
HERE=pathlib.Path(__file__).resolve().parent;TF=HERE.parent
s=importlib.util.spec_from_file_location('native_delivery',HERE/'install.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class DeliveryTests(unittest.TestCase):
 def test_no_application_payload_in_terraform(self):
  text='\n'.join(p.read_text() for p in TF.glob('*.tf'))
  for forbidden in ['MARIADB_ROOT_PASSWORD','SIGN_SECRET_WORD','data.vault_kv_secret_v2.app_common','export DATABASE_ROOT_PASSWORD','cloudflare_zero_trust_tunnel_cloudflared_token','--token ']:self.assertNotIn(forbidden,text)
  used=set(re.findall(r'data\.vault_kv_secret_v2\.app\.data\["([A-Z_]+)"\]',text))
  self.assertEqual(used,{'BACKEND_CONTAINER_PASSWORD','DB_CONTAINER_PASSWORD','CLOUDFLARE_ZONE_ID'})
  self.assertIn('apps/wallettracker/infrastructure',text)
 def test_native_database_guard_has_no_password_ddl(self):
  text=(TF/'database.tf').read_text()
  for bad in ['ALTER USER','IDENTIFIED BY','GRANT ALL','FLUSH PRIVILEGES','mariadb-install-db']:self.assertNotIn(bad,text)
  self.assertIn('SELECT COUNT(*) FROM mysql.global_priv',text)
  self.assertIn('Fresh MariaDB requires separately approved',text)
 def test_public_install_not_plaintext_init(self):
  text=(TF/'backend.tf').read_text()+(TF/'cloudflare.tf').read_text()
  self.assertNotIn('wallettracker_init = <<',text);self.assertNotIn('git -C ${local.repo_path} reset --hard',text)
  self.assertIn('/install.py migrate --guest',text);self.assertIn('10.2.0.4',text)
 def test_migration_uses_same_approle_and_rsa_adapter(self):
  text=(HERE/'migration.hcl').read_text()
  self.assertIn('/'+m.API+'/auth/role_id',text);self.assertIn('render-rsa.py',text);self.assertIn('migrate_all.py',text)
  self.assertIn('restart_on_secret_changes = "never"',text)
  self.assertEqual(text.count('exec {'),1)
 def test_migration_stops_then_one_agent_then_restarts_even_on_failure(self):
  commands=[]
  def execute(args,**kwargs):
   commands.append(args)
   if 'agent' in args:raise RuntimeError('synthetic migration failure')
   return ''
  with mock.patch.object(m,'bootstrap_required'),mock.patch.object(m,'backup',return_value='/protected/backup'),mock.patch.object(m,'run',side_effect=execute):
   with self.assertRaises(RuntimeError):m.migrate(101,102,'10.2.0.202')
  self.assertEqual(commands[0][-2:],['wallettracker','stop']);self.assertEqual(commands[-1][-2:],['wallettracker','start'])
  self.assertEqual(len([c for c in commands if 'agent' in c]),1)
  for command in commands:
   self.assertFalse(any(v.startswith(('DATABASE_ROOT_PASSWORD=','WALLET_TRACKER_SECRET=','PRIVATE_KEY_BASE64=','PUBLIC_KEY_BASE64=')) for v in command))
 def test_missing_bootstrap_fails_closed(self):
  with tempfile.TemporaryDirectory() as td,mock.patch.object(m,'root',return_value=pathlib.Path(td)):
   with self.assertRaisesRegex(RuntimeError,'Out-of-band AppRole bootstrap required'):m.bootstrap_required(101,m.API)
 def test_bootstrap_transport_is_stdin_not_terraform(self):
  text=(HERE/'bootstrap-from-stdin.py').read_text();self.assertIn('json.load(sys.stdin)',text)
  self.assertNotIn('urllib',text);self.assertNotIn('generate_private_key',text)
  self.assertIn('Existing role differs',text)
 def test_cloudflared_start_requires_owner_marker(self):
  text=(HERE/'install.py').read_text();self.assertIn("/CF/'allow-start'",text)
if __name__=='__main__':unittest.main()
