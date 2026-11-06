"""Fresh release-specific restore proof for the first production API-v2 upgrade."""
import os

API_V2 = 'wallettracker-api-v2'
MAIN_HEAD = 'd2a100000001'
TENANT_HEAD = 'd2b100000001'


def statement(sql):
    from sqlalchemy import text
    return text(sql)


def version(engine):
    with engine.connect() as connection:
        return connection.execute(statement('SELECT version_num FROM alembic_version')).scalar_one()


def already_upgraded(get_engine, database_name, get_tenants):
    main = get_engine(database_name)
    try:
        if version(main) != MAIN_HEAD:
            return False
        for name in get_tenants(main):
            tenant = get_engine(name)
            try:
                if version(tenant) != TENANT_HEAD:
                    return False
            finally:
                tenant.dispose()
        return True
    finally:
        main.dispose()


def require_upgrade_checkpoint(get_engine, database_name, get_tenants):
    target = os.environ.get('WALLET_TRACKER_REQUIRED_UPGRADE_CHECKPOINT')
    if not target:
        return
    if target != API_V2:
        raise RuntimeError('Unknown production upgrade checkpoint')
    if already_upgraded(get_engine, database_name, get_tenants):
        return
    metadata = get_engine('wallettracker_migration_metadata')
    try:
        with metadata.connect() as connection:
            approved = connection.execute(statement(
                'SELECT COUNT(*) FROM release_checkpoint WHERE name=:name '
                'AND restore_verified=1 AND write_freeze_verified=1 '
                'AND backup_created_at >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR '
                'AND approved_at >= backup_created_at'), {'name': target}).scalar_one()
            if approved != 1:
                raise RuntimeError('Fresh production release recovery proof is absent')
    finally:
        metadata.dispose()
