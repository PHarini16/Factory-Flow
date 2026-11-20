from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import Conflict, NotFound
from app.core.security import create_access_token, hash_password, verify_password
from app.deps import get_current_user, login_throttle, require_roles
from app.models import Role, User
from app.schemas import LoginIn, TokenOut, UserIn, UserOut, UserPatch
from app.services.common import audit

auth = APIRouter(prefix="/auth", tags=["auth"])
users = APIRouter(prefix="/users", tags=["users"])


@auth.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    login_throttle(request, body.username)
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        audit(db, None, "LOGIN_FAILED", "User", None, new={"username": body.username})
        db.commit()
        raise HTTPException(401, "Invalid username or password")
    token, ttl = create_access_token(user.username, user.role)
    audit(db, user, "LOGIN", "User", user.id)
    db.commit()
    return TokenOut(access_token=token, expires_in=ttl, user=UserOut.model_validate(user))


@auth.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@users.get("", response_model=list[UserOut])
def list_users(role: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles("OWNER", "ADMIN"))):
    stmt = select(User).order_by(User.id)
    return [u for u in db.scalars(stmt) if not role or u.role == role]


@users.post("", response_model=UserOut, status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), me: User = Depends(require_roles("OWNER"))):
    if db.scalar(select(User).where(User.username == body.username)):
        raise Conflict("Username already exists")
    role = db.scalar(select(Role).where(Role.name == body.role))
    u = User(username=body.username, full_name=body.full_name, email=body.email, password_hash=hash_password(body.password), role_id=role.id)
    db.add(u)
    db.flush()
    audit(db, me, "CREATE", "User", u.id, new={"username": u.username, "role": body.role})
    db.commit()
    return u


@users.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserPatch, db: Session = Depends(get_db), me: User = Depends(require_roles("OWNER"))):
    u = db.get(User, user_id)
    if not u:
        raise NotFound("User not found")
    old = {"role": u.role, "is_active": u.is_active}
    data = body.model_dump(exclude_unset=True)
    if data.get("is_active") is False and u.id == me.id:
        raise Conflict("You cannot deactivate your own account")
    if "password" in data:
        u.password_hash = hash_password(data.pop("password"))
    if "role" in data:
        u.role_id = db.scalar(select(Role).where(Role.name == data.pop("role"))).id
    for k, v in data.items():
        setattr(u, k, v)
    db.flush()
    db.refresh(u)
    audit(db, me, "UPDATE", "User", u.id, old=old, new={"role": u.role, "is_active": u.is_active})
    db.commit()
    return u
