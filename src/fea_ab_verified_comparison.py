"""GeoField FEA read-only A/B comparison of two independently reverified solver runs.

This module never writes INP, initiates CalculiX, approves a load redistribution,
certifies structural safety, or treats research candidates as solved results.
Each run must contain complete original case.json/result.json/INP/STA/FRD.
The two decks must be byte-identical except for CLOAD bodies (line endings
normalized); material, nodes, elements, restraints and solver cards stay fixed.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from fea_load_moment import audit_verified_deck, MAX_INP_BYTES

HEX32 = re.compile(r'^[0-9a-f]{32}$')
HEX64 = re.compile(r'^[0-9a-f]{64}$')
_REQUIRED = ('case.json', 'result.json', 'geofield_case.inp',
             'geofield_case.sta', 'geofield_case.frd')


def _json(path):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 8*1024*1024:
        raise ValueError('Missing or oversized case/result JSON evidence')
    with path.open(encoding='utf-8') as f:
        return json.load(f)


def _deck_except_loads(path):
    """Fingerprint every INP line except the *CLOAD body, preserving section order.

    Exact other-section equality, rather than only equal node counts or mesh SHA,
    prevents changing material, constraints, contact, STEP, gravity or geometry
    and falsely attributing a stress delta to nodal force redistribution.
    """
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_INP_BYTES:
        raise ValueError('Missing/unsafe INP deck')
    dig = hashlib.sha256()
    cload_count = 0
    load_rows = []
    section = ''
    with path.open('r', encoding='ascii', newline=None) as f:
        for raw in f:
            line = raw.strip()
            if line.upper().startswith('*CLOAD') and not line.startswith('**'):
                if line.upper() != '*CLOAD':
                    raise ValueError('Unsupported CLOAD keyword options in A/B comparison')
                cload_count += 1
                if cload_count > 1:
                    raise ValueError('Multiple CLOAD sections are ambiguous')
                dig.update(b'*CLOAD\n')
                section = '*CLOAD'
                continue
            if line.startswith('*') and not line.startswith('**'):
                section = line.split(',', 1)[0].strip().upper()
                if section == '*INCLUDE':
                    raise ValueError('External INCLUDE deck cannot be independently compared')
            if section == '*CLOAD' and line and not line.startswith('*'):
                if not line.startswith('**'):
                    load_rows.append(line)
                continue
            # Comments inside CLOAD are excluded only if they are in its body.
            if section == '*CLOAD' and line.startswith('**'):
                continue
            dig.update(raw.rstrip('\r\n').encode('ascii')+b'\n')
    if cload_count != 1 or not load_rows:
        raise ValueError('Exactly one nonempty CLOAD section required')
    components = set()
    for row in load_rows:
        pieces = [p.strip() for p in row.split(',')]
        if len(pieces) != 3:
            raise ValueError('Malformed CLOAD evidence')
        node, axis = int(pieces[0]), int(pieces[1])
        if node <= 0 or axis not in (1,2,3) or (node,axis) in components:
            raise ValueError('Invalid or duplicate CLOAD component')
        components.add((node,axis))
    return dig.hexdigest(), load_rows, components


def _number(v, label):
    if type(v) not in (int, float) or not math.isfinite(v) or v < 0:
        raise ValueError('Unverified '+label)
    return float(v)


def _vec3(v, label):
    if not isinstance(v, (list, tuple)) or len(v) != 3 or any(
        type(x) not in (int,float) or not math.isfinite(x) for x in v
    ):
        raise ValueError('Invalid '+label)
    return [float(x) for x in v]


def _run(jobs_dir, run_id, verifier):
    if not isinstance(run_id, str) or not HEX32.fullmatch(run_id):
        raise ValueError('Invalid run ID')
    base = Path(jobs_dir)
    folder = base / 'fea_runs' / run_id
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('Missing real FEA run directory')
    for name in _REQUIRED:
        p = folder / name
        if p.is_symlink() or not p.is_file() or p.stat().st_size == 0:
            raise ValueError('Missing actual INP/STA/FRD/case/result evidence: '+name)
    case, old = _json(folder/'case.json'), _json(folder/'result.json')
    if case.get('schema') != 'geofield-fea-case-v1' or old.get('schema') != 'geofield-fea-result-v1':
        raise ValueError('Unexpected saved calculation schema')
    cad_sha, case_sha = case.get('cad_sha256'), case.get('case_sha256')
    if not isinstance(cad_sha, str) or not HEX64.fullmatch(cad_sha) or not isinstance(case_sha, str) or not HEX64.fullmatch(case_sha):
        raise ValueError('Invalid CAD or case checksum')
    if (old.get('status') != 'solver_executed_result_parsed' or
        old.get('cad_sha256') != cad_sha or old.get('case_sha256') != case_sha):
        raise ValueError('Saved result does not match signed CAD case')
    if verifier is None:
        from fea_result_trust_gate import verify_directory_for_case as verify_directory
        verifier = verify_directory
    verified, field = verifier(folder, case, cad_sha)
    if (not isinstance(verified, dict) or
        verified.get('schema') != 'geofield-fea-result-v1' or
        verified.get('status') != 'solver_executed_result_parsed' or
        verified.get('cad_sha256') != cad_sha or verified.get('case_sha256') != case_sha):
        raise ValueError('Independent actual INP/STA/FRD verifier rejected run')
    # Old result.json is not sufficient evidence: confirm independent FRD figures.
    actual_values, saved_values = verified.get('results') or {}, old.get('results') or {}
    for key in ('maximum_nodal_von_mises_mpa','maximum_displacement_mm'):
        real, historical = _number(actual_values.get(key), key), _number(saved_values.get(key),key)
        if not math.isclose(real,historical,rel_tol=1e-6,abs_tol=1e-9):
            raise ValueError('Saved FEA values differ from reverified FRD: '+key)
    for key in ('solver','mesher'):
        if not isinstance(verified.get(key),str) or not verified[key] or verified.get(key)!=old.get(key):
            raise ValueError('Solver/mesher provenance does not match the original result')
    for key in ('node_count','tetrahedron_count'):
        actual_count, old_count = (verified.get('mesh') or {}).get(key), (old.get('mesh') or {}).get(key)
        if type(actual_count) is not int or actual_count <= 0 or actual_count != old_count:
            raise ValueError('Actual FEA mesh counts disagree with archived result')
    if actual_values.get('parsed_nodes') != (verified.get('mesh') or {}).get('node_count'):
        raise ValueError('FRD node count mismatches actual INP mesh')
    bc = case.get('boundary_conditions') or {}
    force = bc.get('total_force_n')
    direction = _vec3(bc.get('force_direction_unit'), 'force direction')
    if type(force) not in (int,float) or not math.isfinite(force) or force <= 0:
        raise ValueError('Invalid saved force')
    actual_load = audit_verified_deck(folder/'geofield_case.inp',force,direction)
    deck_sha, cload_rows, cload_components = _deck_except_loads(folder/'geofield_case.inp')
    frd_path = folder/'geofield_case.frd'
    if frd_path.stat().st_size > 512*1024*1024:
        raise ValueError('FRD exceeds comparison evidence size limit')
    with frd_path.open('rb') as source:
        h=hashlib.sha256()
        for chunk in iter(lambda:source.read(1024*1024),b''):
            h.update(chunk)
    frd_sha=h.hexdigest()
    peak = None
    # This is the *surface field* peak, not necessarily an interior global max.
    # The surface field is only considered if the verifier independently returns it.
    if isinstance(field,dict) and (field.get('schema') == 'geofield-fea-surface-field-v1' and
                                   field.get('source') == 'actual_calculix_ascii_frd' and
                                   field.get('cad_sha256') == cad_sha and
                                   field.get('case_sha256') == case_sha):
        stress = field.get('von_mises_mpa'); pts = field.get('positions_mm')
        if (isinstance(stress,list) and isinstance(pts,list) and 0 < len(stress)==len(pts) <= 450000):
            valid = all(type(n) in (int,float) and math.isfinite(n) and n >= 0 for n in stress)
            if valid and max(stress) <= _number(actual_values['maximum_nodal_von_mises_mpa'],'stress')*(1+1e-6)+1e-8:
                idx = max(range(len(stress)),key=lambda i:stress[i]); p = _vec3(pts[idx], 'surface peak coordinates')
                peak = {'position_mm':p,'stress_mpa':float(stress[idx]),
                        'location_scope':'verified_surface_field_only'}
    return {'run_id':run_id,'cad_sha256':cad_sha,'case_sha256':case_sha,
            'deck_without_cload_sha256':deck_sha,'cload_lines':cload_rows,
            'cload_components':sorted(cload_components), 'frd_sha256':frd_sha,
            'actual_load_audit':actual_load,'max_stress_mpa':_number(actual_values['maximum_nodal_von_mises_mpa'],'stress'),
            'max_displacement_mm':_number(actual_values['maximum_displacement_mm'],'displacement'),
            'mesh_nodes':verified['mesh']['node_count'],'mesh_tetrahedra':verified['mesh']['tetrahedron_count'],
            'verified_surface_peak':peak,
            'evidence':'real_INP_STA_FRD_reverified'}


def compare_actual_ab(jobs_dir, original_run_id, candidate_run_id, *, verifier=None):
    """Compare *completed* A/B runs; fail if anything except CLOAD changes.

    Call with two distinct existing CalculiX run directories after solving
    separately. This does not create CLOAD, run CalculiX or infer improvement.
    """
    if original_run_id == candidate_run_id:
        raise ValueError('A/B requires two different solver runs')
    a = _run(jobs_dir,original_run_id,verifier)
    b = _run(jobs_dir,candidate_run_id,verifier)
    if a['case_sha256'] != b['case_sha256'] or a['cad_sha256'] != b['cad_sha256']:
        raise ValueError('A/B comparison requires identical signed CAD/FEA case')
    if a['deck_without_cload_sha256'] != b['deck_without_cload_sha256']:
        raise ValueError('A/B comparison blocked: deck differs outside CLOAD (mesh/material/boundary/solver)')
    if a['cload_components'] != b['cload_components']:
        raise ValueError('A/B applied load nodes/components changed')
    if a['frd_sha256'] == b['frd_sha256']:
        raise ValueError('Identical FRD evidence cannot establish two distinct A/B solver responses')
    if a['cload_lines'] == b['cload_lines']:
        raise ValueError('No physical CLOAD change between A/B decks')
    la, lb = a['actual_load_audit'],b['actual_load_audit']
    fa,fb = la['total_force_n'],lb['total_force_n']
    mag = math.sqrt(math.fsum(t*t for t in fa))
    if mag <= 0 or math.dist(fa,fb)>max(1e-4,mag*1e-5):
        raise ValueError('A/B physical resultant changed')
    # This INP parser requires exact same load nodes, to isolate redistribution.
    if la['applied_node_count'] != lb['applied_node_count']:
        raise ValueError('A/B nodal-load count changed')
    moment_a,moment_b=la['moment_about_global_origin_n_mm'],lb['moment_about_global_origin_n_mm']
    def delta(key):
        old,new=a[key],b[key]
        return {'original':old,'candidate':new,'absolute_change':new-old,
                'percent_vs_original':((new-old)/old*100 if old else None)}
    pa,pb=a['verified_surface_peak'],b['verified_surface_peak']
    peak_move = math.dist(pa['position_mm'],pb['position_mm']) if pa and pb else None
    def public(row):
        return {k:v for k,v in row.items() if k not in ('cload_lines','cload_components')}
    return {
        'status':'two_real_calculix_ab_runs_independently_reverified',
        'read_only':True,'solver_executed_by_this_comparator':False,
        'production_loads_changed_by_this_comparator':False,
        'identical_mesh_material_boundary_solver_cards':True,
        'original':public(a),'candidate':public(b),
        'resultant_difference_n':math.dist(fa,fb),
        'moment_change_about_origin_n_mm':math.dist(moment_a,moment_b),
        'moment_equivalent_lever_arm_change_mm':math.dist(moment_a,moment_b)/mag,
        'maximum_nodal_von_mises_comparison':delta('max_stress_mpa'),
        'maximum_displacement_comparison':delta('max_displacement_mm'),
        'verified_surface_peak_position_movement_mm':peak_move,
        'stress_improvement_certified':False, 'mesh_convergence_certified':False,
        'structural_safety_certified':False,
        'warning':('Same INP outside CLOAD and reverified completed solver files; A/B result comparison only. '
                   'Reweighting changes physical load distribution even when resultant and moment match. '
                   'A surface peak may not be the global nodal stress peak, and a lower stress is not automatically safer.'),
    }
