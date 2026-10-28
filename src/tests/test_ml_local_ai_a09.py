"""A09 BrepMFR/R12 research isolation + local AI review queue (synthetic only).

No native CAD, private model, solver, real user files or API calls.
"""
from __future__ import annotations

import ast
import copy
import json
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_agent_evidence import agent, record, CAD, CASE, JOB, RUN
from test_ml_integrity import valid_r12

SOURCE=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SOURCE.read_text(encoding="utf-8"))
FRAGMENTS={x.name:x for x in TREE.body
           if isinstance(x,ast.FunctionDef) and x.name in
           ("execute_r12","r128_r12_status")}
assert len(FRAGMENTS)==2
R12_RUN="4"*32
NEW_RUN="8"*32


def many_candidates():
    args=list(record())
    args[1]["items"]=[
        {"where":"CAD measured candidate "+str(i),
         "measured_evidence":"real B-Rep measured dimension "+str(i),
         "face_ids":[i+1],
         "next_check":"실제 CAD 형상 검토 "+str(i)}
        for i in range(8)
    ]
    return args


def test_top_three_only_from_verified_cad_and_frd():
    args=many_candidates()
    original=copy.deepcopy(args)
    result=agent(*args)
    assert args==original
    top=result["top_improvements"]
    assert len(top)==3
    assert [x["review_order"] for x in top]==[1,2,3]
    assert top[0]["source"]=="verified_frd_numeric"
    assert top[0]["run_id"]==RUN
    assert top[0]["measured_basis"].startswith("INP/STA/FRD")
    assert all(x["source"] in ("measured_cad_brep","verified_frd_numeric") for x in top)
    assert all(x["cad_sha256"]==CAD and x["structural_severity_verified"] is False
               and x["automatically_changes_cad_or_fea"] is False for x in top)
    assert result["top_improvements_policy"]=="up_to_three_measured_checks_not_verified_risk_ranking"
    assert len(result["findings"])>len(top)


def test_no_frd_numbers_in_improvement_queue_if_not_reverified():
    args=many_candidates()
    args[4]["source_validation"]="not_reverified"
    result=agent(*args)
    assert result["fea"]["status"]=="not_verified"
    assert 0<len(result["top_improvements"])<=3
    assert all(x["source"]=="measured_cad_brep" and x["run_id"] is None
               for x in result["top_improvements"])


@pytest.mark.parametrize("state",["queued","running","failed"])
def test_brepmfr_failure_never_replaces_cad_or_fea_or_priority(state):
    args=many_candidates()
    args[2]["status"]=state
    result=agent(*args)
    assert result["ml"]["status"]==state
    assert result["fea"]["status"]=="INP_STA_FRD_reverified"
    assert result["fea"]["maximum_von_mises_mpa"]==14.512
    assert result["fea"]["maximum_displacement_mm"]==0.05698
    assert result["cad"]["status"]=="measured"
    assert all(x["source"]!="ml_research" for x in result["top_improvements"])


def test_r12_fake_completed_same_sha_cannot_be_top_improvement():
    args=many_candidates()
    args[3]={"state":"complete","mode":"research_only","cad_sha256":CAD,
             "fea_calculated":False,"run_id":R12_RUN,"candidate_count":900}
    result=agent(*args)
    assert result["input_contract"]["r12"]["status"]=="research_complete"
    assert all("R12" not in x["title"] for x in result["top_improvements"])
    assert all(x["source"]!="r12_research" for x in result["top_improvements"])


def test_unmeasured_or_empty_cad_candidates_not_fabricated():
    args=list(record())
    args[1]["items"]=[]
    args[4]["source_validation"]="not_reverified"
    result=agent(*args)
    assert result["top_improvements"]==[]


def r12_context(*,bad=False):
    data=valid_r12()
    data["cad_sha256"]=CAD
    if bad:data["geometry_certified"]=True
    ctx={
      "R12_JOBS":{R12_RUN:{"id":R12_RUN,"cad_job_id":JOB,"cad_sha256":CAD,
                           "status":"complete","result":data}},
      "STATE_LOCK":threading.RLock(),
      "ml_r12_bridge":SimpleNamespace(validate_research_result=lambda raw,sha:
          (_ for _ in ()).throw(ValueError("research-only contract rejected"))
          if raw.get("geometry_certified") is not False or raw.get("cad_sha256")!=sha
          else raw),
      "valid_uid":lambda v:isinstance(v,str) and len(v)==32 and
                           all(c in "0123456789abcdef" for c in v)
    }
    exec(compile(ast.Module(body=[FRAGMENTS["r128_r12_status"]],
                            type_ignores=[]),str(SOURCE),"exec"),ctx)
    return ctx


def test_r12_status_revalidates_every_snapshot_and_preserves_research_only():
    ctx=r12_context()
    result=ctx["r128_r12_status"](JOB,CAD)
    assert result["state"]=="complete"
    assert result["fea_calculated"] is False
    assert result["mode"]=="research_only"
    assert result["run_id"]==R12_RUN
    assert result["candidate_count"]==1
    assert ctx["r128_r12_status"](JOB,"f"*64)["state"]=="not_run"


def test_r12_falsified_geometry_certification_is_rejected_without_cad_changes():
    ctx=r12_context(bad=True)
    original=copy.deepcopy(ctx["R12_JOBS"])
    out=ctx["r128_r12_status"](JOB,CAD)
    assert out["state"]=="evidence_rejected"
    assert ctx["R12_JOBS"]==original


def test_r12_stale_or_wrong_run_id_rejected_even_if_data_valid():
    ctx=r12_context()
    ctx["R12_JOBS"][R12_RUN]["id"]="bogus"
    assert ctx["r128_r12_status"](JOB,CAD)["state"]=="evidence_rejected"
    ctx=r12_context()
    ctx["R12_JOBS"][R12_RUN]["cad_job_id"]="5"*32
    assert ctx["r128_r12_status"](JOB,CAD)["state"]=="not_run"


def test_execute_r12_only_publishes_exact_running_job_and_verified_sha(tmp_path):
    data=valid_r12();data["cad_sha256"]=CAD
    step=tmp_path/"private-test-copy.step";step.write_bytes(b"SYNTHETIC")
    state={R12_RUN:{"id":R12_RUN,"cad_job_id":JOB,"cad_sha256":CAD,
                    "status":"queued"}}
    jobs={JOB:{"status":"complete","sha256":CAD}}
    context={
       "JOBS_DIR":tmp_path,"STATE_LOCK":threading.RLock(),
       "JOBS":jobs,"CURRENT":{"job_id":JOB},
       "R12_JOBS":state,
       "ml_r12_bridge":SimpleNamespace(execute=lambda *args:data,
           validate_research_result=lambda value,sha:value if sha==CAD else
                (_ for _ in ()).throw(ValueError("wrong sha"))),
       "ROOT":tmp_path
    }
    exec(compile(ast.Module(body=[FRAGMENTS["execute_r12"]],type_ignores=[]),
                 str(SOURCE),"exec"),context)
    context["execute_r12"](R12_RUN,JOB,step,CAD)
    assert state[R12_RUN]["status"]=="complete"
    assert state[R12_RUN]["result"]["decision_usage"]=="blocked_diagnostic_only"
    assert not step.exists()


@pytest.mark.parametrize("fault",["selected_cad","same_job_sha","run_id","bad_research"])
def test_execute_r12_stale_or_invalid_research_never_completes(tmp_path,fault):
    data=valid_r12();data["cad_sha256"]=CAD
    step=tmp_path/"synthetic-input.step";step.write_bytes(b"SYNTHETIC")
    state={R12_RUN:{"id":R12_RUN,"cad_job_id":JOB,"cad_sha256":CAD,
                    "status":"queued"}}
    jobs={JOB:{"status":"complete","sha256":CAD}}
    current={"job_id":JOB}
    bridge=SimpleNamespace(execute=lambda *args:data,
        validate_research_result=lambda value,sha:(_ for _ in ()).throw(ValueError("R12 research invalid"))
            if fault=="bad_research" else value)
    if fault=="selected_cad":current["job_id"]="9"*32
    if fault=="same_job_sha":jobs[JOB]["sha256"]="c"*64
    if fault=="run_id":state[R12_RUN]["cad_job_id"]="6"*32
    ctx={"JOBS_DIR":tmp_path,"STATE_LOCK":threading.RLock(),"JOBS":jobs,
         "CURRENT":current,"R12_JOBS":state,"ml_r12_bridge":bridge,"ROOT":tmp_path}
    exec(compile(ast.Module(body=[FRAGMENTS["execute_r12"]],type_ignores=[]),
                 str(SOURCE),"exec"),ctx)
    ctx["execute_r12"](R12_RUN,JOB,step,CAD)
    assert state[R12_RUN]["status"]=="failed"
    assert "result" not in state[R12_RUN]
    assert not step.exists()


def test_api_rechecks_both_ml_status_and_r12_id_before_display():
    src=SOURCE.read_text(encoding="utf-8")
    assert "R12 결과가 오래됐거나 현재 CAD·실행 ID와 다릅니다." in src
    assert "ML 결과가 오래됐거나 현재 CAD·실행 ID와 다릅니다." in src
    assert "qa_validate_brepmfr_diagnostic(result.get('result'),job['sha256'])" in src
    assert "public=r128_r12_status(active,job['sha256'])" in src
    assert "R12 추론 중 CAD 또는 실행 ID가 변경되어 결과를 폐기했습니다." in src


def test_ai_endpoint_rechecks_all_model_selections_after_optional_llm_call():
    src=SOURCE.read_text(encoding="utf-8")
    block=src.split("if path.startswith('/api/agent/evidence/'):",1)[1].split(
        "if path.startswith('/api/integration/decision/'):",1)[0]
    assert "r12_at_start=r128_r12_status(uid,sha)" in block
    assert "r12_at_end=r128_r12_status(uid,sha)" in block
    assert "분석 중 ML 실행이 변경되어 이전 설명을 차단했습니다." in block
    assert "분석 중 FEA 실행이 변경되어 이전 설명을 차단했습니다." in block
    assert "분석 중 R12 연구 결과가 변경되어 이전 설명을 차단했습니다." in block
    assert block.index("r12_at_end=r128_r12_status(uid,sha)") < block.index("return self.send_raw(response)")
