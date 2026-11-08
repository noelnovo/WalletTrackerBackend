import unittest
from unittest.mock import patch
import os
import json
import pathlib
import tempfile
import verify_trusted_security as gate


class TrustedSecurityGateTests(unittest.TestCase):
    def evidence(self, **changes):
        return dict(head_sha='a' * 40, status='completed', conclusion='success', event='push',
                    head_branch='dev', path=gate.WORKFLOW, head_repository={'full_name': gate.REPOSITORY},
                    **changes)

    def test_only_exact_source_owned_trusted_success_is_accepted(self):
        run = self.evidence()
        self.assertTrue(gate.trusted(run, 'a' * 40))
        for changes in [{'head_sha': 'b' * 40}, {'conclusion': 'failure'}, {'status': 'in_progress'},
                        {'event': 'pull_request'}, {'head_branch': 'untrusted'}, {'path': 'other.yml'},
                        {'head_repository': {'full_name': 'other/fork'}}]:
            with self.subTest(changes=changes):
                self.assertFalse(gate.trusted(dict(run, **changes), 'a' * 40))

    def test_trusted_gate_requires_upstream_analysis_and_never_uses_network(self):
        env = dict(GITHUB_REPOSITORY=gate.REPOSITORY, GITHUB_EVENT_NAME='push',
                   APPLICATION_RESULT='success', IMAGE_RESULT='success', SECURITY_RESULT='success')
        with patch.dict(os.environ, env, clear=True), patch.object(gate, 'api') as api:
            gate.main()
            api.assert_not_called()
        for key in ['APPLICATION_RESULT', 'IMAGE_RESULT', 'SECURITY_RESULT']:
            with patch.dict(os.environ, dict(env, **{key: 'failure'}), clear=True):
                with self.assertRaises(RuntimeError):
                    gate.main()

    def test_pr_requires_successful_exact_source_scan_not_a_skipped_scan(self):
        run = dict(self.evidence(), id=123, html_url='https://github.com/example/run/123')
        jobs = [{'name': name, 'conclusion': 'success'} for name in
                ['python-tests', 'delivery-tests', 'image-smoke', 'security-analysis']]
        with tempfile.TemporaryDirectory(dir='/tmp/opencode') as directory:
            event = pathlib.Path(directory) / 'event.json'
            event.write_text(json.dumps({'pull_request': {'head': {'sha': 'a' * 40}}}))
            env = dict(GITHUB_REPOSITORY=gate.REPOSITORY, GITHUB_EVENT_NAME='pull_request',
                       GITHUB_EVENT_PATH=str(event), APPLICATION_RESULT='success', IMAGE_RESULT='success')
            with patch.dict(os.environ, env, clear=True):
                with patch.object(gate, 'api', side_effect=[{'workflow_runs': [run]}, {'jobs': jobs}]):
                    gate.main()
                with patch.object(gate, 'api', return_value={'workflow_runs': []}):
                    with self.assertRaises(RuntimeError):
                        gate.main()
                bad = [dict(job, conclusion='skipped') if job['name'] == 'security-analysis' else job for job in jobs]
                with patch.object(gate, 'api', side_effect=[{'workflow_runs': [run]}, {'jobs': bad}]):
                    with self.assertRaises(RuntimeError):
                        gate.main()


if __name__ == '__main__':
    unittest.main()
