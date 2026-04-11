from datetime import date, datetime, timedelta

import models
from database import SessionLocal

SAMPLE_NOTE = "SAMPLE_ATTENDANCE_VOTE_RESULT"


def pick_creator(db):
    creator = (
        db.query(models.User)
        .filter(
            models.User.role.in_(models.ADMIN_ROLE_VALUES),
            models.User.is_resigned.isnot(True),
        )
        .order_by(models.User.created_at.asc())
        .first()
    )
    if creator:
        return creator

    return (
        db.query(models.User)
        .filter(models.User.is_resigned.isnot(True))
        .order_by(models.User.created_at.asc())
        .first()
    )


def pick_member_targets(db, limit=8):
    return (
        db.query(models.User)
        .filter(
            models.User.role.in_(models.MEMBER_ROLE_VALUES),
            models.User.is_resigned.isnot(True),
        )
        .order_by(models.User.created_at.asc())
        .limit(limit)
        .all()
    )


def upsert_sample_event(db, creator_emp_id):
    event = (
        db.query(models.AttendanceEvent)
        .filter(models.AttendanceEvent.note == SAMPLE_NOTE)
        .order_by(models.AttendanceEvent.id.desc())
        .first()
    )

    today = date.today()
    title = f"출석 투표 샘플 ({today.isoformat()})"

    if not event:
        event = models.AttendanceEvent(
            title=title,
            event_date=today,
            status=models.AttendanceEventStatusEnum.OPEN,
            note=SAMPLE_NOTE,
            created_by=creator_emp_id,
        )
        db.add(event)
        db.flush()
    else:
        event.title = title
        event.event_date = today
        event.status = models.AttendanceEventStatusEnum.OPEN

    setting = (
        db.query(models.AttendanceEventSetting)
        .filter(models.AttendanceEventSetting.event_id == event.id)
        .first()
    )

    vote_start_at = datetime.now() - timedelta(days=1)
    vote_end_at = datetime.now() + timedelta(days=7)

    if not setting:
        setting = models.AttendanceEventSetting(
            event_id=event.id,
            vote_type=models.AttendanceVoteTypeEnum.REST,
            target_team=None,
            vote_start_at=vote_start_at,
            vote_end_at=vote_end_at,
            updated_by=creator_emp_id,
        )
        db.add(setting)
    else:
        setting.vote_type = models.AttendanceVoteTypeEnum.REST
        setting.target_team = None
        setting.vote_start_at = vote_start_at
        setting.vote_end_at = vote_end_at
        setting.updated_by = creator_emp_id

    return event


def seed_votes(db, event_id, members):
    db.query(models.AttendanceVote).filter(models.AttendanceVote.event_id == event_id).delete()

    votes = []
    for idx, user in enumerate(members):
        response = (
            models.AttendanceResponseEnum.ATTEND
            if idx % 3 != 2
            else models.AttendanceResponseEnum.ABSENT
        )
        votes.append(
            models.AttendanceVote(
                event_id=event_id,
                emp_id=user.emp_id,
                response=response,
            )
        )

    if votes:
        db.add_all(votes)

    attend_count = sum(1 for v in votes if v.response == models.AttendanceResponseEnum.ATTEND)
    absent_count = sum(1 for v in votes if v.response == models.AttendanceResponseEnum.ABSENT)
    return attend_count, absent_count, len(votes)


def main():
    db = SessionLocal()
    try:
        creator = pick_creator(db)
        if not creator:
            raise RuntimeError("샘플 이벤트를 생성할 사용자가 없습니다.")

        members = pick_member_targets(db, limit=8)
        if not members:
            raise RuntimeError("투표 샘플을 만들 활성 멤버가 없습니다.")

        event = upsert_sample_event(db, creator.emp_id)
        attend_count, absent_count, total = seed_votes(db, event.id, members)

        db.commit()

        print("[OK] 출석 투표 샘플 생성/갱신 완료")
        print(f"event_id={event.id}")
        print(f"title={event.title}")
        print(f"event_date={event.event_date}")
        print(f"vote_type=REST")
        print(f"total_votes={total}, attend={attend_count}, absent={absent_count}")
        print(f"note={SAMPLE_NOTE}")
    except Exception as exc:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
