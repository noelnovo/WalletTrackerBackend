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

    return app

def create_app(database_uri=None):

    app = Flask(__name__)
    log_path = os.path.join(os.path.dirname(__file__), "logs", "app.log")
    AppLogger.configure(log_path)

    if not (os.path.exists("private_key.pem") and os.path.exists("public_key.pem")):
        generate_keys_file()
    
    enable_register = ENABLE_REGISTER.lower() == "true"
    app.config['ENABLE_REGISTER'] = enable_register
    app.config['PRIVATE_KEY'] = open('private_key.pem', 'r').read()
    app.config['PUBLIC_KEY'] = open('public_key.pem', 'r').read()
    connectionString = database_uri if database_uri is not None else URL.create(
        "mysql", username=DATABASE_USERNAME, password=DATABASE_PASSWORD,
        host=DATABASE_HOST, database=DATABASE_NAME,
    )
    app.config['SQLALCHEMY_DATABASE_URI'] = connectionString   

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    Migrate(app, db, directory="migrations_main", include_object=_include_object)
    app.register_blueprint(auth_bp)
    app.register_blueprint(expense_bp)
    app.register_blueprint(expensecategory_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(season_bp)
    app.register_blueprint(importe_bp)

    return app

