"""A checkout without private development reports must fail closed, not crash CI."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(("report_only", "expected"), [(False, 2), (True, 0)])
def test_missing_local_evidence_never_approves_release(tmp_path, report_only, expected):
    command = [sys.executable, str(ROOT / "scripts/check_release.py"), "--gates", str(tmp_path / "missing.json")]
    if report_only:
        command.append("--report-only")
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    assert result.returncode == expected
    assert "BLOCKED" in result.stdout
    assert "READY" not in result.stdout
    assert not result.stderr


def test_invalid_evidence_cannot_be_reported_as_ready(tmp_path):
    gates = tmp_path / "invalid.json"
    gates.write_text('{"gates": {"A": {"status": "PASS", "evidence": []}}}')
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_release.py"), "--gates", str(gates), "--report-only"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Invalid or unevidenced release gate" in result.stderr
