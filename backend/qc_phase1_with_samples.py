import json
import sys
import os
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("QC_BASE_URL", "http://127.0.0.1:8000")
ADMIN_ID = "master"
ADMIN_PW = "1234"
MEMBER_ID = "test001"


def request(method: str, path: str, data=None, headers=None):
    url = f"{BASE_URL}{path}"
    req_headers = dict(headers or {})
    body = None

    if data is not None:
        if req_headers.get("Content-Type") == "application/x-www-form-urlencoded":
            body = urllib.parse.urlencode(data).encode("utf-8")
        else:
            req_headers.setdefault("Content-Type", "application/json")
            body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = resp.read().decode("utf-8")
            return resp.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        payload = {"detail": raw}
        if raw:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                pass
        return exc.code, payload


def assert_ok(cond: bool, message: str):
    if not cond:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[OK] {message}")


def login(username: str, password: str):
    status, payload = request(
        "POST",
        "/api/auth/login",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert_ok(status == 200, f"login {username} returns 200")
    assert_ok("access_token" in payload, f"login {username} returns token")
    return payload


def run():
    print("=== Phase1 QC (with sample data) ===")

    admin = login(ADMIN_ID, ADMIN_PW)
    admin_h = {"Authorization": f"Bearer {admin['access_token']}"}

    status, events_payload = request("GET", "/api/attendance/events?skip=0&limit=200", headers=admin_h)
    assert_ok(status == 200, "admin can load attendance events")
    events = events_payload.get("items", [])
    assert_ok(isinstance(events, list) and len(events) >= 2, "at least two attendance sample events are visible")

    rest_event = next((e for e in events if "출석 투표 샘플" in str(e.get("title", "")) and e.get("vote_type") == "REST"), None)
    league_event = next((e for e in events if "리그전 출석 투표 샘플" in str(e.get("title", "")) and e.get("vote_type") == "LEAGUE"), None)

    assert_ok(rest_event is not None, "REST sample event exists")
    assert_ok(league_event is not None, "LEAGUE sample event exists")

    for e in (rest_event, league_event):
        eid = e["id"]
        st1, d1 = request("GET", f"/api/attendance/events/{eid}/vote-detail", headers=admin_h)
        st2, d2 = request("GET", f"/api/attendance/admin/events/{eid}/vote-detail", headers=admin_h)
        assert_ok(st1 == 200, f"public detail endpoint works for event_id={eid}")
        assert_ok(st2 == 200, f"admin detail endpoint works for event_id={eid}")
        assert_ok("voted" in d1 and "pending" in d1, f"detail payload includes voted/pending for event_id={eid}")
        assert_ok("summary" in d2, f"admin detail payload includes summary for event_id={eid}")

    league_id = league_event["id"]
    st_league, league_detail = request("GET", f"/api/attendance/events/{league_id}/vote-detail", headers=admin_h)
    assert_ok(st_league == 200, "league detail load succeeds")
    attend_by_team = ((league_detail.get("summary") or {}).get("attend_by_team") or {})
    counts = ((league_detail.get("event") or {}).get("counts") or {})
    attend_total = int(counts.get("ATTEND", 0))

    assert_ok(all(k in attend_by_team for k in ("A", "B", "C")), "league detail includes A/B/C attend counts")
    assert_ok(sum(int(attend_by_team.get(k, 0)) for k in ("A", "B", "C")) == attend_total, "team attend sum matches ATTEND count")

    member = login(MEMBER_ID, "1234")
    member_h = {"Authorization": f"Bearer {member['access_token']}"}

    st_ev_member, ev_member_payload = request("GET", "/api/attendance/events?skip=0&limit=200", headers=member_h)
    assert_ok(st_ev_member == 200, "member can load attendance events")
    ev_member = ev_member_payload.get("items", [])
    assert_ok(len(ev_member) >= 2, "member sees sample events")

    for e in (rest_event, league_event):
        eid = e["id"]
        st_d, d = request("GET", f"/api/attendance/events/{eid}/vote-detail", headers=member_h)
        assert_ok(st_d == 200, f"member can open vote detail event_id={eid}")
        assert_ok("voted" in d and "pending" in d, f"member detail payload valid event_id={eid}")

    print("=== Phase1 QC Passed ===")


if __name__ == "__main__":
    try:
        run()
    except Exception:
        sys.exit(1)
