"""TLS + short-lived access JWTs, rotating opaque refresh grants, no mobile secret."""
import hashlib
import secrets
import time
import uuid
from functools import wraps
import jwt
from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import select
from db import db
from models.Sync import ApiSession, RefreshGrant
from models.User import User
from repositories.UserRepository import UserRepository
from utils.Cryptography import hash_password
from utils.Multitenant import create_tenant_user_and_db

v2auth = Blueprint('v2auth', __name__, url_prefix='/api/v2')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def json_object():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def tokens(session):
    now = int(time.time())
    refresh = secrets.token_urlsafe(32)
    db.session.add(RefreshGrant(digest=digest(refresh), session_id=session.id, used=False))
    access = jwt.encode(dict(sub=str(session.user_id), sid=session.id, iat=now,
                             exp=now + 300, iss='wallettracker', aud='wallettracker-v2',
                             token_use='access'), current_app.config['PRIVATE_KEY'], algorithm='RS256')
    return dict(access_token=access, refresh_token=refresh, expires_in=300, user_id=str(session.user_id))


def authenticated(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            header = request.headers.get('Authorization', '')
            if not header.startswith('Bearer '):
                raise ValueError()
            payload = jwt.decode(header[7:], current_app.config['PUBLIC_KEY'], algorithms=['RS256'],
                                 issuer='wallettracker', audience='wallettracker-v2',
                                 options={'require': ['sub', 'sid', 'iat', 'exp', 'token_use']})
            session = db.session.get(ApiSession, payload['sid'])
            if payload['token_use'] != 'access' or not session or session.revoked or session.expires <= time.time() or str(session.user_id) != payload['sub']:
                raise ValueError()
            g.user = db.session.get(User, session.user_id)
            if not g.user:
                raise ValueError()
            g.api_session = session
        except (jwt.InvalidTokenError, ValueError, KeyError):
            return jsonify(error='Authentication required'), 401
        return function(*args, **kwargs)
    return wrapped


@v2auth.post('/login')
def login():
    data = json_object()
    username, password = data.get('username'), data.get('password')
    if not isinstance(username, str) or not isinstance(password, str) or not 1 <= len(username) <= 128 or not 1 <= len(password) <= 1024:
        return jsonify(error='Invalid credentials'), 401
    user = UserRepository.get_by_username(username)
    # Do comparable password work for unknown users; never disclose account existence.
    if not user:
        hash_password(password)
        return jsonify(error='Invalid credentials'), 401
    if not UserRepository.check_password(user, password):
        return jsonify(error='Invalid credentials'), 401
    session = ApiSession(id=str(uuid.uuid4()), user_id=user.id, expires=int(time.time()) + 30 * 86400, revoked=False)
    db.session.add(session)
    db.session.flush()
    result = tokens(session)
    db.session.commit()
    return jsonify(result)


@v2auth.post('/register')
def register():
    if not current_app.config.get('ENABLE_REGISTER', False):
        return jsonify(error='Registration disabled'), 403
    data = json_object()
    username, password = data.get('username'), data.get('password')
    if not isinstance(username, str) or not 3 <= len(username) <= 128 or username != username.strip() or not isinstance(password, str) or not 12 <= len(password) <= 1024:
        return jsonify(error='Use a username of 3–128 characters and a password of 12–1024 characters'), 400
    if UserRepository.exists(username):
        return jsonify(error='Unable to register this account'), 409
    # Legacy key columns stay intact for existing users. V2 never exchanges keys.
    user = User(username=username, private_key='', public_key='', client_public_key='')
    UserRepository.create_with_password(user, password)
    try:
        create_tenant_user_and_db(user)
    except Exception:
        db.session.rollback()
        current_app.logger.error('Tenant provisioning failed for new account id=%s', user.id)
        return jsonify(error='Account provisioning failed; contact the administrator'), 503
    return jsonify(registered=True), 201


@v2auth.post('/refresh')
def refresh():
    data = json_object()
    raw = data.get('refresh_token')
    if not isinstance(raw, str) or not 32 <= len(raw) <= 256:
        return jsonify(error='Invalid refresh token'), 401
    # Lock session first, then grant, in a consistent order. Concurrent re-use fails closed.
    grant = db.session.get(RefreshGrant, digest(raw))
    if not grant:
        return jsonify(error='Invalid refresh token'), 401
    session = db.session.execute(select(ApiSession).where(ApiSession.id == grant.session_id).with_for_update()).scalar_one()
    grant = db.session.execute(select(RefreshGrant).where(RefreshGrant.digest == digest(raw)).with_for_update().execution_options(populate_existing=True)).scalar_one()
    if grant.used:
        session.revoked = True
        db.session.commit()
        return jsonify(error='Refresh token reused; sign in again'), 401
    if session.revoked or session.expires <= time.time():
        return jsonify(error='Session expired'), 401
    grant.used = True
    result = tokens(session)
    db.session.commit()
    return jsonify(result)


@v2auth.post('/logout')
@authenticated
def logout():
    g.api_session.revoked = True
    db.session.commit()
    return jsonify(logged_out=True)
