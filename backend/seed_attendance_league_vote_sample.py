from datetime import date, datetime, timedelta

import models
from database import SessionLocal

SAMPLE_NOTE = "SAMPLE_ATTENDANCE_LEAGUE_VOTE_RESULT"


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


def pick_target_team_and_members(db):
    members = (
        db.query(models.User)
        .filter(
            models.User.role.in_(models.MEMBER_ROLE_VALUES),
            models.User.is_resigned.isnot(True),
        )
        .all()
    )
    active_member_ids = {m.emp_id for m in members}

    assignments = db.query(models.LeagueTeamAssignment).all()
    grouped = {"A": [], "B": [], "C": []}
    for row in assignments:
        if not row.team_code:
            continue
        team_code = row.team_code.value
        if team_code in grouped and row.emp_id in active_member_ids:
            grouped[team_code].append(row.emp_id)

    team_code = max(grouped.keys(), key=lambda code: len(grouped[code]))
    emp_ids = sorted(grouped[team_code])

    return team_code, emp_ids


def upsert_sample_event(db, creator_emp_id, team_code):
    event = (
        db.query(models.AttendanceEvent)
        .filter(models.AttendanceEvent.note == SAMPLE_NOTE)
        .order_by(models.AttendanceEvent.id.desc())
        .first()
    )

    today = date.today()
    title = f"리그전 출석 투표 샘플 ({team_code}팀, {today.isoformat()})"

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
    target_team_enum = models.LeagueTeamEnum(team_code)

    if not setting:
        setting = models.AttendanceEventSetting(
            event_id=event.id,
            vote_type=models.AttendanceVoteTypeEnum.LEAGUE,
            target_team=target_team_enum,
            vote_start_at=vote_start_at,
            vote_end_at=vote_end_at,
            updated_by=creator_emp_id,
        )
        db.add(setting)
    else:
        setting.vote_type = models.AttendanceVoteTypeEnum.LEAGUE
        setting.target_team = target_team_enum
        setting.vote_start_at = vote_start_at
        setting.vote_end_at = vote_end_at
        setting.updated_by = creator_emp_id

    return event


def seed_votes(db, event_id, target_emp_ids):
    db.query(models.AttendanceVote).filter(models.AttendanceVote.event_id == event_id).delete()

    # Leave some members unvoted on purpose to test pending list UX.
    voting_pool = target_emp_ids[: min(len(target_emp_ids), 8)]
    vote_count = max(1, int(len(voting_pool) * 0.7))
    voted_emp_ids = voting_pool[:vote_count]

    votes = []
    for idx, emp_id in enumerate(voted_emp_ids):
        response = (
            models.AttendanceResponseEnum.ATTEND
            if idx % 3 != 2
            else models.AttendanceResponseEnum.ABSENT
        )
        votes.append(
            models.AttendanceVote(
                event_id=event_id,
                emp_id=emp_id,
                response=response,
            )
        )

    if votes:
        db.add_all(votes)

    attend_count = sum(1 for v in votes if v.response == models.AttendanceResponseEnum.ATTEND)
    absent_count = sum(1 for v in votes if v.response == models.AttendanceResponseEnum.ABSENT)
    pending_count = len(voting_pool) - len(votes)

    return len(voting_pool), len(votes), attend_count, absent_count, pending_count


def main():
    db = SessionLocal()
    try:
        creator = pick_creator(db)
        if not creator:
            raise RuntimeError("샘플 이벤트를 생성할 사용자가 없습니다.")

        team_code, target_emp_ids = pick_target_team_and_members(db)
        if not target_emp_ids:
            raise RuntimeError("리그전 팀 배정 데이터가 없어 LEAGUE 샘플을 만들 수 없습니다.")

        event = upsert_sample_event(db, creator.emp_id, team_code)
        eligible_count, voted_count, attend_count, absent_count, pending_count = seed_votes(db, event.id, target_emp_ids)

        db.commit()

        print("[OK] 리그전 출석 투표 샘플 생성/갱신 완료")
        print(f"event_id={event.id}")
        print(f"title={event.title}")
        print(f"event_date={event.event_date}")
        print("vote_type=LEAGUE")
        print(f"target_team={team_code}")
        print(
            f"eligible={eligible_count}, voted={voted_count}, attend={attend_count}, absent={absent_count}, pending={pending_count}"
        )
        print(f"note={SAMPLE_NOTE}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
