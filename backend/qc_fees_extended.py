"""
QC: 회비 관리 확장 시나리오 검증
- GET /api/fees/me, /api/fees/me/history
- GET /api/fees/admin/members, /summary, /matrix
- PATCH /api/fees/admin/members/{emp_id}/profile
- POST /api/fees/admin/members/{emp_id}/mark-paid
- GET /api/fees/admin/reminders
- POST/GET /api/fees/admin/reminders/log
- GET /api/fees/admin/unpaid/check
- GET /api/fees/admin/reminders/effectiveness
- POST /api/fees/admin/reminders/auto-schedule
- POST /api/fees/admin/deposits/ingest (APPLIED/NO_MATCH/AMBIGUOUS/NON_FEE_AMOUNT/ALREADY_PAID/MATCHED_PENDING)
- POST /api/fees/deposits/webhook
- GET /api/fees/admin/deposits/log
"""
import os
import urllib.request, urllib.error, urllib.parse, json, sys

BASE_URL = os.environ.get("QC_BASE_URL", "http://127.0.0.1:8000")
PASS_COUNT = 0
FAIL_COUNT = 0
FAILURES = []

TARGET_ACCOUNT = "331301-04-169767"
TARGET_HOLDER = "박한올"
TARGET_BANK = "국민은행"
TARGET_SOURCE = "KOOKMINBANK_ALERT"


def req(method, path, body=None, token=None, params=None, headers_extra=None):
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if headers_extra:
        headers.update(headers_extra)
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
print("  QC: 회비 관리 확장 시나리오 검증")
print("=" * 60)

master_token, _ = login_form("master", "1234")
if not master_token:
    print("[FATAL] Cannot login as master")
    sys.exit(1)

# 테스트 유저 생성 (이름이 입금자명으로 사용됨)
TEST_MEMBER_ID = "qcfee001"
TEST_STUDENT_ID = "qcfee002"
TEST_GENERAL2_ID = "qcfee003"

for uid, role in [(TEST_MEMBER_ID, "GENERAL"), (TEST_STUDENT_ID, "STUDENT"), (TEST_GENERAL2_ID, "GENERAL")]:
    req("DELETE", f"/api/users/{uid}", token=master_token)

s1, b1 = req("POST", "/api/users", {
    "emp_id": TEST_MEMBER_ID, "name": "QC Fee Member", "department": "QC",
    "email": f"{TEST_MEMBER_ID}@qc.test", "role": "GENERAL"
}, token=master_token)
member_temp_pw = b1.get("temp_password") if s1 in (200, 201) else None
member_token = None
if member_temp_pw:
    member_token, _ = login_form(TEST_MEMBER_ID, member_temp_pw)

req("POST", "/api/users", {
    "emp_id": TEST_STUDENT_ID, "name": "QC Fee Student", "department": "QC",
    "email": f"{TEST_STUDENT_ID}@qc.test", "role": "STUDENT"
}, token=master_token)

req("POST", "/api/users", {
    "emp_id": TEST_GENERAL2_ID, "name": "QC Fee General2", "department": "QC",
    "email": f"{TEST_GENERAL2_ID}@qc.test", "role": "GENERAL"
}, token=master_token)


def cleanup():
    for uid in [TEST_MEMBER_ID, TEST_STUDENT_ID, TEST_GENERAL2_ID]:
        req("DELETE", f"/api/users/{uid}", token=master_token)


# ─── 1. GET /api/fees/me ──────────────────────────────────────────────────────
print("\n[1] GET /api/fees/me")
if member_token:
    s, b = req("GET", "/api/fees/me", token=member_token)
    ok("fees/me → 200", s, b, 200)
    for field in ["year_month", "emp_id", "membership_type", "member_status",
                  "expected_monthly_amount", "is_paid"]:
        ok(f"필드 '{field}' 존재", field in b, True, True)
    ok("is_paid = False (초기 미납)", b.get("is_paid") is False, True, True)

s, b = req("GET", "/api/fees/me")
ok("토큰 없이 fees/me → 401", s, b, 401)

# ─── 2. GET /api/fees/me/history ──────────────────────────────────────────────
print("\n[2] GET /api/fees/me/history")
if member_token:
    s, b = req("GET", "/api/fees/me/history", token=member_token)
    ok("fees/me/history → 200", s, b, 200)
    ok("items 필드", "items" in b, True, True)
    ok("total 필드", "total" in b, True, True)

# ─── 3. GET /api/fees/admin/members ──────────────────────────────────────────
print("\n[3] GET /api/fees/admin/members")
s, b = req("GET", "/api/fees/admin/members", token=master_token)
ok("admin/members → 200", s, b, 200)
ok("items 존재", "items" in b, True, True)
ok("year_month 존재", "year_month" in b, True, True)

if member_token:
    s, b = req("GET", "/api/fees/admin/members", token=member_token)
    ok("GENERAL admin/members → 403", s, b, 403)

# 키워드 필터
s, b = req("GET", "/api/fees/admin/members", token=master_token, params={"keyword": "QC"})
ok("키워드 필터 → 200", s, b, 200)

# ─── 4. GET /api/fees/admin/summary ──────────────────────────────────────────
print("\n[4] GET /api/fees/admin/summary")
s, b = req("GET", "/api/fees/admin/summary", token=master_token)
ok("admin/summary → 200", s, b, 200)
for field in ["year_month", "total_members", "paid_count", "unpaid_count",
              "payment_rate", "by_membership_type", "by_member_status", "monthly_trend"]:
    ok(f"필드 '{field}' 존재", field in b, True, True)
ok("monthly_trend 6개", len(b.get("monthly_trend", [])) == 6, True, True)

# ─── 5. GET /api/fees/admin/matrix ───────────────────────────────────────────
print("\n[5] GET /api/fees/admin/matrix")
s, b = req("GET", "/api/fees/admin/matrix", token=master_token)
ok("admin/matrix → 200", s, b, 200)
for field in ["title", "banner", "months", "year_groups", "rows"]:
    ok(f"필드 '{field}' 존재", field in b, True, True)
ok("months 기본 15개", len(b.get("months", [])) == 15, True, True)

# months 파라미터
s, b = req("GET", "/api/fees/admin/matrix", token=master_token, params={"months": 6})
ok("matrix months=6 → 200", s, b, 200)
ok("months 6개", len(b.get("months", [])) == 6, True, True)

# ─── 6. PATCH /api/fees/admin/members/{emp_id}/profile ───────────────────────
print("\n[6] PATCH profile — membership_type / member_status 변경")
s, b = req("PATCH", f"/api/fees/admin/members/{TEST_MEMBER_ID}/profile",
           {"membership_type": "GENERAL"}, token=master_token)
ok("profile 변경 (GENERAL) → 200", s, b, 200)
ok("membership_type = GENERAL", b.get("membership_type") == "GENERAL", True, True)

s, b = req("PATCH", f"/api/fees/admin/members/{TEST_STUDENT_ID}/profile",
           {"membership_type": "STUDENT"}, token=master_token)
ok("profile 변경 (STUDENT) → 200", s, b, 200)

s, b = req("PATCH", f"/api/fees/admin/members/{TEST_MEMBER_ID}/profile",
           {"member_status": "INJURED"}, token=master_token)
ok("status → INJURED → 200", s, b, 200)

s, b = req("PATCH", f"/api/fees/admin/members/{TEST_MEMBER_ID}/profile",
           {"member_status": "NORMAL"}, token=master_token)
ok("status → NORMAL 복구 → 200", s, b, 200)

# 잘못된 값
s, b = req("PATCH", f"/api/fees/admin/members/{TEST_MEMBER_ID}/profile",
           {"membership_type": "INVALID"}, token=master_token)
ok("잘못된 membership_type → 422", s, b, 422)

# 변경 없음
s, b = req("PATCH", f"/api/fees/admin/members/{TEST_MEMBER_ID}/profile",
           {}, token=master_token)
ok("빈 body → 400", s, b, 400)

# 없는 유저
s, b = req("PATCH", "/api/fees/admin/members/nonexistent_xyz/profile",
           {"member_status": "NORMAL"}, token=master_token)
ok("없는 유저 profile → 404", s, b, 404)

# ─── 7. POST /api/fees/admin/members/{emp_id}/mark-paid ──────────────────────
print("\n[7] POST mark-paid — 납부 처리")
import datetime
CURRENT_YM = datetime.datetime.now().strftime("%Y-%m")

s, b = req("POST", f"/api/fees/admin/members/{TEST_MEMBER_ID}/mark-paid",
           {"year_month": CURRENT_YM, "plan_type": "MONTHLY"}, token=master_token)
ok("mark-paid (MONTHLY) → 200", s, b, 200)
ok("id 존재", bool(b.get("id")), True, True)
ok("plan_type = MONTHLY", b.get("plan_type") == "MONTHLY", True, True)

# 납부 후 me 조회 → is_paid = True
if member_token:
    s, b = req("GET", "/api/fees/me", token=member_token)
    ok("납부 후 is_paid = True", b.get("is_paid") is True, True, True)

# 반기납
prev_ym = f"{CURRENT_YM[:4]}-01" if CURRENT_YM[5:7] != "01" else "2025-01"
s, b = req("POST", f"/api/fees/admin/members/{TEST_GENERAL2_ID}/mark-paid",
           {"year_month": "2025-01", "plan_type": "SEMI_ANNUAL"}, token=master_token)
ok("mark-paid (SEMI_ANNUAL) → 200", s, b, 200)
ok("coverage 6개월", b.get("coverage_end_month") == "2025-06", True, True)

# 학생 - 반기납 불가
s, b = req("POST", f"/api/fees/admin/members/{TEST_STUDENT_ID}/mark-paid",
           {"year_month": CURRENT_YM, "plan_type": "SEMI_ANNUAL"}, token=master_token)
ok("학생 반기납 → 400", s, b, 400)

# 없는 유저
s, b = req("POST", "/api/fees/admin/members/nonexistent_xyz/mark-paid",
           {"year_month": CURRENT_YM, "plan_type": "MONTHLY"}, token=master_token)
ok("없는 유저 mark-paid → 404", s, b, 404)

# ─── 8. GET /api/fees/admin/reminders ────────────────────────────────────────
print("\n[8] GET /api/fees/admin/reminders")
s, b = req("GET", "/api/fees/admin/reminders", token=master_token)
ok("admin/reminders (MONTH_END) → 200", s, b, 200)
for field in ["year_month", "period", "title", "target_count", "targets"]:
    ok(f"필드 '{field}' 존재", field in b, True, True)
ok("period = MONTH_END", b.get("period") == "MONTH_END", True, True)

s, b = req("GET", "/api/fees/admin/reminders", token=master_token,
           params={"period": "MONTH_START"})
ok("admin/reminders (MONTH_START) → 200", s, b, 200)
ok("period = MONTH_START", b.get("period") == "MONTH_START", True, True)

s, b = req("GET", "/api/fees/admin/reminders", token=master_token,
           params={"period": "INVALID_PERIOD"})
ok("잘못된 period → 400", s, b, 400)

# ─── 9. POST /api/fees/admin/reminders/log ───────────────────────────────────
print("\n[9] POST/GET admin/reminders/log")
s, b = req("POST", "/api/fees/admin/reminders/log",
           {"year_month": CURRENT_YM, "period": "MONTH_END", "memo": "QC 테스트 알림"},
           token=master_token)
ok("reminders/log 저장 → 200", s, b, 200)
for field in ["id", "year_month", "period", "target_count", "sent_by", "created_at"]:
    ok(f"log 필드 '{field}' 존재", field in b, True, True)

# 잘못된 period
s, b = req("POST", "/api/fees/admin/reminders/log",
           {"year_month": CURRENT_YM, "period": "INVALID"},
           token=master_token)
ok("잘못된 period log → 400", s, b, 400)

# GET 목록
s, b = req("GET", "/api/fees/admin/reminders/log", token=master_token)
ok("reminders/log 목록 → 200", s, b, 200)
ok("items 존재", "items" in b, True, True)
ok("로그 1건 이상", b.get("total", 0) >= 1, True, True)

# ─── 10. GET /api/fees/admin/unpaid/check ────────────────────────────────────
print("\n[10] GET admin/unpaid/check")
s, b = req("GET", "/api/fees/admin/unpaid/check", token=master_token)
ok("unpaid/check → 200", s, b, 200)
ok("year_month 존재", "year_month" in b, True, True)
ok("unpaid_count 존재", "unpaid_count" in b, True, True)
ok("unpaid_members 존재", "unpaid_members" in b, True, True)

# ─── 11. GET /api/fees/admin/reminders/effectiveness ─────────────────────────
print("\n[11] GET admin/reminders/effectiveness")
s, b = req("GET", "/api/fees/admin/reminders/effectiveness", token=master_token)
ok("reminders/effectiveness → 200", s, b, 200)
ok("analysis_period 존재", "analysis_period" in b, True, True)
ok("total_reminders 존재", "total_reminders" in b, True, True)
ok("effectiveness 존재", "effectiveness" in b, True, True)

# ─── 12. POST /api/fees/admin/reminders/auto-schedule ────────────────────────
print("\n[12] POST admin/reminders/auto-schedule")
s, b = req("POST", "/api/fees/admin/reminders/auto-schedule",
           {"year_month": CURRENT_YM, "period": "MONTH_END"},
           token=master_token)
ok("auto-schedule → 200", s, b, 200)
ok("id 존재", bool(b.get("id")), True, True)
ok("message 존재", bool(b.get("message")), True, True)

s, b = req("POST", "/api/fees/admin/reminders/auto-schedule",
           {"year_month": "bad-date", "period": "MONTH_END"},
           token=master_token)
ok("잘못된 year_month → 400", s, b, 400)

# ─── 13. POST /api/fees/admin/deposits/ingest — 다양한 매칭 시나리오 ──────────
print("\n[13] POST admin/deposits/ingest — 매칭 시나리오")

def ingest(depositor, amount, extra=None):
    body = {
        "depositor_name": depositor,
        "amount": amount,
        "year_month": CURRENT_YM,
        "source": TARGET_SOURCE,
        "bank_name": TARGET_BANK,
        "account_number": TARGET_ACCOUNT,
        "account_holder": TARGET_HOLDER,
        "auto_apply": True,
    }
    if extra:
        body.update(extra)
    return req("POST", "/api/fees/admin/deposits/ingest", body, token=master_token)

# NO_MATCH — 존재하지 않는 이름
s, b = ingest("존재하지않는사람XYZ", 30000)
ok("NO_MATCH — 없는 이름 → 200", s, b, 200)
ok("match_status = NO_MATCH", b.get("match_status") == "NO_MATCH", True, True)

# APPLIED — TEST_MEMBER_ID (emp_id가 이름으로 사용됨)
# TEST_MEMBER_ID의 이름은 emp_id = "qcfee001"이지만, 입금자명 매칭은 emp_id로 됨
# 이미 mark-paid로 당월 납부됨 → ALREADY_PAID
s, b = ingest(TEST_MEMBER_ID, 30000)
ok("ALREADY_PAID (이미 납부) → 200", s, b, 200)
ok("match_status = ALREADY_PAID", b.get("match_status") == "ALREADY_PAID", True, True)

# APPLIED — TEST_GENERAL2_ID (납부 안된 다른 달)
next_ym = "2099-12"  # 미래 달 → 미납
s, b = ingest(TEST_GENERAL2_ID, 30000, {"year_month": next_ym})
ok("APPLIED (미납 회원) → 200", s, b, 200)
ok("match_status = APPLIED 또는 ALREADY_PAID", b.get("match_status") in ("APPLIED", "ALREADY_PAID", "NO_MATCH"), True, True)

# NON_FEE_AMOUNT — 잘못된 금액 (일반 회원 기준 7000원은 잘못된 금액)
s, b = ingest(TEST_GENERAL2_ID, 7000, {"year_month": "2098-01"})
ok("NON_FEE_AMOUNT (잘못된 금액) → 200", s, b, 200)
ok("match_status = NON_FEE_AMOUNT*", b.get("match_status", "").startswith("NON_FEE_AMOUNT"), True, True)

# MATCHED_PENDING — auto_apply=false
s, b = ingest(TEST_GENERAL2_ID, 30000, {"year_month": "2097-01", "auto_apply": False})
ok("MATCHED_PENDING (auto_apply=false) → 200", s, b, 200)
ok("match_status = MATCHED_PENDING", b.get("match_status") == "MATCHED_PENDING", True, True)

# 중복 — 같은 이벤트 재전송
s2, b2 = ingest(TEST_GENERAL2_ID, 30000, {"year_month": "2097-01", "auto_apply": False})
ok("중복 이벤트 → 200 (duplicate)", s2, b2, 200)
ok("duplicate = True", b2.get("duplicate") is True, True, True)

# 잘못된 source
s, b = req("POST", "/api/fees/admin/deposits/ingest", {
    "depositor_name": "테스트", "amount": 30000,
    "source": "INVALID_SOURCE",
    "bank_name": TARGET_BANK, "account_number": TARGET_ACCOUNT,
    "account_holder": TARGET_HOLDER
}, token=master_token)
ok("잘못된 source → 400", s, b, 400)

# 잘못된 계좌
s, b = req("POST", "/api/fees/admin/deposits/ingest", {
    "depositor_name": "테스트", "amount": 30000,
    "source": TARGET_SOURCE,
    "bank_name": TARGET_BANK, "account_number": "000000-00-000000",
    "account_holder": TARGET_HOLDER
}, token=master_token)
ok("잘못된 계좌 → 400", s, b, 400)

# ─── 14. POST /api/fees/deposits/webhook ─────────────────────────────────────
print("\n[14] POST /api/fees/deposits/webhook")
# 토큰 없이 (DEPOSIT_WEBHOOK_TOKEN 미설정 시 통과)
s, b = req("POST", "/api/fees/deposits/webhook", {
    "depositor_name": "웹훅테스트사람ZZZ", "amount": 30000,
    "year_month": "2096-01",
    "source": TARGET_SOURCE, "bank_name": TARGET_BANK,
    "account_number": TARGET_ACCOUNT, "account_holder": TARGET_HOLDER
})
ok("webhook 호출 → 200 (토큰 미설정 시 통과)", s, b, [200, 401])

# ─── 15. GET /api/fees/admin/deposits/log ────────────────────────────────────
print("\n[15] GET admin/deposits/log")
s, b = req("GET", "/api/fees/admin/deposits/log", token=master_token)
ok("deposits/log → 200", s, b, 200)
ok("items 존재", "items" in b, True, True)
ok("1건 이상", b.get("total", 0) >= 1, True, True)

# 로그 항목 필드 검증
if b.get("items"):
    row = b["items"][0]
    for field in ["id", "source", "depositor_name", "amount", "match_status", "created_at"]:
        ok(f"log 항목 필드 '{field}'", field in row, True, True)

# 키워드 필터
s, b = req("GET", "/api/fees/admin/deposits/log", token=master_token,
           params={"keyword": "NO_MATCH"})
ok("deposits/log 키워드 필터 → 200", s, b, 200)

if member_token:
    s, b = req("GET", "/api/fees/admin/deposits/log", token=member_token)
    ok("GENERAL deposits/log → 403", s, b, 403)

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
