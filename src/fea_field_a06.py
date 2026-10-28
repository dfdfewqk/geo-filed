"""A06: independently reverified FRD surface field -> display evidence contract.

Pure read-only validator. Does not infer CAD face correspondence, hotspot
causality, strength certification or engineering safety from surface peaks.
"""
from __future__ import annotations

import math
import re

HEX32 = re.compile(r"^[0-9a-f]{32}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _number(value, label, *, nonnegative=False):
    if (type(value) not in (int,float) or not math.isfinite(value) or
            (nonnegative and value < 0)):
        raise ValueError(label + "의 실제 계산 수치가 유효하지 않습니다.")
    return float(value)


def _close_or_below(surface, whole):
    return surface <= whole + max(1e-6 if whole >= 1 else 1e-9,
                                 abs(whole) * 1e-5)


def validate_surface_evidence(field, actual, cad_sha, case_sha, run_id,
                              cad_job_id, *, max_nodes=450000,
                              max_triangles=180000):
    """Validate a genuine independent re-import, not untrusted input JSON.

    Return a *new* verified, run-tagged payload. The FRD global maximum can be
    inside the solid; a smaller surface maximum never identifies that interior
    critical position. The source coordinates are raw millimetres, not
    camera-space transforms.
    """
    if (not isinstance(cad_sha,str) or not HEX64.fullmatch(cad_sha) or
            not isinstance(case_sha,str) or not HEX64.fullmatch(case_sha) or
            not isinstance(run_id,str) or not HEX32.fullmatch(run_id) or
            not isinstance(cad_job_id,str) or not HEX32.fullmatch(cad_job_id)):
        raise ValueError("FEA 3D 데이터 실행·CAD·조건 ID 형식 오류")
    if (not isinstance(actual,dict) or
            actual.get("schema") != "geofield-fea-result-v1" or
            actual.get("status") != "solver_executed_result_parsed" or
            actual.get("cad_sha256") != cad_sha or
            actual.get("case_sha256") != case_sha):
        raise ValueError("FEA 3D 데이터와 독립 검증된 솔버 결과가 일치하지 않습니다.")
    numbers = actual.get("results")
    if not isinstance(numbers,dict):
        raise ValueError("실제 솔버의 최대 응력·변위 수치가 없습니다.")
    global_stress = _number(numbers.get("maximum_nodal_von_mises_mpa"),
                            "전체 절점 최대 응력", nonnegative=True)
    global_disp = _number(numbers.get("maximum_displacement_mm"),
                          "전체 절점 최대 변위", nonnegative=True)

    if (not isinstance(field,dict) or
            field.get("schema") != "geofield-fea-surface-field-v1" or
            field.get("source") != "actual_calculix_ascii_frd" or
            field.get("cad_sha256") != cad_sha or
            field.get("case_sha256") != case_sha or
            field.get("run_id",run_id) != run_id or
            field.get("cad_job_id",cad_job_id) != cad_job_id):
        raise ValueError("FEA 표면 필드 출처·run_id·CAD·조건 해시 불일치")
    if (field.get("stress_units") != "MPa" or
            field.get("displacement_units") != "mm" or
            field.get("stress_interpretation") !=
                "extrapolated_nodal_stress_not_integration_point"):
        raise ValueError("FEA 3D 수치 단위 또는 절점 응력 해석 방식이 일치하지 않습니다.")
    scale = field.get("visual_scale_factor")
    if (type(scale) not in (int,float) or
            not math.isfinite(scale) or scale <= 0):
        raise ValueError("FEA 변위 표시 배율이 누락되거나 잘못됐습니다.")

    pts, faces = field.get("positions_mm"), field.get("triangles")
    vm, disp = field.get("von_mises_mpa"), field.get("displacements_mm")
    if (not all(isinstance(x,list) for x in (pts,faces,vm,disp)) or
            not 3 <= len(pts) <= max_nodes or
            not 1 <= len(faces) <= max_triangles or
            len(vm) != len(pts) or len(disp) != len(pts)):
        raise ValueError("FEA 3D 표면 배열 길이·크기 제한 오류")

    max_stress = -1.0
    max_disp = -1.0
    stress_pos = disp_pos = None
    for p,v,s in zip(pts,disp,vm):
        if (not isinstance(p,list) or not isinstance(v,list) or
                len(p) != 3 or len(v) != 3):
            raise ValueError("FEA 좌표/변위는 mm 단위 3D 벡터여야 합니다.")
        position = [_number(x,"표면 좌표") for x in p]
        displacement = [_number(x,"절점 변위") for x in v]
        stress = _number(s,"절점 응력",nonnegative=True)
        length = math.hypot(*displacement)
        if stress > max_stress:
            max_stress = stress
            stress_pos = position
        if length > max_disp:
            max_disp = length
            disp_pos = position
    for triangle in faces:
        if (not isinstance(triangle,list) or len(triangle)!=3 or
                any(type(i) is not int or i<0 or i>=len(pts) for i in triangle) or
                len(set(triangle))!=3):
            raise ValueError("FEA 표면 삼각형 절점 연결이 잘못됐습니다.")
    if not (_close_or_below(max_stress,global_stress) and
            _close_or_below(max_disp,global_disp)):
        raise ValueError("FEA 표면 최대값이 실제 FRD 전체 절점 최대값을 초과합니다.")

    # The maxima are two different kinds of location: an observed surface
    # nodal peak, and a global maximum that might lie in the interior.
    # Do not infer correspondence to a CAD face or stress concentration cause.
    surface = {
        "source": "reverified_actual_calculix_frd_surface_nodes",
        "run_id": run_id,
        "cad_sha256": cad_sha,
        "case_sha256": case_sha,
        "stress_units": "MPa",
        "displacement_units": "mm",
        "positions_units": "mm",
        "surface_max_von_mises_mpa": max_stress,
        "surface_max_displacement_mm": max_disp,
        "global_max_von_mises_mpa": global_stress,
        "global_max_displacement_mm": global_disp,
        "surface_stress_peak_position_mm": stress_pos,
        "surface_displacement_peak_position_mm": disp_pos,
        "surface_peak_is_global_stress_peak": math.isclose(
            max_stress,global_stress,rel_tol=1e-5,abs_tol=1e-6),
        "surface_peak_is_global_displacement_peak": math.isclose(
            max_disp,global_disp,rel_tol=1e-5,abs_tol=1e-9),
        "cad_face_correspondence_verified": False,
        "stress_concentration_cause_verified": False,
        "safety_certified": False,
        "note": ("표면에서 실제 확인된 절점 최댓값·좌표입니다. "
                 "전체 최대 절점이 표면 밖에 있을 수 있으며 CAD 특정 면이나 응력 원인을 확정하지 않습니다.")
    }
    return {**field,"run_id":run_id,"cad_job_id":cad_job_id,
            "surface_evidence":surface}
