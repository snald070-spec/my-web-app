"""
QC 마스터 러너: 모든 QC 스크립트를 순서대로 실행하고 통합 결과를 출력합니다.

실행 방법:
  python qc_run_all.py
  python qc_run_all.py --stop-on-fail   # 첫 실패 시 중단
"""
import subprocess, sys, time, argparse, urllib.request, urllib.error
from pathlib import Path


def wait_for_server(url: str = "http://127.0.0.1:8000/health", timeout: int = 30) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False

SCRIPTS = [
    ("인증 엣지 케이스",    "qc_auth_edge_cases.py"),
    ("API 입력 검증",       "qc_api_validation.py"),
    ("RBAC 전체 검증",      "qc_rbac_full.py"),
    ("출석 관리 전체 플로우","qc_attendance_full.py"),
    ("회비 관리 전체 플로우","qc_fees_full.py"),
    ("통합 E2E 시나리오",   "qc_integration.py"),
]

WIDTH = 60


def run_script(label: str, script: str, python: str) -> tuple[bool, float, str]:
    script_path = Path(__file__).parent / script
    if not script_path.exists():
        return False, 0.0, f"[ERROR] 파일 없음: {script}"

    start = time.monotonic()
    result = subprocess.run(
        [python, str(script_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.monotonic() - start
    output = result.stdout + result.stderr
    passed = result.returncode == 0
    return passed, elapsed, output


def main():
    parser = argparse.ArgumentParser(description="QC 마스터 러너")
    parser.add_argument("--stop-on-fail", action="store_true",
                        help="첫 번째 실패한 스크립트에서 중단")
    args = parser.parse_args()

    python = sys.executable

    print("\n" + "=" * WIDTH)
    print("  QC 전체 실행 시작")
    print("=" * WIDTH)

    print("  서버 응답 대기 중...", end="", flush=True)
    if not wait_for_server():
        print(" [FAIL]")
        print("[FATAL] 서버(http://127.0.0.1:8000)에 연결할 수 없습니다.")
        sys.exit(1)
    print(" [OK]")

    results = []
    total_start = time.monotonic()

    for label, script in SCRIPTS:
        print(f"\n{'─' * WIDTH}")
        print(f"  ▶ {label}  ({script})")
        print("─" * WIDTH)

        passed, elapsed, output = run_script(label, script, python)

        # 스크립트 출력 그대로 표시
        for line in output.splitlines():
            print(line)

        status_str = "PASS" if passed else "FAIL"
        print(f"\n  [{status_str}] {label} — {elapsed:.1f}s")
        results.append((label, script, passed, elapsed))

        if not passed and args.stop_on_fail:
            print("\n  --stop-on-fail 옵션으로 중단합니다.")
            break

    total_elapsed = time.monotonic() - total_start
    passed_count = sum(1 for _, _, p, _ in results if p)
    total_count = len(results)

    print("\n" + "=" * WIDTH)
    print(f"  전체 결과: {passed_count}/{total_count} 스크립트 통과")
    print(f"  총 소요 시간: {total_elapsed:.1f}s")

    failed = [(lbl, scr, el) for lbl, scr, p, el in results if not p]
    if failed:
        print("\n  실패한 스크립트:")
        for lbl, scr, el in failed:
            print(f"    ✗ {lbl}  ({scr})  — {el:.1f}s")
    else:
        print("\n  모든 QC 스크립트 통과!")

    print("=" * WIDTH + "\n")
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
