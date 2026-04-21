"""
QC: 사용자 관리 전체 플로우
- 사용자 생성 (다양한 필드 조합, VIP, division)
- 사용자 단건 조회
- 사용자 목록 (pagination, keyword, role/status/first_login 필터, 정렬)
- 프로필 수정 (department, division, email, emp_id 변경)
- 역할 변경 (MASTER 전용 엔드포인트)
- 상태 변경 (활성/비활성) + 자기 자신 비활성화 차단
- 임시 비밀번호 재발급 (ADMIN 계정 → 200, GENERAL 비폰ID → 400)
- 감사 로그 조회
- 단건 삭제 (MASTER 전용), 자기 자신 삭제 차단
- 일괄 삭제 (bulk-delete)
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


def req_qs(method, path, params=None, token=None):
    if params:
        path = f"{path}?{urllib.parse.urlencode(params)}"
    return req(method, path, token=token)


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
        detail = str(body_or_sentinel)[:120] if body_or_sentinel is not True else str(status_or_val)
        print(f"  [FAIL] {label} — expected {expected}, got {status_or_val} | {detail}")
        FAIL_COUNT += 1
        FAILURES.append(label)
        return False


def login(emp_id, password):
    s, b = req("POST", "/api/auth/login", form_data={"username": emp_id, "password": password})
    return b.get("access_token") if s == 200 else None


print("\n" + "=" * 60)
print("  QC: 사용자 관리 전체 플로우")
print("=" * 60)

master_token = login("master", "1234")
if not master_token:
    print("[FATAL] Cannot login as master")
    sys.exit(1)

U1 = "qc_usr_general"
U2 = "qc_usr_admin"
U3 = "qc_usr_vip"
U4 = "qc_usr_rename"
U5 = "qc_usr_bulk1"
U6 = "qc_usr_bulk2"
ALL_IDS = [U1, U2, U3, U4, U5, U6]


def cleanup():
    for uid in ALL_IDS:
        req("DELETE", f"/api/users/{uid}", token=master_token)
    for uid in ["qc_usr_renamed", "qc_usr_renamed2"]:
        req("DELETE", f"/api/users/{uid}", token=master_token)


cleanup()

# ─── 1. 사용자 생성 ──────────────────────────────────────────────────────────
print("\n[1] 사용자 생성 — 다양한 필드")

s, b = req("POST", "/api/users", {
    "emp_id": U1, "name": U1, "department": "QC팀", "email": f"{U1}@qc.test",
    "role": "GENERAL", "division": "개발", "is_vip": False
}, token=master_token)
ok(f"{U1} (GENERAL) 생성 → 201", s, b, [200, 201])
u1_temp_pw = b.get("temp_password") if s in (200, 201) else None

s, b = req("POST", "/api/users", {
    "emp_id": U2, "name": U2, "department": "QC팀", "email": f"{U2}@qc.test",
    "role": "ADMIN"
}, token=master_token)
ok(f"{U2} (ADMIN) 생성 → 201", s, b, [200, 201])
u2_temp_pw = b.get("temp_password") if s in (200, 201) else None

s, b = req("POST", "/api/users", {
    "emp_id": U3, "name": U3, "department": "QC팀",
    "role": "GENERAL", "is_vip": True
}, token=master_token)
ok(f"{U3} (VIP) 생성 → 201", s, b, [200, 201])

s, b = req("POST", "/api/users", {
    "emp_id": U4, "name": U4, "department": "QC팀", "role": "GENERAL"
}, token=master_token)
ok(f"{U4} (rename test) 생성 → 201", s, b, [200, 201])

# ─── 2. 생성 응답 필드 검증 ──────────────────────────────────────────────────
print("\n[2] 생성 응답 필드 검증")
s, b = req("POST", "/api/users", {
    "emp_id": U5, "name": U5, "department": "QC팀", "role": "GENERAL"
}, token=master_token)
ok(f"{U5} 생성", s, b, [200, 201])
if s in (200, 201):
    ok("temp_password 포함", bool(b.get("temp_password")), True, True)
    ok("emp_id 포함", bool(b.get("emp_id")), True, True)

s, b = req("POST", "/api/users", {
    "emp_id": U6, "name": U6, "department": "QC팀", "role": "GENERAL"
}, token=master_token)
ok(f"{U6} 생성", s, b, [200, 201])

# ─── 3. 단건 조회 ────────────────────────────────────────────────────────────
print("\n[3] 사용자 단건 조회")
s, b = req("GET", f"/api/users/{U1}", token=master_token)
ok(f"{U1} 단건 조회 → 200", s, b, 200)
if s == 200:
    ok("emp_id 필드 존재", "emp_id" in b, True, True)
    ok("role 필드 존재", "role" in b, True, True)
    ok("department 필드 존재", "department" in b, True, True)
    ok("is_resigned 필드 존재", "is_resigned" in b, True, True)
    ok("is_vip 필드 존재", "is_vip" in b, True, True)

s, b = req("GET", f"/api/users/{U3}", token=master_token)
ok(f"{U3} is_vip=True 반영 확인", s, b, 200)
if s == 200:
    ok("is_vip=True", b.get("is_vip") == True, True, True)

# 존재하지 않는 사용자 → 404
s, b = req("GET", "/api/users/no_such_user_xyz_99", token=master_token)
ok("없는 사용자 조회 → 404", s, b, 404)

# ─── 4. 목록 조회 — 페이지네이션 ─────────────────────────────────────────────
print("\n[4] 목록 조회 — 페이지네이션")
s, b = req_qs("GET", "/api/users", {"skip": 0, "limit": 2}, token=master_token)
ok("skip=0, limit=2 → 200", s, b, 200)
if s == 200:
    ok("items 배열 존재", isinstance(b.get("items"), list), True, True)
    ok("limit=2 적용 (≤2개)", len(b.get("items", [])) <= 2, True, True)
    ok("total 필드 존재", "total" in b, True, True)

s, b = req_qs("GET", "/api/users", {"skip": 9999, "limit": 10}, token=master_token)
ok("skip=9999 → 200 (빈 배열)", s, b, 200)
if s == 200:
    ok("결과 0개", len(b.get("items", [])) == 0, True, True)

# ─── 5. 목록 조회 — 키워드 검색 ──────────────────────────────────────────────
print("\n[5] 목록 조회 — 키워드/필터")
s, b = req_qs("GET", "/api/users", {"keyword": "qc_usr"}, token=master_token)
ok("keyword=qc_usr 검색 → 200", s, b, 200)
if s == 200:
    ok("qc_usr 계정들 포함", len(b.get("items", [])) > 0, True, True)

s, b = req_qs("GET", "/api/users", {"role": "ADMIN"}, token=master_token)
ok("role=ADMIN 필터 → 200", s, b, 200)

s, b = req_qs("GET", "/api/users", {"role": "GENERAL"}, token=master_token)
ok("role=GENERAL 필터 → 200", s, b, 200)

s, b = req_qs("GET", "/api/users", {"status": "ACTIVE"}, token=master_token)
ok("status=ACTIVE 필터 → 200", s, b, 200)

s, b = req_qs("GET", "/api/users", {"status": "INACTIVE"}, token=master_token)
ok("status=INACTIVE 필터 → 200", s, b, 200)

s, b = req_qs("GET", "/api/users", {"first_login": "PENDING"}, token=master_token)
ok("first_login=PENDING 필터 → 200", s, b, 200)

s, b = req_qs("GET", "/api/users", {"sort_by": "emp_id", "sort_dir": "asc"}, token=master_token)
ok("sort_by=emp_id asc → 200", s, b, 200)

s, b = req_qs("GET", "/api/users", {"sort_by": "role", "sort_dir": "desc"}, token=master_token)
ok("sort_by=role desc → 200", s, b, 200)

# ─── 6. 프로필 수정 ──────────────────────────────────────────────────────────
print("\n[6] 프로필 수정")
s, b = req("PATCH", f"/api/users/{U1}", {
    "emp_id": U1, "name": U1, "department": "수정된팀",
    "division": "수정된부서", "email": "updated@qc.test",
    "role": "GENERAL", "is_vip": False
}, token=master_token)
ok(f"{U1} 프로필 수정 → 200", s, b, 200)
if s == 200:
    ok("department 수정 반영", b.get("department") == "수정된팀", True, True)

# emp_id 변경 (rename)
s, b = req("PATCH", f"/api/users/{U4}", {
    "emp_id": "qc_usr_renamed", "name": "qc_usr_renamed",
    "department": "QC팀", "role": "GENERAL", "is_vip": False
}, token=master_token)
ok(f"{U4} → qc_usr_renamed ID 변경 → 200", s, b, 200)
if s == 200:
    ok("새 emp_id 반영", b.get("emp_id") == "qc_usr_renamed", True, True)
    # 새 ID로 조회 가능 확인
    s2, b2 = req("GET", "/api/users/qc_usr_renamed", token=master_token)
    ok("변경된 ID로 조회 가능", s2, b2, 200)

# 중복 emp_id로 변경 시도 → 400
s, b = req("PATCH", f"/api/users/qc_usr_renamed", {
    "emp_id": U1, "name": U1,
    "department": "QC팀", "role": "GENERAL", "is_vip": False
}, token=master_token)
ok("중복 emp_id로 변경 시도 → 400", s, b, 400)

# 원복
req("PATCH", "/api/users/qc_usr_renamed", {
    "emp_id": U4, "name": U4,
    "department": "QC팀", "role": "GENERAL", "is_vip": False
}, token=master_token)

# ─── 7. 역할 변경 (PATCH /role) ──────────────────────────────────────────────
print("\n[7] 역할 변경")
s, b = req("PATCH", f"/api/users/{U1}/role", {"role": "ADMIN"}, token=master_token)
ok(f"{U1} → ADMIN 역할 변경 → 200", s, b, 200)
if s == 200:
    ok("role=ADMIN 반영", b.get("role") in ("ADMIN", "admin"), True, True)

# 다시 GENERAL로 원복
req("PATCH", f"/api/users/{U1}/role", {"role": "GENERAL"}, token=master_token)

# MASTER 변경 시도 (ADMIN이 시도) → 403
admin_token = login(U2, u2_temp_pw) if u2_temp_pw else None
if admin_token:
    s, b = req("PATCH", f"/api/users/{U1}/role", {"role": "MASTER"}, token=admin_token)
    ok("ADMIN이 역할 MASTER 변경 시도 → 403", s, b, 403)

    # 본인 역할 변경 시도 → 403
    s, b = req("PATCH", f"/api/users/{U2}/role", {"role": "MASTER"}, token=admin_token)
    ok("본인 역할 변경 시도 → 400 또는 403", s, b, [400, 403])

# ─── 8. 상태 변경 ────────────────────────────────────────────────────────────
print("\n[8] 상태 변경")
s, b = req("PATCH", f"/api/users/{U1}/status", {"is_resigned": True}, token=master_token)
ok(f"{U1} 비활성화 → 200", s, b, 200)
if s == 200:
    ok("is_resigned=True 반영", b.get("is_resigned") == True, True, True)

s, b = req("PATCH", f"/api/users/{U1}/status", {"is_resigned": False}, token=master_token)
ok(f"{U1} 재활성화 → 200", s, b, 200)
if s == 200:
    ok("is_resigned=False 반영", b.get("is_resigned") == False, True, True)

# 자기 자신 비활성화 차단
s, b = req("PATCH", "/api/users/master/status", {"is_resigned": True}, token=master_token)
ok("master 자신 비활성화 차단 → 400", s, b, 400)

# ─── 9. 임시 비밀번호 재발급 ─────────────────────────────────────────────────
print("\n[9] 임시 비밀번호 재발급")
# ADMIN 계정 → 폰 ID 제약 없이 가능
s, b = req("POST", f"/api/users/{U2}/issue-temp-password", token=master_token)
ok(f"{U2} (ADMIN) 임시 비밀번호 재발급 → 200", s, b, 200)
if s == 200:
    ok("temp_password 포함", bool(b.get("temp_password")), True, True)

# GENERAL 계정 비폰ID → 400
s, b = req("POST", f"/api/users/{U1}/issue-temp-password", token=master_token)
ok(f"{U1} (GENERAL, 비폰ID) → 400", s, b, 400)

# master → 403
s, b = req("POST", "/api/users/master/issue-temp-password", token=master_token)
ok("master 임시 비밀번호 재발급 → 403", s, b, 403)

# ─── 10. 감사 로그 조회 ──────────────────────────────────────────────────────
print("\n[10] 감사 로그 조회")
s, b = req("GET", f"/api/users/{U1}/audit", token=master_token)
ok(f"{U1} 감사 로그 → 200", s, b, 200)
if s == 200:
    ok("items 배열 존재", isinstance(b.get("items"), list), True, True)
    # 이 시점에 create, status 변경 등 로그 있어야 함
    ok("감사 로그 1건 이상", len(b.get("items", [])) > 0, True, True)
    if b.get("items"):
        first = b["items"][0]
        ok("actor_emp_id 필드", "actor_emp_id" in first, True, True)
        ok("action 필드", "action" in first, True, True)

# 없는 사용자 감사 로그 → 200(빈 목록) 또는 404
s, b = req("GET", "/api/users/no_such_user_xyz/audit", token=master_token)
ok("없는 사용자 감사 로그 → 200/404", s, b, [200, 404])

# ─── 11. 단건 삭제 ───────────────────────────────────────────────────────────
print("\n[11] 단건 삭제")
# 자기 자신 삭제 차단
s, b = req("DELETE", "/api/users/master", token=master_token)
ok("master 자기 자신 삭제 차단 → 400", s, b, 400)

# 없는 사용자 삭제 → 404
s, b = req("DELETE", "/api/users/nobody_xyz_99", token=master_token)
ok("없는 사용자 삭제 → 404", s, b, 404)

# U3 삭제
s, b = req("DELETE", f"/api/users/{U3}", token=master_token)
ok(f"{U3} 삭제 → 200 또는 204", s, b, [200, 204])

# 삭제 후 조회 → 404
s, b = req("GET", f"/api/users/{U3}", token=master_token)
ok(f"{U3} 삭제 후 조회 → 404", s, b, 404)

# ─── 12. 일괄 삭제 (bulk-delete) ─────────────────────────────────────────────
print("\n[12] 일괄 삭제")
s, b = req("POST", "/api/users/bulk-delete", {"emp_ids": [U5, U6]}, token=master_token)
ok(f"{U5}, {U6} bulk-delete → 200", s, b, 200)
if s == 200:
    ok("deleted 배열 포함", isinstance(b.get("deleted"), list), True, True)
    ok("count=2", b.get("count") == 2, True, True)

# 빈 목록 → 400
s, b = req("POST", "/api/users/bulk-delete", {"emp_ids": []}, token=master_token)
ok("bulk-delete 빈 목록 → 400", s, b, 400)

# 자기 자신 포함 시 차단
s, b = req("POST", "/api/users/bulk-delete", {"emp_ids": ["master", U1]}, token=master_token)
ok("bulk-delete 자기 자신 포함 → 400", s, b, 400)

# ADMIN이 bulk-delete 시도 → 403
if admin_token:
    s, b = req("POST", "/api/users/bulk-delete", {"emp_ids": [U1]}, token=admin_token)
    ok("ADMIN bulk-delete 시도 → 403", s, b, 403)

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
