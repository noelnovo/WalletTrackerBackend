from datetime import date
from db import db

class BaseModel:

    def save(self, session=None):
        if session is None:
            session = db.session
        session.add(self)
        session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()
        
    def to_json_dict(self):
        result = {}
        for column in self.__table__.columns:
            
            value = getattr(self, column.name)
            if isinstance(value, date):
                value = value.isoformat()
            result[column.name] = value
        return result
    
    def edit(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key) and key not in ("id", "username"):
                setattr(self, key, value)
        
    @classmethod
    def get_all(cls):
        return cls.query.all()

    @classmethod
    def get_by_id(cls, id):
        return cls.query.get(id)

    @classmethod
    def simple_filter(cls, **kwargs):
        return cls.query.filter_by(**kwargs).all()
    
    @classmethod
    def rollback(cls):
        cls.session.rollback()
    
    @classmethod
    def delete_all(cls):
        cls.query.delete()
        cls.query.session.commit()