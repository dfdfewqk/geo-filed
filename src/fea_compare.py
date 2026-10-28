# GeoField R18.7 genuine FEA mesh sensitivity study
"""R18: read-only, evidence-verified comparison of two archived FEA results.

This module NEVER triggers a solver, modifies a session or writes existing CAD,
SQLite or FEA files. The two saved solver runs are independently re-verified.
"""
from __future__ import annotations
import math
import re
import contextlib
import sqlite3
from pathlib import Path
from fea_restore import restore_payload

HEX_ID = re.compile(r'^[0-9a-f]{32}$')

def _finite_positive(value, label, allow_zero=True):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (not allow_zero and value == 0):
        raise ValueError(f'{label}: 저장된 FEA 결과값이 유효하지 않습니다.')
    return float(value)

def _side(db, jobs_dir, snapshot_id):
    if not isinstance(snapshot_id, str) or not HEX_ID.fullmatch(snapshot_id):
        raise ValueError('분석 기록 ID 형식이 올바르지 않습니다.')
    db = Path(db)
    if not db.is_file():
        raise ValueError('기존 분석 기록 데이터베이스가 없습니다.')
    # Read-only SQLite URI: never create or migrate the user's existing store.
    with contextlib.closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=5)) as con:
        row = con.execute('SELECT stage, job_id, cad_sha256, cad_name, created_at, summary_json FROM snapshots WHERE id=?', (snapshot_id,)).fetchone()
    if row is None or row[0] != 'fea_result':
        raise ValueError('선택한 항목은 실제 FEA 계산 완료 기록이 아닙니다.')
    import json
    try: summary = json.loads(row[5])
    except (TypeError, ValueError): raise ValueError('저장된 분석 요약이 손상됐습니다.')
    fea = summary.get('fea') or {}
    cad_summary = summary.get('cad') or {}
    rid = fea.get('result_run_id')
    if fea.get('state') != 'complete' or not isinstance(rid, str) or not HEX_ID.fullmatch(rid):
        raise ValueError('실제 계산 실행 ID가 보존되지 않아 비교할 수 없습니다.')
    if not HEX_ID.fullmatch(str(row[1])):
        raise ValueError('보존된 CAD 작업 ID 형식 오류')
    # Reads actual .inp/.sta/.frd files; rejects missing, corrupted or mismatched evidence.
    cad, actual_rid, result, _field = restore_payload(jobs_dir, row[1], run_hint=rid)
    if actual_rid != rid or cad['sha'] != row[2] or cad['sha'] != cad_summary.get('sha256'):
        raise ValueError('실제 CalculiX 파일과 보존된 CAD 식별자가 일치하지 않습니다.')
    numbers = result.get('results') or {}
    stress = _finite_positive(numbers.get('maximum_nodal_von_mises_mpa'), '응력')
    disp = _finite_positive(numbers.get('maximum_displacement_mm'), '변위')
    old_stress = _finite_positive(fea.get('maximum_von_mises_mpa'), '당시 응력 기록')
    old_disp = _finite_positive(fea.get('maximum_displacement_mm'), '당시 변위 기록')
    if not math.isclose(stress, old_stress, rel_tol=1e-6, abs_tol=1e-8) or not math.isclose(disp, old_disp, rel_tol=1e-6, abs_tol=1e-9):
        raise ValueError('계산 파일과 분석 이력의 응력·변위 값이 일치하지 않습니다.')
    case = cad['case']
    mat = case.get('material') or {}
    bc = case.get('boundary_conditions') or {}
    preset = case.get('preset_metadata') or {}
    mesh = case.get('mesh_request') or {}
    if (case.get('cad_sha256') != cad['sha'] or
        result.get('cad_sha256') != cad['sha'] or
        result.get('case_sha256') != case.get('case_sha256') or
        fea.get('result_case_sha256') != case.get('case_sha256')):
        raise ValueError('SQLite 기록과 실제 CalculiX CAD·FEA 조건 서명이 일치하지 않습니다.')
    self_weight = case.get('self_weight_reference') or {}
    enabled = self_weight.get('applied_to_solver',False)
    if type(enabled) is not bool:
        raise ValueError('자중 활성화 조건이 잘못됐습니다.')
    density = self_weight.get('reference_density_kg_m3') if enabled else None
    direction = self_weight.get('gravity_direction') if enabled else None
    accel = self_weight.get('gravity_mm_s2') if enabled else None
    mesh_result = result.get('mesh') or {}
    element_type = mesh.get('element_type','C3D4')
    if element_type not in ('C3D4','C3D10') or mesh_result.get('element_type','C3D4') != element_type:
        raise ValueError('보존된 요소 차수와 실제 계산 결과가 일치하지 않습니다.')
    traction_model=mesh.get('traction_model','free_node_moment_equivalent')
    actual_traction=mesh_result.get('traction_model','free_node_moment_equivalent')
    if (traction_model not in ('free_node_moment_equivalent','straight_tri6_full_consistent') or
        actual_traction!=traction_model or
        (traction_model=='straight_tri6_full_consistent' and element_type!='C3D10')):
        raise ValueError('실제 CalculiX 표면 하중 방식과 보존된 조건이 다릅니다.')
    return {'snapshot_id': snapshot_id, 'created_at': row[4], 'cad_name': row[3],
            'cad_sha256': cad['sha'], 'run_id': rid, 'case_sha256': case['case_sha256'],
            'material': mat.get('name',''), 'young_modulus_mpa': mat.get('young_modulus_mpa'),
            'poisson_ratio': mat.get('poisson_ratio'),
            'fixed_faces': bc.get('fixed_face_ids'), 'load_faces': bc.get('load_face_ids'),
            'force_n': bc.get('total_force_n'), 'direction': bc.get('force_direction_unit'),
            'external_mass_kg': preset.get('mass_kg'),
            'mesh_target_mm': mesh.get('target_element_size_mm'),
            'element_type':element_type, 'traction_model':traction_model,
            'mesh_node_count': mesh_result.get('node_count'),
            'mesh_tetrahedron_count': mesh_result.get('tetrahedron_count'),
            'solver':result.get('solver'), 'mesher':result.get('mesher'),
            'analysis_type':case.get('analysis_type'),
            'load_interpretation':bc.get('load_interpretation'),
            'self_weight_applied':enabled, 'gravity_density_kg_m3':density, 'gravity_direction':direction, 'gravity_mm_s2':accel,
            'max_stress_mpa': stress, 'max_displacement_mm': disp,
            'evidence':'real_solver_files_revalidated',
            'mesh_convergence':'not_verified'}

def compare(db, jobs_dir, left_id, right_id):
    if left_id == right_id:
        raise ValueError('비교할 두 계산 기록을 서로 다르게 선택하세요.')
    left = _side(db, jobs_dir, left_id)
    right = _side(db, jobs_dir, right_id)
    if left['run_id'] == right['run_id']:
        raise ValueError('같은 실제 계산 실행을 두 번 비교할 수 없습니다.')
    # Only the exact same STEP bytes may be compared. A matching filename,
    # dimensions or geometry is not proof of identical analysis input.
    left_sha, right_sha = left.get('cad_sha256'), right.get('cad_sha256')
    if (not isinstance(left_sha, str) or not isinstance(right_sha, str) or
            not re.fullmatch(r'[0-9a-f]{64}', left_sha) or
            not re.fullmatch(r'[0-9a-f]{64}', right_sha)):
        raise ValueError('STEP 원본 SHA-256을 검증할 수 없어 FEA 기록 비교를 제한합니다.')
    if left_sha != right_sha:
        raise ValueError('서로 다른 STEP 원본의 FEA 기록은 비교할 수 없습니다.')
    def delta(name):
        a, b = left[name], right[name]
        return {'absolute_difference': b-a,
                'percent_vs_left': ((b-a)/a*100 if a else None)}
    return {'status':'verified_read_only_comparison', 'left':left, 'right':right,
            'same_cad':left['cad_sha256']==right['cad_sha256'],
            'same_material':all(left[k]==right[k] for k in ('material','young_modulus_mpa','poisson_ratio')),
            'same_boundary_conditions':all(left[k]==right[k] for k in (
                'fixed_faces','load_faces','force_n','direction',
                'external_mass_kg','load_interpretation','self_weight_applied',
                'gravity_density_kg_m3','gravity_direction','gravity_mm_s2')),
            'same_mesh_target':left['mesh_target_mm']==right['mesh_target_mm'],
            'same_element_type':left['element_type']==right['element_type'],
            'same_traction_model':left['traction_model']==right['traction_model'],
            'stress_change':delta('max_stress_mpa'),
            'displacement_change':delta('max_displacement_mm'),
            'message':'이 비교는 서로 다른 실제 CalculiX 계산 파일을 읽어 만든 수치 비교입니다. 재료·하중·경계조건·메시가 다르면 변화 원인을 단정할 수 없으며, 구조 안전성·메시 수렴은 검증하지 않았습니다.'}
