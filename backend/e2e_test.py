"""
E2E Integration Test — Draw Phase 2 Backend
============================================
Covers: Auth · Users · Notices · Attendance · Fees · League · RBAC

Usage:
    python backend/e2e_test.py [--base-url URL] [--admin-id ID] [--admin-pw PW]

Defaults:
    --base-url  http://127.0.0.1:8000
    --admin-id  admin
    --admin-pw  (reads first from ADMIN_PW env var, falls back to 1234 for dev)

Exit codes:
    0 = all tests passed
    1 = at least one assertion failed
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

# ──────────────────────────────────────────────
# Config / helpers
# ──────────────────────────────────────────────

_base_url: str = "http://127.0.0.1:8000"
_failures: list[str] = []
_pass_count: int = 0


def _request(
    method: str,
    path: str,
    data=None,
    headers: dict | None = None,
    expect_json: bool = True,
) -> tuple[int, dict | str]:
    url = f"{_base_url}{path}"
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
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if (expect_json and raw) else raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return e.code, payload


def ok(cond: bool, msg: str) -> None:
    global _pass_count
    if cond:
        _pass_count += 1
        print(f"  [OK] {msg}")
    else:
        _failures.append(msg)
        print(f"  [FAIL] {msg}")


def section(name: str) -> None:
    print(f"\n{'─'*50}")
    print(f"  {name}")
    print(f"{'─'*50}")


# ──────────────────────────────────────────────
# Auth helpers
# ──────────────────────────────────────────────

def _login(username: str, password: str) -> dict | None:
    status, payload = _request(
        "POST",
        "/api/auth/login",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if status == 200 and isinstance(payload, dict) and "access_token" in payload:
        return payload
    return None


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ──────────────────────────────────────────────
# Test suites
# ──────────────────────────────────────────────

def test_health():
    section("Health check")
    s, p = _request("GET", "/api/dashboard/summary", headers={})
    ok(s == 401, "unauthenticated /api/dashboard/summary returns 401")


def test_auth(admin_id: str, admin_pw: str) -> str:
    """Returns admin access token."""
    section("Auth — login")
    token_payload = _login(admin_id, admin_pw)
    ok(token_payload is not None, f"admin login succeeds ({admin_id})")
    if token_payload is None:
        print("[ABORT] Cannot obtain admin token. Remaining tests will be skipped.")
        return ""
    token = token_payload["access_token"]
    ok(isinstance(token, str) and len(token) > 20, "access_token is non-empty string")

    # Wrong password
    s, p = _request(
        "POST", "/api/auth/login",
        data={"username": admin_id, "password": "__wrong__"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    ok(s in (400, 401, 422), "wrong password returns 4xx")

    return token


def test_rbac(admin_token: str) -> str:
    """Creates a test user, gets a member token, returns it plus emp_id."""
    section("RBAC — create test member")
    h = _auth(admin_token)

    test_emp_id = "e2e_test_user"
    # Clean up previous run just in case
    _request("DELETE", f"/api/users/{test_emp_id}", headers=h)

    s, p = _request(
        "POST", "/api/users",
        data={
            "emp_id": test_emp_id,
            "name": test_emp_id,
            "department": "테스트",
            "email": f"{test_emp_id}@example.com",
            "role": "USER",
        },
        headers=h,
    )
    ok(s == 200, "admin can create user")
    if s != 200:
        return "", test_emp_id

    # Issue a temp password
    s2, issued = _request("POST", f"/api/users/{test_emp_id}/issue-temp-password", headers=h)
    ok(s2 == 200, "admin can issue temp password")
    if s2 != 200:
        return "", test_emp_id

    temp_pw = issued.get("temp_password")
    ok(isinstance(temp_pw, str) and len(temp_pw) >= 8, "temp_password is present and long enough")

    member_payload = _login(test_emp_id, temp_pw)
    ok(member_payload is not None, "member can log in with temp password")
    if member_payload is None:
        return "", test_emp_id

    member_token = member_payload["access_token"]

    # Member cannot access admin-only endpoints
    s3, _ = _request("GET", "/api/users?skip=0&limit=1", headers=_auth(member_token))
    ok(s3 == 403, "member cannot access /api/users (RBAC)")

    s4, _ = _request("GET", "/api/dashboard/admin-stats", headers=_auth(member_token))
    ok(s4 == 403, "member cannot access /api/dashboard/admin-stats (RBAC)")

    return member_token, test_emp_id


def test_dashboard(admin_token: str):
    section("Dashboard — admin-stats")
    h = _auth(admin_token)
    s, p = _request("GET", "/api/dashboard/admin-stats", headers=h)
    ok(s == 200, "admin-stats returns 200")
    if isinstance(p, dict):
        ok("total_users" in p, "admin-stats has total_users")


def test_users(admin_token: str):
    section("Users — list, filter, activate/deactivate")
    h = _auth(admin_token)

    s, p = _request("GET", "/api/users?skip=0&limit=5", headers=h)
    ok(s == 200, "list users returns 200")
    ok(isinstance(p.get("items"), list), "users.items is list")
    ok(all(k in p for k in ("total", "skip", "limit")), "pagination keys present")

    # Filter by keyword
    s2, p2 = _request("GET", "/api/users?skip=0&limit=5&keyword=admin", headers=h)
    ok(s2 == 200, "user filter by keyword works")

    # Cannot deactivate own admin account
    s3, _ = _request("PATCH", "/api/users/admin/status", data={"is_resigned": True}, headers=h)
    ok(s3 == 400, "admin cannot deactivate own account")


def test_notices(admin_token: str, member_token: str):
    section("Notices — create, list, update, delete")
    h_admin = _auth(admin_token)
    h_member = _auth(member_token)

    # Create notice
    s, p = _request(
        "POST", "/api/notices",
        data={"title": "[E2E] 테스트 공지", "body": "E2E 테스트 본문입니다.", "is_pinned": False},
        headers=h_admin,
    )
    ok(s == 200, "admin can create notice")
    notice_id = p.get("id") if s == 200 else None

    # List — both member and admin can read
    s2, p2 = _request("GET", "/api/notices?skip=0&limit=10", headers=h_member)
    ok(s2 == 200, "member can list notices")
    ok(isinstance(p2.get("items"), list), "notices.items is list")

    if notice_id:
        # Update notice
        s3, _ = _request(
            "PATCH", f"/api/notices/{notice_id}",
            data={"title": "[E2E] 수정됨", "body": "수정된 본문", "is_pinned": True},
            headers=h_admin,
        )
        ok(s3 == 200, "admin can update notice")

        # Member cannot delete notice
        s4, _ = _request("DELETE", f"/api/notices/{notice_id}", headers=h_member)
        ok(s4 == 403, "member cannot delete notice (RBAC)")

        # Admin can delete notice
        s5, _ = _request("DELETE", f"/api/notices/{notice_id}", headers=h_admin)
        ok(s5 == 200, "admin can delete notice")


def test_attendance(admin_token: str, member_token: str):
    section("Attendance — event create, vote, list")
    h_admin = _auth(admin_token)
    h_member = _auth(member_token)

    event_date = (date.today() + timedelta(days=3)).isoformat()

    # Create event
    s, p = _request(
        "POST", "/api/attendance/events",
        data={"title": "[E2E] 테스트 일정", "event_date": event_date, "vote_type": "REST"},
        headers=h_admin,
    )
    ok(s == 200, "admin can create attendance event")
    event_id = p.get("id") if s == 200 else None

    # List events
    s2, p2 = _request("GET", "/api/attendance/events?skip=0&limit=10", headers=h_member)
    ok(s2 == 200, "member can list attendance events")

    if event_id:
        # Member votes
        s3, _ = _request(
            "POST", f"/api/attendance/events/{event_id}/vote",
            data={"response": "ATTEND"},
            headers=h_member,
        )
        ok(s3 == 200, "member can vote on attendance event")

        # Admin closes event
        s4, _ = _request(
            "PATCH", f"/api/attendance/events/{event_id}/status",
            data={"status": "CLOSED"},
            headers=h_admin,
        )
        ok(s4 in (200, 404), "admin can close attendance event")

        # Admin deletes event (cleanup)
        _request("DELETE", f"/api/attendance/events/{event_id}", headers=h_admin)


def test_fees(admin_token: str, member_token: str):
    section("Fees — list, profile read")
    h_admin = _auth(admin_token)
    h_member = _auth(member_token)

    # Admin can list fee records
    s, p = _request("GET", "/api/fees?skip=0&limit=5", headers=h_admin)
    ok(s == 200, "admin can list fees")

    # Member can read own fee profile
    s2, p2 = _request("GET", "/api/fees/my-profile", headers=h_member)
    ok(s2 == 200, "member can read own fee profile")


def test_league(admin_token: str):
    section("League — season create, list")
    h = _auth(admin_token)

    # List seasons
    s, p = _request("GET", "/api/league/seasons", headers=h)
    ok(s == 200, "admin can list league seasons")
    ok(isinstance(p, list), "seasons is a list")

    # Create a test season
    s2, p2 = _request(
        "POST", "/api/league/seasons",
        data={"total_weeks": 2, "client_year": 2026, "note": "[E2E 테스트 시즌]"},
        headers=h,
    )
    ok(s2 == 200, "admin can create league season")
    season_id = p2.get("id") if s2 == 200 else None

    if season_id:
        # List standings
        s3, _ = _request("GET", f"/api/league/seasons/{season_id}/standings", headers=h)
        ok(s3 == 200, "admin can read league standings")

        # Delete test season (cleanup)
        s4, _ = _request("DELETE", f"/api/league/seasons/{season_id}", headers=h)
        ok(s4 in (200, 204, 404), "admin can delete test season (cleanup)")


def test_cleanup(admin_token: str, test_emp_id: str):
    section("Cleanup — remove test user")
    s, _ = _request("DELETE", f"/api/users/{test_emp_id}", headers=_auth(admin_token))
    ok(s in (200, 204, 404), f"test user {test_emp_id} removed / not found")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    global _base_url

    parser = argparse.ArgumentParser(description="Draw Phase 2 E2E Test Runner")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-id", default="admin")
    parser.add_argument("--admin-pw", default=os.environ.get("ADMIN_PW", "1234"))
    args = parser.parse_args()

    _base_url = args.base_url.rstrip("/")

    print(f"\n{'═'*50}")
    print(f"  Draw Phase 2 — E2E Test")
    print(f"  Target: {_base_url}")
    print(f"{'═'*50}")

    test_health()
    admin_token = test_auth(args.admin_id, args.admin_pw)
    if not admin_token:
        print("\n[ABORT] No admin token. Check server is running and credentials are correct.")
        sys.exit(1)

    member_token, test_emp_id = test_rbac(admin_token)
    test_dashboard(admin_token)
    test_users(admin_token)

    if member_token:
        test_notices(admin_token, member_token)
        test_attendance(admin_token, member_token)
        test_fees(admin_token, member_token)
    else:
        print("\n[SKIP] member_token unavailable — notices/attendance/fees tests skipped")

    test_league(admin_token)
    test_cleanup(admin_token, test_emp_id)

    # Summary
    total = _pass_count + len(_failures)
    print(f"\n{'═'*50}")
    print(f"  결과: {_pass_count}/{total} passed")
    if _failures:
        print(f"\n  실패 목록:")
        for f in _failures:
            print(f"    ✗ {f}")
    else:
        print("  모든 테스트 통과 ✓")
    print(f"{'═'*50}\n")

    sys.exit(0 if not _failures else 1)


if __name__ == "__main__":
    main()
