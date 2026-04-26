from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel

from auth import get_current_user, require_admin
from database import get_db
import models

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class SubscribeRequest(BaseModel):
    endpoint: str
    keys: dict  # {"p256dh": "...", "auth": "..."}


class SendRequest(BaseModel):
    title: str
    body: str
    url: str = "/"
    target_emp_id: str | None = None  # None = 전체 발송


@router.get("/vapid-public-key")
def get_vapid_public_key():
    from services.push_service import get_vapid_public_key
    key = get_vapid_public_key()
    if not key:
        raise HTTPException(status_code=503, detail="푸시 알림이 서버에 설정되지 않았습니다.")
    return {"publicKey": key}


@router.post("/subscribe", status_code=200)
def subscribe(
    body: SubscribeRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.endpoint:
        raise HTTPException(status_code=400, detail="endpoint가 필요합니다.")
    p256dh = (body.keys or {}).get("p256dh", "")
    auth_key = (body.keys or {}).get("auth", "")
    if not p256dh or not auth_key:
        raise HTTPException(status_code=400, detail="keys.p256dh 와 keys.auth 가 필요합니다.")

    existing = db.query(models.PushSubscription).filter(
        models.PushSubscription.endpoint == body.endpoint
    ).first()

    try:
        if existing:
            existing.emp_id = current_user.emp_id
            existing.p256dh = p256dh
            existing.auth = auth_key
        else:
            db.add(models.PushSubscription(
                emp_id=current_user.emp_id,
                endpoint=body.endpoint,
                p256dh=p256dh,
                auth=auth_key,
            ))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="구독 저장 중 오류가 발생했습니다.")

    return {"message": "알림 구독이 완료되었습니다."}


@router.delete("/unsubscribe", status_code=200)
def unsubscribe(
    body: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    endpoint = (body or {}).get("endpoint", "")
    if not endpoint:
        raise HTTPException(status_code=400, detail="endpoint가 필요합니다.")

    db.query(models.PushSubscription).filter(
        models.PushSubscription.emp_id == current_user.emp_id,
        models.PushSubscription.endpoint == endpoint,
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": "알림 구독이 해제되었습니다."}


@router.post("/send", status_code=200)
def send_notification(
    body: SendRequest,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from services.push_service import send_push_to_all, send_push_to_subscription

    title = (body.title or "").strip()
    text = (body.body or "").strip()
    if not title or not text:
        raise HTTPException(status_code=400, detail="title 과 body 는 필수입니다.")

    if body.target_emp_id:
        subs = db.query(models.PushSubscription).filter(
            models.PushSubscription.emp_id == body.target_emp_id
        ).all()
        sent, stale = 0, []
        for sub in subs:
            if send_push_to_subscription(sub, title, text, body.url):
                sent += 1
            else:
                stale.append(sub.id)
        if stale:
            db.query(models.PushSubscription).filter(
                models.PushSubscription.id.in_(stale)
            ).delete(synchronize_session=False)
            db.commit()
        return {"sent": sent, "failed": len(stale)}

    result = send_push_to_all(db, title, text, body.url)
    return result
