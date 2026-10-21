"""Read-only engineering SCREEN for a proposed correction of a nodal surface load.

This checks provenance against the *actual meshed triangles*: it does not
create an INP deck, call CalculiX, certify uniform traction, or establish that
local stresses after redistribution improve. A screen pass permits a controlled
A/B solver study only; it must never activate the research candidate in the
production solver.
"""
from __future__ import annotations

import math

from fea_moment_balancing import propose_free_node_moment_balance

# Deliberately engineering-review thresholds, not universal standards.
MAX_REWEIGHT_PERCENT_FOR_STUDY = 10.0
MAX_EXCLUDED_AREA_WEIGHT_PERCENT_FOR_STUDY = 5.0


def _vec3(value, name):
    if not isinstance(value, (tuple, list)) or len(value) != 3 or any(
        type(x) not in (float, int) or not math.isfinite(x) for x in value
    ):
        raise ValueError(f'{name}: finite three-vector required')
    return tuple(float(x) for x in value)


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def review_actual_surface_candidate(nodes, loaded_surface_triangles, fixed_nodes,
                                    original_loads, direction):
    """Validate actual surface topology, original discretization and a candidate.

    `loaded_surface_triangles` must be obtained independently from the selected
    Gmsh load surface, not fabricated from the desired center. They are not
    reconstructed from the load nodes alone. `original_loads` must correspond
    to the current INP CLOADs and are never modified by this function.

    Returns a research-only diagnostic plus an unapplied candidate.
    """
    if not isinstance(nodes, dict) or not nodes:
        raise ValueError('Missing meshed node coordinates')
    if not isinstance(original_loads, dict) or not original_loads:
        raise ValueError('Missing original loaded node forces')
    direction = _vec3(direction, 'direction')
    if abs(math.fsum(x*x for x in direction) - 1) > 1e-8:
        raise ValueError('Force direction must be a unit vector')
    if not isinstance(loaded_surface_triangles, (tuple, list)) or not loaded_surface_triangles:
        raise ValueError('Missing real load-surface triangle list')
    if len(loaded_surface_triangles) > 500_000:
        raise ValueError('Surface triangle count exceeds review limit')
    try:
        fixed = set(fixed_nodes)
    except TypeError as exc:
        raise ValueError('Invalid fixed node set') from exc
    all_weights: dict[int, float] = {}
    triangles_seen = set()
    area_rows = []
    center_numerator = [[], [], []]
    for tri in loaded_surface_triangles:
        if not isinstance(tri, (list, tuple)) or len(tri) != 3 or any(
            type(n) is not int or n <= 0 or n not in nodes for n in tri
        ) or len(set(tri)) != 3:
            raise ValueError('Invalid selected surface triangle')
        key = tuple(sorted(tri))
        if key in triangles_seen:
            raise ValueError('Repeated surface triangle')
        triangles_seen.add(key)
        a, b, c = (_vec3(nodes[n], 'mesh node') for n in tri)
        ab = [b[k] - a[k] for k in range(3)]
        ac = [c[k] - a[k] for k in range(3)]
        area = math.sqrt(math.fsum(x*x for x in _cross(ab, ac)))*0.5
        if not math.isfinite(area) or area <= 1e-12:
            raise ValueError('Zero-area or invalid selected surface triangle')
        area_rows.append(area)
        for k in range(3):
            center_numerator[k].append(area * math.fsum((a[k], b[k], c[k])) / 3.)
        for n in tri:
            all_weights[n] = all_weights.get(n, 0.) + area/3.
    total_area = math.fsum(area_rows)
    target = [math.fsum(row)/total_area for row in center_numerator]
    free = {n: w for n, w in all_weights.items() if n not in fixed}
    if len(free) < 3 or math.fsum(free.values()) <= 0:
        raise ValueError('Insufficient free loaded-surface nodes')
    if set(original_loads) != set(free):
        raise ValueError('Original CLOAD node set does not match the free load surface')
    weights_total = math.fsum(free.values())
    force_mag_rows = []
    for n in sorted(free):
        force = _vec3(original_loads[n], 'original CLOAD')
        scalar = math.fsum(force[k]*direction[k] for k in range(3))
        if scalar <= 0 or math.dist(force, [scalar*d for d in direction]) > max(1e-9, scalar*1e-8):
            raise ValueError('Original CLOAD has off-axis or reversed force')
        force_mag_rows.append(scalar)
    total_force = math.fsum(force_mag_rows)
    if not math.isfinite(total_force) or total_force <= 0:
        raise ValueError('Invalid total nodal force')
    # Compare serialized CLOAD to the exact area/3 free-node weighting used by
    # the GeoField production solver; a different physical load law is NOT the
    # same case and cannot be treated as a moment-correction candidate.
    for n, w in free.items():
        applied = math.fsum(original_loads[n][k]*direction[k] for k in range(3))
        expected = total_force*w/weights_total
        if abs(applied-expected) > max(1e-9, expected*1e-7):
            raise ValueError('Original CLOAD differs from surface-area nodal weighting')
    balance = propose_free_node_moment_balance(nodes, original_loads, fixed,
                                               target, direction)
    candidate = balance['candidate_loads']
    # Independent physical audit, not only the research optimizer's own report.
    result = [math.fsum(force[k] for force in candidate.values()) for k in range(3)]
    expected_force = [total_force*d for d in direction]
    if math.dist(result, expected_force) > max(1e-7, total_force*1e-8):
        raise ValueError('Independent candidate resultant check failed')
    actual_moment = [math.fsum(_cross(_vec3(nodes[n], 'node'), f)[k]
                                for n, f in candidate.items()) for k in range(3)]
    expected_moment = _cross(target, expected_force)
    moment_residual = math.dist(actual_moment, expected_moment)
    if moment_residual/total_force > 1e-6:
        raise ValueError('Independent candidate moment check failed')
    ratios = [math.fsum(candidate[n][k]*direction[k] for k in range(3)) /
              math.fsum(original_loads[n][k]*direction[k] for k in range(3)) for n in sorted(free)]
    max_reweight = max(abs(r-1.)*100 for r in ratios)
    excluded_share = max(0., (total_area - weights_total)/total_area)*100
    reasons = []
    if max_reweight > MAX_REWEIGHT_PERCENT_FOR_STUDY:
        reasons.append('Candidate changes individual nodal loads beyond the 10% research review screen')
    if excluded_share > MAX_EXCLUDED_AREA_WEIGHT_PERCENT_FOR_STUDY:
        reasons.append('Fixed/free boundary excludes more than 5% of area/3 load weight')
    return {
        'status': ('eligible_for_controlled_solver_ab_comparison_only' if not reasons
                   else 'research_screen_failed_do_not_stage'),
        'passes_research_screen': not reasons,
        'reasons': reasons,
        'solver_executed': False,
        'production_loads_changed': False,
        'uniform_pressure_equivalent': False,
        'safety_or_mesh_convergence_certified': False,
        'source': 'actual_meshed_load_surface_triangles_and_original_cload',
        'surface_triangle_count': len(triangles_seen),
        'free_load_node_count': len(free),
        'shared_fixed_node_count': len(set(all_weights) & fixed),
        'surface_area_mm2': total_area,
        'surface_area_centroid_mm': target,
        'excluded_area_weight_percent': excluded_share,
        'resultant_n': expected_force,
        'original_moment_error_n_mm': balance['original_moment_error_n_mm'],
        'candidate_moment_error_n_mm': moment_residual,
        'maximum_nodal_force_change_percent': max_reweight,
        'candidate_loads_unapplied': candidate,
        'warning': ('A pass is only permission to compare TWO independently solved decks. '
                    'Equal resultant and moment do not imply equal pressure, local stress, displacement, or safety.'),
    }
