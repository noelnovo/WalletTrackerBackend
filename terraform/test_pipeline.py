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

    def test_github_cd_propagates_jenkins_failure(self):
        spec = importlib.util.spec_from_file_location('jenkins_cd', HERE.parent / '.github/scripts/jenkins_cd.py')
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        environment = {'JENKINS_HOSTNAME': 'jenkins.example.invalid', 'JENKINS_USERNAME': 'test',
                       'JENKINS_API_TOKEN': 'synthetic-secret', 'SOURCE_BRANCH': 'main',
                       'SOURCE_REVISION': 'a' * 40, 'APPLY': 'false'}
        trigger = mock.MagicMock()
        trigger.__enter__.return_value.headers = {'Location': 'https://jenkins.example.invalid/queue/item/1/'}
        queue = mock.MagicMock()
        queue.__enter__.return_value.read.return_value = b'{"executable":{"number":1,"url":"https://jenkins.example.invalid/job/wallettracker_cd/1/"}}'
        build = mock.MagicMock()
        build.__enter__.return_value.read.return_value = b'{"building":false,"result":"FAILURE"}'
        opener = mock.Mock()
        opener.open.side_effect = [trigger, queue, build]
        with mock.patch.dict(driver.os.environ, environment, clear=True), \
             mock.patch.object(driver.urllib.request, 'build_opener', return_value=opener), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'finished with FAILURE'):
                driver.main()

    def test_oidc_scopes_exclude_application_credentials(self):
        import json
        contract = json.loads((HERE.parent / '.github/vault-auth.json').read_text())
        self.assertEqual(contract['policies']['wallettracker-cd'], ['downops/data/services/jenkins/api'])
        for name, role in contract['roles'].items():
            self.assertTrue(role['token_no_default_policy'])
            self.assertEqual(role['token_type'], 'batch')
            self.assertEqual(role['bound_claims']['repository_id'], '910129138')
            self.assertEqual(role['token_max_ttl'], 900)
        for path in contract['policies']['wallettracker-scan']:
            self.assertNotIn('provisioning', path)
            self.assertNotIn('runtime', path)


if __name__ == '__main__':
    unittest.main()
