"""A07: verified FEA required to generate current analysis HTML.

Loads production pure functions by AST because installed Windows-only
`integrated_results` / `fea_previous_import` are unavailable on CI.
Real Windows solver/physical report generation are *not* claimed.
"""
from __future__ import annotations

import ast
import copy
import math
from pathlib import Path

import pytest

SOURCE=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SOURCE.read_text(encoding="utf-8"))
NAMES={"gf_verified_analysis_report_ready","r125_reconcile_current_fea_summary"}
FUNCTIONS=[x for x in TREE.body if isinstance(x,ast.FunctionDef) and x.name in NAMES]
assert len(FUNCTIONS)==len(NAMES)
ns={"valid_uid":lambda x:isinstance(x,str) and len(x)==32
    and all(c in "0123456789abcdef" for c in x)}
exec(compile(ast.Module(body=FUNCTIONS,type_ignores=[]),str(SOURCE),"exec"),ns)
ready=ns["gf_verified_analysis_report_ready"]
reconcile=ns["r125_reconcile_current_fea_summary"]

CAD="a"*64
CASE="b"*64
RUN="1"*32
UID="2"*32


def evidence():
    summary={
        "cad":{"sha256":CAD},
        "fea":{"state":"complete","result_run_id":RUN,
               "result_case_sha256":CASE,
               "maximum_von_mises_mpa":14.5,
               "maximum_displacement_mm":0.0569,
               "node_count":2798,
               "tetrahedron_count":8611},
        "ml":{"state":"queued"},
        "ai":{"state":"not_started"}
    }
    proof={
        "source_verification":"INP_STA_FRD_reverified",
        "summary_numbers_crosschecked":True,
        "verified_run_id":RUN,
        "solved_case_sha256":CASE,
        "verified_mesh":{"nodes":2798,"tetrahedra":8611},
        "selected_case_sha256":CASE,
        "editable_case_sha256":CASE
    }
    return summary,proof


def task():
    return {"id":RUN,"cad_job_id":UID,"cad_sha256":CAD,
            "case_sha256":CASE,"status":"complete",
            "source_validation":"INP_STA_FRD_reverified",
            "result":{"schema":"geofield-fea-result-v1",
                      "status":"solver_executed_result_parsed",
                      "cad_sha256":CAD,"case_sha256":CASE,
                      "results":{"maximum_nodal_von_mises_mpa":14.5,
                                 "maximum_displacement_mm":0.0569},
                      "mesh":{"node_count":2798,
                              "tetrahedron_count":8611}}}


def test_actual_reconciled_run_entitles_report_not_recomputing_solvers():
    summary,proof=evidence()
    proof.pop("summary_numbers_crosschecked")
    assert ready(summary,proof) is False
    before=copy.deepcopy(summary)
    output=reconcile(summary,task(),proof,CAD)
    assert output is summary
    assert summary==before
    assert proof["summary_numbers_crosschecked"] is True
    assert ready(summary,proof) is True


def test_optional_ai_ml_waiting_or_failed_does_not_block_fea_report():
    for state in ("queued","not_started","running","failed","unavailable",None):
        summary,proof=evidence()
        summary["ml"]={"state":state}
        summary["ai"]={"state":state}
        assert ready(summary,proof) is True


@pytest.mark.parametrize("change",[
    lambda s,p:s.pop("fea"),
    lambda s,p:s["fea"].update(state="not_run"),
    lambda s,p:s["fea"].update(state="failed"),
    lambda s,p:s["fea"].update(state="rejected"),
    lambda s,p:s["fea"].update(state="running"),
    lambda s,p:p.update(source_verification="report_consistency_rejected"),
    lambda s,p:p.update(source_verification="assumed_verified"),
    lambda s,p:p.pop("summary_numbers_crosschecked"),
    lambda s,p:p.update(summary_numbers_crosschecked=1),
    lambda s,p:p.update(verified_run_id="3"*32),
    lambda s,p:p.update(verified_run_id="malformed"),
    lambda s,p:p.update(solved_case_sha256="3"*64),
    lambda s,p:p.update(solved_case_sha256="b"*63),
    lambda s,p:s["fea"].update(result_run_id="3"*32),
    lambda s,p:s["fea"].update(result_case_sha256="c"*64),
    lambda s,p:s["cad"].update(sha256="not-sha"),
    lambda s,p:s["cad"].update(sha256="G"*64),
    lambda s,p:s["fea"].pop("maximum_von_mises_mpa"),
    lambda s,p:s["fea"].pop("maximum_displacement_mm"),
    lambda s,p:s["fea"].update(maximum_von_mises_mpa=float("nan")),
    lambda s,p:s["fea"].update(maximum_displacement_mm=float("inf")),
    lambda s,p:s["fea"].update(maximum_displacement_mm=-1),
    lambda s,p:s["fea"].update(maximum_displacement_mm=True),
    lambda s,p:s["fea"].update(maximum_von_mises_mpa="12"),
    lambda s,p:s["fea"].update(node_count=0),
    lambda s,p:s["fea"].update(tetrahedron_count=True),
    lambda s,p:s["fea"].update(node_count=3),
    lambda s,p:s["fea"].pop("tetrahedron_count"),
    lambda s,p:p.update(verified_mesh=None),
    lambda s,p:p["verified_mesh"].update(nodes=2999),
    lambda s,p:p["verified_mesh"].update(tetrahedra=1),
])
def test_missing_or_unverified_fea_is_not_reportable(change):
    summary,proof=evidence()
    change(summary,proof)
    assert ready(summary,proof) is False


def test_historic_verified_run_with_missing_optional_summary_ids_is_allowed():
    summary,proof=evidence()
    summary["fea"].pop("result_run_id")
    summary["fea"].pop("result_case_sha256")
    assert ready(summary,proof) is True


def test_original_and_saved_case_differences_are_disclosed_not_mistaken_for_missing_fea():
    summary,proof=evidence()
    proof.update(selected_case_sha256="d"*64,
                 editable_case_sha256="c"*64,
                 result_matches_selected=False,result_matches_saved=False)
    assert ready(summary,proof) is True


def test_reconciliation_rejects_false_numbers_even_with_previously_true_flag():
    summary,proof=evidence()
    summary["fea"]["maximum_von_mises_mpa"]=999
    reconcile(summary,task(),proof,CAD)
    assert summary["fea"]["state"]=="rejected"
    assert proof["summary_numbers_crosschecked"] is False
    assert ready(summary,proof) is False


def test_reconciliation_rejects_wrong_fea_run_and_preserves_cad():
    summary,proof=evidence()
    summary["fea"]["result_run_id"]="3"*32
    original_cad=copy.deepcopy(summary["cad"])
    reconcile(summary,task(),proof,CAD)
    assert ready(summary,proof) is False
    assert summary["cad"]==original_cad


def test_live_report_route_gates_before_html_or_agent_and_preserves_json_summary():
    source=SOURCE.read_text(encoding="utf-8")
    branch="if path.startswith('/api/results/report/'):"
    assert source.count(branch)==1
    block=source.split(branch,1)[1].split("return self.send_raw(summary)",1)[0]
    assert block.index("if not gf_verified_analysis_report_ready(summary,provenance):") < block.index("report=html_report(summary)")
    assert block.index("report=html_report(summary)") < block.index("agent=gf_current_report_agent(")
    assert "return self.fail(" in block
    assert ",409)" in block
    assert "except (ValueError,TypeError,KeyError,OSError,OverflowError) as exc:" in block


def test_report_rechecks_active_run_after_optional_agent_work_and_cannot_send_stale_html():
    source=SOURCE.read_text(encoding="utf-8")
    block=source.split("if path.startswith('/api/results/report/'):",1)[1].split("return self.send_raw(summary)",1)[0]
    assert block.index("active_fea=FEA_JOBS.get(provenance['verified_run_id'])") < block.index("return self.send_raw(report,'text/html')")
    assert block.index("latest_case=r181_current_result_case(uid)") < block.index("return self.send_raw(report,'text/html')")
    assert "active_fea.get('status')=='complete'" in block
    assert "CURRENT.get('verified_restored_run_id')==session.get('verified_restored_run_id')" in block


def test_legacy_record_report_endpoints_are_not_mislabeled_as_new_solver():
    source=SOURCE.read_text(encoding="utf-8")
    assert "entry=verified_archive_summary(entry,uid,HISTORY_DB,JOBS_DIR)" in source
    assert "report=build_verified_report(HISTORY_DB,JOBS_DIR,sid)" in source
    assert "return self.send_raw(summary)" in source
