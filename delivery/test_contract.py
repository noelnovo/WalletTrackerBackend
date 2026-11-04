import importlib.util,json,pathlib,subprocess,sys,unittest
from vault_contract import contract
from render_manifests import resources
ROOT=pathlib.Path(__file__).resolve().parents[1]
class DeliveryContract(unittest.TestCase):
    def test_no_recovery_and_no_early_jenkins_removal(self):
        plan=json.loads((ROOT/'delivery/migration-plan.json').read_text());self.assertFalse(plan['vault_recovery_allowed']);self.assertIn('Jenkins removal before replacement proof',plan['prohibited'])
    def test_database_exact_version_and_persistence(self):
        for env in ['dev','prod']:
            db=next(x for x in resources(env) if x['kind']=='StatefulSet');self.assertEqual(db['spec']['template']['spec']['containers'][0]['image'],'mariadb:11.4.12');self.assertEqual(db['spec']['persistentVolumeClaimRetentionPolicy']['whenDeleted'],'Retain')
    def test_api_fail_closed_secret_keys_and_no_service_account_token(self):
        for env in ['dev','prod']:
            items=resources(env);app=next(x for x in items if x['kind']=='Deployment');pod=app['spec']['template']['spec'];self.assertFalse(pod['automountServiceAccountToken']);self.assertTrue(pod['containers'][0]['securityContext']['readOnlyRootFilesystem']);self.assertEqual(pod['securityContext']['seccompProfile']['type'],'RuntimeDefault')
            cfg=next(x for x in items if x['kind']=='ConfigMap' and x['metadata']['name']=='wallettracker-config')['data'];self.assertEqual(cfg['WALLET_TRACKER_REQUIRE_MANAGED_KEYS'],'true')
    def test_prod_not_started_before_restore(self):
        state=json.loads((ROOT/'delivery/environment-state.json').read_text());items=resources('prod');self.assertEqual(next(x for x in items if x['kind']=='Deployment')['spec']['replicas'],int(state['production_api_enabled']))
        if state['production_api_enabled']:self.assertTrue(state['production_restore_verified'])
        self.assertIn('restore_checkpoint',(ROOT/'delivery/require_restore.py').read_text())
    def test_vso_exact_outputs_exclude_raw_and_no_literals(self):
        for env in ['dev','prod']:
            for x in resources(env):
                self.assertNotEqual(x['kind'],'Secret')
                if x['kind']=='VaultStaticSecret':
                    t=x['spec']['destination']['transformation'];self.assertTrue(t['excludeRaw']);self.assertEqual(t['excludes'],['.*']);self.assertTrue(t['templates'])
    def test_production_canonical_identity_not_copied(self):
        items=[x for x in resources('prod') if x['kind']=='VaultStaticSecret'];self.assertEqual({x['spec']['path'] for x in items},{'apps/wallettracker/runtime','apps/wallettracker/rsa','apps/wallettracker/signing','delivery/harbor-pull'})
    def test_vault_roles_exact_namespace_no_linux_password_grants(self):
        c=contract()
        for name,role in c['roles'].items():
            if name.startswith('jwt/'):
                self.assertTrue(role['bound_subject'].startswith('system:serviceaccount:'));self.assertNotIn('*',role['bound_subject']);self.assertEqual(role['bound_audiences'],['vault-vso'])
        self.assertNotIn('lxc-root-passwords',json.dumps(c));self.assertNotIn('jenkins',json.dumps(c))
    def test_no_automatic_prod_sync_and_project_namespace_isolation(self):
        for env in ['dev','prod']:
            app=json.loads((ROOT/'argocd'/(env+'.yaml')).read_text());self.assertEqual(app['spec']['project'],'wallettracker-'+env)
            if env=='prod':self.assertNotIn('automated',app['spec']['syncPolicy'])
        projects=json.loads((ROOT/'bootstrap/projects.json').read_text())['items']
        for x in projects:
            self.assertEqual(len(x['spec']['destinations']),1);self.assertEqual(x['spec']['clusterResourceWhitelist'],[])
    def test_ci_no_cluster_mutation_or_credential_argv(self):
        text=(ROOT/'delivery/publish.py').read_text();self.assertNotIn('kubectl',text);self.assertNotIn('insecureIgnoreHostKey',text);self.assertIn('StrictHostKeyChecking=yes',text);self.assertIn('--password-stdin',text);self.assertIn('CI_JOB_TOKEN',text);self.assertIn('argocd.int.downops.win/api/webhook',text)
    def test_deployment_uses_immutable_reference_and_manual_backup_enable(self):
        for env in ['dev','prod']:
            for x in resources(env):
                if x['kind']=='CronJob':self.assertEqual(x['spec']['suspend'],not json.loads((ROOT/'delivery/environment-state.json').read_text())['backup_enabled'][env])
            self.assertNotIn(':latest',json.dumps(resources(env)))
    def test_generator_check(self):
        p=subprocess.run([sys.executable,str(ROOT/'delivery/render_manifests.py'),'--check'],capture_output=True);self.assertEqual(p.returncode,0,p.stderr.decode())
if __name__=='__main__':unittest.main()
