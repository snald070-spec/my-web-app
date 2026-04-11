from datetime import date, datetime, timedelta
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from auth import require_admin, get_current_user, has_admin_access
from database import get_db
import models


router = APIRouter(prefix="/api/league", tags=["league"])


class LeagueSeasonCreate(BaseModel):
    total_weeks: int = Field(default=8, ge=1, le=30)
    client_year: int | None = Field(default=None, ge=2000, le=2100)
    start_date: date | None = None
    note: str | None = None


class MatchResultUpdate(BaseModel):
    status: str = Field(default="FINAL")  # FINAL or FORFEIT
    home_score: int | None = Field(default=None, ge=0)
    away_score: int | None = Field(default=None, ge=0)
    forfeited_team: str | None = None
    note: str | None = None


class TradeWindowEvaluateBody(BaseModel):
    week_no: int = Field(default=3, ge=1, le=30)


class TradeWindowWaiveBody(BaseModel):
    waived: bool = True
    note: str | None = None


class TradeProposalCreateBody(BaseModel):
    proposer_team: str
    partner_team: str
    proposer_out_emp_id: str
    partner_out_emp_id: str
    note: str | None = None


class TradeProposalDecisionBody(BaseModel):
    approve: bool = True
    note: str | None = None


class TradeProtectedPlayersBody(BaseModel):
    team_code: str
    emp_ids: list[str] = Field(default_factory=list)
    week_no: int = Field(default=3, ge=1, le=30)


class PlayerStatUpsertBody(BaseModel):
    emp_id: str
    team_code: str
    name: str | None = None
    participated: bool = True
    fg2_made: int = Field(default=0, ge=0)
    fg2_attempted: int = Field(default=0, ge=0)
    fg3_made: int = Field(default=0, ge=0)
    fg3_attempted: int = Field(default=0, ge=0)
    ft_made: int = Field(default=0, ge=0)
    ft_attempted: int = Field(default=0, ge=0)
    o_rebound: int = Field(default=0, ge=0)
    d_rebound: int = Field(default=0, ge=0)
    assist: int = Field(default=0, ge=0)
    steal: int = Field(default=0, ge=0)
    block: int = Field(default=0, ge=0)
    foul: int = Field(default=0, ge=0)
    turnover: int = Field(default=0, ge=0)


class DraftAssignBody(BaseModel):
    team_code: str | None = None


class DraftStartBody(BaseModel):
    season_id: int | None = None


class DraftParticipantBody(BaseModel):
    include: bool = True


DRAFT_TURN_ORDER = [
    models.LeagueTeamEnum.A,
    models.LeagueTeamEnum.B,
    models.LeagueTeamEnum.C,
]


def _resolve_draft_season(db: Session, season_id: int | None) -> models.LeagueSeason:
    if season_id:
        season = db.query(models.LeagueSeason).filter(models.LeagueSeason.id == season_id).first()
    else:
        season = db.query(models.LeagueSeason).order_by(models.LeagueSeason.id.desc()).first()
    if not season:
        raise HTTPException(status_code=404, detail="시즌을 찾을 수 없습니다.")
    return season


def _get_or_create_main_draft(db: Session, season_id: int, actor_emp_id: str | None = None) -> models.LeagueDraft:
    draft = db.query(models.LeagueDraft).filter(
        models.LeagueDraft.season_id == season_id,
        models.LeagueDraft.name == "MAIN",
    ).first()
    if draft:
        return draft

    draft = models.LeagueDraft(
        season_id=season_id,
        name="MAIN",
        status=models.LeagueDraftStatusEnum.PLANNED,
        total_rounds=1,
        updated_by=actor_emp_id,
    )
    db.add(draft)
    db.flush()
    return draft


def _draft_turn_from_count(picked_count: int):
    round_idx = picked_count // len(DRAFT_TURN_ORDER)
    pick_idx = picked_count % len(DRAFT_TURN_ORDER)
    order = DRAFT_TURN_ORDER if round_idx % 2 == 0 else list(reversed(DRAFT_TURN_ORDER))
    return {
        "round_no": round_idx + 1,
        "pick_no": pick_idx + 1,
        "team_code": order[pick_idx],
        "order": order,
    }


def _get_member_status_map(db: Session) -> dict[str, models.MemberStatusEnum]:
    status_map: dict[str, models.MemberStatusEnum] = {}
    for row in db.query(models.MemberProfile).all():
        status_map[row.emp_id] = row.member_status
    return status_map


def _eligible_draft_emp_ids(db: Session, users: list[models.User]) -> set[str]:
    status_map = _get_member_status_map(db)
    eligible = set()
    for u in users:
        status = status_map.get(u.emp_id, models.MemberStatusEnum.NORMAL)
        if status in (models.MemberStatusEnum.DORMANT, models.MemberStatusEnum.INJURED):
            continue
        eligible.add(u.emp_id)
    return eligible


def _selected_participant_ids(db: Session, season_id: int) -> set[str]:
    rows = db.query(models.LeagueDraftParticipant).filter(
        models.LeagueDraftParticipant.season_id == season_id
    ).all()
    return {r.emp_id for r in rows}


TEAM_ROTATIONS = [
    [
        (models.LeagueTeamEnum.A, models.LeagueTeamEnum.B),
        (models.LeagueTeamEnum.B, models.LeagueTeamEnum.C),
        (models.LeagueTeamEnum.C, models.LeagueTeamEnum.A),
    ],
    [
        (models.LeagueTeamEnum.B, models.LeagueTeamEnum.C),
        (models.LeagueTeamEnum.C, models.LeagueTeamEnum.A),
        (models.LeagueTeamEnum.A, models.LeagueTeamEnum.B),
    ],
    [
        (models.LeagueTeamEnum.C, models.LeagueTeamEnum.A),
        (models.LeagueTeamEnum.A, models.LeagueTeamEnum.B),
        (models.LeagueTeamEnum.B, models.LeagueTeamEnum.C),
    ],
]


def _week_pairings(week_no: int):
    return TEAM_ROTATIONS[(week_no - 1) % 3]


def _init_standing_row(team_code: models.LeagueTeamEnum) -> dict:
    return {
        "team_code": team_code,
        "played": 0,
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "forfeits": 0,
        "points": 0,
        "goals_for": 0,
        "goals_against": 0,
        "goal_diff": 0,
    }


def _add_head_to_head(hh: dict, team: models.LeagueTeamEnum, opp: models.LeagueTeamEnum, points: int, gf: int, ga: int):
    if team not in hh:
        hh[team] = {}
    if opp not in hh[team]:
        hh[team][opp] = {"points": 0, "gf": 0, "ga": 0}
    hh[team][opp]["points"] += points
    hh[team][opp]["gf"] += gf
    hh[team][opp]["ga"] += ga


def _calculate_standings(db: Session, season: models.LeagueSeason, week_no: int):
    teams = [models.LeagueTeamEnum.A, models.LeagueTeamEnum.B, models.LeagueTeamEnum.C]
    standings = {team: _init_standing_row(team) for team in teams}
    head_to_head = {team: {} for team in teams}

    matches = (
        db.query(models.LeagueMatch)
        .filter(
            models.LeagueMatch.season_id == season.id,
            models.LeagueMatch.week_no <= week_no,
            models.LeagueMatch.status.in_([models.LeagueMatchStatusEnum.FINAL, models.LeagueMatchStatusEnum.FORFEIT]),
        )
        .order_by(models.LeagueMatch.week_no.asc(), models.LeagueMatch.match_order.asc())
        .all()
    )

    for m in matches:
        home = m.home_team
        away = m.away_team

        if m.status == models.LeagueMatchStatusEnum.FORFEIT:
            if m.forfeited_team not in (home, away):
                continue

            loser = m.forfeited_team
            winner = away if loser == home else home

            standings[winner]["played"] += 1
            standings[loser]["played"] += 1
            standings[winner]["wins"] += 1
            standings[loser]["losses"] += 1
            standings[loser]["forfeits"] += 1
            standings[winner]["points"] += season.points_win
            standings[loser]["points"] += season.points_forfeit_loss

            gf_winner = abs(season.forfeit_goal_diff_penalty)
            ga_winner = 0
            gf_loser = 0
            ga_loser = abs(season.forfeit_goal_diff_penalty)

            standings[winner]["goals_for"] += gf_winner
            standings[winner]["goals_against"] += ga_winner
            standings[loser]["goals_for"] += gf_loser
            standings[loser]["goals_against"] += ga_loser

            _add_head_to_head(head_to_head, winner, loser, season.points_win, gf_winner, ga_winner)
            _add_head_to_head(head_to_head, loser, winner, season.points_forfeit_loss, gf_loser, ga_loser)
            continue

        if m.home_score is None or m.away_score is None:
            continue

        home_score = int(m.home_score)
        away_score = int(m.away_score)

        standings[home]["played"] += 1
        standings[away]["played"] += 1
        standings[home]["goals_for"] += home_score
        standings[home]["goals_against"] += away_score
        standings[away]["goals_for"] += away_score
        standings[away]["goals_against"] += home_score

        if home_score > away_score:
            home_points, away_points = season.points_win, season.points_loss
            standings[home]["wins"] += 1
            standings[away]["losses"] += 1
        elif home_score < away_score:
            home_points, away_points = season.points_loss, season.points_win
            standings[away]["wins"] += 1
            standings[home]["losses"] += 1
        else:
            home_points = away_points = season.points_draw
            standings[home]["draws"] += 1
            standings[away]["draws"] += 1

        standings[home]["points"] += home_points
        standings[away]["points"] += away_points

        _add_head_to_head(head_to_head, home, away, home_points, home_score, away_score)
        _add_head_to_head(head_to_head, away, home, away_points, away_score, home_score)

    for team in teams:
        standings[team]["goal_diff"] = standings[team]["goals_for"] - standings[team]["goals_against"]

    primary_sorted = sorted(
        teams,
        key=lambda t: (
            standings[t]["points"],
            standings[t]["goal_diff"],
        ),
        reverse=True,
    )

    ranked = []
    idx = 0
    while idx < len(primary_sorted):
        base = primary_sorted[idx]
        bucket = [base]
        idx += 1
        while idx < len(primary_sorted):
            t = primary_sorted[idx]
            if standings[t]["points"] == standings[base]["points"] and standings[t]["goal_diff"] == standings[base]["goal_diff"]:
                bucket.append(t)
                idx += 1
            else:
                break

        if len(bucket) == 1:
            ranked.extend(bucket)
            continue

        def mini_key(team: models.LeagueTeamEnum):
            mini_points = 0
            mini_goal_diff = 0
            for opp in bucket:
                if opp == team:
                    continue
                rec = head_to_head.get(team, {}).get(opp, {"points": 0, "gf": 0, "ga": 0})
                mini_points += rec["points"]
                mini_goal_diff += rec["gf"] - rec["ga"]
            return (
                mini_points,
                mini_goal_diff,
                standings[team]["goals_for"],
                team.value,
            )

        ranked.extend(sorted(bucket, key=mini_key, reverse=True))

    rows = []
    for rank, team in enumerate(ranked, start=1):
        hh_compact = {}
        for opp, rec in head_to_head.get(team, {}).items():
            hh_compact[opp.value] = rec
        row = {
            "rank": rank,
            "team_code": team,
            **standings[team],
            "head_to_head_json": json.dumps(hh_compact, ensure_ascii=False),
        }
        rows.append(row)

    return rows


def _upsert_standing_snapshot(db: Session, season: models.LeagueSeason, week_no: int, actor_emp_id: str | None = None):
    rows = _calculate_standings(db, season, week_no)
    db.query(models.LeagueStandingSnapshot).filter(
        models.LeagueStandingSnapshot.season_id == season.id,
        models.LeagueStandingSnapshot.week_no == week_no,
    ).delete(synchronize_session=False)

    for r in rows:
        db.add(
            models.LeagueStandingSnapshot(
                season_id=season.id,
                week_no=week_no,
                team_code=r["team_code"],
                rank=r["rank"],
                played=r["played"],
                wins=r["wins"],
                draws=r["draws"],
                losses=r["losses"],
                forfeits=r["forfeits"],
                points=r["points"],
                goals_for=r["goals_for"],
                goals_against=r["goals_against"],
                goal_diff=r["goal_diff"],
                head_to_head_json=r["head_to_head_json"],
                calculated_by=actor_emp_id,
            )
        )
    return rows


def _sync_schedule_for_season(db: Session, season: models.LeagueSeason, actor_emp_id: str):
    created_weeks = 0
    created_matches = 0

    existing_weeks = {
        w.week_no: w
        for w in db.query(models.LeagueWeek).filter(models.LeagueWeek.season_id == season.id).all()
    }

    existing_match_slots = {
        (m.week_no, m.match_order)
        for m in db.query(models.LeagueMatch).filter(models.LeagueMatch.season_id == season.id).all()
    }

    for week_no in range(1, season.total_weeks + 1):
        week_row = existing_weeks.get(week_no)
        target_week_date = None
        if season.start_date:
            target_week_date = season.start_date + timedelta(days=(week_no - 1) * 7)

        if week_row is None:
            week_row = models.LeagueWeek(
                season_id=season.id,
                week_no=week_no,
                week_date=target_week_date,
                is_trade_week=(week_no == 3),
                updated_by=actor_emp_id,
            )
            db.add(week_row)
            created_weeks += 1
        else:
            changed = False
            if week_row.week_date is None and target_week_date is not None:
                week_row.week_date = target_week_date
                changed = True
            if week_no == 3 and not week_row.is_trade_week:
                week_row.is_trade_week = True
                changed = True
            if changed:
                week_row.updated_by = actor_emp_id

        for order, (home, away) in enumerate(_week_pairings(week_no), start=1):
            if (week_no, order) in existing_match_slots:
                continue

            db.add(
                models.LeagueMatch(
                    season_id=season.id,
                    week_no=week_no,
                    match_order=order,
                    home_team=home,
                    away_team=away,
                    updated_by=actor_emp_id,
                )
            )
            existing_match_slots.add((week_no, order))
            created_matches += 1

    return {
        "created_weeks": created_weeks,
        "created_matches": created_matches,
    }


def _generate_next_season_code(db: Session, year: int) -> str:
    prefix = f"{year}-"
    rows = (
        db.query(models.LeagueSeason.code)
        .filter(models.LeagueSeason.code.like(f"{prefix}%"))
        .all()
    )

    max_seq = 0
    for (code,) in rows:
        raw = (code or "").strip()
        if not raw.startswith(prefix):
            continue
        suffix = raw[len(prefix):]
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))

    next_seq = max_seq + 1
    while True:
        candidate = f"{year}-{next_seq:02d}"
        exists = db.query(models.LeagueSeason).filter(models.LeagueSeason.code == candidate).first()
        if not exists:
            return candidate
        next_seq += 1


def _reset_team_assignments_for_new_season(db: Session, actor_emp_id: str):
    db.query(models.LeagueTeamAssignment).filter(
        (models.LeagueTeamAssignment.team_code.isnot(None)) |
        (models.LeagueTeamAssignment.is_captain.is_(True))
    ).update(
        {
            "team_code": None,
            "is_captain": False,
            "updated_by": actor_emp_id,
        },
        synchronize_session=False,
    )


@router.post("/admin/seasons")
def create_league_season(
    body: LeagueSeasonCreate,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    season_year = int(body.client_year or datetime.now().year)
    code = _generate_next_season_code(db, season_year)

    season = models.LeagueSeason(
        code=code,
        title=code,
        total_weeks=body.total_weeks,
        start_date=body.start_date,
        note=(body.note or "").strip() or None,
        created_by=admin_user.emp_id,
    )

    try:
        _reset_team_assignments_for_new_season(db, admin_user.emp_id)

        db.add(season)
        db.flush()

        sync_result = _sync_schedule_for_season(db, season, admin_user.emp_id)

        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "season_id": season.id,
        "code": season.code,
        "title": season.title,
        "total_weeks": season.total_weeks,
        "created_weeks": sync_result["created_weeks"],
        "created_matches": sync_result["created_matches"],
        "rulebook_basis": {
            "teams": ["A", "B", "C"],
            "weekly_matches": 3,
            "rotation_cycle_weeks": 3,
            "default_total_weeks": 8,
            "trade_week": 3,
        },
    }


@router.post("/admin/seasons/{season_id}/schedule/sync")
def sync_season_schedule(
    season_id: int,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    season = db.query(models.LeagueSeason).filter(models.LeagueSeason.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="시즌을 찾을 수 없습니다.")

    try:
        sync_result = _sync_schedule_for_season(db, season, admin_user.emp_id)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "season_id": season.id,
        "code": season.code,
        "total_weeks": season.total_weeks,
        **sync_result,
        "rulebook_basis": {
            "weekly_matches": 3,
            "rotation_cycle_weeks": 3,
            "trade_week": 3,
        },
    }


@router.get("/admin/seasons")
def list_league_seasons(
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.query(models.LeagueSeason).order_by(models.LeagueSeason.id.desc()).all()
    return [
        {
            "id": r.id,
            "code": r.code,
            "title": r.title,
            "status": r.status.value,
            "total_weeks": r.total_weeks,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/admin/seasons/{season_id}/schedule")
def get_season_schedule(
    season_id: int,
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    season = db.query(models.LeagueSeason).filter(models.LeagueSeason.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="시즌을 찾을 수 없습니다.")

    weeks = (
        db.query(models.LeagueWeek)
        .filter(models.LeagueWeek.season_id == season_id)
        .order_by(models.LeagueWeek.week_no.asc())
        .all()
    )
    matches = (
        db.query(models.LeagueMatch)
        .filter(models.LeagueMatch.season_id == season_id)
        .order_by(models.LeagueMatch.week_no.asc(), models.LeagueMatch.match_order.asc())
        .all()
    )

    by_week = {}
    for w in weeks:
        by_week[w.week_no] = {
            "week_no": w.week_no,
            "week_date": w.week_date,
            "status": w.status.value,
            "is_break_week": w.is_break_week,
            "is_trade_week": w.is_trade_week,
            "matches": [],
        }

    for m in matches:
        row = by_week.get(m.week_no)
        if row is None:
            continue
        row["matches"].append(
            {
                "match_id": m.id,
                "order": m.match_order,
                "home_team": m.home_team.value,
                "away_team": m.away_team.value,
                "status": m.status.value,
                "home_score": m.home_score,
                "away_score": m.away_score,
                "winner_team": m.winner_team.value if m.winner_team else None,
            }
        )

    return {
        "season": {
            "id": season.id,
            "code": season.code,
            "title": season.title,
            "status": season.status.value,
            "total_weeks": season.total_weeks,
        },
        "weeks": [by_week[k] for k in sorted(by_week.keys())],
    }


@router.post("/admin/matches/{match_id}/result")
def update_match_result(
    match_id: int,
    body: MatchResultUpdate,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(models.LeagueMatch).filter(models.LeagueMatch.id == match_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="경기를 찾을 수 없습니다.")

    week_row = (
        db.query(models.LeagueWeek)
        .filter(
            models.LeagueWeek.season_id == row.season_id,
            models.LeagueWeek.week_no == row.week_no,
        )
        .first()
    )
    if week_row and week_row.status == models.LeagueWeekStatusEnum.LOCKED:
        raise HTTPException(status_code=400, detail="잠금된 주차는 경기 결과를 수정할 수 없습니다.")

    try:
        status = models.LeagueMatchStatusEnum((body.status or "FINAL").upper().strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="status must be FINAL or FORFEIT")

    if status not in (models.LeagueMatchStatusEnum.FINAL, models.LeagueMatchStatusEnum.FORFEIT):
        raise HTTPException(status_code=400, detail="status must be FINAL or FORFEIT")

    if status == models.LeagueMatchStatusEnum.FINAL:
        if body.home_score is None or body.away_score is None:
            raise HTTPException(status_code=400, detail="FINAL은 home_score/away_score가 필요합니다.")
        row.home_score = int(body.home_score)
        row.away_score = int(body.away_score)
        row.forfeited_team = None

        if row.home_score > row.away_score:
            row.result_type = models.LeagueResultTypeEnum.WIN
            row.winner_team = row.home_team
        elif row.home_score < row.away_score:
            row.result_type = models.LeagueResultTypeEnum.WIN
            row.winner_team = row.away_team
        else:
            row.result_type = models.LeagueResultTypeEnum.DRAW
            row.winner_team = None
    else:
        if not body.forfeited_team:
            raise HTTPException(status_code=400, detail="FORFEIT은 forfeited_team(A/B/C)이 필요합니다.")
        try:
            forfeited = models.LeagueTeamEnum(body.forfeited_team.strip().upper())
        except ValueError:
            raise HTTPException(status_code=400, detail="forfeited_team must be A, B, or C")
        if forfeited not in (row.home_team, row.away_team):
            raise HTTPException(status_code=400, detail="forfeited_team은 해당 경기 팀이어야 합니다.")

        row.forfeited_team = forfeited
        row.home_score = None
        row.away_score = None
        row.result_type = models.LeagueResultTypeEnum.FORFEIT
        row.winner_team = row.away_team if forfeited == row.home_team else row.home_team

    row.status = status
    row.note = (body.note or "").strip() or row.note
    row.confirmed_by = admin_user.emp_id
    row.confirmed_at = row.confirmed_at or datetime.now()
    row.updated_by = admin_user.emp_id

    season = db.query(models.LeagueSeason).filter(models.LeagueSeason.id == row.season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="시즌을 찾을 수 없습니다.")

    try:
        snapshot_rows = _upsert_standing_snapshot(db, season, row.week_no, admin_user.emp_id)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "match_id": row.id,
        "season_id": row.season_id,
        "week_no": row.week_no,
        "status": row.status.value,
        "winner_team": row.winner_team.value if row.winner_team else None,
        "snapshot_week": row.week_no,
        "standings": [
            {
                "rank": s["rank"],
                "team_code": s["team_code"].value,
                "points": s["points"],
                "goal_diff": s["goal_diff"],
            }
            for s in snapshot_rows
        ],
    }


@router.get("/admin/seasons/{season_id}/standings")
def get_league_standings(
    season_id: int,
    week_no: int = Query(..., ge=1, le=30),
    refresh: bool = Query(default=False),
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    season = db.query(models.LeagueSeason).filter(models.LeagueSeason.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="시즌을 찾을 수 없습니다.")

    if refresh:
        try:
            _upsert_standing_snapshot(db, season, week_no, admin_user.emp_id)
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(status_code=500, detail="Database error.")

    snapshots = (
        db.query(models.LeagueStandingSnapshot)
        .filter(
            models.LeagueStandingSnapshot.season_id == season_id,
            models.LeagueStandingSnapshot.week_no == week_no,
        )
        .order_by(models.LeagueStandingSnapshot.rank.asc())
        .all()
    )

    # Fallback: if not cached yet, calculate on-the-fly without persisting.
    if not snapshots:
        rows = _calculate_standings(db, season, week_no)
        return {
            "season_id": season_id,
            "week_no": week_no,
            "cached": False,
            "rows": [
                {
                    "rank": r["rank"],
                    "team_code": r["team_code"].value,
                    "played": r["played"],
                    "wins": r["wins"],
                    "draws": r["draws"],
                    "losses": r["losses"],
                    "forfeits": r["forfeits"],
                    "points": r["points"],
                    "goals_for": r["goals_for"],
                    "goals_against": r["goals_against"],
                    "goal_diff": r["goal_diff"],
                }
                for r in rows
            ],
        }

    return {
        "season_id": season_id,
        "week_no": week_no,
        "cached": True,
        "rows": [
            {
                "rank": s.rank,
                "team_code": s.team_code.value,
                "played": s.played,
                "wins": s.wins,
                "draws": s.draws,
                "losses": s.losses,
                "forfeits": s.forfeits,
                "points": s.points,
                "goals_for": s.goals_for,
                "goals_against": s.goals_against,
                "goal_diff": s.goal_diff,
                "head_to_head": json.loads(s.head_to_head_json or "{}"),
            }
            for s in snapshots
        ],
    }


@router.post("/admin/seasons/{season_id}/trade-window/evaluate")
def evaluate_trade_window(
    season_id: int,
    body: TradeWindowEvaluateBody,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    season = db.query(models.LeagueSeason).filter(models.LeagueSeason.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="시즌을 찾을 수 없습니다.")

    week_no = body.week_no
    if week_no != 3:
        raise HTTPException(status_code=400, detail="룰북 기준 트레이드 평가는 3주차만 지원합니다.")

    try:
        _upsert_standing_snapshot(db, season, week_no, admin_user.emp_id)
        db.flush()

        standings = (
            db.query(models.LeagueStandingSnapshot)
            .filter(
                models.LeagueStandingSnapshot.season_id == season_id,
                models.LeagueStandingSnapshot.week_no == week_no,
            )
            .order_by(models.LeagueStandingSnapshot.rank.asc())
            .all()
        )
        if len(standings) < 3:
            raise HTTPException(status_code=400, detail="순위 데이터가 부족합니다.")

        leader = standings[0]
        lowest = standings[-1]
        gap = int(leader.points or 0) - int(lowest.points or 0)
        trade_allowed = gap > 5

        window = (
            db.query(models.LeagueTradeWindow)
            .filter(
                models.LeagueTradeWindow.season_id == season_id,
                models.LeagueTradeWindow.week_no == week_no,
            )
            .first()
        )
        if not window:
            window = models.LeagueTradeWindow(
                season_id=season_id,
                week_no=week_no,
            )
            db.add(window)

        window.eligible_team = lowest.team_code
        window.gap_with_leader = gap
        window.trade_allowed = trade_allowed
        window.status = (
            models.LeagueTradeWindowStatusEnum.OPEN
            if trade_allowed and not window.waived
            else models.LeagueTradeWindowStatusEnum.CLOSED
        )
        window.updated_by = admin_user.emp_id

        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "season_id": season_id,
        "week_no": week_no,
        "leader_team": leader.team_code.value,
        "leader_points": leader.points,
        "eligible_team": lowest.team_code.value,
        "eligible_team_points": lowest.points,
        "gap_with_leader": gap,
        "rule": "트레이드권은 최하위팀, 단 1위와 승점차 5점 이하면 미실시",
        "trade_allowed": trade_allowed,
        "window_status": window.status.value,
    }


@router.post("/admin/seasons/{season_id}/trade-window/waive")
def set_trade_waiver(
    season_id: int,
    body: TradeWindowWaiveBody,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    season = db.query(models.LeagueSeason).filter(models.LeagueSeason.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="시즌을 찾을 수 없습니다.")

    window = (
        db.query(models.LeagueTradeWindow)
        .filter(
            models.LeagueTradeWindow.season_id == season_id,
            models.LeagueTradeWindow.week_no == 3,
        )
        .first()
    )
    if not window:
        raise HTTPException(status_code=404, detail="트레이드 윈도우가 없습니다. 먼저 evaluate를 실행하세요.")

    window.waived = bool(body.waived)
    if body.note is not None:
        window.note = body.note.strip() or None

    if window.waived:
        # Rulebook: if eligible team waives, no league-wide trade is executed.
        window.trade_allowed = False
        window.status = models.LeagueTradeWindowStatusEnum.CLOSED
    else:
        window.status = (
            models.LeagueTradeWindowStatusEnum.OPEN
            if window.trade_allowed
            else models.LeagueTradeWindowStatusEnum.CLOSED
        )

    window.updated_by = admin_user.emp_id

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "season_id": season_id,
        "week_no": window.week_no,
        "eligible_team": window.eligible_team.value if window.eligible_team else None,
        "gap_with_leader": window.gap_with_leader,
        "waived": window.waived,
        "trade_allowed": window.trade_allowed,
        "window_status": window.status.value,
        "note": window.note,
    }


@router.post("/admin/seasons/{season_id}/trade-proposals")
def create_trade_proposal(
    season_id: int,
    body: TradeProposalCreateBody,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    season = db.query(models.LeagueSeason).filter(models.LeagueSeason.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="시즌을 찾을 수 없습니다.")

    window = (
        db.query(models.LeagueTradeWindow)
        .filter(
            models.LeagueTradeWindow.season_id == season_id,
            models.LeagueTradeWindow.week_no == 3,
        )
        .first()
    )
    if not window:
        raise HTTPException(status_code=400, detail="트레이드 윈도우가 없습니다. evaluate를 먼저 실행하세요.")
    if window.status != models.LeagueTradeWindowStatusEnum.OPEN or not window.trade_allowed or window.waived:
        raise HTTPException(status_code=400, detail="현재 트레이드가 허용되지 않습니다.")

    try:
        proposer_team = models.LeagueTeamEnum(body.proposer_team.strip().upper())
        partner_team = models.LeagueTeamEnum(body.partner_team.strip().upper())
    except ValueError:
        raise HTTPException(status_code=400, detail="team must be A, B, or C")

    if proposer_team == partner_team:
        raise HTTPException(status_code=400, detail="서로 다른 팀끼리만 트레이드할 수 있습니다.")
    if window.eligible_team and proposer_team != window.eligible_team:
        raise HTTPException(status_code=400, detail="룰북 기준 최하위 팀만 트레이드권을 가집니다.")

    proposer_assignment = db.query(models.LeagueTeamAssignment).filter(
        models.LeagueTeamAssignment.emp_id == body.proposer_out_emp_id.strip()
    ).first()
    partner_assignment = db.query(models.LeagueTeamAssignment).filter(
        models.LeagueTeamAssignment.emp_id == body.partner_out_emp_id.strip()
    ).first()
    if not proposer_assignment or proposer_assignment.team_code != proposer_team:
        raise HTTPException(status_code=400, detail="proposer_out_emp_id가 proposer_team에 속하지 않습니다.")
    if not partner_assignment or partner_assignment.team_code != partner_team:
        raise HTTPException(status_code=400, detail="partner_out_emp_id가 partner_team에 속하지 않습니다.")

    proposer_protected = (
        db.query(models.LeagueTradeProtectedPlayer)
        .filter(
            models.LeagueTradeProtectedPlayer.season_id == season_id,
            models.LeagueTradeProtectedPlayer.week_no == window.week_no,
            models.LeagueTradeProtectedPlayer.team_code == proposer_team,
            models.LeagueTradeProtectedPlayer.emp_id == body.proposer_out_emp_id.strip(),
        )
        .first()
    )
    partner_protected = (
        db.query(models.LeagueTradeProtectedPlayer)
        .filter(
            models.LeagueTradeProtectedPlayer.season_id == season_id,
            models.LeagueTradeProtectedPlayer.week_no == window.week_no,
            models.LeagueTradeProtectedPlayer.team_code == partner_team,
            models.LeagueTradeProtectedPlayer.emp_id == body.partner_out_emp_id.strip(),
        )
        .first()
    )
    if proposer_protected:
        raise HTTPException(status_code=400, detail="proposer_out_emp_id는 보호선수로 지정되어 트레이드할 수 없습니다.")
    if partner_protected:
        raise HTTPException(status_code=400, detail="partner_out_emp_id는 보호선수로 지정되어 트레이드할 수 없습니다.")

    row = models.LeagueTradeProposal(
        season_id=season_id,
        trade_window_id=window.id,
        proposer_team=proposer_team,
        partner_team=partner_team,
        proposer_out_emp_id=body.proposer_out_emp_id.strip(),
        partner_out_emp_id=body.partner_out_emp_id.strip(),
        proposer_protected=False,
        partner_protected=False,
        status=models.LeagueTradeStatusEnum.SUBMITTED,
        requested_by=admin_user.emp_id,
        note=(body.note or "").strip() or None,
    )

    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "proposal_id": row.id,
        "season_id": row.season_id,
        "status": row.status.value,
        "proposer_team": row.proposer_team.value,
        "partner_team": row.partner_team.value,
        "proposer_out_emp_id": row.proposer_out_emp_id,
        "partner_out_emp_id": row.partner_out_emp_id,
    }


@router.post("/admin/trade-proposals/{proposal_id}/decision")
def decide_trade_proposal(
    proposal_id: int,
    body: TradeProposalDecisionBody,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(models.LeagueTradeProposal).filter(models.LeagueTradeProposal.id == proposal_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="트레이드 제안을 찾을 수 없습니다.")

    if row.status not in (models.LeagueTradeStatusEnum.SUBMITTED, models.LeagueTradeStatusEnum.DRAFT):
        raise HTTPException(status_code=400, detail="이미 처리된 트레이드 제안입니다.")

    window = db.query(models.LeagueTradeWindow).filter(models.LeagueTradeWindow.id == row.trade_window_id).first()
    if not window:
        raise HTTPException(status_code=404, detail="트레이드 윈도우를 찾을 수 없습니다.")
    if window.status != models.LeagueTradeWindowStatusEnum.OPEN or not window.trade_allowed or window.waived:
        raise HTTPException(status_code=400, detail="현재 트레이드가 허용되지 않습니다.")

    if not body.approve:
        row.status = models.LeagueTradeStatusEnum.REJECTED
        row.approved_by = admin_user.emp_id
        row.approved_at = datetime.now()
        if body.note is not None:
            row.note = body.note.strip() or row.note
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(status_code=500, detail="Database error.")
        return {
            "proposal_id": row.id,
            "status": row.status.value,
        }

    p1 = db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id == row.proposer_out_emp_id).first()
    p2 = db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id == row.partner_out_emp_id).first()
    if not p1 or not p2:
        raise HTTPException(status_code=400, detail="트레이드 대상 선수 팀 정보를 찾을 수 없습니다.")
    if p1.team_code != row.proposer_team or p2.team_code != row.partner_team:
        raise HTTPException(status_code=400, detail="현재 팀 배정이 제안 당시와 달라 실행할 수 없습니다.")

    p1.team_code = row.partner_team
    p2.team_code = row.proposer_team
    p1.updated_by = admin_user.emp_id
    p2.updated_by = admin_user.emp_id

    row.status = models.LeagueTradeStatusEnum.EXECUTED
    row.approved_by = admin_user.emp_id
    row.approved_at = datetime.now()
    row.executed_at = datetime.now()
    if body.note is not None:
        row.note = body.note.strip() or row.note

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "proposal_id": row.id,
        "status": row.status.value,
        "proposer_out_emp_id": row.proposer_out_emp_id,
        "proposer_new_team": row.partner_team.value,
        "partner_out_emp_id": row.partner_out_emp_id,
        "partner_new_team": row.proposer_team.value,
    }


@router.post("/admin/seasons/{season_id}/trade-protected")
def set_trade_protected_players(
    season_id: int,
    body: TradeProtectedPlayersBody,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    season = db.query(models.LeagueSeason).filter(models.LeagueSeason.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="시즌을 찾을 수 없습니다.")

    window = (
        db.query(models.LeagueTradeWindow)
        .filter(
            models.LeagueTradeWindow.season_id == season_id,
            models.LeagueTradeWindow.week_no == body.week_no,
        )
        .first()
    )
    if not window:
        raise HTTPException(status_code=400, detail="트레이드 윈도우가 없습니다. evaluate를 먼저 실행하세요.")

    try:
        team_code = models.LeagueTeamEnum(body.team_code.strip().upper())
    except ValueError:
        raise HTTPException(status_code=400, detail="team_code must be A, B, or C")

    unique_emp_ids = []
    seen = set()
    for emp_id in body.emp_ids:
        key = (emp_id or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_emp_ids.append(key)

    max_count = 2 if (window.eligible_team and team_code == window.eligible_team) else 1
    if len(unique_emp_ids) > max_count:
        raise HTTPException(status_code=400, detail=f"{team_code.value}팀 보호선수는 최대 {max_count}명입니다.")

    for emp_id in unique_emp_ids:
        assign = db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id == emp_id).first()
        if not assign or assign.team_code != team_code:
            raise HTTPException(status_code=400, detail=f"{emp_id}는 {team_code.value}팀 소속이 아닙니다.")

    try:
        db.query(models.LeagueTradeProtectedPlayer).filter(
            models.LeagueTradeProtectedPlayer.season_id == season_id,
            models.LeagueTradeProtectedPlayer.week_no == body.week_no,
            models.LeagueTradeProtectedPlayer.team_code == team_code,
        ).delete(synchronize_session=False)

        for emp_id in unique_emp_ids:
            db.add(
                models.LeagueTradeProtectedPlayer(
                    season_id=season_id,
                    week_no=body.week_no,
                    team_code=team_code,
                    emp_id=emp_id,
                    marked_by=admin_user.emp_id,
                )
            )

        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "season_id": season_id,
        "week_no": body.week_no,
        "team_code": team_code.value,
        "max_count": max_count,
        "protected_emp_ids": unique_emp_ids,
    }


@router.get("/admin/seasons/{season_id}/trade-proposals")
def list_trade_proposals(
    season_id: int,
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.LeagueTradeProposal)
        .filter(models.LeagueTradeProposal.season_id == season_id)
        .order_by(models.LeagueTradeProposal.id.desc())
        .all()
    )
    return [
        {
            "proposal_id": r.id,
            "trade_window_id": r.trade_window_id,
            "status": r.status.value,
            "proposer_team": r.proposer_team.value,
            "partner_team": r.partner_team.value,
            "proposer_out_emp_id": r.proposer_out_emp_id,
            "partner_out_emp_id": r.partner_out_emp_id,
            "requested_by": r.requested_by,
            "approved_by": r.approved_by,
            "approved_at": r.approved_at,
            "executed_at": r.executed_at,
            "note": r.note,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


def _stat_to_dict(s: models.LeaguePlayerStat) -> dict:
    return {
        "id": s.id,
        "emp_id": s.emp_id,
        "name": s.name,
        "team_code": s.team_code.value,
        "participated": s.participated,
        "fg2_made": s.fg2_made,
        "fg2_attempted": s.fg2_attempted,
        "fg3_made": s.fg3_made,
        "fg3_attempted": s.fg3_attempted,
        "ft_made": s.ft_made,
        "ft_attempted": s.ft_attempted,
        "o_rebound": s.o_rebound,
        "d_rebound": s.d_rebound,
        "assist": s.assist,
        "steal": s.steal,
        "block": s.block,
        "foul": s.foul,
        "turnover": s.turnover,
        "total_points": s.fg2_made * 2 + s.fg3_made * 3 + s.ft_made,
        "updated_at": s.updated_at,
    }


def _analysis_match_sort_key(match: models.LeagueMatch):
    return (match.week_no, match.match_order, match.id)


def _aggregate_analysis_rows(rows: list[dict], game_count: int = 1) -> dict:
    agg = {
        "games": max(game_count, 0),
        "points": 0,
        "fg2_made": 0,
        "fg2_attempted": 0,
        "fg3_made": 0,
        "fg3_attempted": 0,
        "ft_made": 0,
        "ft_attempted": 0,
        "o_rebound": 0,
        "d_rebound": 0,
        "rebounds": 0,
        "assist": 0,
        "steal": 0,
        "block": 0,
        "foul": 0,
        "turnover": 0,
        "participants": 0,
    }
    for row in rows:
        agg["points"] += int(row.get("total_points") or 0)
        agg["fg2_made"] += int(row.get("fg2_made") or 0)
        agg["fg2_attempted"] += int(row.get("fg2_attempted") or 0)
        agg["fg3_made"] += int(row.get("fg3_made") or 0)
        agg["fg3_attempted"] += int(row.get("fg3_attempted") or 0)
        agg["ft_made"] += int(row.get("ft_made") or 0)
        agg["ft_attempted"] += int(row.get("ft_attempted") or 0)
        agg["o_rebound"] += int(row.get("o_rebound") or 0)
        agg["d_rebound"] += int(row.get("d_rebound") or 0)
        agg["assist"] += int(row.get("assist") or 0)
        agg["steal"] += int(row.get("steal") or 0)
        agg["block"] += int(row.get("block") or 0)
        agg["foul"] += int(row.get("foul") or 0)
        agg["turnover"] += int(row.get("turnover") or 0)
        if row.get("participated", True):
            agg["participants"] += 1

    agg["rebounds"] = agg["o_rebound"] + agg["d_rebound"]
    fg_made = agg["fg2_made"] + agg["fg3_made"]
    fg_attempted = agg["fg2_attempted"] + agg["fg3_attempted"]
    agg["fg_made"] = fg_made
    agg["fg_attempted"] = fg_attempted
    agg["fg_pct"] = round((fg_made / fg_attempted) * 100, 1) if fg_attempted else 0.0
    agg["fg3_pct"] = round((agg["fg3_made"] / agg["fg3_attempted"]) * 100, 1) if agg["fg3_attempted"] else 0.0
    agg["ft_pct"] = round((agg["ft_made"] / agg["ft_attempted"]) * 100, 1) if agg["ft_attempted"] else 0.0
    agg["efg_pct"] = round(((fg_made + (0.5 * agg["fg3_made"])) / fg_attempted) * 100, 1) if fg_attempted else 0.0
    ts_denom = 2 * (fg_attempted + (0.44 * agg["ft_attempted"]))
    agg["ts_pct"] = round((agg["points"] / ts_denom) * 100, 1) if ts_denom else 0.0
    agg["estimated_possessions"] = round(fg_attempted + (0.44 * agg["ft_attempted"]) - agg["o_rebound"] + agg["turnover"], 1)
    agg["ast_to_ratio"] = round(agg["assist"] / agg["turnover"], 2) if agg["turnover"] else (float(agg["assist"]) if agg["assist"] else None)
    games = max(agg["games"], 1)
    agg["avg_points"] = round(agg["points"] / games, 1)
    agg["avg_assist"] = round(agg["assist"] / games, 1)
    agg["avg_rebounds"] = round(agg["rebounds"] / games, 1)
    agg["avg_turnover"] = round(agg["turnover"] / games, 1)
    return agg


def _augment_team_advanced_metrics(team_agg: dict, opp_agg: dict | None = None) -> dict:
    advanced = dict(team_agg)
    team_possessions = float(team_agg.get("estimated_possessions") or 0)
    advanced["off_rating"] = round((team_agg["points"] / team_possessions) * 100, 1) if team_possessions > 0 else 0.0
    advanced["pace"] = team_possessions

    if opp_agg:
        opp_possessions = float(opp_agg.get("estimated_possessions") or 0)
        advanced["margin"] = int(team_agg["points"] - opp_agg["points"])
        advanced["def_rating"] = round((opp_agg["points"] / opp_possessions) * 100, 1) if opp_possessions > 0 else 0.0
        advanced["net_rating"] = round(advanced["off_rating"] - advanced["def_rating"], 1)

        total_rebounds = team_agg["rebounds"] + opp_agg["rebounds"]
        advanced["rebound_rate"] = round((team_agg["rebounds"] / total_rebounds) * 100, 1) if total_rebounds else 0.0
        orb_denom = team_agg["o_rebound"] + opp_agg["d_rebound"]
        drb_denom = team_agg["d_rebound"] + opp_agg["o_rebound"]
        advanced["oreb_rate"] = round((team_agg["o_rebound"] / orb_denom) * 100, 1) if orb_denom else 0.0
        advanced["dreb_rate"] = round((team_agg["d_rebound"] / drb_denom) * 100, 1) if drb_denom else 0.0
    else:
        advanced["margin"] = None
        advanced["def_rating"] = None
        advanced["net_rating"] = None
        advanced["rebound_rate"] = None
        advanced["oreb_rate"] = None
        advanced["dreb_rate"] = None

    return advanced


def _player_analysis_rebounds(row: dict) -> int:
    return int(row.get("o_rebound") or 0) + int(row.get("d_rebound") or 0)


def _player_analysis_impact(row: dict) -> float:
    points = int(row.get("total_points") or 0)
    rebounds = _player_analysis_rebounds(row)
    assists = int(row.get("assist") or 0)
    steals = int(row.get("steal") or 0)
    blocks = int(row.get("block") or 0)
    turnovers = int(row.get("turnover") or 0)
    fouls = int(row.get("foul") or 0)
    return round(points + (rebounds * 1.2) + (assists * 1.5) + ((steals + blocks) * 2.0) - (turnovers * 1.5) - (fouls * 0.5), 1)


def _player_summary_text(row: dict) -> str:
    points = int(row.get("total_points") or 0)
    rebounds = _player_analysis_rebounds(row)
    assists = int(row.get("assist") or 0)
    steals = int(row.get("steal") or 0)
    blocks = int(row.get("block") or 0)
    turnovers = int(row.get("turnover") or 0)
    fg_attempted = int(row.get("fg2_attempted") or 0) + int(row.get("fg3_attempted") or 0)
    fg_made = int(row.get("fg2_made") or 0) + int(row.get("fg3_made") or 0)
    fg_pct = round((fg_made / fg_attempted) * 100, 1) if fg_attempted else 0.0

    strengths = []
    cautions = []
    if points >= 15:
        strengths.append(f"득점 {points}점")
    elif points >= 8:
        strengths.append(f"공격 기여 {points}점")
    if rebounds >= 7:
        strengths.append(f"리바운드 {rebounds}개")
    if assists >= 5:
        strengths.append(f"연계 {assists}개")
    if steals + blocks >= 3:
        strengths.append(f"수비 이벤트 {steals + blocks}회")
    if fg_attempted >= 5 and fg_pct >= 50:
        strengths.append(f"야투 효율 {fg_pct}%")
    if turnovers >= 4:
        cautions.append(f"턴오버 {turnovers}회")
    if fg_attempted >= 5 and fg_pct < 35:
        cautions.append(f"슈팅 효율 {fg_pct}%")

    if not strengths:
        strengths.append("보이지 않는 역할 수행")

    summary = f"{' · '.join(strengths)} 중심의 경기였습니다."
    if cautions:
        summary += f" 보완 포인트는 {' · '.join(cautions)}입니다."
    return summary


def _player_advanced_metrics(row: dict) -> dict:
    fg_attempted = int(row.get("fg2_attempted") or 0) + int(row.get("fg3_attempted") or 0)
    fg_made = int(row.get("fg2_made") or 0) + int(row.get("fg3_made") or 0)
    ft_attempted = int(row.get("ft_attempted") or 0)
    points = int(row.get("total_points") or 0)
    turnovers = int(row.get("turnover") or 0)
    assists = int(row.get("assist") or 0)
    efg = round(((fg_made + (0.5 * int(row.get("fg3_made") or 0))) / fg_attempted) * 100, 1) if fg_attempted else 0.0
    ts_denom = 2 * (fg_attempted + (0.44 * ft_attempted))
    ts_pct = round((points / ts_denom) * 100, 1) if ts_denom else 0.0
    ast_to_ratio = round(assists / turnovers, 2) if turnovers else (float(assists) if assists else None)
    return {
        "efg_pct": efg,
        "ts_pct": ts_pct,
        "ast_to_ratio": ast_to_ratio,
    }


def _team_summary_text(team_code: str, team_agg: dict, opp_agg: dict | None = None, game_count: int = 1) -> str:
    strengths = []
    cautions = []
    if opp_agg:
        point_gap = int(team_agg["points"] - opp_agg["points"])
        rebound_gap = int(team_agg["rebounds"] - opp_agg["rebounds"])
        assist_gap = int(team_agg["assist"] - opp_agg["assist"])
        turnover_gap = int(team_agg["turnover"] - opp_agg["turnover"])
        fg_gap = round(team_agg["fg_pct"] - opp_agg["fg_pct"], 1)
        if point_gap > 0:
            strengths.append(f"득점 우세 {team_agg['points']}-{opp_agg['points']}")
        if fg_gap >= 8:
            strengths.append(f"야투 효율 우세 {team_agg['fg_pct']}%")
        if rebound_gap >= 4:
            strengths.append(f"리바운드 장악 +{rebound_gap}")
        if assist_gap >= 3:
            strengths.append(f"패스 전개 +{assist_gap}")
        if turnover_gap <= -2:
            strengths.append("실책 관리 우위")
        if team_agg.get("off_rating", 0) >= (opp_agg.get("off_rating", 0) + 8):
            strengths.append(f"오펜시브 레이팅 {team_agg['off_rating']}")
        if point_gap < 0:
            cautions.append(f"득점 열세 {team_agg['points']}-{opp_agg['points']}")
        if fg_gap <= -8:
            cautions.append(f"야투 효율 저하 {team_agg['fg_pct']}%")
        if rebound_gap <= -4:
            cautions.append(f"리바운드 열세 {rebound_gap}")
        if turnover_gap >= 3:
            cautions.append(f"턴오버 부담 {team_agg['turnover']}회")
        if team_agg.get("def_rating") is not None and team_agg["def_rating"] >= 110:
            cautions.append(f"디펜시브 레이팅 {team_agg['def_rating']}")

    if not strengths:
        strengths.append(f"평균 득점 {team_agg['avg_points']}점 유지")
    if not cautions and team_agg["turnover"] >= max(game_count * 8, 8):
        cautions.append(f"턴오버 관리 필요 {team_agg['turnover']}회")

    lead = f"{team_code}팀은 {game_count}경기 기준 평균 {team_agg['avg_points']}점, 야투율 {team_agg['fg_pct']}%, 평균 리바운드 {team_agg['avg_rebounds']}개를 기록했습니다."
    if game_count == 1:
        lead = f"{team_code}팀은 {team_agg['points']}점, 야투율 {team_agg['fg_pct']}%, 리바운드 {team_agg['rebounds']}개를 기록했습니다."
    if team_agg.get("off_rating") is not None and team_agg.get("def_rating") is not None:
        lead += f" 오펜시브 레이팅 {team_agg['off_rating']}, 디펜시브 레이팅 {team_agg['def_rating']} 기준입니다."
    tail = f" 강점은 {' · '.join(strengths)}입니다."
    if cautions:
        tail += f" 보완 포인트는 {' · '.join(cautions)}입니다."
    return lead + tail


def _build_match_analysis(match: models.LeagueMatch, stats: list[models.LeaguePlayerStat]) -> dict:
    stat_rows = [_stat_to_dict(s) for s in stats]
    grouped = {
        match.home_team.value: [row for row in stat_rows if row["team_code"] == match.home_team.value],
        match.away_team.value: [row for row in stat_rows if row["team_code"] == match.away_team.value],
    }

    home_agg = _aggregate_analysis_rows(grouped[match.home_team.value], 1)
    away_agg = _aggregate_analysis_rows(grouped[match.away_team.value], 1)
    home_agg = _augment_team_advanced_metrics(home_agg, away_agg)
    away_agg = _augment_team_advanced_metrics(away_agg, home_agg)
    margin = abs(home_agg["points"] - away_agg["points"])
    if home_agg["points"] > away_agg["points"]:
        game_result = f"{match.home_team.value}팀 우세"
    elif away_agg["points"] > home_agg["points"]:
        game_result = f"{match.away_team.value}팀 우세"
    else:
        game_result = "동률 흐름"

    game_tone = "접전" if margin <= 5 else "우세 경기" if margin <= 12 else "완승 흐름"
    game_summary = (
        f"{match.week_no}주차 {match.match_order}경기는 {game_result}로 보이며, 점수 차는 {margin}점입니다. "
        f"{game_tone} 양상에서 야투율과 턴오버 관리가 흐름을 갈랐습니다."
    )

    player_rows = []
    for row in stat_rows:
        player_rows.append(
            {
                "emp_id": row["emp_id"],
                "name": row.get("name") or row["emp_id"],
                "team_code": row["team_code"],
                "points": row["total_points"],
                "rebounds": _player_analysis_rebounds(row),
                "assist": row["assist"],
                "steal": row["steal"],
                "block": row["block"],
                "turnover": row["turnover"],
                "impact_score": _player_analysis_impact(row),
                **_player_advanced_metrics(row),
                "summary": _player_summary_text(row),
            }
        )
    player_rows.sort(key=lambda item: (item["impact_score"], item["points"], item["rebounds"]), reverse=True)

    return {
        "match_id": match.id,
        "week_no": match.week_no,
        "match_order": match.match_order,
        "summary": game_summary,
        "teams": [
            {
                "team_code": match.home_team.value,
                "score": home_agg["points"],
                "fg_pct": home_agg["fg_pct"],
                "fg3_pct": home_agg["fg3_pct"],
                "ft_pct": home_agg["ft_pct"],
                "rebounds": home_agg["rebounds"],
                "assist": home_agg["assist"],
                "turnover": home_agg["turnover"],
                "margin": home_agg["margin"],
                "off_rating": home_agg["off_rating"],
                "def_rating": home_agg["def_rating"],
                "net_rating": home_agg["net_rating"],
                "efg_pct": home_agg["efg_pct"],
                "ts_pct": home_agg["ts_pct"],
                "ast_to_ratio": home_agg["ast_to_ratio"],
                "rebound_rate": home_agg["rebound_rate"],
                "oreb_rate": home_agg["oreb_rate"],
                "dreb_rate": home_agg["dreb_rate"],
                "summary": _team_summary_text(match.home_team.value, home_agg, away_agg, 1),
            },
            {
                "team_code": match.away_team.value,
                "score": away_agg["points"],
                "fg_pct": away_agg["fg_pct"],
                "fg3_pct": away_agg["fg3_pct"],
                "ft_pct": away_agg["ft_pct"],
                "rebounds": away_agg["rebounds"],
                "assist": away_agg["assist"],
                "turnover": away_agg["turnover"],
                "margin": away_agg["margin"],
                "off_rating": away_agg["off_rating"],
                "def_rating": away_agg["def_rating"],
                "net_rating": away_agg["net_rating"],
                "efg_pct": away_agg["efg_pct"],
                "ts_pct": away_agg["ts_pct"],
                "ast_to_ratio": away_agg["ast_to_ratio"],
                "rebound_rate": away_agg["rebound_rate"],
                "oreb_rate": away_agg["oreb_rate"],
                "dreb_rate": away_agg["dreb_rate"],
                "summary": _team_summary_text(match.away_team.value, away_agg, home_agg, 1),
            },
        ],
        "top_players": player_rows[:6],
    }


def _build_cumulative_analysis(season_matches: list[models.LeagueMatch], stats_by_match: dict[int, list[models.LeaguePlayerStat]]) -> dict | None:
    completed_matches = []
    for match in season_matches:
        match_stats = stats_by_match.get(match.id, [])
        team_codes = {row.team_code.value for row in match_stats}
        if len(team_codes) >= 2:
            completed_matches.append(match)

    if not completed_matches:
        return None

    team_rows: dict[str, list[dict]] = {}
    team_games: dict[str, set[int]] = {}
    opponent_rows: dict[str, list[dict]] = {}
    player_rows: dict[str, dict] = {}

    for match in completed_matches:
        match_dict_rows = [_stat_to_dict(stat) for stat in stats_by_match.get(match.id, [])]
        match_team_groups: dict[str, list[dict]] = {}
        for row in match_dict_rows:
            match_team_groups.setdefault(row["team_code"], []).append(row)

        for team_code, rows in match_team_groups.items():
            for other_code, other_rows in match_team_groups.items():
                if other_code == team_code:
                    continue
                opponent_rows.setdefault(team_code, []).extend(other_rows)

        for row in match_dict_rows:
            team_code = row["team_code"]
            team_rows.setdefault(team_code, []).append(row)
            team_games.setdefault(team_code, set()).add(match.id)

            player_key = row["emp_id"]
            current = player_rows.get(player_key)
            if current is None:
                player_rows[player_key] = {
                    **row,
                    "games": 1,
                }
            else:
                current["games"] += 1
                for field in [
                    "fg2_made", "fg2_attempted", "fg3_made", "fg3_attempted", "ft_made", "ft_attempted",
                    "o_rebound", "d_rebound", "assist", "steal", "block", "foul", "turnover", "total_points",
                ]:
                    current[field] = int(current.get(field) or 0) + int(row.get(field) or 0)

    team_summaries = []
    for team_code, rows in team_rows.items():
        agg = _aggregate_analysis_rows(rows, len(team_games.get(team_code, set())))
        benchmark = None
        if opponent_rows.get(team_code):
            benchmark = _aggregate_analysis_rows(opponent_rows[team_code], len(team_games.get(team_code, set())))
            agg = _augment_team_advanced_metrics(agg, benchmark)
        else:
            agg = _augment_team_advanced_metrics(agg)
        team_summaries.append(
            {
                "team_code": team_code,
                "games": len(team_games.get(team_code, set())),
                "avg_points": agg["avg_points"],
                "fg_pct": agg["fg_pct"],
                "fg3_pct": agg["fg3_pct"],
                "avg_rebounds": agg["avg_rebounds"],
                "avg_assist": agg["avg_assist"],
                "avg_turnover": agg["avg_turnover"],
                "margin": agg["margin"],
                "off_rating": agg["off_rating"],
                "def_rating": agg["def_rating"],
                "net_rating": agg["net_rating"],
                "efg_pct": agg["efg_pct"],
                "ts_pct": agg["ts_pct"],
                "ast_to_ratio": agg["ast_to_ratio"],
                "rebound_rate": agg["rebound_rate"],
                "summary": _team_summary_text(team_code, agg, benchmark, len(team_games.get(team_code, set()))),
            }
        )

    team_summaries.sort(key=lambda item: (item["avg_points"], item["fg_pct"], item["avg_assist"]), reverse=True)

    cumulative_players = []
    for row in player_rows.values():
        cumulative_players.append(
            {
                "emp_id": row["emp_id"],
                "name": row.get("name") or row["emp_id"],
                "team_code": row["team_code"],
                "games": row["games"],
                "points": row["total_points"],
                "avg_points": round(int(row["total_points"] or 0) / max(int(row["games"] or 1), 1), 1),
                "rebounds": _player_analysis_rebounds(row),
                "assist": row["assist"],
                "impact_score": _player_analysis_impact(row),
                **_player_advanced_metrics(row),
                "summary": _player_summary_text(row),
            }
        )
    cumulative_players.sort(key=lambda item: (item["impact_score"], item["avg_points"], item["games"]), reverse=True)

    leader = team_summaries[0]
    overview = (
        f"현재까지 기록이 저장된 {len(completed_matches)}경기 누적 기준, {leader['team_code']}팀이 평균 득점 {leader['avg_points']}점으로 가장 안정적인 공격 흐름을 보였습니다. "
        f"선수 평가는 누적 임팩트와 경기당 생산성을 함께 반영했습니다."
    )

    return {
        "completed_matches": len(completed_matches),
        "overview": overview,
        "teams": team_summaries,
        "top_players": cumulative_players[:8],
    }


def _get_match_analysis_payload(match: models.LeagueMatch, db: Session) -> dict:
    match_stats = (
        db.query(models.LeaguePlayerStat)
        .filter(models.LeaguePlayerStat.match_id == match.id)
        .order_by(models.LeaguePlayerStat.team_code.asc(), models.LeaguePlayerStat.id.asc())
        .all()
    )

    season_matches = (
        db.query(models.LeagueMatch)
        .filter(models.LeagueMatch.season_id == match.season_id)
        .order_by(models.LeagueMatch.week_no.asc(), models.LeagueMatch.match_order.asc(), models.LeagueMatch.id.asc())
        .all()
    )
    selected_sort_key = _analysis_match_sort_key(match)
    included_match_ids = [m.id for m in season_matches if _analysis_match_sort_key(m) <= selected_sort_key]

    season_stats = (
        db.query(models.LeaguePlayerStat)
        .filter(models.LeaguePlayerStat.match_id.in_(included_match_ids))
        .order_by(models.LeaguePlayerStat.match_id.asc(), models.LeaguePlayerStat.team_code.asc(), models.LeaguePlayerStat.id.asc())
        .all()
    ) if included_match_ids else []

    stats_by_match: dict[int, list[models.LeaguePlayerStat]] = {}
    for stat in season_stats:
        stats_by_match.setdefault(stat.match_id, []).append(stat)

    match_analysis = _build_match_analysis(match, match_stats) if match_stats else None
    cumulative_analysis = _build_cumulative_analysis(
        [m for m in season_matches if m.id in included_match_ids],
        stats_by_match,
    )

    return {
        "match_id": match.id,
        "season_id": match.season_id,
        "match_analysis": match_analysis,
        "cumulative_analysis": cumulative_analysis,
    }


@router.get("/admin/matches/{match_id}/stats")
def get_match_stats(
    match_id: int,
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    match = db.query(models.LeagueMatch).filter(models.LeagueMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="경기를 찾을 수 없습니다.")

    stats = (
        db.query(models.LeaguePlayerStat)
        .filter(models.LeaguePlayerStat.match_id == match_id)
        .order_by(models.LeaguePlayerStat.team_code.asc(), models.LeaguePlayerStat.id.asc())
        .all()
    )
    return [_stat_to_dict(s) for s in stats]


@router.get("/admin/matches/{match_id}/analysis")
def get_match_analysis(
    match_id: int,
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    match = db.query(models.LeagueMatch).filter(models.LeagueMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="경기를 찾을 수 없습니다.")
    return _get_match_analysis_payload(match, db)


@router.post("/admin/matches/{match_id}/stats/upsert")
def upsert_match_player_stat(
    match_id: int,
    body: PlayerStatUpsertBody,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    match = db.query(models.LeagueMatch).filter(models.LeagueMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="경기를 찾을 수 없습니다.")

    try:
        team_code = models.LeagueTeamEnum(body.team_code.strip().upper())
    except ValueError:
        raise HTTPException(status_code=400, detail="team_code must be A, B, or C")

    if team_code not in (match.home_team, match.away_team):
        raise HTTPException(status_code=400, detail="해당 팀은 이 경기에 참가하지 않습니다.")

    emp_id = (body.emp_id or "").strip()
    if not emp_id:
        raise HTTPException(status_code=400, detail="emp_id is required")

    existing = (
        db.query(models.LeaguePlayerStat)
        .filter(
            models.LeaguePlayerStat.match_id == match_id,
            models.LeaguePlayerStat.emp_id == emp_id,
        )
        .first()
    )

    try:
        if existing:
            existing.team_code = team_code
            existing.name = body.name
            existing.participated = body.participated
            existing.fg2_made = body.fg2_made
            existing.fg2_attempted = body.fg2_attempted
            existing.fg3_made = body.fg3_made
            existing.fg3_attempted = body.fg3_attempted
            existing.ft_made = body.ft_made
            existing.ft_attempted = body.ft_attempted
            existing.o_rebound = body.o_rebound
            existing.d_rebound = body.d_rebound
            existing.assist = body.assist
            existing.steal = body.steal
            existing.block = body.block
            existing.foul = body.foul
            existing.turnover = body.turnover
            existing.entered_by = admin_user.emp_id
            stat = existing
        else:
            stat = models.LeaguePlayerStat(
                season_id=match.season_id,
                match_id=match_id,
                week_no=match.week_no,
                team_code=team_code,
                emp_id=emp_id,
                name=body.name,
                participated=body.participated,
                fg2_made=body.fg2_made,
                fg2_attempted=body.fg2_attempted,
                fg3_made=body.fg3_made,
                fg3_attempted=body.fg3_attempted,
                ft_made=body.ft_made,
                ft_attempted=body.ft_attempted,
                o_rebound=body.o_rebound,
                d_rebound=body.d_rebound,
                assist=body.assist,
                steal=body.steal,
                block=body.block,
                foul=body.foul,
                turnover=body.turnover,
                entered_by=admin_user.emp_id,
            )
            db.add(stat)

        db.commit()
        db.refresh(stat)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return _stat_to_dict(stat)


@router.get("/draft/board")
def get_draft_board(
    season_id: int | None = Query(default=None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    season = _resolve_draft_season(db, season_id)
    draft = _get_or_create_main_draft(db, season.id, current_user.emp_id)

    seasons = db.query(models.LeagueSeason).order_by(models.LeagueSeason.id.desc()).all()
    users = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).order_by(models.User.emp_id.asc()).all()

    assignments = {
        row.emp_id: row
        for row in db.query(models.LeagueTeamAssignment).all()
    }

    actor_assignment = assignments.get(current_user.emp_id)
    actor_team = actor_assignment.team_code.value if actor_assignment and actor_assignment.team_code else None
    actor_is_captain = bool(actor_assignment.is_captain) if actor_assignment else False
    actor_is_admin = has_admin_access(current_user)

    status_map = _get_member_status_map(db)
    eligible_emp_ids = _eligible_draft_emp_ids(db, users)
    selected_emp_ids = _selected_participant_ids(db, season.id)

    items = []
    for u in users:
        row = assignments.get(u.emp_id)
        member_status = status_map.get(u.emp_id, models.MemberStatusEnum.NORMAL)
        auto_excluded = member_status in (models.MemberStatusEnum.DORMANT, models.MemberStatusEnum.INJURED)
        is_participant = (u.emp_id in selected_emp_ids) and not auto_excluded
        items.append(
            {
                "emp_id": u.emp_id,
                "name": u.emp_id,
                "department": u.department,
                "team_code": row.team_code.value if row and row.team_code else None,
                "is_captain": bool(row.is_captain) if row else False,
                "member_status": member_status.value,
                "auto_excluded": auto_excluded,
                "is_participant": is_participant,
            }
        )

    picks = (
        db.query(models.LeagueDraftPick)
        .filter(models.LeagueDraftPick.draft_id == draft.id)
        .order_by(models.LeagueDraftPick.id.asc())
        .all()
    )

    participant_emp_ids = {i["emp_id"] for i in items if i["is_participant"]}
    assigned_participant_count = sum(1 for i in items if i["is_participant"] and i["team_code"] is not None)
    unassigned_count = len(participant_emp_ids) - assigned_participant_count
    picked_count = len(picks)

    if draft.status == models.LeagueDraftStatusEnum.OPEN and unassigned_count == 0:
        draft.status = models.LeagueDraftStatusEnum.CLOSED
        draft.closed_at = datetime.now()
        draft.updated_by = current_user.emp_id
        db.commit()
        db.refresh(draft)

    current_turn = None
    if draft.status == models.LeagueDraftStatusEnum.OPEN and unassigned_count > 0:
        current_turn = _draft_turn_from_count(picked_count)

    history = [
        {
            "round": p.round_no,
            "pick_no": p.pick_no,
            "team_code": p.team_code.value,
            "emp_id": p.selected_emp_id,
            "name": p.selected_emp_id,
            "picked_by": p.picked_by,
            "picked_at": p.picked_at,
        }
        for p in picks
    ]

    return {
        "seasons": [
            {
                "id": s.id,
                "code": s.code,
                "title": s.title,
                "status": s.status.value,
                "total_weeks": s.total_weeks,
                "start_date": s.start_date,
                "end_date": s.end_date,
            }
            for s in seasons
        ],
        "season": {
            "id": season.id,
            "code": season.code,
            "title": season.title,
            "status": season.status.value,
            "total_weeks": season.total_weeks,
            "start_date": season.start_date,
            "end_date": season.end_date,
        },
        "items": items,
        "me": {
            "emp_id": current_user.emp_id,
            "is_admin": actor_is_admin,
            "is_captain": actor_is_captain,
            "team_code": actor_team,
        },
        "draft": {
            "id": draft.id,
            "status": draft.status.value,
            "started_at": draft.started_at,
            "closed_at": draft.closed_at,
            "picked_count": picked_count,
            "participant_count": len(participant_emp_ids),
            "unassigned_count": unassigned_count,
            "current_round": current_turn["round_no"] if current_turn else None,
            "current_pick_no": current_turn["pick_no"] if current_turn else None,
            "current_turn_team": current_turn["team_code"].value if current_turn else None,
            "current_turn_order": [t.value for t in current_turn["order"]] if current_turn else [],
            "history": history,
        },
    }


@router.put("/draft/participants/{emp_id}")
def set_draft_participant(
    emp_id: str,
    body: DraftParticipantBody,
    season_id: int | None = Query(default=None),
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    season = _resolve_draft_season(db, season_id)

    user = db.query(models.User).filter(
        models.User.emp_id == emp_id,
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다.")

    status_map = _get_member_status_map(db)
    member_status = status_map.get(emp_id, models.MemberStatusEnum.NORMAL)
    if member_status in (models.MemberStatusEnum.DORMANT, models.MemberStatusEnum.INJURED):
        raise HTTPException(status_code=400, detail="휴면/부상 회원은 드래프트 참여 대상에서 자동 제외됩니다.")

    row = db.query(models.LeagueDraftParticipant).filter(
        models.LeagueDraftParticipant.season_id == season.id,
        models.LeagueDraftParticipant.emp_id == emp_id,
    ).first()

    if body.include:
        if row:
            row.updated_by = admin_user.emp_id
        else:
            db.add(models.LeagueDraftParticipant(
                season_id=season.id,
                emp_id=emp_id,
                updated_by=admin_user.emp_id,
            ))
    else:
        if row:
            db.delete(row)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "season_id": season.id,
        "emp_id": emp_id,
        "included": bool(body.include),
    }


@router.post("/draft/start")
def start_draft(
    body: DraftStartBody,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    actor_row = db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id == current_user.emp_id).first()
    actor_is_admin = has_admin_access(current_user)
    actor_is_captain = bool(actor_row and actor_row.is_captain and actor_row.team_code)

    if not actor_is_admin and not actor_is_captain:
        raise HTTPException(status_code=403, detail="드래프트 시작 권한이 없습니다.")

    season = _resolve_draft_season(db, body.season_id)
    draft = _get_or_create_main_draft(db, season.id, current_user.emp_id)

    users = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).all()
    eligible_emp_ids = _eligible_draft_emp_ids(db, users)
    selected_emp_ids = _selected_participant_ids(db, season.id)
    participant_emp_ids = selected_emp_ids.intersection(eligible_emp_ids)
    if len(participant_emp_ids) == 0:
        raise HTTPException(status_code=400, detail="드래프트 참여 인원을 먼저 지정해주세요.")

    if draft.status == models.LeagueDraftStatusEnum.CLOSED:
        raise HTTPException(status_code=400, detail="종료된 드래프트입니다.")

    if draft.status != models.LeagueDraftStatusEnum.OPEN:
        draft.status = models.LeagueDraftStatusEnum.OPEN
        draft.started_at = draft.started_at or datetime.now()
        draft.updated_by = current_user.emp_id

    try:
        db.commit()
        db.refresh(draft)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "draft_id": draft.id,
        "season_id": season.id,
        "status": draft.status.value,
        "started_at": draft.started_at,
    }


@router.put("/draft/assignments/{emp_id}")
def draft_assign_member(
    emp_id: str,
    body: DraftAssignBody,
    season_id: int | None = Query(default=None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    season = _resolve_draft_season(db, season_id)
    draft = _get_or_create_main_draft(db, season.id, current_user.emp_id)

    users = db.query(models.User).filter(
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).all()
    eligible_emp_ids = _eligible_draft_emp_ids(db, users)
    selected_emp_ids = _selected_participant_ids(db, season.id)
    participant_emp_ids = selected_emp_ids.intersection(eligible_emp_ids)

    actor_row = db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id == current_user.emp_id).first()
    actor_is_admin = has_admin_access(current_user)
    actor_is_captain = bool(actor_row and actor_row.is_captain and actor_row.team_code)

    if not actor_is_admin and not actor_is_captain:
        raise HTTPException(status_code=403, detail="드래프트 지명 권한이 없습니다.")

    if draft.status != models.LeagueDraftStatusEnum.OPEN:
        raise HTTPException(status_code=400, detail="드래프트가 시작되지 않았습니다.")

    picked_count = db.query(models.LeagueDraftPick).filter(models.LeagueDraftPick.draft_id == draft.id).count()
    turn = _draft_turn_from_count(picked_count)
    target_team = turn["team_code"]

    if not actor_is_admin and actor_row.team_code != target_team:
        raise HTTPException(status_code=400, detail="현재 본인 팀 턴이 아닙니다.")

    user = db.query(models.User).filter(
        models.User.emp_id == emp_id,
        models.User.role.in_(models.MEMBER_ROLE_VALUES),
        models.User.is_resigned.isnot(True),
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다.")
    if user.emp_id not in participant_emp_ids:
        raise HTTPException(status_code=400, detail="선택된 드래프트 참여 인원만 지명할 수 있습니다.")

    target_row = db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id == emp_id).first()
    if target_row and target_row.team_code is not None:
        raise HTTPException(status_code=400, detail="이미 팀이 배정된 인원은 지명할 수 없습니다.")

    if target_row:
        target_row.team_code = target_team
        target_row.is_captain = False
        target_row.updated_by = current_user.emp_id
    else:
        target_row = models.LeagueTeamAssignment(
            emp_id=emp_id,
            team_code=target_team,
            is_captain=False,
            updated_by=current_user.emp_id,
        )
        db.add(target_row)

    pick = models.LeagueDraftPick(
        draft_id=draft.id,
        season_id=season.id,
        round_no=turn["round_no"],
        pick_no=turn["pick_no"],
        team_code=target_team,
        selected_emp_id=user.emp_id,
        selected_name=user.emp_id,
        is_skipped=False,
        picked_by=current_user.emp_id,
        picked_at=datetime.now(),
    )
    db.add(pick)

    if turn["round_no"] > int(draft.total_rounds or 1):
        draft.total_rounds = turn["round_no"]
    draft.updated_by = current_user.emp_id

    db.flush()
    assigned_participant_count = db.query(models.LeagueTeamAssignment).filter(
        models.LeagueTeamAssignment.emp_id.in_(list(participant_emp_ids)),
        models.LeagueTeamAssignment.team_code.isnot(None),
    ).count()
    remaining_unassigned = len(participant_emp_ids) - assigned_participant_count
    if remaining_unassigned <= 0:
        draft.status = models.LeagueDraftStatusEnum.CLOSED
        draft.closed_at = datetime.now()

    try:
        db.commit()
        db.refresh(target_row)
        db.refresh(pick)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error.")

    return {
        "emp_id": target_row.emp_id,
        "team_code": target_row.team_code.value if target_row.team_code else None,
        "round": pick.round_no,
        "pick_no": pick.pick_no,
        "turn_team": pick.team_code.value,
        "draft_status": draft.status.value,
    }


# ── Public (any logged-in user) read-only endpoints ────────────────────────────


@router.get("/public/seasons")
def public_list_seasons(
    _user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all seasons — available to all members."""
    rows = db.query(models.LeagueSeason).order_by(models.LeagueSeason.id.desc()).all()
    season_stat_counts: dict[int, int] = {}
    season_recorded_match_ids: dict[int, set[int]] = {}

    all_stats = db.query(models.LeaguePlayerStat.season_id, models.LeaguePlayerStat.match_id).all()
    for season_id, match_id in all_stats:
        season_stat_counts[season_id] = season_stat_counts.get(season_id, 0) + 1
        season_recorded_match_ids.setdefault(season_id, set()).add(match_id)

    return [
        {
            "id": r.id,
            "code": r.code,
            "title": r.title,
            "status": r.status.value,
            "total_weeks": r.total_weeks,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "recorded_match_count": len(season_recorded_match_ids.get(r.id, set())),
            "recorded_stat_count": season_stat_counts.get(r.id, 0),
        }
        for r in rows
    ]


@router.get("/public/seasons/{season_id}/schedule")
def public_get_schedule(
    season_id: int,
    _user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Match schedule with results — available to all members."""
    season = db.query(models.LeagueSeason).filter(models.LeagueSeason.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="시즌을 찾을 수 없습니다.")

    weeks = (
        db.query(models.LeagueWeek)
        .filter(models.LeagueWeek.season_id == season_id)
        .order_by(models.LeagueWeek.week_no.asc())
        .all()
    )
    matches = (
        db.query(models.LeagueMatch)
        .filter(models.LeagueMatch.season_id == season_id)
        .order_by(models.LeagueMatch.week_no.asc(), models.LeagueMatch.match_order.asc())
        .all()
    )
    match_stat_counts: dict[int, int] = {}
    for match_id, in db.query(models.LeaguePlayerStat.match_id).filter(models.LeaguePlayerStat.season_id == season_id).all():
        match_stat_counts[match_id] = match_stat_counts.get(match_id, 0) + 1

    by_week: dict = {}
    for w in weeks:
        by_week[w.week_no] = {
            "week_no": w.week_no,
            "week_date": w.week_date,
            "matches": [],
        }

    for m in matches:
        row = by_week.get(m.week_no)
        if row is None:
            continue
        row["matches"].append(
            {
                "match_id": m.id,
                "order": m.match_order,
                "home_team": m.home_team.value,
                "away_team": m.away_team.value,
                "status": m.status.value,
                "home_score": m.home_score,
                "away_score": m.away_score,
                "winner_team": m.winner_team.value if m.winner_team else None,
                "forfeited_team": m.forfeited_team.value if m.forfeited_team else None,
                "has_stats": bool(match_stat_counts.get(m.id)),
                "stat_count": match_stat_counts.get(m.id, 0),
            }
        )

    return {
        "season": {
            "id": season.id,
            "code": season.code,
            "title": season.title,
            "total_weeks": season.total_weeks,
        },
        "weeks": [by_week[k] for k in sorted(by_week.keys())],
    }


@router.get("/public/seasons/{season_id}/standings")
def public_get_standings(
    season_id: int,
    week_no: int = Query(..., ge=1, le=30),
    _user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Standings snapshot for a given week — available to all members."""
    season = db.query(models.LeagueSeason).filter(models.LeagueSeason.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="시즌을 찾을 수 없습니다.")

    snapshots = (
        db.query(models.LeagueStandingSnapshot)
        .filter(
            models.LeagueStandingSnapshot.season_id == season_id,
            models.LeagueStandingSnapshot.week_no == week_no,
        )
        .order_by(models.LeagueStandingSnapshot.rank.asc())
        .all()
    )

    if not snapshots:
        rows = _calculate_standings(db, season, week_no)
        return {
            "season_id": season_id,
            "week_no": week_no,
            "rows": [
                {
                    "rank": r["rank"],
                    "team_code": r["team_code"].value,
                    "played": r["played"],
                    "wins": r["wins"],
                    "draws": r["draws"],
                    "losses": r["losses"],
                    "forfeits": r["forfeits"],
                    "points": r["points"],
                    "goals_for": r["goals_for"],
                    "goals_against": r["goals_against"],
                    "goal_diff": r["goal_diff"],
                }
                for r in rows
            ],
        }

    return {
        "season_id": season_id,
        "week_no": week_no,
        "rows": [
            {
                "rank": s.rank,
                "team_code": s.team_code.value,
                "played": s.played,
                "wins": s.wins,
                "draws": s.draws,
                "losses": s.losses,
                "forfeits": s.forfeits,
                "points": s.points,
                "goals_for": s.goals_for,
                "goals_against": s.goals_against,
                "goal_diff": s.goal_diff,
            }
            for s in snapshots
        ],
    }


@router.get("/public/seasons/{season_id}/stats/players")
def public_get_player_stats(
    season_id: int,
    week_no: int | None = Query(default=None, ge=1, le=30),
    _user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregated player stat totals for the season (or up to a specific week)."""
    season = db.query(models.LeagueSeason).filter(models.LeagueSeason.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="시즌을 찾을 수 없습니다.")

    q = db.query(models.LeaguePlayerStat).filter(
        models.LeaguePlayerStat.season_id == season_id,
        models.LeaguePlayerStat.participated == True,
    )
    if week_no is not None:
        q = q.filter(models.LeaguePlayerStat.week_no <= week_no)

    stats = q.all()

    # Aggregate by emp_id
    agg: dict = {}
    for s in stats:
        key = s.emp_id
        if key not in agg:
            agg[key] = {
                "emp_id": s.emp_id,
                "name": s.name or s.emp_id,
                "team_code": s.team_code.value,
                "games": 0,
                "fg2_made": 0, "fg2_attempted": 0,
                "fg3_made": 0, "fg3_attempted": 0,
                "ft_made": 0, "ft_attempted": 0,
                "o_rebound": 0, "d_rebound": 0,
                "assist": 0, "steal": 0, "block": 0,
                "foul": 0, "turnover": 0,
                "total_points": 0,
            }
        row = agg[key]
        row["games"]        += 1
        row["fg2_made"]     += s.fg2_made
        row["fg2_attempted"]+= s.fg2_attempted
        row["fg3_made"]     += s.fg3_made
        row["fg3_attempted"]+= s.fg3_attempted
        row["ft_made"]      += s.ft_made
        row["ft_attempted"] += s.ft_attempted
        row["o_rebound"]    += s.o_rebound
        row["d_rebound"]    += s.d_rebound
        row["assist"]       += s.assist
        row["steal"]        += s.steal
        row["block"]        += s.block
        row["foul"]         += s.foul
        row["turnover"]     += s.turnover
        row["total_points"] += s.fg2_made * 2 + s.fg3_made * 3 + s.ft_made
        # Keep latest known name
        if s.name:
            row["name"] = s.name

    result = sorted(agg.values(), key=lambda r: r["total_points"], reverse=True)
    return result


@router.get("/public/scoresheets/catalog")
def public_get_scoresheet_catalog(
    _user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    seasons = db.query(models.LeagueSeason).order_by(models.LeagueSeason.id.desc()).all()
    matches = (
        db.query(models.LeagueMatch)
        .order_by(models.LeagueMatch.season_id.desc(), models.LeagueMatch.week_no.asc(), models.LeagueMatch.match_order.asc())
        .all()
    )

    match_stat_counts: dict[int, int] = {}
    season_recorded_match_ids: dict[int, set[int]] = {}
    season_stat_counts: dict[int, int] = {}
    for season_id, match_id in db.query(models.LeaguePlayerStat.season_id, models.LeaguePlayerStat.match_id).all():
        match_stat_counts[match_id] = match_stat_counts.get(match_id, 0) + 1
        season_recorded_match_ids.setdefault(season_id, set()).add(match_id)
        season_stat_counts[season_id] = season_stat_counts.get(season_id, 0) + 1

    by_season: dict[int, dict] = {}
    for season in seasons:
        by_season[season.id] = {
            "id": season.id,
            "code": season.code,
            "title": season.title,
            "status": season.status.value,
            "total_weeks": season.total_weeks,
            "start_date": season.start_date,
            "end_date": season.end_date,
            "recorded_match_count": len(season_recorded_match_ids.get(season.id, set())),
            "recorded_stat_count": season_stat_counts.get(season.id, 0),
            "matches": [],
        }

    for match in matches:
        row = by_season.get(match.season_id)
        if row is None:
            continue
        stat_count = match_stat_counts.get(match.id, 0)
        row["matches"].append(
            {
                "match_id": match.id,
                "week_no": match.week_no,
                "order": match.match_order,
                "home_team": match.home_team.value,
                "away_team": match.away_team.value,
                "status": match.status.value,
                "home_score": match.home_score,
                "away_score": match.away_score,
                "winner_team": match.winner_team.value if match.winner_team else None,
                "forfeited_team": match.forfeited_team.value if match.forfeited_team else None,
                "has_stats": stat_count > 0,
                "stat_count": stat_count,
            }
        )

    result = list(by_season.values())
    result.sort(key=lambda season: (season["recorded_match_count"], season["id"]), reverse=True)
    return result


@router.get("/public/matches/{match_id}/stats")
def public_get_match_stats(
    match_id: int,
    _user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    match = db.query(models.LeagueMatch).filter(models.LeagueMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="경기를 찾을 수 없습니다.")

    stats = (
        db.query(models.LeaguePlayerStat)
        .filter(models.LeaguePlayerStat.match_id == match_id)
        .order_by(models.LeaguePlayerStat.team_code.asc(), models.LeaguePlayerStat.id.asc())
        .all()
    )
    return [_stat_to_dict(s) for s in stats]


@router.get("/public/matches/{match_id}/analysis")
def public_get_match_analysis(
    match_id: int,
    _user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    match = db.query(models.LeagueMatch).filter(models.LeagueMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="경기를 찾을 수 없습니다.")

    return _get_match_analysis_payload(match, db)
