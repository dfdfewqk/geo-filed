"""Research-only real C3D4/C3D10 bending comparison (NOT a production solver patch).

Runs exactly the same public STEP/material/load and Gmsh linear volume mesh;
adds shared straight midside nodes to form true quadratic tetra elements. The
original CLOAD at vertex nodes is kept identical, isolating element order.
The load discretization is not a quadratic consistent surface traction; findings
are diagnostic and not mesh-convergence certification.
"""
from __future__ import annotations
import copy, hashlib, json, math, os, pathlib, re, subprocess, sys
from verify_three_mesh_real_ci import reference_case, sha256

EDGES=((0,1),(1,2),(2,0),(0,3),(1,3),(2,3))

def parse_deck(path):
    nodes={}; tets=[];loads={}; fixed=set(); mat=[]
    section=None
    for raw in pathlib.Path(path).read_text(encoding='ascii').splitlines():
        line=raw.strip()
        if not line or line.startswith('**'): continue
        if line.startswith('*'):
            section=line.upper().split(',')[0]; continue
        a=[q.strip() for q in line.split(',')]
        if section=='*NODE':
            if len(a)!=4: raise ValueError('invalid node')
            nodes[int(a[0])]=tuple(float(z) for z in a[1:])
        elif section=='*ELEMENT':
            if len(a)!=5:raise ValueError('non C3D4 deck')
            tets.append((int(a[0]),tuple(int(z) for z in a[1:])))
        elif section=='*CLOAD':
            if len(a)!=3:raise ValueError('invalid load')
            n,ax,val=int(a[0]),int(a[1]),float(a[2]);loads.setdefault(n,[0.,0.,0.])[ax-1]+=val
        elif section=='*BOUNDARY':
            fixed.add(int(a[0]))
        elif section=='*ELASTIC':
            mat=[float(x) for x in a]
    if not nodes or not tets or not loads or not fixed or len(mat)!=2:raise ValueError('empty deck fields')
    if fixed&set(loads):raise ValueError('fixed node load')
    return nodes,tets,loads,fixed,mat

def make_quadratic(source, dest):
    nodes,tets,loads,fixed,mat=parse_deck(source)
    original_nodes=len(nodes)
    midsides={}
    elements=[]
    next_id=max(nodes)+1
    for eid,corner in tets:
        extra=[]
        for a,b in EDGES:
            edge=tuple(sorted((corner[a],corner[b])))
            if edge not in midsides:
                pa,pb=nodes[edge[0]],nodes[edge[1]]
                midpoint=tuple((pa[j]+pb[j])*.5 for j in range(3))
                if not all(math.isfinite(z) for z in midpoint):raise ValueError('bad midpoint')
                nodes[next_id]=midpoint
                midsides[edge]=next_id
                if edge[0] in fixed and edge[1] in fixed:
                    fixed.add(next_id)
                next_id+=1
            extra.append(midsides[edge])
        elements.append((eid,corner+tuple(extra)))
    if not all(len(set(conn))==10 for _,conn in elements):raise ValueError('bad C3D10')
    if not len(nodes)>original_nodes:raise AssertionError('not quadratic')
    with pathlib.Path(dest).open('w',encoding='ascii') as out:
        out.write('*HEADING\nGeoField - experimental C3D10 comparison, N mm MPa\n*NODE\n')
        for nid, xyz in sorted(nodes.items()):
            out.write(str(nid)+', '+', '.join(f'{v:.14g}' for v in xyz)+'\n')
        out.write('*ELEMENT, TYPE=C3D10, ELSET=VOLUME\n')
        for eid,conn in elements:
            out.write(str(eid)+', '+', '.join(map(str,conn))+'\n')
        out.write('*MATERIAL, NAME=ISOTROPIC\n*ELASTIC\n'+f'{mat[0]:.14g}, {mat[1]:.14g}'+'\n')
        out.write('*SOLID SECTION, ELSET=VOLUME, MATERIAL=ISOTROPIC\n')
        out.write('*NSET, NSET=GEOFIELD_FIXED\n')
        for i in range(0,len(fixed),16):out.write(', '.join(map(str,sorted(fixed)[i:i+16]))+'\n')
        out.write('*STEP\n*STATIC\n1., 1.\n*BOUNDARY\n')
        for nid in sorted(fixed):out.write(f'{nid}, 1, 3, 0.\n')
        out.write('*CLOAD\n')
        for nid,vec in sorted(loads.items()):
            for ax,value in enumerate(vec,1):
                if abs(value)>1e-15:out.write(f'{nid}, {ax}, {value:.13g}\n')
        out.write('*NODE PRINT, NSET=GEOFIELD_FIXED, GLOBAL=YES, TOTALS=NO\nRF\n')
        out.write('*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n')
    return nodes,tets,loads,fixed

def run():
    repo=pathlib.Path(__file__).resolve().parents[2]
    sys.path[:0]=[str(repo/'src'),str(repo/'src'/'tests'/'fea_ci_dependencies'),str(repo/'src'/'payload')]
    from fea_solver import run_real_fea,parse_frd_results,parse_fixed_reactions_dat
    out=repo/'_fea_quadratic_research_evidence';out.mkdir(exist_ok=True)
    step,physics,model=reference_case(repo,sha256(repo/'src'/'payload'/'fea_solver.py'))
    summary=[]
    for size in [3.0,1.7]:
        folder=out/str(size).replace('.','_');folder.mkdir(exist_ok=True)
        case=copy.deepcopy(physics);case.pop('solver_sha256');case.update(schema='geofield-fea-case-v1',status='configuration_prepared_solver_not_connected',mesh_request={'target_element_size_mm':size})
        case['case_sha256']=hashlib.sha256(json.dumps(case,sort_keys=True).encode()).hexdigest()
        original=folder/'linear';original.mkdir(exist_ok=True)
        result=run_real_fea(step,case,model,original)
        lin=result['results'];original_inp=original/'geofield_case.inp'
        quad=folder/'quadratic';quad.mkdir(exist_ok=True)
        quad_inp=quad/'quadratic_case.inp'
        nodes,tets,loads,fixed=make_quadratic(original_inp,quad_inp)
        # CalculiX outputs 1 set per job, real ccx executable is a system package.
        exec_=subprocess.run(['ccx','-i','quadratic_case'],cwd=quad,text=True,capture_output=True,timeout=240)
        (quad/'ccx_stdout.log').write_text(exec_.stdout+'\nSTDERR:\n'+exec_.stderr,encoding='utf8')
        if exec_.returncode!=0:raise RuntimeError(f'C3D10 ccx exit {exec_.returncode}: '+exec_.stdout[-800:]+exec_.stderr[-400:])
        qpath=quad/'quadratic_case.frd';dpath=quad/'quadratic_case.dat';stapath=quad/'quadratic_case.sta'
        if not all(p.is_file() and p.stat().st_size>0 for p in (qpath,dpath,stapath)):
            raise RuntimeError('Quadratic actual solver INP STA FRD DAT incomplete')
        field=parse_frd_results(qpath,nodes,include_fields=True)
        reaction=parse_fixed_reactions_dat(dpath,nodes,fixed,loads)
        if reaction['checked'] is not True:raise RuntimeError('C3D10 equilibrium not verified')
        maxstress=field['maximum_nodal_von_mises_mpa'];maxdisp=field['maximum_displacement_mm']
        row={'target_mesh_mm':size,'element':'C3D10 experimental', 'same_initial_tetrahedron_count':len(tets),'quadratic_nodes':len(nodes),'quadratic_fixed_nodes':len(fixed),'C3D4_displacement_mm':lin['maximum_displacement_mm'],'C3D10_displacement_mm':maxdisp,'C3D4_von_mises_mpa':lin['maximum_nodal_von_mises_mpa'],'C3D10_von_mises_mpa':maxstress, 'reaction_force_residual_n':reaction['force_residual_magnitude_n'],'reaction_moment_residual_n_mm':reaction['moment_residual_magnitude_n_mm'], 'input_identical_corner_CLOAD':True,'note':'C3D10 uses same vertex CLOADs (not consistent quadratic traction)'}
        print('ACTUAL_QUADRATIC_COMPARISON='+json.dumps(row,ensure_ascii=False),flush=True)
        summary.append(row)
    obj={'status':'real_quadratic_comparison_not_production','rows':summary,'actual_solver':True,'not_convergence_certification':True,'not_identical_quadratic_consistent_face_load':True}
    (out/'quadratic_summary.json').write_text(json.dumps(obj,indent=2),encoding='utf8')
    return obj

if __name__=='__main__':run()
