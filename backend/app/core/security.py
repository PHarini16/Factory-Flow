from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_access_token(subject: str, role: str) -> tuple[str, int]:
    s = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=s.access_token_minutes)
    token = jwt.encode({"sub": subject, "role": role, "exp": expires}, s.secret_key, algorithm=s.jwt_algorithm)
    return token, s.access_token_minutes * 60


def decode_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.secret_key, algorithms=[s.jwt_algorithm])
