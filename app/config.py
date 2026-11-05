import os

DATABASE_PASSWORD = os.environ.get("DATABASE_ROOT_PASSWORD")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "wallet_tracker")
DATABASE_USERNAME = os.environ.get("WALLET_TRACKER_DB_USER", "root")
DATABASE_HOST = os.environ.get("WALLET_TRACKER_DB_HOST", "db")
SECRET = os.environ.get("WALLET_TRACKER_SECRET", "randomSecret")
ENABLE_REGISTER = os.environ.get("ENABLE_REGISTER", "false")
REFRESH_TOKEN_EXPIRY_DAYS = 30

MAIN_TABLES = {"User", "RefreshToken", "ApiSession", "RefreshGrant", "RateBucket"}
