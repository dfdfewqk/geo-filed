"""Actual GeoField ML preflight fast-path with missing private assets.

Extract the production pure preflight function. Never install a checkpoint or
replace the user's Python and never call an external model/FEA service.
"""
import ast
import hashlib
import os
from pathlib import Path
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"


def source_preflight(root, resolve, expected_sha):
    code=SOURCE.read_text(encoding="utf-8")
    matches=[x for x in ast.parse(code).body if isinstance(x,ast.FunctionDef)
             and x.name=="ml_preflight"]
    assert len(matches)==1
    space={"ROOT":root,"Path":Path,"os":os,
           "REQUIRED_ML":("torch","numpy"),
           "BREPMFR_SHA256":expected_sha,
           "resolve_ml_python":resolve,
           "file_sha256":lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()}
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
