import secrets
import threading
from pathlib import Path
from flask_migrate import upgrade as migrate_upgrade
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from db import db
from config import DATABASE_HOST, DATABASE_NAME
from exceptions.Http import HttpException
from utils.Constants import MultitenantMessages
_engine_cache = {}
_lock = threading.Lock()


def construct_db_name(base: str, user_id: int) -> str:
    return f"{base}_u{user_id}"


def construct_db_connection_string(db_username: str, db_password: str, user_id: int) -> str:
    user_dbname = construct_db_name(DATABASE_NAME, user_id)
    return f"mysql://{db_username}:{db_password}@{DATABASE_HOST}/{user_dbname}"


def create_tenant_user_and_db(user) -> tuple[str, str]:
    try:
        admin_engine = db.engine
        user_dbname = construct_db_name(DATABASE_NAME, user.id)
        db_username = f"u{user.id}"
        db_password = secrets.token_urlsafe(16)

        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{user_dbname}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )

            conn.execute(
                text(f"CREATE USER IF NOT EXISTS '{db_username}'@'%' IDENTIFIED BY :pwd"),
                {"pwd": db_password},
            )

            conn.execute(
                text(f"GRANT ALL PRIVILEGES ON `{user_dbname}`.* TO '{db_username}'@'%'")
            )
            conn.execute(text("FLUSH PRIVILEGES"))

        user.db_username = db_username
        user.db_password = db_password
        user.save()
        migrate_new_tenant(user)
        initialise_tenant_db(user)

        return db_username, db_password
    except Exception as e:
        raise HttpException(MultitenantMessages.INIT_TENANT_FAILED, 500, e)
    


def migrate_new_tenant(user):
    # Registration creates an empty tenant database. Apply its real versioned
    # schema, never create_all/stamp an assumed baseline or alter existing data.
    from app import create_app
    uri = construct_db_connection_string(user.db_username, user.db_password, user.id)
    tenant_app = create_app(database_uri=uri)
    with tenant_app.app_context():
        migrate_upgrade(directory=str(Path(__file__).resolve().parents[1] / 'migrations_tenant'))


def initialise_tenant_db(user):
    try:
        with _lock:
            if user.id in _engine_cache:
                return _engine_cache[user.id]

            uri = construct_db_connection_string(user.db_username, user.db_password, user.id)
            eng = create_engine(uri, pool_pre_ping=True, pool_recycle=3600)
            _engine_cache[user.id] = eng

            return eng
    except Exception as e:
        raise HttpException(MultitenantMessages.INIT_TENANT_FAILED, 500, e) 
    
def get_tenant_session(user):
    try:
        eng = initialise_tenant_db(user)
        return scoped_session(sessionmaker(bind=eng))
    except Exception as e:
        raise HttpException(MultitenantMessages.INIT_TENANT_FAILED, 500, e)

        
