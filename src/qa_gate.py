# -*- coding: utf-8 -*-
"""GeoField deterministic OFFLINE integration test coordinator.

Use from the repository root:
    python src/qa_gate.py --mode b --output /tmp/geofield-qa.json
    python src/qa_gate.py --mode ab --output /tmp/geofield-ab-qa.json

Mode ab requires Chat A's FEA branch already merged into an ISOLATED CI
checkout. This tool does not merge branches, install packages, touch real
Windows runtime, run CalculiX, or falsely certify FEA convergence.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
B_TESTS = (
    "test_runtime_preflight", "test_windows_install_safety",
    "test_cad_session_integrity", "test_cad_geometry_identity",
    "test_fea_report_provenance",
    "test_ml_integrity", "test_ml_worker_isolation", "test_sqlite_archive_reverify",
    "test_ui_cleanup", "test_port8600_recovery",
    "test_qa8.ModelChecks", "test_qa8.FeaChecks", "test_qa8.RouteChecks",
)
JS_TESTS = (
    ("cad_import_race", "CAD", "test_cad_import_race.js"),
    ("cad_evidence_race", "CAD", "test_cad_evidence_race.js"),
    ("fea_field_provenance", "FEA_3D", "test_fea_display_provenance.js"),
    ("fea_run_race", "FEA_3D", "test_fea_run_race.js"),
    ("fea_archive_preview", "SQLITE_HISTORY", "test_fea_archive_preview_race.js"),
    ("fea_archive_identity", "SQLITE_HISTORY", "test_fea_archive_identity.js"),
    ("fea_previous_relink", "SQLITE_HISTORY", "test_fea_previous_relink_race.js"),
    ("fea_restore_import_race", "CAD", "test_fea_restore_import_race.js"),
    ("fea_mesh_label", "FEA_3D", "test_fea_mesh_label_contract.js"),
    ("ml_display", "ML", "test_ml_display.js"),
)
TEST_RE = re.compile(r"\bRan\s+(\d+)\s+tests?\b")
PASS_RE = re.compile(r"\bPASS:\s*(\d+)\b")
SKIP_RE = re.compile(r"\bskipped\s*=\s*(\d+)\b")


@dataclass(frozen=True)
class Suite:
    id: str
    domain: str
    command: tuple[str, ...]
    cwd: Path
    evidence: str


def suites(mode: str) -> tuple[Suite, ...]:
    """Explicit audited command allowlist; user input cannot execute a shell."""
    if mode not in ("b", "ab"):
        raise ValueError("Allowed modes are b and ab")
    base = (
        Suite("python_b", "MULTI", (PYTHON, "-m", "unittest", *B_TESTS, "-v"),
              ROOT / "src" / "tests", "synthetic unit/regression tests"),
        Suite("python_syntax", "INTEGRATION",
              (PYTHON, "-m", "py_compile", "payload/GeoField_CAD_Analysis.py",
               "bootstrap.py", "installer.py", "runtime_preflight.py",
               "build_integration_candidate.py"),
              ROOT / "src", "Python syntax only"),
        Suite("javascript_syntax", "INTEGRATION",
              ("node", "--check", "src/payload/frontend/cad.js"),
              ROOT, "JavaScript syntax only"),
    )
    js = tuple(
        Suite(ident, domain, ("node", "src/tests/" + path), ROOT,
              "synthetic front-end contract/race tests")
        for ident, domain, path in JS_TESTS
    )
    if mode == "b":
        return base + js
    ab = (
        Suite("python_a_fea", "FEA_PHYSICS",
              (PYTHON, "-m", "unittest", "discover", "-s", "tests",
               "-p", "test_fea_*.py", "-v"),
              ROOT / "src", "synthetic and archived FEA tests; skips are not real convergence"),
        Suite("candidate_install", "INSTALL",
              (PYTHON, "-m", "unittest", "test_integration_candidate", "-v"),
              ROOT / "src" / "tests",
              "temporary runtime A+B package, upgrade and rollback"),
    )
    return base + js + ab


def execute(item: Suite, runner: Callable = subprocess.run,
            timeout: int = 110) -> dict:
    """Treat a zero-tests success, timeout or missing PASS marker as failure."""
    command = list(item.command)
    result = {
        "suite": item.id, "domain": item.domain,
        "evidence_type": item.evidence, "status": "failed",
        "test_count": 0, "skipped_count": 0,
        "exit_code": None, "message": "",
    }
    try:
        finished = runner(command, cwd=str(item.cwd), capture_output=True,
                          text=True, errors="replace", timeout=timeout)
        output = (finished.stdout or "") + "\n" + (finished.stderr or "")
        result["exit_code"] = finished.returncode
        is_test = item.id not in ("python_syntax", "javascript_syntax")
        node = item.command[0] == "node"
        count = PASS_RE.findall(output) if node and is_test else TEST_RE.findall(output)
        result["test_count"] = int(count[-1]) if count else 0
        skips = SKIP_RE.findall(output)
        result["skipped_count"] = int(skips[-1]) if skips else 0
        if finished.returncode != 0:
            result["message"] = ("Command failed (tail): " + output[-1800:]).strip()
        elif is_test and result["test_count"] < 1:
            result["message"] = "No executed test count or PASS marker; cannot accept green result"
        else:
            result["status"] = "passed_with_skips" if result["skipped_count"] else "passed"
            result["message"] = "Offline checks only; no actual CAD/FEA validation"
    except subprocess.TimeoutExpired:
        result["message"] = f"Test suite exceeded {timeout}s"
    except (OSError, ValueError) as exc:
        result["message"] = type(exc).__name__ + ": " + str(exc)[:500]
    return result


def make_report(mode: str, executor: Callable = execute) -> dict:
    outcomes = [executor(s) for s in suites(mode)]
    failures = [x["suite"] for x in outcomes if x["status"] == "failed"]
    skipped = [x["suite"] for x in outcomes if x["status"] == "passed_with_skips"]
    return {
        "schema": "geofield-offline-integration-gate-v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "github_sha": os.environ.get("GITHUB_SHA", ""),
        "conclusion": "failed" if failures else ("passed_with_skips" if skipped else "passed"),
        "failed_suites": failures,
        "skipped_suites": skipped,
        "total_test_cases_executed": sum(max(0, x["test_count"]-x["skipped_count"]) for x in outcomes),
        "total_test_cases_discovered": sum(x["test_count"] for x in outcomes),
        "total_test_cases_skipped": sum(x["skipped_count"] for x in outcomes),
        "suites": outcomes,
        "final_windows_e2e": "NOT_TESTED",
        "actual_calculix_run": "NOT_TESTED",
        "three_mesh_convergence_certified": False,
        "production_release_approved": False,
        "limitation": ("Passing an offline suite does not establish actual STEP geometry, "
                       "Gmsh/CalculiX physics, Windows WebGL, private user records, "
                       "three-stage convergence, or a shippable installer."),
    }


def write_report(report: dict, location: Path) -> None:
    """Atomically emit report, including on test failure. Existing files are protected."""
    location = Path(location)
    if location.exists() or location.is_symlink():
        raise FileExistsError("Refusing to replace an existing QA report")
    location.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".geofield-qa-", suffix=".tmp",
                                dir=str(location.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, location)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=["b", "ab"])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = make_report(args.mode)
    write_report(report, args.output)
    print("GeoField OFFLINE QA:", report["conclusion"], "suites:",
          len(report["suites"]), "failed:", len(report["failed_suites"]),
          "skipped:", report["total_test_cases_skipped"])
    print("Report:", args.output)
    print("Real Windows CAD/FEA/3D:", report["final_windows_e2e"])
    return 1 if report["failed_suites"] else 0


if __name__ == "__main__":
    sys.exit(main())
