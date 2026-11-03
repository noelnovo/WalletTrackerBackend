import contextlib
import importlib.util
import io
import pathlib
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('check_plan', HERE / 'check_plan.py')
plan_guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan_guard)


class PipelineTests(unittest.TestCase):
    def plan(self, address, actions, mode='managed'):
        return {'resource_changes': [{'address': address, 'mode': mode, 'change': {'actions': actions, 'before': {'password': 'synthetic-secret'}, 'after': {'password': 'synthetic-secret'}}}]}

    def test_guest_and_database_replacement_blocked(self):
        for address in ['proxmox_lxc.api', 'proxmox_lxc.mariadb', 'cloudflare_dns_record.api']:
            with self.assertRaises(RuntimeError), contextlib.redirect_stdout(io.StringIO()):
                plan_guard.check(self.plan(address, ['delete', 'create']))

    def test_empty_state_cannot_create_production(self):
        with self.assertRaises(RuntimeError), contextlib.redirect_stdout(io.StringIO()):
            plan_guard.check(self.plan('proxmox_lxc.api', ['create']))

    def test_release_provisioners_allowed_without_secret_output(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            plan_guard.check(self.plan('null_resource.deploy_api', ['delete', 'create']))
        self.assertNotIn('synthetic-secret', output.getvalue())

    def test_no_blind_apply_retries_or_mutable_release(self):
        text = (HERE.parent / 'Jenkinsfile').read_text()
        self.assertNotIn('retry(', text)
        self.assertNotIn('-auto-approve', text)
        self.assertNotIn(':latest', text)
        self.assertIn('release.tfplan', text)
        self.assertIn('input message:', text)
        self.assertIn('defaultValue: false', text)

    def test_exact_revision_and_frozen_dependencies(self):
        text = (HERE / 'backend.tf').read_text()
        self.assertIn('checkout --detach ${var.source_revision}', text)
        self.assertIn('uv sync --frozen', text)
        self.assertNotIn('merge --ff-only @{u}', text)

    def test_canonical_vault_contract(self):
        text = (HERE.parent / 'Jenkinsfile').read_text()
        self.assertNotIn('HARBOR_HOSTNAME', text)
        self.assertIn('services/harbor/urls', text)
        self.assertIn('https://vault.int.downops.win', text)

    def test_github_cd_rejects_unmatched_webhook(self):
        spec = importlib.util.spec_from_file_location('jenkins_cd', HERE.parent / '.github/scripts/jenkins_cd.py')
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        environment = {'JENKINS_WEBHOOK_URL': 'https://jenkins.example.invalid/generic-webhook-trigger/invoke',
                       'JENKINS_CD_SECRET': 'synthetic-secret', 'SOURCE_BRANCH': 'main',
                       'SOURCE_REVISION': 'a' * 40}
        trigger = mock.MagicMock()
        trigger.__enter__.return_value.read.return_value = b'{"jobs":{}}'
        opener = mock.Mock()
        opener.open.return_value = trigger
        with mock.patch.dict(driver.os.environ, environment, clear=True), \
             mock.patch.object(driver.urllib.request, 'build_opener', return_value=opener), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'did not trigger wallettracker_cd'):
                driver.main()

    def test_oidc_scopes_exclude_application_credentials(self):
        import json
        contract = json.loads((HERE.parent / '.github/vault-auth.json').read_text())
        self.assertEqual(contract['policies']['wallettracker-cd'], ['downops/data/services/jenkins/webhooks/instance-001'])
        for name, role in contract['roles'].items():
            self.assertTrue(role['token_no_default_policy'])
            self.assertEqual(role['token_type'], 'batch')
            self.assertEqual(role['bound_claims']['repository_id'], '910129138')
            self.assertEqual(role['token_max_ttl'], 900)
        for path in contract['policies']['wallettracker-scan']:
            self.assertNotIn('provisioning', path)
            self.assertNotIn('runtime', path)

    def test_periodic_jenkins_token_renewal_is_not_a_deployment(self):
        source = (HERE.parent / 'Jenkinsfile').read_text()
        self.assertIn('vault token renew >/dev/null 2>&1', source)
        self.assertNotIn('vault token renew -self', source)
        self.assertIn("when { expression { env.origin != 'credential-renewal' } }", source)
        workflow = (HERE.parent / '.github/workflows/cd.yml').read_text()
        self.assertIn("cron: '0 8 * * 1'", workflow)

    def test_proxmox_provisioners_use_key_only_and_pin_host_identity(self):
        for name in ['backend.tf', 'database.tf', 'cloudflare.tf']:
            source = (HERE / name).read_text()
            self.assertNotIn('password = data.vault_kv_secret_v2.proxmox', source)
            self.assertEqual(source.count('connection {'), source.count('private_key = file(var.proxmox_ssh_identity_file)'))
            self.assertEqual(source.count('connection {'), source.count('host_key    = var.proxmox_ssh_host_key'))


if __name__ == '__main__':
    unittest.main()
