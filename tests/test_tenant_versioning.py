from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from utils.Multitenant import migrate_new_tenant, create_tenant_user_and_db


def test_new_tenant_runs_real_versioned_migrations():
    user = SimpleNamespace(id=77, db_username='u77', db_password='synthetic-only')
    tenant_app = MagicMock()
    with patch('app.create_app', return_value=tenant_app) as create, patch('utils.Multitenant.migrate_upgrade') as upgrade:
        migrate_new_tenant(user)
    assert create.call_args.kwargs['database_uri'].database.endswith('_u77')
    assert upgrade.call_args.kwargs['directory'].endswith('/migrations_tenant')
    tenant_app.app_context.assert_called_once()


def test_registration_versions_schema_before_caching_engine(app):
    user = SimpleNamespace(id=78, db_username=None, db_password=None, save=MagicMock())
    engine = MagicMock()
    with app.app_context(), patch('utils.Multitenant.db') as database, patch('utils.Multitenant.migrate_new_tenant') as migrate, patch('utils.Multitenant.initialise_tenant_db') as initialize:
        database.engine = engine
        username, password = create_tenant_user_and_db(user)
    assert username == 'u78' and password
    user.save.assert_called_once()
    migrate.assert_called_once_with(user)
    initialize.assert_called_once_with(user)
