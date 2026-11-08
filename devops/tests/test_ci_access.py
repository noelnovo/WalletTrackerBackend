import os
import unittest
from unittest.mock import patch
from devops.ci import ci_access


class ScopedGitLabAccessTests(unittest.TestCase):
    identity = {'GITLAB_CI': 'true', 'CI_PROJECT_ID': '1',
                'CI_PROJECT_PATH': 'downops/wallet-tracker-backend',
                'CI_PIPELINE_SOURCE': 'push', 'VAULT_ID_TOKEN': 'synthetic-jwt'}

    def test_job_token_login_uses_only_the_exact_role(self):
        with patch.dict(os.environ, self.identity, clear=True), patch.object(ci_access, 'request', return_value={'auth': {'client_token': 'synthetic-token'}}) as request:
            vault = ci_access.Vault('wallettracker-ci-dev')
        self.assertEqual(vault.token, 'synthetic-token')
        self.assertEqual(request.call_args.args, ('https://vault.int.downops.win/v1/auth/gitlab-ci/login', 'POST', {'role': 'wallettracker-ci-dev', 'jwt': 'synthetic-jwt'}))

    def test_wrong_project_missing_token_and_merge_requests_cannot_login(self):
        for change in [{'CI_PROJECT_ID': '31'}, {'CI_PROJECT_PATH': 'other/repo'},
                       {'CI_PIPELINE_SOURCE': 'merge_request_event'}, {'VAULT_ID_TOKEN': ''}]:
            with self.subTest(change=change), patch.dict(os.environ, self.identity | change, clear=True), patch.object(ci_access, 'request') as request:
                with self.assertRaises(RuntimeError):
                    ci_access.Vault('wallettracker-ci-dev')
                request.assert_not_called()
