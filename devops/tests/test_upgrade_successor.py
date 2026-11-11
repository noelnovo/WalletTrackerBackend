"""Restart safety for the explicitly reviewed additive AppProperty migration."""
import ast
import pathlib
import unittest
from unittest.mock import patch
from devops.database import upgrade_checkpoint as subject


class UpgradeSuccessorTests(unittest.TestCase):
    def check(self, main_head, tenant_head):
        class Engine:
            def __init__(self,head):self.head=head;self.disposed=False
            def dispose(self):self.disposed=True
        engines={'wallet_tracker':Engine(main_head),'synthetic_tenant':Engine(tenant_head)}
        with patch.object(subject,'version',side_effect=lambda engine:engine.head):
            result=subject.already_upgraded(engines.__getitem__,'wallet_tracker',lambda engine:['synthetic_tenant'])
        self.assertTrue(engines['wallet_tracker'].disposed)
        return result

    def test_existing_v2_baseline_and_reviewed_successor_survive_restart(self):
        self.assertTrue(self.check('d2a100000001','d2b100000001'))
        self.assertTrue(self.check('d2c100000001','d2b100000001'))

    def test_unknown_main_or_tenant_heads_do_not_bypass_the_original_guard(self):
        self.assertFalse(self.check('future-unreviewed-head','d2b100000001'))
        self.assertFalse(self.check('d2c100000001','future-unreviewed-tenant'))

    def test_accepted_successor_is_exactly_the_committed_additive_migration(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        migration=root/'app/migrations_main/versions/d2c100000001_server_properties.py'
        tree=ast.parse(migration.read_text())
        values={node.targets[0].id:ast.literal_eval(node.value) for node in tree.body
                if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name)}
        self.assertEqual('d2a100000001',values['down_revision'])
        self.assertEqual({'d2a100000001',values['revision']},set(subject.UPGRADED_MAIN_HEADS))


if __name__=='__main__':unittest.main()
