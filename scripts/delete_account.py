"""
특정 emp_id 계정을 DB에서 완전 삭제하는 일회성 스크립트.
사용법: python scripts/delete_account.py master

이 스크립트는 backend/ 디렉터리 위에서 실행해야 합니다.
  cd ~/draw_phase2_backend
  python scripts/delete_account.py master
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from database import SessionLocal, engine
import models

models.Base.metadata.create_all(bind=engine)

TARGET_EMP_ID = sys.argv[1] if len(sys.argv) > 1 else "master"

db = SessionLocal()
try:
    user = db.query(models.User).filter(models.User.emp_id == TARGET_EMP_ID).first()
    if not user:
        print(f"[ERROR] 계정 '{TARGET_EMP_ID}'을(를) 찾을 수 없습니다.")
        sys.exit(1)

    print(f"[INFO] 삭제 대상: emp_id={user.emp_id}, name={user.name}, role={user.role}")
    confirm = input("정말 삭제하시겠습니까? (yes 입력): ").strip()
    if confirm != "yes":
        print("[ABORTED] 취소되었습니다.")
        sys.exit(0)

    # 연관 데이터 삭제
    db.query(models.MemberProfile).filter(models.MemberProfile.emp_id == TARGET_EMP_ID).delete(synchronize_session=False)
    db.query(models.MembershipPayment).filter(models.MembershipPayment.emp_id == TARGET_EMP_ID).delete(synchronize_session=False)
    db.query(models.AttendanceVote).filter(models.AttendanceVote.emp_id == TARGET_EMP_ID).delete(synchronize_session=False)
    db.query(models.LeagueTeamAssignment).filter(models.LeagueTeamAssignment.emp_id == TARGET_EMP_ID).delete(synchronize_session=False)
    db.query(models.PushSubscription).filter(models.PushSubscription.emp_id == TARGET_EMP_ID).delete(synchronize_session=False)
    db.query(models.User).filter(models.User.emp_id == TARGET_EMP_ID).delete(synchronize_session=False)
    db.commit()
    print(f"[OK] 계정 '{TARGET_EMP_ID}'이(가) 삭제되었습니다.")
finally:
    db.close()
