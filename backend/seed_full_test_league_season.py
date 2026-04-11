from __future__ import annotations

from datetime import date, datetime, timedelta
import random

import models
from auth import hash_password
from database import SessionLocal
from routers.league import _generate_next_season_code, _sync_schedule_for_season, _upsert_standing_snapshot


RNG = random.Random(20260410)
TEST_NOTE = "FULL_8_WEEK_TEST_SEASON"

TEAM_ROSTERS = {
    models.LeagueTeamEnum.A: ["test001", "test002", "test003", "test004", "test005"],
    models.LeagueTeamEnum.B: ["test006", "test007", "test008", "test009", "test012"],
    models.LeagueTeamEnum.C: ["test013", "test014", "test015", "test016", "test017"],
}

PLAYER_NAMES = {
    "test001": "테스트01",
    "test002": "테스트02",
    "test003": "테스트03",
    "test004": "테스트04",
    "test005": "테스트05",
    "test006": "테스트06",
    "test007": "테스트07",
    "test008": "테스트08",
    "test009": "테스트09",
    "test012": "테스트12",
    "test013": "테스트13",
    "test014": "테스트14",
    "test015": "테스트15",
    "test016": "테스트16",
    "test017": "테스트17",
}


def upsert_user(db, emp_id: str, name: str):
    row = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if row:
        row.name = name
        row.department = "LEAGUE"
        row.role = models.RoleEnum.GENERAL
        row.is_first_login = False
        row.is_resigned = False
        return row

    row = models.User(
        emp_id=emp_id,
        name=name,
        department="LEAGUE",
        email=f"{emp_id}@example.com",
        hashed_password=hash_password("Pw123456!"),
        role=models.RoleEnum.GENERAL,
        is_first_login=False,
        temp_password=None,
        is_resigned=False,
    )
    db.add(row)
    return row


def upsert_member_profile(db, emp_id: str):
    row = db.query(models.MemberProfile).filter(models.MemberProfile.emp_id == emp_id).first()
    if row:
        row.member_status = models.MemberStatusEnum.NORMAL
        row.membership_type = models.MembershipTypeEnum.GENERAL
        return
    db.add(
        models.MemberProfile(
            emp_id=emp_id,
            member_status=models.MemberStatusEnum.NORMAL,
            membership_type=models.MembershipTypeEnum.GENERAL,
        )
    )


def split_points(total: int, parts: int) -> list[int]:
    minimums = [6, 5, 4, 3, 2][:parts]
    minimum_sum = sum(minimums)
    if total < minimum_sum:
        minimums = [max(total // parts, 0)] * parts
        for idx in range(total - sum(minimums)):
            minimums[idx % parts] += 1
        return minimums

    remaining = total - minimum_sum
    weights = [1.15 - (idx * 0.12) + RNG.random() * 0.18 for idx in range(parts)]
    weight_sum = sum(weights)
    values = []
    consumed = 0
    for idx, weight in enumerate(weights):
        if idx == parts - 1:
            extra = remaining - consumed
        else:
            extra = int(remaining * (weight / weight_sum))
            consumed += extra
        values.append(minimums[idx] + extra)

    remainder = total - sum(values)
    for idx in range(remainder):
        values[idx % parts] += 1
    return values


def build_player_stat(emp_id: str, team_code: models.LeagueTeamEnum, points: int, player_index: int) -> dict:
    fg3_made = RNG.randint(0, min(3, points // 3))
    remaining = points - (fg3_made * 3)
    ft_made = remaining % 2
    fg2_made = (remaining - ft_made) // 2

    fg2_attempted = fg2_made + RNG.randint(1, max(2, fg2_made // 2 + 1))
    fg3_attempted = fg3_made + RNG.randint(1, 3 if fg3_made else 2)
    ft_attempted = ft_made + RNG.randint(0, 2)

    o_rebound = max(0, RNG.randint(0, 2) + (1 if player_index >= 3 else 0))
    d_rebound = RNG.randint(1, 5) + (1 if player_index >= 2 else 0)
    assist = RNG.randint(1, 5) if player_index <= 1 else RNG.randint(0, 3)
    steal = RNG.randint(0, 3)
    block = RNG.randint(0, 2) if player_index >= 2 else RNG.randint(0, 1)
    foul = RNG.randint(1, 4)
    turnover = RNG.randint(1, 4)

    return {
        "emp_id": emp_id,
        "name": PLAYER_NAMES[emp_id],
        "team_code": team_code,
        "participated": True,
        "fg2_made": fg2_made,
        "fg2_attempted": fg2_attempted,
        "fg3_made": fg3_made,
        "fg3_attempted": fg3_attempted,
        "ft_made": ft_made,
        "ft_attempted": ft_attempted,
        "o_rebound": o_rebound,
        "d_rebound": d_rebound,
        "assist": assist,
        "steal": steal,
        "block": block,
        "foul": foul,
        "turnover": turnover,
    }


def create_match_stats(match: models.LeagueMatch) -> tuple[list[dict], int, int]:
    strength = {
        models.LeagueTeamEnum.A: 1.06,
        models.LeagueTeamEnum.B: 1.0,
        models.LeagueTeamEnum.C: 0.96,
    }
    home_score = 54 + int(strength[match.home_team] * 8) + RNG.randint(4, 20)
    away_score = 52 + int(strength[match.away_team] * 8) + RNG.randint(4, 18)
    if home_score == away_score:
        home_score += 1

    home_points = split_points(home_score, len(TEAM_ROSTERS[match.home_team]))
    away_points = split_points(away_score, len(TEAM_ROSTERS[match.away_team]))

    stats = []
    for idx, emp_id in enumerate(TEAM_ROSTERS[match.home_team]):
        stats.append(build_player_stat(emp_id, match.home_team, home_points[idx], idx))
    for idx, emp_id in enumerate(TEAM_ROSTERS[match.away_team]):
        stats.append(build_player_stat(emp_id, match.away_team, away_points[idx], idx))

    return stats, home_score, away_score


def seed_full_test_season():
    db = SessionLocal()
    try:
        admin = db.query(models.User).filter(models.User.emp_id == "admin").first()
        if not admin:
            raise RuntimeError("admin account is required before seeding the test season")

        for emp_id, name in PLAYER_NAMES.items():
            upsert_user(db, emp_id, name)
            upsert_member_profile(db, emp_id)

        season_year = date.today().year
        code = _generate_next_season_code(db, season_year)
        start_date = date.today() - timedelta(days=7 * 7)
        season = models.LeagueSeason(
            code=code,
            title=code,
            total_weeks=8,
            start_date=start_date,
            end_date=start_date + timedelta(days=7 * 7),
            status=models.LeagueSeasonStatusEnum.FINISHED,
            note=TEST_NOTE,
            created_by=admin.emp_id,
        )
        db.add(season)
        db.flush()
        _sync_schedule_for_season(db, season, admin.emp_id)
        db.flush()

        db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id.in_(list(PLAYER_NAMES.keys()))).delete(synchronize_session=False)
        for team_code, roster in TEAM_ROSTERS.items():
            for idx, emp_id in enumerate(roster):
                db.add(
                    models.LeagueTeamAssignment(
                        emp_id=emp_id,
                        team_code=team_code,
                        is_captain=(idx == 0),
                        updated_by=admin.emp_id,
                    )
                )

        matches = (
            db.query(models.LeagueMatch)
            .filter(models.LeagueMatch.season_id == season.id)
            .order_by(models.LeagueMatch.week_no.asc(), models.LeagueMatch.match_order.asc())
            .all()
        )

        stat_count = 0
        for match in matches:
            player_stats, home_score, away_score = create_match_stats(match)
            match.status = models.LeagueMatchStatusEnum.FINAL
            match.home_score = home_score
            match.away_score = away_score
            match.result_type = models.LeagueResultTypeEnum.WIN
            match.winner_team = match.home_team if home_score > away_score else match.away_team
            match.confirmed_by = admin.emp_id
            match.confirmed_at = datetime.now()
            match.updated_by = admin.emp_id

            for stat in player_stats:
                db.add(
                    models.LeaguePlayerStat(
                        season_id=season.id,
                        match_id=match.id,
                        week_no=match.week_no,
                        team_code=stat["team_code"],
                        emp_id=stat["emp_id"],
                        name=stat["name"],
                        participated=stat["participated"],
                        fg2_made=stat["fg2_made"],
                        fg2_attempted=stat["fg2_attempted"],
                        fg3_made=stat["fg3_made"],
                        fg3_attempted=stat["fg3_attempted"],
                        ft_made=stat["ft_made"],
                        ft_attempted=stat["ft_attempted"],
                        o_rebound=stat["o_rebound"],
                        d_rebound=stat["d_rebound"],
                        assist=stat["assist"],
                        steal=stat["steal"],
                        block=stat["block"],
                        foul=stat["foul"],
                        turnover=stat["turnover"],
                        entered_by=admin.emp_id,
                    )
                )
                stat_count += 1

            db.flush()

        weeks = (
            db.query(models.LeagueWeek)
            .filter(models.LeagueWeek.season_id == season.id)
            .order_by(models.LeagueWeek.week_no.asc())
            .all()
        )
        for week in weeks:
            week.status = models.LeagueWeekStatusEnum.LOCKED
            week.updated_by = admin.emp_id
            _upsert_standing_snapshot(db, season, week.week_no, admin.emp_id)

        db.commit()
        print(
            {
                "season_id": season.id,
                "code": season.code,
                "title": season.title,
                "weeks": len(weeks),
                "matches": len(matches),
                "stats": stat_count,
                "note": season.note,
            }
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_full_test_season()