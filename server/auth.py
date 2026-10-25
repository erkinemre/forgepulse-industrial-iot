import hashlib
import hmac
import os
import secrets
import time


def hash_password(password):
    salt = os.urandom(16)
    return salt.hex() + ":" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 250000).hex()


def verify_password(password, encoded):
    salt, digest = encoded.split(":")
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 250000)
    return hmac.compare_digest(candidate, bytes.fromhex(digest))


class Sessions:
    def __init__(self):
        self.tokens = {}

    def create(self, username):
        token = secrets.token_urlsafe(32)
        self.tokens[token] = (username, time.time() + 8 * 3600)
        return token

    def get(self, token):
        value = self.tokens.get(token)
        return value[0] if value and value[1] > time.time() else None
