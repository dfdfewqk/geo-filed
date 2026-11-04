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

def _side(db, jobs_dir, snapshot_id, *, allow_partial=False):
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
    # Only the two-record comparison is permitted to omit an unavailable
    # measurement. Report/restoration/convergence callers remain strict.
    # Invalid values (NaN, booleans, negatives) and disagreements always fail.
    def verified_measure(actual_key, saved_key, label, atol):
        actual = numbers.get(actual_key)
        saved = fea.get(saved_key)
        if actual is not None:
            actual = _finite_positive(actual, label)
        if saved is not None:
            saved = _finite_positive(saved, '당시 '+label+' 기록')
        if actual is None or saved is None:
            if allow_partial:
                return None
            raise ValueError(label + ': 저장된 FEA 계산 수치가 누락됐습니다.')
        if not math.isclose(actual, saved, rel_tol=1e-6, abs_tol=atol):
            raise ValueError('계산 파일과 분석 이력의 응력·변위 값이 일치하지 않습니다: '+label)
        return actual
    stress = verified_measure('maximum_nodal_von_mises_mpa','maximum_von_mises_mpa','응력',1e-8)
    disp = verified_measure('maximum_displacement_mm','maximum_displacement_mm','변위',1e-9)
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
    left = _side(db, jobs_dir, left_id, allow_partial=True)
    right = _side(db, jobs_dir, right_id, allow_partial=True)
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
    metric_keys = (('max_stress_mpa','응력'),('max_displacement_mm','변위'))
    for side in (left,right):
        for name,label in metric_keys:
            if side.get(name) is not None:
                _finite_positive(side[name],label)
    missing = [label for name,label in metric_keys
               if left.get(name) is None or right.get(name) is None]
    if len(missing)==2:
        raise ValueError('두 FEA 기록에 함께 검증된 응력·변위 비교 항목이 없습니다.')
    def delta(name):
        a, b = left[name], right[name]
        if a is None or b is None:
            return {'absolute_difference':None,'percent_vs_left':None}
        return {'absolute_difference': b-a,
                'percent_vs_left': ((b-a)/a*100 if a else None)}
    return {'status':'verified_read_only_comparison', 'left':left, 'right':right,
            'unavailable_metrics':missing,
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
            'message':('이 비교는 서로 다른 실제 CalculiX 계산 파일을 읽어 만든 수치 비교입니다. '
                       '재료·하중·경계조건·메시가 다르면 변화 원인을 단정할 수 없으며, 구조 안전성·메시 수렴은 검증하지 않았습니다.'
                       + (' 저장된 계산값의 누락으로 비교하지 못한 항목: '+', '.join(missing)+'.' if missing else ''))}


# GEOFIELD_D6_CROSS_GEOMETRY_COMPARE_V1
def compare_d6_geometry_variant(db, jobs_dir, original_snapshot_id, variant_snapshot_id,
                                variant_link, *, load_side=None, load_physics=None):
    """Descriptive two-geometry FEA comparison; NEVER approve a redesign.

    Existing compare() deliberately rejects a different STEP SHA. Preserve it.
    Only a prior server-side OCC-verified D5.5 -> D6.0 link and two separately
    reverified SQLite/INP/STA/FRD snapshots permit an observational delta.
    Different support/load face indices must NOT be reused or treated as a proof
    of equivalent physical locations or load moment.
    """
    if original_snapshot_id == variant_snapshot_id:
        raise ValueError('동일한 FEA 기록 두 개로 설계변경을 비교할 수 없습니다.')
    if not isinstance(variant_link,dict) or (
        variant_link.get('operation')!='lbracket_d55_to_d60_4_through_copy_v1' or
        variant_link.get('source')!='server_OCP_postexport_reverified' or
        variant_link.get('geometry_only_verified') is not True or
        variant_link.get('structural_improvement_verified') is not False or
        variant_link.get('needs_new_face_selection') is not True):
        raise ValueError('원본-변경본 형상 생성 근거가 확인되지 않습니다.')
    origin=variant_link.get('source_sha256')
    variant=variant_link.get('variant_sha256')
    if not (isinstance(origin,str) and isinstance(variant,str) and
            re.fullmatch(r'[0-9a-f]{64}',origin) and
            re.fullmatch(r'[0-9a-f]{64}',variant) and origin!=variant):
        raise ValueError('원본과 변경본의 CAD SHA 연결이 잘못됐습니다.')

    side=_side if load_side is None else load_side
    a=side(db,jobs_dir,original_snapshot_id)
    b=side(db,jobs_dir,variant_snapshot_id)
    if (a.get('snapshot_id')!=original_snapshot_id or
        b.get('snapshot_id')!=variant_snapshot_id or
        a.get('cad_sha256')!=origin or b.get('cad_sha256')!=variant):
        raise ValueError('실제 FEA 계산 기록의 CAD SHA와 OCC 변형 근거가 불일치합니다.')
    if a.get('run_id')==b.get('run_id') or a.get('case_sha256')==b.get('case_sha256'):
        raise ValueError('독립된 서로 다른 형상 FEA 계산이 아닙니다.')
    if a.get('evidence')!='real_solver_files_revalidated' or b.get('evidence')!='real_solver_files_revalidated':
        raise ValueError('원본과 변경본 각각의 INP·STA·FRD가 독립 검증되지 않았습니다.')

    def finite(name, row, *, positive=False):
        val=row.get(name)
        if type(val) not in (int,float) or not math.isfinite(val) or val<0 or (positive and val==0):
            raise ValueError('계산 근거에 필요한 값이 누락되거나 잘못됐습니다: '+name)
        return float(val)

    for item in (a,b):
        finite('max_stress_mpa',item)
        finite('max_displacement_mm',item)
        finite('force_n',item,positive=True)
        finite('young_modulus_mpa',item,positive=True)
        finite('mesh_target_mm',item,positive=True)
        n=item.get('mesh_node_count')
        t=item.get('mesh_tetrahedron_count')
        if type(n) is not int or n<=0 or type(t) is not int or t<=0:
            raise ValueError('실제 메시 절점/요소 수를 재확인할 수 없습니다.')
        d=item.get('direction')
        if (not isinstance(d,list) or len(d)!=3 or
            any(type(x) not in (int,float) or not math.isfinite(x) for x in d)):
            raise ValueError('FEA 하중 방향을 재확인할 수 없습니다.')
        if (not isinstance(item.get('fixed_faces'),list) or
            not item['fixed_faces'] or
            not isinstance(item.get('load_faces'),list) or
            not item['load_faces']):
            raise ValueError('새 형상에서 고정면 및 하중면의 재선택 여부를 확인할 수 없습니다.')

    # Compare physical/material inputs, not face IDs: a changed STEP reindexes
    # faces. Equal face IDs or equal net force DO NOT prove equivalent supports.
    string_keys=('material','solver','mesher','analysis_type','load_interpretation',
                 'element_type','traction_model')
    numeric_keys=('young_modulus_mpa','poisson_ratio','force_n','external_mass_kg',
                  'mesh_target_mm','gravity_density_kg_m3','gravity_mm_s2')
    for key in string_keys:
        if (not isinstance(a.get(key),str) or not a.get(key) or a.get(key)!=b.get(key)):
            raise ValueError('재료/해석 입력이 서로 달라 비교를 보류합니다: '+key)
    def same_numeric(key):
        x,y=a.get(key),b.get(key)
        if x is None and y is None:
            return True
        return (type(x) in (int,float) and type(y) in (int,float) and
                math.isfinite(x) and math.isfinite(y) and
                math.isclose(x,y,rel_tol=1e-9,abs_tol=1e-9))
    for key in numeric_keys:
        if not same_numeric(key):
            raise ValueError('기하 변경 외의 재료·하중·메시 입력이 달라 비교를 보류합니다: '+key)
    for key in ('direction','gravity_direction'):
        if a.get(key)!=b.get(key):
            raise ValueError('하중 또는 자중 방향이 달라 비교를 보류합니다.')
    if a.get('self_weight_applied')!=b.get('self_weight_applied'):
        raise ValueError('자중 적용 조건이 달라 비교를 보류합니다.')
    if type(a.get('self_weight_applied')) is not bool:
        raise ValueError('기존 자중 적용 상태를 확인할 수 없습니다.')
    if a['self_weight_applied'] is True:
        # Changing the actual CAD volume changes total gravitational body
        # force even when material density/acceleration are held constant.
        raise ValueError('실제 솔리드 체적이 다른 두 형상의 자중은 동일한 물리 하중이 아닙니다.')

    # The existing genuine INP force/moment verifier is the authority.
    # This additional cross-STEP screen checks FIXED + LOADED spatial bounds.
    # It cannot prove identical face sets, reaction distributions or safety.
    if load_physics is None:
        from fea_load_moment import screen_two_geometry_verified_inp
        load_physics=screen_two_geometry_verified_inp
    screen=load_physics(jobs_dir,a,b)
    if (not isinstance(screen,dict) or
        screen.get('status')!='real_two_inp_load_support_screen_passed' or
        screen.get('source')!='two_real_reverified_inp_decks_node_boundary_cload' or
        screen.get('read_only') is not True or
        screen.get('gravity_body_loads_included') is not False or
        screen.get('support_bounding_screen_passed') is not True or
        screen.get('applied_load_and_moment_screen_passed') is not True or
        screen.get('physical_cad_surface_correspondence_verified') is not False or
        screen.get('reaction_equilibrium_correspondence_verified') is not False or
        screen.get('geometry_improvement_verified') is not False or
        screen.get('structural_safety_certified') is not False):
        raise ValueError('원본과 변경본 실제 하중·고정 영역 비교 검증에 실패했습니다.')
    drift_fields=('support_bbox_max_drift_mm','load_bbox_max_drift_mm',
                  'load_center_distance_mm','resultant_drift_n',
                  'load_moment_change_n_mm',
                  'load_moment_equivalent_lever_arm_change_mm')
    if any(type(screen.get(k)) not in (int,float) or not math.isfinite(screen[k]) or
           screen[k]<0 for k in drift_fields):
        raise ValueError('실제 하중·고정 비교 진단값이 올바르지 않습니다.')

    def delta(field):
        old,new=finite(field,a),finite(field,b)
        return {'original':old,'variant':new,'absolute_difference':new-old,
                'percent_vs_original':None if old==0 else (new-old)/old*100}
    return {
        'schema':'geofield-d6-two-geometry-descriptive-v1',
        'status':'two_different_cad_real_solver_runs_descriptive_only',
        'read_only':True,
        'source':'original_and_server_generated_D6_step_sha_bound',
        'original':{key:a[key] for key in (
            'snapshot_id','run_id','cad_sha256','case_sha256','cad_name',
            'max_stress_mpa','max_displacement_mm','mesh_node_count',
            'mesh_tetrahedron_count','mesh_target_mm')},
        'variant':{key:b[key] for key in (
            'snapshot_id','run_id','cad_sha256','case_sha256','cad_name',
            'max_stress_mpa','max_displacement_mm','mesh_node_count',
            'mesh_tetrahedron_count','mesh_target_mm')},
        'same_material_and_selected_load_magnitude_direction':True,
        'same_nominal_mesh_target':True,
        'actual_mesh_counts_may_differ':True,
        'fixed_and_loaded_surface_equivalence_verified':False,
        'reaction_and_applied_moment_equivalence_verified':False,
        'support_location_screen_passed':True,
        'applied_load_moment_screen_passed':True,
        'physical_load_screen':{k:screen[k] for k in drift_fields},
        'hotspot_location_correspondence_verified':False,
        'mesh_convergence_certified':False,
        'design_improvement_verified':False,
        'structural_safety_certified':False,
        'stress_change':delta('max_stress_mpa'),
        'displacement_change':delta('max_displacement_mm'),
        'message':('원본 Ø5.5와 별도 변경본 Ø6.0의 실제 CalculiX 응력·변위 수치를 '
                   '독립 검증 후 나란히 표시합니다. STEP 형상이 다르므로 고정/하중면의 '
                   '고정 영역과 하중 작용 위치·모멘트의 실제 INP 선별 검사는 통과했지만 '
                   '전체 CAD 고정·하중면 형상과 반력, 메시 수렴은 아직 검증되지 않았습니다. '
                   '응력이 줄어도 설계 개선·수렴·안전성의 증거가 아닙니다.')
    }
