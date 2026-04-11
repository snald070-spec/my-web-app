"""
Dashboard router — stub / placeholder.
Replace the body with your real business logic.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone
from auth import get_current_user, require_admin
from database import get_db
import models

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def get_summary(current_user: models.User = Depends(get_current_user)):
    """Public summary — any authenticated user."""
    return {
        "message": f"Hello, {current_user.emp_id}!",
        "role":    current_user.role,
    }


@router.get("/admin-stats")
def get_admin_stats(
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only stats endpoint."""
    today = datetime.now(timezone.utc).date().isoformat()

    total_users = db.query(models.User).count()
    status_changes_today = (
        db.query(models.UserAuditLog)
        .filter(
            func.date(models.UserAuditLog.created_at) == today,
            models.UserAuditLog.action == "update_status",
        )
        .count()
    )

    non_fee_deposit_alerts = (
        db.query(models.BankDepositEvent)
        .filter(models.BankDepositEvent.match_status == "NON_FEE_AMOUNT")
        .count()
    )
    non_fee_deposit_alerts_today = (
        db.query(models.BankDepositEvent)
        .filter(
            models.BankDepositEvent.match_status == "NON_FEE_AMOUNT",
            func.date(models.BankDepositEvent.created_at) == today,
        )
        .count()
    )
    recent_non_fee_deposits = (
        db.query(models.BankDepositEvent)
        .filter(models.BankDepositEvent.match_status == "NON_FEE_AMOUNT")
        .order_by(models.BankDepositEvent.created_at.desc(), models.BankDepositEvent.id.desc())
        .limit(5)
        .all()
    )

    return {
        "total_users": total_users,
        "status_changes_today": status_changes_today,
        "non_fee_deposit_alerts": non_fee_deposit_alerts,
        "non_fee_deposit_alerts_today": non_fee_deposit_alerts_today,
        "recent_non_fee_deposits": [
            {
                "id": r.id,
                "depositor_name": r.depositor_name,
                "amount": r.amount,
                "year_month": r.year_month,
                "matched_emp_id": r.matched_emp_id,
                "created_at": r.created_at,
                "note": r.note,
            }
            for r in recent_non_fee_deposits
        ],
    }


@router.post("/admin/non-fee-deposits/ack-all")
def acknowledge_non_fee_deposits(
    today_only: bool = Query(True),
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Mark NON_FEE_AMOUNT deposit alerts as acknowledged so they stop appearing in master warning banner."""
    q = db.query(models.BankDepositEvent).filter(models.BankDepositEvent.match_status == "NON_FEE_AMOUNT")

    if today_only:
        today = datetime.now(timezone.utc).date().isoformat()
        q = q.filter(func.date(models.BankDepositEvent.created_at) == today)

    rows = q.all()
    if not rows:
        return {
            "acknowledged": 0,
            "today_only": today_only,
            "message": "확인할 회비 외 입금 알림이 없습니다.",
        }

    for row in rows:
        row.match_status = "NON_FEE_AMOUNT_ACKED"

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "acknowledged": len(rows),
        "today_only": today_only,
        "message": "회비 외 입금 알림을 확인 처리했습니다.",
    }
