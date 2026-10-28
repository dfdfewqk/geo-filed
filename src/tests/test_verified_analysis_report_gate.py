"""Analysis reports require a reverified FEA result (80th design decision).

This test extracts the pure report gate from the production module because
the integrated Windows backend imports optional local runtime dependencies.
It does not require Gmsh/CalculiX or mutate any saved analysis data.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "payload" / "GeoField_CAD_Analysis.py"


def _gate():
    source = SOURCE.read_text(encoding="utf-8")
    module = ast.parse(source)
    node = next(
        n for n in module.body
        if isinstance(n, ast.FunctionDef) and n.name == "gf_verified_analysis_report_ready"
    )
    code = compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec")
    namespace = {"valid_uid": lambda s: isinstance(s,str) and
                 re.fullmatch(r"[0-9a-f]{32}",s) is not None}
    exec(code, namespace)
    return namespace["gf_verified_analysis_report_ready"]


def _good_data():
    run_id = "a" * 32
    case_sha = "b" * 64
    return (
        {"cad": {"sha256": "c"*64},
         "fea": {"state": "complete", "result_run_id": run_id,
                 "result_case_sha256": case_sha}},
        {"source_verification": "INP_STA_FRD_reverified",
         "summary_numbers_crosschecked": True,
         "verified_run_id": run_id, "solved_case_sha256": case_sha},
    )


def test_verified_fea_allows_report_before_optional_ai_finishes():
    summary, proof = _good_data()
    assert _gate()(summary, proof) is True


def test_missing_fea_is_not_reportable():
    summary, proof = _good_data()
    summary["fea"] = {"state": "not_run"}
    assert _gate()(summary, proof) is False


def test_rejected_fea_is_not_reportable():
    summary, proof = _good_data()
    summary["fea"]["state"] = "rejected"
    assert _gate()(summary, proof) is False


def test_failed_source_reverification_is_not_reportable():
    summary, proof = _good_data()
    proof["source_verification"] = "report_consistency_rejected"
    assert _gate()(summary, proof) is False


def test_missing_number_crosscheck_is_not_reportable():
    summary, proof = _good_data()
    proof.pop("summary_numbers_crosschecked")
    assert _gate()(summary, proof) is False


def test_mismatched_record_run_is_not_reportable():
    summary, proof = _good_data()
    summary["fea"]["result_run_id"] = "d" * 32
    assert _gate()(summary, proof) is False


def test_mismatched_solver_case_is_not_reportable():
    summary, proof = _good_data()
    summary["fea"]["result_case_sha256"] = "e" * 64
    assert _gate()(summary, proof) is False


def test_report_gate_applies_only_to_analysis_html_endpoint():
    source = SOURCE.read_text(encoding="utf-8")
    report_branch = "if path.startswith('/api/results/report/'):" 
    gate_call = "if not gf_verified_analysis_report_ready(summary,provenance):"
    render_call = "report=html_report(summary)"
    assert source.count(report_branch) == 1
    segment = source.split(report_branch, 1)[1].split("if path=='/api/integration/quality'", 1)[0]
    assert segment.index(gate_call) < segment.index(render_call)
