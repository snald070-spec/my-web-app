from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.requests import Request
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os
import logging
import threading
import time
from pydantic import BaseModel

import models
from database import engine, get_db, Base
from auth import (
    verify_password, create_access_token, hash_password,
    get_current_user, require_admin, generate_temp_password, validate_password_policy,
)
from routers import dashboard, users, notices, fees, attendance, league
from logging_config import setup_logging

load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

# Create all tables on startup
Base.metadata.create_all(bind=engine)


def _ensure_league_team_assignment_columns():
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("league_team_assignments")}
    if "is_captain" in columns:
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE league_team_assignments ADD COLUMN is_captain BOOLEAN NOT NULL DEFAULT 0"))


_ensure_league_team_assignment_columns()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup: seed admin account if no users exist ─────────────────────────
    from database import SessionLocal
    db = SessionLocal()
    try:
        legacy_users = db.query(models.User).all()
        migrated = False
        for row in legacy_users:
            canonical_role = models.canonical_role(row.role)
            if row.emp_id == "admin":
                canonical_role = models.RoleEnum.MASTER
            if row.role != canonical_role:
                row.role = canonical_role
                migrated = True
            # Canonical identity policy: keep legacy name column identical to emp_id.
            if row.name != row.emp_id:
                row.name = row.emp_id
                migrated = True
        if migrated:
            db.commit()

        if db.query(models.User).count() == 0:
            temp_pw = generate_temp_password()
            admin = models.User(
                emp_id          = "admin",
                name            = "admin",
                department      = "IT",
                email           = "admin@example.com",
                hashed_password = hash_password(temp_pw),
                role            = models.RoleEnum.MASTER,
                is_first_login  = True,
                temp_password   = temp_pw,
            )
            db.add(admin)
            db.commit()
            logger.info("✅ Seeded master account. emp_id=admin  temp_password=%s", temp_pw)
    finally:
        db.close()
    yield
    # ── Shutdown (add cleanup here if needed) ─────────────────────────────────


app = FastAPI(
    title="Draw Basketball Team API",
    version="1.0.0",
    lifespan=lifespan,
)


def _parse_cors_origins() -> list[str]:
    raw = (os.environ.get("CORS_ALLOW_ORIGINS") or "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost",
        "https://localhost",
        "capacitor://localhost",
        "ionic://localhost",
    ]


LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "7"))
LOGIN_BLOCK_MINUTES = int(os.environ.get("LOGIN_BLOCK_MINUTES", "10"))
_login_attempts_lock = threading.Lock()
_login_attempts: dict[str, dict[str, float | int]] = {}


def _login_bucket_key(request: Request, username: str) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    ip = (forwarded_for.split(",")[0].strip() if forwarded_for else (request.client.host if request.client else "unknown"))
    return f"{ip}|{(username or '').strip().lower()}"


def _is_login_blocked(bucket_key: str) -> bool:
    now = time.time()
    with _login_attempts_lock:
        bucket = _login_attempts.get(bucket_key)
        if not bucket:
            return False
        blocked_until = float(bucket.get("blocked_until", 0))
        if blocked_until == 0:
            # Still counting failures, not yet blocked
            return False
        if blocked_until <= now:
            # Block period has expired, reset
            _login_attempts.pop(bucket_key, None)
            return False
        return True


def _record_login_failure(bucket_key: str) -> None:
    now = time.time()
    with _login_attempts_lock:
        bucket = _login_attempts.setdefault(bucket_key, {"count": 0, "blocked_until": 0.0})
        bucket["count"] = int(bucket.get("count", 0)) + 1
        if int(bucket["count"]) >= LOGIN_MAX_ATTEMPTS:
            bucket["blocked_until"] = now + (LOGIN_BLOCK_MINUTES * 60)


def _clear_login_failures(bucket_key: str) -> None:
    with _login_attempts_lock:
        _login_attempts.pop(bucket_key, None)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Feature routers ───────────────────────────────────────────────────────────
app.include_router(dashboard.router)
app.include_router(users.router)
app.include_router(notices.router)
app.include_router(fees.router)
app.include_router(attendance.router)
app.include_router(league.router)
# Add more routers here: app.include_router(my_feature.router)


# ── Auth endpoints ────────────────────────────────────────────────────────────
@app.post("/api/auth/login")
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db:   Session = Depends(get_db),
):
    """Standard OAuth2 password flow. Uses emp_id as login identifier. Returns JWT + user profile."""
    bucket_key = _login_bucket_key(request, form.username)
    if _is_login_blocked(bucket_key):
        raise HTTPException(status_code=429, detail="Too many login attempts. Please try again later.")

    # Login identifier is emp_id.
    user = db.query(models.User).filter(models.User.emp_id == form.username).first()
    
    if not user or not verify_password(form.password, user.hashed_password):
        _record_login_failure(bucket_key)
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    if getattr(user, "is_resigned", False):
        raise HTTPException(status_code=403, detail="This account has been deactivated.")

    _clear_login_failures(bucket_key)

    token = create_access_token({"sub": user.emp_id})
    role = models.canonical_role(user.role)
    return {
        "access_token":  token,
        "token_type":    "bearer",
        "emp_id":        user.emp_id,
        "name":          user.emp_id,
        "department":    user.department,
        "division":      user.division,
        "email":         user.email,
        "role":          role.value,
        "is_first_login": user.is_first_login,
        "is_vip":        user.is_vip,
    }


@app.get("/api/auth/me")
def me(
    current_user: models.User = Depends(get_current_user),
):
    """Returns the current user's latest profile (including up-to-date role)."""
    role = models.canonical_role(current_user.role)
    return {
        "emp_id":        current_user.emp_id,
        "name":          current_user.emp_id,
        "department":    current_user.department,
        "division":      current_user.division,
        "email":         current_user.email,
        "role":          role.value,
        "is_first_login": current_user.is_first_login,
        "is_vip":        current_user.is_vip,
    }


@app.post("/api/auth/check-email")
def check_email(body: dict, db: Session = Depends(get_db)):
    """
    Step 1 of 2-step login: check if account exists.
    If account exists → return action='exists'.
    If not found → you could send a temp password email here (stub).
    Searches by email or emp_id.
    """
    email_or_id = (body.get("email") or "").strip()
    user = (
        db.query(models.User)
        .filter(
            (models.User.email == email_or_id) | (models.User.emp_id == email_or_id)
        )
        .first()
    )
    return {"action": "exists" if user else "pending_verification"}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@app.post("/api/auth/change-password")
def change_password(
    body: ChangePasswordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change current user's password. Requires old password for verification."""
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    is_valid, reason = validate_password_policy(body.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=reason)
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from current password.")

    current_user.hashed_password = hash_password(body.new_password)
    current_user.is_first_login  = False
    current_user.temp_password   = None
    try:
        db.commit()
        logger.info("User changed password: emp_id=%s", current_user.emp_id)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")
    return {"message": "Password changed successfully."}


@app.post("/api/auth/skip-password-change")
def skip_password_change(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Password change cannot be skipped in beta-security mode."""
    raise HTTPException(status_code=403, detail="Password change is required on first login.")


# ── Serve built React app (production) ───────────────────────────────────────
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        index = os.path.join(FRONTEND_DIST, "index.html")
        return FileResponse(index)
