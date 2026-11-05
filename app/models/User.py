from db import db
from models.BaseModel import BaseModel

class User(db.Model, BaseModel):
    __tablename__ = "User"

    #TODO uses int in sqlite but bigint in mysql (testing uses sqlite)
    id = db.Column(db.Integer().with_variant(db.BigInteger, "mysql"), primary_key=True, autoincrement=True)
    username = db.Column(db.String(255), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    salt = db.Column(db.String(64), nullable=False)
    private_key = db.Column(db.Text, nullable=False)
    public_key = db.Column(db.Text, nullable=False)
    client_public_key = db.Column(db.Text, nullable=True)
    db_username = db.Column(db.String(255), nullable=True)
    db_password = db.Column(db.String(255), nullable=True)

    def to_json_dict(self):
        # Never serialize database credentials, password hashes, salts or private keys.
        return {"id": self.id, "username": self.username}
