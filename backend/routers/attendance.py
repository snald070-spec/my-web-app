from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError

from auth import get_current_user, require_admin
from database import get_db
from utils.pagination import paginate
import models

router = APIRouter(prefix="/api/attendance", tags=["attendance"])


class AttendanceEventCreate(BaseModel):
    title: str
    event_date: date
    note: str | None = None
    vote_type: str = "REST"
    target_team: str | None = None


class AttendanceVoteBody(BaseModel):
    response: str


class AttendanceStatusUpdate(BaseModel):
    status: str


class TeamAssignmentUpdate(BaseModel):
    team_code: str | None = None
    is_captain: bool | None = None


class ReminderDispatchBody(BaseModel):
    event_id: int
    stage: str
    memo: str | None = None


def _get_or_create_event_setting(db: Session, event, actor_emp_id: str | None = None):
    setting = db.query(models.AttendanceEventSetting).filter(models.AttendanceEventSetting.event_id == event.id).first()
    if setting:
        return setting

    # Legacy fallback: existing events become REST votes for the event date 00:00~23:59.
    setting = models.AttendanceEventSetting(
        event_id=event.id,
        vote_type=models.AttendanceVoteTypeEnum.REST,
        target_team=None,
        vote_start_at=datetime.combine(event.event_date, datetime.min.time()),
        vote_end_at=datetime.combine(event.event_date, datetime.max.time()).replace(microsecond=0),
        updated_by=actor_emp_id,
    )
    db.add(setting)
    db.flush()
    return setting


def _resolve_team_code(value: str | None):
    if value is None or str(value).strip() == "":
        return None
    try:
        return models.LeagueTeamEnum(str(value).strip().upper())
    except ValueError:
        raise HTTPException(status_code=400, detail="team_code/target_team must be A, B, or C")


def _get_user_team(db: Session, emp_id: str):
    row = db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id == emp_id).first()
    return row.team_code if row else None


def _eligible_emp_ids_for_event(db: Session, setting: models.AttendanceEventSetting) -> set[str]:
    users = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).all()

    if setting.vote_type == models.AttendanceVoteTypeEnum.REST:
        return {u.emp_id for u in users}

    # League vote targets members assigned to the event target team only.
    if not setting.target_team:
        return set()

    assignments = db.query(models.LeagueTeamAssignment).filter(
        models.LeagueTeamAssignment.team_code == setting.target_team
    ).all()
    active_emp_ids = {u.emp_id for u in users}
    return {a.emp_id for a in assignments if a.emp_id in active_emp_ids}


def _is_vote_window_open(setting: models.AttendanceEventSetting) -> bool:
    if setting.vote_start_at is None or setting.vote_end_at is None:
        return True
    now = datetime.now()
    return setting.vote_start_at <= now <= setting.vote_end_at


def _get_due_stage(setting: models.AttendanceEventSetting, now: datetime) -> models.AttendanceReminderStageEnum | None:
    if setting.vote_end_at is None:
        return None

    one_day_before = setting.vote_end_at - timedelta(days=1)
    one_hour_before = setting.vote_end_at - timedelta(hours=1)

    # Allow scheduler polling window: stage becomes due when we pass threshold and before end.
    if one_day_before <= now < one_hour_before:
        return models.AttendanceReminderStageEnum.DAY_BEFORE
    if one_hour_before <= now < setting.vote_end_at:
        return models.AttendanceReminderStageEnum.HOUR_BEFORE
    return None


def _event_counts(db: Session, event_id: int) -> dict:
    votes = db.query(models.AttendanceVote).filter(models.AttendanceVote.event_id == event_id).all()
    counts = {"ATTEND": 0, "ABSENT": 0, "LATE": 0}
    for v in votes:
        key = v.response.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def _serialize_event(db: Session, event, current_emp_id: str | None = None) -> dict:
    setting = _get_or_create_event_setting(db, event)
    counts = _event_counts(db, event.id)
    my_vote = None
    my_team = None
    eligible = True
    can_vote = event.status == models.AttendanceEventStatusEnum.OPEN and _is_vote_window_open(setting)

    if current_emp_id:
        row = (
            db.query(models.AttendanceVote)
            .filter(models.AttendanceVote.event_id == event.id, models.AttendanceVote.emp_id == current_emp_id)
            .first()
        )
        if row:
            my_vote = row.response.value

        my_team = _get_user_team(db, current_emp_id)
        eligible_emp_ids = _eligible_emp_ids_for_event(db, setting)
        eligible = current_emp_id in eligible_emp_ids
        can_vote = can_vote and eligible

    return {
        "id": event.id,
        "title": event.title,
        "event_date": event.event_date,
        "status": event.status.value,
        "note": event.note,
        "created_by": event.created_by,
        "vote_type": setting.vote_type.value,
        "target_team": setting.target_team.value if setting.target_team else None,
        "vote_start_at": setting.vote_start_at,
        "vote_end_at": setting.vote_end_at,
        "counts": counts,
        "my_vote": my_vote,
        "my_team": my_team.value if my_team else None,
        "eligible": eligible,
        "can_vote": can_vote,
    }


@router.get("/events")
def list_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(models.AttendanceEvent).order_by(desc(models.AttendanceEvent.event_date), desc(models.AttendanceEvent.id))
    return paginate(q, skip, limit, lambda e: _serialize_event(db, e, current_user.emp_id))


@router.post("/events")
def create_event(
    body: AttendanceEventCreate,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not (body.title or "").strip():
        raise HTTPException(status_code=400, detail="이벤트 제목은 필수입니다.")

    vote_type_raw = (body.vote_type or "REST").upper().strip()
    try:
        vote_type = models.AttendanceVoteTypeEnum(vote_type_raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="vote_type must be LEAGUE or REST")

    target_team = _resolve_team_code(body.target_team)
    if vote_type == models.AttendanceVoteTypeEnum.LEAGUE and target_team is None:
        raise HTTPException(status_code=400, detail="리그전 투표는 target_team(A/B/C)이 필요합니다.")
    if vote_type == models.AttendanceVoteTypeEnum.REST:
        target_team = None

    # Rest vote policy: weekly Thu 12:00 start -> Sun 12:00 end.
    if vote_type == models.AttendanceVoteTypeEnum.REST:
        # Use the week of event_date as 기준. Thursday=3, Sunday=6
        weekday = body.event_date.weekday()
        thursday = body.event_date + timedelta(days=(3 - weekday))
        sunday = thursday + timedelta(days=3)
        vote_start_at = datetime(thursday.year, thursday.month, thursday.day, 12, 0, 0)
        vote_end_at = datetime(sunday.year, sunday.month, sunday.day, 12, 0, 0)
    else:
        vote_start_at = datetime.combine(body.event_date, datetime.min.time())
        vote_end_at = datetime.combine(body.event_date, datetime.max.time()).replace(microsecond=0)

    row = models.AttendanceEvent(
        title=body.title.strip(),
        event_date=body.event_date,
        note=(body.note or "").strip() or None,
        created_by=admin_user.emp_id,
    )
    try:
        db.add(row)
        db.flush()

        setting = models.AttendanceEventSetting(
            event_id=row.id,
            vote_type=vote_type,
            target_team=target_team,
            vote_start_at=vote_start_at,
            vote_end_at=vote_end_at,
            updated_by=admin_user.emp_id,
        )
        db.add(setting)
        db.commit()
        db.refresh(row)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")
    return _serialize_event(db, row)


@router.patch("/events/{event_id}/status")
def update_event_status(
    event_id: int,
    body: AttendanceStatusUpdate,
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(models.AttendanceEvent).filter(models.AttendanceEvent.id == event_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="출석 이벤트를 찾을 수 없습니다.")
    try:
        row.status = models.AttendanceEventStatusEnum((body.status or "").upper().strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="status must be OPEN or CLOSED")

    try:
        db.commit()
        db.refresh(row)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")
    return _serialize_event(db, row)


@router.post("/events/{event_id}/vote")
def vote_event(
    event_id: int,
    body: AttendanceVoteBody,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = db.query(models.AttendanceEvent).filter(models.AttendanceEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="출석 이벤트를 찾을 수 없습니다.")
    if event.status != models.AttendanceEventStatusEnum.OPEN:
        raise HTTPException(status_code=400, detail="마감된 이벤트입니다.")

    setting = _get_or_create_event_setting(db, event)
    if not _is_vote_window_open(setting):
        raise HTTPException(status_code=400, detail="현재 투표 가능 시간이 아닙니다.")

    eligible_emp_ids = _eligible_emp_ids_for_event(db, setting)
    if current_user.emp_id not in eligible_emp_ids:
        raise HTTPException(status_code=403, detail="투표 대상이 아닙니다. 결과만 확인할 수 있습니다.")

    try:
        response = models.AttendanceResponseEnum((body.response or "").upper().strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="response must be ATTEND, ABSENT, or LATE")

    if response == models.AttendanceResponseEnum.LATE:
        raise HTTPException(status_code=400, detail="현재 투표는 ATTEND/ABSENT만 지원합니다.")

    row = (
        db.query(models.AttendanceVote)
        .filter(models.AttendanceVote.event_id == event_id, models.AttendanceVote.emp_id == current_user.emp_id)
        .first()
    )
    if row:
        row.response = response
    else:
        row = models.AttendanceVote(
            event_id=event_id,
            emp_id=current_user.emp_id,
            response=response,
        )
        db.add(row)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return _serialize_event(db, event, current_user.emp_id)


@router.get("/me/summary")
def get_my_attendance_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    votes = db.query(models.AttendanceVote).filter(models.AttendanceVote.emp_id == current_user.emp_id).all()
    total = len(votes)
    attend = sum(1 for v in votes if v.response == models.AttendanceResponseEnum.ATTEND)
    late = sum(1 for v in votes if v.response == models.AttendanceResponseEnum.LATE)
    absent = sum(1 for v in votes if v.response == models.AttendanceResponseEnum.ABSENT)
    score = attend * 1.0 + late * 0.5
    rate = round((attend / total) * 100, 1) if total > 0 else 0.0

    return {
        "emp_id": current_user.emp_id,
        "total_votes": total,
        "attend_count": attend,
        "late_count": late,
        "absent_count": absent,
        "attendance_rate": rate,
        "cumulative_score": score,
    }


@router.get("/admin/member-summary")
def get_member_attendance_summary(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=300),
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).order_by(models.User.created_at.asc()).all()

    rows = []
    for u in users:
        votes = db.query(models.AttendanceVote).filter(models.AttendanceVote.emp_id == u.emp_id).all()
        team = _get_user_team(db, u.emp_id)
        total = len(votes)
        attend = sum(1 for v in votes if v.response == models.AttendanceResponseEnum.ATTEND)
        late = sum(1 for v in votes if v.response == models.AttendanceResponseEnum.LATE)
        absent = sum(1 for v in votes if v.response == models.AttendanceResponseEnum.ABSENT)
        score = attend * 1.0 + late * 0.5
        rate = round((attend / total) * 100, 1) if total > 0 else 0.0
        rows.append(
            {
                "emp_id": u.emp_id,
                "name": u.emp_id,
                "department": u.department,
                "league_team": team.value if team else None,
                "total_votes": total,
                "attend_count": attend,
                "late_count": late,
                "absent_count": absent,
                "attendance_rate": rate,
                "cumulative_score": score,
            }
        )

    total_rows = len(rows)
    return {
        "items": rows[skip: skip + limit],
        "total": total_rows,
        "skip": skip,
        "limit": limit,
    }


@router.get("/admin/team-assignments")
def list_team_assignments(
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).order_by(models.User.emp_id.asc()).all()

    assignments = {
        row.emp_id: row
        for row in db.query(models.LeagueTeamAssignment).all()
    }

    items = []
    for u in users:
        row = assignments.get(u.emp_id)
        items.append(
            {
                "emp_id": u.emp_id,
                "name": u.emp_id,
                "department": u.department,
                "team_code": row.team_code.value if row and row.team_code else None,
                "is_captain": bool(row.is_captain) if row else False,
            }
        )
    return {"items": items, "total": len(items), "skip": 0, "limit": len(items) or 1}


@router.put("/admin/team-assignments/{emp_id}")
def upsert_team_assignment(
    emp_id: str,
    body: TeamAssignmentUpdate,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(
        models.User.emp_id == emp_id,
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다.")

    team_code = _resolve_team_code(body.team_code)
    row = db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id == emp_id).first()
    next_team_code = team_code if body.team_code is not None else (row.team_code if row else None)
    next_is_captain = bool(body.is_captain) if body.is_captain is not None else (bool(row.is_captain) if row else False)

    if next_team_code is None:
        next_is_captain = False

    if next_is_captain and next_team_code is None:
        raise HTTPException(status_code=400, detail="팀장이 되려면 먼저 팀에 배정되어야 합니다.")

    if row:
        row.team_code = next_team_code
        row.is_captain = next_is_captain
        row.updated_by = admin_user.emp_id
    else:
        row = models.LeagueTeamAssignment(
            emp_id=emp_id,
            team_code=next_team_code,
            is_captain=next_is_captain,
            updated_by=admin_user.emp_id,
        )
        db.add(row)

    if next_is_captain and next_team_code is not None:
        db.query(models.LeagueTeamAssignment).filter(
            models.LeagueTeamAssignment.team_code == next_team_code,
            models.LeagueTeamAssignment.emp_id != emp_id,
            models.LeagueTeamAssignment.is_captain.is_(True),
        ).update({"is_captain": False, "updated_by": admin_user.emp_id}, synchronize_session=False)

    try:
        db.commit()
        db.refresh(row)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "emp_id": emp_id,
        "team_code": row.team_code.value if row.team_code else None,
        "is_captain": bool(row.is_captain),
    }


@router.get("/admin/reminders/pending")
def get_pending_reminders(
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    now = datetime.now()
    events = db.query(models.AttendanceEvent).filter(models.AttendanceEvent.status == models.AttendanceEventStatusEnum.OPEN).all()
    pending = []

    for event in events:
        setting = _get_or_create_event_setting(db, event)
        stage = _get_due_stage(setting, now)
        if stage is None:
            continue

        eligible_emp_ids = _eligible_emp_ids_for_event(db, setting)
        if not eligible_emp_ids:
            continue

        voted_emp_ids = {
            v.emp_id for v in db.query(models.AttendanceVote).filter(models.AttendanceVote.event_id == event.id).all()
        }
        not_voted_emp_ids = sorted(list(eligible_emp_ids - voted_emp_ids))
        if not not_voted_emp_ids:
            continue

        already_sent = {
            r.emp_id for r in db.query(models.AttendanceReminderLog).filter(
                models.AttendanceReminderLog.event_id == event.id,
                models.AttendanceReminderLog.stage == stage,
            ).all()
        }
        targets = [emp_id for emp_id in not_voted_emp_ids if emp_id not in already_sent]
        if not targets:
            continue

        pending.append(
            {
                "event_id": event.id,
                "title": event.title,
                "vote_type": setting.vote_type.value,
                "target_team": setting.target_team.value if setting.target_team else None,
                "stage": stage.value,
                "vote_end_at": setting.vote_end_at,
                "target_emp_ids": targets,
                "target_count": len(targets),
            }
        )

    return {"items": pending, "total": len(pending), "skip": 0, "limit": len(pending) or 1}


@router.post("/admin/reminders/dispatch")
def dispatch_reminder(
    body: ReminderDispatchBody,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    event = db.query(models.AttendanceEvent).filter(models.AttendanceEvent.id == body.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="출석 이벤트를 찾을 수 없습니다.")

    setting = _get_or_create_event_setting(db, event, actor_emp_id=admin_user.emp_id)
    try:
        stage = models.AttendanceReminderStageEnum((body.stage or "").upper().strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="stage must be DAY_BEFORE or HOUR_BEFORE")

    eligible_emp_ids = _eligible_emp_ids_for_event(db, setting)
    voted_emp_ids = {
        v.emp_id for v in db.query(models.AttendanceVote).filter(models.AttendanceVote.event_id == event.id).all()
    }
    not_voted_emp_ids = sorted(list(eligible_emp_ids - voted_emp_ids))

    already_sent = {
        r.emp_id for r in db.query(models.AttendanceReminderLog).filter(
            models.AttendanceReminderLog.event_id == event.id,
            models.AttendanceReminderLog.stage == stage,
        ).all()
    }
    targets = [emp_id for emp_id in not_voted_emp_ids if emp_id not in already_sent]

    try:
        for emp_id in targets:
            db.add(
                models.AttendanceReminderLog(
                    event_id=event.id,
                    stage=stage,
                    emp_id=emp_id,
                    sent_by=admin_user.emp_id,
                    memo=(body.memo or "").strip() or None,
                )
            )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "event_id": event.id,
        "stage": stage.value,
        "sent_count": len(targets),
        "target_emp_ids": targets,
    }


def _build_event_vote_detail_payload(db: Session, event_id: int) -> dict:
    event = db.query(models.AttendanceEvent).filter(models.AttendanceEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="출석 이벤트를 찾을 수 없습니다.")

    setting = _get_or_create_event_setting(db, event)
    counts = _event_counts(db, event.id)
    eligible_emp_ids = _eligible_emp_ids_for_event(db, setting)

    member_rows = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).all()
    member_by_emp_id = {row.emp_id: row for row in member_rows}

    team_by_emp_id = {
        row.emp_id: (row.team_code.value if row.team_code else None)
        for row in db.query(models.LeagueTeamAssignment).all()
    }

    votes = db.query(models.AttendanceVote).filter(models.AttendanceVote.event_id == event.id).all()
    voted_emp_ids = set()
    voted_items = []
    for vote in votes:
        voted_emp_ids.add(vote.emp_id)
        user = member_by_emp_id.get(vote.emp_id)
        voted_items.append(
            {
                "emp_id": vote.emp_id,
                "name": user.emp_id if user else vote.emp_id,
                "department": user.department if user else "-",
                "league_team": team_by_emp_id.get(vote.emp_id),
                "response": vote.response.value,
                "voted_at": vote.voted_at,
            }
        )

    voted_items.sort(key=lambda item: (item["response"], item["name"]))

    pending_ids = sorted(list(eligible_emp_ids - voted_emp_ids))
    pending_items = []
    for emp_id in pending_ids:
        user = member_by_emp_id.get(emp_id)
        pending_items.append(
            {
                "emp_id": emp_id,
                "name": user.emp_id if user else emp_id,
                "department": user.department if user else "-",
                "league_team": team_by_emp_id.get(emp_id),
            }
        )

    pending_items.sort(key=lambda item: item["name"])

    attend_by_team = {"A": 0, "B": 0, "C": 0}
    for item in voted_items:
        if item["response"] != models.AttendanceResponseEnum.ATTEND.value:
            continue
        team = item.get("league_team")
        if team in attend_by_team:
            attend_by_team[team] += 1

    return {
        "event": {
            "id": event.id,
            "title": event.title,
            "event_date": event.event_date,
            "status": event.status.value,
            "vote_type": setting.vote_type.value,
            "target_team": setting.target_team.value if setting.target_team else None,
            "vote_start_at": setting.vote_start_at,
            "vote_end_at": setting.vote_end_at,
            "counts": counts,
        },
        "voted": voted_items,
        "pending": pending_items,
        "summary": {
            "eligible_count": len(eligible_emp_ids),
            "voted_count": len(voted_items),
            "pending_count": len(pending_items),
            "attend_by_team": attend_by_team,
        },
    }


@router.get("/events/{event_id}/vote-detail")
def get_event_vote_detail(
    event_id: int,
    _current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _build_event_vote_detail_payload(db, event_id)


@router.get("/admin/events/{event_id}/vote-detail")
def get_event_vote_detail_admin(
    event_id: int,
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _build_event_vote_detail_payload(db, event_id)
