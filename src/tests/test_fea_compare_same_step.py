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
