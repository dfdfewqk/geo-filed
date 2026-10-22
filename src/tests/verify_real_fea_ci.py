"""Real Gmsh+CalculiX GeoField smoke test for the public generic L-bracket.

This program runs the production FEA solver with actual binaries. It does not
mock gmsh, CalculiX, FRD, STA, or RF, and does not modify user project records.
Only a successful calculation with parsed equilibrium evidence is a pass.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import sys


def run():
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo / 'src' / 'tests' / 'fea_ci_dependencies'))
    sys.path.insert(0, str(repo / 'src' / 'payload'))
    from fea_solver import run_real_fea, sha256
    import gmsh

    step = repo / 'fixtures' / 'L_bracket.step'
    out = repo / '_real_fea_evidence'
    out.mkdir(exist_ok=True)
    if not step.is_file():
        raise RuntimeError('Public reference STEP fixture is missing')

    initialized = False
    try:
        gmsh.initialize(['-nopopup'])
        initialized = True
        gmsh.option.setNumber('General.Terminal', 0)
        gmsh.model.add('reference_face_signature')
        gmsh.model.occ.importShapes(str(step), highestDimOnly=False)
        gmsh.model.occ.synchronize()
        faces = []
        for dim, tag in gmsh.model.getEntities(2):
            center = list(map(float, gmsh.model.occ.getCenterOfMass(dim, tag)))
            area = float(gmsh.model.occ.getMass(dim, tag))
            faces.append((tag, center, area))
        if len(faces) != 12:
            raise RuntimeError(f'Unexpected public L-bracket topology: {len(faces)} faces')
        signatures = [dict(face_id=i+1, center_mm=c, area_mm2=a)
                      for i, (_tag, c, a) in enumerate(faces)]
        def find_face(target):
            matches = [i + 1 for i, (_tag, center, area) in enumerate(faces)
                       if area > 1400 and math.dist(center, target) < 0.02]
            if len(matches) != 1:
                raise RuntimeError(f'Ambiguous support or load face {target}: {matches}')
            return matches[0]
        fixed_id = find_face([0.0, 0.0, 25.0])
        load_id = find_face([25.0, 0.0, 0.0])
    finally:
        if initialized:
            gmsh.finalize()

    file_sha = sha256(step)
    force = 3.0 * 9.80665
    case = {
        'schema': 'geofield-fea-case-v1',
        'status': 'configuration_prepared_solver_not_connected',
        'cad_sha256': file_sha,
        'case_sha256': hashlib.sha256(
            f'public-smoke-case:{file_sha}:{fixed_id}:{load_id}:3kg'.encode()
        ).hexdigest(),
        'material': {'young_modulus_mpa': 68900., 'poisson_ratio': 0.33},
        'mesh_request': {'target_element_size_mm': 3.0},
        'boundary_conditions': {
            'fixed_face_ids': [fixed_id],
            'load_face_ids': [load_id],
            'total_force_n': force,
            'force_direction_unit': [0., 0., -1.],
        },
        'self_weight_reference': {'applied_to_solver': False},
    }
    model = {
        'sha256': file_sha,
        'mesh': {'face_ids': [s['face_id'] for s in signatures],
                 'face_signatures': signatures},
    }
    (out / 'input_case.json').write_text(json.dumps(case, indent=2), encoding='utf8')
    result = run_real_fea(step, case, model, out)
    (out / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf8')
    reaction = result.get('support_reaction_equilibrium_audit') or {}
    if result.get('status') != 'solver_executed_result_parsed':
        raise AssertionError('The real solver did not complete and parse successfully')
    if reaction.get('checked') is not True:
        raise AssertionError('Actual fixed-node RF equilibrium was not verified')
    if not result.get('results', {}).get('maximum_nodal_von_mises_mpa', 0) > 0:
        raise AssertionError('No real von Mises stress result')
    if not result.get('results', {}).get('maximum_displacement_mm', 0) > 0:
        raise AssertionError('No real nodal displacement result')
    public_result = {
        'status': result['status'],
        'node_count': result['mesh']['node_count'],
        'tetrahedron_count': result['mesh']['tetrahedron_count'],
        'force_n': force,
        'maximum_nodal_von_mises_mpa': result['results']['maximum_nodal_von_mises_mpa'],
        'maximum_displacement_mm': result['results']['maximum_displacement_mm'],
        'support_reaction_equilibrium_audit': reaction,
        'actual_calculix': True,
        'mesh_convergence_assessed': False,
    }
    print('ACTUAL_GMSH_CALCULIX_FEA_RESULT=' + json.dumps(public_result, ensure_ascii=False))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf8') as f:
            f.write('### Actual Gmsh + CalculiX smoke result\n\n')
            f.write('```json\n' + json.dumps(public_result, indent=2, ensure_ascii=False) + '\n```\n')
    return public_result


if __name__ == '__main__':
    run()
