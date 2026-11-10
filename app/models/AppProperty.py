"""Server-side configuration values; the client reads them instead of hardcoding."""
from db import db


class AppProperty(db.Model):
    __tablename__ = 'AppProperty'
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.JSON, nullable=False)
