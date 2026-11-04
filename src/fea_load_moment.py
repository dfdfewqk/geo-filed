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


# GEOFIELD_D6_REAL_INP_PHYSICS_SCREEN_V1
# A conservative SCREEN for two distinct STEP meshes. It cannot prove that
# two selected CAD faces are mechanically identical or that stresses converged.
D6_SUPPORT_BBOX_MAX_DRIFT_MM = 0.05
D6_LOAD_REGION_MAX_DRIFT_MM = 0.10
D6_LOAD_CENTER_MAX_DRIFT_MM = 0.10
D6_MOMENT_LEVER_ARM_MAX_DRIFT_MM = REVIEW_LEVER_ARM_MM


def _audit_cross_geometry_regions(path):
    """Read only exact INP node/BOUNDARY/CLOAD cards and their spatial extents.

    Require *explicit* zero-displacement x/y/z fixed nodes. Avoid *NSET aliases,
    external INCLUDE, gravity/body loads, partial restraints, and nonplanar
    or degenerate supports. Exact CAD surface mapping is NOT established.
    """
    p=Path(path)
    if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=MAX_INP_BYTES:
        raise ValueError('Physical A/B screen requires a real, bounded INP deck')
    points={}
    fixed_dofs={}
    load_nodes=set()
    section=''
    boundary_sections=0
    cload_sections=0
    with p.open('r',encoding='ascii') as handle:
        for raw in handle:
            line=raw.strip()
            if not line or line.startswith('**'):
                continue
            if line.startswith('*'):
                keyword=line.split(',',1)[0].upper().strip()
                if keyword=='*INCLUDE' or keyword=='*DLOAD':
                    raise ValueError('External includes or gravity body loads cannot be screened')
                section=keyword
                if keyword=='*BOUNDARY':
                    boundary_sections+=1
                    if line.upper()!='*BOUNDARY':
                        raise ValueError('Unsupported boundary keyword options')
                if keyword=='*CLOAD':
                    cload_sections+=1
                    if line.upper()!='*CLOAD':
                        raise ValueError('Unsupported CLOAD keyword options')
                continue
            if section=='*NODE':
                parts=[x.strip() for x in line.split(',')]
                if len(parts)!=4:
                    raise ValueError('Malformed INP node coordinates')
                idx=int(parts[0])
                xyz=[float(x) for x in parts[1:]]
                if idx<=0 or idx in points or any(not math.isfinite(x) for x in xyz):
                    raise ValueError('Invalid or duplicate INP node')
                points[idx]=xyz
                if len(points)>MAX_NODES:
                    raise ValueError('INP node limit exceeded')
            elif section=='*BOUNDARY':
                vals=[x.strip() for x in line.split(',')]
                if len(vals)!=4:
                    raise ValueError('Expected explicit 3-DOF zero boundary per node')
                node,first,last=int(vals[0]),int(vals[1]),int(vals[2])
                displacement=float(vals[3])
                if (node<=0 or first!=1 or last!=3 or
                    not math.isfinite(displacement) or displacement!=0. or
                    node in fixed_dofs):
                    raise ValueError('Partial, duplicate or nonzero support condition')
                fixed_dofs[node]=True
            elif section=='*CLOAD':
                parts=[v.strip() for v in line.split(',')]
                if len(parts)!=3:
                    raise ValueError('Malformed applied nodal load')
                node,axis,value=int(parts[0]),int(parts[1]),float(parts[2])
                if node<=0 or axis not in (1,2,3) or not math.isfinite(value):
                    raise ValueError('Malformed applied force')
                load_nodes.add(node)
    if (boundary_sections!=1 or cload_sections!=1 or len(fixed_dofs)<3 or
        len(load_nodes)<2 or
        any(x not in points for x in fixed_dofs) or
        any(x not in points for x in load_nodes) or
        set(fixed_dofs)&load_nodes):
        raise ValueError('Insufficient independently measured support/load nodes')

    def bounds(ids):
        out=[]
        for i in range(3):
            values=[points[idx][i] for idx in ids]
            out.extend([min(values),max(values)])
        return out
    fixed_bbox=bounds(fixed_dofs)
    loaded_bbox=bounds(load_nodes)
    spans=[fixed_bbox[i+1]-fixed_bbox[i] for i in (0,2,4)]
    planar=[i for i,span in enumerate(spans) if span<=1e-4]
    if len(planar)!=1 or sorted(spans)[1]<1.0:
        raise ValueError('One planar, nondegenerate support area is required')
    return {
        'fixed_node_count':len(fixed_dofs),
        'loaded_node_count':len(load_nodes),
        'fixed_bbox_mm':fixed_bbox,
        'loaded_bbox_mm':loaded_bbox,
        'fixed_plane_axis':planar[0],
        'fixed_plane_coordinate_mm':fixed_bbox[2*planar[0]],
        'source':'actual_serialized_inp_node_boundary_cload_only'}


def screen_two_geometry_verified_inp(jobs_dir, original, variant):
    """Check spatial SUPPORT/LOAD bounds plus actual force/moment in two INPs.

    Caller must FIRST independently verify both real INP/STA/FRD runs via
    fea_compare._side. All checks are fail-closed screening thresholds, not
    tolerance standards or full physical face correspondence certification.
    """
    import re
    if (not isinstance(original,dict) or not isinstance(variant,dict) or
        original.get('evidence')!='real_solver_files_revalidated' or
        variant.get('evidence')!='real_solver_files_revalidated'):
        raise ValueError('Independent real solver verification is mandatory')
    base=Path(jobs_dir)/'fea_runs'
    records=[]
    for row in (original,variant):
        rid=row.get('run_id')
        if not isinstance(rid,str) or not re.fullmatch('[0-9a-f]{32}',rid):
            raise ValueError('Actual solver run ID is missing')
        if row.get('self_weight_applied') is not False:
            raise ValueError('Different solids with self-weight cannot use CLOAD-only moment screening')
        deck=base/rid/'geofield_case.inp'
        physics=audit_verified_deck(deck,row.get('force_n'),row.get('direction'))
        region=_audit_cross_geometry_regions(deck)
        records.append((physics,region))
    (ap,ar),(bp,br)=records
    if ar['fixed_plane_axis']!=br['fixed_plane_axis']:
        raise ValueError('Rechosen supports are on different coordinate planes')
    mag=math.sqrt(math.fsum(v*v for v in ap['total_force_n']))
    if mag<=0:
        raise ValueError('Invalid applied resultant for geometry comparison')
    resultant_drift=math.dist(ap['total_force_n'],bp['total_force_n'])
    moment_drift=math.dist(ap['moment_about_global_origin_n_mm'],
                           bp['moment_about_global_origin_n_mm'])
    lever_drift=moment_drift/mag
    center_drift=math.dist(ap['force_application_center_mm'],
                           bp['force_application_center_mm'])
    support_bbox_drift=max(abs(a-b) for a,b in
                           zip(ar['fixed_bbox_mm'],br['fixed_bbox_mm']))
    load_bbox_drift=max(abs(a-b) for a,b in
                        zip(ar['loaded_bbox_mm'],br['loaded_bbox_mm']))
    if not all(math.isfinite(v) for v in (
        resultant_drift,moment_drift,lever_drift,center_drift,
        support_bbox_drift,load_bbox_drift)):
        raise ValueError('Non-finite physical loading diagnostic')
    if resultant_drift>max(1e-4,mag*2e-5):
        raise ValueError('Measured INP force resultant changed')
    if lever_drift>D6_MOMENT_LEVER_ARM_MAX_DRIFT_MM:
        raise ValueError('Measured load moment arm changed beyond screening threshold')
    if center_drift>D6_LOAD_CENTER_MAX_DRIFT_MM:
        raise ValueError('Measured physical load application center drifted')
    if support_bbox_drift>D6_SUPPORT_BBOX_MAX_DRIFT_MM:
        raise ValueError('Actual fixed-support bounding coordinates changed')
    if load_bbox_drift>D6_LOAD_REGION_MAX_DRIFT_MM:
        raise ValueError('Actual loaded nodal region coordinates changed')

    return {
        'status':'real_two_inp_load_support_screen_passed',
        'source':'two_real_reverified_inp_decks_node_boundary_cload',
        'read_only':True,'gravity_body_loads_included':False,
        'support_bbox_max_drift_mm':support_bbox_drift,
        'load_bbox_max_drift_mm':load_bbox_drift,
        'load_center_distance_mm':center_drift,
        'resultant_drift_n':resultant_drift,
        'load_moment_change_n_mm':moment_drift,
        'load_moment_equivalent_lever_arm_change_mm':lever_drift,
        'fixed_plane_axis':ar['fixed_plane_axis'],
        'support_bounding_screen_passed':True,
        'applied_load_and_moment_screen_passed':True,
        'physical_cad_surface_correspondence_verified':False,
        'reaction_equilibrium_correspondence_verified':False,
        'geometry_improvement_verified':False,
        'structural_safety_certified':False,
        'warning':('Only real INP nodal support/load extents, force and applied '
                   'moment passed conservative review screens. Identical CAD '
                   'face shapes, reaction forces, stress convergence, and design '
                   'safety are not proven.') }
