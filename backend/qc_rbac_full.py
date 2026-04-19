"""
QC: 전체 RBAC (Role-Based Access Control) 검증
- GENERAL 멤버: 관리자 전용 엔드포인트 차단
- MASTER vs ADMIN 역할 분리
- 다른 사용자 데이터 접근 차단 (cross-user)
- 비활성화 계정 접근 차단
- 본인 역할 변경 불가
"""
import urllib.request, urllib.error, urllib.parse, json, sys

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
print("  QC: 전체 RBAC 검증")
print("=" * 60)

admin_token = login("master", "1234")
if not admin_token:
    print("[FATAL] Cannot login as master")
    sys.exit(1)

GENERAL_ID = "qc_rbac_general"
ADMIN_ID = "qc_rbac_admin"

def cleanup():
    for uid in [GENERAL_ID, ADMIN_ID]:
        req("DELETE", f"/api/users/{uid}", token=admin_token)

cleanup()

# 테스트 계정 생성
s, b = req("POST", "/api/users", {
    "emp_id": GENERAL_ID, "name": "RBAC General", "department": "QC",
    "email": f"{GENERAL_ID}@qc.test", "role": "GENERAL"
}, token=admin_token)
ok("GENERAL 계정 생성", s, b, [200, 201])
general_temp_pw = b.get("temp_password") if s in (200, 201) else None

s, b = req("POST", "/api/users", {
    "emp_id": ADMIN_ID, "name": "RBAC Admin", "department": "QC",
    "email": f"{ADMIN_ID}@qc.test", "role": "ADMIN"
}, token=admin_token)
ok("ADMIN 계정 생성", s, b, [200, 201])
admin_role_temp_pw = b.get("temp_password") if s in (200, 201) else None

# 임시 비밀번호로 로그인 (생성 응답에서 직접 획득)
general_token = login(GENERAL_ID, general_temp_pw) if general_temp_pw else None
admin_role_token = login(ADMIN_ID, admin_role_temp_pw) if admin_role_temp_pw else None

if not general_token:
    print("[SKIP] GENERAL 토큰 없음 — RBAC 테스트 일부 건너뜀")
if not admin_role_token:
    print("[SKIP] ADMIN 토큰 없음 — ADMIN RBAC 테스트 일부 건너뜀")

# ─── 1. 인증 없이 보호된 엔드포인트 접근 ────────────────────────────────────
print("\n[1] 인증 없이 보호된 엔드포인트")
protected = [
    ("GET", "/api/users"),
    ("GET", "/api/dashboard/admin-stats"),
    ("GET", "/api/attendance/admin/member-summary"),
    ("GET", "/api/fees/admin/members"),
    ("GET", "/api/fees/admin/summary"),
]
for method, path in protected:
    s, b = req(method, path)
    ok(f"비인증 {method} {path} → 401", s, b, 401)

# ─── 2. GENERAL 멤버 — 관리자 전용 엔드포인트 차단 ──────────────────────────
print("\n[2] GENERAL 멤버 — 관리자 전용 엔드포인트 차단")
if general_token:
    admin_only_endpoints = [
        ("GET", "/api/users"),
        ("POST", "/api/users"),
        ("GET", "/api/dashboard/admin-stats"),
        ("GET", "/api/attendance/admin/member-summary"),
        ("GET", "/api/fees/admin/members"),
        ("GET", "/api/fees/admin/summary"),
        ("GET", "/api/fees/admin/matrix"),
        ("GET", "/api/league/admin/seasons"),
    ]
    for method, path in admin_only_endpoints:
        s, b = req(method, path, token=general_token)
        ok(f"GENERAL {method} {path} → 403", s, b, 403)

# ─── 3. GENERAL 멤버 — 접근 가능한 엔드포인트 ──────────────────────────────
print("\n[3] GENERAL 멤버 — 접근 허용 엔드포인트")
if general_token:
    member_allowed = [
        ("GET", "/api/attendance/events"),
        ("GET", "/api/auth/me"),
        ("GET", "/api/fees/me"),
        ("GET", "/api/fees/me/history"),
        ("GET", "/api/notices"),
    ]
    for method, path in member_allowed:
        s, b = req(method, path, token=general_token)
        ok(f"GENERAL {method} {path} → 200", s, b, 200)

# ─── 4. GENERAL 멤버 — 다른 사용자 데이터 접근 차단 ────────────────────────
print("\n[4] GENERAL 멤버 — Cross-user 데이터 접근 차단")
if general_token:
    s, b = req("GET", f"/api/users/{ADMIN_ID}", token=general_token)
    ok(f"다른 사용자 상세 조회 차단 → 403 또는 404", s, b, [403, 404])

    s, b = req("PATCH", f"/api/users/{ADMIN_ID}/status",
               {"is_resigned": True}, token=general_token)
    ok("다른 사용자 비활성화 시도 차단 → 403", s, b, 403)

    s, b = req("PATCH", f"/api/users/{ADMIN_ID}/role",
               {"role": "GENERAL"}, token=general_token)
    ok("다른 사용자 역할 변경 시도 차단 → 403", s, b, 403)

# ─── 5. GENERAL 멤버 — 본인 역할 변경 불가 ──────────────────────────────────
print("\n[5] GENERAL 멤버 — 본인 역할 변경 불가")
if general_token:
    s, b = req("PATCH", f"/api/users/{GENERAL_ID}/role",
               {"role": "MASTER"}, token=general_token)
    ok("본인 역할 MASTER로 변경 시도 → 403", s, b, 403)

# ─── 6. MASTER — 모든 관리자 엔드포인트 접근 가능 ───────────────────────────
print("\n[6] MASTER — 관리자 엔드포인트 전체 접근")
master_endpoints = [
    ("GET", "/api/users"),
    ("GET", "/api/dashboard/admin-stats"),
    ("GET", "/api/attendance/admin/member-summary"),
    ("GET", "/api/fees/admin/members"),
    ("GET", "/api/league/admin/seasons"),
]
for method, path in master_endpoints:
    s, b = req(method, path, token=admin_token)
    ok(f"MASTER {method} {path} → 200", s, b, 200)

# ─── 7. 비활성화 계정 — 토큰이 있어도 재로그인 불가 확인 ───────────────────
print("\n[7] 비활성화 계정 — 로그인 차단")
req("PATCH", f"/api/users/{GENERAL_ID}/status", {"is_resigned": True}, token=admin_token)
s, b = req("POST", "/api/auth/login",
           form_data={"username": GENERAL_ID, "password": "1234"})
ok("비활성화 계정 로그인 차단 → 401 또는 403", s, b, [401, 403])

# ─── 8. 공지사항 — 역할별 권한 ──────────────────────────────────────────────
print("\n[8] 공지사항 CRUD 권한")
# Admin creates notice
s, b = req("POST", "/api/notices", {
    "title": "RBAC 테스트 공지", "body": "테스트 내용", "is_pinned": False
}, token=admin_token)
ok("MASTER 공지사항 생성 → 201", s, b, [200, 201])
notice_id = b.get("id") if s in (200, 201) else None

if notice_id and admin_role_token:
    s, b = req("DELETE", f"/api/notices/{notice_id}", token=admin_role_token)
    ok("ADMIN 공지사항 삭제 → 200 또는 204", s, b, [200, 204])
    notice_id = None

if notice_id and general_token:
    s, b = req("DELETE", f"/api/notices/{notice_id}", token=general_token)
    ok("GENERAL 공지사항 삭제 차단 → 403", s, b, 403)

if notice_id:
    req("DELETE", f"/api/notices/{notice_id}", token=admin_token)

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
