from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from sqlalchemy import or_, asc, desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from pydantic import BaseModel
import logging
import re
import json
import os
import time
from io import BytesIO
from PIL import Image

from auth import require_admin, has_master_access, hash_password, generate_temp_password, get_current_user
from database import get_db
from utils.pagination import paginate
import models

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger(__name__)
def _is_phone_id(emp_id: str) -> bool:
    return bool(re.fullmatch(r"\d{10,15}", emp_id or ""))


def _normalize_phone_id(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _generate_emp_id_from_name(name: str, db: Session) -> str:
    """
    Generate emp_id from user's name.
    If duplicate exists, append B, C, D, etc.
    Example: "Kim Min" -> "kimmin", "kimminB", "kimminC" if duplicates exist.
    """
    base_name = re.sub(r"\s+", "", (name or "").lower().strip())
    if not base_name:
        raise ValueError("Name is required to generate ID.")
    
    # Check if base name is available
    if not db.query(models.User).filter(models.User.emp_id == base_name).first():
        return base_name
    
    # Try appending B, C, D, ... Z
    for suffix_ord in range(ord('B'), ord('Z') + 1):
        suffix_char = chr(suffix_ord)
        emp_id = base_name + suffix_char.lower()
        if not db.query(models.User).filter(models.User.emp_id == emp_id).first():
            return emp_id
    
    # Fallback: if all single suffixes used, try double (BB, BC, ...)
    for suffix_ord in range(ord('B'), ord('Z') + 1):
        for suffix_ord2 in range(ord('B'), ord('Z') + 1):
            suffix = chr(suffix_ord).lower() + chr(suffix_ord2).lower()
            emp_id = base_name + suffix
            if not db.query(models.User).filter(models.User.emp_id == emp_id).first():
                return emp_id
    
    raise ValueError(f"Cannot generate unique ID for name '{name}'. Too many duplicates.")


def _append_audit_log(
    db: Session,
    actor_emp_id: str,
    target_emp_id: str,
    action: str,
    details: dict | None = None,
):
    log = models.UserAuditLog(
        actor_emp_id=actor_emp_id,
        target_emp_id=target_emp_id,
        action=action,
        details=json.dumps(details or {}, ensure_ascii=False),
    )
    db.add(log)


class UserStatusUpdate(BaseModel):
    is_resigned: bool


class UserRoleUpdate(BaseModel):
    role: str


class UserProfileUpdate(BaseModel):
    emp_id: str | None = None
    name: str | None = None
    email: str | None = None
    role: str
    is_vip: bool = False
    birth_year: int | None = None
    position: str | None = None


class UserCreate(BaseModel):
    emp_id: str | None = None
    name: str | None = None
    email: str | None = None
    role: str = "USER"
    is_vip: bool = False


def _rekey_user_references(db: Session, old_emp_id: str, new_emp_id: str):
    if old_emp_id == new_emp_id:
        return

    db.query(models.UserAuditLog).filter(models.UserAuditLog.target_emp_id == old_emp_id).update(
        {models.UserAuditLog.target_emp_id: new_emp_id}, synchronize_session=False
    )
    db.query(models.UserAuditLog).filter(models.UserAuditLog.actor_emp_id == old_emp_id).update(
        {models.UserAuditLog.actor_emp_id: new_emp_id}, synchronize_session=False
    )

    db.query(models.Notice).filter(models.Notice.created_by == old_emp_id).update(
        {models.Notice.created_by: new_emp_id}, synchronize_session=False
    )
    db.query(models.Notice).filter(models.Notice.updated_by == old_emp_id).update(
        {models.Notice.updated_by: new_emp_id}, synchronize_session=False
    )

    db.query(models.MemberProfile).filter(models.MemberProfile.emp_id == old_emp_id).update(
        {models.MemberProfile.emp_id: new_emp_id}, synchronize_session=False
    )
    db.query(models.MemberProfile).filter(models.MemberProfile.updated_by == old_emp_id).update(
        {models.MemberProfile.updated_by: new_emp_id}, synchronize_session=False
    )

    db.query(models.MembershipPayment).filter(models.MembershipPayment.emp_id == old_emp_id).update(
        {models.MembershipPayment.emp_id: new_emp_id}, synchronize_session=False
    )
    db.query(models.MembershipPayment).filter(models.MembershipPayment.marked_by == old_emp_id).update(
        {models.MembershipPayment.marked_by: new_emp_id}, synchronize_session=False
    )

    db.query(models.FeeReminderLog).filter(models.FeeReminderLog.sent_by == old_emp_id).update(
        {models.FeeReminderLog.sent_by: new_emp_id}, synchronize_session=False
    )

    db.query(models.AttendanceEvent).filter(models.AttendanceEvent.created_by == old_emp_id).update(
        {models.AttendanceEvent.created_by: new_emp_id}, synchronize_session=False
    )
    db.query(models.AttendanceVote).filter(models.AttendanceVote.emp_id == old_emp_id).update(
        {models.AttendanceVote.emp_id: new_emp_id}, synchronize_session=False
    )
    db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id == old_emp_id).update(
        {models.LeagueTeamAssignment.emp_id: new_emp_id}, synchronize_session=False
    )
    db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.updated_by == old_emp_id).update(
        {models.LeagueTeamAssignment.updated_by: new_emp_id}, synchronize_session=False
    )
    db.query(models.AttendanceEventSetting).filter(models.AttendanceEventSetting.updated_by == old_emp_id).update(
        {models.AttendanceEventSetting.updated_by: new_emp_id}, synchronize_session=False
    )
    db.query(models.AttendanceReminderLog).filter(models.AttendanceReminderLog.emp_id == old_emp_id).update(
        {models.AttendanceReminderLog.emp_id: new_emp_id}, synchronize_session=False
    )
    db.query(models.AttendanceReminderLog).filter(models.AttendanceReminderLog.sent_by == old_emp_id).update(
        {models.AttendanceReminderLog.sent_by: new_emp_id}, synchronize_session=False
    )

    db.query(models.LeaguePlayerStat).filter(models.LeaguePlayerStat.emp_id == old_emp_id).update(
        {models.LeaguePlayerStat.emp_id: new_emp_id}, synchronize_session=False
    )
    db.query(models.LeaguePlayerStat).filter(models.LeaguePlayerStat.entered_by == old_emp_id).update(
        {models.LeaguePlayerStat.entered_by: new_emp_id}, synchronize_session=False
    )

    db.query(models.LeagueMatch).filter(models.LeagueMatch.confirmed_by == old_emp_id).update(
        {models.LeagueMatch.confirmed_by: new_emp_id}, synchronize_session=False
    )
    db.query(models.LeagueMatch).filter(models.LeagueMatch.updated_by == old_emp_id).update(
        {models.LeagueMatch.updated_by: new_emp_id}, synchronize_session=False
    )

    db.query(models.BankDepositEvent).filter(models.BankDepositEvent.matched_emp_id == old_emp_id).update(
        {models.BankDepositEvent.matched_emp_id: new_emp_id}, synchronize_session=False
    )


def _serialize_user(user: models.User) -> dict:
    role = models.canonical_role(user.role)
    return {
        "emp_id": user.emp_id,
        "name": user.name,
        "email": user.email,
        "role": role.value,
        "is_resigned": bool(user.is_resigned),
        "is_vip": bool(user.is_vip),
        "birth_year": user.birth_year,
        "position": user.position,
        "avatar_url": user.avatar_url,
    }


@router.post("", status_code=201)
def create_user(
    body: UserCreate,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    emp_id = (body.emp_id or body.name or "").strip()
    if not emp_id:
        raise HTTPException(status_code=400, detail="ID is required.")

    if db.query(models.User).filter(models.User.emp_id == emp_id).first():
        raise HTTPException(status_code=409, detail="이미 사용 중인 이름(아이디)입니다.")

    actor_is_master = has_master_access(admin_user)
    role_norm = (body.role or "").upper().strip()
    try:
        role_value = models.RoleEnum(role_norm)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role value.")

    role_value = models.canonical_role(role_value)
    if not actor_is_master and role_value not in (models.RoleEnum.GENERAL, models.RoleEnum.STUDENT):
        raise HTTPException(status_code=403, detail="관리자는 일반/학생 회원만 추가할 수 있습니다.")

    temp_pw = generate_temp_password()
    user = models.User(
        emp_id=emp_id,
        name=(body.name or "").strip() or emp_id,
        department="",
        email=(body.email or "").strip() or None,
        hashed_password=hash_password(temp_pw),
        role=role_value,
        is_first_login=True,
        temp_password=temp_pw,
        is_vip=bool(body.is_vip),
    )

    if not user.emp_id:
        raise HTTPException(status_code=400, detail="ID is required.")

    try:
        _append_audit_log(
            db,
            actor_emp_id=admin_user.emp_id,
            target_emp_id=user.emp_id,
            action="create_user",
            details={"role": user.role.value, "is_vip": user.is_vip},
        )
        db.add(user)
        db.commit()
        logger.info(
            "Admin created user: actor=%s target=%s role=%s",
            admin_user.emp_id,
            user.emp_id,
            user.role,
        )
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "emp_id": user.emp_id,
        "temp_password": temp_pw,
        "message": "User created with temporary password.",
    }


@router.get("/{emp_id}")
def get_user(
    emp_id: str,
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return _serialize_user(user)


@router.get("/{emp_id}/audit")
def get_user_audit_logs(
    emp_id: str,
    limit: int = Query(20, ge=1, le=200),
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.UserAuditLog)
        .filter(models.UserAuditLog.target_emp_id == emp_id)
        .order_by(models.UserAuditLog.created_at.desc(), models.UserAuditLog.id.desc())
        .limit(limit)
        .all()
    )
    items = []
    for r in rows:
        try:
            parsed = json.loads(r.details or "{}")
        except Exception:
            parsed = {"raw": r.details}
        items.append(
            {
                "id": r.id,
                "actor_emp_id": r.actor_emp_id,
                "target_emp_id": r.target_emp_id,
                "action": r.action,
                "details": parsed,
                "created_at": r.created_at,
            }
        )
    return {"items": items, "total": len(items), "skip": 0, "limit": limit}


@router.get("")
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    keyword: str = Query(""),
    role: str = Query("ALL"),
    status: str = Query("ALL"),
    first_login: str = Query("ALL"),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(models.User)

    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(
            or_(
                models.User.emp_id.ilike(like),
                models.User.name.ilike(like),
                models.User.email.ilike(like),
            )
        )

    role_norm = (role or "ALL").upper()
    if role_norm != "ALL":
        try:
            role_value = models.canonical_role(models.RoleEnum(role_norm))
            if role_norm in ("GENERAL", "STUDENT", "USER"):
                q = q.filter(models.User.role.in_(models.MEMBER_ROLE_VALUES if role_value == models.RoleEnum.GENERAL and role_norm == "USER" else (role_value,)))
            else:
                q = q.filter(models.User.role == role_value)
        except ValueError:
            q = q.filter(models.User.emp_id == "__no_match__")

    status_norm = (status or "ALL").upper()
    if status_norm == "ACTIVE":
        q = q.filter(models.User.is_resigned.isnot(True))
    elif status_norm == "INACTIVE":
        q = q.filter(models.User.is_resigned.is_(True))

    first_login_norm = (first_login or "ALL").upper()
    if first_login_norm == "PENDING":
        q = q.filter(models.User.is_first_login.is_(True))
    elif first_login_norm == "COMPLETED":
        q = q.filter(models.User.is_first_login.is_(False))

    sort_map = {
        "created_at": models.User.created_at,
        "emp_id": models.User.emp_id,
        "name": models.User.name,
        "role": models.User.role,
    }
    sort_col = sort_map.get((sort_by or "").strip(), models.User.created_at)
    dir_norm = (sort_dir or "desc").lower().strip()
    q = q.order_by(asc(sort_col) if dir_norm == "asc" else desc(sort_col))

    return paginate(q, skip, limit, _serialize_user)


@router.patch("/{emp_id}/status")
def update_user_status(
    emp_id: str,
    body: UserStatusUpdate,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if models.canonical_role(user.role) == models.RoleEnum.MASTER and not has_master_access(admin_user):
        raise HTTPException(status_code=403, detail="마스터 계정은 마스터만 수정할 수 있습니다.")

    if user.emp_id == admin_user.emp_id and body.is_resigned:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")

    user.is_resigned = bool(body.is_resigned)
    if body.is_resigned:
        if user.resigned_date is None:
            from datetime import date
            user.resigned_date = date.today()
    else:
        user.resigned_date = None

    try:
        _append_audit_log(
            db,
            actor_emp_id=admin_user.emp_id,
            target_emp_id=user.emp_id,
            action="update_status",
            details={"is_resigned": user.is_resigned},
        )
        db.commit()
        db.refresh(user)
        logger.info(
            "Admin status update: actor=%s target=%s is_resigned=%s",
            admin_user.emp_id,
            user.emp_id,
            user.is_resigned,
        )
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return _serialize_user(user)


# ── Self-service profile update (name / birth_year / position) ───────────────

class SelfProfileUpdate(BaseModel):
    name: str | None = None
    birth_year: int | None = None
    position: str | None = None


VALID_POSITIONS = {"PG", "SG", "SF", "PF", "C", "F", "G"}


@router.patch("/me")
def update_my_profile(
    body: SelfProfileUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """로그인한 회원이 자신의 이름·나이·포지션을 수정합니다."""
    user = db.query(models.User).filter(models.User.emp_id == current_user.emp_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="이름은 비워둘 수 없습니다.")
        user.name = name

    if "birth_year" in body.model_fields_set:
        if body.birth_year is not None and not (1940 <= body.birth_year <= 2015):
            raise HTTPException(status_code=422, detail="출생연도가 올바르지 않습니다.")
        user.birth_year = body.birth_year

    if "position" in body.model_fields_set:
        raw = (body.position or "").strip()
        if raw:
            parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
            if not all(p in VALID_POSITIONS for p in parts):
                raise HTTPException(status_code=422, detail="포지션 값이 올바르지 않습니다.")
            user.position = ",".join(parts)
        else:
            user.position = None

    db.commit()
    db.refresh(user)
    return _serialize_user(user)


@router.patch("/{emp_id}")
def update_user_profile(
    emp_id: str,
    body: UserProfileUpdate,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    role_norm = (body.role or "").upper().strip()
    try:
        next_role = models.canonical_role(models.RoleEnum(role_norm))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role value.")

    current_role = models.canonical_role(user.role)
    actor_is_master = has_master_access(admin_user)
    old_emp_id = user.emp_id
    next_emp_id = (body.emp_id or body.name or "").strip()

    if not next_emp_id:
        raise HTTPException(status_code=400, detail="ID is required.")

    if current_role == models.RoleEnum.MASTER and not actor_is_master:
        raise HTTPException(status_code=403, detail="마스터 계정은 마스터만 수정할 수 있습니다.")

    if not actor_is_master and next_role != current_role:
        raise HTTPException(status_code=403, detail="권한 변경은 마스터만 할 수 있습니다.")

    if user.emp_id == admin_user.emp_id and next_role != models.RoleEnum.ADMIN:
        if not actor_is_master or next_role != models.RoleEnum.MASTER:
            raise HTTPException(status_code=400, detail="You cannot change your own role.")

    if next_emp_id != old_emp_id:
        duplicate = db.query(models.User).filter(models.User.emp_id == next_emp_id).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="이미 사용 중인 이름(아이디)입니다.")
        _rekey_user_references(db, old_emp_id, next_emp_id)

    user.emp_id = next_emp_id
    user.name = (body.name or "").strip() or user.name
    user.email = (body.email or "").strip() or None
    user.role = next_role
    user.is_vip = bool(body.is_vip)
    user.birth_year = body.birth_year
    user.position = (body.position or "").strip() or None

    try:
        _append_audit_log(
            db,
            actor_emp_id=admin_user.emp_id,
            target_emp_id=user.emp_id,
            action="update_profile",
            details={"previous_emp_id": old_emp_id, "role": user.role.value, "is_vip": user.is_vip},
        )
        db.commit()
        db.refresh(user)
        logger.info(
            "Admin profile update: actor=%s target=%s role=%s vip=%s",
            admin_user.emp_id,
            user.emp_id,
            user.role,
            user.is_vip,
        )
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return _serialize_user(user)


@router.patch("/{emp_id}/role")
def update_user_role(
    emp_id: str,
    body: UserRoleUpdate,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    role_norm = (body.role or "").upper().strip()
    try:
        next_role = models.canonical_role(models.RoleEnum(role_norm))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role value.")

    actor_is_master = has_master_access(admin_user)
    current_role = models.canonical_role(user.role)

    if not actor_is_master:
        raise HTTPException(status_code=403, detail="권한 변경은 마스터만 할 수 있습니다.")

    if user.emp_id == admin_user.emp_id:
        raise HTTPException(status_code=400, detail="본인 권한은 변경할 수 없습니다.")

    if current_role == next_role:
        return _serialize_user(user)

    user.role = next_role
    try:
        _append_audit_log(
            db,
            actor_emp_id=admin_user.emp_id,
            target_emp_id=user.emp_id,
            action="update_profile",
            details={"role": user.role.value, "role_only": True},
        )
        db.commit()
        db.refresh(user)
        logger.info(
            "Admin role update: actor=%s target=%s role=%s",
            admin_user.emp_id,
            user.emp_id,
            user.role,
        )
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return _serialize_user(user)


class BulkDeleteBody(BaseModel):
    emp_ids: list[str]


@router.post("/bulk-delete")
def bulk_delete_users(
    body: BulkDeleteBody,
    master_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from auth import has_master_access
    if not has_master_access(master_user):
        raise HTTPException(status_code=403, detail="회원 삭제는 마스터만 할 수 있습니다.")

    ids = [i.strip() for i in (body.emp_ids or []) if i.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="삭제할 회원 ID를 입력하세요.")

    # Prevent self-deletion
    if master_user.emp_id in ids:
        raise HTTPException(status_code=400, detail="자신의 계정은 삭제할 수 없습니다.")

    deleted = []
    try:
        for emp_id in ids:
            user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
            if not user:
                continue
            _append_audit_log(
                db,
                actor_emp_id=master_user.emp_id,
                target_emp_id=emp_id,
                action="delete_user",
                details={"role": user.role.value, "name": user.name},
            )
            db.query(models.MemberProfile).filter(models.MemberProfile.emp_id == emp_id).delete(synchronize_session=False)
            db.query(models.MembershipPayment).filter(models.MembershipPayment.emp_id == emp_id).delete(synchronize_session=False)
            db.query(models.AttendanceVote).filter(models.AttendanceVote.emp_id == emp_id).delete(synchronize_session=False)
            db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id == emp_id).delete(synchronize_session=False)
            db.query(models.AttendanceReminderLog).filter(models.AttendanceReminderLog.emp_id == emp_id).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.emp_id == emp_id).delete(synchronize_session=False)
            deleted.append(emp_id)
        db.commit()
        logger.info("Master bulk-deleted users: actor=%s targets=%s", master_user.emp_id, deleted)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {"deleted": deleted, "count": len(deleted)}


@router.delete("/{emp_id}")
def delete_user(
    emp_id: str,
    master_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from auth import has_master_access
    if not has_master_access(master_user):
        raise HTTPException(status_code=403, detail="회원 삭제는 마스터만 할 수 있습니다.")

    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.emp_id == master_user.emp_id:
        raise HTTPException(status_code=400, detail="자신의 계정은 삭제할 수 없습니다.")

    try:
        _append_audit_log(
            db,
            actor_emp_id=master_user.emp_id,
            target_emp_id=user.emp_id,
            action="delete_user",
            details={"role": user.role.value, "name": user.name},
        )
        # Remove related records
        db.query(models.MemberProfile).filter(models.MemberProfile.emp_id == emp_id).delete(synchronize_session=False)
        db.query(models.MembershipPayment).filter(models.MembershipPayment.emp_id == emp_id).delete(synchronize_session=False)
        db.query(models.AttendanceVote).filter(models.AttendanceVote.emp_id == emp_id).delete(synchronize_session=False)
        db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id == emp_id).delete(synchronize_session=False)
        db.query(models.AttendanceReminderLog).filter(models.AttendanceReminderLog.emp_id == emp_id).delete(synchronize_session=False)
        db.query(models.User).filter(models.User.emp_id == emp_id).delete(synchronize_session=False)
        db.commit()
        logger.info("Master deleted user: actor=%s target=%s", master_user.emp_id, emp_id)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {"message": f"User '{emp_id}' has been deleted."}


@router.post("/{emp_id}/issue-temp-password")
def issue_temp_password(
    emp_id: str,
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if models.canonical_role(user.role) == models.RoleEnum.MASTER:
        raise HTTPException(status_code=403, detail="Master account password cannot be reset via this endpoint.")

    temp_pw = generate_temp_password()
    user.hashed_password = hash_password(temp_pw)
    user.temp_password = temp_pw
    user.is_first_login = True

    try:
        _append_audit_log(
            db,
            actor_emp_id=_admin.emp_id,
            target_emp_id=user.emp_id,
            action="issue_temp_password",
            details={"is_first_login": True},
        )
        db.commit()
        logger.info(
            "Admin issued temp password: actor=%s target=%s",
            _admin.emp_id,
            user.emp_id,
        )
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "emp_id": user.emp_id,
        "temp_password": temp_pw,
        "message": "Temporary password issued.",
    }


@router.get("/public/members")
def get_public_members(
    _user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """로그인한 모든 회원이 볼 수 있는 활동 회원 목록 (커리어 평균 스탯 포함)."""
    from datetime import date

    members = (
        db.query(models.User)
        .filter(
            models.User.is_resigned == False,
            models.User.role != models.RoleEnum.MASTER,
        )
        .all()
    )

    # 커리어 스탯: emp_id별 집계
    all_stats = (
        db.query(models.LeaguePlayerStat)
        .filter(models.LeaguePlayerStat.participated == True)
        .all()
    )

    stat_agg: dict[str, dict] = {}
    for s in all_stats:
        key = s.emp_id
        if key not in stat_agg:
            stat_agg[key] = {"games": 0, "pts": 0, "reb": 0, "ast": 0, "stl": 0, "blk": 0}
        row = stat_agg[key]
        row["games"] += 1
        row["pts"]   += s.fg2_made * 2 + s.fg3_made * 3 + s.ft_made
        row["reb"]   += s.o_rebound + s.d_rebound
        row["ast"]   += s.assist
        row["stl"]   += s.steal
        row["blk"]   += s.block

    current_year = date.today().year

    result = []
    for m in members:
        agg = stat_agg.get(m.emp_id)
        g = agg["games"] if agg else 0

        def avg(val):
            return round(val / g, 1) if g > 0 else None

        career_avg = {
            "games":       g,
            "avg_points":  avg(agg["pts"]) if agg else None,
            "avg_rebound": avg(agg["reb"]) if agg else None,
            "avg_assist":  avg(agg["ast"]) if agg else None,
            "avg_steal":   avg(agg["stl"]) if agg else None,
            "avg_block":   avg(agg["blk"]) if agg else None,
        } if agg else None

        result.append({
            "emp_id":     m.emp_id,
            "name":       m.name,
            "birth_year": m.birth_year,
            "age":        (current_year - m.birth_year) if m.birth_year else None,
            "position":   m.position,
            "avatar_url": m.avatar_url,
            "career_avg": career_avg,
        })

    # 가나다 순 (한글 유니코드 코드포인트 기준 정렬)
    result.sort(key=lambda r: r["name"] or "")
    return result


# ── Avatar upload / delete ────────────────────────────────────────────────────

AVATAR_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "avatars")
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_AVATAR_BYTES = 5 * 1024 * 1024   # 5 MB
AVATAR_MAX_PX    = 400               # 최대 가로/세로


def _avatar_path(emp_id: str, ext: str) -> str:
    safe = re.sub(r"[^\w\-]", "_", emp_id)
    return os.path.join(AVATAR_DIR, f"{safe}{ext}")


@router.post("/{emp_id}/avatar")
async def upload_avatar(
    emp_id: str,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """프로필 사진 업로드 — 관리자는 전체, 일반 회원은 본인만."""
    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    is_admin = models.canonical_role(current_user.role) in (models.RoleEnum.MASTER, models.RoleEnum.ADMIN)
    if not is_admin and current_user.emp_id != emp_id:
        raise HTTPException(status_code=403, detail="본인 사진만 변경할 수 있습니다.")

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="JPG, PNG, WebP, GIF 파일만 허용됩니다.")

    raw = await file.read()
    if len(raw) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="파일 크기는 5 MB 이하여야 합니다.")

    # Resize & convert to JPEG via Pillow
    try:
        img = Image.open(BytesIO(raw)).convert("RGB")
        img.thumbnail((AVATAR_MAX_PX, AVATAR_MAX_PX), Image.LANCZOS)
    except Exception:
        raise HTTPException(status_code=400, detail="이미지 파일을 읽을 수 없습니다.")

    os.makedirs(AVATAR_DIR, exist_ok=True)

    # Remove old avatar file if different extension
    if user.avatar_url:
        old_path = os.path.join(AVATAR_DIR, os.path.basename(user.avatar_url.split("?")[0]))
        if os.path.isfile(old_path):
            os.remove(old_path)

    safe_id = re.sub(r"[^\w\-]", "_", emp_id)
    filename = f"{safe_id}.jpg"
    filepath = os.path.join(AVATAR_DIR, filename)
    img.save(filepath, format="JPEG", quality=85, optimize=True)

    avatar_url = f"/avatars/{filename}?v={int(time.time())}"
    user.avatar_url = avatar_url
    db.commit()

    return {"avatar_url": avatar_url}


@router.delete("/{emp_id}/avatar")
def delete_avatar(
    emp_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """프로필 사진 삭제 — 관리자는 전체, 일반 회원은 본인만."""
    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    is_admin = models.canonical_role(current_user.role) in (models.RoleEnum.MASTER, models.RoleEnum.ADMIN)
    if not is_admin and current_user.emp_id != emp_id:
        raise HTTPException(status_code=403, detail="본인 사진만 삭제할 수 있습니다.")

    if user.avatar_url:
        filepath = os.path.join(AVATAR_DIR, os.path.basename(user.avatar_url.split("?")[0]))
        if os.path.isfile(filepath):
            os.remove(filepath)
        user.avatar_url = None
        db.commit()

    return {"message": "사진이 삭제되었습니다."}
