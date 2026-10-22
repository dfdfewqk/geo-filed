"""Read-only moment comparability checks for three separately verified FEA INP decks.

CalculiX evidence (INP/STA/FRD and run ID) MUST have passed fea_compare._side
before calling compare_verified_runs. This module reads CLOAD/NODE only; it never
modifies a deck, reconstructs physical stresses, or certifies mesh convergence.
"""
from __future__ import annotations

import math
from pathlib import Path

MAX_INP_BYTES = 96 * 1024 * 1024
MAX_NODES = 450000
REVIEW_LEVER_ARM_MM = 0.1  # engineering review SCREEN, not acceptance/safety standard


def _vector(v, name):
    if not isinstance(v, (list, tuple)) or len(v) != 3 or any(
        type(x) not in (int, float) or not math.isfinite(x) for x in v
    ):
        raise ValueError(name + ': three finite numeric components required')
    return [float(x) for x in v]


def audit_verified_deck(path, expected_force_n, direction):
    """Inspect actual *NODE and *CLOAD cards after independent solver verification.

    All forces are N, coordinates mm, moments N*mm. A one-pass parser avoids
    reading huge node arrays into raw memory. Unexpected duplicate node or
    CLOAD axis entries fail closed rather than silently summing them.
    """
    p = Path(path)
    if p.is_symlink() or not p.is_file() or not 0 < p.stat().st_size <= MAX_INP_BYTES:
        raise ValueError('INP evidence missing, symbolic link or invalid file size')
    if type(expected_force_n) not in (float, int) or not math.isfinite(expected_force_n) or expected_force_n <= 0:
        raise ValueError('Invalid requested force')
    direction = _vector(direction, 'direction')
    if abs(math.fsum(v*v for v in direction) - 1.0) > 1e-6:
        raise ValueError('Load direction must be a unit vector')
    points, fixed, loads, seen_components = {}, set(), {}, set()
    section, cload_sections = '', 0
    with p.open(encoding='ascii') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('**'):
                continue
            if line.startswith('*'):
                section = line.split(',', 1)[0].strip().upper()
                if section == '*CLOAD':
                    cload_sections += 1
                    if cload_sections > 1:
                        raise ValueError('Unexpected multiple CLOAD sections')
                continue
            if section not in ('*NODE', '*BOUNDARY', '*CLOAD'):
                continue
            values = [v.strip() for v in line.split(',')]
            if section == '*NODE':
                if len(values) != 4:
                    raise ValueError('Malformed INP node')
                n = int(values[0]); pos = [float(v) for v in values[1:]]
                if n <= 0 or n in points or any(not math.isfinite(v) for v in pos):
                    raise ValueError('Duplicate/invalid INP node')
                points[n] = pos
                if len(points) > MAX_NODES:
                    raise ValueError('INP node limit exceeded')
            elif section == '*BOUNDARY':
                if len(values) < 3:
                    raise ValueError('Malformed INP boundary')
                n = int(values[0])
                if n <= 0:
                    raise ValueError('Invalid fixed node')
                fixed.add(n)
            else:
                if len(values) != 3:
                    raise ValueError('Malformed INP CLOAD')
                n, axis, val = int(values[0]), int(values[1]), float(values[2])
                if n <= 0 or axis not in (1, 2, 3) or not math.isfinite(val) or (n, axis) in seen_components:
                    raise ValueError('Invalid/duplicate INP CLOAD component')
                seen_components.add((n, axis))
                loads.setdefault(n, [0., 0., 0.])[axis - 1] = val
                if len(loads) > MAX_NODES:
                    raise ValueError('INP CLOAD limit exceeded')
    if not loads or any(n not in points or n in fixed for n in loads) or any(n not in points for n in fixed):
        raise ValueError('Missing nodes or CLOAD applied to fixed nodes')
    total = [math.fsum(force[i] for force in loads.values()) for i in range(3)]
    expected = [float(expected_force_n)*component for component in direction]
    if math.dist(total, expected) > max(1e-4, expected_force_n*2e-5):
        raise ValueError('Actual INP resultant does not match requested force')
    projected = {}
    for n, force in loads.items():
        along = math.fsum(force[i]*direction[i] for i in range(3))
        if along <= 0 or math.dist(force, [along*v for v in direction]) > max(1e-8, expected_force_n*1e-7):
            raise ValueError('INP contains off-axis or opposing nodal load')
        projected[n] = along
    scalar_sum = math.fsum(projected.values())
    center = [math.fsum(points[n][i]*a for n, a in projected.items())/scalar_sum for i in range(3)]
    moment = [math.fsum((points[n][1]*f[2]-points[n][2]*f[1]) for n, f in loads.items()),
              math.fsum((points[n][2]*f[0]-points[n][0]*f[2]) for n, f in loads.items()),
              math.fsum((points[n][0]*f[1]-points[n][1]*f[0]) for n, f in loads.items())]
    if not all(math.isfinite(v) for v in center + moment):
        raise ValueError('Invalid INP center/moment')
    return {'applied_node_count':len(loads),'total_force_n':total,
            'force_application_center_mm':center,'moment_about_global_origin_n_mm':moment}


def compare_verified_runs(jobs_dir, runs):
    """Compare CLOAD physics for three *already* independently verified runs.

    No comparison is permitted if any INP is missing/malformed; the caller must
    not treat an unavailable diagnostic as '0 mm' drift or a passed check.
    """
    if not isinstance(runs, list) or len(runs) != 3:
        raise ValueError('Three independently verified FEA runs are required')
    roots = Path(jobs_dir) / 'fea_runs'
    ids = [row.get('run_id') if isinstance(row, dict) else None for row in runs]
    import re
    if any(not isinstance(rid, str) or not re.fullmatch('[a-f0-9]{32}', rid) for rid in ids) or len(set(ids)) != 3:
        raise ValueError('Unique, verified 32-hex run IDs required')
    rows = [audit_verified_deck(roots / rid / 'geofield_case.inp', run['force_n'], run['direction'])
            for rid,run in zip(ids,runs)]
    base = rows[0]['total_force_n']
    magnitude = math.sqrt(math.fsum(x*x for x in base))
    resultant_deviation = [math.dist(base,r['total_force_n']) for r in rows[1:]]
    if max(resultant_deviation)>max(1e-4,magnitude*2e-5):
        raise ValueError('Real mesh INP resultant changed between runs')
    # The cross-product moment is origin-independent for equal resultants.
    moment_steps = [math.dist(rows[i]['moment_about_global_origin_n_mm'],rows[i+1]['moment_about_global_origin_n_mm'])
                    for i in (0,1)]
    arm_steps = [moment/magnitude for moment in moment_steps]
    centers = [r['force_application_center_mm'] for r in rows]
    passes = all(arm <= REVIEW_LEVER_ARM_MM for arm in arm_steps)
    return {
        'status':'evaluated_from_three_verified_inp_decks',
        'read_only':True, 'convergence_certified':False,
        'actual_load_nodes':[r['applied_node_count'] for r in rows],
        'force_application_centers_mm':centers,
        'center_step_distances_mm':[math.dist(centers[i], centers[i+1]) for i in (0,1)],
        'moment_step_changes_n_mm':moment_steps,
        'moment_equivalent_lever_arm_step_mm':arm_steps,
        'review_threshold_mm':REVIEW_LEVER_ARM_MM,
        'moment_comparable_for_mesh_only_review':passes,
        'warning':('Actual INP load moment changed beyond review screen; stress differences are not mesh-only evidence.'
                   if not passes else 'Load-moment drift is within review screen, NOT proof of convergence.'),
    }
