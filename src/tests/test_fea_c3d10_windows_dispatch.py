"""Regression for C3D10 archive verification dispatch on existing Windows runtimes.

No fake FEA values are used. This tests only routing and rejection, not the
engineering validity of any CalculiX solve.
"""
import sys
import types
from unittest.mock import patch

import pytest

from fea_result_trust_gate import verify_directory_for_case


def test_c3d10_does_not_use_legacy_private_c3d4_verifier():
    calls = []
    new = types.ModuleType("fea_solver")
    old = types.ModuleType("fea_previous_import")
    def good(folder, case, sha):
        calls.append(("c3d10", folder, sha))
        return {"source": "true_raw_files"}, None
    def reject(*args):
        raise AssertionError("Old C3D4-only verifier must not receive a C3D10 run")
    new.verify_c3d10_archive = good
    old.verify_directory = reject
    with patch.dict(sys.modules, {"fea_solver": new, "fea_previous_import": old}):
        result, field = verify_directory_for_case("archive", {
            "mesh_request": {"element_type": "C3D10"}
        }, "a" * 64)
    assert result == {"source": "true_raw_files"} and field is None
    assert calls == [("c3d10", "archive", "a" * 64)]


def test_existing_default_c3d4_keeps_legacy_verifier():
    old = types.ModuleType("fea_previous_import")
    calls = []
    def original(folder, case, sha):
        calls.append(folder)
        return {"original": True}, None
    old.verify_directory = original
    with patch.dict(sys.modules, {"fea_previous_import": old}):
        result, _ = verify_directory_for_case("old-run", {"mesh_request": {}}, "b" * 64)
    assert result == {"original": True} and calls == ["old-run"]


@pytest.mark.parametrize("mode", ["C3D8", "C3D20", "C3D10_bug", None])
def test_unknown_element_types_rejected(mode):
    with pytest.raises(ValueError, match="요소 형식"):
        verify_directory_for_case("wrong", {"mesh_request": {"element_type": mode}}, "c" * 64)


def test_missing_signed_case_rejected():
    with pytest.raises(ValueError, match="원본 조건"):
        verify_directory_for_case(".", None, "d" * 64)
