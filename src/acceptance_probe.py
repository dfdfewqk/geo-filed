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
    # Import discovery is a deliberately explicit user action: optional ML
    # backends may take up to 55 seconds without affecting core CAD startup.
    timeout=70 if path in ("/api/ml/preflight","/api/ml/r12/preflight") else 6
    with client.open(req,timeout=timeout) as response:
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


def assess(fetch=fetch_json, *, check_ml_env=False):
    """Return privacy-minimized observed status; no raw CAD/FEA identifiers."""
    result={
        "schema":"geofield-windows-acceptance-observation-v1",
        "created_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "mode":"read_only_local_observation",
        "server":"not_verified","cad":"not_verified",
        "ml":"not_verified","fea":"not_verified","ai":"not_verified",
        "ml_probe_state":"not_checked",
        "brepmfr_environment":"not_checked",
        "r12_environment":"not_checked",
        "ml_user_windows_inference":"NOT_TESTED_BY_THIS_PROBE",
        "restore":"not_checked","agent_llm":"not_called",
        "three_d_visual":"NOT_VERIFIABLE_BY_THIS_PROBE",
        "actual_solver_execution_this_session":"NOT_VERIFIABLE_BY_THIS_PROBE",
        "mesh_convergence":"NOT_VERIFIED",
        "structural_safety":"NOT_VERIFIED",
        "production_release_approved":False,
        "api_errors":[],
        "next_action":"start_geofield_main_keep_running",
        "note":"This is only a READ-ONLY observer, not a launcher. The server must already be running. No engineering result is inferred when a check cannot connect."
    }
    def unavailable(phase,exc):
        # Never log arbitrary server messages: they could contain private paths,
        # original file names, API tokens or other user data.
        result["api_errors"].append({"phase":phase,"error_type":type(exc).__name__})
    try:
        status=fetch("/api/status")
    except (OSError,ValueError,TypeError,KeyError,TimeoutError,UnicodeError) as exc:
        unavailable("server",exc)
        # A URLerror is a connectivity observation, NOT evidence that CAD,
        # ML, FEA, AI or existing saved projects have failed.
        result["server"]="local_api_unreachable" if isinstance(
            exc,(urllib.error.URLError,ConnectionError,TimeoutError)
        ) else "local_api_response_invalid"
        result["next_action"]="start_geofield_main_keep_running" if (
            result["server"]=="local_api_unreachable"
        ) else "check_local_port_8600_and_backend_identity"
        return result
    current=status.get("current") if isinstance(status.get("current"),dict) else {}
    if status.get("ok") is not True or status.get("version")!="R20-core-stabilization":
        result["server"]="unexpected_local_backend"
        result["next_action"]="check_local_port_8600_and_backend_identity"
        return result
    result["server"]="observed_expected_local_backend"
    result["next_action"]="load_step_and_run_real_fea_then_recheck"
    capabilities=status.get("capabilities") if isinstance(status.get("capabilities"),dict) else {}
    result["cad_engine_detected"]=bool(capabilities.get("cad_analysis"))
    result["fea_solver_detected"]=bool(capabilities.get("fea"))
    # /api/status now intentionally skips optional heavyweight Python probes.
    # Never turn its False sentinel into a statement that ML is unavailable.
    result["ml_environment_reported_available"]=None
    result["ml_probe_state"]="not_checked_optional"
    if capabilities.get("ml_probe_state")=="checked":
        result["ml_probe_state"]="checked"
        result["ml_environment_reported_available"]=(capabilities.get("ml_inference") is True)
    if check_ml_env:
        for label,path,mode in (
            ("brepmfr_environment","/api/ml/preflight","experimental_research_only_not_validated"),
            ("r12_environment","/api/ml/r12/preflight","research_only_not_for_fea"),
        ):
            try:
                info=fetch(path)
                result[label]=("ready_for_research_inference_not_executed"
                               if info.get("available") is True and info.get("mode")==mode
                               else "unavailable_or_untrusted")
                if not isinstance(info.get("available"),bool) or info.get("mode")!=mode:
                    result[label]="invalid_local_preflight_contract"
            except (OSError,ValueError,TypeError,KeyError,TimeoutError,UnicodeError) as exc:
                unavailable(label,exc)
                result[label]="local_preflight_unreachable"
        result["ml_probe_state"]="explicit_read_only_preflight" 
        # Either independently verified research engine may be ready. This is
        # only a local import/asset preflight, NOT proof any user STEP ran.
        result["ml_environment_reported_available"]=any(
            result[name]=="ready_for_research_inference_not_executed"
            for name in ("brepmfr_environment","r12_environment"))
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
        result["next_action"]="inspect_summary_agent_evidence_api"
        return result
    cad=summary.get("cad") if isinstance(summary.get("cad"),dict) else {}
    sha=cad.get("sha256")
    if (not isinstance(sha,str) or not SHA.fullmatch(sha) or
        agent.get("cad_sha256")!=sha or
        agent.get("schema")!="geofield-evidence-agent-v1"):
        result["cad"]="identity_mismatch"
        result["next_action"]="review_cad_sha_and_agent_evidence"
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
    result["next_action"]=(
        "review_saved_run_and_video_evidence"
        if real else "complete_real_fea_and_verify_inp_sta_frd"
    )
    result["recommendation"]="inspect_video_and_solver_files_before_release"
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=None)
    parser.add_argument("--check-ml-env",action="store_true",
                        help="Explicitly query two read-only local ML preflights; never run inference")
    opt=parser.parse_args(argv)
    report=assess(check_ml_env=opt.check_ml_env)
    default=Path(os.environ.get("LOCALAPPDATA","."))/"GeoFieldCAD"/"diagnostics"/"acceptance"/"geofield_acceptance_latest.json"
    destination=opt.output or default
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf8")
    print(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    print("[ACCEPTANCE REPORT]",destination)
    if report["server"]=="local_api_unreachable":
        print("[SERVER OFFLINE] GeoField was not reachable on 127.0.0.1:8600.")
        print("[ACTION] This CHECK tool does NOT launch GeoField. Open GeoField_Start.cmd first.")
        print("[ACTION] Keep the GeoField backend CMD open, load STEP, run the FEA test, then check again.")
        print("[LOG] If main startup fails, inspect %LOCALAPPDATA%\\GeoFieldCAD\\diagnostics\\r12_launcher\\backend_latest.log")
        return 25
    if report["server"]!="observed_expected_local_backend":
        print("[SERVER NOT VERIFIED] Port 8600 did not return the expected GeoField API.")
        print("[ACTION] Check the original GeoField_Start.cmd startup output and port 8600 owner. Never terminate unrecognized processes.")
        return 24
    if report["cad"]=="no_stable_selected_cad":
        print("[CAD NOT SELECTED] The server is running. Load a real STEP and finish its CAD analysis first.")
        return 24
    if report["fea"]!="same_run_backend_reverified_source":
        print("[FEA NOT VERIFIED] Server checked, but no same-CAD reverified INP/STA/FRD result is established.")
        print("[ACTION] Review the FEA run, its material/mesh choice, original solver logs and history; this check never executes FEA.")
    # HTTP evidence is NOT physical acceptance; 0 means the probe could
    # inspect a same-CAD solver result, not approval for production.
    return 0 if report["fea"]=="same_run_backend_reverified_source" and report["ai"]=="rules_evidence_observed" else 24


if __name__=="__main__":
    sys.exit(main())
