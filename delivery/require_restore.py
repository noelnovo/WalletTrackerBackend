"""Fail closed before production schema changes unless an operator marked restore."""
import os,sys,time
sys.path.insert(0,'/app')
# Newly created Pods can briefly precede NetworkPolicy/dataplane convergence.
# Wait for authenticated SQL, never treat a transport failure as restore proof.
from sqlalchemy import create_engine,text
from sqlalchemy.exc import OperationalError
from migrate_all import database_url
probe=create_engine(database_url('mysql'),connect_args={'connect_timeout':5})
try:
    for attempt in range(30):
        try:
            with probe.connect() as connection:connection.execute(text('SELECT 1'))
            break
        except OperationalError:
            if attempt==29:raise SystemExit('Database connectivity did not converge; migration refused') from None
            time.sleep(2)
finally:probe.dispose()
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
