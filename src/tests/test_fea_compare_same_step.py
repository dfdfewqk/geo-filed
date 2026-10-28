"""Regression tests for verified, read-only FEA history comparisons.

The comparison policy is exercised without an installed Windows solver, SQLite
database, STEP files or private user data.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "fea_compare.py"


def _module():
    # The real restore module lives in the installed Windows GeoField runtime.
    fake_restore = types.ModuleType("fea_restore")
    fake_restore.restore_payload = lambda *args, **kwargs: None
    with patch.dict(sys.modules, {"fea_restore": fake_restore}):
        spec = importlib.util.spec_from_file_location("geofield_compare_regression", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return module


def _side(sha, run_id, stress, displacement, mesh_target=2.0):
    return {
        "cad_sha256": sha, "run_id": run_id,
        "material": "steel", "young_modulus_mpa": 200000,
        "poisson_ratio": 0.3, "fixed_faces": [1], "load_faces": [2],
        "force_n": 49.05, "direction": [0, 0, -1],
        "external_mass_kg": 5.0, "load_interpretation": "gravity_equivalent",
        "self_weight_applied": False, "gravity_density_kg_m3": None,
        "gravity_direction": None, "gravity_mm_s2": None,
        "mesh_target_mm": mesh_target, "element_type": "C3D4",
        "traction_model": "free_node_moment_equivalent",
        "max_stress_mpa": stress, "max_displacement_mm": displacement,
    }


def _compare(left, right):
    module = _module()
    with patch.object(module, "_side", side_effect=[left, right]) as mocked:
        result = module.compare("readonly-history.sqlite3", "fea-runs", "a" * 32, "b" * 32)
    assert mocked.call_count == 2
    return result


def test_different_step_sha_is_not_comparable():
    left = _side("a" * 64, "1" * 32, 20.0, 0.01)
    right = _side("b" * 64, "2" * 32, 25.0, 0.015)
    with pytest.raises(ValueError, match="서로 다른 STEP 원본"):
        _compare(left, right)


def test_unknown_step_sha_is_not_assumed_identical():
    left = _side("", "1" * 32, 20.0, 0.01)
    right = _side("", "2" * 32, 25.0, 0.015)
    with pytest.raises(ValueError, match="SHA-256"):
        _compare(left, right)


def test_same_step_but_different_mesh_can_be_compared():
    left = _side("a" * 64, "1" * 32, 20.0, 0.01, 2.0)
    right = _side("a" * 64, "2" * 32, 25.0, 0.015, 1.0)
    result = _compare(left, right)
    assert result["same_cad"] is True
    assert result["same_mesh_target"] is False
    assert result["stress_change"]["absolute_difference"] == pytest.approx(5.0)
    assert result["stress_change"]["percent_vs_left"] == pytest.approx(25.0)
    assert result["displacement_change"]["percent_vs_left"] == pytest.approx(50.0)


def test_zero_baseline_has_no_invented_percentage():
    left = _side("a" * 64, "1" * 32, 0.0, 0.0)
    right = _side("a" * 64, "2" * 32, 10.0, 0.01)
    result = _compare(left, right)
    assert result["stress_change"]["absolute_difference"] == pytest.approx(10.0)
    assert result["stress_change"]["percent_vs_left"] is None
    assert result["displacement_change"]["percent_vs_left"] is None


def test_changed_self_weight_is_not_same_boundary_condition():
    left = _side("a" * 64, "1" * 32, 20.0, 0.01)
    right = _side("a" * 64, "2" * 32, 25.0, 0.015)
    right["self_weight_applied"] = True
    right["gravity_density_kg_m3"] = 7850.0
    right["gravity_direction"] = [0, 0, -1]
    right["gravity_mm_s2"] = 9810.0
    result = _compare(left, right)
    assert result["same_boundary_conditions"] is False


def test_changed_external_mass_or_load_model_not_same_boundary_condition():
    left = _side("a" * 64, "1" * 32, 20.0, 0.01)
    right = _side("a" * 64, "2" * 32, 25.0, 0.015)
    for key, changed in (("external_mass_kg", 6.0),
                         ("load_interpretation", "distributed_surface_force")):
        changed_right = dict(right, **{key: changed})
        assert _compare(left, changed_right)["same_boundary_conditions"] is False


def test_exact_same_physics_keeps_boundary_flag_true():
    left = _side("a" * 64, "1" * 32, 20.0, 0.01)
    right = _side("a" * 64, "2" * 32, 25.0, 0.015)
    result = _compare(left, right)
    assert result["same_boundary_conditions"] is True


def test_partial_saved_stress_uses_only_verified_displacement():
    left = _side("a" * 64, "1" * 32, None, 0.01)
    right = _side("a" * 64, "2" * 32, 25.0, 0.015)
    result = _compare(left, right)
    assert result["stress_change"] == {"absolute_difference": None, "percent_vs_left": None}
    assert result["displacement_change"]["absolute_difference"] == pytest.approx(0.005)
    assert result["unavailable_metrics"] == ["응력"]
    assert "누락" in result["message"]


def test_partial_displacement_uses_only_verified_stress():
    left = _side("a" * 64, "1" * 32, 20.0, 0.01)
    right = _side("a" * 64, "2" * 32, 25.0, None)
    result = _compare(left, right)
    assert result["stress_change"]["percent_vs_left"] == pytest.approx(25.0)
    assert result["displacement_change"] == {"absolute_difference": None, "percent_vs_left": None}
    assert result["unavailable_metrics"] == ["변위"]


def test_no_common_verified_metric_is_rejected():
    left = _side("a" * 64, "1" * 32, 20.0, None)
    right = _side("a" * 64, "2" * 32, None, 0.01)
    with pytest.raises(ValueError, match="함께 검증된"):
        _compare(left, right)


@pytest.mark.parametrize("invalid", ["NaN", float("nan"), -1, True, float("inf")])
def test_invalid_metric_never_passes_as_missing(invalid):
    left = _side("a" * 64, "1" * 32, invalid, 0.01)
    right = _side("a" * 64, "2" * 32, 25.0, 0.015)
    with pytest.raises(ValueError, match="유효하지"):
        _compare(left, right)


def test_strict_side_still_requires_both_numbers_but_comparator_allows_missing(tmp_path):
    import json
    import sqlite3
    module = _module()
    cad_sha, case_sha = "a"*64, "b"*64
    uid, rid, snapshot = "1"*32, "2"*32, "3"*32
    db = tmp_path/"archived.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE snapshots (stage TEXT, job_id TEXT, cad_sha256 TEXT, cad_name TEXT, created_at TEXT, summary_json TEXT, id TEXT)")
        con.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?)",(
            "fea_result",uid,cad_sha,"sample","2026-10-28",json.dumps({
                "cad":{"sha256":cad_sha},
                "fea":{"state":"complete","result_run_id":rid,"result_case_sha256":case_sha,
                       "maximum_displacement_mm":0.015}
            }),snapshot))
    frozen_case={
        "cad_sha256":cad_sha,"case_sha256":case_sha,
        "material":{"name":"steel"},
        "boundary_conditions":{"fixed_face_ids":[1],"load_face_ids":[2],
                               "total_force_n":49.05,"force_direction_unit":[0,0,-1]},
        "mesh_request":{"element_type":"C3D4"}
    }
    solver_result={
        "cad_sha256":cad_sha,"case_sha256":case_sha,
        "results":{"maximum_nodal_von_mises_mpa":25.0,
                   "maximum_displacement_mm":0.015},
        "mesh":{"element_type":"C3D4"}
    }
    original = lambda *_args,**_kwargs: (
        {"sha":cad_sha,"case":frozen_case},rid,solver_result,None)
    with patch.object(module,"restore_payload",side_effect=original):
        with pytest.raises(ValueError,match="누락"):
            module._side(db,tmp_path,snapshot)
        partial = module._side(db,tmp_path,snapshot,allow_partial=True)
    assert partial["max_stress_mpa"] is None
    assert partial["max_displacement_mm"] == pytest.approx(0.015)
    # A comparison must not write or replace the user's historic SQLite database.
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 1


def test_nonmissing_wrong_stress_not_suppressed_by_partial_mode(tmp_path):
    import json
    import sqlite3
    module = _module()
    cad_sha,case_sha="a"*64,"b"*64
    uid,rid,snapshot="1"*32,"2"*32,"3"*32
    db=tmp_path/"archive.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE snapshots (stage TEXT, job_id TEXT, cad_sha256 TEXT, cad_name TEXT, created_at TEXT, summary_json TEXT, id TEXT)")
        con.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?,?)",(
            "fea_result",uid,cad_sha,"part","2026-10-28",json.dumps({
                "cad":{"sha256":cad_sha},
                "fea":{"state":"complete","result_run_id":rid,"result_case_sha256":case_sha,
                       "maximum_von_mises_mpa":999.0,"maximum_displacement_mm":0.015}
            }),snapshot))
    result={"cad_sha256":cad_sha,"case_sha256":case_sha,
            "results":{"maximum_nodal_von_mises_mpa":25.0,"maximum_displacement_mm":0.015},
            "mesh":{}}
    cad={"sha":cad_sha,"case":{"cad_sha256":cad_sha,"case_sha256":case_sha}}
    with patch.object(module,"restore_payload",return_value=(cad,rid,result,None)):
        with pytest.raises(ValueError,match="일치하지"):
            module._side(db,tmp_path,snapshot,allow_partial=True)
