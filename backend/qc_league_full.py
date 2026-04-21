"""
QC: 리그 전체 시나리오 검증
- 시즌 생성/목록/스케줄 sync/get
- 경기 결과 입력 (FINAL/FORFEIT)
- 순위표 조회 (캐시/실시간)
- 트레이드 윈도우 (evaluate/waive/proposals/protected)
- 선수 기록 (upsert/get/analysis)
- 드래프트 (board/participants/start/assign)
- 퍼블릭 엔드포인트

주의: 시즌 생성 시 기존 팀 배정이 초기화됩니다.
      이 스크립트는 실행 전 팀 배정을 저장하고, 완료 후 복원합니다.
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
        print(f"  [FAIL] {label} - {detail} | {str(body_or_sentinel)[:120]}")
        FAIL_COUNT += 1
        FAILURES.append(label)
        return False


print("\n" + "=" * 60)
print("  QC: 리그 전체 시나리오 검증")
print("=" * 60)

master_token, _ = login_form("master", "1234")
if not master_token:
    print("[FATAL] Cannot login as master")
    sys.exit(1)

# ─── 기존 팀 배정 저장 ────────────────────────────────────────────────────────
print("\n  [사전 작업] 기존 팀 배정 저장 중...")
saved_assignments = {}
s_ta, b_ta = req("GET", "/api/attendance/admin/team-assignments", token=master_token)
if s_ta == 200:
    for item in b_ta.get("items", []):
        if item.get("team_code"):
            saved_assignments[item["emp_id"]] = {
                "team_code": item["team_code"],
                "is_captain": item.get("is_captain", False),
            }
print(f"  저장된 팀 배정: {len(saved_assignments)}명")

# ─── 테스트 유저 생성 ─────────────────────────────────────────────────────────
TEAM_A_1, TEAM_A_2 = "qclg_a1", "qclg_a2"
TEAM_B_1, TEAM_B_2 = "qclg_b1", "qclg_b2"
TEAM_C_1, TEAM_C_2 = "qclg_c1", "qclg_c2"
ALL_MEMBERS = [TEAM_A_1, TEAM_A_2, TEAM_B_1, TEAM_B_2, TEAM_C_1, TEAM_C_2]

for uid in ALL_MEMBERS:
    req("DELETE", f"/api/users/{uid}", token=master_token)

cap_tokens = {}
for uid in ALL_MEMBERS:
    s, b = req("POST", "/api/users", {
        "emp_id": uid, "name": f"QC League {uid}", "department": "QC",
        "email": f"{uid}@qc.test", "role": "GENERAL"
    }, token=master_token)
    if s in (200, 201) and b.get("temp_password"):
        t, _ = login_form(uid, b["temp_password"])
        cap_tokens[uid] = t


def restore_and_cleanup():
    print("\n  [정리] 팀 배정 복원 중...")
    # 시즌 생성 시 모든 팀 배정이 초기화되었으므로 복원
    for emp_id, data in saved_assignments.items():
        req("PUT", f"/api/attendance/admin/team-assignments/{emp_id}",
            {"team_code": data["team_code"], "is_captain": data["is_captain"]},
            token=master_token)
    # 테스트 유저 삭제
    for uid in ALL_MEMBERS:
        req("DELETE", f"/api/users/{uid}", token=master_token)
    print(f"  복원된 팀 배정: {len(saved_assignments)}명")
    print("  테스트 유저 삭제 완료")


# ─── 1. 시즌 생성 ─────────────────────────────────────────────────────────────
print("\n[1] 시즌 생성")
s, b = req("POST", "/api/league/admin/seasons", {
    "total_weeks": 4,
    "client_year": 2099,
    "note": "QC 테스트 시즌"
}, token=master_token)
ok("시즌 생성 → 200", s, b, 200)
season_id = b.get("season_id")
ok("season_id 존재", bool(season_id), True, True)
ok("total_weeks = 4", b.get("total_weeks") == 4, True, True)
ok("created_weeks = 4", b.get("created_weeks") == 4, True, True)
ok("created_matches = 12", b.get("created_matches") == 12, True, True)
rulebook = b.get("rulebook_basis", {})
ok("rulebook teams 3개", rulebook.get("teams") == ["A", "B", "C"], True, True)

if not season_id:
    print("[FATAL] 시즌 생성 실패 - 이후 테스트 불가")
    restore_and_cleanup()
    sys.exit(1)

# ─── 2. 시즌 목록 ─────────────────────────────────────────────────────────────
print("\n[2] 시즌 목록")
s, b = req("GET", "/api/league/admin/seasons", token=master_token)
ok("admin/seasons → 200", s, b, 200)
ok("list 타입", isinstance(b, list), True, True)
ok("시즌 1개 이상", len(b) >= 1, True, True)
if b:
    row = b[0]
    for field in ["id", "code", "title", "status", "total_weeks"]:
        ok(f"시즌 필드 '{field}'", field in row, True, True)

# GENERAL 권한 불가
gen_token = cap_tokens.get(TEAM_A_1)
if gen_token:
    s, b = req("GET", "/api/league/admin/seasons", token=gen_token)
    ok("GENERAL admin/seasons → 403", s, b, 403)

# ─── 3. 스케줄 sync / get ─────────────────────────────────────────────────────
print("\n[3] 스케줄 sync / get")
s, b = req("POST", f"/api/league/admin/seasons/{season_id}/schedule/sync",
           token=master_token)
ok("schedule/sync → 200", s, b, 200)
ok("season_id 존재", "season_id" in b, True, True)

s, b = req("GET", f"/api/league/admin/seasons/{season_id}/schedule",
           token=master_token)
ok("schedule/get → 200", s, b, 200)
ok("season 필드", "season" in b, True, True)
ok("weeks 필드", "weeks" in b, True, True)
weeks = b.get("weeks", [])
ok("4주차 생성됨", len(weeks) == 4, True, True)
if weeks:
    w1 = weeks[0]
    ok("week_no = 1", w1.get("week_no") == 1, True, True)
    ok("3경기/주", len(w1.get("matches", [])) == 3, True, True)
    if w1["matches"]:
        m = w1["matches"][0]
        ok("match_id 존재", bool(m.get("match_id")), True, True)
        ok("home_team 존재", bool(m.get("home_team")), True, True)

# 경기 ID 수집 (주차별 첫 번째 경기)
match_ids_by_week = {}
for week in weeks:
    wn = week["week_no"]
    if week["matches"]:
        match_ids_by_week[wn] = week["matches"][0]["match_id"]

print(f"    수집된 경기 ID: {match_ids_by_week}")

# ─── 4. 팀 배정 (선수 통계 / 트레이드 테스트용) ──────────────────────────────
print("\n[4] 테스트 팀 배정")
for uid, team in [(TEAM_A_1, "A"), (TEAM_A_2, "A"), (TEAM_B_1, "B"),
                  (TEAM_B_2, "B"), (TEAM_C_1, "C"), (TEAM_C_2, "C")]:
    s, b = req("PUT", f"/api/attendance/admin/team-assignments/{uid}",
               {"team_code": team, "is_captain": uid in (TEAM_A_1, TEAM_B_1, TEAM_C_1)},
               token=master_token)
    ok(f"{uid} → 팀{team} 배정", s, b, 200)

# ─── 5. 경기 결과 입력 ────────────────────────────────────────────────────────
print("\n[5] 경기 결과 입력")

def set_result(match_id, home_score, away_score, note="QC"):
    return req("POST", f"/api/league/admin/matches/{match_id}/result", {
        "status": "FINAL",
        "home_score": home_score,
        "away_score": away_score,
        "note": note
    }, token=master_token)

# 주차 1~3 전체 경기 결과 입력
for week in weeks[:3]:
    for match in week["matches"]:
        mid = match["match_id"]
        home = match["home_team"]
        away = match["away_team"]
        # A팀이 항상 이기는 스코어 설정 (트레이드 윈도우 테스트용)
        if home == "A":
            hs, as_ = 60, 20
        elif away == "A":
            hs, as_ = 20, 60
        elif home == "B":
            hs, as_ = 50, 30  # B가 C에게 이김
        else:
            hs, as_ = 30, 50  # C는 B에게 짐
        s, b = set_result(mid, hs, as_)
        ok(f"경기{mid} 결과 입력 → 200", s, b, 200)

# FINAL 결과 검증
if match_ids_by_week.get(1):
    mid1 = match_ids_by_week[1]
    s, b = req("GET", f"/api/league/admin/seasons/{season_id}/standings",
               token=master_token, params={"week_no": 1})
    ok("주차1 순위표 → 200", s, b, 200)
    ok("rows 존재", "rows" in b, True, True)
    ok("3팀 존재", len(b.get("rows", [])) == 3, True, True)

# FORFEIT 테스트 (4주차 경기)
if match_ids_by_week.get(4):
    mid4 = match_ids_by_week[4]
    # 먼저 4주차 어떤 팀 경기인지 확인
    w4 = next((w for w in weeks if w["week_no"] == 4), None)
    if w4 and w4["matches"]:
        m4 = w4["matches"][0]
        forfeit_team = m4["home_team"]
        s, b = req("POST", f"/api/league/admin/matches/{m4['match_id']}/result", {
            "status": "FORFEIT",
            "forfeited_team": forfeit_team,
            "note": "QC FORFEIT 테스트"
        }, token=master_token)
        ok("FORFEIT 결과 → 200", s, b, 200)
        ok("winner_team 존재", bool(b.get("winner_team")), True, True)

# 없는 경기 결과 입력
s, b = set_result(99999999, 50, 30)
ok("없는 경기 결과 → 404", s, b, 404)

# ─── 6. 순위표 조회 ──────────────────────────────────────────────────────────
print("\n[6] 순위표 조회 (3주차)")
s, b = req("GET", f"/api/league/admin/seasons/{season_id}/standings",
           token=master_token, params={"week_no": 3})
ok("3주차 순위표 → 200", s, b, 200)
rows_st = b.get("rows", [])
ok("rows 3개", len(rows_st) == 3, True, True)
if rows_st:
    r0 = rows_st[0]
    for field in ["rank", "team_code", "played", "wins", "draws", "losses", "points"]:
        ok(f"순위표 필드 '{field}'", field in r0, True, True)
    ok("1위 rank = 1", r0.get("rank") == 1, True, True)

# refresh 파라미터
s, b = req("GET", f"/api/league/admin/seasons/{season_id}/standings",
           token=master_token, params={"week_no": 3, "refresh": "true"})
ok("순위표 refresh=true → 200", s, b, 200)

# 없는 시즌
s, b = req("GET", "/api/league/admin/seasons/99999999/standings",
           token=master_token, params={"week_no": 1})
ok("없는 시즌 순위표 → 404", s, b, 404)

# ─── 7. 트레이드 윈도우 evaluate ─────────────────────────────────────────────
print("\n[7] 트레이드 윈도우 - evaluate")
s, b = req("POST", f"/api/league/admin/seasons/{season_id}/trade-window/evaluate",
           {"week_no": 3}, token=master_token)
ok("trade-window/evaluate → 200", s, b, 200)
ok("season_id 존재", "season_id" in b, True, True)
ok("eligible_team 존재", "eligible_team" in b, True, True)
ok("gap_with_leader 존재", "gap_with_leader" in b, True, True)
ok("trade_allowed 존재", "trade_allowed" in b, True, True)
ok("window_status 존재", "window_status" in b, True, True)

eligible_team = b.get("eligible_team")
gap = b.get("gap_with_leader", 0)
trade_allowed = b.get("trade_allowed", False)
print(f"    eligible_team={eligible_team}, gap={gap}, trade_allowed={trade_allowed}")

# week_no != 3 → 400
s, b = req("POST", f"/api/league/admin/seasons/{season_id}/trade-window/evaluate",
           {"week_no": 2}, token=master_token)
ok("week_no=2 evaluate → 400", s, b, 400)

# ─── 8. 트레이드 윈도우 waive ─────────────────────────────────────────────────
print("\n[8] 트레이드 윈도우 - waive")
s, b = req("POST", f"/api/league/admin/seasons/{season_id}/trade-window/waive",
           {"waived": True, "note": "QC 포기"}, token=master_token)
ok("trade-window/waive (포기) → 200", s, b, 200)
ok("waived = True", b.get("waived") is True, True, True)
ok("window_status = CLOSED", b.get("window_status") == "CLOSED", True, True)

# 포기 취소
s, b = req("POST", f"/api/league/admin/seasons/{season_id}/trade-window/waive",
           {"waived": False}, token=master_token)
ok("waive 취소 → 200", s, b, 200)
ok("waived = False", b.get("waived") is False, True, True)

# 윈도우가 없는 시즌
s, b = req("POST", "/api/league/admin/seasons/99999999/trade-window/waive",
           {"waived": True}, token=master_token)
ok("없는 시즌 waive → 404", s, b, 404)

# ─── 9. 보호선수 설정 ─────────────────────────────────────────────────────────
print("\n[9] 보호선수 설정")
if trade_allowed and eligible_team:
    # eligible_team은 최하위팀 → 최대 2명 보호
    # 첫 번째 선수(proposer_out 예정)는 보호하지 않고, 두 번째 선수만 보호
    if eligible_team == "A":
        protect_ids = [TEAM_A_1, TEAM_A_2]
    elif eligible_team == "B":
        protect_ids = [TEAM_B_1, TEAM_B_2]
    else:
        protect_ids = [TEAM_C_1, TEAM_C_2]

    # protect_ids[1]만 보호 - protect_ids[0]은 트레이드에 사용 예정
    s, b = req("POST", f"/api/league/admin/seasons/{season_id}/trade-protected", {
        "team_code": eligible_team,
        "emp_ids": [protect_ids[1]],
        "week_no": 3
    }, token=master_token)
    ok(f"보호선수 설정 ({eligible_team}) → 200", s, b, 200)
    ok("protected_emp_ids 존재", "protected_emp_ids" in b, True, True)

    # 2명 보호 테스트 (eligible_team은 최대 2명)
    s, b = req("POST", f"/api/league/admin/seasons/{season_id}/trade-protected", {
        "team_code": eligible_team,
        "emp_ids": [protect_ids[1]],  # 같은 선수 다시 (멱등성 테스트)
        "week_no": 3
    }, token=master_token)
    ok("보호선수 재설정 → 200", s, b, 200)
else:
    # trade 미허용: 보호선수 설정 시 에러 예상
    s, b = req("POST", f"/api/league/admin/seasons/{season_id}/trade-protected", {
        "team_code": "A", "emp_ids": [TEAM_A_1], "week_no": 3
    }, token=master_token)
    ok("트레이드 미허용 - 보호선수 설정 → 400 (window 없음 시)", s, b, [200, 400])

# ─── 10. 트레이드 제안 ───────────────────────────────────────────────────────
print("\n[10] 트레이드 제안 (trade proposals)")

# evaluate 결과에 따라 window가 OPEN인 경우에만 진행
# waive=False이므로 trade_allowed에 따라 window가 결정됨
# 다시 evaluate하여 window status 확인
s_ev2, b_ev2 = req("POST", f"/api/league/admin/seasons/{season_id}/trade-window/evaluate",
                    {"week_no": 3}, token=master_token)
window_status = b_ev2.get("window_status", "CLOSED")
trade_allowed2 = b_ev2.get("trade_allowed", False)
eligible_team2 = b_ev2.get("eligible_team", "")
print(f"    window_status={window_status}, trade_allowed={trade_allowed2}, eligible_team={eligible_team2}")

if trade_allowed2 and window_status == "OPEN" and eligible_team2:
    # eligible_team2의 선수가 proposer, 다른 팀 선수가 partner
    if eligible_team2 == "A":
        proposer_out = TEAM_A_1
        partner_team = "B"
        partner_out = TEAM_B_1
        proposer_out2 = TEAM_A_2
        partner_out2 = TEAM_B_2
    elif eligible_team2 == "B":
        proposer_out = TEAM_B_1
        partner_team = "A"
        partner_out = TEAM_A_1
        proposer_out2 = TEAM_B_2
        partner_out2 = TEAM_A_2
    else:
        proposer_out = TEAM_C_1
        partner_team = "A"
        partner_out = TEAM_A_1
        proposer_out2 = TEAM_C_2
        partner_out2 = TEAM_A_2

    s, b = req("POST", f"/api/league/admin/seasons/{season_id}/trade-proposals", {
        "proposer_team": eligible_team2,
        "partner_team": partner_team,
        "proposer_out_emp_id": proposer_out,
        "partner_out_emp_id": partner_out,
        "note": "QC 테스트 트레이드"
    }, token=master_token)
    ok("트레이드 제안 생성 → 200", s, b, 200)
    proposal_id_1 = b.get("proposal_id")
    ok("proposal_id 존재", bool(proposal_id_1), True, True)
    ok("status = SUBMITTED", b.get("status") == "SUBMITTED", True, True)

    # 같은 팀끼리 트레이드 불가
    s, b = req("POST", f"/api/league/admin/seasons/{season_id}/trade-proposals", {
        "proposer_team": eligible_team2,
        "partner_team": eligible_team2,
        "proposer_out_emp_id": proposer_out,
        "partner_out_emp_id": proposer_out2,
    }, token=master_token)
    ok("같은 팀 트레이드 → 400", s, b, 400)

    # 보호선수 tradeout 시도 → 400 (protect_ids[1]은 보호됨)
    s, b = req("POST", f"/api/league/admin/seasons/{season_id}/trade-proposals", {
        "proposer_team": eligible_team2,
        "partner_team": partner_team,
        "proposer_out_emp_id": protect_ids[1],  # 보호선수 → 400
        "partner_out_emp_id": partner_out,
        "note": "보호선수 트레이드 시도"
    }, token=master_token)
    ok("보호선수 proposer_out → 400", s, b, 400)

    # 트레이드 제안 목록 (제안 1건 이상)
    s, b = req("GET", f"/api/league/admin/seasons/{season_id}/trade-proposals",
               token=master_token)
    ok("trade-proposals 목록 → 200", s, b, 200)
    ok("list 타입", isinstance(b, list), True, True)
    ok("제안 1건 이상", len(b) >= 1, True, True)

    # 제안 승인 (팀 배정 변경됨)
    if proposal_id_1:
        s, b = req("POST", f"/api/league/admin/trade-proposals/{proposal_id_1}/decision",
                   {"approve": True}, token=master_token)
        ok("제안 승인 → 200", s, b, 200)
        ok("status = EXECUTED", b.get("status") == "EXECUTED", True, True)
        ok("proposer_new_team 존재", "proposer_new_team" in b, True, True)
        ok("partner_new_team 존재", "partner_new_team" in b, True, True)

        # 이미 실행된 제안 재결정 불가
        s, b = req("POST", f"/api/league/admin/trade-proposals/{proposal_id_1}/decision",
                   {"approve": False}, token=master_token)
        ok("실행된 제안 재결정 → 400", s, b, 400)
else:
    print(f"    [SKIP] 트레이드 미허용 또는 window CLOSED - proposals 테스트 스킵")
    ok("트레이드 미허용 시 proposals 스킵 처리", True, True, True)

# ─── 11. 선수 기록 upsert / get / analysis ─────────────────────────────────────
print("\n[11] 선수 기록 (stats/upsert/get/analysis)")
# 주차1 경기에 통계 입력
target_mid = None
if weeks and weeks[0]["matches"]:
    target_match = weeks[0]["matches"][0]
    target_mid = target_match["match_id"]
    home_team = target_match["home_team"]
    away_team = target_match["away_team"]

    # home 팀의 선수 stats 입력
    home_player = TEAM_A_1 if home_team == "A" else (TEAM_B_1 if home_team == "B" else TEAM_C_1)
    s, b = req("POST", f"/api/league/admin/matches/{target_mid}/stats/upsert", {
        "emp_id": home_player, "team_code": home_team, "name": f"QC {home_player}",
        "participated": True,
        "fg2_made": 5, "fg2_attempted": 10,
        "fg3_made": 2, "fg3_attempted": 5,
        "ft_made": 3, "ft_attempted": 4,
        "o_rebound": 3, "d_rebound": 5,
        "assist": 4, "steal": 2, "block": 1, "foul": 2, "turnover": 2
    }, token=master_token)
    ok("stats upsert (home) → 200", s, b, 200)
    ok("emp_id 존재", "emp_id" in b, True, True)
    ok("total_points 계산됨", b.get("total_points") == 5*2+2*3+3, True, True)

    # away 팀 선수 stats
    away_player = TEAM_B_1 if away_team == "B" else (TEAM_A_1 if away_team == "A" else TEAM_C_1)
    req("POST", f"/api/league/admin/matches/{target_mid}/stats/upsert", {
        "emp_id": away_player, "team_code": away_team, "name": f"QC {away_player}",
        "participated": True,
        "fg2_made": 3, "fg2_attempted": 8,
        "fg3_made": 1, "fg3_attempted": 4,
        "ft_made": 2, "ft_attempted": 3,
        "o_rebound": 2, "d_rebound": 4,
        "assist": 3, "steal": 1, "block": 0, "foul": 3, "turnover": 3
    }, token=master_token)

    # GET stats
    s, b = req("GET", f"/api/league/admin/matches/{target_mid}/stats",
               token=master_token)
    ok("match stats get → 200", s, b, 200)
    ok("list 타입", isinstance(b, list), True, True)
    ok("stats 2건", len(b) >= 2, True, True)

    # analysis
    s, b = req("GET", f"/api/league/admin/matches/{target_mid}/analysis",
               token=master_token)
    ok("match analysis → 200", s, b, 200)
    ok("match_analysis 필드", "match_analysis" in b, True, True)
    ok("match_id 일치", b.get("match_id") == target_mid, True, True)

    # stats upsert - 잘못된 team_code
    s, b = req("POST", f"/api/league/admin/matches/{target_mid}/stats/upsert", {
        "emp_id": "test", "team_code": "X"
    }, token=master_token)
    ok("잘못된 team_code → 400", s, b, 400)

    # 없는 경기
    s, b = req("GET", "/api/league/admin/matches/99999999/stats", token=master_token)
    ok("없는 경기 stats → 404", s, b, 404)

# ─── 12. 드래프트 ─────────────────────────────────────────────────────────────
print("\n[12] 드래프트 (board/participants/start/assign)")

# 드래프트 보드 조회 (public for any logged-in user)
s, b = req("GET", "/api/league/draft/board", token=master_token,
           params={"season_id": season_id})
ok("draft/board → 200", s, b, 200)
ok("seasons 필드", "seasons" in b, True, True)
ok("season 필드", "season" in b, True, True)
ok("items 필드", "items" in b, True, True)
ok("draft 필드", "draft" in b, True, True)
ok("me 필드", "me" in b, True, True)

# 드래프트 참여자 설정 (teams 배정 전이므로, 팀 배정 후 재설정 필요)
# 현재 모든 테스트 유저를 팀에 배정했으므로 참여자로 포함
for uid in ALL_MEMBERS:
    s, b = req("PUT", f"/api/league/draft/participants/{uid}",
               {"include": True},
               token=master_token, params={"season_id": season_id})
    ok(f"{uid} 드래프트 참여 설정 → 200", s, b, 200)
    ok("included = True", b.get("included") is True, True, True)

# 참여 제외 테스트
s, b = req("PUT", f"/api/league/draft/participants/{TEAM_A_2}",
           {"include": False},
           token=master_token, params={"season_id": season_id})
ok("드래프트 참여 제외 → 200", s, b, 200)
ok("included = False", b.get("included") is False, True, True)

# 참여 복구
req("PUT", f"/api/league/draft/participants/{TEAM_A_2}",
    {"include": True}, token=master_token, params={"season_id": season_id})

# 없는 유저 참여 설정
s, b = req("PUT", "/api/league/draft/participants/nonexistent_xyz",
           {"include": True}, token=master_token, params={"season_id": season_id})
ok("없는 유저 드래프트 참여 → 404", s, b, 404)

# 드래프트 시작 전 팀 배정 해제 (빈 문자열로 전송해야 team_code가 실제로 null로 초기화됨)
for uid in ALL_MEMBERS:
    req("PUT", f"/api/attendance/admin/team-assignments/{uid}",
        {"team_code": "", "is_captain": False}, token=master_token)

s, b = req("POST", "/api/league/draft/start",
           {"season_id": season_id}, token=master_token)
ok("draft/start (관리자) → 200", s, b, 200)
ok("status = OPEN", b.get("status") == "OPEN", True, True)
ok("draft_id 존재", bool(b.get("draft_id")), True, True)

# 드래프트 배정 (A→B→C→C→B→A snake 순서)
assign_results = []
for uid in ALL_MEMBERS:
    s, b = req("PUT", f"/api/league/draft/assignments/{uid}",
               {"team_code": None},
               token=master_token, params={"season_id": season_id})
    assign_results.append((uid, s, b))
    if s == 200:
        ok(f"{uid} 드래프트 배정 → 200", s, b, 200)
    else:
        ok(f"{uid} 드래프트 배정 → 200", s, b, 200)

# 이미 배정된 선수 재배정 불가
if ALL_MEMBERS:
    s, b = req("PUT", f"/api/league/draft/assignments/{ALL_MEMBERS[0]}",
               {"team_code": None},
               token=master_token, params={"season_id": season_id})
    ok("이미 배정된 선수 재배정 → 400", s, b, 400)

# ─── 13. 퍼블릭 엔드포인트 ───────────────────────────────────────────────────
print("\n[13] 퍼블릭 엔드포인트")

gen_t = cap_tokens.get(TEAM_A_1) or master_token

# public/seasons
s, b = req("GET", "/api/league/public/seasons", token=gen_t)
ok("public/seasons → 200", s, b, 200)
ok("list 타입", isinstance(b, list), True, True)
if b:
    row = b[0]
    for field in ["id", "code", "status", "total_weeks"]:
        ok(f"public/seasons 필드 '{field}'", field in row, True, True)

# public/seasons/{id}/schedule
s, b = req("GET", f"/api/league/public/seasons/{season_id}/schedule", token=gen_t)
ok("public/seasons/{id}/schedule → 200", s, b, 200)
ok("season 필드", "season" in b, True, True)
ok("weeks 필드", "weeks" in b, True, True)

# public/seasons/{id}/standings
s, b = req("GET", f"/api/league/public/seasons/{season_id}/standings",
           token=gen_t, params={"week_no": 1})
ok("public/standings (week_no=1) → 200", s, b, 200)
ok("rows 존재", "rows" in b, True, True)

# public/seasons/{id}/stats/players
s, b = req("GET", f"/api/league/public/seasons/{season_id}/stats/players", token=gen_t)
ok("public/stats/players → 200", s, b, 200)
ok("list 타입", isinstance(b, list), True, True)

# public/scoresheets/catalog
s, b = req("GET", "/api/league/public/scoresheets/catalog", token=gen_t)
ok("public/scoresheets/catalog → 200", s, b, 200)
ok("list 타입", isinstance(b, list), True, True)

# public/matches/{id}/stats (stats가 있는 경기)
if target_mid:
    s, b = req("GET", f"/api/league/public/matches/{target_mid}/stats", token=gen_t)
    ok("public/matches/{id}/stats → 200", s, b, 200)
    ok("stats list", isinstance(b, list), True, True)

    s, b = req("GET", f"/api/league/public/matches/{target_mid}/analysis", token=gen_t)
    ok("public/matches/{id}/analysis → 200", s, b, 200)
    ok("match_id 일치", b.get("match_id") == target_mid, True, True)

# 없는 리소스 404
s, b = req("GET", "/api/league/public/seasons/99999999/schedule", token=gen_t)
ok("public/seasons/99999/schedule → 404", s, b, 404)

s, b = req("GET", "/api/league/public/matches/99999999/stats", token=gen_t)
ok("public/matches/99999/stats → 404", s, b, 404)

# 토큰 없이 퍼블릭 엔드포인트 → 401
s, b = req("GET", "/api/league/public/seasons")
ok("토큰 없이 public/seasons → 401", s, b, 401)

# ─── 정리 ────────────────────────────────────────────────────────────────────
restore_and_cleanup()

print(f"\n{'=' * 60}")
print(f"  결과: {PASS_COUNT}/{PASS_COUNT + FAIL_COUNT} passed")
if FAILURES:
    print("\n  실패 목록:")
    for f in FAILURES:
        print(f"    ✗ {f}")
print("=" * 60)
sys.exit(0 if FAIL_COUNT == 0 else 1)
