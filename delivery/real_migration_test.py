"""CI-only real MariaDB main/tenant migration and repeat-upgrade smoke."""
import os,time,pathlib
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
# Rehearse the source-account adoption SQL on this disposable CI service only.
# No live source password, data or account is read or changed.
engine=get_engine(None)
with engine.connect() as c:
    c.execute(text('CREATE DATABASE wallet_tracker'))
    c.execute(text('CREATE TABLE wallet_tracker.User (id INT PRIMARY KEY)'))
    c.execute(text("INSERT INTO mysql.global_priv (Host,User,Priv) SELECT '10.2.0.201',User,Priv FROM mysql.global_priv WHERE User='root' AND Host='%'"));c.commit()
    sql=pathlib.Path(__file__).with_name('adopt-pod-grant.sql').read_text()
    block=sql.split('DELIMITER //',1)[1].split('END//',1)[0]+'END'
    c.exec_driver_sql(block);c.exec_driver_sql('FLUSH PRIVILEGES')
    assert c.execute(text("SELECT COUNT(*) FROM mysql.global_priv WHERE User='root' AND Host='10.42.0.%' AND Priv=(SELECT Priv FROM mysql.global_priv WHERE User='root' AND Host='10.2.0.201')")).scalar()==1
engine.dispose()
print('Real synthetic MariaDB main/tenant idempotence and unchanged account-privilege adoption passed')
