# -*- coding: utf-8 -*-
"""GeoField one-shot Windows acceptance EVIDENCE probe (read-only).

Run once with GeoField open after the user's normal CAD/FEA test. This tool
does not import STEP, execute solver/ML, install software, change CAD/SQLite,
send CAD externally or call the optional LLM service. Only local GET endpoints.
Never claim actual 3D rendering or engineering safety is verified by HTTP.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

SERVER="http://127.0.0.1:8600"
SHA=re.compile(r"^[a-f0-9]{64}$")
RUN=re.compile(r"^[a-f0-9]{32}$")
MAX_REPLY=4_000_000


def fetch_json(path, opener=None):
    """Hardcoded loopback origin, no proxies, redirects or external requests."""
    if not path.startswith("/api/") or not re.fullmatch(r"/api/[a-zA-Z0-9/_-]+",path):
        raise ValueError("Local API path rejected")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):
            return None
    client=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect)
    req=urllib.request.Request(SERVER+path,headers={"Accept":"application/json",
                                                    "Cache-Control":"no-store"})
    with client.open(req,timeout=6) as response:
        if response.status!=200:
            raise ValueError("Local API HTTP status not successful")
        media=response.headers.get("Content-Type","").lower()
        if "application/json" not in media:
            raise ValueError("Local GeoField API did not return JSON")
        payload=response.read(MAX_REPLY+1)
        if len(payload)>MAX_REPLY:
            raise ValueError("Local API JSON response is too large")
        result=json.loads(payload)
        if not isinstance(result,dict):
            raise ValueError("Local API JSON is not an object")
        return result


def _finite(value):
    return type(value) in (int,float) and math.isfinite(value) and value>=0


def assess(fetch=fetch_json):
    """Return privacy-minimized observed status; no raw CAD/FEA identifiers."""
    result={
        "schema":"geofield-windows-acceptance-observation-v1",
        "created_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "mode":"read_only_local_observation",
        "server":"not_verified","cad":"not_verified",
        "ml":"not_verified","fea":"not_verified","ai":"not_verified",
        "restore":"not_checked","agent_llm":"not_called",
        "three_d_visual":"NOT_VERIFIABLE_BY_THIS_PROBE",
        "actual_solver_execution_this_session":"NOT_VERIFIABLE_BY_THIS_PROBE",
        "mesh_convergence":"NOT_VERIFIED",
        "structural_safety":"NOT_VERIFIED",
        "production_release_approved":False,
        "api_errors":[],
        "note":"Only local API claims were checked. Real Windows WebGL, STEP geometry, actual solver run and physics require independent observation."
    }
    def unavailable(phase,exc):
        # Never log arbitrary server messages: they could contain private paths,
        # original file names, API tokens or other user data.
        result["api_errors"].append({"phase":phase,"error_type":type(exc).__name__})
    try:
        status=fetch("/api/status")
    except (OSError,ValueError,TypeError,KeyError,TimeoutError,UnicodeError) as exc:
        unavailable("server",exc)
        return result
    current=status.get("current") if isinstance(status.get("current"),dict) else {}
    if status.get("ok") is not True or status.get("version")!="R20-core-stabilization":
        result["server"]="unexpected_local_backend"
        return result
    result["server"]="observed_expected_local_backend"
    capabilities=status.get("capabilities") if isinstance(status.get("capabilities"),dict) else {}
    result["cad_engine_detected"]=bool(capabilities.get("cad_analysis"))
    result["fea_solver_detected"]=bool(capabilities.get("fea"))
    result["ml_environment_reported_available"]=bool(capabilities.get("ml_inference"))
    job=current.get("job_id")
    if not isinstance(job,str) or not RUN.fullmatch(job) or current.get("pending_job_id") not in (None,job):
        result["cad"]="no_stable_selected_cad"
        return result
    try:
        summary=fetch("/api/results/summary/"+job)
        agent=fetch("/api/agent/evidence/"+job)
    except (OSError,ValueError,TypeError,KeyError,TimeoutError,UnicodeError) as exc:
        unavailable("cad_or_agent",exc)
        result["cad"]="selected_cad_but_evidence_unavailable"
        return result
    cad=summary.get("cad") if isinstance(summary.get("cad"),dict) else {}
    sha=cad.get("sha256")
    if (not isinstance(sha,str) or not SHA.fullmatch(sha) or
        agent.get("cad_sha256")!=sha or
        agent.get("schema")!="geofield-evidence-agent-v1"):
        result["cad"]="identity_mismatch"
        return result
    result["cad"]="matching_cad_sha_and_evidence_schema"
    fea=agent.get("fea") if isinstance(agent.get("fea"),dict) else {}
    result["ai"]="rules_evidence_observed" if (
        agent.get("mode")=="rules_only" and
        isinstance(agent.get("llm"),dict) and
        agent["llm"].get("executed") is False and
        agent["llm"].get("connected") is False and
        fea.get("safety_certified") is False
    ) else "unexpected_ai_contract"
    ml=agent.get("ml") if isinstance(agent.get("ml"),dict) else {}
    result["ml"]=ml.get("status") if ml.get("status") in (
        "not_run","queued","running","failed","research_unverified",
        "identity_rejected","evidence_rejected") else "unrecognized_or_not_verified"
    summary_fea=summary.get("fea") if isinstance(summary.get("fea"),dict) else {}
    provenance=summary.get("fea_case_provenance") if isinstance(summary.get("fea_case_provenance"),dict) else {}
    run=fea.get("run_id");case=fea.get("case_sha256")
    real=(fea.get("status")=="INP_STA_FRD_reverified" and
          isinstance(run,str) and RUN.fullmatch(run) and
          isinstance(case,str) and SHA.fullmatch(case) and
          provenance.get("verified_run_id")==run and
          provenance.get("solved_case_sha256")==case and
          provenance.get("source_verification")=="INP_STA_FRD_reverified" and
          provenance.get("summary_numbers_crosschecked") is True and
          summary_fea.get("state")=="complete" and
          summary_fea.get("result_run_id") in (None,run) and
          summary_fea.get("result_case_sha256") in (None,case) and
          _finite(fea.get("maximum_von_mises_mpa")) and
          _finite(fea.get("maximum_displacement_mm")) and
          _finite(summary_fea.get("maximum_von_mises_mpa")) and
          _finite(summary_fea.get("maximum_displacement_mm")) and
          math.isclose(fea["maximum_von_mises_mpa"],
                       summary_fea["maximum_von_mises_mpa"],rel_tol=1e-9,abs_tol=1e-10) and
          math.isclose(fea["maximum_displacement_mm"],
                       summary_fea["maximum_displacement_mm"],rel_tol=1e-9,abs_tol=1e-10) and
          fea.get("convergence")=="not_independently_verified" and
          fea.get("safety_certified") is False)
    result["fea"]="same_run_backend_reverified_source" if real else "not_verified_for_selected_cad"
    if real:
        result["verified_max_von_mises_mpa"]=fea["maximum_von_mises_mpa"]
        result["verified_max_displacement_mm"]=fea["maximum_displacement_mm"]
        result["element_type"]=fea.get("element_type") if fea.get("element_type") in ("C3D4","C3D10") else "unverified"
    restored=current.get("verified_restored_run_id")
    if restored is not None:
        proof=agent.get("restore_evidence") if isinstance(agent.get("restore_evidence"),dict) else {}
        result["restore"]="verified_read_only_past_run" if (
            real and proof.get("status")=="verified_restored_read_only" and
            proof.get("run_id")==run==restored and
            proof.get("cad_sha256")==sha and
            proof.get("case_sha256")==case and
            proof.get("read_only") is True) else "not_verified"
    else:
        result["restore"]="not_in_restored_session"
    result["recommendation"]="inspect_video_and_solver_files_before_release"
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=None)
    opt=parser.parse_args(argv)
    report=assess()
    default=Path(os.environ.get("LOCALAPPDATA","."))/"GeoFieldCAD"/"diagnostics"/"acceptance"/"geofield_acceptance_latest.json"
    destination=opt.output or default
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf8")
    print(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    print("[ACCEPTANCE REPORT]",destination)
    # HTTP evidence is NOT physical acceptance; 0 means the probe could
    # inspect a same-CAD solver result, not approval for production.
    return 0 if report["fea"]=="same_run_backend_reverified_source" and report["ai"]=="rules_evidence_observed" else 24


if __name__=="__main__":
    sys.exit(main())
