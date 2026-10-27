"""Run actual opt-in GeoField production C3D10 end-to-end, three sizes.

No fake solver or transformed research deck. FEA source is the production
payload/fea_solver.py and C3D10 is explicitly requested in each signed case.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
from verify_three_mesh_real_ci import reference_case,sha256,relative_percent

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'src'/'payload'),str(ROOT/'src'/'tests'/'fea_ci_dependencies')]
from fea_solver import run_real_fea


def run():
    step,physics,model=reference_case(ROOT,sha256(ROOT/'src'/'payload'/'fea_solver.py'))
    physics.pop('solver_sha256')
    profile=os.environ.get('GEOFIELD_C3D10_MESH_PROFILE','standard')
    traction=os.environ.get('GEOFIELD_C3D10_TRACTION_MODEL','legacy')
    profiles={'standard':(3.,2.25,1.7),'finer':(2.25,1.7,1.3),
              'deep':(1.7,1.3,1.0)}
    if profile not in profiles or traction not in ('legacy','full_tri6'):
        raise ValueError('Unsupported explicit C3D10 research study profile')
    if profile=='standard' and traction=='legacy':
        base=ROOT/'_fea_production_c3d10_evidence'
    else:
        base=ROOT/('_fea_production_c3d10_'+profile+'_'+traction+'_evidence')
    base.mkdir(parents=True,exist_ok=True)
    summary=[]
    for size in profiles[profile]:
        case=copy.deepcopy(physics)
        case.update(schema='geofield-fea-case-v1',status='configuration_prepared_solver_not_connected')
        case['mesh_request']={'target_element_size_mm':size,'element_type':'C3D10'}
        if traction=='full_tri6':
            case['mesh_request']['traction_model']='straight_tri6_full_consistent'
        case['case_sha256']=hashlib.sha256(json.dumps(case,sort_keys=True).encode()).hexdigest()
        folder=base/str(size).replace('.','_');folder.mkdir(exist_ok=True)
        (folder/'case.json').write_text(json.dumps(case,indent=2),encoding='utf-8')
        result=run_real_fea(step,case,model,folder)
        (folder/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        expected=('geofield_case.inp','geofield_case.sta','geofield_case.frd','geofield_case.dat','geofield_fea_surface_field.json')
        if any(not (folder/x).is_file() or not (folder/x).stat().st_size for x in expected):
            raise RuntimeError('Missing real C3D10 solver/visualization evidence')
        raw=(folder/'geofield_case.inp').read_text(encoding='ascii')
        if '*ELEMENT, TYPE=C3D10' not in raw or 'TYPE=C3D4' in raw:
            raise RuntimeError('Wrong FE type in actual ccx input')
        if result['mesh']['element_type']!='C3D10':raise RuntimeError('Wrong result provenance')
        expected_traction=('straight_tri6_full_consistent' if traction=='full_tri6'
                           else 'free_node_moment_equivalent')
        if result['mesh'].get('traction_model')!=expected_traction:
            raise RuntimeError('Saved case and real solver traction model differ')
        reaction=result['support_reaction_equilibrium_audit']
        if not reaction['checked']:raise RuntimeError('Unverified actual C3D10 reaction force')
        load=result['load_equilibrium_audit']
        if (load['moment_equivalent_within_roundoff'] is not True or
            load['written_inp_cload_verified'] is not True):
            raise RuntimeError('Invalid actual C3D10 distributed surface load')
        field=json.loads((folder/'geofield_fea_surface_field.json').read_text(encoding='utf8'))
        if len(field['positions_mm'])<10 or not len(field['triangles']):
            raise RuntimeError('Second-order midside field not generated')
        # Real solver outputs: used to assess numerical stability, never certify safety.
        metrics=result['results']
        row={'target_mesh_mm':size,'element_type':result['mesh']['element_type'],
             'traction_model':result['mesh'].get('traction_model'),
             'nodes':result['mesh']['node_count'],'elements':result['mesh']['tetrahedron_count'],
             'maximum_displacement_mm':metrics['maximum_displacement_mm'],
             'maximum_von_mises_mpa':metrics['maximum_nodal_von_mises_mpa'],
             'reaction_force_residual_n':reaction['force_residual_magnitude_n'],
             'reaction_moment_residual_n_mm':reaction['moment_residual_magnitude_n_mm'],
             'surface_triangles':len(field['triangles']),
             'actual_original_load_triangle_count':load['surface_triangle_count'],
             'source_sha256':sha256(folder/'geofield_case.inp'),
             'output_sha256':{ext:sha256(folder/('geofield_case.'+ext)) for ext in ('sta','frd','dat')}}
        print('PRODUCTION_C3D10_SOLVE='+json.dumps(row),flush=True)
        summary.append(row)
    change_u=[relative_percent(a['maximum_displacement_mm'],b['maximum_displacement_mm']) for a,b in zip(summary,summary[1:])]
    change_s=[relative_percent(a['maximum_von_mises_mpa'],b['maximum_von_mises_mpa']) for a,b in zip(summary,summary[1:])]
    final={'status':'real_production_opt_in_C3D10_3_run_completed',
           'profile':profile,'traction_model':traction,
           'rows':summary,'adjacent_displacement_change_percent':change_u,
           'adjacent_stress_change_percent':change_s,
           'numeric_stability_screen_passes':all(x<5. for x in change_u+change_s),
           'uniform_traction_locally_exact_at_fixed_load_shared_edge':False,
           'engineering_safety_or_mathematical_convergence_certified':False,
           'windows_integration_verified':False,
           'production_element_type_default_remains_C3D4':True}
    (base/'production_c3d10_summary.json').write_text(json.dumps(final,indent=2),encoding='utf8')
    print('PRODUCTION_C3D10_THREE_MESH_RESULT='+json.dumps(final),flush=True)
    return final

if __name__=='__main__':run()
