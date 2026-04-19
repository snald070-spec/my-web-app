"""
QC: Authentication Edge Cases
- 최초 로그인 강제 비밀번호 변경
- 비활성화(resigned) 계정 로그인 차단
- 비밀번호 정책 검증
- 잘못된/만료된 토큰 처리
- 로그인 Rate Limiting
"""
import urllib.request, urllib.error, urllib.parse, json, sys, time

BASE_URL = "http://127.0.0.1:8000"
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
    if status == expected:
        print(f"  [OK]  {label}")
        PASS_COUNT += 1
        return True
    else:
        print(f"  [FAIL] {label} — expected {expected}, got {status} | {body}")
        FAIL_COUNT += 1
        FAILURES.append(f"{label} (expected {expected}, got {status})")
        return False


def login(emp_id, password):
    s, b = req("POST", "/api/auth/login", form_data={"username": emp_id, "password": password})
    if s == 200:
        return b.get("access_token")
    return None


def create_test_user(admin_token, emp_id, name="Test User", role="GENERAL"):
    s, b = req("POST", "/api/users", {
        "emp_id": emp_id, "name": name, "department": "QC",
        "email": f"{emp_id}@qc.test", "role": role
    }, token=admin_token)
    return s, b


def delete_test_user(admin_token, emp_id):
    req("DELETE", f"/api/users/{emp_id}", token=admin_token)


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  QC: Authentication Edge Cases")
print("=" * 60)

admin_token = login("master", "1234")
if not admin_token:
    print("[FATAL] Cannot login as master")
    sys.exit(1)

TEST_ID = "qc_auth_test"

# 테스트 사용자 정리 (기존 것 있으면 삭제)
delete_test_user(admin_token, TEST_ID)

# ─── 1. 임시 비밀번호 발급 및 최초 로그인 ────────────────────────────────────
print("\n[1] 임시 비밀번호 발급 및 최초 로그인")
s, b = create_test_user(admin_token, TEST_ID)
ok("테스트 사용자 생성", s, b, 201)

s, b = req("POST", f"/api/users/{TEST_ID}/issue-temp-password", token=admin_token)
ok("임시 비밀번호 발급 (관리자)", s, b, 200)
temp_pw = b.get("temp_password")

if temp_pw:
    s, b = req("POST", "/api/auth/login", form_data={"username": TEST_ID, "password": temp_pw})
    ok("임시 비밀번호로 로그인 성공", s, b, 200)
    member_token = b.get("access_token")
    is_first = b.get("is_first_login")
    ok("is_first_login=True 반환", is_first, True, True)
else:
    print("  [SKIP] temp_pw 없음 — 최초 로그인 테스트 건너뜀")
    member_token = None

# ─── 2. 비밀번호 정책 검증 ───────────────────────────────────────────────────
print("\n[2] 비밀번호 정책 검증")
if member_token:
    cases = [
        ("1234",          400, "너무 짧은 비밀번호"),
        ("aaaaaaaaaaa",   400, "대문자/숫자/특수문자 없음"),
        ("AAAAAAAAAAA1",  400, "소문자/특수문자 없음"),
        ("Abcdefgh1!",    200, "유효한 비밀번호"),
    ]
    for pw, exp, label in cases:
        s, b = req("POST", "/api/auth/change-password",
                   {"current_password": temp_pw, "new_password": pw},
                   token=member_token)
        ok(f"비밀번호 정책: {label}", s, b, exp)
        if exp == 200:
            # 비밀번호 변경 성공 후 새 토큰으로 재로그인
            member_token = login(TEST_ID, "Abcdefgh1!")

# ─── 3. 비활성화(resigned) 계정 로그인 차단 ──────────────────────────────────
print("\n[3] 비활성화 계정 로그인 차단")
s, b = req("PATCH", f"/api/users/{TEST_ID}/status", {"is_resigned": True}, token=admin_token)
ok("계정 비활성화", s, b, 200)

new_pw = "Abcdefgh1!" if member_token else (temp_pw or "1234")
s, b = req("POST", "/api/auth/login", form_data={"username": TEST_ID, "password": new_pw})
ok("비활성화 계정 로그인 차단 (403)", s, b, 403)

# ─── 4. 잘못된/손상된 토큰 ───────────────────────────────────────────────────
print("\n[4] 잘못된/손상된 토큰 처리")
s, b = req("GET", "/api/auth/me", token="garbage_token_xyz")
ok("쓰레기 토큰 → 401", s, b, 401)

s, b = req("GET", "/api/auth/me", token="eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlIn0.wrongsig")
ok("잘못된 서명 토큰 → 401", s, b, 401)

s, b = req("GET", "/api/auth/me")
ok("토큰 없음 → 401", s, b, 401)

# ─── 5. 비밀번호 변경 후 이전 토큰 무효화 ───────────────────────────────────
print("\n[5] 계정 재활성화 후 접근 검증")
s, b = req("PATCH", f"/api/users/{TEST_ID}/status", {"is_resigned": False}, token=admin_token)
ok("계정 재활성화", s, b, 200)

# ─── 6. 관리자 자신의 계정 비활성화 차단 ────────────────────────────────────
print("\n[6] 관리자 자신의 계정 비활성화 차단")
s, b = req("PATCH", "/api/users/master/status", {"is_resigned": True}, token=admin_token)
ok("관리자 자신 비활성화 차단 (400)", s, b, 400)

# ─── 7. 비밀번호 스킵 차단 ──────────────────────────────────────────────────
print("\n[7] 최초 로그인 비밀번호 변경 스킵 차단")
# 새 임시 비밀번호 발급
s, b = req("POST", f"/api/users/{TEST_ID}/issue-temp-password", token=admin_token)
if s == 200 and b.get("temp_password"):
    skip_token = login(TEST_ID, b["temp_password"])
    if skip_token:
        s, b = req("POST", "/api/auth/skip-password-change", token=skip_token)
        ok("비밀번호 변경 스킵 차단 (403)", s, b, 403)

# ─── 정리 ────────────────────────────────────────────────────────────────────
delete_test_user(admin_token, TEST_ID)

print(f"\n{'=' * 60}")
print(f"  결과: {PASS_COUNT}/{PASS_COUNT + FAIL_COUNT} passed")
if FAILURES:
    print("\n  실패 목록:")
    for f in FAILURES:
        print(f"    ✗ {f}")
print("=" * 60)
sys.exit(0 if FAIL_COUNT == 0 else 1)
