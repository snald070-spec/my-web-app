from sqlalchemy import Column, String, Boolean, DateTime, Enum, Text, Date, Integer, UniqueConstraint
from sqlalchemy.sql import func
from database import Base
import enum


class RoleEnum(str, enum.Enum):
    MASTER   = "MASTER"
    ADMIN    = "ADMIN"
    GENERAL  = "GENERAL"
    STUDENT  = "STUDENT"

    # Legacy values kept temporarily for existing SQLite rows.
    USER     = "USER"
    APPROVER = "APPROVER"
    PARTNER  = "PARTNER"


MEMBER_ROLE_VALUES = (
    RoleEnum.GENERAL,
    RoleEnum.STUDENT,
    RoleEnum.USER,
)


ADMIN_ROLE_VALUES = (
    RoleEnum.MASTER,
    RoleEnum.ADMIN,
)


def canonical_role(role: RoleEnum | str | None) -> RoleEnum:
    if role in (RoleEnum.MASTER, RoleEnum.ADMIN, RoleEnum.GENERAL, RoleEnum.STUDENT):
        return role
    if role == RoleEnum.USER:
        return RoleEnum.GENERAL
    if role in (RoleEnum.APPROVER, RoleEnum.PARTNER):
        return RoleEnum.GENERAL
    return RoleEnum.GENERAL


class MembershipTypeEnum(str, enum.Enum):
    GENERAL = "GENERAL"
    STUDENT = "STUDENT"


class MemberStatusEnum(str, enum.Enum):
    NORMAL = "NORMAL"
    INJURED = "INJURED"
    DORMANT = "DORMANT"


class FeePlanEnum(str, enum.Enum):
    MONTHLY = "MONTHLY"
    SEMI_ANNUAL = "SEMI_ANNUAL"
    ANNUAL = "ANNUAL"


class User(Base):
    __tablename__ = "users"

    emp_id     = Column(String(50), primary_key=True, comment="Employee ID / username")
    name       = Column(String(50),  nullable=False)
    division   = Column(String(100), nullable=True,  comment="Business unit / division")
    department = Column(String(100), nullable=False, comment="Team / department")
    email      = Column(String(100), nullable=True)
    hashed_password = Column(String(256), nullable=False)

    role = Column(Enum(RoleEnum), default=RoleEnum.GENERAL, nullable=False)

    # First-login forced password change
    is_first_login = Column(Boolean, default=True)
    temp_password  = Column(String(20), nullable=True, comment="Plaintext temp pw (cleared after first login)")

    # Account state
    is_resigned  = Column(Boolean, default=False, nullable=True)
    resigned_date = Column(Date,   nullable=True)

    # Profile info
    birth_year = Column(Integer, nullable=True, comment="출생연도 (나이 계산용)")
    position   = Column(String(20), nullable=True, comment="농구 포지션 (PG/SG/SF/PF/C 등)")
    avatar_url = Column(String(300), nullable=True, comment="프로필 사진 경로")

    # Profile completion (Google 신규가입 후 추가 입력)
    birthday           = Column(String(5),   nullable=True, comment="생일 MM-DD")
    is_profile_complete = Column(Boolean, default=True, nullable=True, comment="False = Google 신규가입 후 프로필 미완성")

    # Social login
    google_id = Column(String(200), nullable=True, unique=True, comment="Google OAuth sub (unique ID)")

    # Global reader / VIP flag — DB-managed instead of hard-coded names
    is_vip = Column(Boolean, default=False, nullable=False)

    # Per-module permission overrides (JSON string: {"module_a":"writer","module_b":"none"})
    permissions = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class UserAuditLog(Base):
    __tablename__ = "user_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_emp_id = Column(String(50), nullable=False, comment="Admin who performed action")
    target_emp_id = Column(String(50), nullable=False, comment="User account affected")
    action = Column(String(50), nullable=False, comment="Action key: create/update/status/temp-password")
    details = Column(Text, nullable=True, comment="JSON string details")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class Notice(Base):
    __tablename__ = "notices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)
    created_by = Column(String(50), nullable=False)
    updated_by = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class MemberProfile(Base):
    __tablename__ = "member_profiles"

    emp_id = Column(String(50), primary_key=True)
    membership_type = Column(Enum(MembershipTypeEnum), default=MembershipTypeEnum.GENERAL, nullable=False)
    member_status = Column(Enum(MemberStatusEnum), default=MemberStatusEnum.NORMAL, nullable=False)
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class MembershipPayment(Base):
    __tablename__ = "membership_payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    emp_id = Column(String(50), nullable=False, index=True)
    plan_type = Column(Enum(FeePlanEnum), nullable=False, default=FeePlanEnum.MONTHLY)
    year_month = Column(String(7), nullable=False, index=True, comment="YYYY-MM 기준 월")
    coverage_start_month = Column(String(7), nullable=False)
    coverage_end_month = Column(String(7), nullable=False)
    expected_amount = Column(Integer, nullable=False)
    paid_amount = Column(Integer, nullable=False)
    is_paid = Column(Boolean, default=True, nullable=False)
    note = Column(Text, nullable=True)
    marked_by = Column(String(50), nullable=False)
    marked_at = Column(DateTime, server_default=func.now(), nullable=False)


class FeeReminderLog(Base):
    __tablename__ = "fee_reminder_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    year_month = Column(String(7), nullable=False, index=True)
    period = Column(String(20), nullable=False, comment="MONTH_END or MONTH_START")
    target_count = Column(Integer, nullable=False, default=0)
    sent_by = Column(String(50), nullable=False)
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class BankDepositEvent(Base):
    __tablename__ = "bank_deposit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_key = Column(String(64), nullable=False, unique=True, index=True)
    source = Column(String(40), nullable=False, default="KAKAOBANK_ALERT")
    depositor_name = Column(String(50), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    occurred_at = Column(DateTime, nullable=True)
    year_month = Column(String(7), nullable=False, index=True)
    match_status = Column(String(30), nullable=False, default="RECEIVED")
    matched_emp_id = Column(String(50), nullable=True, index=True)
    months_covered = Column(Integer, nullable=False, default=0)
    linked_payment_id = Column(Integer, nullable=True, index=True)
    raw_text = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class AttendanceResponseEnum(str, enum.Enum):
    ATTEND = "ATTEND"
    ABSENT = "ABSENT"
    LATE = "LATE"


class AttendanceEventStatusEnum(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class AttendanceVoteTypeEnum(str, enum.Enum):
    LEAGUE = "LEAGUE"
    REST = "REST"


class LeagueTeamEnum(str, enum.Enum):
    A = "A"
    B = "B"
    C = "C"


class LeagueSeasonStatusEnum(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    FINISHED = "FINISHED"
    ARCHIVED = "ARCHIVED"


class LeagueWeekStatusEnum(str, enum.Enum):
    OPEN = "OPEN"
    LOCKED = "LOCKED"


class LeagueMatchStatusEnum(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    FINAL = "FINAL"
    FORFEIT = "FORFEIT"
    CANCELED = "CANCELED"


class LeagueResultTypeEnum(str, enum.Enum):
    WIN = "WIN"
    DRAW = "DRAW"
    FORFEIT = "FORFEIT"


class LeagueDraftStatusEnum(str, enum.Enum):
    PLANNED = "PLANNED"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class LeagueTradeStatusEnum(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"
    EXECUTED = "EXECUTED"


class LeagueTradeWindowStatusEnum(str, enum.Enum):
    PLANNED = "PLANNED"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class AttendanceEvent(Base):
    __tablename__ = "attendance_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(120), nullable=False)
    event_date = Column(Date, nullable=False, index=True)
    status = Column(Enum(AttendanceEventStatusEnum), nullable=False, default=AttendanceEventStatusEnum.OPEN)
    note = Column(Text, nullable=True)
    created_by = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class AttendanceVote(Base):
    __tablename__ = "attendance_votes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, nullable=False, index=True)
    emp_id = Column(String(50), nullable=False, index=True)
    response = Column(Enum(AttendanceResponseEnum), nullable=False)
    voted_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class LeagueTeamAssignment(Base):
    __tablename__ = "league_team_assignments"

    emp_id = Column(String(50), primary_key=True)
    team_code = Column(Enum(LeagueTeamEnum), nullable=True)
    is_captain = Column(Boolean, nullable=False, default=False)
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class LeagueSeason(Base):
    __tablename__ = "league_seasons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(30), nullable=False, unique=True, index=True, comment="Season code like 2026-S1")
    title = Column(String(100), nullable=False, comment="Display title for admin/member UI")
    status = Column(Enum(LeagueSeasonStatusEnum), nullable=False, default=LeagueSeasonStatusEnum.DRAFT)
    total_weeks = Column(Integer, nullable=False, default=8, comment="Rulebook default is 8")
    points_win = Column(Integer, nullable=False, default=3)
    points_draw = Column(Integer, nullable=False, default=2)
    points_loss = Column(Integer, nullable=False, default=1)
    points_forfeit_loss = Column(Integer, nullable=False, default=0)
    forfeit_goal_diff_penalty = Column(Integer, nullable=False, default=-10)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    note = Column(Text, nullable=True)
    created_by = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class LeagueWeek(Base):
    __tablename__ = "league_weeks"
    __table_args__ = (
        UniqueConstraint("season_id", "week_no", name="uq_league_week_season_week"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, nullable=False, index=True)
    week_no = Column(Integer, nullable=False, comment="1..8")
    week_date = Column(Date, nullable=True, comment="Usually Monday game date")
    status = Column(Enum(LeagueWeekStatusEnum), nullable=False, default=LeagueWeekStatusEnum.OPEN)
    is_break_week = Column(Boolean, nullable=False, default=False, comment="Optional break week by schedule")
    is_trade_week = Column(Boolean, nullable=False, default=False, comment="Rulebook week 3 trade window")
    note = Column(Text, nullable=True)
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class LeagueMatch(Base):
    __tablename__ = "league_matches"
    __table_args__ = (
        UniqueConstraint("season_id", "week_no", "match_order", name="uq_league_match_slot"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, nullable=False, index=True)
    week_no = Column(Integer, nullable=False, index=True)
    match_order = Column(Integer, nullable=False, comment="1..3 for weekly round-robin order")
    home_team = Column(Enum(LeagueTeamEnum), nullable=False)
    away_team = Column(Enum(LeagueTeamEnum), nullable=False)
    status = Column(Enum(LeagueMatchStatusEnum), nullable=False, default=LeagueMatchStatusEnum.SCHEDULED)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    result_type = Column(Enum(LeagueResultTypeEnum), nullable=True)
    winner_team = Column(Enum(LeagueTeamEnum), nullable=True)
    forfeited_team = Column(Enum(LeagueTeamEnum), nullable=True)
    score_sheet_url = Column(String(300), nullable=True)
    note = Column(Text, nullable=True)
    confirmed_by = Column(String(50), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class LeagueStandingSnapshot(Base):
    __tablename__ = "league_standing_snapshots"
    __table_args__ = (
        UniqueConstraint("season_id", "week_no", "team_code", name="uq_league_standing_snapshot"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, nullable=False, index=True)
    week_no = Column(Integer, nullable=False, index=True)
    team_code = Column(Enum(LeagueTeamEnum), nullable=False, index=True)
    rank = Column(Integer, nullable=True)
    played = Column(Integer, nullable=False, default=0)
    wins = Column(Integer, nullable=False, default=0)
    draws = Column(Integer, nullable=False, default=0)
    losses = Column(Integer, nullable=False, default=0)
    forfeits = Column(Integer, nullable=False, default=0)
    points = Column(Integer, nullable=False, default=0)
    goals_for = Column(Integer, nullable=False, default=0)
    goals_against = Column(Integer, nullable=False, default=0)
    goal_diff = Column(Integer, nullable=False, default=0)
    head_to_head_json = Column(Text, nullable=True, comment="JSON tie-break helper by opponent")
    calculated_at = Column(DateTime, server_default=func.now(), nullable=False)
    calculated_by = Column(String(50), nullable=True)


class LeagueDraft(Base):
    __tablename__ = "league_drafts"
    __table_args__ = (
        UniqueConstraint("season_id", "name", name="uq_league_draft_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, nullable=False, index=True)
    name = Column(String(60), nullable=False, default="MAIN")
    status = Column(Enum(LeagueDraftStatusEnum), nullable=False, default=LeagueDraftStatusEnum.PLANNED)
    total_rounds = Column(Integer, nullable=False, default=1)
    started_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class LeagueDraftPick(Base):
    __tablename__ = "league_draft_picks"
    __table_args__ = (
        UniqueConstraint("draft_id", "round_no", "pick_no", name="uq_league_draft_pick_order"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    draft_id = Column(Integer, nullable=False, index=True)
    season_id = Column(Integer, nullable=False, index=True)
    round_no = Column(Integer, nullable=False)
    pick_no = Column(Integer, nullable=False)
    team_code = Column(Enum(LeagueTeamEnum), nullable=False)
    selected_emp_id = Column(String(50), nullable=True, index=True)
    selected_name = Column(String(50), nullable=True)
    is_skipped = Column(Boolean, nullable=False, default=False)
    picked_by = Column(String(50), nullable=True)
    picked_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)


class LeagueDraftParticipant(Base):
    __tablename__ = "league_draft_participants"
    __table_args__ = (
        UniqueConstraint("season_id", "emp_id", name="uq_league_draft_participant"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, nullable=False, index=True)
    emp_id = Column(String(50), nullable=False, index=True)
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class LeagueTradeWindow(Base):
    __tablename__ = "league_trade_windows"
    __table_args__ = (
        UniqueConstraint("season_id", "week_no", name="uq_league_trade_window_week"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, nullable=False, index=True)
    week_no = Column(Integer, nullable=False, default=3)
    status = Column(Enum(LeagueTradeWindowStatusEnum), nullable=False, default=LeagueTradeWindowStatusEnum.PLANNED)
    eligible_team = Column(Enum(LeagueTeamEnum), nullable=True, comment="Lowest team after week 3")
    points_gap_limit = Column(Integer, nullable=False, default=5)
    gap_with_leader = Column(Integer, nullable=True)
    trade_allowed = Column(Boolean, nullable=False, default=True)
    waived = Column(Boolean, nullable=False, default=False, comment="When eligible team waives rights")
    opened_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class LeagueTradeProposal(Base):
    __tablename__ = "league_trade_proposals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, nullable=False, index=True)
    trade_window_id = Column(Integer, nullable=False, index=True)
    proposer_team = Column(Enum(LeagueTeamEnum), nullable=False)
    partner_team = Column(Enum(LeagueTeamEnum), nullable=False)
    proposer_out_emp_id = Column(String(50), nullable=False, index=True)
    partner_out_emp_id = Column(String(50), nullable=False, index=True)
    proposer_protected = Column(Boolean, nullable=False, default=False)
    partner_protected = Column(Boolean, nullable=False, default=False)
    status = Column(Enum(LeagueTradeStatusEnum), nullable=False, default=LeagueTradeStatusEnum.DRAFT)
    requested_by = Column(String(50), nullable=False)
    approved_by = Column(String(50), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class LeagueTradeProtectedPlayer(Base):
    __tablename__ = "league_trade_protected_players"
    __table_args__ = (
        UniqueConstraint("season_id", "week_no", "team_code", "emp_id", name="uq_league_trade_protected_player"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, nullable=False, index=True)
    week_no = Column(Integer, nullable=False, default=3, index=True)
    team_code = Column(Enum(LeagueTeamEnum), nullable=False, index=True)
    emp_id = Column(String(50), nullable=False, index=True)
    marked_by = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class LeaguePlayerStat(Base):
    __tablename__ = "league_player_stats"
    __table_args__ = (
        UniqueConstraint("match_id", "emp_id", name="uq_league_player_stat"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, nullable=False, index=True)
    match_id = Column(Integer, nullable=False, index=True)
    week_no = Column(Integer, nullable=False, index=True)
    team_code = Column(Enum(LeagueTeamEnum), nullable=False, index=True)
    emp_id = Column(String(50), nullable=False, index=True)
    name = Column(String(50), nullable=True)
    participated = Column(Boolean, nullable=False, default=True)
    fg2_made = Column(Integer, nullable=False, default=0)
    fg2_attempted = Column(Integer, nullable=False, default=0)
    fg3_made = Column(Integer, nullable=False, default=0)
    fg3_attempted = Column(Integer, nullable=False, default=0)
    ft_made = Column(Integer, nullable=False, default=0)
    ft_attempted = Column(Integer, nullable=False, default=0)
    o_rebound = Column(Integer, nullable=False, default=0)
    d_rebound = Column(Integer, nullable=False, default=0)
    assist = Column(Integer, nullable=False, default=0)
    steal = Column(Integer, nullable=False, default=0)
    block = Column(Integer, nullable=False, default=0)
    foul = Column(Integer, nullable=False, default=0)
    turnover = Column(Integer, nullable=False, default=0)
    entered_by = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class AttendanceEventSetting(Base):
    __tablename__ = "attendance_event_settings"

    event_id = Column(Integer, primary_key=True)
    vote_type = Column(Enum(AttendanceVoteTypeEnum), nullable=False, default=AttendanceVoteTypeEnum.REST)
    target_team = Column(Enum(LeagueTeamEnum), nullable=True)
    vote_start_at = Column(DateTime, nullable=True)
    vote_end_at = Column(DateTime, nullable=True)
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class AttendanceReminderStageEnum(str, enum.Enum):
    DAY_BEFORE = "DAY_BEFORE"
    HOUR_BEFORE = "HOUR_BEFORE"


class AttendanceReminderLog(Base):
    __tablename__ = "attendance_reminder_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, nullable=False, index=True)
    stage = Column(Enum(AttendanceReminderStageEnum), nullable=False)
    emp_id = Column(String(50), nullable=False, index=True)
    sent_by = Column(String(50), nullable=False)
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
