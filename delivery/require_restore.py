"""Fail closed before production schema changes unless an operator marked restore."""
import os,sys
sys.path.insert(0,'/app')
if os.environ.get('WALLET_TRACKER_REQUIRE_RESTORE_CHECKPOINT','false').lower()=='true':
    from sqlalchemy import text
    from migrate_all import database_url
    from sqlalchemy import create_engine
    engine=create_engine(database_url('wallettracker_migration_metadata'))
    try:
        with engine.connect() as connection:
            if connection.execute(text('SELECT COUNT(*) FROM restore_checkpoint WHERE id=1')).scalar()!=1:
                raise RuntimeError()
    except Exception:
        raise SystemExit('Approved production restore checkpoint absent; migration refused') from None
    finally:engine.dispose()
from migrate_all import main
main()
