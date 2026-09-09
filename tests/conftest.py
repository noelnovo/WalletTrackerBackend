import os
import pytest

# Enable registration feature during tests (endpoints read from config at import time)
os.environ.setdefault("ENABLE_REGISTER", "true")

# Ensure `werkzeug.__version__` exists in the test environment so Flask's
# `test_client()` can build a default `User-Agent`. Some Werkzeug releases
# no longer expose `__version__` as a module attribute; read it from
# package metadata as a best-effort fallback.
try:
    import werkzeug
    if not hasattr(werkzeug, "__version__"):
        try:
            import importlib.metadata as _md
        except Exception:
            _md = importlib.metadata
        try:
            werkzeug.__version__ = _md.version("werkzeug")
        except Exception:
            werkzeug.__version__ = "0"
except Exception:
    pass

from app import create_app_test, db
from utils.Cryptography import hash_password, generate_keys_file
from utils.Logger import AppLogger

@pytest.fixture(scope="session", autouse=True)
def configure_logger():
    AppLogger.configure(log_file=None)

@pytest.fixture
def keys(tmp_path):
    private_key_path = tmp_path / "private_key.pem"
    public_key_path = tmp_path / "public_key.pem"
    generate_keys_file(str(tmp_path))
    with open(private_key_path, "r") as f:
        private_key = f.read()
    with open(public_key_path, "r") as f:
        public_key = f.read()
    return {"private": private_key, "public": public_key}


@pytest.fixture
def app(keys, tmp_path):
    db_path = tmp_path / "test.db"
    test_config = {
        "PRIVATE_KEY": keys["private"],
        "PUBLIC_KEY": keys["public"],
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "TESTING": True,
    }

    AppLogger.configure()

    app = create_app_test(test_config)

    with app.app_context():
        from models.User import User
        from models.RefreshToken import RefreshToken
        from models.Expense import Expense
        from models.ExpenseCategory import ExpenseCategory
        from models.Season import Season
        from models.Importe import Importe
        db.create_all()

        hex_hashed_password, hex_salt = hash_password("password123")
        user = User(
            username="testuser",
            password=hex_hashed_password,
            salt=hex_salt,
            private_key=keys["private"],
            public_key=keys["public"],
        )
        db.session.add(user)
        db.session.commit()

        category = ExpenseCategory(name="Groceries")
        category.save()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
