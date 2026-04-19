"""
QC: 통합 E2E 시나리오
- 신규 멤버 온보딩 전체 흐름
- 시즌 내 출석 + 회비 동시 관리
- 공지사항 CRUD 전체 흐름
- 리그 시즌 생성 및 조회
- 멀티 멤버 동시 투표 시나리오
"""
import urllib.request, urllib.error, urllib.parse, json, sys
from datetime import date, datetime, timedelta

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


def req_qs(method, path, query_params=None, token=None):
    """GET request with properly URL-encoded query parameters."""
    if query_params:
        qs = urllib.parse.urlencode(query_params)
        path = f"{path}?{qs}"
    return req(method, path, token=token)


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


def future_dt(hours=1):
    dt = datetime.now() + timedelta(hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


print("\n" + "=" * 60)
print("  QC: 통합 E2E 시나리오")
print("=" * 60)

admin_token = login("master", "1234")
if not admin_token:
    print("[FATAL] Cannot login as master")
    sys.exit(1)

# 테스트에 사용할 멤버 IDs
MEMBERS = ["qc_int_m1", "qc_int_m2", "qc_int_m3"]


def cleanup():
    for uid in MEMBERS:
        req("DELETE", f"/api/users/{uid}", token=admin_token)


cleanup()

# ─── 시나리오 1: 신규 멤버 온보딩 전체 흐름 ─────────────────────────────────
print("\n[시나리오 1] 신규 멤버 온보딩")

member_tokens = {}
for i, uid in enumerate(MEMBERS):
    s, b = req("POST", "/api/users", {
        "emp_id": uid,
        "name": f"Integration Member {i+1}",
        "department": "QC",
        "email": f"{uid}@qc.test",
        "role": "GENERAL"
    }, token=admin_token)
    ok(f"{uid} 계정 생성 → 200/201", s, b, [200, 201])

    if s in (200, 201):
        temp_pw = b.get("temp_password")
        if temp_pw:
            # 임시 비밀번호로 로그인
            s3, b3 = req("POST", "/api/auth/login",
                         form_data={"username": uid, "password": temp_pw})
            ok(f"{uid} 최초 로그인 성공 → 200", s3, b3, 200)
            token = b3.get("access_token")

            # is_first_login 플래그 확인
            is_first = b3.get("is_first_login")
            ok(f"{uid} is_first_login=True", is_first, True, True)

            if token:
                # 비밀번호 변경
                new_pw = f"Int@Pass{i+1}!"
                s4, b4 = req("POST", "/api/auth/change-password", {
                    "current_password": temp_pw,
                    "new_password": new_pw
                }, token=token)
                ok(f"{uid} 비밀번호 변경 → 200", s4, b4, 200)

                # 새 비밀번호로 재로그인
                final_token = login(uid, new_pw)
                ok(f"{uid} 새 비밀번호로 재로그인 성공", final_token is not None, True, True)
                member_tokens[uid] = final_token

# ─── 시나리오 2: 출석 이벤트 생성 + 멀티 멤버 투표 ─────────────────────────
print("\n[시나리오 2] 멀티 멤버 출석 투표")

event_date = (date.today() + timedelta(days=7)).isoformat()
s, b = req("POST", "/api/attendance/events", {
    "title": "통합테스트 출석 이벤트",
    "event_date": event_date,
    "vote_type": "REST",
    "vote_open_at": (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"),
    "vote_close_at": (datetime.now() + timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%S"),
}, token=admin_token)
ok("출석 이벤트 생성 → 200/201", s, b, [200, 201])
att_event_id = b.get("id") or b.get("event_id")

if att_event_id:
    votes = {
        MEMBERS[0]: "ATTEND",
        MEMBERS[1]: "ABSENT",
        MEMBERS[2]: "ATTEND",
    }
    voted_count = 0
    for uid, vote_val in votes.items():
        t = member_tokens.get(uid)
        if t:
            s, b = req("POST", f"/api/attendance/events/{att_event_id}/vote",
                       {"response": vote_val}, token=t)
            if ok(f"{uid} {vote_val} 투표 → 200/201", s, b, [200, 201]):
                if vote_val == "ATTEND":
                    voted_count += 1

    # 투표 집계 확인
    s, b = req("GET", f"/api/attendance/admin/events/{att_event_id}/vote-detail",
               token=admin_token)
    ok("관리자 투표 집계 조회 → 200", s, b, 200)
    if s == 200 and voted_count > 0:
        attend_count = b.get("event", {}).get("counts", {}).get("ATTEND", 0)
        ok(f"attend_count >= {voted_count}", attend_count >= voted_count, True, True)

    # 멤버 본인 요약 확인
    t0 = member_tokens.get(MEMBERS[0])
    if t0:
        s, b = req("GET", "/api/attendance/me/summary", token=t0)
        ok("멤버 본인 출석 요약 → 200", s, b, 200)

# ─── 시나리오 3: 회비 관리 E2E ───────────────────────────────────────────────
print("\n[시나리오 3] 회비 관리 E2E")

year_month = f"{date.today().year}-{date.today().month:02d}"

for uid in MEMBERS[:2]:
    s, b = req("POST", f"/api/fees/admin/members/{uid}/mark-paid", {
        "year_month": year_month,
        "paid_amount": 30000,
        "note": "통합테스트 납부"
    }, token=admin_token)
    ok(f"{uid} 회비 납부 기록 → 200/201", s, b, [200, 201])

# 납부 후 이력 각 멤버 확인
for uid in MEMBERS[:2]:
    t = member_tokens.get(uid)
    if t:
        s, b = req("GET", "/api/fees/me/history", token=t)
        ok(f"{uid} 납부 이력 조회 → 200", s, b, 200)
        if s == 200:
            items = b.get("items", b if isinstance(b, list) else [])
            ok(f"{uid} 납부 이력 존재", len(items) > 0, True, True)

# 요약에서 납부 현황 반영 확인
s, b = req("GET", "/api/fees/admin/summary", token=admin_token)
ok("관리자 회비 요약 → 200", s, b, 200)

s, b = req("GET", "/api/fees/admin/matrix", token=admin_token)
ok("회비 매트릭스 → 200", s, b, 200)

# 미납 멤버 체크
s, b = req("GET", "/api/fees/admin/unpaid/check", token=admin_token)
ok("미납 체크 → 200", s, b, 200)

# ─── 시나리오 4: 공지사항 CRUD 전체 흐름 ────────────────────────────────────
print("\n[시나리오 4] 공지사항 CRUD 전체 흐름")

# 생성
s, b = req("POST", "/api/notices", {
    "title": "통합테스트 공지사항",
    "body": "이것은 통합 테스트용 공지입니다.",
    "is_pinned": True
}, token=admin_token)
ok("공지사항 생성 → 201", s, b, [200, 201])
notice_id = b.get("id") if s in (200, 201) else None

# 목록 조회 (일반 멤버도 가능)
t0 = member_tokens.get(MEMBERS[0])
if t0:
    s, b = req("GET", "/api/notices", token=t0)
    ok("멤버 공지사항 목록 조회 → 200", s, b, 200)
    if s == 200:
        items = b.get("items", [])
        found = any(n.get("id") == notice_id for n in items) if notice_id else False
        ok("생성된 공지사항이 목록에 존재", found, True, True)

# 키워드 검색 (URL-encoded)
s, b = req_qs("GET", "/api/notices", {"keyword": "통합테스트"}, token=admin_token)
ok("공지사항 키워드 검색 → 200", s, b, 200)

# 수정 (관리자만 가능)
if notice_id:
    s, b = req("PATCH", f"/api/notices/{notice_id}", {
        "title": "통합테스트 공지사항 (수정됨)",
        "body": "수정된 공지 내용입니다.",
        "is_pinned": False
    }, token=admin_token)
    ok("공지사항 수정 → 200", s, b, 200)

    # 일반 멤버 수정 시도 차단
    if t0:
        s, b = req("PATCH", f"/api/notices/{notice_id}", {
            "title": "멤버가 수정 시도",
            "body": "차단되어야 함",
            "is_pinned": False
        }, token=t0)
        ok("멤버 공지사항 수정 차단 → 403", s, b, 403)

    # 삭제
    s, b = req("DELETE", f"/api/notices/{notice_id}", token=admin_token)
    ok("공지사항 삭제 → 200/204", s, b, [200, 204])

    # 삭제 후 조회 확인
    s, b = req_qs("GET", "/api/notices", {"keyword": "통합테스트"}, token=admin_token)
    if s == 200:
        items = b.get("items", [])
        still_exists = any(n.get("id") == notice_id for n in items)
        ok("삭제 후 목록에서 제거됨", not still_exists, True, True)

# ─── 시나리오 5: 리그 시즌 생성 및 조회 ─────────────────────────────────────
print("\n[시나리오 5] 리그 시즌 관리")

s, b = req("POST", "/api/league/admin/seasons", {
    "total_weeks": 8,
    "client_year": date.today().year,
    "note": "통합테스트 시즌"
}, token=admin_token)
ok("리그 시즌 생성 → 200/201", s, b, [200, 201])

s, b = req("GET", "/api/league/admin/seasons", token=admin_token)
ok("리그 시즌 목록 → 200", s, b, 200)

# 일반 멤버는 관리자 시즌 목록 접근 불가
if t0:
    s, b = req("GET", "/api/league/admin/seasons", token=t0)
    ok("멤버 리그 시즌 목록 접근 차단 → 403", s, b, 403)

# ─── 시나리오 6: 대시보드 ────────────────────────────────────────────────────
print("\n[시나리오 6] 대시보드 접근")

s, b = req("GET", "/api/dashboard/admin-stats", token=admin_token)
ok("관리자 대시보드 통계 → 200", s, b, 200)

if t0:
    s, b = req("GET", "/api/dashboard/admin-stats", token=t0)
    ok("멤버 대시보드 통계 접근 차단 → 403", s, b, 403)

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
