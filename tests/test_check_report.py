"""Phase 7: the check report runs in replay mode and every check passes."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_check_report_passes_in_replay_mode():
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_report.py")],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = (ROOT / "reports" / "check-results.md").read_text(encoding="utf-8")
    for check in ("M1", "M2", "M3", "M4", "M5"):
        assert f"| {check} |" in report
    assert "FAIL" not in report.split("## Summary")[0]
