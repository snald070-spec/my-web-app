from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel

from auth import get_current_user, require_admin
from database import get_db
from utils.pagination import paginate
import models

router = APIRouter(prefix="/api/notices", tags=["notices"])


class NoticeCreate(BaseModel):
    title: str
    body: str
    is_pinned: bool = False


class NoticeUpdate(BaseModel):
    title: str
    body: str
    is_pinned: bool = False


def _serialize_notice(row: models.Notice) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "body": row.body,
        "is_pinned": bool(row.is_pinned),
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("")
def list_notices(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    keyword: str = Query(""),
    sort_dir: str = Query("desc"),
    _user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(models.Notice)

    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter((models.Notice.title.ilike(like)) | (models.Notice.body.ilike(like)))

    order_time = asc(models.Notice.created_at) if (sort_dir or "desc").lower() == "asc" else desc(models.Notice.created_at)
    q = q.order_by(desc(models.Notice.is_pinned), order_time)

    return paginate(q, skip, limit, _serialize_notice)


@router.post("", status_code=201)
def create_notice(
    body: NoticeCreate,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    title = (body.title or "").strip()
    text = (body.body or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="제목은 필수입니다.")
    if not text:
        raise HTTPException(status_code=400, detail="내용은 필수입니다.")

    row = models.Notice(
        title=title,
        body=text,
        is_pinned=bool(body.is_pinned),
        created_by=admin_user.emp_id,
        updated_by=admin_user.emp_id,
    )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    try:
        from services.push_service import send_push_to_all
        send_push_to_all(db, f"📢 공지사항: {title}", text[:80], url="/notices")
    except Exception:
        pass

    return _serialize_notice(row)


@router.patch("/{notice_id}")
def update_notice(
    notice_id: int,
    body: NoticeUpdate,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(models.Notice).filter(models.Notice.id == notice_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다.")

    title = (body.title or "").strip()
    text = (body.body or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="제목은 필수입니다.")
    if not text:
        raise HTTPException(status_code=400, detail="내용은 필수입니다.")

    row.title = title
    row.body = text
    row.is_pinned = bool(body.is_pinned)
    row.updated_by = admin_user.emp_id

    try:
        db.commit()
        db.refresh(row)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return _serialize_notice(row)


@router.delete("/{notice_id}")
def delete_notice(
    notice_id: int,
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(models.Notice).filter(models.Notice.id == notice_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다.")

    try:
        db.delete(row)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {"message": "삭제되었습니다."}
