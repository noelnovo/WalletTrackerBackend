"""CI-only real MariaDB main/tenant migration and repeat-upgrade smoke."""
import os,time
from sqlalchemy import text,inspect
from migrate_all import main,get_engine
if os.environ.get('CI')!='true':raise SystemExit('CI-only synthetic database probe')
name=os.environ['DATABASE_NAME']
if not name.endswith('_ci'):raise SystemExit('Refusing non-CI schema name')
for _ in range(60):
    try:
        engine=get_engine(None)
        with engine.connect() as c:c.execute(text('SELECT 1'))
        engine.dispose();break
    except Exception:time.sleep(2)
else:raise SystemExit('Synthetic MariaDB service did not become ready')
main();engine=get_engine(name)
with engine.begin() as c:c.execute(text('CREATE DATABASE IF NOT EXISTS `'+name+'_u1`'))
engine.dispose();main();main()
for db,tables in [(name,{'User','RefreshToken','alembic_version'}),(name+'_u1',{'Expense','ExpenseCategory','Importe','Season','alembic_version'})]:
    e=get_engine(db);assert set(inspect(e).get_table_names())==tables;e.dispose()
print('Real synthetic MariaDB main/tenant and idempotent migrations passed')
