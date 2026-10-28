"""A08 verified report composition + immutable atomic export (temporary files only)."""
import ast
import copy
import hashlib
import os
from pathlib import Path
import threading
from unittest.mock import patch

import pytest

from fea_report_a08 import compose_evidence_html, append_verified_evidence, save_immutable_html

CAD="a"*64
CASE="b"*64
RUN="1"*32
UID="2"*32
HTML="<html><body><h1>검증된 FEA</h1></body></html>"


def summary():
    return {"cad":{"sha256":CAD,"name":"<script>UNTRUSTED</script>"},
            "fea":{"state":"complete","result_run_id":RUN,
                   "result_case_sha256":CASE,
                   "maximum_von_mises_mpa":15.18,
                   "maximum_displacement_mm":0.0209,
                   "node_count":100,"tetrahedron_count":50},
            "ml":{"state":"running"}}


def proof():
    return {"verified_run_id":RUN,"solved_case_sha256":CASE,
            "source_verification":"INP_STA_FRD_reverified",
            "summary_numbers_crosschecked":True,
            "verified_mesh":{"nodes":100,"tetrahedra":50}}


def case():
    return {"cad_sha256":CAD,"case_sha256":CASE,
            "material":{"name":"Steel <test>","young_modulus_mpa":200000},
            "boundary_conditions":{"total_force_n":49.05,
                "force_direction_unit":[0,0,-1],
                "fixed_face_ids":[1,2],"load_face_ids":[3]},
            "mesh_request":{"element_type":"C3D4"}}


def local_agent():
    return {"schema":"geofield-evidence-agent-v1",
            "mode":"rules_only","cad_sha256":CAD,"llm":{"executed":False}}


def deepseek():
    return {"provider":"deepseek","status":"external_explanation_only",
            "executed":True,"opt_in":True,
            "cad_sha256":CAD,"case_sha256":CASE,"run_id":RUN,
            "explanation":"실제 계산 원본 검증 후 사용자에게 설명"}


def test_real_cad_fea_ml_and_local_agent_labels_only():
    sec=compose_evidence_html(summary(),proof(),case(),local_agent=local_agent())
    assert "15.18 MPa" in sec
    assert "0.0209 mm" in sec
    assert "49.05 N" in sec
    assert "C3D4" in sec
    assert "전체 절점" in sec
    assert "실험적 ML 상태: running" in sec
    assert "동일 CAD 기반 규칙 설명 포함" in sec
    assert "DeepSeek 설명: 표시 불가" in sec
    assert "3D 화면 이미지: 표시 불가" in sec
    assert "<img" not in sec
    assert "&lt;test&gt;" in sec
    assert "<script>" not in sec
    assert CAD in sec and CASE in sec and RUN in sec


def test_actual_video_report_direction_vector_not_silently_unavailable():
    s=summary();s["fea"]["maximum_von_mises_mpa"]=18.8603
    s["fea"]["maximum_displacement_mm"]=0.0330929
    c=case();c["boundary_conditions"]["force_direction_unit"]=[1.0,0.0,0.0]
    p=proof();p["verified_element_type"]="C3D4"
    html=compose_evidence_html(s,p,c)
    assert "<th>하중 방향</th><td>(1, 0, 0)</td>" in html
    assert "C3D4 (실제 솔버 메시)" in html
    assert "18.8603 MPa" in html
    assert "0.0330929 mm" in html


def test_verified_solver_element_type_when_legacy_case_has_no_element_field():
    p=proof();p["verified_element_type"]="C3D4"
    c=case();c["mesh_request"].pop("element_type")
    html=compose_evidence_html(summary(),p,c)
    assert "C3D4 (실제 솔버 메시)" in html
    p["verified_element_type"]="C3D10"
    html=compose_evidence_html(summary(),p,c)
    assert "C3D10 (실제 솔버 메시)" in html
    assert "확인 불가" not in html.split("<th>메시 요소</th>")[1].split("</td>")[0]


def test_unverified_mesh_type_not_upgraded_to_solver_verified_label():
    c=case();p=proof()
    html=compose_evidence_html(summary(),p,c)
    assert "C3D4 (저장된 조건 · 실제 요소 확인 불가)" in html
    c["mesh_request"]["element_type"]="C3D10"
    p["verified_element_type"]="C3D4"
    html=compose_evidence_html(summary(),p,c)
    assert "조건/실제 요소 형식 불일치 · 검증 필요" in html


def test_invalid_direction_is_not_exposed_as_measured_vector():
    for invalid in ([1,1,0],[float("nan"),0,0],["1",0,0],None):
        c=case();c["boundary_conditions"]["force_direction_unit"]=invalid
        html=compose_evidence_html(summary(),proof(),c)
        assert "<th>하중 방향</th><td>확인 불가</td>" in html


def test_identical_case_required_to_display_material_loads():
    altered=case()
    altered["case_sha256"]="c"*64
    sec=compose_evidence_html(summary(),proof(),altered)
    assert "Steel" not in sec
    assert "49.05 N" not in sec
    assert "15.18 MPa" in sec


def test_a07_proof_mandatory_before_report_append():
    for key,change in [
        ("source",lambda x:x.update(source_verification="not_checked")),
        ("flag",lambda x:x.update(summary_numbers_crosschecked=False)),
        ("run",lambda x:x.update(verified_run_id="0"*32)),
        ("case",lambda x:x.update(solved_case_sha256="0"*64))
    ]:
        p=proof();change(p)
        if key in ("run","case"):
            # Mismatches must be rejected, even if format is valid.
            pass
        with pytest.raises(ValueError):
            append_verified_evidence(HTML,summary(),p,case())


@pytest.mark.parametrize("value", [None,-1,False,float("nan"),float("inf"),"12"])
def test_bad_numeric_values_never_rendered(value):
    s=summary();s["fea"]["maximum_von_mises_mpa"]=value
    with pytest.raises(ValueError):
        append_verified_evidence(HTML,s,proof(),case())


@pytest.mark.parametrize("bad", [
    "<html><body>broken</body></body></html>",
    "<html><body>missing close",
    None,
    5,
    "x" * (4*1024*1024+5)
])
def test_invalid_html_cannot_be_saved(bad):
    with pytest.raises(ValueError):
        append_verified_evidence(bad,summary(),proof(),case())


def test_evidence_only_one_append_and_no_mutations():
    s,p,c=summary(),proof(),case()
    originals=copy.deepcopy((s,p,c))
    html=append_verified_evidence(HTML,s,p,c,local_agent=local_agent())
    assert html.count('id="geofield-a08-evidence"')==1
    assert html.endswith("</body></html>")
    with pytest.raises(ValueError,match="이미"):
        append_verified_evidence(html,s,p,c)
    assert (s,p,c)==originals


def test_no_fabricated_deepseek_even_if_configured_or_not_explicitly_opted_in():
    for key,val in [("opt_in",False),("executed",False),("run_id","4"*32),
                    ("case_sha256","c"*64),("status","not_configured"),
                    ("provider","openai")]:
        d=deepseek();d[key]=val
        html=compose_evidence_html(summary(),proof(),case(),external_agent=d)
        assert "DeepSeek 설명: 표시 불가" in html
    verified=compose_evidence_html(summary(),proof(),case(),external_agent=deepseek())
    assert "실제 연결·동일 실행 검증된 DeepSeek 설명" in verified
    malicious=deepseek();malicious["explanation"]="<script>alert(1)</script>"
    verified=compose_evidence_html(summary(),proof(),case(),external_agent=malicious)
    assert "<script>" not in verified
    assert "&lt;script&gt;" in verified


def test_immutable_create_reopen_identical_and_different_bytes_protected(tmp_path):
    payload=append_verified_evidence(HTML,summary(),proof(),case())
    first=save_immutable_html(tmp_path/"reports",payload,RUN,CAD,CASE)
    assert first["saved"] is True and first["reused"] is False
    original=Path(first["path"]).read_bytes()
    assert hashlib.sha256(original).hexdigest()==first["sha256"]
    second=save_immutable_html(tmp_path/"reports",payload,RUN,CAD,CASE)
    assert second["reused"] is True
    assert second["path"]==first["path"]
    with pytest.raises(FileExistsError,match="덮어쓸"):
        save_immutable_html(tmp_path/"reports",payload.replace("C3D4","C3D10"),RUN,CAD,CASE)
    assert Path(first["path"]).read_bytes()==original
    assert not list((tmp_path/"reports").glob("*.tmp"))


def test_atomic_link_failure_removes_temp_and_keeps_previous_reports(tmp_path):
    root=tmp_path/"reports"
    first=save_immutable_html(root,append_verified_evidence(HTML,summary(),proof(),case()),RUN,CAD,CASE)
    old=Path(first["path"]).read_bytes()
    new_run="9"*32
    with patch("fea_report_a08.os.link",side_effect=OSError("simulated NTFS lock")):
        with pytest.raises(OSError,match="simulated NTFS lock"):
            save_immutable_html(root,append_verified_evidence(HTML,summary(),proof(),case()),new_run,CAD,CASE)
    assert Path(first["path"]).read_bytes()==old
    assert not any(root.glob("*.tmp"))
    assert not any(root.glob("*.html")) is False


def test_symlink_root_refused_without_original_modification(tmp_path):
    source=tmp_path/"source"
    source.mkdir()
    (source/"keep.txt").write_text("DO NOT DELETE")
    alias=tmp_path/"alias"
    alias.symlink_to(source,target_is_directory=True)
    with pytest.raises(ValueError,match="심볼릭"):
        save_immutable_html(alias,append_verified_evidence(HTML,summary(),proof(),case()),RUN,CAD,CASE)
    assert (source/"keep.txt").read_text()=="DO NOT DELETE"


def test_invalid_ids_and_report_without_verified_section_never_saved(tmp_path):
    for run,sha,csha in [("bad",CAD,CASE),(RUN,"x"*64,CASE),(RUN,CAD,"y"*64)]:
        with pytest.raises(ValueError):
            save_immutable_html(tmp_path,append_verified_evidence(HTML,summary(),proof(),case()),run,sha,csha)
    with pytest.raises(ValueError,match="근거"):
        save_immutable_html(tmp_path,HTML,RUN,CAD,CASE)
    assert not list(tmp_path.glob("*.html"))


SOURCE=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SOURCE.read_text(encoding="utf-8"))
WANTED=[x for x in TREE.body if isinstance(x,ast.FunctionDef) and x.name=="gf_current_verified_report"]
assert len(WANTED)==1


def test_production_uses_one_render_path_for_browser_and_atomic_export():
    code=SOURCE.read_text(encoding="utf-8")
    assert "def gf_current_verified_report(uid, *, as_html=False):" in code
    assert "gf_current_verified_report(uid,as_html=html_requested)" in code
    assert "data=gf_current_verified_report(uid,as_html=True)" in code
    assert "save_immutable_html(" in code
    assert "X-GeoField-Report-Export" in code
    assert "EXPLICIT_SAVE" in code
    assert "append_verified_evidence(report,summary,provenance,case,local_agent=agent)" in code
    assert "return self.send_raw(report,'text/html')" not in code


def test_report_renderer_without_real_fea_stops_before_legacy_html():
    scope={"valid_uid":lambda x:isinstance(x,str) and len(x)==32,
           "STATE_LOCK":threading.RLock(),"JOBS":{UID:{"status":"complete","sha256":CAD,
                                                      "analysis":{},"findings":[]}},
           "CURRENT":{"job_id":UID},"ML_JOBS":{},
           "FEA_JOBS":{RUN:{"id":RUN,"status":"complete","cad_job_id":UID}},
           "JOBS_DIR":Path("/synthetic/does-not-touch"),
           "json":__import__("json"),
           "measure_geometry":lambda *_:{},
           "fea_solver_status":lambda :{},
           "r171_event":lambda *args:None,
           "r181_current_result_case":lambda uid:case(),
           "reverify_task_for_display":lambda *args:None,
           "build_summary":lambda *args:summary(),
           "r124_case_provenance":lambda *args:proof(),
           "r125_reconcile_current_fea_summary":lambda s,*_:s,
           "r128_r12_status":lambda *args:{},
           "gf_verified_analysis_report_ready":lambda *args:False,
           "html_report":lambda *_:pytest.fail("unverified HTML renderer invoked")}
    # Create only the same CAD's synthetic model.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="geofield-a08-mock-") as folder:
        root=Path(folder)
        (root/(UID+".json")).write_text(__import__("json").dumps({"sha256":CAD,"mesh":{"face_ids":[1]}}))
        scope["JOBS_DIR"]=root
        exec(compile(ast.Module(body=WANTED,type_ignores=[]),str(SOURCE),"exec"),scope)
        with pytest.raises(ValueError,match="검증된 실제 FEA"):
            scope["gf_current_verified_report"](UID,as_html=True)


def test_server_report_route_checks_session_and_accepts_no_uploaded_html():
    source=SOURCE.read_text(encoding="utf-8")
    post=source.split("if path.startswith('/api/results/report-save/'):",1)[1].split("if path.startswith('/api/history/fea-delete/'):",1)[0]
    assert "origin not in allowed" in post
    assert "self.headers.get('Content-Length','0')!='0'" in post
    assert "same" in post and "active_case=r181_current_result_case(uid)" in post
    assert "return self.send_raw({'ok':True" in post
    assert "self.rfile.read" not in post
