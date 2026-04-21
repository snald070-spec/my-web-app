from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
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
    get_current_user, require_admin, validate_password_policy,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from routers import dashboard, users, notices, fees, attendance, league
from logging_config import setup_logging

load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

APP_ENV = (os.environ.get("APP_ENV") or "development").strip().lower()
_is_production = APP_ENV in {"prod", "production"}
_CSP_CONNECT_SRC = os.environ.get("CSP_CONNECT_SRC", "")

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

        if migrated:
            db.commit()

        # Migration: legacy "admin" seed → "master" with known password
        _admin_row = db.query(models.User).filter(models.User.emp_id == "admin").first()
        _master_row = db.query(models.User).filter(models.User.emp_id == "master").first()
        if _admin_row and not _master_row:
            _init_pw = os.environ.get("MASTER_INIT_PASSWORD", "1234")
            _admin_row.emp_id = "master"
            _admin_row.name = "master"
            _admin_row.hashed_password = hash_password(_init_pw)
            _admin_row.is_first_login = False
            _admin_row.temp_password = None
            db.commit()
            logger.info("✅ Migrated admin -> master account")

        if db.query(models.User).count() == 0:
            init_pw = os.environ.get("MASTER_INIT_PASSWORD", "1234")
            admin = models.User(
                emp_id          = "master",
                name            = "master",
                department      = "IT",
                email           = "admin@example.com",
                hashed_password = hash_password(init_pw),
                role            = models.RoleEnum.MASTER,
                is_first_login  = False,
                temp_password   = None,
            )
            db.add(admin)
            db.commit()
            logger.info("✅ Seeded master account. emp_id=master")
    finally:
        db.close()
    yield
    # ── Shutdown (add cleanup here if needed) ─────────────────────────────────


app = FastAPI(
    title="Draw Basketball Team API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)


_CORS_ALWAYS_ALLOWED = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost",
    "https://localhost",
    "capacitor://localhost",
    "ionic://localhost",
}


def _parse_cors_origins() -> list[str]:
    origins: set[str] = set(_CORS_ALWAYS_ALLOWED)

    # Env-specified origins (comma-separated)
    raw = (os.environ.get("CORS_ALLOW_ORIGINS") or "").strip()
    for o in raw.split(","):
        o = o.strip()
        if o:
            origins.add(o)

    # Auto-include SERVER_HOST so public IP is never accidentally dropped
    server_host = (os.environ.get("SERVER_HOST") or "").strip()
    if server_host:
        origins.add(f"http://{server_host}:5173")
        origins.add(f"https://{server_host}:5173")
        origins.add(f"http://{server_host}")
        origins.add(f"https://{server_host}")

    origins_list = sorted(origins)
    logger.info("CORS allowed origins: %s", origins_list)
    return origins_list


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


_API_RATE_LIMIT = int(os.environ.get("API_RATE_LIMIT", "300"))  # requests per IP per minute
_API_RATE_WINDOW = 60
_api_rate_lock = threading.Lock()
_api_rate_buckets: dict[str, dict] = {}
_API_SKIP_PATHS = {"/health", "/"}


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    return forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client.host if request.client else "unknown"
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=(), "
        "usb=(), bluetooth=(), accelerometer=(), gyroscope=()"
    )
    connect_src = f"'self' {_CSP_CONNECT_SRC}".strip()
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; "
        f"script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        f"style-src 'self' 'unsafe-inline'; "
        f"img-src 'self' data: blob: https:; "
        f"connect-src {connect_src}; "
        f"font-src 'self' data:; "
        f"object-src 'none'; "
        f"base-uri 'self'; "
        f"form-action 'self'; "
        f"frame-ancestors 'none';"
    )
    if _is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    return response


@app.middleware("http")
async def global_rate_limit(request: Request, call_next):
    if request.url.path in _API_SKIP_PATHS or request.url.path.startswith("/assets"):
        return await call_next(request)

    ip = _get_client_ip(request)
    now = time.time()

    with _api_rate_lock:
        bucket = _api_rate_buckets.setdefault(ip, {"count": 0, "window_start": now})
        if now - float(bucket["window_start"]) > _API_RATE_WINDOW:
            bucket["count"] = 0
            bucket["window_start"] = now
        bucket["count"] = int(bucket["count"]) + 1
        count = int(bucket["count"])
        if count == 1 and len(_api_rate_buckets) > 10000:
            cutoff = now - _API_RATE_WINDOW * 2
            stale = [k for k, v in _api_rate_buckets.items() if float(v["window_start"]) < cutoff]
            for k in stale:
                del _api_rate_buckets[k]

    if count > _API_RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."},
            headers={"Retry-After": str(_API_RATE_WINDOW)},
        )

    return await call_next(request)


# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    max_age=600,
)

# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "ok"}


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
        "expires_in":    ACCESS_TOKEN_EXPIRE_MINUTES * 60,
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
    if models.canonical_role(current_user.role) == models.RoleEnum.MASTER:
        raise HTTPException(status_code=403, detail="Master account password is locked. Contact the system administrator.")
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


@app.post("/api/auth/refresh")
def refresh_token(current_user: models.User = Depends(get_current_user)):
    """Issue a fresh JWT for a still-valid token (proactive client-side renewal)."""
    token = create_access_token({"sub": current_user.emp_id})
    role = models.canonical_role(current_user.role)
    return {
        "access_token":  token,
        "token_type":    "bearer",
        "expires_in":    ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "emp_id":        current_user.emp_id,
        "name":          current_user.emp_id,
        "department":    current_user.department,
        "division":      current_user.division,
        "email":         current_user.email,
        "role":          role.value,
        "is_first_login": current_user.is_first_login,
        "is_vip":        current_user.is_vip,
    }


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
