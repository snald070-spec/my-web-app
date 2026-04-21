"""
QC: 대시보드 전체 시나리오 검증
- GET /api/dashboard/summary (인증 필요, 역할 무관)
- GET /api/dashboard/admin-stats (관리자 전용)
- POST /api/dashboard/admin/non-fee-deposits/ack-all (관리자 전용)
"""
import os
import urllib.request, urllib.error, urllib.parse, json, sys

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
print("  QC: 대시보드 전체 시나리오 검증")
print("=" * 60)

master_token, _ = login_form("master", "1234")
if not master_token:
    print("[FATAL] Cannot login as master")
    sys.exit(1)

# 테스트용 GENERAL 유저 생성
GENERAL_ID = "qc_dash_general"
s, b = req("POST", "/api/users", {
    "emp_id": GENERAL_ID, "name": "QC Dash General", "department": "QC",
    "email": f"{GENERAL_ID}@qc.test", "role": "GENERAL"
}, token=master_token)
general_temp_pw = b.get("temp_password") if s in (200, 201) else None
general_token = None
if general_temp_pw:
    general_token, _ = login_form(GENERAL_ID, general_temp_pw)


def cleanup():
    req("DELETE", f"/api/users/{GENERAL_ID}", token=master_token)


# ─── 1. /api/dashboard/summary ───────────────────────────────────────────────
print("\n[1] GET /api/dashboard/summary")
s, b = req("GET", "/api/dashboard/summary", token=master_token)
ok("master summary → 200", s, b, 200)
ok("message 필드 존재", "message" in b, True, True)
ok("role 필드 존재", "role" in b, True, True)

if general_token:
    s, b = req("GET", "/api/dashboard/summary", token=general_token)
    ok("GENERAL summary → 200", s, b, 200)

s, b = req("GET", "/api/dashboard/summary")
ok("토큰 없이 summary → 401", s, b, 401)

# ─── 2. /api/dashboard/admin-stats ───────────────────────────────────────────
print("\n[2] GET /api/dashboard/admin-stats")
s, b = req("GET", "/api/dashboard/admin-stats", token=master_token)
ok("master admin-stats → 200", s, b, 200)
for field in ["total_users", "status_changes_today", "non_fee_deposit_alerts",
              "non_fee_deposit_alerts_today", "recent_non_fee_deposits"]:
    ok(f"필드 '{field}' 존재", field in b, True, True)
ok("total_users ≥ 1", int(b.get("total_users", 0)) >= 1, True, True)
ok("recent_non_fee_deposits 는 list", isinstance(b.get("recent_non_fee_deposits"), list), True, True)

if general_token:
    s, b = req("GET", "/api/dashboard/admin-stats", token=general_token)
    ok("GENERAL admin-stats → 403", s, b, 403)

s, b = req("GET", "/api/dashboard/admin-stats")
ok("토큰 없이 admin-stats → 401", s, b, 401)

# recent_non_fee_deposits 항목 필드 검증 (항목이 있는 경우)
stats_body = None
s2, b2 = req("GET", "/api/dashboard/admin-stats", token=master_token)
if s2 == 200:
    stats_body = b2
    recent = b2.get("recent_non_fee_deposits", [])
    if recent:
        row = recent[0]
        for field in ["id", "depositor_name", "amount", "year_month", "created_at"]:
            ok(f"recent_non_fee_deposits[0].{field} 존재", field in row, True, True)

# ─── 3. POST /api/dashboard/admin/non-fee-deposits/ack-all ───────────────────
print("\n[3] POST /api/dashboard/admin/non-fee-deposits/ack-all")

# today_only=True (기본값)
s, b = req("POST", "/api/dashboard/admin/non-fee-deposits/ack-all", token=master_token)
ok("ack-all (today_only 기본값) → 200", s, b, 200)
ok("acknowledged 필드 존재", "acknowledged" in b, True, True)
ok("today_only 필드 존재", "today_only" in b, True, True)
ok("message 필드 존재", "message" in b, True, True)

# today_only=False
s, b = req("POST", "/api/dashboard/admin/non-fee-deposits/ack-all", token=master_token,
           params={"today_only": "false"})
ok("ack-all (today_only=false) → 200", s, b, 200)

# GENERAL 유저 권한 거부
if general_token:
    s, b = req("POST", "/api/dashboard/admin/non-fee-deposits/ack-all", token=general_token)
    ok("GENERAL ack-all → 403", s, b, 403)

# 토큰 없음
s, b = req("POST", "/api/dashboard/admin/non-fee-deposits/ack-all")
ok("토큰 없이 ack-all → 401", s, b, 401)

# ─── 4. ack 후 admin-stats 재확인 ─────────────────────────────────────────────
print("\n[4] ack 후 non_fee_deposit_alerts_today 감소 확인")
s_after, b_after = req("GET", "/api/dashboard/admin-stats", token=master_token)
ok("ack 후 admin-stats → 200", s_after, b_after, 200)
# ack 처리 후 today 알림 수는 0이어야 함
ok("today 알림 수 = 0", int(b_after.get("non_fee_deposit_alerts_today", -1)) == 0, True, True)

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
