from unittest import mock
import pytest
from sqlalchemy import URL
import migrate_all
from app import create_app
from db import db


def test_tenant_uri_is_bound_before_sqlalchemy_initialization(keys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'private_key.pem').write_text(keys['private'])
    (tmp_path / 'public_key.pem').write_text(keys['public'])
    target = URL.create('sqlite', database=str(tmp_path / 'tenant.db'))
    app = create_app(database_uri=target)
    with app.app_context():
        assert db.engine.url == target


def test_database_password_special_characters_are_not_url_syntax(monkeypatch):
    monkeypatch.setattr(migrate_all, 'DATABASE_PASSWORD', 'synthetic:p@ss/word?with#chars')
    target = migrate_all.database_url('wallet_tracker_u1')
    assert target.password == 'synthetic:p@ss/word?with#chars'
    assert target.database == 'wallet_tracker_u1'


def test_failed_tenant_migration_fails_the_deployment():
    with mock.patch.object(migrate_all, 'ensure_database_exists'), \
         mock.patch.object(migrate_all, 'get_engine'), \
         mock.patch.object(migrate_all, 'get_tenant_databases', return_value=['wallet_tracker_u1']), \
         mock.patch.object(migrate_all, 'create_app') as factory, \
         mock.patch.object(migrate_all, 'migrate_app', side_effect=[None, RuntimeError('synthetic-secret')]):
        with pytest.raises(RuntimeError, match='Tenant migration failed'):
            migrate_all.main()
        assert factory.call_args.kwargs['database_uri'].database == 'wallet_tracker_u1'


def test_unversioned_database_is_not_silently_stamped():
    app = mock.MagicMock()
    with mock.patch.object(migrate_all, 'needs_stamp', return_value=True), \
         mock.patch.object(migrate_all, 'stamp_head') as stamp, \
         mock.patch.object(migrate_all, 'migrate_upgrade') as upgrade:
        with pytest.raises(RuntimeError, match='approved baseline'):
            migrate_all.migrate_app(app, 'unused', mock.Mock())
        stamp.assert_not_called()
        upgrade.assert_not_called()
