import argparse
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def run_step(script_name: str) -> None:
    script_path = BASE_DIR / script_name
    print(f"\n>>> RUN {script_name}")
    proc = subprocess.run([sys.executable, str(script_path)], cwd=str(BASE_DIR))
    if proc.returncode != 0:
        raise RuntimeError(f"Step failed: {script_name}")


def run_phase1() -> None:
    # Option 1: keep sample data and verify full sample-based flows.
    run_step("seed_attendance_vote_sample.py")
    run_step("seed_attendance_league_vote_sample.py")
    run_step("qc_phase1_with_samples.py")


def run_phase2() -> None:
    # Option 2: remove sample data and verify clean initial state.
    run_step("cleanup_attendance_samples.py")
    run_step("qc_phase2_without_samples.py")


def run_full() -> None:
    # Full cycle: phase1 then phase2.
    run_phase1()
    run_phase2()


def main() -> None:
    parser = argparse.ArgumentParser(description="Attendance sample QC cycle runner")
    parser.add_argument(
        "--mode",
        choices=["phase1", "phase2", "full"],
        default="phase1",
        help="phase1=restore+sample QC, phase2=cleanup+clean-state QC, full=phase1 then phase2",
    )
    args = parser.parse_args()

    try:
        if args.mode == "phase1":
            run_phase1()
        elif args.mode == "phase2":
            run_phase2()
        else:
            run_full()
    except Exception as exc:
        print(f"\n[FAIL] {exc}")
        sys.exit(1)

    print("\n[OK] QC cycle completed")


if __name__ == "__main__":
    main()
