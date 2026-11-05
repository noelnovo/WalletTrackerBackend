import os
from flask import Flask
from flask_migrate import Migrate
from sqlalchemy import URL
from endpoints.ExpenseEndpoints import expense_bp
from endpoints.ExpenseCategoryEndpoints import expensecategory_bp
from endpoints.AuthenticationEndpoints import auth_bp
from endpoints.HealthEndpoints import health_bp
from endpoints.SeasonEndpoints import season_bp
from endpoints.ImporteEndpoints import importe_bp
from db import db
from config import DATABASE_USERNAME, DATABASE_PASSWORD, DATABASE_HOST, DATABASE_NAME, ENABLE_REGISTER, MAIN_TABLES
from utils.Cryptography import generate_keys_file
from utils.Logger import AppLogger
from runtime_identity import managed_mode, load_managed_identity
from endpoints.V2Auth import v2auth
from endpoints.V2Sync import v2sync
from security import install_security

def _include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in MAIN_TABLES
    return True

def create_app_test(test_config=None):
    app = Flask(__name__)

    app.config.update(test_config)

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(expense_bp)
    app.register_blueprint(expensecategory_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(season_bp)
    app.register_blueprint(importe_bp)
    app.register_blueprint(v2auth)
    app.register_blueprint(v2sync)
    install_security(app)

    return app

def create_app(database_uri=None):

    app = Flask(__name__)
    log_path = os.path.join(os.path.dirname(__file__), "logs", "app.log")
    AppLogger.configure(None if os.environ.get('WALLET_TRACKER_STDOUT_LOG', 'false').lower() == 'true' else log_path)

    if managed_mode():
        private_key, public_key = load_managed_identity()
    else:
        if not (os.path.exists("private_key.pem") and os.path.exists("public_key.pem")):
            generate_keys_file()
        with open('private_key.pem', 'r') as private_file, open('public_key.pem', 'r') as public_file:
            private_key, public_key = private_file.read(), public_file.read()
    
    enable_register = ENABLE_REGISTER.lower() == "true"
    app.config['ENABLE_REGISTER'] = enable_register
    app.config['PRIVATE_KEY'] = private_key
    app.config['PUBLIC_KEY'] = public_key
    connection_string = database_uri if database_uri is not None else URL.create(
        "mysql", username=DATABASE_USERNAME, password=DATABASE_PASSWORD,
        host=DATABASE_HOST, database=DATABASE_NAME,
    )
    app.config['SQLALCHEMY_DATABASE_URI'] = connection_string

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    Migrate(app, db, directory="migrations_main", include_object=_include_object)
    app.register_blueprint(auth_bp)
    app.register_blueprint(expense_bp)
    app.register_blueprint(expensecategory_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(season_bp)
    app.register_blueprint(importe_bp)
    app.register_blueprint(v2auth)
    app.register_blueprint(v2sync)
    install_security(app)

    @app.after_request
    def build_revision(response):
        response.headers['X-WalletTracker-Revision'] = os.environ.get('APP_BUILD_REVISION', 'unknown')
        return response

    return app
