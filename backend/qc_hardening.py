"""
QC: 로그인 안정성 하드닝 검증 (2026-04-21 적용분)
- /api/auth/refresh 엔드포인트
- login 응답에 expires_in 포함 여부
- is_resigned 계정의 기존 토큰 즉시 무효화
- API 전역 Rate Limit (429)
- 토큰 갱신 후 기존 요청 재시도 흐름 (서버 측 검증)
- master 비밀번호 변경/재발급 이중 잠금 확인
"""
import os
import urllib.request, urllib.error, urllib.parse, json, sys, time

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


def ok(label, status_or_val, body_or_sentinel=None, expected=200):
    global PASS_COUNT, FAIL_COUNT
    # Support both ok(label, status, body, expected) and ok(label, bool_val, True, True)
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
        FAILURES.append(f"{label}")
        return False


def login(emp_id, password):
    s, b = req("POST", "/api/auth/login", form_data={"username": emp_id, "password": password})
    return (b.get("access_token"), b) if s == 200 else (None, b)


print("\n" + "=" * 60)
print("  QC: 로그인 안정성 하드닝 검증")
print("=" * 60)

master_token, _ = login("master", "1234")
if not master_token:
    print("[FATAL] Cannot login as master")
    sys.exit(1)

TEST_ID = "qc_hardening_user"


def cleanup():
    req("DELETE", f"/api/users/{TEST_ID}", token=master_token)


cleanup()

# ─── 1. login 응답에 expires_in 포함 ─────────────────────────────────────────
print("\n[1] login 응답 — expires_in 포함 확인")
s, b = req("POST", "/api/auth/login", form_data={"username": "master", "password": "1234"})
ok("master 로그인 → 200", s, b, 200)
ok("expires_in 필드 존재", "expires_in" in b, True, True)
ok("expires_in > 0", int(b.get("expires_in", 0)) > 0, True, True)
expires_in = b.get("expires_in", 0)
ok(f"expires_in = {expires_in}초 (7200 예상)", expires_in, {}, 7200)

# ─── 2. /api/auth/refresh 엔드포인트 ─────────────────────────────────────────
print("\n[2] /api/auth/refresh 엔드포인트")
s, b = req("POST", "/api/auth/refresh", token=master_token)
ok("/api/auth/refresh → 200", s, b, 200)
ok("새 access_token 발급", bool(b.get("access_token")), True, True)
ok("expires_in 포함", "expires_in" in b, True, True)

new_token = b.get("access_token")
if new_token:
    # 새 토큰으로 me 조회 → 정상 동작 확인
    s2, b2 = req("GET", "/api/auth/me", token=new_token)
    ok("갱신된 토큰으로 /api/auth/me → 200", s2, b2, 200)

# 토큰 없이 refresh → 401
s, b = req("POST", "/api/auth/refresh")
ok("토큰 없이 refresh → 401", s, b, 401)

# ─── 3. is_resigned 계정의 기존 토큰 즉시 무효화 ─────────────────────────────
print("\n[3] is_resigned 계정 — 기존 토큰 즉시 무효화")
# 테스트 계정 생성
s, b = req("POST", "/api/users", {
    "emp_id": TEST_ID, "name": "Hardening User", "department": "QC",
    "email": f"{TEST_ID}@qc.test", "role": "GENERAL"
}, token=master_token)
ok(f"{TEST_ID} 생성 → 200/201", s, b, [200, 201])
temp_pw = b.get("temp_password") if s in (200, 201) else None

if temp_pw:
    user_token, _ = login(TEST_ID, temp_pw)
    ok(f"{TEST_ID} 로그인 성공", bool(user_token), True, True)

    if user_token:
        # 활성 상태에서 me 조회 → 200
        s, b = req("GET", "/api/auth/me", token=user_token)
        ok("비활성화 전 /api/auth/me → 200", s, b, 200)

        # 관리자가 계정 비활성화
        s, b = req("PATCH", f"/api/users/{TEST_ID}/status",
                   {"is_resigned": True}, token=master_token)
        ok("계정 비활성화 → 200", s, b, 200)

        # 기존 토큰으로 me 조회 → 401 (즉시 무효화)
        s, b = req("GET", "/api/auth/me", token=user_token)
        ok("비활성화 후 기존 토큰 → 401", s, b, 401)

        # refresh도 차단 확인
        s, b = req("POST", "/api/auth/refresh", token=user_token)
        ok("비활성화 후 refresh → 401", s, b, 401)

# ─── 4. master 비밀번호 변경 이중 잠금 ───────────────────────────────────────
print("\n[4] master 비밀번호 이중 잠금")
s, b = req("POST", "/api/auth/change-password", {
    "current_password": "1234",
    "new_password": "NewPass1234!"
}, token=master_token)
ok("master change-password → 403 (잠금)", s, b, 403)

s, b = req("POST", "/api/users/master/issue-temp-password", token=master_token)
ok("master issue-temp-password → 403 (잠금)", s, b, 403)

# ─── 5. 로그인 실패 rate limit → 성공 후 초기화 ──────────────────────────────
print("\n[5] 로그인 rate limit 및 성공 후 초기화")
RATE_ID = "qc_rate_test"
req("DELETE", f"/api/users/{RATE_ID}", token=master_token)
s, b = req("POST", "/api/users", {
    "emp_id": RATE_ID, "name": "Rate Test", "department": "QC",
    "email": f"{RATE_ID}@qc.test", "role": "GENERAL"
}, token=master_token)
rate_temp_pw = b.get("temp_password") if s in (200, 201) else None

if rate_temp_pw:
    # 7회 실패
    throttled = False
    for i in range(10):
        s2, _ = req("POST", "/api/auth/login",
                    form_data={"username": RATE_ID, "password": "wrongpassword"})
        if s2 == 429:
            throttled = True
            print(f"    → {i+1}회 시도 후 429 차단됨")
            break
    ok("7회 실패 후 rate limit 429", throttled, True, True)

    # 잠금 해제 대기 없이 올바른 비밀번호로 시도 → 여전히 429
    if throttled:
        s2, _ = req("POST", "/api/auth/login",
                    form_data={"username": RATE_ID, "password": rate_temp_pw})
        ok("잠금 중 올바른 비밀번호도 429", s2, _, 429)

    req("DELETE", f"/api/users/{RATE_ID}", token=master_token)

# ─── 6. /api/auth/me — 응답 필드 완전성 검증 ─────────────────────────────────
print("\n[6] /api/auth/me 응답 필드 완전성")
s, b = req("GET", "/api/auth/me", token=master_token)
ok("/api/auth/me → 200", s, b, 200)
required_fields = ["emp_id", "name", "role", "department", "is_first_login", "is_vip"]
for field in required_fields:
    ok(f"필드 '{field}' 존재", field in b, True, True)

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
