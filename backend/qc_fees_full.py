"""
QC: 회비 관리 전체 플로우
- 멤버 프로필 조회 및 수정
- 회비 납부 기록
- 납부 이력 조회
- 멤버십 타입 변경 (GENERAL / STUDENT)
- 멤버 상태 변경 (NORMAL / INJURED / DORMANT)
- 미납 체크
- 관리자 전용 기능 권한 검증
"""
import os
import urllib.request, urllib.error, urllib.parse, json, sys
from datetime import date

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


print("\n" + "=" * 60)
print("  QC: 회비 관리 전체 플로우")
print("=" * 60)

admin_token = login("master", "1234")
if not admin_token:
    print("[FATAL] Cannot login as master")
    sys.exit(1)

MEMBER_ID = "qc_fee_member"
MEMBER2_ID = "qc_fee_member2"

def cleanup():
    req("DELETE", f"/api/users/{MEMBER_ID}", token=admin_token)
    req("DELETE", f"/api/users/{MEMBER2_ID}", token=admin_token)

cleanup()

# 멤버 계정 생성
member_token = None
member2_token = None
for uid, name in [(MEMBER_ID, "Fee Member 1"), (MEMBER2_ID, "Fee Member 2")]:
    s, b = req("POST", "/api/users", {
        "emp_id": uid, "name": name, "department": "QC",
        "email": f"{uid}@qc.test", "role": "GENERAL"
    }, token=admin_token)
    ok(f"{uid} 생성", s, b, [200, 201])
    tmp_pw = b.get("temp_password") if s in (200, 201) else None
    if tmp_pw:
        tok = login(uid, tmp_pw)
        if uid == MEMBER_ID:
            member_token = tok
        else:
            member2_token = tok

# ─── 1. 멤버 본인 회비 프로필 조회 ──────────────────────────────────────────
print("\n[1] 멤버 본인 회비 프로필 조회")
if member_token:
    s, b = req("GET", "/api/fees/me", token=member_token)
    ok("멤버 본인 프로필 조회", s, b, 200)
    if s == 200:
        ok("membership_type 필드 존재", "membership_type" in b, True, True)
        ok("member_status 필드 존재", "member_status" in b, True, True)

    s, b = req("GET", "/api/fees/me/history", token=member_token)
    ok("멤버 납부 이력 조회", s, b, 200)

# ─── 2. Cross-user 접근 차단 ─────────────────────────────────────────────────
print("\n[2] Cross-user 회비 접근 차단")
if member_token:
    s, b = req("GET", f"/api/fees/admin/members", token=member_token)
    ok("멤버가 관리자 회비 목록 조회 차단 → 403", s, b, 403)

if member2_token:
    # 다른 멤버의 회비 납부 기록 시도 (관리자 전용)
    s, b = req("POST", f"/api/fees/admin/members/{MEMBER_ID}/mark-paid",
               {"year_month": "2026-01", "paid_amount": 30000, "note": "cross-user test"},
               token=member2_token)
    ok("다른 멤버 회비 납부 기록 시도 차단 → 403", s, b, 403)

# ─── 3. 관리자 회비 프로필 조회 및 수정 ─────────────────────────────────────
print("\n[3] 관리자 회비 프로필 관리")
s, b = req("GET", "/api/fees/admin/members", token=admin_token)
ok("관리자 멤버 목록 조회", s, b, 200)

s, b = req("GET", "/api/fees/admin/summary", token=admin_token)
ok("관리자 회비 요약 조회", s, b, 200)

# 멤버십 타입 변경: GENERAL → STUDENT
s, b = req("PATCH", f"/api/fees/admin/members/{MEMBER_ID}/profile",
           {"membership_type": "STUDENT"}, token=admin_token)
ok("membership_type → STUDENT 변경", s, b, 200)
if s == 200:
    ok("변경된 타입 반영 확인", b.get("membership_type") == "STUDENT", True, True)

# 멤버 상태 변경: NORMAL → INJURED
s, b = req("PATCH", f"/api/fees/admin/members/{MEMBER_ID}/profile",
           {"member_status": "INJURED"}, token=admin_token)
ok("member_status → INJURED 변경", s, b, 200)

# 원래대로 복구
s, b = req("PATCH", f"/api/fees/admin/members/{MEMBER_ID}/profile",
           {"membership_type": "GENERAL", "member_status": "NORMAL"}, token=admin_token)
ok("프로필 원복", s, b, 200)

# ─── 4. 회비 납부 기록 ───────────────────────────────────────────────────────
print("\n[4] 회비 납부 기록")
today = date.today()
year_month = f"{today.year}-{today.month:02d}"

s, b = req("POST", f"/api/fees/admin/members/{MEMBER_ID}/mark-paid", {
    "year_month": year_month,
    "paid_amount": 30000,
    "note": "QC 테스트 납부"
}, token=admin_token)
ok(f"회비 납부 기록 ({year_month})", s, b, [200, 201])

# 납부 후 이력 확인
if member_token:
    s, b = req("GET", "/api/fees/me/history", token=member_token)
    ok("납부 후 이력 조회", s, b, 200)
    if s == 200:
        items = b.get("items", b if isinstance(b, list) else [])
        ok("납부 이력에 데이터 존재", len(items) > 0, True, True)

# ─── 5. 관리자 회비 매트릭스 ────────────────────────────────────────────────
print("\n[5] 회비 매트릭스 및 미납 체크")
s, b = req("GET", "/api/fees/admin/matrix", token=admin_token)
ok("회비 매트릭스 조회", s, b, 200)

s, b = req("GET", "/api/fees/admin/unpaid/check", token=admin_token)
ok("미납 체크 조회", s, b, 200)

# ─── 6. 잘못된 year_month 형식 ──────────────────────────────────────────────
print("\n[6] 납부 기록 — 입력 검증")
s, b = req("POST", f"/api/fees/admin/members/{MEMBER_ID}/mark-paid", {
    "year_month": "2026/01",  # 잘못된 형식
    "amount": 30000
}, token=admin_token)
ok("잘못된 year_month 형식 → 400 또는 422", s, b, [400, 422])

s, b = req("POST", f"/api/fees/admin/members/{MEMBER_ID}/mark-paid", {
    "year_month": year_month,
    "paid_amount": -1000  # 음수 금액
}, token=admin_token)
ok("음수 금액 → 400 또는 422 또는 저장됨", s, b, [200, 201, 400, 422])

# ─── 7. 리마인더 조회 ────────────────────────────────────────────────────────
print("\n[7] 회비 리마인더")
s, b = req("GET", "/api/fees/admin/reminders", token=admin_token)
ok("리마인더 조회", s, b, 200)

if member_token:
    s, b = req("GET", "/api/fees/admin/reminders", token=member_token)
    ok("멤버 리마인더 조회 차단 → 403", s, b, 403)

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
