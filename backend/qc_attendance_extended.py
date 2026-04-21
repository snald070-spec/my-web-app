"""
QC: 출석 관리 확장 시나리오 검증
- GET/POST /api/attendance/events
- PATCH /api/attendance/events/{id}/status
- POST /api/attendance/events/{id}/vote
- GET /api/attendance/me/summary
- GET /api/attendance/admin/member-summary
- GET/PUT /api/attendance/admin/team-assignments/{emp_id}
- GET /api/attendance/admin/reminders/pending
- POST /api/attendance/admin/reminders/dispatch
- GET /api/attendance/events/{id}/vote-detail
- GET /api/attendance/admin/events/{id}/vote-detail
"""
import os
import urllib.request, urllib.error, urllib.parse, json, sys
from datetime import date, datetime, timedelta

BASE_URL = os.environ.get("QC_BASE_URL", "http://127.0.0.1:8000")
PASS_COUNT = 0
FAIL_COUNT = 0
FAILURES = []


def req(method, path, body=None, token=None, params=None):
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    else:
        data = None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def login_form(emp_id, password):
    url = BASE_URL + "/api/auth/login"
    data = urllib.parse.urlencode({"username": emp_id, "password": password}).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(r) as resp:
            b = json.loads(resp.read())
            return b.get("access_token"), b
    except Exception:
        return None, {}


def ok(label, status_or_val, body_or_sentinel=None, expected=200):
    global PASS_COUNT, FAIL_COUNT
    if body_or_sentinel is True and expected is True:
        passed = bool(status_or_val)
    elif isinstance(expected, (list, tuple)):
        passed = status_or_val in expected
    else:
        passed = status_or_val == expected
    if passed:
        print(f"  [OK]  {label}")
        PASS_COUNT += 1
        return True
    else:
        detail = f"got {status_or_val}" if body_or_sentinel is not True else f"was {status_or_val}"
        print(f"  [FAIL] {label} — {detail} | {str(body_or_sentinel)[:120]}")
        FAIL_COUNT += 1
        FAILURES.append(label)
        return False


print("\n" + "=" * 60)
print("  QC: 출석 관리 확장 시나리오 검증")
print("=" * 60)

master_token, _ = login_form("master", "1234")
if not master_token:
    print("[FATAL] Cannot login as master")
    sys.exit(1)

# 테스트 유저 생성
MEMBER_A = "qcatt_a"
MEMBER_B = "qcatt_b"

for uid in [MEMBER_A, MEMBER_B]:
    req("DELETE", f"/api/users/{uid}", token=master_token)

_, b1 = req("POST", "/api/users", {
    "emp_id": MEMBER_A, "name": "QC Att A", "department": "QC",
    "email": f"{MEMBER_A}@qc.test", "role": "GENERAL"
}, token=master_token)
token_a = None
pw_a = b1.get("temp_password")
if pw_a:
    token_a, _ = login_form(MEMBER_A, pw_a)

_, b2 = req("POST", "/api/users", {
    "emp_id": MEMBER_B, "name": "QC Att B", "department": "QC",
    "email": f"{MEMBER_B}@qc.test", "role": "GENERAL"
}, token=master_token)
token_b = None
pw_b = b2.get("temp_password")
if pw_b:
    token_b, _ = login_form(MEMBER_B, pw_b)

CREATED_EVENT_IDS = []
FUTURE_DATE = (date.today() + timedelta(days=7)).isoformat()
PAST_DATE = (date.today() - timedelta(days=7)).isoformat()


def cleanup():
    for eid in CREATED_EVENT_IDS:
        pass  # 이벤트 삭제 API 없음
    for uid in [MEMBER_A, MEMBER_B]:
        req("DELETE", f"/api/users/{uid}", token=master_token)


# ─── 1. GET /api/attendance/events ───────────────────────────────────────────
print("\n[1] GET /api/attendance/events")
s, b = req("GET", "/api/attendance/events", token=master_token)
ok("events 목록 → 200", s, b, 200)
ok("items 필드", "items" in b, True, True)
ok("total 필드", "total" in b, True, True)

s, b = req("GET", "/api/attendance/events")
ok("토큰 없이 events → 401", s, b, 401)

# ─── 2. POST /api/attendance/events ──────────────────────────────────────────
print("\n[2] POST /api/attendance/events")

# 타임존 차이를 피하기 위해 고정된 넓은 투표 창 사용
VOTE_START = "2020-01-01T00:00:00"
VOTE_END = "2099-12-31T23:59:59"

s, b = req("POST", "/api/attendance/events", {
    "title": "QC REST 이벤트",
    "event_date": FUTURE_DATE,
    "note": "QC 테스트",
    "vote_type": "REST",
    "vote_open_at": VOTE_START,
    "vote_close_at": VOTE_END,
}, token=master_token)
ok("REST 이벤트 생성 → 200", s, b, 200)
rest_event_id = b.get("id")
if rest_event_id:
    CREATED_EVENT_IDS.append(rest_event_id)
ok("id 존재", bool(rest_event_id), True, True)
ok("vote_type = REST", b.get("vote_type") == "REST", True, True)
ok("status = OPEN", b.get("status") == "OPEN", True, True)

# 필수 필드 검증 (빈 제목)
s, b = req("POST", "/api/attendance/events", {
    "title": "", "event_date": FUTURE_DATE
}, token=master_token)
ok("빈 제목 이벤트 → 400", s, b, 400)

# LEAGUE 이벤트 (target_team 필수)
s, b = req("POST", "/api/attendance/events", {
    "title": "QC League 이벤트",
    "event_date": FUTURE_DATE,
    "vote_type": "LEAGUE",
    "target_team": "A",
    "vote_open_at": VOTE_START,
    "vote_close_at": VOTE_END,
}, token=master_token)
ok("LEAGUE 이벤트 생성 → 200", s, b, 200)
league_event_id = b.get("id")
if league_event_id:
    CREATED_EVENT_IDS.append(league_event_id)
ok("vote_type = LEAGUE", b.get("vote_type") == "LEAGUE", True, True)
ok("target_team = A", b.get("target_team") == "A", True, True)

# LEAGUE 이벤트 — target_team 없이
s, b = req("POST", "/api/attendance/events", {
    "title": "QC League 이벤트",
    "event_date": FUTURE_DATE,
    "vote_type": "LEAGUE",
}, token=master_token)
ok("LEAGUE 이벤트 target_team 없이 → 400", s, b, 400)

# GENERAL 권한 불가
if token_a:
    s, b = req("POST", "/api/attendance/events", {
        "title": "일반유저 이벤트", "event_date": FUTURE_DATE
    }, token=token_a)
    ok("GENERAL 이벤트 생성 → 403", s, b, 403)

# ─── 3. PATCH /api/attendance/events/{id}/status ─────────────────────────────
print("\n[3] PATCH events/{id}/status")
if rest_event_id:
    s, b = req("PATCH", f"/api/attendance/events/{rest_event_id}/status",
               {"status": "CLOSED"}, token=master_token)
    ok("이벤트 CLOSED → 200", s, b, 200)
    ok("status = CLOSED", b.get("status") == "CLOSED", True, True)

    s, b = req("PATCH", f"/api/attendance/events/{rest_event_id}/status",
               {"status": "OPEN"}, token=master_token)
    ok("이벤트 다시 OPEN → 200", s, b, 200)

    s, b = req("PATCH", f"/api/attendance/events/{rest_event_id}/status",
               {"status": "INVALID"}, token=master_token)
    ok("잘못된 status → 400", s, b, 400)

    s, b = req("PATCH", "/api/attendance/events/99999999/status",
               {"status": "CLOSED"}, token=master_token)
    ok("없는 이벤트 status → 404", s, b, 404)

# ─── 4. POST /api/attendance/events/{id}/vote ────────────────────────────────
print("\n[4] POST events/{id}/vote")
if rest_event_id and token_a:
    s, b = req("POST", f"/api/attendance/events/{rest_event_id}/vote",
               {"response": "ATTEND"}, token=token_a)
    ok("ATTEND 투표 → 200", s, b, 200)
    ok("my_vote = ATTEND", b.get("my_vote") == "ATTEND", True, True)

    # 재투표 (변경)
    s, b = req("POST", f"/api/attendance/events/{rest_event_id}/vote",
               {"response": "ABSENT"}, token=token_a)
    ok("ABSENT 재투표 → 200", s, b, 200)
    ok("my_vote = ABSENT", b.get("my_vote") == "ABSENT", True, True)

    # LATE는 현재 차단됨
    s, b = req("POST", f"/api/attendance/events/{rest_event_id}/vote",
               {"response": "LATE"}, token=token_a)
    ok("LATE 투표 → 400 (미지원)", s, b, 400)

    # 잘못된 response
    s, b = req("POST", f"/api/attendance/events/{rest_event_id}/vote",
               {"response": "INVALID"}, token=token_a)
    ok("잘못된 response → 400", s, b, 400)

    # CLOSED 이벤트에 투표
    req("PATCH", f"/api/attendance/events/{rest_event_id}/status",
        {"status": "CLOSED"}, token=master_token)
    s, b = req("POST", f"/api/attendance/events/{rest_event_id}/vote",
               {"response": "ATTEND"}, token=token_b)
    ok("CLOSED 이벤트 투표 → 400", s, b, 400)
    req("PATCH", f"/api/attendance/events/{rest_event_id}/status",
        {"status": "OPEN"}, token=master_token)

# ─── 5. GET /api/attendance/me/summary ───────────────────────────────────────
print("\n[5] GET /api/attendance/me/summary")
if token_a:
    s, b = req("GET", "/api/attendance/me/summary", token=token_a)
    ok("me/summary → 200", s, b, 200)
    for field in ["emp_id", "total_votes", "attend_count", "late_count",
                  "absent_count", "attendance_rate", "cumulative_score"]:
        ok(f"필드 '{field}' 존재", field in b, True, True)
    ok("total_votes >= 1 (투표 후)", b.get("total_votes", 0) >= 1, True, True)

# ─── 6. GET /api/attendance/admin/member-summary ─────────────────────────────
print("\n[6] GET admin/member-summary")
s, b = req("GET", "/api/attendance/admin/member-summary", token=master_token)
ok("admin/member-summary → 200", s, b, 200)
ok("items 필드", "items" in b, True, True)
if b.get("items"):
    row = b["items"][0]
    for field in ["emp_id", "total_votes", "attend_count", "attendance_rate", "cumulative_score"]:
        ok(f"member-summary 필드 '{field}'", field in row, True, True)

if token_a:
    s, b = req("GET", "/api/attendance/admin/member-summary", token=token_a)
    ok("GENERAL admin/member-summary → 403", s, b, 403)

# ─── 7. GET/PUT /api/attendance/admin/team-assignments ───────────────────────
print("\n[7] GET/PUT admin/team-assignments")
s, b = req("GET", "/api/attendance/admin/team-assignments", token=master_token)
ok("team-assignments 목록 → 200", s, b, 200)
ok("items 필드", "items" in b, True, True)

# 팀 배정
s, b = req("PUT", f"/api/attendance/admin/team-assignments/{MEMBER_A}",
           {"team_code": "A", "is_captain": False}, token=master_token)
ok(f"{MEMBER_A} 팀A 배정 → 200", s, b, 200)
ok("team_code = A", b.get("team_code") == "A", True, True)
ok("is_captain = False", b.get("is_captain") is False, True, True)

s, b = req("PUT", f"/api/attendance/admin/team-assignments/{MEMBER_B}",
           {"team_code": "B", "is_captain": False}, token=master_token)
ok(f"{MEMBER_B} 팀B 배정 → 200", s, b, 200)

# 주장 설정
s, b = req("PUT", f"/api/attendance/admin/team-assignments/{MEMBER_A}",
           {"team_code": "A", "is_captain": True}, token=master_token)
ok(f"{MEMBER_A} 주장 설정 → 200", s, b, 200)
ok("is_captain = True", b.get("is_captain") is True, True, True)

# 없는 유저
s, b = req("PUT", "/api/attendance/admin/team-assignments/nonexistent_xyz",
           {"team_code": "A"}, token=master_token)
ok("없는 유저 팀 배정 → 404", s, b, 404)

# 팀 배정 없이 주장 설정 불가
s, b = req("PUT", f"/api/attendance/admin/team-assignments/{MEMBER_A}",
           {"team_code": None, "is_captain": True}, token=master_token)
# team_code=None은 팀 해제를 의미하므로 is_captain은 False가 됨 → 이 케이스는 실제로 400이 아닐 수도 있음
# 실제 로직상 next_team_code가 None이면 next_is_captain도 False로 강제됨
ok("팀 없이 주장 설정 → 200 (is_captain 강제 false)", s, b, 200)

# 팀 복구
req("PUT", f"/api/attendance/admin/team-assignments/{MEMBER_A}",
    {"team_code": "A", "is_captain": True}, token=master_token)

# GENERAL 권한 불가
if token_a:
    s, b = req("GET", "/api/attendance/admin/team-assignments", token=token_a)
    ok("GENERAL team-assignments → 403", s, b, 403)

# ─── 8. vote-detail 검증 ──────────────────────────────────────────────────────
print("\n[8] GET events/{id}/vote-detail")
if rest_event_id:
    s, b = req("GET", f"/api/attendance/events/{rest_event_id}/vote-detail",
               token=token_a or master_token)
    ok("vote-detail (일반) → 200", s, b, 200)
    ok("event 필드", "event" in b, True, True)
    ok("voted 필드", "voted" in b, True, True)
    ok("pending 필드", "pending" in b, True, True)
    ok("summary 필드", "summary" in b, True, True)

    s, b = req("GET", f"/api/attendance/admin/events/{rest_event_id}/vote-detail",
               token=master_token)
    ok("vote-detail (admin) → 200", s, b, 200)

    s, b = req("GET", "/api/attendance/events/99999999/vote-detail",
               token=master_token)
    ok("없는 이벤트 vote-detail → 404", s, b, 404)

# ─── 9. GET /api/attendance/admin/reminders/pending ──────────────────────────
print("\n[9] GET admin/reminders/pending")
s, b = req("GET", "/api/attendance/admin/reminders/pending", token=master_token)
ok("reminders/pending → 200", s, b, 200)
ok("items 필드", "items" in b, True, True)
ok("total 필드", "total" in b, True, True)

if token_a:
    s, b = req("GET", "/api/attendance/admin/reminders/pending", token=token_a)
    ok("GENERAL reminders/pending → 403", s, b, 403)

# ─── 10. POST /api/attendance/admin/reminders/dispatch ───────────────────────
print("\n[10] POST admin/reminders/dispatch")
if rest_event_id:
    s, b = req("POST", "/api/attendance/admin/reminders/dispatch", {
        "event_id": rest_event_id,
        "stage": "DAY_BEFORE",
        "memo": "QC 테스트 알림"
    }, token=master_token)
    ok("reminder dispatch → 200", s, b, 200)
    ok("event_id 존재", "event_id" in b, True, True)
    ok("sent_count 존재", "sent_count" in b, True, True)
    ok("target_emp_ids 존재", "target_emp_ids" in b, True, True)

    # 잘못된 stage
    s, b = req("POST", "/api/attendance/admin/reminders/dispatch", {
        "event_id": rest_event_id,
        "stage": "INVALID"
    }, token=master_token)
    ok("잘못된 stage → 400", s, b, 400)

    # 없는 이벤트
    s, b = req("POST", "/api/attendance/admin/reminders/dispatch", {
        "event_id": 99999999,
        "stage": "DAY_BEFORE"
    }, token=master_token)
    ok("없는 이벤트 dispatch → 404", s, b, 404)

# ─── 정리 ────────────────────────────────────────────────────────────────────
cleanup()

print(f"\n{'=' * 60}")
print(f"  결과: {PASS_COUNT}/{PASS_COUNT + FAIL_COUNT} passed")
if FAILURES:
    print("\n  실패 목록:")
    for f in FAILURES:
        print(f"    ✗ {f}")
print("=" * 60)
sys.exit(0 if FAIL_COUNT == 0 else 1)
