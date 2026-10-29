"""Read-only, real-source R12 preflight regressions; no private engine or installer."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

BRIDGE=Path(__file__).resolve().parents[1]/"payload"/"ml_r12_bridge.py"
REPORT=Path(__file__).resolve().parents[1]/"payload"/"ml"/"r12_research"/"report.json"


def live_preflight(root, resolver, expected_sha):
    tree=ast.parse(BRIDGE.read_text(encoding="utf-8"))
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)
           and n.name in ("locations","preflight")]
    assert len(nodes)==2
    scope={"Path":Path,"json":json,"EXPECTED_MODEL_SHA256":expected_sha,
           "REQUIRED":("cadquery","OCP","numpy","sklearn","joblib"),
           "sha":lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest(),
           "resolve":resolver}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(BRIDGE),"exec"),scope)
    return scope["preflight"]


def put_assets(root):
    dest=root/"ml"/"r12_research"
    dest.mkdir(parents=True)
    model=dest/"research_model.joblib"
    model.write_bytes(b"trusted synthetic model bytes, not to be loaded")
    expected=hashlib.sha256(model.read_bytes()).hexdigest()
    record=json.loads(REPORT.read_text(encoding="utf-8"))
    record["model_sha256"]=expected
    (dest/"report.json").write_text(json.dumps(record),encoding="utf-8")
    for name in ("worker.py","features.py","train_eval.py","build_data.py"):
        (dest/name).write_text("# real module presence is tested separately\n",encoding="utf-8")
    return dest,model,expected


def test_absent_r12_assets_never_block_cad_with_python_probe(tmp_path):
    resolver=Mock(side_effect=AssertionError("must not discover Python without model"))
    state=live_preflight(tmp_path,resolver,"e"*64)(tmp_path)
    assert not state["available"]
    assert state["python"] is None
    assert state["python_source"]=="skipped_missing_or_untrusted_assets"
    assert "R12 연구 모델 파일이 없습니다." in state["missing"]
    resolver.assert_not_called()


def test_corrupted_r12_model_does_not_probe_python(tmp_path):
    root,model,expected=put_assets(tmp_path)
    model.write_bytes(model.read_bytes()+b"-tampered")
    resolver=Mock(side_effect=AssertionError("must not run Python on wrong model hash"))
    state=live_preflight(tmp_path,resolver,expected)(tmp_path)
    assert not state["available"]
    assert "모델 해시" in state["missing"][0]
    resolver.assert_not_called()


def test_missing_required_worker_file_stops_before_python_probe(tmp_path):
    folder,_,expected=put_assets(tmp_path)
    (folder/"train_eval.py").unlink()
    resolver=Mock(side_effect=AssertionError("do not resolve Python when worker missing"))
    state=live_preflight(tmp_path,resolver,expected)(tmp_path)
    assert "R12 모듈 누락: train_eval.py" in state["missing"][0]
    resolver.assert_not_called()


def test_matching_assets_probe_once_and_require_real_imports(tmp_path):
    _,_,expected=put_assets(tmp_path)
    resolver=Mock(return_value={"ok":True,"path":"python-for-ML",
                                "source":"verified_existing_python","attempts":[],
                                "modules":{"cadquery":True,"OCP":True}})
    state=live_preflight(tmp_path,resolver,expected)(tmp_path)
    assert state["available"] and state["python"]=="python-for-ML"
    resolver.assert_called_once_with(
        "GEOFIELD_R12_PYTHON",("cadquery","OCP","numpy","sklearn","joblib"))


def test_invalid_python_import_does_not_claim_ml_ready(tmp_path):
    _,_,expected=put_assets(tmp_path)
    resolver=Mock(return_value={"ok":False,"path":None,"error":"OCP DLL failed",
                                "modules":{"OCP":"ImportError"},"attempts":[]})
    state=live_preflight(tmp_path,resolver,expected)(tmp_path)
    assert not state["available"]
    assert "R12 Python 필수 모듈 미탐지" in state["missing"][0]
