import os
import unittest
import json
import pathlib
import tempfile
from unittest.mock import MagicMock, patch
from devops.database import upgrade_checkpoint


class UpgradeCheckpointTests(unittest.TestCase):
    def setUp(self):
        replacement = patch.object(upgrade_checkpoint, 'statement', side_effect=lambda sql: sql)
        replacement.start()
        self.addCleanup(replacement.stop)

    def test_dev_does_not_need_production_proof(self):
        factory = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            upgrade_checkpoint.require_upgrade_checkpoint(factory, 'fixture', MagicMock())
        factory.assert_not_called()

    def test_unknown_checkpoint_fails_closed(self):
        with patch.dict(os.environ, {'WALLET_TRACKER_REQUIRED_UPGRADE_CHECKPOINT': 'unknown'}, clear=True):
            with self.assertRaises(RuntimeError):
                upgrade_checkpoint.require_upgrade_checkpoint(MagicMock(), 'fixture', MagicMock())

    def test_migrated_schemas_do_not_require_repeating_backup_for_same_upgrade(self):
        factory = MagicMock()
        with patch.dict(os.environ, {'WALLET_TRACKER_REQUIRED_UPGRADE_CHECKPOINT': upgrade_checkpoint.API_V2}, clear=True), \
             patch.object(upgrade_checkpoint, 'already_upgraded', return_value=True):
            upgrade_checkpoint.require_upgrade_checkpoint(factory, 'fixture', MagicMock())
        factory.assert_not_called()

    def test_first_upgrade_requires_release_specific_verified_fresh_checkpoint(self):
        for approved in (0, 1):
            with self.subTest(approved=approved):
                engine = MagicMock()
                connection = engine.connect.return_value.__enter__.return_value
                connection.execute.return_value.scalar_one.return_value = approved
                with patch.dict(os.environ, {'WALLET_TRACKER_REQUIRED_UPGRADE_CHECKPOINT': upgrade_checkpoint.API_V2}, clear=True), \
                     patch.object(upgrade_checkpoint, 'already_upgraded', return_value=False):
                    if approved:
                        upgrade_checkpoint.require_upgrade_checkpoint(lambda _: engine, 'fixture', MagicMock())
                    else:
                        with self.assertRaises(RuntimeError):
                            upgrade_checkpoint.require_upgrade_checkpoint(lambda _: engine, 'fixture', MagicMock())
                sql = str(connection.execute.call_args.args[0])
                self.assertIn('release_checkpoint', sql)
                self.assertIn('restore_verified=1', sql)
                self.assertIn('write_freeze_verified=1', sql)
                self.assertIn('INTERVAL 24 HOUR', sql)
                engine.dispose.assert_called_once()

    def test_every_tenant_must_have_target_version(self):
        main, tenant = MagicMock(), MagicMock()
        factory = lambda name: main if name == 'fixture' else tenant
        for head, expected in ((upgrade_checkpoint.TENANT_HEAD, True), ('c34bd55b3ea7', False)):
            with self.subTest(head=head), patch.object(upgrade_checkpoint, 'version', side_effect=[upgrade_checkpoint.MAIN_HEAD, head]):
                self.assertEqual(upgrade_checkpoint.already_upgraded(factory, 'fixture', lambda _: ['fixture_u1']), expected)

    def test_explicit_schema_only_approval_is_not_restore_evidence(self):
        approval = {'approval_id': 'wallettracker-api-v2-schema-only', 'approved_by': 'owner',
                    'schema_upgrade_authorized': True, 'source_revision': 'a'*40,
                    'database_name': 'wallet_tracker', 'namespace': 'wallettracker-prod',
                    'target_main_head': upgrade_checkpoint.MAIN_HEAD,
                    'target_tenant_head': upgrade_checkpoint.TENANT_HEAD,
                    'backup_requested': False, 'restore_requested': False, 'data_reset': False}
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)/'approval.json'
            path.write_text(json.dumps(approval))
            env = {'APP_BUILD_REVISION': 'a'*40, 'POD_NAMESPACE': 'wallettracker-prod',
                   'WALLET_TRACKER_REQUIRED_UPGRADE_CHECKPOINT': upgrade_checkpoint.API_V2,
                   'WALLET_TRACKER_SCHEMA_UPGRADE_APPROVAL_FILE': str(path)}
            factory = MagicMock()
            with patch.dict(os.environ, env, clear=True), patch.object(upgrade_checkpoint, 'already_upgraded', return_value=False):
                upgrade_checkpoint.require_upgrade_checkpoint(factory, 'wallet_tracker', MagicMock())
            factory.assert_not_called()
            for change in [{'source_revision': 'b'*40}, {'data_reset': True},
                           {'backup_requested': True}, {'schema_upgrade_authorized': False},
                           {'namespace': 'wallettracker-dev'}, {'target_main_head': 'old'}]:
                path.write_text(json.dumps(approval | change))
                with patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(RuntimeError):
                        upgrade_checkpoint.require_schema_only_approval(path, 'wallet_tracker')


if __name__ == '__main__':
    unittest.main()
