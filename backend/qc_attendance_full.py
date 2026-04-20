"""
QC: 출석 관리 전체 플로우
- 이벤트 생성 / 수정 / 상태 전환
- 투표 창 (vote window) 적용
- 멤버 투표 (ATTEND / ABSENT / LATE)
- 투표 수정 가능 여부
- 통계 및 집계 검증
- REST vs LEAGUE 투표 타입
- 관리자 이벤트 상세 vs 멤버 이벤트 상세 차이
"""
import os
import urllib.request, urllib.error, urllib.parse, json, sys
from datetime import datetime, timedelta, date

BASE_URL = os.environ.get("QC_BASE_URL", "http://127.0.0.1:8000")
PASS_COUNT = 0
FAIL_COUNT = 0
FAILURES = []


def req(method, path, body=None, token=None, form_data=None):
    url = BASE_URL + path
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form_data:
        data = urllib.parse.urlencode(form_data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
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


def ok(label, status, body, expected=200):
    global PASS_COUNT, FAIL_COUNT
    if isinstance(expected, (list, tuple)):
        passed = status in expected
    else:
        passed = status == expected
    if passed:
        print(f"  [OK]  {label}")
        PASS_COUNT += 1
        return True
    else:
        print(f"  [FAIL] {label} — expected {expected}, got {status} | {str(body)[:150]}")
        FAIL_COUNT += 1
        FAILURES.append(f"{label} (expected {expected}, got {status})")
        return False


def login(emp_id, password):
    s, b = req("POST", "/api/auth/login", form_data={"username": emp_id, "password": password})
    return b.get("access_token") if s == 200 else None


def today_str():
    return date.today().isoformat()


def future_dt(days=1, hours=0):
    dt = datetime.utcnow() + timedelta(days=days, hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def past_dt(days=1):
    dt = datetime.utcnow() - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


print("\n" + "=" * 60)
print("  QC: 출석 관리 전체 플로우")
print("=" * 60)

admin_token = login("master", "1234")
if not admin_token:
    print("[FATAL] Cannot login as master")
    sys.exit(1)

MEMBER_ID = "qc_att_member"

def cleanup_member():
    req("DELETE", f"/api/users/{MEMBER_ID}", token=admin_token)

cleanup_member()

# 멤버 계정 생성
s, b = req("POST", "/api/users", {
    "emp_id": MEMBER_ID, "name": "Attendance Member", "department": "QC",
    "email": f"{MEMBER_ID}@qc.test", "role": "GENERAL"
}, token=admin_token)
ok("멤버 계정 생성", s, b, [200, 201])
member_temp_pw = b.get("temp_password") if s in (200, 201) else None
member_token = login(MEMBER_ID, member_temp_pw) if member_temp_pw else None

# ─── 1. 출석 이벤트 생성 ─────────────────────────────────────────────────────
print("\n[1] 출석 이벤트 생성")
event_date = (date.today() + timedelta(days=7)).isoformat()
s, b = req("POST", "/api/attendance/events", {
    "title": "QC 테스트 이벤트 REST",
    "event_date": event_date,
    "vote_type": "REST",
    "vote_open_at": past_dt(days=1),
    "vote_close_at": future_dt(days=6),
}, token=admin_token)
ok("REST 이벤트 생성 → 201 또는 200", s, b, [200, 201])
event_id = b.get("id") or b.get("event_id")

# ─── 2. 이벤트 목록 조회 ─────────────────────────────────────────────────────
print("\n[2] 이벤트 목록 조회")
s, b = req("GET", "/api/attendance/events", token=admin_token)
ok("관리자 이벤트 목록 조회", s, b, 200)

if member_token:
    s, b = req("GET", "/api/attendance/events", token=member_token)
    ok("멤버 이벤트 목록 조회", s, b, 200)

# ─── 3. 멤버 투표 ────────────────────────────────────────────────────────────
print("\n[3] 멤버 투표")
if event_id and member_token:
    s, b = req("POST", f"/api/attendance/events/{event_id}/vote",
               {"response": "ATTEND"}, token=member_token)
    ok("ATTEND 투표 → 200 또는 201", s, b, [200, 201])

    # 투표 수정 (ABSENT로 변경)
    s, b = req("POST", f"/api/attendance/events/{event_id}/vote",
               {"response": "ABSENT"}, token=member_token)
    ok("투표 수정 (ABSENT) → 200 또는 201", s, b, [200, 201])

    # 잘못된 투표값
    s, b = req("POST", f"/api/attendance/events/{event_id}/vote",
               {"response": "INVALID"}, token=member_token)
    ok("잘못된 투표값 → 422", s, b, [400, 422])

    # 다시 ATTEND로
    s, b = req("POST", f"/api/attendance/events/{event_id}/vote",
               {"response": "ATTEND"}, token=member_token)
    ok("투표 재변경 (ATTEND) → 200 또는 201", s, b, [200, 201])

# ─── 4. 관리자 이벤트 상세 vs 멤버 상세 ─────────────────────────────────────
print("\n[4] 이벤트 상세 권한 분리")
if event_id:
    s, b = req("GET", f"/api/attendance/admin/events/{event_id}/vote-detail", token=admin_token)
    ok("관리자 투표 상세 조회", s, b, 200)

    if member_token:
        s, b = req("GET", f"/api/attendance/events/{event_id}/vote-detail", token=member_token)
        ok("멤버 투표 상세 조회", s, b, 200)

        s, b = req("GET", f"/api/attendance/admin/events/{event_id}/vote-detail", token=member_token)
        ok("멤버가 관리자 상세 접근 차단 → 403", s, b, 403)

# ─── 5. 통계 검증 ────────────────────────────────────────────────────────────
print("\n[5] 출석 통계 검증")
if event_id:
    s, b = req("GET", f"/api/attendance/admin/events/{event_id}/vote-detail", token=admin_token)
    if s == 200:
        attend_count = b.get("event", {}).get("counts", {}).get("ATTEND", None)
        ok("출석 통계에 attend_count 존재", attend_count is not None, True, True)

s, b = req("GET", "/api/attendance/admin/member-summary", token=admin_token)
ok("관리자 멤버 출석 요약", s, b, 200)

if member_token:
    s, b = req("GET", "/api/attendance/me/summary", token=member_token)
    ok("멤버 본인 출석 요약", s, b, 200)

# ─── 6. 이벤트 상태 전환 ─────────────────────────────────────────────────────
print("\n[6] 이벤트 상태 전환 (OPEN → CLOSED)")
if event_id:
    s, b = req("PATCH", f"/api/attendance/events/{event_id}/status",
               {"status": "CLOSED"}, token=admin_token)
    ok("이벤트 CLOSED로 변경", s, b, 200)

    # 닫힌 이벤트에 투표 시도
    if member_token:
        s, b = req("POST", f"/api/attendance/events/{event_id}/vote",
                   {"response": "ATTEND"}, token=member_token)
        ok("닫힌 이벤트 투표 차단 → 400 또는 403", s, b, [400, 403, 409])

# ─── 7. LEAGUE 타입 이벤트 ───────────────────────────────────────────────────
print("\n[7] LEAGUE 타입 이벤트")
s, b = req("POST", "/api/attendance/events", {
    "title": "QC 테스트 이벤트 LEAGUE",
    "event_date": (date.today() + timedelta(days=14)).isoformat(),
    "vote_type": "LEAGUE",
    "target_team": "A",
    "vote_open_at": past_dt(days=1),
    "vote_close_at": future_dt(days=13),
}, token=admin_token)
ok("LEAGUE 이벤트 생성", s, b, [200, 201])
league_event_id = b.get("id") or b.get("event_id")

if league_event_id and member_token:
    s, b = req("POST", f"/api/attendance/events/{league_event_id}/vote",
               {"response": "ATTEND"}, token=member_token)
    ok("LEAGUE 이벤트 투표", s, b, [200, 201, 400, 403])  # 팀 미배정 멤버는 403

# ─── 8. 리마인더 관련 ────────────────────────────────────────────────────────
print("\n[8] 리마인더 조회")
s, b = req("GET", "/api/attendance/admin/reminders/pending", token=admin_token)
ok("대기 중인 리마인더 조회", s, b, 200)

if member_token:
    s, b = req("GET", "/api/attendance/admin/reminders/pending", token=member_token)
    ok("멤버가 리마인더 조회 차단 → 403", s, b, 403)

# ─── 정리 ────────────────────────────────────────────────────────────────────
cleanup_member()

print(f"\n{'=' * 60}")
print(f"  결과: {PASS_COUNT}/{PASS_COUNT + FAIL_COUNT} passed")
if FAILURES:
    print("\n  실패 목록:")
    for f in FAILURES:
        print(f"    ✗ {f}")
print("=" * 60)
sys.exit(0 if FAIL_COUNT == 0 else 1)
