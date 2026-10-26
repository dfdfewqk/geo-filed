"""Research-only, read-only positive nodal load moment-balancing proposal.

This is NOT a uniform-pressure traction law, not an actual FE solver result,
and not a change to production CalculiX CLOAD decks. It finds a candidate
positive redistribution over existing free load nodes which preserves the
requested resultant and the two physically relevant moment components.

Inputs are actual nodal positions, previously applied (parallel) nodal forces,
and the actual meshed surface area centroid. No private data are written.
"""
from __future__ import annotations

import math


def _vector(v, label):
    if not isinstance(v, (tuple, list)) or len(v) != 3 or any(
            type(x) not in (int, float) or not math.isfinite(x) for x in v):
        raise ValueError(label + ': expected three finite numeric components')
    return tuple(float(x) for x in v)


def _basis(direction):
    # Numerically stable orthonormal basis perpendicular to force direction.
    pivot = (1., 0., 0.) if abs(direction[0]) < 0.9 else (0., 1., 0.)
    parallel = sum(a*b for a,b in zip(pivot, direction))
    u = [pivot[k] - parallel*direction[k] for k in range(3)]
    size = math.sqrt(sum(x*x for x in u))
    u = tuple(x/size for x in u)
    v = (direction[1]*u[2]-direction[2]*u[1],
         direction[2]*u[0]-direction[0]*u[2],
         direction[0]*u[1]-direction[1]*u[0])
    return u, v


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0]]


def propose_free_node_moment_balance(nodes, original_loads, fixed_nodes,
                                     surface_area_centroid_mm, direction,
                                     *, tolerance_mm=1e-7, max_iterations=90):
    """Find candidate positive loads with same sum and area-centroid moment.

    Based on minimum relative entropy (KL divergence) from original nodal
    weights; uses damped Newton updates of the exponential tilt. A solution
    exists only if the target projected centroid lies in the convex hull of
    existing free loaded nodes. Ill-conditioned cases fail closed.

    Returns diagnostics AND candidate_loads, which must NOT be used as solver
    input until independently reviewed and a new CalculiX comparison is run.
    """
    d = _vector(direction, 'direction')
    if abs(math.fsum(x*x for x in d)-1) > 1e-8:
        raise ValueError('Load direction must be a unit vector')
    target = _vector(surface_area_centroid_mm, 'surface centroid')
    if not isinstance(nodes, dict) or not isinstance(original_loads, dict) or not original_loads:
        raise ValueError('Missing actual load nodes')
    if type(tolerance_mm) not in (int,float) or not 0 < tolerance_mm <= 0.001:
        raise ValueError('Invalid tolerance')
    if type(max_iterations) is not int or not 1 <= max_iterations <= 200:
        raise ValueError('Invalid iteration limit')
    fixed = set(fixed_nodes)
    u, v = _basis(d)
    node_ids = sorted(original_loads)
    coords, weights = [], []
    for n in node_ids:
        if type(n) is not int or n <= 0 or n in fixed or n not in nodes:
            raise ValueError('Candidate cannot load fixed/unknown nodes')
        p, force = _vector(nodes[n], 'node'), _vector(original_loads[n], 'nodal force')
        w = math.fsum(force[k]*d[k] for k in range(3))
        if w <= 0 or not math.isfinite(w) or math.dist(force, tuple(w*a for a in d)) > max(1e-8, w*1e-8):
            raise ValueError('Nonparallel, zero or reversed original load')
        coords.append(p)
        weights.append(w)
    total = math.fsum(weights)
    if total <= 0 or not math.isfinite(total):
        raise ValueError('Invalid original resultant')
    xy = [(math.fsum((p[k]-target[k])*u[k] for k in range(3)),
           math.fsum((p[k]-target[k])*v[k] for k in range(3))) for p in coords]
    # Scale the Newton unknowns by geometry, not raw-world coordinates.
    span = max((math.hypot(x,y) for x,y in xy), default=0.)
    if span < 1e-9:
        raise ValueError('Loaded free nodes do not span a surface')
    xy = [(x/span,y/span) for x,y in xy]
    base = [w/total for w in weights]
    logs = [math.log(w) for w in base]

    def evaluate(lam0, lam1):
        terms = [logw+lam0*x+lam1*y for logw,(x,y) in zip(logs, xy)]
        peak = max(terms)
        exp_terms = [math.exp(t-peak) for t in terms]
        scale = math.fsum(exp_terms)
        a = [t/scale for t in exp_terms]
        mx = math.fsum(a[i]*xy[i][0] for i in range(len(a)))
        my = math.fsum(a[i]*xy[i][1] for i in range(len(a)))
        cxx = math.fsum(a[i]*(xy[i][0]-mx)**2 for i in range(len(a)))
        cyy = math.fsum(a[i]*(xy[i][1]-my)**2 for i in range(len(a)))
        cxy = math.fsum(a[i]*(xy[i][0]-mx)*(xy[i][1]-my) for i in range(len(a)))
        # KL convex dual f(lambda)=log(sum(w_i*exp(lambda*p_i)))
        # Its gradient is the projected candidate center offset.
        objective = peak+math.log(scale)
        return a, mx, my, cxx, cyy, cxy, objective

    la=lb=0.
    original = [math.fsum(base[i]*coords[i][k] for i in range(len(base))) for k in range(3)]
    convergence = False
    for iteration in range(max_iterations):
        a,mx,my,cxx,cyy,cxy,obj = evaluate(la, lb)
        if math.hypot(mx,my)*span <= tolerance_mm:
            convergence=True;break
        det = cxx*cyy-cxy*cxy
        if det <= max(1e-21, cxx*cyy*1e-11):
            raise ValueError('Moment balancing is geometrically ill-conditioned')
        # Newton correction C^{-1} mean; take a damped step when far from center.
        dl0=(-cyy*mx+cxy*my)/det
        dl1=(cxy*mx-cxx*my)/det
        scale_step=1.
        old_err = math.hypot(mx,my)
        while scale_step > 1/65536:
            n0=la+scale_step*dl0;n1=lb+scale_step*dl1
            nxt=evaluate(n0,n1)
            if math.hypot(nxt[1],nxt[2]) < old_err*(1-1e-5*scale_step):
                la=n0;lb=n1;break
            scale_step*=0.5
        else:
            raise ValueError('Free nodal weights cannot preserve target moment')
    if not convergence:
        raise ValueError('Moment balancing did not converge: target may be outside free-node convex hull')
    fractions=evaluate(la,lb)[0]
    candidate={n:[total*fractions[i]*d[k] for k in range(3)]
               for i,n in enumerate(node_ids)}
    center=[math.fsum(fractions[i]*coords[i][k] for i in range(len(node_ids))) for k in range(3)]
    base_moment=_cross(original, [total*x for x in d])
    candidate_moment=_cross(center, [total*x for x in d])
    target_moment=_cross(target, [total*x for x in d])
    if math.dist(candidate_moment,target_moment)/total > tolerance_mm*1.01:
        raise ValueError('Resultant moment validation failed')
    if len(candidate)!=len(original_loads) or any(n in fixed for n in candidate):
        raise ValueError('Candidate is not restricted to free loaded nodes')
    return {
        'status':'research_only_positive_free_node_moment_balancing_proposal',
        'solver_executed':False, 'candidate_not_uniform_pressure':True,
        'not_approved_for_production':True, 'load_node_count':len(candidate),
        'total_force_n':[total*d[k] for k in range(3)],
        'requested_surface_center_mm':list(target),
        'original_force_center_mm':original,
        'candidate_force_center_mm':center,
        'original_moment_error_n_mm':math.dist(base_moment,target_moment),
        'candidate_moment_error_n_mm':math.dist(candidate_moment,target_moment),
        'original_center_shift_perpendicular_mm':math.dist(base_moment,target_moment)/total,
        'candidate_center_shift_perpendicular_mm':math.dist(candidate_moment,target_moment)/total,
        'relative_nodal_force_changes':{
            'max_absolute_percent':max(abs(fractions[i]/base[i]-1)*100 for i in range(len(base))),
            'mean_absolute_weighted_percent':math.fsum(abs(fractions[i]-base[i]) for i in range(len(base)))*100,
            'max_force_multiplier':max(fractions[i]/base[i] for i in range(len(base))),
        },
        'iterations':iteration,
        'candidate_loads':candidate,
        'warning':'This is a force-and-moment-equivalent proposal, NOT uniform surface pressure or a new CalculiX result.'
    }
