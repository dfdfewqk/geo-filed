"""GeoField: mesh sensitivity comparison of THREE reverified CalculiX runs.

Read-only. Does not solve, modify CAD, update SQLite or infer structural safety.
Results can only be compared if geometry, material, applied loads, and boundaries
are identical. Report adjacent changes; do not assert mathematical convergence.
"""
from __future__ import annotations
import math
import re
from fea_compare import _side

# GeoField mesh evidence completion 2026-10-19: no synthetic FEA, no safety certification.

HEX32 = re.compile(r'^[0-9a-f]{32}$')

def _positive_number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(label + ' 값이 유효하지 않습니다.')
    return float(value)


def _physics(row):
    # Include only invariants that determine this solver model; no display/file names.
    # An unrecognized/unknown physics field must be inspected before adding new cases.
    names = ('cad_sha256', 'material', 'young_modulus_mpa', 'poisson_ratio',
             'fixed_faces', 'load_faces', 'force_n', 'direction',
             'external_mass_kg', 'analysis_type', 'load_interpretation',
             'self_weight_applied', 'gravity_density_kg_m3', 'gravity_direction', 'gravity_mm_s2', 'solver', 'mesher')
    return {name: row.get(name) for name in names}


def _percent_delta(coarse, fine):
    # Relative to the finer mesh. A zero reference is not silently converted to 0%.
    return abs(fine-coarse)/abs(fine)*100 if fine != 0 else None


def assess(db, jobs_dir, ids):
    if not isinstance(ids, (list, tuple)) or len(ids) != 3:
        raise ValueError('메시 민감도 분석에는 서로 다른 실제 FEA 계산 기록 3건이 필요합니다.')
    if any(not isinstance(i, str) or not HEX32.fullmatch(i) for i in ids) or len(set(ids)) != 3:
        raise ValueError('실제 FEA 기록 ID 3개를 중복 없이 선택하세요.')

    # _side individually validates actual INP/STA/FRD and persisted values.
    runs = [_side(db, jobs_dir, i) for i in ids]
    if len({r['run_id'] for r in runs}) != 3:
        raise ValueError('서로 다른 CalculiX 실행 결과 3건이어야 합니다.')
    reference = _physics(runs[0])
    for r in runs[1:]:
        if _physics(r) != reference:
            raise ValueError('메시 수렴 비교 불가: CAD·재료·물성·하중·고정 면·중력·솔버 조건이 서로 다릅니다.')
    for r in runs:
        _positive_number(r.get('mesh_target_mm'), '목표 메시 크기')
        if r.get('mesh_node_count') is None or r.get('mesh_tetrahedron_count') is None:
            raise ValueError('실제 메시 노드/요소 개수 기록이 없어 민감도를 평가할 수 없습니다.')
        nodes = r['mesh_node_count']; tets = r['mesh_tetrahedron_count']
        if type(nodes) is not int or nodes < 4 or type(tets) is not int or tets < 1:
            raise ValueError('실제 FEA 메시 노드/요소 수가 잘못됐습니다.')
    # Largest target (coarsest requested size) to smallest target.
    runs.sort(key=lambda x: x['mesh_target_mm'], reverse=True)
    if len({r['mesh_target_mm'] for r in runs}) != 3:
        raise ValueError('서로 다른 목표 메시 크기의 계산 3건이 필요합니다.')

    def trend(coarse, fine):
        return {
            'from_target_mm':coarse['mesh_target_mm'],
            'to_target_mm':fine['mesh_target_mm'],
            'stress_absolute_change_mpa': fine['max_stress_mpa']-coarse['max_stress_mpa'],
            'stress_relative_change_percent': _percent_delta(coarse['max_stress_mpa'],fine['max_stress_mpa']),
            'displacement_absolute_change_mm': fine['max_displacement_mm']-coarse['max_displacement_mm'],
            'displacement_relative_change_percent': _percent_delta(coarse['max_displacement_mm'],fine['max_displacement_mm'])}
    mesh_grows = all(runs[i+1]['mesh_tetrahedron_count'] > runs[i]['mesh_tetrahedron_count'] for i in (0,1))
    node_grows = all(runs[i+1]['mesh_node_count'] > runs[i]['mesh_node_count'] for i in (0,1))
    trends = [trend(runs[0],runs[1]), trend(runs[1],runs[2])]
    # _side revalidates actual solver files. Re-read each matching INP so that
    # small stress/displacement deltas cannot be called stable if force/moment
    # application changed between different meshes. Synthetic old comparator
    # fixtures have no evidence flag and are explicitly NOT production proof.
    actual_runs = all(r.get('evidence') == 'real_solver_files_revalidated' for r in runs)
    if actual_runs:
        from fea_load_moment import compare_verified_runs
        load_moment = compare_verified_runs(jobs_dir, runs)
        physically_comparable = load_moment['moment_comparable_for_mesh_only_review']
    else:
        load_moment = {'status':'not_evaluated_test_only',
                       'moment_comparable_for_mesh_only_review':False,
                       'convergence_certified':False,
                       'warning':'Actual INP load-moment audit was not executed.'}
        physically_comparable = False
    # A 5% diagnostic threshold is intentionally NOT a mathematical convergence proof.
    # It is only a readable measure of stability in the recorded global maxima.
    finite_deltas = [t[key] for t in trends for key in
        ('stress_relative_change_percent','displacement_relative_change_percent')]
    threshold = 5.0
    stable_maxima = (mesh_grows and node_grows and
        len(finite_deltas)==4 and all(v is not None and math.isfinite(v) and v<=threshold for v in finite_deltas))
    # The original numeric stability screen remains useful for synthetic tests,
    # but a real solver run must satisfy the INP load-moment comparability screen.
    if actual_runs and not physically_comparable:
        stable_maxima = False
    result_rows = [{k:r[k] for k in (
        'run_id','snapshot_id','mesh_target_mm','mesh_node_count','mesh_tetrahedron_count',
        'max_stress_mpa','max_displacement_mm')} for r in runs]
    return {
        'status':'verified_three_mesh_sensitivity_only',
        'read_only':True,
        'same_physical_case':True,
        'solver_evidence':'each_calculix_run_revalidated',
        'mesh_count_increases_with_refinement':mesh_grows,
        'node_count_increases_with_refinement':node_grows,
        'actual_load_moment_comparability':load_moment,
        'numeric_stability_diagnostic':{
            'criterion':'two_adjacent_steps_both_maxima_at_most_five_percent',
            'threshold_percent':threshold,
            'passes':stable_maxima,
            'is_convergence_proof':False,
            'actual_inp_load_screen_passes':physically_comparable,
        },
        'verified_result_rows':result_rows,
        'runs_coarse_to_fine':runs,
        'adjacent_changes':trends,
        'convergence_certified':False,
        'safety_certified':False,
        'message':('실제 메시 크기별 최대 절점 응력·변위의 변화율만 표시합니다. '
                   '값의 안정만으로 수렴·응력 특이점 부재·안전성은 확정할 수 없습니다. '
                   '특히 고정·하중 면 모서리 응력과 C3D4 요소의 특성을 별도로 검토해야 합니다. '
                   '5% 수치 안정 판정은 진단 기준일 뿐 수렴 증명은 아닙니다.'),
        'warning': ('요청 메시 크기가 작아져도 실제 사면체 요소 또는 노드 수가 증가하지 않았습니다. '
                    '메시 품질과 실제 노드/요소 수를 확인하세요. ' if not (mesh_grows and node_grows) else '') +
                   (load_moment['warning'] if actual_runs and not physically_comparable else '')}
