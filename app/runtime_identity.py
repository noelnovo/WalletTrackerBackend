"""Validate managed identity without generating or rotating deployment keys."""
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization

def managed_mode():
    return os.environ.get('WALLET_TRACKER_REQUIRE_MANAGED_KEYS', 'false').lower() == 'true'

def load_managed_identity():
    """Return existing PEM strings; errors never include key/password values."""
    for key in ('DATABASE_ROOT_PASSWORD', 'WALLET_TRACKER_SECRET',
                'WALLET_TRACKER_PRIVATE_KEY_FILE', 'WALLET_TRACKER_PUBLIC_KEY_FILE'):
        if not os.environ.get(key):
            raise RuntimeError('Required managed runtime input is missing: ' + key)
    try:
        private_path = Path(os.environ['WALLET_TRACKER_PRIVATE_KEY_FILE'])
        public_path = Path(os.environ['WALLET_TRACKER_PUBLIC_KEY_FILE'])
        if private_path.stat().st_size > 65536 or public_path.stat().st_size > 65536:
            raise ValueError()
        private_bytes, public_bytes = private_path.read_bytes(), public_path.read_bytes()
        private = serialization.load_pem_private_key(private_bytes, password=None)
        public = serialization.load_pem_public_key(public_bytes)
        if private.public_key().public_numbers() != public.public_numbers():
            raise ValueError()
        return private_bytes.decode('utf-8'), public_bytes.decode('utf-8')
    except Exception:
        raise RuntimeError('Managed RSA identity is absent, invalid or mismatched; refusing key generation') from None
