import importlib.util,json,pathlib,subprocess,sys,unittest
from vault_contract import contract
from render_manifests import resources
ROOT=pathlib.Path(__file__).resolve().parents[1]
class DeliveryContract(unittest.TestCase):
    def test_github_is_authoritative_and_gitlab_passive(self):
        workflow=(ROOT/'.github/workflows/backend.yml').read_text()
        self.assertIn('  python-tests:',workflow)
        self.assertIn('  sonarqube:',workflow)
        self.assertIn('when: never',(ROOT/'.gitlab-ci.yml').read_text())
        self.assertNotIn('include:',(ROOT/'.gitlab-ci.yml').read_text())
    def test_network_access_is_owned_by_existing_firewall(self):
        items=resources('dev')
        cfg=next(x for x in items if x['kind']=='ConfigMap' and x['metadata']['name']=='wallettracker-config')['data']
        self.assertNotIn('WALLET_TRACKER_DEV_NETWORKS',cfg)
        self.assertEqual(cfg['WALLET_TRACKER_TRUSTED_PROXIES'],'10.2.0.10/32')
        self.assertEqual(cfg['WALLET_TRACKER_V2_ONLY'],'true')
    def test_dev_vault_readers_use_verified_canonical_staging(self):
        items=resources('dev')
        actual={x['metadata']['name']:(x['spec']['mount'],x['spec']['path']) for x in items if x['kind']=='VaultStaticSecret'}
        self.assertEqual(actual['wallettracker-db'],('downops','apps/wallettracker/dev/runtime'))
        self.assertEqual(actual['wallettracker-rsa'],('downops','apps/wallettracker/dev/rsa'))
        self.assertEqual(actual['wallettracker-signing'],('downops','apps/wallettracker/dev/signing'))
        self.assertEqual(actual['harbor-pull'],('downops','apps/wallettracker/delivery/harbor-pull'))
        c=contract()
        self.assertIsNone(c['new_kv_mount'])
        self.assertNotIn('wallettracker/data/dev/',c['policies']['wallettracker-dev-identity'])
        self.assertIn('downops/data/apps/wallettracker/delivery/argocd-dev',c['policies']['wallettracker-ci-dev'])
        self.assertIn('downops/data/apps/wallettracker/delivery/harbor-ci',c['policies']['wallettracker-ci-dev'])
        self.assertIn('downops/data/apps/wallettracker/delivery/harbor-pull',c['policies']['wallettracker-dev-pull'])
        self.assertNotIn('downops/data/apps/wallettracker/dev/delivery/',str(c['required_input_records']))
        for role in ['wallettracker-dev-identity','wallettracker-dev-database','wallettracker-dev-pull','wallettracker-ci-dev']:
            self.assertNotIn('"wallettracker/data/',c['policies'][role])
    def test_approved_release_uses_canonical_delivery_sources(self):
        from publish import DELIVERY_SECRET_PREFIXES,STATUS_SECRET_PATHS
        self.assertEqual(DELIVERY_SECRET_PREFIXES['dev'],'downops/data/apps/wallettracker/delivery/')
        self.assertEqual(STATUS_SECRET_PATHS['dev'],'downops/data/apps/wallettracker/delivery/argocd-dev')
        self.assertEqual(DELIVERY_SECRET_PREFIXES['prod'],'downops/data/apps/wallettracker/delivery/')
        self.assertEqual(STATUS_SECRET_PATHS['prod'],'downops/data/apps/wallettracker/delivery/argocd-prod')
    def test_legacy_bootstrap_cannot_create_root_engines_or_credentials(self):
        # Bootstrap remains read-only even when desired contracts gain new readers.
        p=subprocess.run([sys.executable,str(ROOT/'delivery/bootstrap_vault.py'),'--apply','--credentials-file','/nonexistent'],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('writes are retired',p.stdout)
    def test_owner_vault_only_backup_policy(self):
        state=json.loads((ROOT/'delivery/environment-state.json').read_text())
        self.assertEqual(state['kubernetes_backup_policy'],'vault-only')
        self.assertFalse(any(state['backup_enabled'].values()))
        for env in ['dev','prod']:
            self.assertFalse(any(r['metadata']['name'] in ['wallettracker-backups','wallettracker-backup'] for r in resources(env)))
    def test_shared_repository_reader_is_gitops_managed_and_grants_stay_additive(self):
        generated=json.loads((ROOT/'k8s/credentials/resources.json').read_text())['items']
        reader=next(x for x in generated if x['kind']=='VaultStaticSecret')
        self.assertEqual((reader['spec']['mount'],reader['spec']['path']),('downops','apps/wallettracker/delivery/gitops-read'))
        policies=contract()['policies']
        retained={
            'wallettracker-prod-database':['downops/data/apps/wallettracker/runtime'],
            'wallettracker-prod-identity':['downops/data/apps/wallettracker/rsa','downops/data/apps/wallettracker/signing'],
            'wallettracker-prod-pull':['wallettracker/data/delivery/harbor-pull'],
            'wallettracker-ci-prod':['wallettracker/data/delivery/harbor-ci','wallettracker/data/delivery/github-mirror','wallettracker/data/delivery/argocd-prod'],
            'wallettracker-repository':['wallettracker/data/delivery/gitops-read','downops/data/apps/wallettracker/delivery/gitops-read'],
        }
        for policy,paths in retained.items():
            for path in paths:self.assertIn('path "'+path+'"',policies[policy])
    def test_no_recovery_and_no_early_jenkins_removal(self):
        plan=json.loads((ROOT/'delivery/migration-plan.json').read_text());self.assertIn('authorization_update',plan);self.assertIn('Jenkins removal before replacement proof',plan['prohibited'])
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
        items=[x for x in resources('prod') if x['kind']=='VaultStaticSecret'];self.assertEqual({x['spec']['path'] for x in items},{'apps/wallettracker/prod/runtime','apps/wallettracker/prod/rsa','apps/wallettracker/prod/signing','apps/wallettracker/delivery/harbor-pull'})
        self.assertTrue(all(x['spec']['mount']=='downops' for x in items))
        config=next(x for x in resources('prod') if x['kind']=='ConfigMap' and x['metadata']['name']=='wallettracker-config')['data']
        self.assertEqual(config['ENABLE_REGISTER'],'false')
        self.assertEqual(config['WALLET_TRACKER_V2_ONLY'],'true')
        self.assertEqual(config['WALLET_TRACKER_REQUIRED_UPGRADE_CHECKPOINT'],'wallettracker-api-v2')
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
    def test_disabled_backup_cannot_deadlock_initial_sync(self):
        state=json.loads((ROOT/'delivery/environment-state.json').read_text())
        for env in ['dev','prod']:
            backup_names={r['metadata']['name'] for r in resources(env) if r['metadata']['name'] in ['wallettracker-backups','wallettracker-backup']}
            self.assertEqual(backup_names,{'wallettracker-backups','wallettracker-backup'} if state['backup_enabled'][env] else set())
    def test_generator_check(self):
        p=subprocess.run([sys.executable,str(ROOT/'delivery/render_manifests.py'),'--check'],capture_output=True);self.assertEqual(p.returncode,0,p.stderr.decode())
if __name__=='__main__':unittest.main()
