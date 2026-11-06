"""Shared-worker, database-backed throttles. Never trust arbitrary forwarded IPs."""
import hashlib
import ipaddress
import os
import time
from flask import current_app, jsonify, request
from sqlalchemy import case, delete
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.Sync import RateBucket


def client_address():
    address = request.remote_addr or 'unknown'
    try:
        peer = ipaddress.ip_address(address)
        trusted = current_app.config.get('TRUSTED_PROXY_NETWORKS', [])
        if any(peer in ipaddress.ip_network(cidr) for cidr in trusted):
            address = str(ipaddress.ip_address(request.headers.get('X-Forwarded-For', '').split(',')[-1].strip()))
    except ValueError:
        pass
    return address


def enforce_api_version():
    probe = request.path.rstrip('/').endswith(('/health', '/ready'))
    if os.environ.get('WALLET_TRACKER_V2_ONLY', 'false').lower() == 'true' and request.path.startswith('/api/v1/') and not probe:
        return jsonify(error='Update WalletTracker to version 3 or newer'), 410
    return None


def consume_bucket(key, now, expires, limit):
    table = RateBucket.__table__
    # Commit cleanup BEFORE upsert: expiry-index gap locks must not deadlock
    # concurrent first attempts. Auth rollbacks cannot undo these transactions.
    with db.engine.begin() as conn:
        conn.execute(delete(table).where(table.c.expires < now - 3600))
    with db.engine.begin() as conn:
        increment = case((table.c.hits <= limit, table.c.hits + 1), else_=table.c.hits)
        values = {'id': key, 'hits': 1, 'expires': expires}
        if conn.dialect.name == 'mysql':
            statement = mysql_insert(table).values(**values).on_duplicate_key_update(hits=increment)
        else:
            statement = sqlite_insert(table).values(**values).on_conflict_do_update(index_elements=['id'], set_={'hits': increment})
        conn.execute(statement)
        hits = conn.execute(db.select(table.c.hits).where(table.c.id == key)).scalar_one()
        return hits <= limit


def throttle():
    path = request.path.rstrip('/')
    limits = {'login': (10, 300), 'register': (3, 3600), 'refresh': (30, 300)}
    action = path.rsplit('/', 1)[-1]
    if request.method != 'POST' or action not in limits or not path.startswith(('/api/v1/', '/api/v2/')):
        return None
    if current_app.config.get('RATE_LIMIT_DISABLED', False) and current_app.testing:
        return None
    limit, period = limits[action]
    now = int(time.time())
    bucket = now // period
    key = hashlib.sha256(f'{action}:{client_address()}:{bucket}'.encode()).hexdigest()
    expires = (bucket + 1) * period
    try:
        if consume_bucket(key, now, expires, limit):
            return None
    except SQLAlchemyError:
        return jsonify(error='Authentication temporarily unavailable'), 503
    response = jsonify(error='Too many attempts. Try again later.')
    response.status_code = 429
    response.headers['Retry-After'] = str(expires - now)
    return response


def security_headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
    return response


def install_security(app):
    app.config.setdefault('MAX_CONTENT_LENGTH', 256 * 1024)
    app.config.setdefault('TRUSTED_PROXY_NETWORKS', [value for value in os.environ.get('WALLET_TRACKER_TRUSTED_PROXIES', '').split(',') if value])
    app.before_request(enforce_api_version)
    app.before_request(throttle)
    app.after_request(security_headers)
