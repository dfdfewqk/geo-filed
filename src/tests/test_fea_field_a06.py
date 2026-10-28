"""A06 real-FRD field contract with isolated synthetic values; no solver or PC files."""
from __future__ import annotations

import ast
import copy
import math
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from fea_field_a06 import validate_surface_evidence

CAD="a"*64
CASE="b"*64
RUN="1"*32
UID="2"*32
SID="3"*32

def result():
    return {
        "schema":"geofield-fea-result-v1",
        "status":"solver_executed_result_parsed",
        "cad_sha256":CAD,"case_sha256":CASE,
        "results":{"maximum_nodal_von_mises_mpa":24.5,
                   "maximum_displacement_mm":0.055}
    }

def field():
    # Genuine unit keys and provenance schema; numeric fixtures synthetic.
    return {
        "schema":"geofield-fea-surface-field-v1",
        "source":"actual_calculix_ascii_frd",
        "cad_sha256":CAD,"case_sha256":CASE,
        "stress_interpretation":"extrapolated_nodal_stress_not_integration_point",
        "stress_units":"MPa","displacement_units":"mm",
        "visual_scale_factor":1.0,
        "positions_mm":[[0.,0.,0.],[10.,0.,0.],[0.,10.,0.],[0.,0.,10.]],
        "triangles":[[0,1,2],[0,1,3],[0,2,3],[1,2,3]],
        "von_mises_mpa":[5.,19.,12.,8.],
        "displacements_mm":[[0.,0.,0.],[0.,0.,0.025],
                             [0.,0.03,0.],[0.,0.,0.01]],
    }

def verify(data=None, actual=None, **kw):
    return validate_surface_evidence(
        field() if data is None else data,
        result() if actual is None else actual,
        CAD,CASE,RUN,UID,**kw)


def test_verified_surface_maximum_and_real_location_only():
    out=verify()
    s=out["surface_evidence"]
    assert out["run_id"]==RUN
    assert out["cad_job_id"]==UID
    assert s["surface_max_von_mises_mpa"]==19
    assert s["global_max_von_mises_mpa"]==24.5
    assert s["surface_max_displacement_mm"]==pytest.approx(0.03)
    assert s["global_max_displacement_mm"]==0.055
    assert s["surface_stress_peak_position_mm"]==[10.,0.,0.]
    assert s["surface_displacement_peak_position_mm"]==[0.,10.,0.]
    assert s["stress_units"]=="MPa"
    assert s["positions_units"]=="mm"
    assert s["displacement_units"]=="mm"
    assert not s["surface_peak_is_global_stress_peak"]
    assert not s["surface_peak_is_global_displacement_peak"]
    assert s["cad_face_correspondence_verified"] is False
    assert s["stress_concentration_cause_verified"] is False
    assert s["safety_certified"] is False


@pytest.mark.parametrize("change,phrase",[
    (lambda f:f.update(cad_sha256="c"*64),"해시"),
    (lambda f:f.update(case_sha256="c"*64),"해시"),
    (lambda f:f.update(run_id="4"*32),"run_id"),
    (lambda f:f.update(cad_job_id="5"*32),"run_id"),
    (lambda f:f.update(source="synthetic"),"출처"),
    (lambda f:f.update(stress_units="Pa"),"단위"),
    (lambda f:f.update(displacement_units="m"),"단위"),
    (lambda f:f.update(stress_interpretation="element_center"),"단위"),
    (lambda f:f.update(visual_scale_factor=0.),"배율"),
    (lambda f:f.update(visual_scale_factor=float("nan")),"배율"),
    (lambda f:f["von_mises_mpa"].__setitem__(0,float("nan")),"절점 응력"),
    (lambda f:f["von_mises_mpa"].__setitem__(0,-5),"절점 응력"),
    (lambda f:f["von_mises_mpa"].__setitem__(0,True),"절점 응력"),
    (lambda f:f["positions_mm"][0].__setitem__(0,float("inf")),"표면 좌표"),
    (lambda f:f["displacements_mm"][1].__setitem__(0,False),"절점 변위"),
    (lambda f:f["triangles"][0].__setitem__(2,999),"인덱스"),
    (lambda f:f["triangles"][0].__setitem__(2,True),"인덱스"),
    (lambda f:f["triangles"][0].__setitem__(2,1),"인덱스"),
    (lambda f:f["positions_mm"].pop(),"배열"),
    (lambda f:f["von_mises_mpa"].pop(),"배열"),
])
def test_bad_3d_source_values_fail_closed(change,phrase):
    bad=field()
    change(bad)
    with pytest.raises(ValueError,match=phrase):
        verify(bad)


def test_surface_exceeding_global_stress_rejected():
    bad=field()
    bad["von_mises_mpa"][1]=30.0
    with pytest.raises(ValueError,match="초과"):
        verify(bad)


def test_surface_exceeding_global_displacement_rejected():
    bad=field()
    bad["displacements_mm"][2]=[0,0.06,0]
    with pytest.raises(ValueError,match="초과"):
        verify(bad)


def test_global_solver_evidence_identity_and_values_mandatory():
    for change in [
        lambda x:x.update(case_sha256="c"*64),
        lambda x:x.update(status="failed"),
        lambda x:x.update(schema="fake"),
        lambda x:x["results"].update(maximum_displacement_mm=-1),
        lambda x:x["results"].update(maximum_nodal_von_mises_mpa=float("nan")),
    ]:
        bad=result();change(bad)
        with pytest.raises(ValueError):
            verify(actual=bad)


def test_field_none_rejected_but_original_untouched():
    raw=field();original=copy.deepcopy(raw)
    got=verify(raw)
    assert raw==original
    assert "run_id" not in raw
    assert "surface_evidence" not in raw
    assert got is not raw
    with pytest.raises(ValueError):
        verify(None,{"schema":"invalid"})


def test_old_field_that_only_claims_identity_is_not_verified():
    bad=field()
    bad.pop("stress_units")
    with pytest.raises(ValueError,match="단위"):
        verify(bad)


def test_maximum_on_surface_does_not_prove_cad_face_or_safety():
    actual=result()
    actual["results"]["maximum_nodal_von_mises_mpa"]=19.
    actual["results"]["maximum_displacement_mm"]=0.03
    s=verify(actual=actual)["surface_evidence"]
    assert s["surface_peak_is_global_stress_peak"] is True
    assert s["surface_peak_is_global_displacement_peak"] is True
    assert s["cad_face_correspondence_verified"] is False
    assert s["safety_certified"] is False


def test_preview_size_limit_blocks_visual_only():
    with pytest.raises(ValueError,match="크기"):
        verify(max_nodes=3)
    with pytest.raises(ValueError,match="크기"):
        verify(max_triangles=3)


SOURCE=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SOURCE.read_text(encoding="utf-8"))
NAMES={"_a06_archive_field_available","r185_verified_archive_field"}
FUNCS=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
assert len(FUNCS)==len(NAMES)


def test_production_archived_preview_reverifies_second_read_and_discloses_surface():
    scope={
        "valid_uid":lambda x:isinstance(x,str) and len(x)==32,
        "validate_surface_evidence":validate_surface_evidence,
        "r184_verified_archive_numbers":lambda sid:{
            "cad_job_id":UID,"cad_sha256":CAD,"run_id":RUN,
            "case_sha256":CASE,"conditions":{"material":"steel"},
            "maximum_von_mises_mpa":24.5,"maximum_displacement_mm":0.055},
        "restore_payload":lambda *args,**kwargs:(
            {"sha":CAD,"case":{"case_sha256":CASE}},RUN,result(),field()),
        "JOBS_DIR":Path("/synthetic-test-only")
    }
    exec(compile(ast.Module(body=FUNCS,type_ignores=[]),str(SOURCE),"exec"),scope)
    data=scope["r185_verified_archive_field"](SID)
    assert data["source"]=="reverified_actual_calculix_inp_sta_frd"
    assert data["snapshot_id"]==SID
    assert data["field"]["stress_units"]=="MPa"
    assert data["field"]["surface_evidence"]["surface_max_von_mises_mpa"]==19
    assert data["field"]["surface_evidence"]["cad_face_correspondence_verified"] is False
    assert scope["_a06_archive_field_available"](field(),result(),CAD,CASE,RUN,UID) is True


def test_production_archived_preview_refuses_second_run_numeric_mismatch():
    scope={
        "valid_uid":lambda x:isinstance(x,str) and len(x)==32,
        "validate_surface_evidence":validate_surface_evidence,
        "r184_verified_archive_numbers":lambda sid:{
            "cad_job_id":UID,"cad_sha256":CAD,"run_id":RUN,
            "case_sha256":CASE,"conditions":{},
            "maximum_von_mises_mpa":25.0,"maximum_displacement_mm":0.055},
        "restore_payload":lambda *args,**kwargs:(
            {"sha":CAD,"case":{"case_sha256":CASE}},RUN,result(),field()),
        "JOBS_DIR":Path("/synthetic-test-only")
    }
    exec(compile(ast.Module(body=FUNCS,type_ignores=[]),str(SOURCE),"exec"),scope)
    with pytest.raises(ValueError,match="다른 실행"):
        scope["r185_verified_archive_field"](SID)
    broken=field();broken["von_mises_mpa"][1]=26.
    assert scope["_a06_archive_field_available"](broken,result(),CAD,CASE,RUN,UID) is False


def test_current_endpoint_checks_frd_and_session_after_verification():
    # Keep the existing user-facing frontend intact; assert production's
    # endpoint calls the same pure verifier with the actual independent FRD.
    source=SOURCE.read_text(encoding="utf-8")
    assert "payload=validate_surface_evidence(payload,verified,job['sha256']," in source
    assert "latest=r181_current_result_case(active)" in source
    assert "FEA_JOBS.get(rid,{}).get('status')=='complete'" in source
    assert "현재 FEA 결과와 실제 원본 FRD 최댓값이 다릅니다" in source
