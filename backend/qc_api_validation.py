"""
QC: API 입력 검증
- 필수 필드 누락
- 잘못된 enum 값
- 타입 오류
- 범위 초과 값
- 중복 생성 방지
- 페이지네이션 경계
- 특수문자/긴 문자열
"""
import os
import urllib.request, urllib.error, urllib.parse, json, sys

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
        print(f"  [FAIL] {label} — expected {expected}, got {status} | {str(body)[:120]}")
        FAIL_COUNT += 1
        FAILURES.append(f"{label} (expected {expected}, got {status})")
        return False


def login(emp_id, password):
    s, b = req("POST", "/api/auth/login", form_data={"username": emp_id, "password": password})
    return b.get("access_token") if s == 200 else None


print("\n" + "=" * 60)
print("  QC: API 입력 검증")
print("=" * 60)

admin_token = login("master", "1234")
if not admin_token:
    print("[FATAL] Cannot login as master")
    sys.exit(1)

TEST_ID = "qc_val_test"

# 테스트 후 정리 함수
def cleanup():
    req("DELETE", f"/api/users/{TEST_ID}", token=admin_token)
    req("DELETE", f"/api/users/{TEST_ID}_2", token=admin_token)

cleanup()

# ─── 1. 사용자 생성 — 필수 필드 누락 ────────────────────────────────────────
print("\n[1] 사용자 생성 — 필수 필드 누락")
cases = [
    ({}, "모든 필드 누락"),
    ({"emp_id": TEST_ID}, "name 누락"),
    ({"name": "Test"}, "emp_id 누락"),
    ({"emp_id": TEST_ID, "name": "Test"}, "department 누락"),
]
for body, label in cases:
    s, b = req("POST", "/api/users", body, token=admin_token)
    ok(f"필수 필드 누락: {label} → 422", s, b, 422)

# ─── 2. 사용자 생성 — 잘못된 enum 값 ────────────────────────────────────────
print("\n[2] 잘못된 role enum 값")
s, b = req("POST", "/api/users", {
    "emp_id": TEST_ID, "name": "Test", "department": "QC",
    "email": f"{TEST_ID}@test.com", "role": "SUPERUSER"
}, token=admin_token)
ok("role=SUPERUSER → 400 또는 422", s, b, [400, 422])

s, b = req("POST", "/api/users", {
    "emp_id": TEST_ID, "name": "Test", "department": "QC",
    "email": f"{TEST_ID}@test.com", "role": "GENERAL"
}, token=admin_token)
ok("유효한 사용자 생성 → 201", s, b, [200, 201])

# ─── 3. 중복 emp_id 방지 ─────────────────────────────────────────────────────
print("\n[3] 중복 emp_id 방지")
s, b = req("POST", "/api/users", {
    "emp_id": TEST_ID, "name": "Test2", "department": "QC",
    "email": f"{TEST_ID}_2@test.com", "role": "GENERAL"
}, token=admin_token)
ok("중복 emp_id 방지 → 409", s, b, 409)

# ─── 4. 잘못된 status body ───────────────────────────────────────────────────
print("\n[4] 사용자 상태 변경 — 잘못된 입력")
s, b = req("PATCH", f"/api/users/{TEST_ID}/status", {}, token=admin_token)
ok("빈 body로 상태 변경 → 422", s, b, 422)

s, b = req("PATCH", f"/api/users/{TEST_ID}/status", {"is_resigned": "yes"}, token=admin_token)
ok("is_resigned='yes'(문자열) → 422 또는 200(lax 허용)", s, b, [200, 422])

# ─── 5. 존재하지 않는 사용자 조회 ───────────────────────────────────────────
print("\n[5] 존재하지 않는 리소스 조회")
s, b = req("GET", "/api/users/nonexistent_user_xyz", token=admin_token)
ok("없는 사용자 조회 → 404", s, b, 404)

s, b = req("GET", "/api/attendance/events/99999999", token=admin_token)
ok("없는 출석 이벤트 조회 → 404", s, b, 404)

# ─── 6. 페이지네이션 경계 ────────────────────────────────────────────────────
print("\n[6] 페이지네이션 경계값")
s, b = req("GET", "/api/users?skip=0&limit=1", token=admin_token)
ok("skip=0, limit=1 → 200", s, b, 200)

s, b = req("GET", "/api/users?skip=99999&limit=10", token=admin_token)
ok("skip=99999 (결과 없음) → 200", s, b, 200)
if s == 200:
    ok("빈 items 배열 반환", b.get("items", None) is not None, True, True)

s, b = req("GET", "/api/users?skip=-1&limit=10", token=admin_token)
ok("skip=-1 → 422 또는 200", s, b, [200, 422])

s, b = req("GET", "/api/users?limit=0", token=admin_token)
ok("limit=0 → 422 또는 200", s, b, [200, 422])

# ─── 7. 출석 이벤트 생성 — 입력 검증 ───────────────────────────────────────
print("\n[7] 출석 이벤트 생성 — 입력 검증")
s, b = req("POST", "/api/attendance/events", {
    "title": "", "event_date": "2026-01-01", "vote_type": "REST"
}, token=admin_token)
ok("빈 제목 → 422 또는 400", s, b, [400, 422])

s, b = req("POST", "/api/attendance/events", {
    "title": "테스트 이벤트", "event_date": "not-a-date", "vote_type": "REST"
}, token=admin_token)
ok("잘못된 날짜 형식 → 422", s, b, [400, 422])

s, b = req("POST", "/api/attendance/events", {
    "title": "테스트 이벤트", "event_date": "2026-06-01", "vote_type": "INVALID_TYPE"
}, token=admin_token)
ok("잘못된 vote_type → 422", s, b, [400, 422])

# ─── 8. 회비 프로필 — 잘못된 입력 ───────────────────────────────────────────
print("\n[8] 회비 프로필 — 잘못된 입력")
s, b = req("PATCH", f"/api/fees/admin/members/{TEST_ID}/profile",
           {"membership_type": "INVALID_TYPE"}, token=admin_token)
ok("잘못된 membership_type → 422", s, b, [400, 422])

s, b = req("PATCH", f"/api/fees/admin/members/{TEST_ID}/profile",
           {"member_status": "INVALID_STATUS"}, token=admin_token)
ok("잘못된 member_status → 422", s, b, [400, 422])

# ─── 9. 특수문자/긴 문자열 ──────────────────────────────────────────────────
print("\n[9] 특수문자 및 긴 문자열")
long_name = "A" * 300
s, b = req("POST", "/api/users", {
    "emp_id": f"{TEST_ID}_2", "name": long_name, "department": "QC",
    "email": f"{TEST_ID}_2@test.com", "role": "GENERAL"
}, token=admin_token)
ok("300자 이름 → 422 또는 201/200(허용)", s, b, [200, 201, 400, 422])
if s in (200, 201):
    req("DELETE", f"/api/users/{TEST_ID}_2", token=admin_token)

s, b = req("POST", "/api/notices", {
    "title": "A' OR '1'='1",
    "body": "<script>alert(1)</script>",
    "is_pinned": False
}, token=admin_token)
ok("SQL인젝션/XSS 입력 → 저장되지 않거나 201/200(이스케이프됨)", s, b, [200, 201, 400, 422])
if s in (200, 201):
    notice_id = b.get("id")
    if notice_id:
        s2, b2 = req("GET", "/api/notices", token=admin_token)
        if s2 == 200:
            items = b2.get("items", [])
            bad = next((n for n in items if n.get("id") == notice_id), None)
            if bad:
                title = bad.get("title", "")
                ok("저장된 제목에 스크립트 태그 없음", "<script>" not in title.lower(), True, True)
                req("DELETE", f"/api/notices/{notice_id}", token=admin_token)

# ─── 10. 로그인 빈 자격증명 ─────────────────────────────────────────────────
print("\n[10] 로그인 — 빈/잘못된 자격증명")
s, b = req("POST", "/api/auth/login", form_data={"username": "", "password": ""})
ok("빈 자격증명 → 401 또는 422", s, b, [401, 422])

s, b = req("POST", "/api/auth/login", form_data={"username": "master", "password": ""})
ok("빈 비밀번호 → 401 또는 422", s, b, [401, 422])

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
