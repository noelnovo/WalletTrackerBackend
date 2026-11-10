import os
import base64
import json
import jwt
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import current_app
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.backends import default_backend
import hashlib
import binascii
from config import SECRET
from utils.Constants import TokenMessages, AuthMessages
from utils.ResponseMaker import make_response
from exceptions.Http import HttpException

def generate_private_key():
    try:
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        return private_key
    except Exception as e:
        raise HttpException(AuthMessages.PRIVATE_KEY_FAILED, 401, e)
    

def generate_private_key_string(private_key):
    try:
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        return base64.b64encode(private_bytes).decode()
    except Exception as e:
        raise HttpException(AuthMessages.PRIVATE_KEY_FAILED, 401, e)
    
    

def generate_public_key_string(private_key):
    try:
        public_key = private_key.public_key()
        public_key_bytes =  public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )
        return base64.b64encode(public_key_bytes).decode()
    except Exception as e:
        raise HttpException(AuthMessages.PUBLIC_KEY_FAILED, 401, e)
    

def generate_keys_file(folder=""):
    try:
        folder_path = Path(folder)
        folder_path.mkdir(parents=True, exist_ok=True)

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        private_path = folder_path / "private_key.pem"
        public_path = folder_path / "public_key.pem"

        with open(private_path, "wb") as private_file:
            private_file.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                )
            )

        public_key = private_key.public_key()
        with open(public_path, "wb") as public_file:
            public_file.write(
                public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )
            )
    except Exception as e:
        raise RuntimeError(f"Failed to generate keys: {e}")
    
    

def hybrid_decryption(encrypted_data, private_key_str):
    try:
        if not encrypted_data:
            return make_response(None, False, AuthMessages.INVALID_PAYLOAD), 401
        
        private_key = serialization.load_pem_private_key(
            base64.b64decode(private_key_str), password=None, backend=default_backend()
        )

        encrypted_aes_key = base64.b64decode(encrypted_data["encrypted_aes_key"])
        iv = base64.b64decode(encrypted_data["iv"])
        ciphertext = base64.b64decode(encrypted_data["ciphertext"])
        tag = base64.b64decode(encrypted_data["tag"])

        aes_key = private_key.decrypt(
            encrypted_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        cipher = Cipher(algorithms.AES(aes_key), modes.GCM(iv, tag), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_bytes = decryptor.update(ciphertext) + decryptor.finalize()
        decrypted_text = decrypted_bytes.decode("utf-8")
        decrypted_json = json.loads(decrypted_text)
        
        return decrypted_json
    except Exception as e:
        raise HttpException(AuthMessages.DECRYPTION_FAILED, 401, e)

def hybrid_encryption(dict, public_key_pem):

    try:
        data = json.dumps(dict)
        aes_key = os.urandom(32)
        iv = os.urandom(12)

        cipher = Cipher(algorithms.AES(aes_key), modes.GCM(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(data.encode("utf-8")) + encryptor.finalize()
        tag = encryptor.tag

        public_key = serialization.load_pem_public_key(base64.b64decode(public_key_pem), backend=default_backend())

        encrypted_aes_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        return {
            "encrypted_aes_key": base64.b64encode(encrypted_aes_key).decode(),
            "iv": base64.b64encode(iv).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "tag": base64.b64encode(tag).decode()
        }
    except Exception as e:
        raise HttpException(AuthMessages.ENCRYPTION_FAILED, 401, e)
    
def sign(private_key_pem):
    try:
        private_key = serialization.load_pem_private_key(base64.b64decode(private_key_pem), password=None, backend=default_backend())
        signature = private_key.sign(
            SECRET.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=32
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode()
    except Exception as e:
        raise HttpException(AuthMessages.SIGNATURE_FAILED, 401, e)
    
    

def verify_signature(public_key_pem, signed_text_bs64):
    try:
        if not signed_text_bs64:
            return make_response(None, False, AuthMessages.INVALID_HEADERS), 415
        
        public_key = serialization.load_pem_public_key(
            base64.b64decode(public_key_pem)
        )
        signature_bytes = base64.b64decode(signed_text_bs64)
        public_key.verify(
            signature_bytes,
            SECRET.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
    except Exception as e:
        raise HttpException(AuthMessages.VERIFICATION_FAILED, 401, e)
            
def decode_jwt(token):
    try:
        payload = jwt.decode(
                token,
                current_app.config['PUBLIC_KEY'],
                algorithms=['RS256']
            )
        return payload
    except jwt.ExpiredSignatureError:
        raise HttpException(TokenMessages.EXPIRED, 401)
    except jwt.InvalidTokenError:
        raise HttpException(TokenMessages.INVALID, 401)

def generate_access_token(user_id: int, jti: str) -> str:
    payload = {
        'user': user_id,
        'jti': jti,
        'exp': datetime.now(timezone.utc) + timedelta(minutes=5)
    }
    return jwt.encode(payload, current_app.config['PRIVATE_KEY'], algorithm='RS256')

def decode_jwt_ignore_expiry(token):
    try:
        payload = jwt.decode(
                token,
                current_app.config['PUBLIC_KEY'],
                algorithms=['RS256'],
                options={"verify_exp": False}
            )
        return payload
    except jwt.InvalidTokenError:
        raise HttpException(TokenMessages.INVALID, 401)

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if salt is None:
        salt = "v2:" + os.urandom(16).hex()
    modern = salt.startswith("v2:")
    salt_bytes = binascii.unhexlify(salt[3:] if modern else salt)

    hashed_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        600000 if modern else 100000
    )

    hashed_password = binascii.hexlify(hashed_bytes).decode("utf-8")
    salt_hex = salt
    return hashed_password, salt_hex
