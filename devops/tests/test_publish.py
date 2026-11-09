import os
import pathlib
import unittest
from unittest.mock import patch
from devops.ci import publish


class PublicationBoundaryTests(unittest.TestCase):
    def test_bad_branch_and_unapproved_prod_fail_before_secret_access(self):
        for target, env in [('dev', {'CI_COMMIT_BRANCH': 'main'}),
                            ('prod', {'CI_COMMIT_TAG': 'v0.0.0', 'CI_COMMIT_REF_PROTECTED': 'true'}),
                            ('dev', {'CI_COMMIT_BRANCH': 'dev', 'CI_PIPELINE_SOURCE': 'merge_request_event'})]:
            with self.subTest(target=target, env=env), patch.dict(os.environ, {'CI_COMMIT_SHA': 'a'*40} | env, clear=True), patch.object(publish, 'Vault') as vault:
                with self.assertRaises(RuntimeError):
                    publish.main(target)
                vault.assert_not_called()

    def test_only_tested_image_is_published_not_rebuilt(self):
        source = pathlib.Path(publish.__file__).read_text()
        self.assertNotIn("['docker','build'", source)
        self.assertIn('receipt=verify()', source)
        self.assertIn("['docker','load'", source)
        self.assertIn("['docker','tag'", source)
        self.assertIn('Source superseded', source)

    def test_tooling_layout_keeps_runtime_migration_files_and_sql_separate(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        self.assertTrue((root / 'devops/database/sql/adopt-pod-grant.sql').is_file())
        self.assertFalse(list((root / 'delivery').glob('*.py')))
        self.assertEqual({p.name for p in root.glob('*.md')}, {'README.md'})
        documentation=(root/'README.md').read_text()
        self.assertIn('Cloudflare -->|"Production Service"| Workloads',documentation)
        self.assertIn('no scheduled WalletTracker database backup',' '.join(documentation.split()))
        self.assertIn('not the active deployment runbook',documentation)
        self.assertIn('devops.database.v2_mariadb_smoke', (root / 'devops/database/real_migration_test.py').read_text())
