"""
QC: 공지사항 전체 시나리오 검증
- GET /api/notices (페이지네이션, 키워드, 정렬)
- POST /api/notices (관리자 전용, 입력 검증)
- PATCH /api/notices/{id} (수정, 404)
- DELETE /api/notices/{id} (삭제, 404)
- 권한 검증: GENERAL 유저 쓰기 불가
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
print("  QC: 공지사항 전체 시나리오 검증")
print("=" * 60)

master_token, _ = login_form("master", "1234")
if not master_token:
    print("[FATAL] Cannot login as master")
    sys.exit(1)

# ─── 테스트 일반 유저 생성 ─────────────────────────────────────────────────────
GENERAL_ID = "qc_notice_general"
s, b = req("POST", "/api/users", {
    "emp_id": GENERAL_ID, "name": "QC Notice General", "department": "QC",
    "email": f"{GENERAL_ID}@qc.test", "role": "GENERAL"
}, token=master_token)
general_temp_pw = b.get("temp_password") if s in (200, 201) else None
general_token = None
if general_temp_pw:
    general_token, _ = login_form(GENERAL_ID, general_temp_pw)

CREATED_IDS = []


def cleanup():
    for nid in CREATED_IDS:
        req("DELETE", f"/api/notices/{nid}", token=master_token)
    req("DELETE", f"/api/users/{GENERAL_ID}", token=master_token)


# ─── 1. 초기 목록 조회 ────────────────────────────────────────────────────────
print("\n[1] 공지사항 목록 조회 (초기)")
s, b = req("GET", "/api/notices", token=master_token)
ok("목록 조회 → 200", s, b, 200)
ok("items 필드 존재", "items" in b, True, True)
ok("total 필드 존재", "total" in b, True, True)

# ─── 2. 공지 생성 (관리자) ────────────────────────────────────────────────────
print("\n[2] 공지사항 생성 (관리자)")
s, b = req("POST", "/api/notices", {
    "title": "QC Test 공지 1",
    "body": "QC 테스트 본문 내용입니다.",
    "is_pinned": False
}, token=master_token)
ok("공지 생성 → 201", s, b, 201)
notice1_id = b.get("id")
if notice1_id:
    CREATED_IDS.append(notice1_id)
ok("id 필드 존재", bool(notice1_id), True, True)
ok("title 일치", b.get("title") == "QC Test 공지 1", True, True)
ok("is_pinned = False", b.get("is_pinned") is False, True, True)
ok("created_by 존재", bool(b.get("created_by")), True, True)

# 핀 공지 생성
s, b = req("POST", "/api/notices", {
    "title": "QC 핀 공지",
    "body": "이것은 핀된 공지입니다.",
    "is_pinned": True
}, token=master_token)
ok("핀 공지 생성 → 201", s, b, 201)
pin_id = b.get("id")
if pin_id:
    CREATED_IDS.append(pin_id)
ok("is_pinned = True", b.get("is_pinned") is True, True, True)

# 두 번째 일반 공지 생성
s, b = req("POST", "/api/notices", {
    "title": "QC Test 공지 2",
    "body": "QC 두 번째 공지입니다.",
    "is_pinned": False
}, token=master_token)
notice2_id = b.get("id")
if notice2_id:
    CREATED_IDS.append(notice2_id)

# ─── 3. 입력 검증 ─────────────────────────────────────────────────────────────
print("\n[3] 입력 검증")
s, b = req("POST", "/api/notices", {"title": "", "body": "본문"}, token=master_token)
ok("제목 없음 → 400", s, b, 400)

s, b = req("POST", "/api/notices", {"title": "제목", "body": ""}, token=master_token)
ok("본문 없음 → 400", s, b, 400)

s, b = req("POST", "/api/notices", {"title": "  ", "body": "본문"}, token=master_token)
ok("공백만 있는 제목 → 400", s, b, 400)

# ─── 4. 권한 검증 ─────────────────────────────────────────────────────────────
print("\n[4] GENERAL 유저 권한 검증")
if general_token:
    s, b = req("POST", "/api/notices", {
        "title": "일반유저 공지", "body": "본문"
    }, token=general_token)
    ok("GENERAL → 공지 생성 403", s, b, 403)

    if notice1_id:
        s, b = req("PATCH", f"/api/notices/{notice1_id}", {
            "title": "수정", "body": "수정본문"
        }, token=general_token)
        ok("GENERAL → 공지 수정 403", s, b, 403)

        s, b = req("DELETE", f"/api/notices/{notice1_id}", token=general_token)
        ok("GENERAL → 공지 삭제 403", s, b, 403)

# 토큰 없음
s, b = req("GET", "/api/notices")
ok("토큰 없이 목록 조회 → 401", s, b, 401)

# ─── 5. 목록 정렬 — 핀 공지가 최상단 ─────────────────────────────────────────
print("\n[5] 정렬: 핀 공지 최상단")
s, b = req("GET", "/api/notices", token=master_token, params={"limit": 50})
ok("목록 조회 → 200", s, b, 200)
items = b.get("items", [])
if items:
    ok("첫 번째 항목이 핀 공지", items[0].get("is_pinned") is True, True, True)

# ─── 6. 키워드 검색 ───────────────────────────────────────────────────────────
print("\n[6] 키워드 검색")
s, b = req("GET", "/api/notices", token=master_token, params={"keyword": "QC Test"})
ok("키워드 검색 → 200", s, b, 200)
items_kw = b.get("items", [])
ok("QC Test 키워드 결과 > 0", len(items_kw) > 0, True, True)

s, b = req("GET", "/api/notices", token=master_token,
           params={"keyword": "존재하지않는키워드XYZ999"})
ok("없는 키워드 → 0건", b.get("total", -1) == 0, True, True)

# ─── 7. 정렬 방향 ─────────────────────────────────────────────────────────────
print("\n[7] 정렬 방향 (asc/desc)")
s_asc, b_asc = req("GET", "/api/notices", token=master_token, params={"sort_dir": "asc", "limit": 50})
s_desc, b_desc = req("GET", "/api/notices", token=master_token, params={"sort_dir": "desc", "limit": 50})
ok("asc 정렬 → 200", s_asc, b_asc, 200)
ok("desc 정렬 → 200", s_desc, b_desc, 200)

# ─── 8. 페이지네이션 ─────────────────────────────────────────────────────────
print("\n[8] 페이지네이션")
s, b = req("GET", "/api/notices", token=master_token, params={"skip": 0, "limit": 2})
ok("페이지 1 (limit=2) → 200", s, b, 200)
ok("items 수 ≤ 2", len(b.get("items", [])) <= 2, True, True)

s, b = req("GET", "/api/notices", token=master_token, params={"skip": 1, "limit": 2})
ok("페이지 2 (skip=1) → 200", s, b, 200)

# ─── 9. 공지 수정 ─────────────────────────────────────────────────────────────
print("\n[9] 공지 수정")
if notice1_id:
    s, b = req("PATCH", f"/api/notices/{notice1_id}", {
        "title": "QC 수정된 공지",
        "body": "수정된 본문입니다.",
        "is_pinned": True
    }, token=master_token)
    ok("공지 수정 → 200", s, b, 200)
    ok("제목 수정 확인", b.get("title") == "QC 수정된 공지", True, True)
    ok("is_pinned 수정 확인", b.get("is_pinned") is True, True, True)
    ok("updated_by 존재", bool(b.get("updated_by")), True, True)

    # 수정 입력 검증
    s, b = req("PATCH", f"/api/notices/{notice1_id}", {
        "title": "", "body": "본문"
    }, token=master_token)
    ok("수정 — 제목 없음 → 400", s, b, 400)

# ─── 10. 없는 공지 수정/삭제 ─────────────────────────────────────────────────
print("\n[10] 없는 공지 404")
s, b = req("PATCH", "/api/notices/99999999", {
    "title": "없음", "body": "없음"
}, token=master_token)
ok("없는 공지 수정 → 404", s, b, 404)

s, b = req("DELETE", "/api/notices/99999999", token=master_token)
ok("없는 공지 삭제 → 404", s, b, 404)

# ─── 11. 응답 필드 완전성 ─────────────────────────────────────────────────────
print("\n[11] 응답 필드 완전성")
if notice2_id:
    s, b = req("GET", "/api/notices", token=master_token, params={"keyword": "QC Test 공지 2"})
    items = b.get("items", [])
    if items:
        row = items[0]
        for field in ["id", "title", "body", "is_pinned", "created_by", "updated_by", "created_at"]:
            ok(f"필드 '{field}' 존재", field in row, True, True)

# ─── 12. 공지 삭제 ────────────────────────────────────────────────────────────
print("\n[12] 공지 삭제")
if notice2_id:
    s, b = req("DELETE", f"/api/notices/{notice2_id}", token=master_token)
    ok("공지 삭제 → 200", s, b, 200)
    CREATED_IDS.remove(notice2_id)

    s, b = req("GET", "/api/notices", token=master_token, params={"keyword": "QC Test 공지 2"})
    items_after = b.get("items", [])
    notice2_still_exists = any(i.get("id") == notice2_id for i in items_after)
    ok("삭제 후 해당 공지 없음", not notice2_still_exists, True, True)

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
