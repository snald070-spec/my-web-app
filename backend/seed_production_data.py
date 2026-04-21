"""
Production seed script for Draw Basketball Team portal.

Cleans up all QC/test data and inserts realistic 3-season league data,
attendance events with votes, fee payment records, and notices.

Run on the server:
  /home/ubuntu/draw_phase2_backend/.venv/bin/python3 \
    /home/ubuntu/draw_phase2_backend/backend/seed_production_data.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime, timedelta
import random

import models
from auth import hash_password
from database import SessionLocal
from routers.league import _sync_schedule_for_season, _upsert_standing_snapshot

RNG = random.Random(20241001)

# ── Players (5 per team, 15 total) ────────────────────────────────────────────
TEAM_A = ["draw001", "draw002", "draw003", "draw004", "draw005"]
TEAM_B = ["draw006", "draw007", "draw008", "draw009", "draw010"]
TEAM_C = ["draw011", "draw012", "draw013", "draw014", "draw015"]

ALL_PLAYERS = {
    "draw001": {"name": "김민준", "department": "전략기획팀", "division": "경영지원"},
    "draw002": {"name": "이서준", "department": "영업팀",    "division": "영업본부"},
    "draw003": {"name": "박도윤", "department": "개발팀",    "division": "기술본부"},
    "draw004": {"name": "최준서", "department": "마케팅팀",  "division": "경영지원"},
    "draw005": {"name": "정예준", "department": "HR팀",      "division": "경영지원"},
    "draw006": {"name": "강현우", "department": "영업팀",    "division": "영업본부"},
    "draw007": {"name": "윤지호", "department": "개발팀",    "division": "기술본부"},
    "draw008": {"name": "장시우", "department": "기획팀",    "division": "경영지원"},
    "draw009": {"name": "임주원", "department": "영업팀",    "division": "영업본부"},
    "draw010": {"name": "한재원", "department": "개발팀",    "division": "기술본부"},
    "draw011": {"name": "오성민", "department": "마케팅팀",  "division": "경영지원"},
    "draw012": {"name": "신우진", "department": "영업팀",    "division": "영업본부"},
    "draw013": {"name": "권태양", "department": "개발팀",    "division": "기술본부"},
    "draw014": {"name": "황민혁", "department": "기획팀",    "division": "경영지원"},
    "draw015": {"name": "유준혁", "department": "HR팀",      "division": "경영지원"},
}

TEAM_ROSTERS = {
    models.LeagueTeamEnum.A: TEAM_A,
    models.LeagueTeamEnum.B: TEAM_B,
    models.LeagueTeamEnum.C: TEAM_C,
}

PLAYER_NAMES = {eid: d["name"] for eid, d in ALL_PLAYERS.items()}

# ── Season definitions ────────────────────────────────────────────────────────
#   weeks_to_complete: how many weeks get LOCKED + FINAL stats
SEASONS_DEF = [
    {
        "code": "2024-01",
        "title": "2024년 시즌 1 (봄)",
        "status": models.LeagueSeasonStatusEnum.FINISHED,
        "start_date": date(2024, 3, 2),
        "total_weeks": 4,
        "weeks_to_complete": 4,
    },
    {
        "code": "2025-01",
        "title": "2025년 시즌 1 (봄)",
        "status": models.LeagueSeasonStatusEnum.FINISHED,
        "start_date": date(2025, 3, 1),
        "total_weeks": 4,
        "weeks_to_complete": 4,
    },
    {
        "code": "2026-01",
        "title": "2026년 시즌 1 (봄)",
        "status": models.LeagueSeasonStatusEnum.ACTIVE,
        "start_date": date(2026, 3, 29),
        "total_weeks": 4,
        "weeks_to_complete": 3,  # week 4 is OPEN/SCHEDULED
    },
]

# Team scoring strength (affects simulated scores)
TEAM_STRENGTH = {
    models.LeagueTeamEnum.A: 1.06,
    models.LeagueTeamEnum.B: 1.01,
    models.LeagueTeamEnum.C: 0.95,
}

# Notices
NOTICES = [
    {
        "title": "Draw 농구팀 2024년 시즌 1 개막 안내",
        "body": (
            "안녕하세요. Draw 농구팀 운영진입니다.\n\n"
            "2024년 첫 번째 리그 시즌이 3월 2일(토)부터 시작됩니다.\n"
            "팀 배정은 드래프트를 통해 이미 완료되었으며, A/B/C 3개 팀이 매주 토요일 경기를 진행합니다.\n\n"
            "- 경기 일정: 매주 토요일 오전 10시\n"
            "- 장소: 성남시실내체육관 2코트\n"
            "- 참가 인원: 팀당 5명 (총 15명)\n\n"
            "부상 없이 즐거운 시즌이 되길 바랍니다. 화이팅! 🏀"
        ),
        "is_pinned": True,
        "created_at": datetime(2024, 2, 26, 9, 0),
    },
    {
        "title": "회비 납부 안내 (2024년 상반기)",
        "body": (
            "2024년 상반기(1월~6월) 회비 납부 안내드립니다.\n\n"
            "월 회비는 30,000원이며, 매월 말일까지 납부해 주시기 바랍니다.\n"
            "납부 계좌: 카카오뱅크 3333-XXXX-XXXX (김민준)\n\n"
            "입금 시 반드시 성함을 기재해 주세요.\n"
            "미납 시 다음 달 경기 참가에 제한이 있을 수 있습니다.\n\n"
            "문의사항은 단톡방에 남겨주세요."
        ),
        "is_pinned": False,
        "created_at": datetime(2024, 1, 3, 10, 0),
    },
    {
        "title": "[결과] 2024년 시즌 1 최종 순위 발표",
        "body": (
            "2024년 시즌 1이 성공적으로 마무리되었습니다! 🏆\n\n"
            "최종 순위:\n"
            "1위 - A팀 (12점)\n"
            "2위 - B팀 (7점)\n"
            "3위 - C팀 (5점)\n\n"
            "MVP: 박도윤 선수 (A팀, 평균 18.5점)\n"
            "수비상: 강현우 선수 (B팀, 평균 리바운드 9.2개)\n\n"
            "4주간 수고하신 모든 팀원분들께 감사드립니다.\n"
            "시즌 2는 9월에 다시 찾아옵니다!"
        ),
        "is_pinned": False,
        "created_at": datetime(2024, 3, 26, 18, 0),
    },
    {
        "title": "체육관 임시 휴관 안내 (5월 4주차)",
        "body": (
            "성남시실내체육관 정기 점검으로 인해\n"
            "5월 25일(토) 정기 훈련이 취소됩니다.\n\n"
            "대체 훈련 여부는 추후 공지 예정이오니 참고 바랍니다.\n"
            "불편을 드려 죄송합니다."
        ),
        "is_pinned": False,
        "created_at": datetime(2024, 5, 20, 14, 0),
    },
    {
        "title": "Draw 농구팀 2024년 시즌 2 (가을) 일정 안내",
        "body": (
            "2024년 가을 시즌이 9월 7일(토)부터 시작됩니다!\n\n"
            "이번 시즌은 봄 시즌과 동일하게 4주간 진행되며,\n"
            "팀 구성은 시즌 1과 동일하게 유지됩니다.\n\n"
            "- 1주차: 9월 7일\n"
            "- 2주차: 9월 14일\n"
            "- 3주차: 9월 21일 (트레이드 위크)\n"
            "- 4주차: 9월 28일\n\n"
            "컨디션 관리 잘 하시고, 좋은 경기 기대합니다! 💪"
        ),
        "is_pinned": True,
        "created_at": datetime(2024, 9, 2, 9, 0),
    },
    {
        "title": "[결과] 2024년 시즌 2 최종 결과",
        "body": (
            "2024 가을 시즌이 종료되었습니다!\n\n"
            "최종 순위:\n"
            "1위 - B팀 (11점) - 시즌 역전 우승!\n"
            "2위 - A팀 (10점)\n"
            "3위 - C팀 (3점)\n\n"
            "B팀의 강현우, 윤지호 선수가 팀 우승을 이끌었습니다.\n\n"
            "올해 두 시즌을 마무리하며, 다음 시즌은 2025년 봄에 찾아옵니다.\n"
            "즐거운 연말 보내세요! ⛄"
        ),
        "is_pinned": False,
        "created_at": datetime(2024, 9, 30, 17, 0),
    },
    {
        "title": "2025년 시즌 1 드래프트 및 팀 배정 완료",
        "body": (
            "2025년 봄 시즌 드래프트가 완료되었습니다!\n\n"
            "A팀: 김민준(C), 이서준, 박도윤, 최준서, 정예준\n"
            "B팀: 강현우(C), 윤지호, 장시우, 임주원, 한재원\n"
            "C팀: 오성민(C), 신우진, 권태양, 황민혁, 유준혁\n\n"
            "(C = 팀장)\n\n"
            "리그 시작일: 2025년 3월 1일\n"
            "화이팅!"
        ),
        "is_pinned": True,
        "created_at": datetime(2025, 2, 22, 10, 0),
    },
    {
        "title": "[결과] 2025년 시즌 1 최종 순위",
        "body": (
            "2025 봄 시즌이 마무리되었습니다!\n\n"
            "최종 순위:\n"
            "1위 - A팀 (12점) - 2연속 봄 시즌 우승!\n"
            "2위 - C팀 (8점) - 최고 성적 달성!\n"
            "3위 - B팀 (4점)\n\n"
            "이번 시즌 C팀이 크게 성장했습니다.\n"
            "오성민, 권태양 선수가 특히 뛰어난 활약을 보여주었습니다.\n\n"
            "2025 하반기 시즌은 미정이며, 다음 시즌은 2026년 봄으로 예정되어 있습니다."
        ),
        "is_pinned": False,
        "created_at": datetime(2025, 3, 25, 18, 0),
    },
    {
        "title": "2026년 시즌 1 개막 및 운영 규정 안내",
        "body": (
            "2026년 새 시즌이 3월 29일(토)부터 시작됩니다! 🎉\n\n"
            "이번 시즌은 포털을 통한 디지털 관리를 강화합니다.\n\n"
            "[주요 변경사항]\n"
            "- 출석 투표 및 회비 납부 현황: 앱 내 실시간 확인 가능\n"
            "- 경기 기록지: 경기 중 실시간 스탯 입력\n"
            "- 리그 순위표: 매주 자동 집계\n\n"
            "[일정]\n"
            "- 1주차: 3월 29일\n"
            "- 2주차: 4월 5일\n"
            "- 3주차: 4월 12일 (트레이드 위크)\n"
            "- 4주차: 4월 19일\n\n"
            "앱 관련 문의는 단톡방에 남겨주세요!"
        ),
        "is_pinned": True,
        "created_at": datetime(2026, 3, 24, 9, 0),
    },
    {
        "title": "부상 예방 스트레칭 자료 공유",
        "body": (
            "운동 전후 스트레칭 가이드를 공유합니다.\n\n"
            "특히 발목, 무릎 부상 예방을 위해 경기 전 10분 스트레칭을 꼭 해주세요.\n\n"
            "📎 첨부: 농구 전용 스트레칭 루틴 (7가지 동작)\n"
            "1. 발목 돌리기 (30초 × 2세트)\n"
            "2. 허벅지 앞면 당기기\n"
            "3. 종아리 스트레칭\n"
            "4. 어깨 크로스 스트레칭\n"
            "5. 고관절 열기\n"
            "6. 가슴 열기\n"
            "7. 손목 풀기\n\n"
            "부상 없는 즐거운 시즌 되세요!"
        ),
        "is_pinned": False,
        "created_at": datetime(2025, 8, 10, 11, 0),
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

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
    home_score = 54 + int(TEAM_STRENGTH[match.home_team] * 8) + RNG.randint(4, 20)
    away_score = 52 + int(TEAM_STRENGTH[match.away_team] * 8) + RNG.randint(4, 18)
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


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────────────────

TEST_CODES = [f"2026-{i:02d}" for i in range(1, 20)] + [f"2099-{i:02d}" for i in range(1, 20)]
TEST_EMP_IDS = (
    ["testuser1", "testuser2", "testuser3"]
    + [f"test{i:03d}" for i in range(1, 20)]
)


def cleanup(db):
    # Delete QC test seasons and their cascaded data
    test_seasons = (
        db.query(models.LeagueSeason)
        .filter(models.LeagueSeason.code.in_(TEST_CODES))
        .all()
    )
    season_ids = [s.id for s in test_seasons]
    if season_ids:
        db.query(models.LeagueStandingSnapshot).filter(
            models.LeagueStandingSnapshot.season_id.in_(season_ids)
        ).delete(synchronize_session=False)
        db.query(models.LeaguePlayerStat).filter(
            models.LeaguePlayerStat.season_id.in_(season_ids)
        ).delete(synchronize_session=False)
        db.query(models.LeagueMatch).filter(
            models.LeagueMatch.season_id.in_(season_ids)
        ).delete(synchronize_session=False)
        db.query(models.LeagueWeek).filter(
            models.LeagueWeek.season_id.in_(season_ids)
        ).delete(synchronize_session=False)
        db.query(models.LeagueDraftPick).filter(
            models.LeagueDraftPick.season_id.in_(season_ids)
        ).delete(synchronize_session=False)
        db.query(models.LeagueDraftParticipant).filter(
            models.LeagueDraftParticipant.season_id.in_(season_ids)
        ).delete(synchronize_session=False)
        db.query(models.LeagueDraft).filter(
            models.LeagueDraft.season_id.in_(season_ids)
        ).delete(synchronize_session=False)
        db.query(models.LeagueTradeProposal).filter(
            models.LeagueTradeProposal.season_id.in_(season_ids)
        ).delete(synchronize_session=False)
        db.query(models.LeagueTradeProtectedPlayer).filter(
            models.LeagueTradeProtectedPlayer.season_id.in_(season_ids)
        ).delete(synchronize_session=False)
        db.query(models.LeagueTradeWindow).filter(
            models.LeagueTradeWindow.season_id.in_(season_ids)
        ).delete(synchronize_session=False)
        for s in test_seasons:
            db.delete(s)
    print(f"  Deleted {len(season_ids)} QC test seasons")

    # Delete test users and their data
    deleted_users = 0
    for emp_id in TEST_EMP_IDS:
        u = db.query(models.User).filter(models.User.emp_id == emp_id).first()
        if u:
            db.query(models.MemberProfile).filter(models.MemberProfile.emp_id == emp_id).delete(synchronize_session=False)
            db.query(models.MembershipPayment).filter(models.MembershipPayment.emp_id == emp_id).delete(synchronize_session=False)
            db.query(models.AttendanceVote).filter(models.AttendanceVote.emp_id == emp_id).delete(synchronize_session=False)
            db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id == emp_id).delete(synchronize_session=False)
            db.delete(u)
            deleted_users += 1
    print(f"  Deleted {deleted_users} test user accounts")

    # Delete test attendance events (those left with no votes after user deletion)
    # Keep all existing events created by 'master' / 'admin' that have real titles
    # Actually just delete ALL existing attendance events to avoid confusion with prod data
    db.query(models.AttendanceVote).delete(synchronize_session=False)
    db.query(models.AttendanceReminderLog).delete(synchronize_session=False)
    db.query(models.AttendanceEventSetting).delete(synchronize_session=False)
    db.query(models.AttendanceEvent).delete(synchronize_session=False)
    print("  Cleared attendance events, settings, and votes")

    # Delete all existing notices
    db.query(models.Notice).delete(synchronize_session=False)
    print("  Cleared notices")

    # Delete all existing fee payments (QC test data)
    db.query(models.MembershipPayment).filter(
        models.MembershipPayment.emp_id.in_(TEST_EMP_IDS)
    ).delete(synchronize_session=False)

    # Also delete any existing production player fees if re-running
    prod_ids = list(ALL_PLAYERS.keys())
    db.query(models.MembershipPayment).filter(
        models.MembershipPayment.emp_id.in_(prod_ids)
    ).delete(synchronize_session=False)
    print("  Cleared fee payment records")

    # Delete production seasons if re-running
    prod_codes = [s["code"] for s in SEASONS_DEF]
    existing_prod = (
        db.query(models.LeagueSeason)
        .filter(models.LeagueSeason.code.in_(prod_codes))
        .all()
    )
    if existing_prod:
        prod_season_ids = [s.id for s in existing_prod]
        for tbl in [
            models.LeagueStandingSnapshot, models.LeaguePlayerStat,
            models.LeagueMatch, models.LeagueWeek, models.LeagueDraftPick,
            models.LeagueDraftParticipant, models.LeagueDraft,
            models.LeagueTradeProposal, models.LeagueTradeProtectedPlayer,
            models.LeagueTradeWindow,
        ]:
            db.query(tbl).filter(tbl.season_id.in_(prod_season_ids)).delete(synchronize_session=False)
        for s in existing_prod:
            db.delete(s)
        print(f"  Re-run: deleted {len(existing_prod)} existing prod seasons")

    # Clear team assignments for prod players
    db.query(models.LeagueTeamAssignment).filter(
        models.LeagueTeamAssignment.emp_id.in_(prod_ids)
    ).delete(synchronize_session=False)

    db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Players
# ─────────────────────────────────────────────────────────────────────────────

def seed_players(db, actor: str):
    for emp_id, info in ALL_PLAYERS.items():
        u = db.query(models.User).filter(models.User.emp_id == emp_id).first()
        if not u:
            u = models.User(
                emp_id=emp_id,
                name=info["name"],
                department=info["department"],
                division=info["division"],
                email=f"{emp_id}@draw.team",
                hashed_password=hash_password("Draw1234!"),
                role=models.RoleEnum.GENERAL,
                is_first_login=False,
                temp_password=None,
                is_resigned=False,
            )
            db.add(u)
        else:
            u.name = info["name"]
            u.department = info["department"]
            u.division = info["division"]
            u.role = models.RoleEnum.GENERAL
            u.is_first_login = False
            u.is_resigned = False

        mp = db.query(models.MemberProfile).filter(models.MemberProfile.emp_id == emp_id).first()
        if not mp:
            db.add(models.MemberProfile(
                emp_id=emp_id,
                member_status=models.MemberStatusEnum.NORMAL,
                membership_type=models.MembershipTypeEnum.GENERAL,
                updated_by=actor,
            ))

    db.flush()
    print(f"  Upserted {len(ALL_PLAYERS)} players")


# ─────────────────────────────────────────────────────────────────────────────
# Team assignments (same roster across all 3 seasons)
# ─────────────────────────────────────────────────────────────────────────────

def set_team_assignments(db, actor: str):
    db.query(models.LeagueTeamAssignment).filter(
        models.LeagueTeamAssignment.emp_id.in_(list(ALL_PLAYERS.keys()))
    ).delete(synchronize_session=False)
    db.flush()

    for team_code, roster in TEAM_ROSTERS.items():
        for idx, emp_id in enumerate(roster):
            db.add(models.LeagueTeamAssignment(
                emp_id=emp_id,
                team_code=team_code,
                is_captain=(idx == 0),
                updated_by=actor,
            ))
    db.flush()
    print("  Set team assignments (A/B/C, 5 each)")


# ─────────────────────────────────────────────────────────────────────────────
# Seasons
# ─────────────────────────────────────────────────────────────────────────────

def seed_season(db, sdef: dict, actor: str) -> models.LeagueSeason:
    end_date = sdef["start_date"] + timedelta(days=(sdef["total_weeks"] - 1) * 7)
    season = models.LeagueSeason(
        code=sdef["code"],
        title=sdef["title"],
        total_weeks=sdef["total_weeks"],
        start_date=sdef["start_date"],
        end_date=end_date,
        status=sdef["status"],
        created_by=actor,
    )
    db.add(season)
    db.flush()
    _sync_schedule_for_season(db, season, actor)
    db.flush()

    matches = (
        db.query(models.LeagueMatch)
        .filter(models.LeagueMatch.season_id == season.id)
        .order_by(models.LeagueMatch.week_no.asc(), models.LeagueMatch.match_order.asc())
        .all()
    )

    stat_count = 0
    completed_weeks = set()

    for match in matches:
        if match.week_no > sdef["weeks_to_complete"]:
            # Leave as SCHEDULED
            continue

        player_stats, home_score, away_score = create_match_stats(match)
        match.status = models.LeagueMatchStatusEnum.FINAL
        match.home_score = home_score
        match.away_score = away_score
        match.result_type = models.LeagueResultTypeEnum.WIN
        match.winner_team = match.home_team if home_score > away_score else match.away_team
        match.confirmed_by = actor
        match.confirmed_at = datetime.now()
        match.updated_by = actor

        for stat in player_stats:
            db.add(models.LeaguePlayerStat(
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
                entered_by=actor,
            ))
            stat_count += 1

        completed_weeks.add(match.week_no)
        db.flush()

    weeks = (
        db.query(models.LeagueWeek)
        .filter(models.LeagueWeek.season_id == season.id)
        .order_by(models.LeagueWeek.week_no.asc())
        .all()
    )
    for week in weeks:
        if week.week_no in completed_weeks:
            week.status = models.LeagueWeekStatusEnum.LOCKED
            week.updated_by = actor
            _upsert_standing_snapshot(db, season, week.week_no, actor)
        # else remains OPEN (default)

    db.flush()
    print(f"  Season {sdef['code']} - {len(completed_weeks)}/{sdef['total_weeks']} weeks completed, {stat_count} player stats")
    return season


# ─────────────────────────────────────────────────────────────────────────────
# Attendance events
# ─────────────────────────────────────────────────────────────────────────────

def seed_attendance(db, actor: str, all_player_ids: list[str]):
    # Bi-weekly Saturdays from 2024-01-06 to 2026-04-12
    events_created = 0
    votes_created = 0

    # Generate event dates (every 2 weeks on Saturday)
    current = date(2024, 1, 6)
    today = date(2026, 4, 21)
    event_dates = []
    while current <= today:
        event_dates.append(current)
        current += timedelta(weeks=2)

    for i, event_date in enumerate(event_dates):
        is_past = event_date < today
        is_league_week = (i % 4 == 0)  # every 4th event is a league game week

        if is_league_week:
            title = f"리그전 경기일 ({event_date.strftime('%Y-%m-%d')})"
            vote_type = models.AttendanceVoteTypeEnum.LEAGUE
        else:
            title = f"정기 훈련 ({event_date.strftime('%Y-%m-%d')})"
            vote_type = models.AttendanceVoteTypeEnum.REST

        status = (
            models.AttendanceEventStatusEnum.CLOSED
            if is_past
            else models.AttendanceEventStatusEnum.OPEN
        )

        event = models.AttendanceEvent(
            title=title,
            event_date=event_date,
            status=status,
            note=None,
            created_by=actor,
        )
        db.add(event)
        db.flush()

        # Attendance vote settings
        db.add(models.AttendanceEventSetting(
            event_id=event.id,
            vote_type=vote_type,
            updated_by=actor,
        ))

        # Generate votes for past events
        if is_past:
            for emp_id in all_player_ids:
                # ~80% attendance rate, some late
                roll = RNG.random()
                if roll < 0.75:
                    response = models.AttendanceResponseEnum.ATTEND
                elif roll < 0.87:
                    response = models.AttendanceResponseEnum.ABSENT
                else:
                    response = models.AttendanceResponseEnum.LATE

                vote_time = datetime.combine(event_date, datetime.min.time()) + timedelta(hours=RNG.randint(8, 23))
                db.add(models.AttendanceVote(
                    event_id=event.id,
                    emp_id=emp_id,
                    response=response,
                    voted_at=vote_time,
                ))
                votes_created += 1

        events_created += 1

    db.flush()
    print(f"  Created {events_created} attendance events, {votes_created} votes")


# ─────────────────────────────────────────────────────────────────────────────
# Fee payments
# ─────────────────────────────────────────────────────────────────────────────

def seed_fees(db, actor: str, all_player_ids: list[str]):
    payments_created = 0

    # 2024-01 through 2025-12 = 24 months
    months = []
    for year in [2024, 2025]:
        for month in range(1, 13):
            months.append(f"{year}-{month:02d}")

    for emp_id in all_player_ids:
        # Each player may miss 1-2 random months per year
        skip_months_2024 = set(RNG.sample([f"2024-{m:02d}" for m in range(1, 13)], k=RNG.randint(0, 2)))
        skip_months_2025 = set(RNG.sample([f"2025-{m:02d}" for m in range(1, 13)], k=RNG.randint(0, 2)))
        skip_months = skip_months_2024 | skip_months_2025

        for ym in months:
            if ym in skip_months:
                continue

            db.add(models.MembershipPayment(
                emp_id=emp_id,
                plan_type=models.FeePlanEnum.MONTHLY,
                year_month=ym,
                coverage_start_month=ym,
                coverage_end_month=ym,
                expected_amount=30000,
                paid_amount=30000,
                is_paid=True,
                note=None,
                marked_by=actor,
            ))
            payments_created += 1

    db.flush()
    print(f"  Created {payments_created} fee payment records")


# ─────────────────────────────────────────────────────────────────────────────
# Notices
# ─────────────────────────────────────────────────────────────────────────────

def seed_notices(db, actor: str):
    for n in NOTICES:
        notice = models.Notice(
            title=n["title"],
            body=n["body"],
            is_pinned=n.get("is_pinned", False),
            created_by=actor,
        )
        # Manually set created_at for realistic history
        notice.created_at = n["created_at"]
        notice.updated_at = n["created_at"]
        db.add(notice)

    db.flush()
    print(f"  Created {len(NOTICES)} notices")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    db = SessionLocal()
    try:
        # Find admin/master account
        actor = None
        for candidate in ("master", "admin"):
            u = db.query(models.User).filter(models.User.emp_id == candidate).first()
            if u:
                actor = u.emp_id
                break
        if not actor:
            raise RuntimeError("No master/admin account found. Create one first.")
        print(f"Using actor: {actor}")

        print("\n[1/6] Cleanup...")
        cleanup(db)

        print("\n[2/6] Players...")
        seed_players(db, actor)

        print("\n[3/6] Team assignments...")
        set_team_assignments(db, actor)

        print("\n[4/6] Seasons...")
        for sdef in SEASONS_DEF:
            seed_season(db, sdef, actor)

        print("\n[5/6] Attendance...")
        all_ids = list(ALL_PLAYERS.keys())
        seed_attendance(db, actor, all_ids)

        print("\n[6/6] Fees...")
        seed_fees(db, actor, all_ids)

        print("\n[+] Notices...")
        seed_notices(db, actor)

        db.commit()
        print("\nDone! Production data seeded successfully.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
