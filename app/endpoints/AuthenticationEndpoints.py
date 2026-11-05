import uuid
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request
from utils.Cryptography import generate_private_key, generate_private_key_string, generate_public_key_string, decode_jwt_ignore_expiry, generate_access_token
from utils.Constants import Messages, AuthMessages, UserMessages, TokenMessages
from utils.Multitenant import create_tenant_user_and_db
from utils.ResponseMaker import make_response
from repositories.UserRepository import UserRepository
from models.User import User
from models.RefreshToken import RefreshToken
from db import db
from endpoints.middlewares.AuthMiddleware import token_required
from exceptions.Http import HttpException
from validators.FieldValidator import is_empty
from config import REFRESH_TOKEN_EXPIRY_DAYS, ENABLE_REGISTER


auth_bp = Blueprint('authentication', __name__)

@auth_bp.route("/api/v1/login/", methods=['POST'])
def login():
    try:
        auth = request.get_json()
        if auth:
            user = UserRepository.get_by_username(auth.get('username'))
            
            if user is None:
                return make_response(None, False, UserMessages.USER_NOT_FOUND), 401
            if(UserRepository.check_password(user, auth.get('password'))):
                jti = str(uuid.uuid4())
                token = generate_access_token(user.id, jti)

                refresh_token = RefreshToken(
                    jti=jti,
                    user_id=user.id,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRY_DAYS)
                )
                db.session.add(refresh_token)
                db.session.commit()

                return make_response({'token': token}, True, AuthMessages.LOGGED_IN), 200
            else:
                return make_response(None, False, UserMessages.USER_NOT_FOUND), 401

        return make_response(None, False, Messages.INVALID_REQUEST), 200
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500
    
@auth_bp.route("/api/v1/register/", methods=['POST'])
def register():
    try:
        if ENABLE_REGISTER.lower() != "true":
            return make_response(None, False, Messages.INVALID_REQUEST), 403
            
        data = request.get_json()
        if not data:
            return make_response(None, False, Messages.INVALID_REQUEST), 200
        is_empty(data, ["username", "password"])
            
        new_username = data.get('username')
        password = data.get('password')
            
        if UserRepository.exists(new_username):
            return make_response(None, False, AuthMessages.ALREADY_EXISTS), 200
            
        private_key = generate_private_key() 
        private_keystring = generate_private_key_string(private_key)
        public_keystring = generate_public_key_string(private_key)
            
        new_user = User(
            username = new_username,
            private_key = private_keystring,
            public_key = public_keystring,
            client_public_key = ""
        )

        created_user = UserRepository.create_with_password(new_user, password)
        create_tenant_user_and_db(created_user)

        return make_response(created_user, True, UserMessages.CREATED)
        
    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    except Exception as e:
        db.session.rollback()
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500

    

@auth_bp.route("/api/v1/getUserServerPubKey/", methods=['GET'])
@token_required
def get_user_pub_key(user_id, session, user):
    try:

        if not user_id:
            return make_response(None, False, Messages.INVALID_REQUEST), 200
        return make_response({'userId': user.id, 'publicKey':user.public_key}, True, AuthMessages.FETCHED_SERVER_PUB_KEY), 200
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500
    

@auth_bp.route("/api/v1/setUserClientPubKey/", methods=['POST'])
@token_required
def set_user_pub_key(user_id, session, user):
    try:
        data = request.get_json()

        if not data:
            return make_response(None, False, Messages.INVALID_REQUEST), 200

        pub_key_b64 = data.get('publicKey')
        if not pub_key_b64:
            return make_response(None, False, Messages.INVALID_REQUEST), 200

        if not user_id:
            return make_response(None, False, Messages.INVALID_REQUEST), 200
        
        user.client_public_key = pub_key_b64
        user.save()
        
        return make_response(None, True, AuthMessages.ASSIGNED_SERVER_CLIENT_KEY), 200
    
    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500


@auth_bp.route("/api/v1/refresh/", methods=['POST'])
def refresh():
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith("Bearer "):
            return make_response(None, False, AuthMessages.INVALID_HEADERS), 415

        raw_token = auth_header.split(" ")[1]
        payload = decode_jwt_ignore_expiry(raw_token)

        jti = payload.get('jti')
        if not jti:
            return make_response(None, False, TokenMessages.REFRESH_INVALID), 401

        refresh_token = RefreshToken.query.filter_by(jti=jti).first()
        if not refresh_token:
            return make_response(None, False, TokenMessages.REFRESH_INVALID), 401

        if refresh_token.revoked:
            RefreshToken.query.filter_by(user_id=refresh_token.user_id, revoked=False).update({'revoked': True})
            db.session.commit()
            return make_response(None, False, TokenMessages.REFRESH_INVALID), 401

        if not refresh_token.is_valid():
            return make_response(None, False, TokenMessages.REFRESH_EXPIRED), 401

        user = UserRepository.get_by_id(refresh_token.user_id)
        if not user:
            return make_response(None, False, UserMessages.USER_NOT_FOUND), 401

        new_jti = str(uuid.uuid4())
        original_expiry = refresh_token.expires_at
        refresh_token.revoked = True
        new_refresh_token = RefreshToken(
            jti=new_jti,
            user_id=user.id,
            expires_at=original_expiry
        )
        db.session.add(new_refresh_token)

        RefreshToken.query.filter(
            RefreshToken.user_id == user.id,
            RefreshToken.expires_at < datetime.now(timezone.utc)
        ).delete()

        db.session.commit()

        token = generate_access_token(user.id, new_jti)

        return make_response({'token': token}, True, TokenMessages.REFRESHED), 200

    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500


@auth_bp.route("/api/v1/logout/", methods=['POST'])
def logout():
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith("Bearer "):
            return make_response(None, False, AuthMessages.INVALID_HEADERS), 415

        raw_token = auth_header.split(" ")[1]
        payload = decode_jwt_ignore_expiry(raw_token)

        jti = payload.get('jti')
        if jti:
            refresh_token = RefreshToken.query.filter_by(jti=jti).first()
            if refresh_token and not refresh_token.revoked:
                refresh_token.revoked = True
                db.session.commit()

        return make_response(None, True, TokenMessages.LOGGED_OUT), 200

    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500
