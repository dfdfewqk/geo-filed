"""Actual GeoField ML preflight fast-path with missing private assets.

Extract the production pure preflight function. Never install a checkpoint or
replace the user's Python and never call an external model/FEA service.
"""
import ast
import hashlib
import os
import time
from pathlib import Path
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"


def source_preflight(root, resolve, expected_sha, hasher=None):
    code=SOURCE.read_text(encoding="utf-8")
    matches=[x for x in ast.parse(code).body if isinstance(x,ast.FunctionDef)
             and x.name=="ml_preflight"]
    assert len(matches)==1
    space={"ROOT":root,"Path":Path,"os":os,"time":time,
           "REQUIRED_ML":("torch","numpy"),
           "BREPMFR_SHA256":expected_sha,
           "resolve_ml_python":resolve,
           "file_sha256":hasher or (lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest())}
    exec(compile(ast.Module(body=matches,type_ignores=[]),str(SOURCE),"exec"),space)
    return space["ml_preflight"]


def test_missing_worker_and_weights_report_exact_missing_without_slow_python_probe(tmp_path):
    calls=[]
    def forbidden(*args):
        calls.append(args)
        raise AssertionError("cannot probe Python when required private model is missing")
    check=source_preflight(tmp_path,forbidden,"f"*64)
    with patch.dict(os.environ,{"GEOFIELD_BREPMFR_CKPT":str(tmp_path/"missing.ckpt")}):
        result=check()
    assert not result["available"]
    assert "BrepMFR inference source" in result["missing"]
    assert "BrepMFR worker module" in result["missing"]
    assert "기존 epoch43 가중치 파일" in result["missing"]
    assert result["python_source"]=="skipped_missing_assets"
    assert result["python_executable"] is None
    assert calls==[]


def test_untested_or_changed_checkpoint_never_probes_python(tmp_path):
    (tmp_path/"ml"/"brepmfr_core").mkdir(parents=True)
    (tmp_path/"ml"/"compare_preprocessing.py").write_bytes(b"unrelated")
    (tmp_path/"ml"/"brepmfr_core"/"compare_preprocessing.py").write_bytes(b"synthetic source")
    (tmp_path/"ml"/"brepmfr_worker.py").write_bytes(b"synthetic worker")
    ckpt=tmp_path/"weights.ckpt";ckpt.write_bytes(b"wrong checkpoint")
    check=source_preflight(tmp_path,lambda *a:1,"a"*64)
    with patch.dict(os.environ,{"GEOFIELD_BREPMFR_CKPT":str(ckpt)}):
        out=check()
    assert out["missing"]==["가중치 SHA-256 불일치"]
    assert out["python_source"]=="skipped_missing_assets"


def test_only_full_exact_assets_run_real_python_import_probe(tmp_path):
    folder=tmp_path/"ml"/"brepmfr_core";folder.mkdir(parents=True)
    (folder/"compare_preprocessing.py").write_bytes(b"source")
    (tmp_path/"ml"/"brepmfr_worker.py").write_bytes(b"worker")
    ckpt=tmp_path/"weight.ckpt";ckpt.write_bytes(b"approved checkpoint")
    sha=hashlib.sha256(ckpt.read_bytes()).hexdigest()
    calls=[]
    def probe(key,requirements):
        calls.append((key,requirements))
        return {"ok":True,"path":"synthetic-python",
                "modules":{"torch":True,"numpy":True},"source":"verified"}
    check=source_preflight(tmp_path,probe,sha)
    with patch.dict(os.environ,{"GEOFIELD_BREPMFR_CKPT":str(ckpt)}):
        out=check()
    assert out["available"]
    assert out["checkpoint_sha_verified"]
    assert out["python_executable"]=="synthetic-python"
    assert calls==[("GEOFIELD_ML_PYTHON",("torch","numpy"))]


def test_python_import_failure_can_never_claim_available(tmp_path):
    folder=tmp_path/"ml"/"brepmfr_core";folder.mkdir(parents=True)
    (folder/"compare_preprocessing.py").write_bytes(b"source")
    (tmp_path/"ml"/"brepmfr_worker.py").write_bytes(b"worker")
    ckpt=tmp_path/"weight.ckpt";ckpt.write_bytes(b"approved checkpoint")
    check=source_preflight(tmp_path,lambda *a:{
        "ok":False,"path":None,"modules":{"torch":True,"numpy":"DLL load failed"},
        "source":"none"},hashlib.sha256(ckpt.read_bytes()).hexdigest())
    with patch.dict(os.environ,{"GEOFIELD_BREPMFR_CKPT":str(ckpt)}):
        out=check()
    assert not out["available"]
    assert "numpy" in out["missing"]
    assert out["python_errors"]["numpy"]=="DLL load failed"


def test_capabilities_only_calls_ml_preflight_once():
    source=ast.parse(SOURCE.read_text(encoding="utf-8"))
    funcs=[x for x in source.body if isinstance(x,ast.FunctionDef)
           and x.name=="capabilities"]
    assert len(funcs)==1
    calls=[x for x in ast.walk(funcs[0]) if isinstance(x,ast.Call)
           and isinstance(x.func,ast.Name) and x.func.id=="ml_preflight"]
    assert len(calls)==1

def test_periodic_status_reuses_checkpoint_hash_but_rechecks_on_metadata_change(tmp_path):
    folder=tmp_path/"ml"/"brepmfr_core";folder.mkdir(parents=True)
    (folder/"compare_preprocessing.py").write_text("x=1",encoding="utf-8")
    (tmp_path/"ml"/"brepmfr_worker.py").write_text("x=1",encoding="utf-8")
    ckpt=tmp_path/"trusted.ckpt";ckpt.write_bytes(b"verified weight bytes")
    trusted=hashlib.sha256(ckpt.read_bytes()).hexdigest()
    count=[]
    def hash_file(path):
        count.append(str(path))
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    check=source_preflight(tmp_path,lambda *args:{
        "ok":True,"path":"python","modules":{"torch":True,"numpy":True},
        "source":"mock_import_test"},trusted,hasher=hash_file)
    with patch.dict(os.environ,{"GEOFIELD_BREPMFR_CKPT":str(ckpt)}):
        assert check()["available"]
        assert check()["available"]
        assert len(count)==1,"/api/status must not reread large checkpoint every poll"
        ckpt.write_bytes(b"corrupted new weights")
        assert not check()["available"]
        assert len(count)==2
        assert "가중치 SHA-256 불일치" in check()["missing"]


def test_unreadable_checkpoint_status_does_not_crash_cad_api(tmp_path):
    folder=tmp_path/"ml"/"brepmfr_core";folder.mkdir(parents=True)
    (folder/"compare_preprocessing.py").write_bytes(b"x=1")
    (tmp_path/"ml"/"brepmfr_worker.py").write_bytes(b"x=2")
    ckpt=tmp_path/"readonly.ckpt";ckpt.write_bytes(b"weights")
    def deny(_path):
        raise PermissionError("no access to checkpoint")
    check=source_preflight(tmp_path,lambda *args:None,"a"*64,hasher=deny)
    with patch.dict(os.environ,{"GEOFIELD_BREPMFR_CKPT":str(ckpt)}):
        out=check()
    assert not out["available"]
    assert out["checkpoint_present"]
    assert any("PermissionError" in item for item in out["missing"])


def test_symlink_checkpoint_refused_without_read_or_import_probe(tmp_path):
    folder=tmp_path/"ml"/"brepmfr_core";folder.mkdir(parents=True)
    (folder/"compare_preprocessing.py").write_bytes(b"x=1")
    (tmp_path/"ml"/"brepmfr_worker.py").write_bytes(b"x=2")
    outside=tmp_path.parent/"geofield-unrelated-checkpoint.ckpt"
    # Use a target inside the isolated temp runtime to avoid unrelated data.
    outside=tmp_path/"regular.ckpt";outside.write_bytes(b"some checkpoint bytes")
    link=tmp_path/"linked.ckpt"
    try: link.symlink_to(outside)
    except (OSError,NotImplementedError):return
    check=source_preflight(tmp_path,lambda *a:(_ for _ in ()).throw(AssertionError("no probe")),
                            hashlib.sha256(outside.read_bytes()).hexdigest())
    with patch.dict(os.environ,{"GEOFIELD_BREPMFR_CKPT":str(link)}):
        out=check()
    assert not out["available"]
    assert "심볼릭 링크" in " ".join(out["missing"])

def test_core_status_does_not_probe_optional_ml_or_block_backend_startup():
    tree=ast.parse(SOURCE.read_text(encoding="utf-8"))
    funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef)
           and n.name=="capabilities"]
    assert len(funcs)==1
    calls=[]
    def optional_probe():
        calls.append("ML ran")
        return {"available":True}
    scope={"ml_preflight":optional_probe,"detect_ocp":lambda:True,
           "detect_freecad_cmd":lambda *args:None,
           "fea_solver_status":lambda:{"enabled":True},
           "gf_agent_llm_config":lambda:{"configured":False},
           "DB":"synthetic-only-db-path"}
    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(SOURCE),"exec"),scope)
    status=scope["capabilities"](None)
    assert status["cad_analysis"] and status["fea"]
    assert status["ml_probe_state"]=="not_checked_optional"
    assert not status["ml_inference"]
    assert calls==[],"/api/status and bootstrap --check must not perform 55-sec PyTorch probing"
    checked=scope["capabilities"](None,probe_ml=True)
    assert checked["ml_probe_state"]=="checked" and checked["ml_inference"]
    assert calls==["ML ran"]
    original=SOURCE.read_text(encoding="utf-8")
    assert "BrepMFR readiness at /api/ml/preflight (not probed during core startup)" in original
