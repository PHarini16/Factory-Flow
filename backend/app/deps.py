"""Authentication + authorisation dependencies. Roles are enforced here, server-side."""
import time
from collections import defaultdict, deque

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import decode_token
from app.models import User

bearer = HTTPBearer(auto_error=False)


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired, please log in again")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
    user = db.scalar(select(User).where(User.username == payload.get("sub")))
    if not user or not user.is_active:
        raise HTTPException(401, "User inactive or not found")
    return user


def require_roles(*roles: str):
    allowed = set(roles)

    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(403, f"Role {user.role} is not permitted to perform this action")
        return user
    return dep


# simple in-memory login throttle (per process) - see README for production notes
_attempts: dict[str, deque] = defaultdict(deque)


def login_throttle(request: Request, username: str) -> None:
    limit = get_settings().login_rate_limit
    key = f"{request.client.host if request.client else '?'}:{username.lower()}"
    now = time.time()
    q = _attempts[key]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many login attempts. Try again in a minute.")
    q.append(now)


def reset_throttle() -> None:
    _attempts.clear()


ALL = ("OWNER", "ADMIN", "SALESMAN", "PRODUCTION", "ACCOUNTANT")
FIN_READ = ("OWNER", "ADMIN", "ACCOUNTANT")
OPS_READ = ("OWNER", "ADMIN", "PRODUCTION", "ACCOUNTANT")
