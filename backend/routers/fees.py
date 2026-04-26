from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from sqlalchemy.exc import SQLAlchemyError
import hashlib
import os

from auth import get_current_user, require_admin, require_master
from database import get_db
from utils.pagination import paginate
import models

router = APIRouter(prefix="/api/fees", tags=["fees"])


TARGET_BANK_NAME = "국민은행"
TARGET_ACCOUNT_NUMBER = "331301-04-169767"
TARGET_ACCOUNT_HOLDER = "박한올"
TARGET_DEPOSIT_SOURCE = "KOOKMINBANK_ALERT"


def _current_year_month() -> str:
    return datetime.now().strftime("%Y-%m")


def _ym_to_int(ym: str) -> int:
    parts = (ym or "").split("-")
    if len(parts) != 2:
        return -1
    y, m = parts[0], parts[1]
    if not (y.isdigit() and m.isdigit()):
        return -1
    yv, mv = int(y), int(m)
    if mv < 1 or mv > 12:
        return -1
    return yv * 100 + mv


def _add_months(ym: str, months: int) -> str:
    y, m = map(int, ym.split("-"))
    idx = (y * 12 + (m - 1)) + months
    ny, nm = divmod(idx, 12)
    return f"{ny:04d}-{nm + 1:02d}"


def _recent_months(end_year_month: str, size: int = 6) -> list[str]:
    months = []
    for i in range(size - 1, -1, -1):
        months.append(_add_months(end_year_month, -i))
    return months


def _get_or_create_profile(db: Session, user: models.User) -> models.MemberProfile:
    profile = db.query(models.MemberProfile).filter(models.MemberProfile.emp_id == user.emp_id).first()
    if profile:
        return profile
    profile = models.MemberProfile(emp_id=user.emp_id)
    db.add(profile)
    db.flush()
    return profile


def _expected_amount(membership_type: models.MembershipTypeEnum, plan: models.FeePlanEnum) -> int:
    if membership_type == models.MembershipTypeEnum.STUDENT:
        return 20000
    if plan == models.FeePlanEnum.SEMI_ANNUAL:
        return 150000
    if plan == models.FeePlanEnum.ANNUAL:
        return 300000
    return 30000


def _coverage_end(year_month: str, plan: models.FeePlanEnum) -> str:
    if plan == models.FeePlanEnum.SEMI_ANNUAL:
        return _add_months(year_month, 5)
    if plan == models.FeePlanEnum.ANNUAL:
        return _add_months(year_month, 11)
    return year_month


def _is_paid_for_month(db: Session, emp_id: str, year_month: str) -> bool:
    target = _ym_to_int(year_month)
    rows = (
        db.query(models.MembershipPayment)
        .filter(models.MembershipPayment.emp_id == emp_id, models.MembershipPayment.is_paid.is_(True))
        .all()
    )
    for r in rows:
        s = _ym_to_int(r.coverage_start_month)
        e = _ym_to_int(r.coverage_end_month)
        if s <= target <= e:
            return True
    return False


class MemberProfileUpdate(BaseModel):
    membership_type: str | None = None
    member_status: str | None = None


class MarkPaidBody(BaseModel):
    year_month: str
    plan_type: str = "MONTHLY"
    paid_amount: int | None = None
    note: str | None = None


class ReminderLogBody(BaseModel):
    year_month: str
    period: str
    memo: str | None = None


class DepositIngestBody(BaseModel):
    depositor_name: str
    amount: int
    year_month: str | None = None
    occurred_at: str | None = None
    source: str = TARGET_DEPOSIT_SOURCE
    bank_name: str = TARGET_BANK_NAME
    account_number: str = TARGET_ACCOUNT_NUMBER
    account_holder: str = TARGET_ACCOUNT_HOLDER
    raw_text: str | None = None
    auto_apply: bool = True


class EditPaymentBody(BaseModel):
    paid_amount: int | None = None
    note: str | None = None
    year_month: str | None = None


class FeeHistorySettingBody(BaseModel):
    months: int  # 1 ~ 36


FEE_HISTORY_MONTHS_KEY = "fee_history_months"
FEE_HISTORY_MONTHS_DEFAULT = 12


def _get_fee_history_months(db: Session) -> int:
    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == FEE_HISTORY_MONTHS_KEY).first()
    if row:
        try:
            return max(1, min(36, int(row.value)))
        except (ValueError, TypeError):
            pass
    return FEE_HISTORY_MONTHS_DEFAULT


def _set_fee_history_months(db: Session, months: int, actor_emp_id: str) -> None:
    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == FEE_HISTORY_MONTHS_KEY).first()
    if row:
        row.value = str(months)
        row.updated_by = actor_emp_id
    else:
        db.add(models.SystemSetting(key=FEE_HISTORY_MONTHS_KEY, value=str(months), updated_by=actor_emp_id))


def _normalize_name(name: str) -> str:
    return "".join((name or "").strip().split()).lower()


def _normalize_account_number(account_number: str) -> str:
    return "".join((account_number or "").strip().split())


def _normalize_bank_name(bank_name: str) -> str:
    return "".join((bank_name or "").strip().split()).lower()


def _parse_occurred_at(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.strip()
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(status_code=400, detail="occurred_at must be ISO-8601 datetime")


def _resolve_months_and_plan(profile: models.MemberProfile, amount: int) -> tuple[int, models.FeePlanEnum, int]:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    if profile.membership_type == models.MembershipTypeEnum.STUDENT:
        base = 20000
        if amount % base != 0:
            raise HTTPException(status_code=400, detail="학생 회비 금액이 월 단위(20,000원)와 맞지 않습니다.")
        months = amount // base
        return months, models.FeePlanEnum.MONTHLY, base * months

    # GENERAL
    if amount == 150000:
        return 6, models.FeePlanEnum.SEMI_ANNUAL, 150000
    if amount == 300000:
        return 12, models.FeePlanEnum.ANNUAL, 300000
    if amount % 30000 != 0:
        raise HTTPException(status_code=400, detail="일반 회비 금액이 월 단위(30,000원)와 맞지 않습니다.")
    months = amount // 30000
    return months, models.FeePlanEnum.MONTHLY, 30000 * months


def _find_member_by_exact_name(db: Session, name: str) -> list[models.User]:
    target = _normalize_name(name)
    users = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).all()
    return [u for u in users if _normalize_name(u.name) == target]


def _build_event_key(source: str, depositor_name: str, amount: int, occurred_at: datetime | None, year_month: str) -> str:
    base = "|".join([
        (source or "").strip().upper(),
        _normalize_name(depositor_name),
        str(amount),
        occurred_at.isoformat() if occurred_at else "",
        year_month,
    ])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _ingest_deposit_event(db: Session, body: DepositIngestBody, actor_emp_id: str):
    depositor_name = (body.depositor_name or "").strip()
    if not depositor_name:
        raise HTTPException(status_code=400, detail="depositor_name is required")

    ym = (body.year_month or _current_year_month()).strip()
    if _ym_to_int(ym) < 0:
        raise HTTPException(status_code=400, detail="year_month must be YYYY-MM")

    bank_name = (body.bank_name or "").strip()
    account_number = _normalize_account_number(body.account_number or "")
    account_holder = (body.account_holder or "").strip()
    source = (body.source or TARGET_DEPOSIT_SOURCE).strip().upper()

    # Source is fixed for this integration path (Kookmin bank alerts).
    if source != TARGET_DEPOSIT_SOURCE:
        raise HTTPException(status_code=400, detail=f"지원 소스가 아닙니다. {TARGET_DEPOSIT_SOURCE}만 허용됩니다.")

    # Bank name may vary by label (국민은행/KB국민은행), so account number + holder are authoritative.
    bank_norm = _normalize_bank_name(bank_name)
    if bank_norm and ("국민" not in bank_norm and "kb" not in bank_norm):
        raise HTTPException(status_code=400, detail=f"지원 은행이 아닙니다. {TARGET_BANK_NAME} 계좌만 허용됩니다.")

    if account_number != TARGET_ACCOUNT_NUMBER:
        raise HTTPException(status_code=400, detail=f"지원 계좌가 아닙니다. {TARGET_ACCOUNT_NUMBER} 계좌만 허용됩니다.")

    occurred_at = _parse_occurred_at(body.occurred_at)
    event_key = _build_event_key(body.source, depositor_name, body.amount, occurred_at, ym)

    existing = db.query(models.BankDepositEvent).filter(models.BankDepositEvent.event_key == event_key).first()
    if existing:
        return {
            "message": "이미 처리된 입금 이벤트입니다.",
            "duplicate": True,
            "event_id": existing.id,
            "match_status": existing.match_status,
            "linked_payment_id": existing.linked_payment_id,
        }

    matched_users = _find_member_by_exact_name(db, depositor_name)
    if len(matched_users) == 0:
        row = models.BankDepositEvent(
            event_key=event_key,
            source=(body.source or TARGET_DEPOSIT_SOURCE).strip().upper(),
            depositor_name=depositor_name,
            amount=body.amount,
            occurred_at=occurred_at,
            year_month=ym,
            match_status="NO_MATCH",
            raw_text=(body.raw_text or "").strip() or None,
            note="동일 이름 회원 없음",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "message": "매칭 가능한 회원이 없습니다.",
            "duplicate": False,
            "event_id": row.id,
            "match_status": row.match_status,
        }

    if len(matched_users) > 1:
        row = models.BankDepositEvent(
            event_key=event_key,
            source=(body.source or TARGET_DEPOSIT_SOURCE).strip().upper(),
            depositor_name=depositor_name,
            amount=body.amount,
            occurred_at=occurred_at,
            year_month=ym,
            match_status="AMBIGUOUS",
            raw_text=(body.raw_text or "").strip() or None,
            note=f"동일 이름 회원 {len(matched_users)}명",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "message": "동일 이름 회원이 2명 이상입니다. 수동 확인이 필요합니다.",
            "duplicate": False,
            "event_id": row.id,
            "match_status": row.match_status,
        }

    user = matched_users[0]
    profile = _get_or_create_profile(db, user)
    try:
        months, plan, expected_total = _resolve_months_and_plan(profile, body.amount)
    except HTTPException as ex:
        row = models.BankDepositEvent(
            event_key=event_key,
            source=(body.source or TARGET_DEPOSIT_SOURCE).strip().upper(),
            depositor_name=depositor_name,
            amount=body.amount,
            occurred_at=occurred_at,
            year_month=ym,
            match_status="NON_FEE_AMOUNT",
            matched_emp_id=user.emp_id,
            raw_text=(body.raw_text or "").strip() or None,
            note=f"회비 외 금액 감지: {ex.detail}",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "message": "회비 외 입금 금액이 감지되어 자동 반영하지 않았습니다.",
            "duplicate": False,
            "event_id": row.id,
            "match_status": row.match_status,
            "matched_emp_id": user.emp_id,
            "matched_name": user.name,
        }

    coverage_end = _add_months(ym, months - 1)

    already_paid_months = []
    for offset in range(months):
        m = _add_months(ym, offset)
        if _is_paid_for_month(db, user.emp_id, m):
            already_paid_months.append(m)

    if already_paid_months:
        row = models.BankDepositEvent(
            event_key=event_key,
            source=(body.source or TARGET_DEPOSIT_SOURCE).strip().upper(),
            depositor_name=depositor_name,
            amount=body.amount,
            occurred_at=occurred_at,
            year_month=ym,
            match_status="ALREADY_PAID",
            matched_emp_id=user.emp_id,
            months_covered=months,
            raw_text=(body.raw_text or "").strip() or None,
            note=f"이미 납부 처리된 월 포함: {', '.join(already_paid_months)}",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "message": "이미 납부 처리된 월이 포함되어 자동 반영을 건너뜁니다.",
            "duplicate": False,
            "event_id": row.id,
            "match_status": row.match_status,
            "already_paid_months": already_paid_months,
        }

    if not body.auto_apply:
        row = models.BankDepositEvent(
            event_key=event_key,
            source=(body.source or TARGET_DEPOSIT_SOURCE).strip().upper(),
            depositor_name=depositor_name,
            amount=body.amount,
            occurred_at=occurred_at,
            year_month=ym,
            match_status="MATCHED_PENDING",
            matched_emp_id=user.emp_id,
            months_covered=months,
            raw_text=(body.raw_text or "").strip() or None,
            note="auto_apply=false",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "message": "회원 매칭 완료 (반영 대기)",
            "duplicate": False,
            "event_id": row.id,
            "match_status": row.match_status,
            "matched_emp_id": user.emp_id,
            "matched_name": user.name,
            "months_covered": months,
            "coverage_start_month": ym,
            "coverage_end_month": coverage_end,
        }

    payment = models.MembershipPayment(
        emp_id=user.emp_id,
        plan_type=plan,
        year_month=ym,
        coverage_start_month=ym,
        coverage_end_month=coverage_end,
        expected_amount=expected_total,
        paid_amount=body.amount,
        is_paid=True,
        note=(f"AUTO:{(body.source or TARGET_DEPOSIT_SOURCE).strip().upper()} {TARGET_BANK_NAME}/{TARGET_ACCOUNT_NUMBER} 입금자={depositor_name}"),
        marked_by=actor_emp_id,
    )
    db.add(payment)
    db.flush()

    row = models.BankDepositEvent(
        event_key=event_key,
        source=(body.source or TARGET_DEPOSIT_SOURCE).strip().upper(),
        depositor_name=depositor_name,
        amount=body.amount,
        occurred_at=occurred_at,
        year_month=ym,
        match_status="APPLIED",
        matched_emp_id=user.emp_id,
        months_covered=months,
        linked_payment_id=payment.id,
        raw_text=(body.raw_text or "").strip() or None,
        note=f"자동 반영 완료: {ym} ~ {coverage_end}",
    )
    db.add(row)

    try:
        db.commit()
        db.refresh(row)
        db.refresh(payment)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "message": "입금 알림이 자동 반영되었습니다.",
        "duplicate": False,
        "event_id": row.id,
        "match_status": row.match_status,
        "payment": {
            "id": payment.id,
            "emp_id": payment.emp_id,
            "name": user.name,
            "plan_type": payment.plan_type.value,
            "months_covered": months,
            "coverage_start_month": payment.coverage_start_month,
            "coverage_end_month": payment.coverage_end_month,
            "paid_amount": payment.paid_amount,
            "marked_by": payment.marked_by,
            "marked_at": payment.marked_at,
        },
    }


@router.get("/me")
def get_my_fee_status(
    year_month: str = Query(default=""),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ym = year_month or _current_year_month()
    if _ym_to_int(ym) < 0:
        raise HTTPException(status_code=400, detail="year_month must be YYYY-MM")

    profile = _get_or_create_profile(db, current_user)
    is_paid = _is_paid_for_month(db, current_user.emp_id, ym)
    monthly_expected = _expected_amount(profile.membership_type, models.FeePlanEnum.MONTHLY)

    latest_payment = (
        db.query(models.MembershipPayment)
        .filter(models.MembershipPayment.emp_id == current_user.emp_id)
        .order_by(desc(models.MembershipPayment.marked_at), desc(models.MembershipPayment.id))
        .first()
    )

    return {
        "year_month": ym,
        "emp_id": current_user.emp_id,
        "name": current_user.name,
        "membership_type": profile.membership_type.value,
        "member_status": profile.member_status.value,
        "expected_monthly_amount": monthly_expected,
        "is_paid": is_paid,
        "latest_payment": {
            "plan_type": latest_payment.plan_type.value,
            "coverage_start_month": latest_payment.coverage_start_month,
            "coverage_end_month": latest_payment.coverage_end_month,
            "paid_amount": latest_payment.paid_amount,
            "marked_at": latest_payment.marked_at,
        } if latest_payment else None,
    }


@router.get("/me/history")
def get_my_fee_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    history_months = _get_fee_history_months(db)
    cutoff_ym = _add_months(_current_year_month(), -(history_months - 1))

    q = (
        db.query(models.MembershipPayment)
        .filter(
            models.MembershipPayment.emp_id == current_user.emp_id,
            models.MembershipPayment.year_month >= cutoff_ym,
        )
        .order_by(desc(models.MembershipPayment.marked_at), desc(models.MembershipPayment.id))
    )

    return paginate(
        q,
        skip,
        limit,
        lambda r: {
            "id": r.id,
            "year_month": r.year_month,
            "plan_type": r.plan_type.value,
            "coverage_start_month": r.coverage_start_month,
            "coverage_end_month": r.coverage_end_month,
            "expected_amount": r.expected_amount,
            "paid_amount": r.paid_amount,
            "is_paid": bool(r.is_paid),
            "note": r.note,
            "marked_by": r.marked_by,
            "marked_at": r.marked_at,
        },
    )


@router.get("/admin/members")
def get_members_fee_status(
    year_month: str = Query(default=""),
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=300),
    keyword: str = Query(default=""),
    member_status: str = Query(default="ALL"),
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ym = year_month or _current_year_month()
    if _ym_to_int(ym) < 0:
        raise HTTPException(status_code=400, detail="year_month must be YYYY-MM")

    users_q = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    )

    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        users_q = users_q.filter(
            (models.User.emp_id.ilike(like))
            | (models.User.department.ilike(like))
        )

    rows = users_q.order_by(models.User.created_at.desc()).all()
    items = []
    for u in rows:
        profile = _get_or_create_profile(db, u)
        if member_status != "ALL" and profile.member_status.value != member_status:
            continue
        paid = _is_paid_for_month(db, u.emp_id, ym)
        items.append(
            {
                "emp_id": u.emp_id,
                "name": u.name,
                "department": u.department,
                "membership_type": profile.membership_type.value,
                "member_status": profile.member_status.value,
                "expected_monthly_amount": _expected_amount(profile.membership_type, models.FeePlanEnum.MONTHLY),
                "is_paid": paid,
            }
        )

    total = len(items)
    return {
        "items": items[skip: skip + limit],
        "total": total,
        "skip": skip,
        "limit": limit,
        "year_month": ym,
    }


@router.get("/admin/summary")
def get_fee_admin_summary(
    year_month: str = Query(default=""),
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ym = year_month or _current_year_month()
    if _ym_to_int(ym) < 0:
        raise HTTPException(status_code=400, detail="year_month must be YYYY-MM")

    users = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).all()

    total_members = len(users)
    paid_count = 0

    by_type = {
        "GENERAL": {"total": 0, "paid": 0, "unpaid": 0},
        "STUDENT": {"total": 0, "paid": 0, "unpaid": 0},
    }
    by_status = {
        "NORMAL": {"total": 0, "paid": 0, "unpaid": 0},
        "INJURED": {"total": 0, "paid": 0, "unpaid": 0},
        "DORMANT": {"total": 0, "paid": 0, "unpaid": 0},
    }

    for u in users:
        profile = _get_or_create_profile(db, u)
        is_paid = _is_paid_for_month(db, u.emp_id, ym)
        if is_paid:
            paid_count += 1

        t_key = profile.membership_type.value
        s_key = profile.member_status.value

        by_type[t_key]["total"] += 1
        by_type[t_key]["paid" if is_paid else "unpaid"] += 1

        by_status[s_key]["total"] += 1
        by_status[s_key]["paid" if is_paid else "unpaid"] += 1

    unpaid_count = max(total_members - paid_count, 0)
    payment_rate = round((paid_count / total_members) * 100, 1) if total_members > 0 else 0.0

    trend = []
    for month in _recent_months(ym, 6):
        month_paid = 0
        for u in users:
            if _is_paid_for_month(db, u.emp_id, month):
                month_paid += 1
        month_total = total_members
        month_rate = round((month_paid / month_total) * 100, 1) if month_total > 0 else 0.0
        trend.append(
            {
                "year_month": month,
                "total": month_total,
                "paid": month_paid,
                "unpaid": max(month_total - month_paid, 0),
                "payment_rate": month_rate,
            }
        )

    return {
        "year_month": ym,
        "total_members": total_members,
        "paid_count": paid_count,
        "unpaid_count": unpaid_count,
        "payment_rate": payment_rate,
        "by_membership_type": by_type,
        "by_member_status": by_status,
        "monthly_trend": trend,
    }


@router.get("/admin/matrix")
def get_fee_admin_matrix(
    end_year_month: str = Query(default=""),
    months: int = Query(15, ge=3, le=24),
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    end_ym = end_year_month or _current_year_month()
    if _ym_to_int(end_ym) < 0:
        raise HTTPException(status_code=400, detail="end_year_month must be YYYY-MM")

    month_keys = _recent_months(end_ym, months)
    month_meta = []
    year_groups = []
    for ym in month_keys:
        year, month = ym.split("-")
        month_meta.append(
            {
                "key": ym,
                "year": int(year),
                "month": int(month),
                "label": f"{int(month)}월",
            }
        )
        if not year_groups or year_groups[-1]["year"] != int(year):
            year_groups.append({"year": int(year), "colspan": 1})
        else:
            year_groups[-1]["colspan"] += 1

    users = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).order_by(models.User.created_at.asc()).all()

    rows = []
    for u in users:
        profile = _get_or_create_profile(db, u)
        cells = []
        for ym in month_keys:
            if _is_paid_for_month(db, u.emp_id, ym):
                cells.append("O")
            elif profile.member_status == models.MemberStatusEnum.DORMANT:
                cells.append("휴면")
            elif profile.member_status == models.MemberStatusEnum.INJURED:
                cells.append("부상")
            else:
                cells.append("X")

        rows.append(
            {
                "emp_id": u.emp_id,
                "name": u.name,
                "membership_type": profile.membership_type.value,
                "member_status": profile.member_status.value,
                "cells": cells,
            }
        )

    return {
        "title": "DRAW 회비 납부 현황",
        "banner": "331301-04-169767 국민은행 박한올 / 월 30,000원 (학생 20,000원) (갱신일 : 2026년 3월 24일 10:41) - 6개월 15만원 1년 30만원",
        "months": month_meta,
        "year_groups": year_groups,
        "rows": rows,
    }


@router.patch("/admin/members/{emp_id}/profile")
def update_member_profile(
    emp_id: str,
    body: MemberProfileUpdate,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다.")

    if body.membership_type is None and body.member_status is None:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")

    profile = _get_or_create_profile(db, user)

    if body.membership_type is not None:
        try:
            profile.membership_type = models.MembershipTypeEnum(body.membership_type.upper().strip())
        except ValueError:
            raise HTTPException(status_code=422, detail="잘못된 membership_type 값입니다.")

    if body.member_status is not None:
        try:
            profile.member_status = models.MemberStatusEnum(body.member_status.upper().strip())
        except ValueError:
            raise HTTPException(status_code=422, detail="잘못된 member_status 값입니다.")

    profile.updated_by = admin_user.emp_id

    try:
        db.commit()
        db.refresh(profile)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "emp_id": emp_id,
        "membership_type": profile.membership_type.value,
        "member_status": profile.member_status.value,
    }


@router.post("/admin/members/{emp_id}/mark-paid")
def mark_paid(
    emp_id: str,
    body: MarkPaidBody,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.emp_id == emp_id, models.User.role.in_(models.MEMBER_ROLE_VALUES)).first()
    if not user:
        raise HTTPException(status_code=404, detail="일반 회원을 찾을 수 없습니다.")

    ym = (body.year_month or "").strip()
    if _ym_to_int(ym) < 0:
        raise HTTPException(status_code=400, detail="year_month must be YYYY-MM")

    try:
        plan = models.FeePlanEnum((body.plan_type or "MONTHLY").upper().strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 납부 구분입니다.")

    profile = _get_or_create_profile(db, user)
    if profile.membership_type == models.MembershipTypeEnum.STUDENT and plan != models.FeePlanEnum.MONTHLY:
        raise HTTPException(status_code=400, detail="학생 회원은 월납만 선택할 수 있습니다.")
    expected = _expected_amount(profile.membership_type, plan)
    amount = body.paid_amount if body.paid_amount is not None else expected

    row = models.MembershipPayment(
        emp_id=emp_id,
        plan_type=plan,
        year_month=ym,
        coverage_start_month=ym,
        coverage_end_month=_coverage_end(ym, plan),
        expected_amount=expected,
        paid_amount=amount,
        is_paid=True,
        note=(body.note or "").strip() or None,
        marked_by=admin_user.emp_id,
    )

    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "id": row.id,
        "emp_id": row.emp_id,
        "year_month": row.year_month,
        "plan_type": row.plan_type.value,
        "coverage_start_month": row.coverage_start_month,
        "coverage_end_month": row.coverage_end_month,
        "paid_amount": row.paid_amount,
        "marked_by": row.marked_by,
        "marked_at": row.marked_at,
    }


@router.get("/admin/reminders")
def get_fee_reminders(
    year_month: str = Query(default=""),
    period: str = Query(default="MONTH_END"),
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ym = year_month or _current_year_month()
    if _ym_to_int(ym) < 0:
        raise HTTPException(status_code=400, detail="year_month must be YYYY-MM")

    p = (period or "MONTH_END").upper().strip()
    if p not in ("MONTH_END", "MONTH_START"):
        raise HTTPException(status_code=400, detail="period must be MONTH_END or MONTH_START")

    users = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).all()

    unpaid = []
    for u in users:
        profile = _get_or_create_profile(db, u)
        if _is_paid_for_month(db, u.emp_id, ym):
            continue
        unpaid.append(
            {
                "emp_id": u.emp_id,
                "name": u.name,
                "member_status": profile.member_status.value,
                "membership_type": profile.membership_type.value,
                "expected_monthly_amount": _expected_amount(profile.membership_type, models.FeePlanEnum.MONTHLY),
            }
        )

    title = "월말 회비 납부 안내" if p == "MONTH_END" else "월초 회비 납부 리마인드"
    return {
        "year_month": ym,
        "period": p,
        "title": title,
        "target_count": len(unpaid),
        "targets": unpaid,
    }


@router.post("/admin/reminders/log")
def log_fee_reminder(
    body: ReminderLogBody,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ym = (body.year_month or "").strip()
    if _ym_to_int(ym) < 0:
        raise HTTPException(status_code=400, detail="year_month must be YYYY-MM")

    p = (body.period or "").upper().strip()
    if p not in ("MONTH_END", "MONTH_START"):
        raise HTTPException(status_code=400, detail="period must be MONTH_END or MONTH_START")

    reminder = get_fee_reminders(ym, p, admin_user, db)
    row = models.FeeReminderLog(
        year_month=ym,
        period=p,
        target_count=reminder["target_count"],
        sent_by=admin_user.emp_id,
        memo=(body.memo or "").strip() or None,
    )

    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "id": row.id,
        "year_month": row.year_month,
        "period": row.period,
        "target_count": row.target_count,
        "sent_by": row.sent_by,
        "created_at": row.created_at,
    }


@router.get("/admin/reminders/log")
def list_fee_reminder_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(models.FeeReminderLog).order_by(desc(models.FeeReminderLog.created_at), desc(models.FeeReminderLog.id))
    return paginate(
        q,
        skip,
        limit,
        lambda r: {
            "id": r.id,
            "year_month": r.year_month,
            "period": r.period,
            "target_count": r.target_count,
            "sent_by": r.sent_by,
            "memo": r.memo,
            "created_at": r.created_at,
        },
    )


# ===== 미납자 자동 감지 및 알림 통합 기능 =====

@router.get("/admin/unpaid/check")
def check_unpaid_members(
    year_month: str = Query(default=""),
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """현재 월의 미납자 실시간 확인 (자동 감지)."""
    ym = year_month or _current_year_month()
    if _ym_to_int(ym) < 0:
        raise HTTPException(status_code=400, detail="year_month must be YYYY-MM")

    users = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).all()

    unpaid_list = []
    for u in users:
        profile = _get_or_create_profile(db, u)
        is_paid = _is_paid_for_month(db, u.emp_id, ym)
        
        if not is_paid and profile.member_status != models.MemberStatusEnum.DORMANT:
            unpaid_list.append({
                "emp_id": u.emp_id,
                "name": u.name,
                "department": u.department,
                "member_status": profile.member_status.value,
                "membership_type": profile.membership_type.value,
                "expected_monthly_amount": _expected_amount(profile.membership_type, models.FeePlanEnum.MONTHLY),
                "last_payment": None,
            })

    # 각 미납자의 마지막 납부 기록 추가
    for item in unpaid_list:
        last_payment = (
            db.query(models.MembershipPayment)
            .filter(models.MembershipPayment.emp_id == item["emp_id"])
            .order_by(desc(models.MembershipPayment.marked_at))
            .first()
        )
        if last_payment:
            item["last_payment"] = {
                "year_month": last_payment.year_month,
                "marked_at": last_payment.marked_at,
                "days_ago": (datetime.now() - last_payment.marked_at).days,
            }

    return {
        "year_month": ym,
        "unpaid_count": len(unpaid_list),
        "unpaid_members": sorted(unpaid_list, key=lambda x: x["name"]),
    }


@router.get("/admin/reminders/effectiveness")
def measure_reminder_effectiveness(
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """알림 발송 전후 납부율 변화 측정 (지난 3개월)."""
    current_ym = _current_year_month()
    recent_months = _recent_months(current_ym, 3)
    
    # 지난 3개월의 알림 기록 조회
    reminder_logs = (
        db.query(models.FeeReminderLog)
        .filter(models.FeeReminderLog.year_month.in_(recent_months))
        .order_by(models.FeeReminderLog.year_month.desc())
        .all()
    )

    effectiveness_data = []
    for log in reminder_logs:
        # 해당 월의 전체 회원 수
        total_users = len(
            db.query(models.User).filter(
                models.User.role.in_(models.MEMBER_ROLE_VALUES),
                models.User.is_resigned.isnot(True),
            ).all()
        )
        
        # 알림 당시 미납자 수
        unpaid_at_reminder = log.target_count
        
        # 현재 기준 해당 월의 납부 현황
        current_paid_count = 0
        users = db.query(models.User).filter(
            models.User.role.in_(models.MEMBER_ROLE_VALUES),
            models.User.is_resigned.isnot(True),
        ).all()
        
        for u in users:
            if _is_paid_for_month(db, u.emp_id, log.year_month):
                current_paid_count += 1

        effectiveness_rate = (
            round(((total_users - unpaid_at_reminder) / total_users) * 100, 1) 
            if total_users > 0 else 0.0
        )

        effectiveness_data.append({
            "year_month": log.year_month,
            "period": log.period,
            "sent_by": log.sent_by,
            "reminder_target_count": unpaid_at_reminder,
            "total_members": total_users,
            "current_paid_rate": effectiveness_rate,
            "memo": log.memo,
            "sent_at": log.created_at,
        })

    return {
        "analysis_period": f"{recent_months[0]} ~ {recent_months[-1]}",
        "total_reminders": len(effectiveness_data),
        "effectiveness": effectiveness_data,
    }


@router.post("/admin/reminders/auto-schedule")
def schedule_auto_reminder(
    body: ReminderLogBody,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """월별 자동 알림 스케줄 기록 (향후 자동화 시스템 연동용)."""
    ym = (body.year_month or "").strip()
    if _ym_to_int(ym) < 0:
        raise HTTPException(status_code=400, detail="year_month must be YYYY-MM")

    p = (body.period or "").upper().strip()
    if p not in ("MONTH_END", "MONTH_START"):
        raise HTTPException(status_code=400, detail="period must be MONTH_END or MONTH_START")

    # 현재 미납자 조회
    users = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).all()

    unpaid_count = 0
    for u in users:
        if not _is_paid_for_month(db, u.emp_id, ym):
            unpaid_count += 1

    row = models.FeeReminderLog(
        year_month=ym,
        period=p,
        target_count=unpaid_count,
        sent_by=admin_user.emp_id,
        memo=(body.memo or "").strip() or None,
    )

    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "id": row.id,
        "year_month": row.year_month,
        "period": row.period,
        "target_count": row.target_count,
        "sent_by": row.sent_by,
        "created_at": row.created_at,
        "message": f"예정된 알림이 기록되었습니다. (대상: {unpaid_count}명)",
    }


@router.post("/admin/deposits/ingest")
def ingest_deposit_admin(
    body: DepositIngestBody,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """관리자 수동/테스트용 입금 이벤트 수신 API."""
    return _ingest_deposit_event(db, body, admin_user.emp_id)


@router.post("/deposits/webhook")
def ingest_deposit_webhook(
    body: DepositIngestBody,
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
    db: Session = Depends(get_db),
):
    """카카오뱅크 알림 파싱 서버에서 호출하는 웹훅 진입점."""
    expected_token = (os.environ.get("DEPOSIT_WEBHOOK_TOKEN") or "").strip()
    if not expected_token:
        raise HTTPException(status_code=403, detail="Webhook token not configured on server")
    if x_webhook_token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    return _ingest_deposit_event(db, body, "AUTO_WEBHOOK")


@router.get("/admin/deposits/log")
def list_deposit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    keyword: str = Query(default=""),
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(models.BankDepositEvent)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(
            (models.BankDepositEvent.depositor_name.ilike(like))
            | (models.BankDepositEvent.matched_emp_id.ilike(like))
            | (models.BankDepositEvent.match_status.ilike(like))
        )

    q = q.order_by(desc(models.BankDepositEvent.created_at), desc(models.BankDepositEvent.id))
    return paginate(
        q,
        skip,
        limit,
        lambda r: {
            "id": r.id,
            "source": r.source,
            "depositor_name": r.depositor_name,
            "amount": r.amount,
            "occurred_at": r.occurred_at,
            "year_month": r.year_month,
            "match_status": r.match_status,
            "matched_emp_id": r.matched_emp_id,
            "months_covered": r.months_covered,
            "linked_payment_id": r.linked_payment_id,
            "note": r.note,
            "created_at": r.created_at,
        },
    )


# ===== MASTER 전용: 납부 기록 수정/삭제 =====

@router.get("/admin/members/{emp_id}/payments")
def list_member_payments(
    emp_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    master_user: models.User = Depends(require_master),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다.")

    q = (
        db.query(models.MembershipPayment)
        .filter(models.MembershipPayment.emp_id == emp_id)
        .order_by(desc(models.MembershipPayment.marked_at), desc(models.MembershipPayment.id))
    )
    return paginate(
        q,
        skip,
        limit,
        lambda r: {
            "id": r.id,
            "year_month": r.year_month,
            "plan_type": r.plan_type.value,
            "coverage_start_month": r.coverage_start_month,
            "coverage_end_month": r.coverage_end_month,
            "expected_amount": r.expected_amount,
            "paid_amount": r.paid_amount,
            "is_paid": bool(r.is_paid),
            "note": r.note,
            "marked_by": r.marked_by,
            "marked_at": r.marked_at,
        },
    )


@router.patch("/admin/payments/{payment_id}")
def edit_payment(
    payment_id: int,
    body: EditPaymentBody,
    master_user: models.User = Depends(require_master),
    db: Session = Depends(get_db),
):
    row = db.query(models.MembershipPayment).filter(models.MembershipPayment.id == payment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="납부 기록을 찾을 수 없습니다.")

    if body.paid_amount is not None:
        if body.paid_amount < 0:
            raise HTTPException(status_code=400, detail="paid_amount는 0 이상이어야 합니다.")
        row.paid_amount = body.paid_amount

    if body.note is not None:
        row.note = body.note.strip() or None

    if body.year_month is not None:
        ym = body.year_month.strip()
        if _ym_to_int(ym) < 0:
            raise HTTPException(status_code=400, detail="year_month must be YYYY-MM")
        row.year_month = ym

    row.marked_by = master_user.emp_id

    try:
        db.commit()
        db.refresh(row)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "id": row.id,
        "year_month": row.year_month,
        "plan_type": row.plan_type.value,
        "coverage_start_month": row.coverage_start_month,
        "coverage_end_month": row.coverage_end_month,
        "paid_amount": row.paid_amount,
        "is_paid": bool(row.is_paid),
        "note": row.note,
        "marked_by": row.marked_by,
        "marked_at": row.marked_at,
    }


@router.delete("/admin/payments/{payment_id}", status_code=204)
def delete_payment(
    payment_id: int,
    master_user: models.User = Depends(require_master),
    db: Session = Depends(get_db),
):
    row = db.query(models.MembershipPayment).filter(models.MembershipPayment.id == payment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="납부 기록을 찾을 수 없습니다.")

    try:
        db.delete(row)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")


# ===== MASTER 전용: 회비 공개 기간 설정 =====

@router.get("/admin/settings")
def get_fee_settings(
    master_user: models.User = Depends(require_master),
    db: Session = Depends(get_db),
):
    months = _get_fee_history_months(db)
    return {"fee_history_months": months}


@router.patch("/admin/settings")
def update_fee_settings(
    body: FeeHistorySettingBody,
    master_user: models.User = Depends(require_master),
    db: Session = Depends(get_db),
):
    if body.months < 1 or body.months > 36:
        raise HTTPException(status_code=400, detail="months는 1~36 사이여야 합니다.")

    _set_fee_history_months(db, body.months, master_user.emp_id)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {"fee_history_months": body.months}
