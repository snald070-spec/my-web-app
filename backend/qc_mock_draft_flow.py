from datetime import date

from fastapi.testclient import TestClient

import models
from auth import create_access_token, hash_password
from database import SessionLocal
from main import app


def assert_ok(cond: bool, message: str):
    if not cond:
        raise AssertionError(message)
    print(f"[OK] {message}")


def auth_header(emp_id: str) -> dict:
    token = create_access_token({"sub": emp_id})
    return {"Authorization": f"Bearer {token}"}


def upsert_user(db, emp_id: str, name: str, role: models.RoleEnum, department: str = "QC"):
    row = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if row:
        row.name = name
        row.role = role
        row.department = department
        row.is_resigned = False
        return row

    row = models.User(
        emp_id=emp_id,
        name=name,
        department=department,
        email=f"{emp_id}@example.com",
        hashed_password=hash_password("Pw123456!"),
        role=role,
        is_first_login=False,
        temp_password=None,
        is_resigned=False,
    )
    db.add(row)
    return row


def upsert_member_profile(db, emp_id: str, status: models.MemberStatusEnum):
    row = db.query(models.MemberProfile).filter(models.MemberProfile.emp_id == emp_id).first()
    if row:
        row.member_status = status
        return
    db.add(models.MemberProfile(emp_id=emp_id, member_status=status, membership_type=models.MembershipTypeEnum.GENERAL))


def prepare_test_identities():
    db = SessionLocal()
    try:
        upsert_user(db, "admin", "Master", models.RoleEnum.MASTER, "IT")
        upsert_user(db, "qc_admin", "QC Admin", models.RoleEnum.ADMIN, "IT")
        upsert_user(db, "qc_viewer", "QC Viewer", models.RoleEnum.GENERAL, "QA")

        for i in range(1, 13):
            emp_id = f"test{i:03d}"
            upsert_user(db, emp_id, f"테스트{i:03d}", models.RoleEnum.GENERAL, "QA")

        # Draft participants (normal)
        for i in range(1, 10):
            upsert_member_profile(db, f"test{i:03d}", models.MemberStatusEnum.NORMAL)

        # Auto-excluded cases
        upsert_member_profile(db, "test010", models.MemberStatusEnum.INJURED)
        upsert_member_profile(db, "test011", models.MemberStatusEnum.DORMANT)
        upsert_member_profile(db, "test012", models.MemberStatusEnum.NORMAL)

        db.commit()
        print("[OK] Test identities prepared")
    finally:
        db.close()


def run_qc():
    prepare_test_identities()

    client = TestClient(app)

    master_h = auth_header("admin")
    admin_h = auth_header("qc_admin")
    viewer_h = auth_header("qc_viewer")
    captain_a_h = auth_header("test001")
    captain_b_h = auth_header("test002")
    captain_c_h = auth_header("test003")

    # 1) Master creates season
    res = client.post(
        "/api/league/admin/seasons",
        json={"total_weeks": 8, "client_year": date.today().year, "start_date": str(date.today())},
        headers=master_h,
    )
    assert_ok(res.status_code == 200, "Master can create season")
    season_id = res.json()["season_id"]

    # 2) Master/Admin select participants (season-scoped)
    participant_ids = [f"test{i:03d}" for i in range(1, 10)]
    for idx, emp_id in enumerate(participant_ids):
        actor_h = master_h if idx % 2 == 0 else admin_h
        r = client.put(
            f"/api/league/draft/participants/{emp_id}?season_id={season_id}",
            json={"include": True},
            headers=actor_h,
        )
        assert_ok(r.status_code == 200, f"Participant include success: {emp_id}")

    # 2-1) Auto-excluded member cannot be included
    r = client.put(
        f"/api/league/draft/participants/test010?season_id={season_id}",
        json={"include": True},
        headers=admin_h,
    )
    assert_ok(r.status_code == 400, "Injured member is auto-excluded from draft")

    r = client.put(
        f"/api/league/draft/participants/test011?season_id={season_id}",
        json={"include": True},
        headers=master_h,
    )
    assert_ok(r.status_code == 400, "Dormant member is auto-excluded from draft")

    # 3) Master/Admin assign captains
    r = client.put(
        "/api/attendance/admin/team-assignments/test001",
        json={"team_code": "A", "is_captain": True},
        headers=master_h,
    )
    assert_ok(r.status_code == 200, "Captain A assigned by master")

    r = client.put(
        "/api/attendance/admin/team-assignments/test002",
        json={"team_code": "B", "is_captain": True},
        headers=admin_h,
    )
    assert_ok(r.status_code == 200, "Captain B assigned by admin")

    r = client.put(
        "/api/attendance/admin/team-assignments/test003",
        json={"team_code": "C", "is_captain": True},
        headers=master_h,
    )
    assert_ok(r.status_code == 200, "Captain C assigned by master")

    # 4) Start draft
    r = client.post("/api/league/draft/start", json={"season_id": season_id}, headers=master_h)
    assert_ok(r.status_code == 200, "Draft start succeeded")

    # 5) Live visibility for all members
    board = client.get(f"/api/league/draft/board?season_id={season_id}", headers=viewer_h)
    assert_ok(board.status_code == 200, "Viewer can read draft board")
    b = board.json()
    assert_ok(b["draft"]["status"] == "OPEN", "Draft status visible as OPEN")
    assert_ok(b["draft"]["current_turn_team"] == "A", "Initial turn is A")

    # 6) Turn enforcement negative test: B captain tries on A turn -> fail
    r = client.put(
        f"/api/league/draft/assignments/test004?season_id={season_id}",
        json={},
        headers=captain_b_h,
    )
    assert_ok(r.status_code == 400, "Non-turn captain cannot pick")

    # 7) Complete draft in snake order
    # R1: A,B,C / R2: C,B,A
    picks = [
        (captain_a_h, "test004", "A"),
        (captain_b_h, "test005", "B"),
        (captain_c_h, "test006", "C"),
        (captain_c_h, "test007", "C"),
        (captain_b_h, "test008", "B"),
        (captain_a_h, "test009", "A"),
    ]

    for idx, (actor_h, target_emp, expected_team) in enumerate(picks, start=1):
        r = client.put(
            f"/api/league/draft/assignments/{target_emp}?season_id={season_id}",
            json={},
            headers=actor_h,
        )
        assert_ok(r.status_code == 200, f"Pick #{idx} accepted ({target_emp})")
        payload = r.json()
        assert_ok(payload["team_code"] == expected_team, f"Pick #{idx} assigned to expected team {expected_team}")

        # realtime visibility check after each pick
        live = client.get(f"/api/league/draft/board?season_id={season_id}", headers=viewer_h)
        assert_ok(live.status_code == 200, f"Live board visible after pick #{idx}")
        live_data = live.json()
        assert_ok(len(live_data["draft"]["history"]) == idx, f"History length updated after pick #{idx}")

    # 8) Already assigned member cannot be picked again
    r = client.put(
        f"/api/league/draft/assignments/test004?season_id={season_id}",
        json={},
        headers=captain_a_h,
    )
    assert_ok(r.status_code == 400, "Already-assigned member cannot be picked again")

    # 9) Draft should close automatically
    board = client.get(f"/api/league/draft/board?season_id={season_id}", headers=viewer_h)
    assert_ok(board.status_code == 200, "Viewer can read final board")
    b = board.json()
    assert_ok(b["draft"]["status"] == "CLOSED", "Draft auto-closed after all participants assigned")
    assert_ok(b["draft"]["unassigned_count"] == 0, "No unassigned participants remain")

    # 10) Final team composition QC (3 per team)
    team_counts = {"A": 0, "B": 0, "C": 0}
    for row in b["items"]:
        if row.get("is_participant") and row.get("team_code") in team_counts:
            team_counts[row["team_code"]] += 1
    assert_ok(team_counts == {"A": 3, "B": 3, "C": 3}, f"Final participant team counts are balanced: {team_counts}")

    print("\n=== STRICT QC PASSED: mock draft end-to-end succeeded ===")


if __name__ == "__main__":
    run_qc()
