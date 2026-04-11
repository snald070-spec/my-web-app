import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "http://127.0.0.1:8000"
MEMBER_ID = "01012345678"


def _request(method: str, path: str, data=None, headers=None):
    url = f"{BASE_URL}{path}"
    req_headers = headers.copy() if headers else {}

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
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        payload = {}
        if raw:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"detail": raw}
        return e.code, payload


def _assert(cond: bool, message: str):
    if not cond:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[OK] {message}")


def login(username: str, password: str):
    status, payload = _request(
        "POST",
        "/api/auth/login",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    _assert(status == 200, f"login {username} should return 200")
    _assert("access_token" in payload, f"login {username} should return token")
    return payload


def run():
    print("=== Smoke Test Start ===")

    admin = login("admin", "1234")

    admin_h = {"Authorization": f"Bearer {admin['access_token']}"}

    status, issued = _request(
        "POST",
        f"/api/users/{MEMBER_ID}/issue-temp-password",
        headers=admin_h,
    )
    _assert(status == 200, "admin can issue temporary password for member")

    member = login(MEMBER_ID, issued["temp_password"])
    member_h = {"Authorization": f"Bearer {member['access_token']}"}

    status, payload = _request("GET", "/api/dashboard/summary", headers=admin_h)
    _assert(status == 200, "admin can access /api/dashboard/summary")
    _assert("message" in payload, "summary response contains message")

    status, _ = _request("GET", "/api/dashboard/admin-stats", headers=member_h)
    _assert(status == 403, "member cannot access /api/dashboard/admin-stats")

    status, payload = _request("GET", "/api/users?skip=0&limit=10", headers=admin_h)
    _assert(status == 200, "admin can access /api/users")
    _assert(isinstance(payload.get("items"), list), "users.items should be list")
    _assert(all(k in payload for k in ("total", "skip", "limit")), "users payload is paginated")

    status, _ = _request("GET", "/api/users?skip=0&limit=10", headers=member_h)
    _assert(status == 403, "member cannot access /api/users")

    status, _ = _request(
        "PATCH",
        "/api/users/admin/status",
        data={"is_resigned": True},
        headers=admin_h,
    )
    _assert(status == 400, "admin cannot deactivate own account")

    status, payload = _request(
        "PATCH",
        f"/api/users/{MEMBER_ID}/status",
        data={"is_resigned": True},
        headers=admin_h,
    )
    _assert(status == 200 and payload.get("is_resigned") is True, "admin can deactivate member")

    status, payload = _request(
        "PATCH",
        f"/api/users/{MEMBER_ID}/status",
        data={"is_resigned": False},
        headers=admin_h,
    )
    _assert(status == 200 and payload.get("is_resigned") is False, "admin can reactivate member")

    status, payload = _request(
        "GET",
        f"/api/users?skip=0&limit=10&keyword={MEMBER_ID}&role=USER&status=ACTIVE",
        headers=admin_h,
    )
    _assert(status == 200, "filtered user list call should succeed")
    _assert(payload.get("total", 0) >= 1, "filtered result should include member user")

    print("=== Smoke Test Passed ===")


if __name__ == "__main__":
    try:
        run()
    except Exception:
        sys.exit(1)
