"""Shared-worker, database-backed throttles. Never trust arbitrary forwarded IPs."""
import hashlib
import ipaddress
import os
import time
from flask import current_app, jsonify, request
from sqlalchemy import delete, insert, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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


def install_security(app):
    app.config.setdefault('MAX_CONTENT_LENGTH', 256 * 1024)
    app.config.setdefault('TRUSTED_PROXY_NETWORKS', [value for value in os.environ.get('WALLET_TRACKER_TRUSTED_PROXIES', '').split(',') if value])
    app.config.setdefault('DEV_ALLOWED_NETWORKS', [value for value in os.environ.get('WALLET_TRACKER_DEV_NETWORKS', '').split(',') if value])

    @app.before_request
    def private_development_api():
        if os.environ.get('WALLET_TRACKER_V2_ONLY', 'false').lower() == 'true' and request.path.startswith('/api/v1/') and not request.path.rstrip('/').endswith(('/health', '/ready')):
            return jsonify(error='Update the development client to API v2'), 410
        networks = app.config['DEV_ALLOWED_NETWORKS']
        if not networks or not request.path.startswith('/api/') or request.path.rstrip('/').endswith(('/health', '/ready')):
            return None
        try:
            address = ipaddress.ip_address(client_address())
            if any(address in ipaddress.ip_network(cidr) for cidr in networks):
                return None
        except ValueError:
            pass
        return jsonify(error='Development API is available only on the private network'), 403

    @app.before_request
    def throttle():
        path = request.path.rstrip('/')
        limits = {'login': (10, 300), 'register': (3, 3600), 'refresh': (30, 300)}
        action = path.rsplit('/', 1)[-1]
        if request.method != 'POST' or action not in limits or not path.startswith(('/api/v1/', '/api/v2/')):
            return None
        if app.config.get('RATE_LIMIT_DISABLED', False) and app.testing:
            return None
        limit, period = limits[action]
        now = int(time.time())
        bucket = now // period
        key = hashlib.sha256(f'{action}:{client_address()}:{bucket}'.encode()).hexdigest()
        table = RateBucket.__table__
        try:
            # Separate transaction: a later auth rollback cannot undo a failed attempt.
            with db.engine.begin() as conn:
                conn.execute(delete(table).where(table.c.expires < now - 3600))
                changed = conn.execute(update(table).where(table.c.id == key, table.c.hits < limit).values(hits=table.c.hits + 1)).rowcount
                if changed:
                    return None
                exists = conn.execute(db.select(table.c.id).where(table.c.id == key)).first()
                if not exists:
                    conn.execute(insert(table).values(id=key, hits=1, expires=(bucket + 1) * period))
                    return None
        except IntegrityError:
            # Concurrent first attempt: retry through the same atomic update.
            with db.engine.begin() as conn:
                if conn.execute(update(table).where(table.c.id == key, table.c.hits < limit).values(hits=table.c.hits + 1)).rowcount:
                    return None
        except SQLAlchemyError:
            return jsonify(error='Authentication temporarily unavailable'), 503
        response = jsonify(error='Too many attempts. Try again later.')
        response.status_code = 429
        response.headers['Retry-After'] = str((bucket + 1) * period - now)
        return response

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
        return response
