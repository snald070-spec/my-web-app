import sqlite3

DB_PATH = r"c:/Users/sksky/OneDrive/문서/draw_phase2_backend/backend/app.db"
SAMPLE_NOTES = (
    "SAMPLE_ATTENDANCE_VOTE_RESULT",
    "SAMPLE_ATTENDANCE_LEAGUE_VOTE_RESULT",
)


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        select id
        from attendance_events
        where note in (?, ?)
        """,
        SAMPLE_NOTES,
    )
    event_ids = [row[0] for row in cur.fetchall()]

    if not event_ids:
        print("[OK] 삭제할 출석 샘플이 없습니다.")
        conn.close()
        return

    placeholders = ",".join(["?"] * len(event_ids))

    cur.execute(
        f"delete from attendance_reminder_logs where event_id in ({placeholders})",
        event_ids,
    )
    reminder_deleted = cur.rowcount

    cur.execute(
        f"delete from attendance_votes where event_id in ({placeholders})",
        event_ids,
    )
    votes_deleted = cur.rowcount

    cur.execute(
        f"delete from attendance_event_settings where event_id in ({placeholders})",
        event_ids,
    )
    settings_deleted = cur.rowcount

    cur.execute(
        f"delete from attendance_events where id in ({placeholders})",
        event_ids,
    )
    events_deleted = cur.rowcount

    conn.commit()
    conn.close()

    print("[OK] 출석 샘플 데이터 삭제 완료")
    print(f"event_ids={event_ids}")
    print(f"deleted_events={events_deleted}")
    print(f"deleted_settings={settings_deleted}")
    print(f"deleted_votes={votes_deleted}")
    print(f"deleted_reminders={reminder_deleted}")


if __name__ == "__main__":
    main()
