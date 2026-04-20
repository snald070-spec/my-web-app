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
MEMBER_PW = "1234"


SAMPLE_MARKERS = (
    "출석 투표 샘플",
    "리그전 출석 투표 샘플",
)


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


def has_sample_title(title: str) -> bool:
    t = str(title or "")
    return any(marker in t for marker in SAMPLE_MARKERS)


def run():
    print("=== Phase2 QC (without sample data) ===")

    admin = login(ADMIN_ID, ADMIN_PW)
    admin_h = {"Authorization": f"Bearer {admin['access_token']}"}

    status, events_payload = request("GET", "/api/attendance/events?skip=0&limit=200", headers=admin_h)
    assert_ok(status == 200, "admin can load attendance events")
    events = events_payload.get("items", [])
    assert_ok(all(not has_sample_title(e.get("title")) for e in events), "sample attendance events are removed")

    # Initial-state safety check: empty list or normal list should both be valid.
    print(f"[INFO] admin_visible_events={len(events)}")

    member = login(MEMBER_ID, MEMBER_PW)
    member_h = {"Authorization": f"Bearer {member['access_token']}"}

    st_member, member_events_payload = request("GET", "/api/attendance/events?skip=0&limit=200", headers=member_h)
    assert_ok(st_member == 200, "member can load attendance events")
    member_events = member_events_payload.get("items", [])
    assert_ok(all(not has_sample_title(e.get("title")) for e in member_events), "member view has no sample attendance events")

    # If there is any remaining real event, detail endpoint should still work.
    if member_events:
        first_event_id = member_events[0].get("id")
        st_detail, detail_payload = request("GET", f"/api/attendance/events/{first_event_id}/vote-detail", headers=member_h)
        assert_ok(st_detail == 200, "member can open detail for remaining event")
        assert_ok("summary" in detail_payload and "voted" in detail_payload and "pending" in detail_payload, "detail payload shape is valid")
    else:
        print("[INFO] No remaining attendance events (empty initial state confirmed).")

    print("=== Phase2 QC Passed ===")


if __name__ == "__main__":
    try:
        run()
    except Exception:
        sys.exit(1)
