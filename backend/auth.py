from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
from dotenv import load_dotenv
import bcrypt
import hashlib
import secrets
import threading
import time
import os
import models

load_dotenv()

# ── Secret & config ────────────────────────────────────────────────────────────
_raw_secret = os.environ.get("SECRET_KEY", "")
if not _raw_secret:
    import warnings
    warnings.warn("SECRET_KEY env var not set. Set it in production!", stacklevel=1)
    _raw_secret = "dev-only-insecure-secret-CHANGE-ME"

APP_ENV = (os.environ.get("APP_ENV") or "development").strip().lower()
if APP_ENV in {"prod", "production"} and _raw_secret == "dev-only-insecure-secret-CHANGE-ME":
    raise RuntimeError("SECRET_KEY must be configured in production.")

SECRET_KEY = _raw_secret
ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Password utilities ─────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    """bcrypt hash (use for all new passwords)."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def _is_legacy_sha256(hashed: str) -> bool:
    """SHA-256 hex string: exactly 64 lowercase hex chars."""
    return len(hashed) == 64 and all(c in "0123456789abcdef" for c in hashed)

def verify_password(plain: str, hashed: str) -> tuple[bool, bool]:
    """
    Verify password. Returns (is_valid, needs_upgrade).
    needs_upgrade=True when SHA-256 legacy hash matched — caller must rehash with bcrypt.
    """
    import logging as _l
    try:
        if bcrypt.checkpw(plain.encode(), hashed.encode()):
            return True, False
    except Exception:
        pass
    if _is_legacy_sha256(hashed) and hashlib.sha256(plain.encode()).hexdigest() == hashed:
        _l.getLogger(__name__).warning("SHA-256 legacy hash matched — will upgrade to bcrypt")
        return True, True
    return False, False

def generate_temp_password() -> str:
    """10-char temp password: uppercase + lowercase + digit, no confusable chars."""
    UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    LOWER = "abcdefghjkmnpqrstuvwxyz"
    DIGIT = "123456789"
    chars = UPPER + LOWER + DIGIT
    while True:
        pw = "".join(secrets.choice(chars) for _ in range(10))
        if any(c in UPPER for c in pw) and any(c in LOWER for c in pw) and any(c in DIGIT for c in pw):
            return pw


def validate_password_policy(password: str) -> tuple[bool, str]:
    """Return (is_valid, reason). Minimal beta policy: 10+, upper/lower/digit/special."""
    if len(password or "") < 10:
        return False, "New password must be at least 10 characters."
    if not any(c.isupper() for c in password):
        return False, "New password must include at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "New password must include at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "New password must include at least one number."
    if not any(not c.isalnum() for c in password):
        return False, "New password must include at least one special character."
    return True, ""


# ── Token blacklist (logout) ───────────────────────────────────────────────────
_token_blacklist: dict[str, float] = {}  # token -> exp_timestamp
_blacklist_lock = threading.Lock()


def blacklist_token(token: str) -> None:
    """Add token to blacklist. Self-cleaning: removes expired entries on each call."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        exp = float(payload.get("exp", 0))
    except Exception:
        exp = time.time() + ACCESS_TOKEN_EXPIRE_MINUTES * 60
    now = time.time()
    with _blacklist_lock:
        _token_blacklist[token] = exp
        expired = [t for t, e in _token_blacklist.items() if e < now]
        for t in expired:
            del _token_blacklist[t]


def is_token_blacklisted(token: str) -> bool:
    with _blacklist_lock:
        return token in _token_blacklist


# ── JWT ────────────────────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    import logging as _logging
    _log = _logging.getLogger(__name__)
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if is_token_blacklisted(token):
        raise exc
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        emp_id: str = payload.get("sub")
        if emp_id is None:
            _log.warning("get_current_user: token has no sub claim")
            raise exc
    except JWTError as e:
        _log.warning("get_current_user: JWT decode failed — %s", e)
        raise exc

    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if user is None:
        _log.warning("get_current_user: user not found for emp_id=%r", emp_id)
        raise exc
    if getattr(user, "is_resigned", False):
        _log.warning("get_current_user: resigned user emp_id=%r", emp_id)
        raise exc
    return user


def find_user_by_name_or_id(name_or_id: str, db: Session) -> models.User | None:
    """Find user by emp_id."""
    return db.query(models.User).filter(models.User.emp_id == name_or_id).first()


# ── RBAC dependency guards ─────────────────────────────────────────────────────
def has_admin_access(user: models.User) -> bool:
    return models.canonical_role(user.role) in (models.RoleEnum.MASTER, models.RoleEnum.ADMIN)


def has_master_access(user: models.User) -> bool:
    return models.canonical_role(user.role) == models.RoleEnum.MASTER


def require_admin(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if not has_admin_access(current_user):
        raise HTTPException(status_code=403, detail="Admin or Master access required.")
    return current_user


def require_master(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if not has_master_access(current_user):
        raise HTTPException(status_code=403, detail="Master access required.")
    return current_user

def require_approver_or_admin(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if not has_admin_access(current_user):
        raise HTTPException(status_code=403, detail="Admin or Master access required.")
    return current_user

def is_global_reader(user: models.User) -> bool:
    """VIP / global read-only flag — DB-managed, never hard-coded names."""
    return bool(getattr(user, "is_vip", False))

def require_admin_or_vip(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if not has_admin_access(current_user) and not is_global_reader(current_user):
        raise HTTPException(status_code=403, detail="Access denied.")
    return current_user
