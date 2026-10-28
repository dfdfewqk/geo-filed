"""Regression contract: FEA progress must reflect actual reached solver stages.

Only checks source structure; no Windows solver, STEP geometry or private files needed.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "payload"


def _function(path: str, name: str) -> ast.FunctionDef:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _calls(function: ast.FunctionDef, name: str) -> list[ast.Call]:
    return [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    ]


def test_solver_stage_callback_is_optional_and_ordered():
    function = _function("fea_solver.py", "run_real_fea")
    assert function.args.kwonlyargs[-1].arg == "progress_callback"
    assert isinstance(function.args.kw_defaults[-1], ast.Constant)
    assert function.args.kw_defaults[-1].value is None
    stage_calls = [
        call for call in _calls(function, "progress")
        if call.args and isinstance(call.args[0], ast.Constant)
    ]
    stages = [(call.args[0].value, call.lineno) for call in stage_calls]
    assert [name for name, _ in sorted(stages, key=lambda x: x[1])] == [
        "mesh", "solver", "verification"
    ]


def test_backend_forwards_actual_stage_without_inventing_worker_steps():
    function = _function("GeoField_CAD_Analysis.py", "execute_fea")
    source = (ROOT / "GeoField_CAD_Analysis.py").read_text(encoding="utf-8")
    block = ast.get_source_segment(source, function)
    assert block is not None
    assert "progress_callback=report_progress" in block
    assert "별도 Gmsh Python 해석 중 · 세부 단계 확인 불가" in block
    assert "report_progress('verification', '별도 해석 결과 검증 중')" in block
    assert "task.get('status')=='running'" in block
