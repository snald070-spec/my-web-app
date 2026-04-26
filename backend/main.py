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
    get_current_user, require_admin, require_master, validate_password_policy,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from routers import dashboard, users, notices, fees, attendance, league, notifications
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


def _ensure_user_profile_columns():
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "birth_year" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN birth_year INTEGER"))
        if "position" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN position VARCHAR(20)"))
        if "avatar_url" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN avatar_url VARCHAR(300)"))
        if "google_id" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN google_id VARCHAR(200)"))
        if "birthday" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN birthday VARCHAR(5)"))
        if "is_profile_complete" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_profile_complete BOOLEAN DEFAULT 1"))
            # Google 신규 가입자 중 birth_year가 없는 경우 미완성으로 표시
            conn.execute(text(
                "UPDATE users SET is_profile_complete = 0 "
                "WHERE google_id IS NOT NULL AND birth_year IS NULL"
            ))
        if "is_approved" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_approved BOOLEAN DEFAULT 1 NOT NULL"))


_ensure_league_team_assignment_columns()
_ensure_user_profile_columns()

# VAPID 키 초기화 (없으면 자동 생성)
try:
    from services.push_service import ensure_vapid_keys
    ensure_vapid_keys()
except Exception as _e:
    logger.warning("VAPID 키 초기화 실패 (push 알림 비활성): %s", _e)


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
    connect_src = f"'self' https://accounts.google.com https://oauth2.googleapis.com https://fcm.googleapis.com {_CSP_CONNECT_SRC}".strip()
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; "
        f"script-src 'self' 'unsafe-inline' 'unsafe-eval' https://accounts.google.com; "
        f"style-src 'self' 'unsafe-inline' https://accounts.google.com; "
        f"img-src 'self' data: blob: https:; "
        f"connect-src {connect_src}; "
        f"font-src 'self' data:; "
        f"object-src 'none'; "
        f"base-uri 'self'; "
        f"form-action 'self'; "
        f"frame-src https://accounts.google.com; "
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
app.include_router(notifications.router)


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
        "name":          user.name,
        "department":    user.department,
        "division":      user.division,
        "email":         user.email,
        "role":          role.value,
        "is_first_login":       user.is_first_login,
        "is_vip":               user.is_vip,
        "birth_year":           user.birth_year,
        "position":             user.position,
        "avatar_url":           user.avatar_url,
        "birthday":             getattr(user, "birthday", None),
        "is_profile_complete":  bool(getattr(user, "is_profile_complete", True)),
    }


@app.get("/api/auth/me")
def me(
    current_user: models.User = Depends(get_current_user),
):
    """Returns the current user's latest profile (including up-to-date role)."""
    role = models.canonical_role(current_user.role)
    return {
        "emp_id":        current_user.emp_id,
        "name":          current_user.name,
        "department":    current_user.department,
        "division":      current_user.division,
        "email":         current_user.email,
        "role":          role.value,
        "is_first_login":       current_user.is_first_login,
        "is_vip":               current_user.is_vip,
        "birth_year":           current_user.birth_year,
        "position":             current_user.position,
        "avatar_url":           current_user.avatar_url,
        "birthday":             getattr(current_user, "birthday", None),
        "is_profile_complete":  bool(getattr(current_user, "is_profile_complete", True)),
        "is_approved":          bool(getattr(current_user, "is_approved", True)),
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


class CompleteProfileRequest(BaseModel):
    name: str
    birth_year: int
    position: str
    birthday: str | None = None   # MM-DD (선택)
    avatar_url: str | None = None  # 선택


_ALLOWED_POSITIONS = {"PG", "SG", "SF", "PF", "C", "F", "G"}


@app.post("/api/auth/complete-profile")
def complete_profile(
    body: CompleteProfileRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Google 신규 가입자 프로필 완성 (이름·출생연도·포지션 필수, 사진·생일 선택)."""
    import re as _re
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력해주세요.")
    if not (1930 <= body.birth_year <= 2015):
        raise HTTPException(status_code=400, detail="올바른 출생연도를 입력해주세요.")
    pos_list = [p.strip() for p in body.position.split(",") if p.strip()]
    if not pos_list or not all(p in _ALLOWED_POSITIONS for p in pos_list):
        raise HTTPException(status_code=400, detail="올바른 포지션을 선택해주세요.")
    if body.birthday and not _re.match(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$", body.birthday):
        raise HTTPException(status_code=400, detail="생일 형식이 올바르지 않습니다. (MM-DD)")

    current_user.name = name
    current_user.birth_year = body.birth_year
    current_user.position = body.position
    if body.birthday:
        current_user.birthday = body.birthday
    if body.avatar_url:
        current_user.avatar_url = body.avatar_url
    current_user.is_profile_complete = True

    try:
        db.commit()
        db.refresh(current_user)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="프로필 저장 중 오류가 발생했습니다.")

    role = models.canonical_role(current_user.role)
    return {
        "access_token":        create_access_token({"sub": current_user.emp_id}),
        "token_type":          "bearer",
        "expires_in":          ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "emp_id":              current_user.emp_id,
        "name":                current_user.name,
        "department":          current_user.department,
        "division":            getattr(current_user, "division", None),
        "email":               current_user.email,
        "role":                role.value,
        "is_first_login":      False,
        "is_vip":              bool(current_user.is_vip),
        "birth_year":          current_user.birth_year,
        "position":            current_user.position,
        "avatar_url":          current_user.avatar_url,
        "birthday":            current_user.birthday,
        "is_profile_complete": True,
        "is_approved":         bool(getattr(current_user, "is_approved", True)),
    }


class GoogleLoginRequest(BaseModel):
    credential: str | None = None    # ID token (구버전 호환)
    access_token: str | None = None  # Access token (모바일 팝업 플로우)


@app.post("/api/auth/google")
def google_login(
    body: GoogleLoginRequest,
    db: Session = Depends(get_db),
):
    """Google OAuth 로그인. ID token 또는 access_token을 검증 후 자체 JWT 발급."""
    google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    if not google_client_id:
        raise HTTPException(status_code=503, detail="Google 로그인이 서버에 설정되지 않았습니다. 관리자에게 문의하세요.")

    if not body.credential and not body.access_token:
        raise HTTPException(status_code=400, detail="Google 인증 정보가 없습니다.")

    if body.credential:
        # ID token 검증 (기존 플로우)
        try:
            from google.oauth2 import id_token as google_id_token
            from google.auth.transport import requests as google_requests
            id_info = google_id_token.verify_oauth2_token(
                body.credential,
                google_requests.Request(),
                google_client_id,
            )
        except Exception as e:
            logger.warning("Google ID token verification failed: %s", e)
            raise HTTPException(status_code=401, detail="Google 인증에 실패했습니다. 다시 시도해주세요.")
    else:
        # Access token 검증 (모바일 팝업 플로우 — FedCM 우회)
        import requests as _http
        try:
            resp = _http.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"access_token": body.access_token},
                timeout=10,
            )
            if not resp.ok:
                raise ValueError(f"tokeninfo status {resp.status_code}")
            id_info = resp.json()
        except Exception as e:
            logger.warning("Google access_token tokeninfo failed: %s", e)
            raise HTTPException(status_code=401, detail="Google 인증에 실패했습니다. 다시 시도해주세요.")
        # 발급 대상 검증
        if id_info.get("azp") != google_client_id and id_info.get("aud") != google_client_id:
            logger.warning("Google tokeninfo azp/aud mismatch: %s", id_info)
            raise HTTPException(status_code=401, detail="Google 토큰 검증에 실패했습니다.")

    google_sub = id_info.get("sub", "")
    google_email = (id_info.get("email") or "").strip().lower()
    google_name = (id_info.get("name") or id_info.get("given_name") or "").strip()

    if not google_sub:
        raise HTTPException(status_code=401, detail="Google 계정 정보를 가져올 수 없습니다.")

    # 1) google_id로 기존 연동 계정 조회
    user = db.query(models.User).filter(models.User.google_id == google_sub).first()

    # 2) google_id 없으면 이메일로 기존 계정 조회 (이메일 연동)
    if not user and google_email:
        user = db.query(models.User).filter(models.User.email == google_email).first()
        if user:
            if getattr(user, "is_resigned", False):
                raise HTTPException(status_code=403, detail="비활성화된 계정입니다. 관리자에게 문의하세요.")
            user.google_id = google_sub
            try:
                db.commit()
            except SQLAlchemyError:
                db.rollback()

    # 3) 계정 없으면 자동 가입
    if not user:
        # emp_id 생성: 이름 기반 (중복 시 B, C, D... 접미사)
        import re
        base = re.sub(r"\s+", "", (google_name or "google").lower().strip()) or "google"
        emp_id = base
        suffix_ord = ord('B')
        while db.query(models.User).filter(models.User.emp_id == emp_id).first():
            emp_id = base + chr(suffix_ord).lower()
            suffix_ord += 1
            if suffix_ord > ord('Z'):
                import secrets
                emp_id = base + secrets.token_hex(3)
                break

        import secrets as _secrets
        user = models.User(
            emp_id=emp_id,
            name=google_name or google_email,
            email=google_email or None,
            department="",
            hashed_password=hash_password(_secrets.token_urlsafe(32)),
            role=models.RoleEnum.GENERAL,
            is_first_login=False,
            google_id=google_sub,
            is_profile_complete=False,
            is_approved=False,
        )
        try:
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info("Google 신규 가입 (승인 대기): emp_id=%s email=%s", user.emp_id, google_email)
            # MASTER 계정에 푸시 알림
            try:
                from services.push_service import send_push_to_all
                send_push_to_all(
                    db,
                    title="🏀 새 회원 가입 신청",
                    body=f"{user.name}님이 Google로 가입을 요청했습니다. 승인이 필요합니다.",
                    url="/admin/users",
                    target_roles=["MASTER"],
                )
            except Exception:
                pass
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(status_code=500, detail="계정 생성 중 오류가 발생했습니다.")

    if getattr(user, "is_resigned", False):
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다. 관리자에게 문의하세요.")

    token = create_access_token({"sub": user.emp_id})
    role = models.canonical_role(user.role)
    return {
        "access_token":   token,
        "token_type":     "bearer",
        "expires_in":     ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "emp_id":         user.emp_id,
        "name":           user.name,
        "department":     user.department,
        "division":       getattr(user, "division", None),
        "email":          user.email,
        "role":           role.value,
        "is_first_login":       False,
        "is_vip":               bool(user.is_vip),
        "birth_year":           user.birth_year,
        "position":             user.position,
        "avatar_url":           user.avatar_url,
        "birthday":             getattr(user, "birthday", None),
        "is_profile_complete":  bool(getattr(user, "is_profile_complete", True)),
        "is_approved":          bool(getattr(user, "is_approved", True)),
    }


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
        "name":          current_user.name,
        "department":    current_user.department,
        "division":      current_user.division,
        "email":         current_user.email,
        "role":          role.value,
        "is_first_login":       current_user.is_first_login,
        "is_vip":               current_user.is_vip,
        "birth_year":           current_user.birth_year,
        "position":             current_user.position,
        "avatar_url":           current_user.avatar_url,
        "birthday":             getattr(current_user, "birthday", None),
        "is_profile_complete":  bool(getattr(current_user, "is_profile_complete", True)),
        "is_approved":          bool(getattr(current_user, "is_approved", True)),
    }


@app.get("/api/admin/pending-approval")
def list_pending_approval(
    master_user: models.User = Depends(require_master),
    db: Session = Depends(get_db),
):
    """Google 가입 후 승인 대기 중인 회원 목록 (MASTER only)."""
    users = (
        db.query(models.User)
        .filter(models.User.is_approved.is_(False), models.User.is_resigned.isnot(True))
        .order_by(models.User.created_at.asc())
        .all()
    )
    return {
        "count": len(users),
        "items": [
            {
                "emp_id": u.emp_id,
                "name": u.name,
                "email": u.email,
                "position": u.position,
                "birth_year": u.birth_year,
                "avatar_url": u.avatar_url,
                "created_at": u.created_at,
                "is_profile_complete": bool(getattr(u, "is_profile_complete", True)),
            }
            for u in users
        ],
    }


@app.post("/api/admin/users/{emp_id}/approve")
def approve_user(
    emp_id: str,
    master_user: models.User = Depends(require_master),
    db: Session = Depends(get_db),
):
    """Google 신규 가입 승인 (MASTER only)."""
    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다.")
    if bool(getattr(user, "is_approved", True)):
        raise HTTPException(status_code=400, detail="이미 승인된 회원입니다.")
    user.is_approved = True
    try:
        db.commit()
        logger.info("회원 승인: actor=%s target=%s", master_user.emp_id, emp_id)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")
    try:
        from services.push_service import send_push_to_all
        send_push_to_all(
            db,
            title="✅ 가입이 승인되었습니다",
            body="Draw Basketball Team에 오신 것을 환영합니다!",
            url="/",
            target_emp_ids=[emp_id],
        )
    except Exception:
        pass
    return {"emp_id": emp_id, "is_approved": True}


@app.post("/api/admin/users/{emp_id}/reject")
def reject_user(
    emp_id: str,
    master_user: models.User = Depends(require_master),
    db: Session = Depends(get_db),
):
    """Google 신규 가입 거절 — 계정 삭제 (MASTER only)."""
    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다.")
    try:
        db.query(models.PushSubscription).filter(models.PushSubscription.emp_id == emp_id).delete(synchronize_session=False)
        db.delete(user)
        db.commit()
        logger.info("회원 가입 거절(삭제): actor=%s target=%s", master_user.emp_id, emp_id)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")
    return {"emp_id": emp_id, "rejected": True}


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
