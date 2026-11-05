"""V2 metadata: auth stays in main; finance data stays in each user's database."""
from db import db


class ApiSession(db.Model):
    __tablename__ = 'ApiSession'
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer().with_variant(db.BigInteger, 'mysql'), db.ForeignKey('User.id'), nullable=False, index=True)
    expires = db.Column(db.BigInteger, nullable=False)
    revoked = db.Column(db.Boolean, nullable=False, default=False)


class RefreshGrant(db.Model):
    __tablename__ = 'RefreshGrant'
    digest = db.Column(db.String(64), primary_key=True)
    session_id = db.Column(db.String(36), db.ForeignKey('ApiSession.id'), nullable=False, index=True)
    used = db.Column(db.Boolean, nullable=False, default=False)


class RateBucket(db.Model):
    __tablename__ = 'RateBucket'
    id = db.Column(db.String(64), primary_key=True)
    hits = db.Column(db.Integer, nullable=False)
    expires = db.Column(db.BigInteger, nullable=False, index=True)


class SyncClock(db.Model):
    __tablename__ = 'SyncClock'
    id = db.Column(db.Integer, primary_key=True)
    revision = db.Column(db.BigInteger, nullable=False, default=0)


class SyncRecord(db.Model):
    __tablename__ = 'SyncRecord'
    id = db.Column(db.String(36), primary_key=True)
    kind = db.Column(db.String(16), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    revision = db.Column(db.BigInteger, nullable=False, unique=True)
    deleted = db.Column(db.Boolean, nullable=False, default=False)
    payload = db.Column(db.JSON, nullable=False)

    def public(self):
        return dict(id=self.id, kind=self.kind, version=self.version,
                    revision=self.revision, deleted=self.deleted, payload=self.payload)


class SyncReceipt(db.Model):
    __tablename__ = 'SyncReceipt'
    id = db.Column(db.String(36), primary_key=True)
    digest = db.Column(db.String(64), nullable=False)
    result = db.Column(db.JSON, nullable=False)
