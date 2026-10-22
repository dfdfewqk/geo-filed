"""GeoField: mesh sensitivity comparison of THREE reverified CalculiX runs.

Read-only. Does not solve, modify CAD, update SQLite or infer structural safety.
Results can only be compared if geometry, material, applied loads, and boundaries
are identical. Report adjacent changes; do not assert mathematical convergence.
"""
from __future__ import annotations
import math
import re
from pathlib import Path
from fea_compare import _side

# GeoField mesh evidence completion 2026-10-19: no synthetic FEA, no safety certification.

HEX32 = re.compile(r'^[0-9a-f]{32}$')
C3D10_EDGES=((0,1),(1,2),(2,0),(0,3),(1,3),(2,3))

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
             'self_weight_applied', 'gravity_density_kg_m3', 'gravity_direction', 'gravity_mm_s2', 'solver', 'mesher', 'element_type')
    return {name: row.get(name,'C3D4' if name=='element_type' else None) for name in names}


def _percent_delta(coarse, fine):
    # Relative to the finer mesh. A zero reference is not silently converted to 0%.
    return abs(fine-coarse)/abs(fine)*100 if fine != 0 else None



def actual_tetra_edge_resolution(inp_path, expected_nodes, expected_tets):
    """Read the *verified* solver INP, not target mesh-size metadata.

    The mean longest C3D4/C3D10 corner edge is a diagnostic of actual discretization.
    The deck must already be independently trusted by fea_compare._side.
    Never infers stress convergence or a safety rating from this number.
    """
    path = Path(inp_path)
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= 96 * 1024 * 1024):
        raise ValueError('메시 INP 원본이 없거나 파일 크기가 잘못됐습니다.')
    if type(expected_nodes) is not int or type(expected_tets) is not int:
        raise ValueError('INP 검증에 필요한 실제 노드/요소 개수가 없습니다.')
    positions, seen_elements = {}, set()
    section = ''
    element_type = None
    tetra_count = 0
    edge_max_sum = 0.0
    edge_max_peak = 0.0
    # No selection of just a few convenient elements: every tetra is inspected.
    with path.open('r', encoding='ascii') as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith('**'):
                continue
            if line.startswith('*'):
                header = line.upper().replace(' ', '')
                keyword = header.split(',', 1)[0]
                if keyword == '*ELEMENT':
                    types=[v.split('=',1)[1] for v in header.split(',')[1:] if v.startswith('TYPE=')]
                    if len(types)!=1 or types[0] not in ('C3D4','C3D10'):
                        raise ValueError('메시 INP에 지원되지 않는 요소 종류가 있습니다.')
                    if element_type is not None and element_type!=types[0]:
                        raise ValueError('메시 INP에 1차/2차 요소가 혼합됐습니다.')
                    element_type=types[0]
                section = keyword
                continue
            if section == '*NODE':
                fields = [f.strip() for f in line.split(',')]
                if len(fields) != 4:
                    raise ValueError('실제 메시 노드 좌표 형식 오류')
                index = int(fields[0]); xyz = tuple(float(x) for x in fields[1:])
                if index <= 0 or index in positions or any(not math.isfinite(v) for v in xyz):
                    raise ValueError('메시 노드 식별자 중복 또는 좌표 오류')
                positions[index] = xyz
                if len(positions) > 450000:
                    raise ValueError('실제 메시의 노드 수 제한 초과')
            elif section == '*ELEMENT':
                fields = [f.strip() for f in line.split(',')]
                if len(fields) != (11 if element_type=='C3D10' else 5):
                    raise ValueError('사면체 요소와 절점 개수·요소 종류가 일치하지 않습니다.')
                eid = int(fields[0]); ids = tuple(int(x) for x in fields[1:])
                if eid <= 0 or eid in seen_elements or len(set(ids)) != len(ids):
                    raise ValueError('중복 요소 또는 잘못된 사면체 절점')
                seen_elements.add(eid)
                try:
                    pts = [positions[i] for i in ids]
                    if element_type=='C3D10':
                        for j,(a,b) in enumerate(C3D10_EDGES):
                            mid=[(pts[a][k]+pts[b][k])/2 for k in range(3)]
                            if math.dist(mid,pts[j+4])>1e-6*max(1.,math.dist(pts[a],pts[b])):
                                raise ValueError('실제 C3D10 변의 중간 절점이 잘못됐습니다.')
                    pts=pts[:4]
                except KeyError as exc:
                    raise ValueError('요소가 존재하지 않는 절점을 참조합니다.') from exc
                longest_squared = max(math.fsum((a[k]-b[k])**2 for k in range(3))
                    for i,a in enumerate(pts) for b in pts[i+1:])
                if longest_squared <= 0 or not math.isfinite(longest_squared):
                    raise ValueError('길이가 0이거나 유효하지 않은 요소 변')
                longest = math.sqrt(longest_squared)
                edge_max_sum += longest
                edge_max_peak = max(longest, edge_max_peak)
                tetra_count += 1
                if tetra_count > 600000:
                    raise ValueError('실제 메시의 사면체 수 제한 초과')
    if len(positions) != expected_nodes or tetra_count != expected_tets or tetra_count < 1:
        raise ValueError('실제 INP 메시 수와 검증된 결과의 노드·요소 수가 다릅니다.')
    return {'actual_nodes':len(positions),'actual_tetrahedra':tetra_count,
            'element_type':element_type,
            'mean_longest_tetra_edge_mm':edge_max_sum/tetra_count,
            'maximum_tetra_edge_mm':edge_max_peak}

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
    # Requested Gmsh target sizes are not evidence that a different/finer real
    # tetrahedral mesh was produced. Independently inspect every actual INP.
    if actual_runs:
        root = Path(jobs_dir) / 'fea_runs'
        edge_rows = [actual_tetra_edge_resolution(root / r['run_id'] / 'geofield_case.inp',
                      r['mesh_node_count'], r['mesh_tetrahedron_count']) for r in runs]
        actual_refines = all(edge_rows[i+1]['mean_longest_tetra_edge_mm'] <
                             edge_rows[i]['mean_longest_tetra_edge_mm'] for i in (0, 1))
        mesh_resolution = {'status':'measured_from_three_verified_inp_meshes',
                           'mean_longest_tetra_edge_mm':[x['mean_longest_tetra_edge_mm'] for x in edge_rows],
                           'maximum_tetra_edge_mm':[x['maximum_tetra_edge_mm'] for x in edge_rows],
                           'effective_mean_edge_refinement':actual_refines,
                           'convergence_certified':False,
                           'warning':('실제 사면체 평균 최장 변 길이가 단계별로 감소하지 않습니다. '
                                      '목표 메시 크기만으로 세분화를 인정할 수 없습니다.' if not actual_refines else '')}
    else:
        actual_refines = False
        mesh_resolution = {'status':'not_evaluated_test_only',
                           'effective_mean_edge_refinement':False,
                           'convergence_certified':False,
                           'warning':'실제 INP 메시 변 길이를 검증하지 않았습니다.'}
    # A 5% diagnostic threshold is intentionally NOT a mathematical convergence proof.
    # It is only a readable measure of stability in the recorded global maxima.
    finite_deltas = [t[key] for t in trends for key in
        ('stress_relative_change_percent','displacement_relative_change_percent')]
    threshold = 5.0
    stable_maxima = (mesh_grows and node_grows and
        len(finite_deltas)==4 and all(v is not None and math.isfinite(v) and v<=threshold for v in finite_deltas))
    # The original numeric stability screen remains useful for synthetic tests,
    # but a real solver run must satisfy the INP load-moment comparability screen.
    if actual_runs and (not physically_comparable or not actual_refines):
        stable_maxima = False
    result_rows = [{k:r.get(k,'C3D4' if k=='element_type' else None) for k in (
        'run_id','snapshot_id','mesh_target_mm','mesh_node_count','mesh_tetrahedron_count','element_type',
        'max_stress_mpa','max_displacement_mm')} for r in runs]
    return {
        'status':'verified_three_mesh_sensitivity_only',
        'read_only':True,
        'same_physical_case':True,
        'solver_evidence':'each_calculix_run_revalidated',
        'mesh_count_increases_with_refinement':mesh_grows,
        'node_count_increases_with_refinement':node_grows,
        'actual_load_moment_comparability':load_moment,
        'actual_mesh_resolution_diagnostic':mesh_resolution,
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
                   (load_moment['warning'] if actual_runs and not physically_comparable else '') +
                   (mesh_resolution['warning'] if actual_runs and not actual_refines else '')}
