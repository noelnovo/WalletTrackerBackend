import os
from alembic import context
from flask import current_app
from logging.config import fileConfig
from sqlalchemy.engine import make_url

config = context.config

if config.config_file_name is not None and os.path.isfile(config.config_file_name):
    fileConfig(config.config_file_name)

database_url = make_url(current_app.config["SQLALCHEMY_DATABASE_URI"])
config.set_main_option(
    "sqlalchemy.url",
    database_url.render_as_string(hide_password=False).replace("%", "%%")
)

target_metadata = current_app.extensions["migrate"].db.metadata

from config import MAIN_TABLES

def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        return name not in MAIN_TABLES
    return True


def run_migrations_offline():
    context.configure(
        url=current_app.config["SQLALCHEMY_DATABASE_URI"],
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    from sqlalchemy import create_engine
    url = current_app.config["SQLALCHEMY_DATABASE_URI"]
    connectable = create_engine(url)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
