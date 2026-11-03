import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import OperationalError
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from flask_migrate import upgrade as migrate_upgrade
from app import create_app

DATABASE_PASSWORD = os.environ.get("DATABASE_ROOT_PASSWORD")
DATABASE_NAME     = os.environ.get("DATABASE_NAME", "wallet_tracker")
DATABASE_USERNAME = os.environ.get("WALLET_TRACKER_DB_USER", "root")
DATABASE_HOST     = os.environ.get("WALLET_TRACKER_DB_HOST", "db")

MAIN_MIGRATIONS_DIR   = os.path.join(os.path.dirname(__file__), "migrations_main")
TENANT_MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations_tenant")
TENANT_PREFIX         = f"{DATABASE_NAME}_u"


# =======================
# HELPERS
# =======================

def ensure_database_exists():
    """Connect to MySQL server and create DB if missing"""
    server_url = database_url(None)
    engine = create_engine(server_url)

    with engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DATABASE_NAME}`"))
        conn.commit()

    engine.dispose()


def stamp_head(engine, migrations_dir):
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", migrations_dir)
    script = ScriptDirectory.from_config(cfg)
    head_revision = script.get_current_head()

    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        ))

        result = conn.execute(text("SELECT COUNT(*) FROM alembic_version"))
        count = result.scalar()

        if count == 0:
            conn.execute(text(
                f"INSERT INTO alembic_version (version_num) VALUES ('{head_revision}')"
            ))

        conn.commit()


def database_url(db_name):
    return URL.create("mysql", username=DATABASE_USERNAME, password=DATABASE_PASSWORD,
                      host=DATABASE_HOST, database=db_name)


def get_engine(db_name):
    return create_engine(database_url(db_name))


def get_tenant_databases(engine):
    with engine.connect() as conn:
        rows = conn.execute(text("SHOW DATABASES"))
        return [row[0] for row in rows if row[0].startswith(TENANT_PREFIX)]


def needs_stamp(engine):
    try:
        with engine.connect() as conn:
            tables = conn.execute(text("SHOW TABLES")).fetchall()
            table_names = [row[0] for row in tables]
            return len(table_names) > 0 and "alembic_version" not in table_names
    except OperationalError:
        return False


def migrate_app(app, migrations_dir, engine):
    with app.app_context():
        if needs_stamp(engine):
            raise RuntimeError("Unversioned existing database requires an approved baseline; refusing to stamp head")

        migrate_upgrade(directory=migrations_dir)


# ========================
# MAIN
# ========================

def main():
    print("[migrate_all] Ensuring main database exists...")
    ensure_database_exists()

    admin_engine = get_engine(DATABASE_NAME)

    print("[migrate_all] Migrating main DB...")
    app = create_app()
    migrate_app(app, MAIN_MIGRATIONS_DIR, admin_engine)
    print("[migrate_all] Main DB done.")

    tenant_dbs = get_tenant_databases(admin_engine)
    admin_engine.dispose()

    if not tenant_dbs:
        print("[migrate_all] No tenant databases found.")
        return

    print(f"[migrate_all] Migrating {len(tenant_dbs)} tenant database(s)...")

    for db_name in tenant_dbs:
        try:
            tenant_engine = get_engine(db_name)

            # Flask-SQLAlchemy binds the engine at init_app, not at first use.
            tenant_app = create_app(database_uri=database_url(db_name))

            migrate_app(tenant_app, TENANT_MIGRATIONS_DIR, tenant_engine)

            print(f"[migrate_all]   [OK] {db_name}")

        except Exception:
            raise RuntimeError("Tenant migration failed; deployment must not report success") from None
        finally:
            if 'tenant_engine' in locals():
                tenant_engine.dispose()

    print("[migrate_all] Done.")


if __name__ == "__main__":
    main()
