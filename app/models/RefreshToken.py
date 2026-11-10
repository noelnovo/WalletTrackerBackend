from datetime import datetime, timezone
from db import db
from models.BaseModel import BaseModel
from utils.TZDateTime import TZDateTime

class RefreshToken(db.Model, BaseModel):
    __tablename__ = "RefreshToken"

    # Uses int in sqlite but bigint in mysql (testing uses sqlite)
    id = db.Column(db.Integer().with_variant(db.BigInteger, "mysql"), primary_key=True, autoincrement=True)
    jti = db.Column(db.String(36), nullable=False, unique=True)
    user_id = db.Column(db.Integer().with_variant(db.BigInteger, "mysql"), db.ForeignKey('User.id'), nullable=False)
    expires_at = db.Column(TZDateTime, nullable=False)
    revoked = db.Column(db.Boolean, nullable=False, default=False)

    def is_valid(self):
        return not self.revoked and self.expires_at > datetime.now(timezone.utc)
