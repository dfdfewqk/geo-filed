"""Real solver validation of the video-like SUS304 / 10kg / +X load.

Loads the published locked L-bracket STEP and same physical planes used in
reference_case.  The original FreeCAD viewer face IDs 3 and 1 in a Windows
video cannot be presumed identical to Gmsh's mapped face IDs.
Never claim this is a numerical replay of the user's original project/run.
"""
from __future__ import annotations
import copy,hashlib,json,math,os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'src'/'payload'),str(ROOT/'src'/'tests'/'fea_ci_dependencies'),str(ROOT/'src'/'tests')]
from verify_three_mesh_real_ci import reference_case,sha256,relative_percent
from fea_solver import run_real_fea

SHA='fe65841074c5fc6bd74442b147e5688490ec1ad79d5fb1e41bdccd3514bccf32'
STUDY_PROFILES={'comparison':(('C3D4','free_node_moment_equivalent'),
                              ('C3D10','straight_tri6_full_consistent')),
                 'deep':(('C3D10','straight_tri6_full_consistent'),)}
LEVELS={'comparison':(3.0,2.25,1.7),'deep':(1.7,1.3,1.0)}
def run():
    step,base,model=reference_case(ROOT,sha256(ROOT/'src/payload/fea_solver.py'))
    if sha256(step)!=SHA:raise RuntimeError('Public fixture changed')
    base.pop('solver_sha256')
    base['material']={'young_modulus_mpa':193000.,'poisson_ratio':.29}
    base['boundary_conditions']['total_force_n']=98.0665
    base['boundary_conditions']['force_direction_unit']=[1.,0.,0.]
    base['self_weight_reference']={'applied_to_solver':False}
    profile=os.environ.get('GEOFIELD_SUS304_FEA_PROFILE','comparison')
    if profile not in STUDY_PROFILES:raise ValueError('Invalid video-like FEA study profile')
    root=ROOT/('_fea_windows_video_like_comparison' if profile=='comparison'
              else '_fea_windows_video_like_deep')
    root.mkdir(exist_ok=True)
    rows=[]
    for typ,traction in STUDY_PROFILES[profile]:
        cases=[]
        for mm in LEVELS[profile]:
            case=copy.deepcopy(base)
            case.update(schema='geofield-fea-case-v1',
                        status='configuration_prepared_solver_not_connected')
            case['mesh_request']={'target_element_size_mm':mm,'element_type':typ}
            if typ=='C3D10':
                case['mesh_request']['traction_model']=traction
            case['case_sha256']=hashlib.sha256(json.dumps(case,sort_keys=True).encode()).hexdigest()
            folder=root/typ/str(mm).replace('.','_')
            folder.mkdir(parents=True,exist_ok=True)
            (folder/'input_case.json').write_text(json.dumps(case,ensure_ascii=False,indent=2),encoding='utf8')
            result=run_real_fea(step,case,model,folder)
            (folder/'solver_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
            for name in ('geofield_case.inp','geofield_case.sta',
                         'geofield_case.dat','geofield_case.frd',
                         'geofield_fea_surface_field.json'):
                p=folder/name
                if not p.is_file() or not p.stat().st_size:raise RuntimeError('Missing real CalculiX output '+name)
            evidence=result['load_equilibrium_audit']
            reaction=result['support_reaction_equilibrium_audit']
            if (result['cad_sha256']!=SHA or
                result['case_sha256']!=case['case_sha256'] or
                result['mesh']['element_type']!=typ or
                result['mesh']['traction_model']!=traction or
                not evidence['written_inp_cload_verified'] or
                not evidence['moment_equivalent_within_roundoff'] or
                not reaction['checked']):
                raise RuntimeError('Actual load/mesh/FRD provenance not verified')
            if (reaction['force_residual_magnitude_n']>=0.01 or
                reaction['moment_residual_magnitude_n_mm']>=0.25):
                raise RuntimeError('Support reactions not in force/moment equilibrium')
            vals=result['results']
            row={'element_type':typ,'traction_model':traction,'target_mm':mm,
                 'max_vm_mpa':vals['maximum_nodal_von_mises_mpa'],
                 'max_u_mm':vals['maximum_displacement_mm'],
                 'nodes':result['mesh']['node_count'],
                 'tets':result['mesh']['tetrahedron_count'],
                 'support_force_residual_n':reaction['force_residual_magnitude_n'],
                 'case_sha256':case['case_sha256']}
            print('SUS304_ACTUAL_FEA_SOLVE='+json.dumps(row),flush=True)
            cases.append(row)
        drifts_u=[relative_percent(a['max_u_mm'],b['max_u_mm']) for a,b in zip(cases,cases[1:])]
        drifts_s=[relative_percent(a['max_vm_mpa'],b['max_vm_mpa']) for a,b in zip(cases,cases[1:])]
        rows.append({'element_type':typ,'traction_model':traction,
                     'runs':cases,'stress_adjacent_drift_percent':drifts_s,
                     'displacement_adjacent_drift_percent':drifts_u,
                     'five_percent_stability_review':all(v<=5 for v in (*drifts_u,*drifts_s))})
    outcome={'status':'real_ccx_video_like_sus304_10kg_x','profile':profile,
             'cad_sha256':SHA,'physics':base,'distinct_from_user_windows_face_ids':True,
             'element_comparison':rows,
             'design_safety_or_mathematical_convergence_certified':False}
    (root/'comparison_summary.json').write_text(json.dumps(outcome,indent=2,ensure_ascii=False),encoding='utf8')
    print('SUS304_FEA_ACTUAL_COMPARISON='+json.dumps(outcome,ensure_ascii=False),flush=True)
    # The initial 3/2.25/1.7mm screen intentionally records the C3D10
    # non-pass as genuine scientific evidence rather than marking CI broken.
    # Only a separately requested *deep* refinement is used as a hard
    # decision gate for changing future UI defaults.
    if profile=='deep' and not rows[0]['five_percent_stability_review']:
        raise AssertionError('C3D10 full Tri6 did not pass 5% 1.7-1.3-1.0mm SUS304 study; do not change UI default')
    return outcome
if __name__=='__main__':run()
