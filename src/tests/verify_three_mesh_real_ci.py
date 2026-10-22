"""Run three genuine production GeoField CalculiX solves, keeping raw evidence.

Identical public STEP, face selection, material, load, constraints, solver;
only the requested Gmsh target element size changes.  This is a mesh
sensitivity study, not a proof of convergence or structural safety.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys

TARGETS = (('coarse', 4.2), ('medium', 3.0), ('fine', 2.25))


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def reference_case(repo, solver_sha):
    """Choose physical faces from the actual imported OpenCASCADE geometry."""
    import gmsh
    step = repo / 'fixtures' / 'L_bracket.step'
    if not step.is_file():
        raise RuntimeError('Missing approved public L-bracket fixture')
    if sha256(step) != 'fe65841074c5fc6bd74442b147e5688490ec1ad79d5fb1e41bdccd3514bccf32':
        raise RuntimeError('STEP public fixture SHA changed')
    gmsh.initialize(['-nopopup'])
    try:
        gmsh.option.setNumber('General.Terminal', 0)
        gmsh.model.add('three_mesh_face_signature')
        gmsh.model.occ.importShapes(str(step), highestDimOnly=False)
        gmsh.model.occ.synchronize()
        faces = []
        for dim, tag in gmsh.model.getEntities(2):
            center = list(map(float, gmsh.model.occ.getCenterOfMass(dim, tag)))
            area = float(gmsh.model.occ.getMass(dim, tag))
            faces.append((tag, center, area))
        if len(faces) != 12:
            raise RuntimeError('Public reference topology changed')
        sigs = [dict(face_id=i+1, center_mm=center, area_mm2=area)
                for i, (_, center, area) in enumerate(faces)]
        def select(target):
            matches = [i + 1 for i, (_, center, area) in enumerate(faces)
                       if area > 1400 and math.dist(center, target) < 0.02]
            if len(matches) != 1:
                raise RuntimeError(f'Ambiguous face matching {target}: {matches}')
            return matches[0]
        fixed = select([0., 0., 25.])
        loaded = select([25., 0., 0.])
    finally:
        gmsh.finalize()
    step_sha = sha256(step)
    physical = {
        'cad_sha256': step_sha,
        'material': {'young_modulus_mpa': 68900., 'poisson_ratio': 0.33},
        'boundary_conditions': {
            'fixed_face_ids': [fixed], 'load_face_ids': [loaded],
            'total_force_n': 29.41995, 'force_direction_unit': [0., 0., -1.]},
        'self_weight_reference': {'applied_to_solver': False},
        'solver_sha256': solver_sha,
    }
    model = {'sha256': step_sha, 'mesh': {'face_ids': [s['face_id'] for s in sigs],
              'face_signatures': sigs}}
    return step, physical, model


def relative_percent(a, b):
    if b == 0:
        raise ValueError('Cannot compare against zero displacement/stress')
    return 100. * abs(b-a) / abs(b)



def actual_tetra_edge_resolution(inp_path, expected_nodes, expected_tets):
    """Calculate the mean of each C3D4 tetrahedron's actual longest edge."""
    path = Path(inp_path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 96*1024*1024:
        raise ValueError('Invalid actual INP evidence')
    node_xyz = {}
    seen_elements = set()
    section = None
    count = 0
    edge_sum = 0.
    edge_max = 0.
    for raw in path.read_text(encoding='ascii').splitlines():
        line = raw.strip()
        if not line or line.startswith('**'):
            continue
        if line.startswith('*'):
            upper = line.upper().replace(' ', '')
            section = upper.split(',',1)[0]
            if section == '*ELEMENT' and 'TYPE=C3D4' not in upper.split(',')[1:]:
                raise ValueError('Unexpected non-tetrahedral element')
            continue
        if section == '*NODE':
            a = [part.strip() for part in line.split(',')]
            if len(a) != 4: raise ValueError('Invalid node entry')
            n = int(a[0]); xyz = tuple(float(v) for v in a[1:])
            if n <= 0 or n in node_xyz or not all(math.isfinite(v) for v in xyz):
                raise ValueError('Duplicate or invalid node')
            node_xyz[n] = xyz
        if section == '*ELEMENT':
            a = [part.strip() for part in line.split(',')]
            if len(a) != 5: raise ValueError('Invalid C3D4 row')
            eid = int(a[0]); ids = [int(v) for v in a[1:]]
            if eid <= 0 or eid in seen_elements or len(set(ids)) != 4:
                raise ValueError('Duplicate or malformed element')
            seen_elements.add(eid)
            points = [node_xyz[v] for v in ids]
            longest = math.sqrt(max(sum((x[k]-y[k])**2 for k in range(3))
                                  for ix,x in enumerate(points) for y in points[ix+1:]))
            if longest <= 0 or not math.isfinite(longest): raise ValueError('Invalid edge')
            edge_sum += longest
            edge_max = max(edge_max,longest)
            count += 1
    if len(node_xyz) != expected_nodes or count != expected_tets or count == 0:
        raise ValueError('Measured INP nodes/elements differ from solver result')
    return {'mean_longest_tetra_edge_mm':edge_sum/count,
            'maximum_tetra_edge_mm':edge_max}


def run():
    repo = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(repo / 'src'),
                    str(repo / 'src' / 'tests' / 'fea_ci_dependencies'),
                    str(repo / 'src' / 'payload')]
    from fea_solver import run_real_fea
    from fea_load_moment import audit_verified_deck

    out = repo / '_real_fea_three_mesh_evidence'
    out.mkdir(exist_ok=True)
    solver_sha = sha256(repo / 'src' / 'payload' / 'fea_solver.py')
    step, physics, model = reference_case(repo, solver_sha)
    (out / 'physics.json').write_text(json.dumps(physics, indent=2), encoding='utf-8')
    rows = []
    for label, target_mm in TARGETS:
        folder = out / label
        folder.mkdir(exist_ok=True)
        case = copy.deepcopy(physics)
        case.pop('solver_sha256')
        case.update(schema='geofield-fea-case-v1',
                    status='configuration_prepared_solver_not_connected',
                    mesh_request={'target_element_size_mm':target_mm})
        case['case_sha256'] = hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest()
        (folder / 'input_case.json').write_text(json.dumps(case, indent=2), encoding='utf-8')
        result = run_real_fea(step, case, model, folder)
        (folder / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        if result['status'] != 'solver_executed_result_parsed':
            raise RuntimeError(f'{label} CalculiX was not successfully parsed')
        audit = result['support_reaction_equilibrium_audit']
        if audit.get('checked') is not True or audit.get('status') != 'static_force_and_moment_balanced':
            raise RuntimeError(f'{label} reaction equilibrium failed')
        inp = folder / 'geofield_case.inp'
        sta = folder / 'geofield_case.sta'
        frd = folder / 'geofield_case.frd'
        dat = folder / 'geofield_case.dat'
        for path in (inp, sta, frd, dat):
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError(f'{label} missing actual {path.name}')
        mesh = result['mesh']
        edge = actual_tetra_edge_resolution(inp, mesh['node_count'], mesh['tetrahedron_count'])
        load = audit_verified_deck(inp, 29.41995, [0., 0., -1.])
        fields = result['results']
        row = {
            'label': label, 'target_mm': target_mm, 'case_sha256': case['case_sha256'],
            'cad_sha256': case['cad_sha256'], 'solver_source_sha256': solver_sha,
            'nodes': mesh['node_count'], 'tetrahedra': mesh['tetrahedron_count'],
            'mean_longest_tetra_edge_mm': edge['mean_longest_tetra_edge_mm'],
            'max_longest_tetra_edge_mm': edge['maximum_tetra_edge_mm'],
            'maximum_nodal_von_mises_mpa': fields['maximum_nodal_von_mises_mpa'],
            'maximum_displacement_mm': fields['maximum_displacement_mm'],
            'load_application_center_mm': load['force_application_center_mm'],
            'load_moment_origin_n_mm': load['moment_about_global_origin_n_mm'],
            'load_resultant_n': load['total_force_n'],
            'reaction_force_residual_n': audit['force_residual_magnitude_n'],
            'reaction_moment_residual_n_mm': audit['moment_residual_magnitude_n_mm'],
            'reaction_checked': audit['checked'],
            'file_sha256': {p.name:sha256(p) for p in (inp,sta,frd,dat)},
        }
        rows.append(row)
        print('ACTUAL_MESH_RUN=' + json.dumps(row, ensure_ascii=False), flush=True)

    same_geometry = len({r['cad_sha256'] for r in rows}) == 1
    same_solver = len({r['solver_source_sha256'] for r in rows}) == 1
    monotonic = all(rows[i+1]['tetrahedra'] > rows[i]['tetrahedra'] and
                    rows[i+1]['nodes'] > rows[i]['nodes'] and
                    rows[i+1]['mean_longest_tetra_edge_mm'] < rows[i]['mean_longest_tetra_edge_mm']
                    for i in (0,1))
    fmag = physics['boundary_conditions']['total_force_n']
    moments = [r['load_moment_origin_n_mm'] for r in rows]
    moment_drifts = [math.dist(moments[i],moments[i+1]) / fmag for i in (0,1)]
    moment_comparable = all(v <= .1 for v in moment_drifts)
    stress_change = [relative_percent(rows[i]['maximum_nodal_von_mises_mpa'],rows[i+1]['maximum_nodal_von_mises_mpa']) for i in (0,1)]
    displacement_change = [relative_percent(rows[i]['maximum_displacement_mm'],rows[i+1]['maximum_displacement_mm']) for i in (0,1)]
    # A diagnostic only, not a proof of mathematical convergence.
    numerical_stability_screen = (monotonic and moment_comparable and
        all(v <= 5. for v in stress_change+displacement_change))
    if not same_geometry or not same_solver:
        raise RuntimeError('A physical or solver input identity changed across three runs')
    result = {
        'status':'three_real_calculix_runs_verified',
        'real_solver_runs':3, 'physical_case_identity_verified':True,
        'only_gmsh_target_size_changed':True,
        'actual_mesh_refinement_monotonic':monotonic,
        'load_moment_comparable_within_0_1mm':moment_comparable,
        'load_moment_equivalent_arm_drift_mm':moment_drifts,
        'adjacent_stress_max_change_percent':stress_change,
        'adjacent_displacement_max_change_percent':displacement_change,
        'five_percent_numerical_stability_screen_passes':numerical_stability_screen,
        'mathematical_convergence_certified':False,
        'safety_certified':False,
        'warnings':'Max nodal extrapolated stress at fixed/load edge may be mesh-sensitive; three runs cannot certify local convergence or design safety.',
        'runs':rows,
    }
    (out / 'three_mesh_summary.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
    print('ACTUAL_THREE_MESH_FEA_RESULT=' + json.dumps(result, ensure_ascii=False),flush=True)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf8') as f:
            f.write('## Three genuine independent Gmsh + CalculiX runs\n')
            f.write('Only mesh target size varies; **not convergence or safety certification**.\n\n')
            f.write('|Mesh|Target mm|Nodes|Tets|Mean longest tetra edge mm|Max nodal stress MPa|Max displacement mm|\n')
            f.write('|---|---:|---:|---:|---:|---:|---:|\n')
            for r in rows:
                f.write(f"|{r['label']}|{r['target_mm']}|{r['nodes']}|{r['tetrahedra']}|{r['mean_longest_tetra_edge_mm']:.4f}|{r['maximum_nodal_von_mises_mpa']:.5f}|{r['maximum_displacement_mm']:.6f}|\n")
            f.write('\n' + json.dumps({k:v for k,v in result.items() if k!='runs'},indent=2) + '\n')
    if not monotonic or not moment_comparable:
        # Save the evidence first and fail the CI so incomplete validity is visible.
        raise AssertionError('Actual mesh order/load-moment comparability failed; inspect saved raw evidence')
    return result


if __name__ == '__main__':
    run()
