# GeoField R20.1 opt-in physically applied gravity 2026-10-19
"""Optional real STEP -> Gmsh 3D tetra -> CalculiX CCX linear static FEA bridge.

Zero solver results are simulated. Gmsh and CCX are optional and must be
installed independently; importing this module requires only stdlib.

The original CAD is provided as a *temporary copy*, verified by SHA-256, then
handled in an isolated worker directory. CAD face IDs are never assumed to be
stable across STEP importers: conservative unique surface signatures must match.
"""
from __future__ import annotations
from gravity_evidence import gravity_spec, gravity_input_validation
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from engine_runtime import gmsh_python_status

MAX_TETS=600000
MAX_NODES=450000
MAX_SECONDS=180
EXP_RE=re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)[EeDd][-+]?\d+')

class FEAUnavailable(RuntimeError):
    pass


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):
            h.update(block)
    return h.hexdigest()


def detect_ccx(explicit=None):
    for value in (explicit,os.environ.get('CALCULIX_EXE'),shutil.which('ccx'),shutil.which('ccx.exe')):
        if value and Path(value).is_file():return str(Path(value).resolve())
    private_prefix=os.environ.get('GEOFIELD_ENGINE_PREFIX','').strip()
    if private_prefix:
        for name in ('Library/bin/ccx.exe','Scripts/ccx.exe','bin/ccx.exe'):
            candidate=Path(private_prefix)/name
            if candidate.is_file():return str(candidate.resolve())
    # Already installed FreeCAD or CalculiX distributions on Windows.
    # Scan only known locations; do not install or run a downloaded binary.
    if os.name=='nt':
        roots=[Path(os.environ.get('PROGRAMFILES','C:/Program Files')),
               Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)')),
               Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Programs']
        for base in roots:
            if not base.is_dir():continue
            for pat in ('FreeCAD*/bin/ccx.exe','FreeCAD*/bin/ccx_*exe',
                        'CalculiX*/ccx.exe','CalculiX*/bin/ccx.exe',
                        'bConverged*/CalculiX*/ccx.exe'):
                for candidate in base.glob(pat):
                    if candidate.is_file():return str(candidate.resolve())
    return None


def status(explicit=None):
    runtime=gmsh_python_status()
    has_gmsh=runtime['ok']
    ccx=detect_ccx(explicit)
    return {'implemented':True,'enabled':bool(has_gmsh and ccx),
            'gmsh_python_detected':has_gmsh,'calculix_executable_detected':bool(ccx),
            'gmsh_python_executable':runtime.get('python',runtime['path']),
            'gmsh_import_error':(str(runtime.get('modules',{}).get('gmsh') or runtime.get('error') or '') if not has_gmsh else ''),
            'gmsh_environment_source':runtime.get('selection','unknown'),
            'calculix_executable':ccx or '',
            'freecad_required_for_solver':False,
            'supported_case':'single valid solid, small-strain isotropic linear elasticity, 4-node tets',
            'note':('Gmsh Python API와 CalculiX를 탐지했습니다. 실제 실행 결과가 검증된 것은 아닙니다.' if has_gmsh and ccx else
                    '실제 계산에는 Gmsh Python 모듈 및 CalculiX ccx가 필요합니다. 설치/실행 자동 수행 안 함.')}


def source_face_signatures(analysis_model):
    sigs=(analysis_model.get('mesh') or {}).get('face_signatures')
    if not isinstance(sigs,list) or not sigs:
        raise ValueError('CAD 면의 중심·면적 원본 서명이 없습니다. 이 버전으로 STEP을 새로 불러오세요.')
    ids=set(analysis_model['mesh']['face_ids'])
    if set(t.get('face_id') for t in sigs)!=ids:
        raise ValueError('원본 CAD 면 서명과 뷰어 면 ID의 대응이 일치하지 않습니다.')
    for s in sigs:
        if (type(s.get('face_id')) is not int or
            not isinstance(s.get('center_mm'),list) or len(s['center_mm'])!=3 or
            any(type(c) not in (int,float) or not math.isfinite(c) for c in s['center_mm']) or
            not isinstance(s.get('area_mm2'),(int,float)) or
            not math.isfinite(s['area_mm2']) or s['area_mm2']<=0):
            raise ValueError('면 서명 값 오류')
    return sigs


def match_surfaces(signatures, actual_surfaces, required_face_ids):
    """Conservative, unique area+mass-center matching; never trust surface order.

    Skip if imported geometry splits/merges faces, changes scaling or mapping
    is ambiguous. No fuzzy fallback: wrong boundaries are worse than no FEA.
    """
    for surface in actual_surfaces:
        if (type(surface.get('tag')) is not int or surface['tag'] <= 0 or
            not isinstance(surface.get('area_mm2'),(int,float)) or
            not math.isfinite(surface['area_mm2']) or surface['area_mm2'] <= 0 or
            not isinstance(surface.get('center_mm'),(list,tuple)) or
            len(surface['center_mm']) != 3 or any(
                type(value) not in (int,float) or not math.isfinite(value)
                for value in surface['center_mm'])):
            raise ValueError('Gmsh 면 대응에 비정상 수치가 있습니다.')
    selected={s['face_id']:s for s in signatures if s['face_id'] in set(required_face_ids)}
    if set(selected)!=set(required_face_ids):
        raise ValueError('FEA 조건이 CAD에 없는 면을 참조합니다.')
    # Only match selected faces; do not require CAD importers to number identically.
    matches={};used=set()
    for face_id in sorted(selected):
        sig=selected[face_id]; good=[]
        for s in actual_surfaces:
            if s['tag'] in used:continue
            a,b=float(sig['area_mm2']),float(s['area_mm2'])
            if abs(a-b)>max(1e-3,1e-4*a):continue
            distance=math.dist(sig['center_mm'],s['center_mm'])
            if distance>max(2e-3,1e-4*math.sqrt(a)):continue
            good.append(s['tag'])
        if len(good)!=1:
            raise ValueError(f'CAD 면 ID {face_id}의 Gmsh 대응이 {len(good)}개입니다. 자동 경계조건 적용을 차단합니다.')
        matches[face_id]=good[0];used.add(good[0])
    return matches


def validate_volume_mesh(nodes, tets):
    """Reject non-finite, inverted, zero-volume and disconnected C3D4 connectivity.

    Preserves the original Gmsh node order; silently reversing it would mask
    an import/element-convention error in the CalculiX input.
    """
    if not nodes or not tets:
        raise ValueError('체적 메시가 비어 있습니다.')
    for tag, xyz in nodes.items():
        if type(tag) is not int or tag <= 0 or len(xyz) != 3 or any(
            type(v) not in (int,float) or not math.isfinite(v) for v in xyz
        ):
            raise ValueError('FEA 메시 노드 좌표/번호가 유효하지 않습니다.')
    used = set()
    element_ids = set()
    volume = 0.0
    for eid, tet in tets:
        if type(eid) is not int or eid <= 0 or eid in element_ids:
            raise ValueError('FEA 요소 번호 중복 또는 오류')
        element_ids.add(eid)
        if len(tet) != 4 or len(set(tet)) != 4 or any(n not in nodes for n in tet):
            raise ValueError('FEA 사면체 노드 연결 오류')
        p0,p1,p2,p3 = (nodes[n] for n in tet)
        a=[p1[i]-p0[i] for i in range(3)]
        b=[p2[i]-p0[i] for i in range(3)]
        c=[p3[i]-p0[i] for i in range(3)]
        v=(a[0]*(b[1]*c[2]-b[2]*c[1])
           -a[1]*(b[0]*c[2]-b[2]*c[0])
           +a[2]*(b[0]*c[1]-b[1]*c[0]))/6.0
        if not math.isfinite(v) or v <= 1e-12:
            raise ValueError(f'FEA 사면체 요소 {eid} 반전/퇴화 메시')
        volume += v
        used.update(tet)
    if used != set(nodes):
        raise ValueError('FEA 메시의 사용되지 않는 노드가 있습니다.')
    return {'tetrahedral_volume_mm3':volume,'verified_nodes':len(nodes),'verified_tets':len(tets)}


def triangle_area(p1,p2,p3):
    a=[p2[i]-p1[i] for i in range(3)];b=[p3[i]-p1[i] for i in range(3)]
    c=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    return 0.5*math.sqrt(sum(x*x for x in c))


def weighted_surface_force(nodes, triangles, force_n, vector, exclude_nodes=()):
    """Consistent total force spread by surface area, not per-node force/pressure."""
    if (type(force_n) not in (int,float) or not math.isfinite(force_n) or
        force_n <= 0 or len(vector) != 3 or any(
            type(component) not in (int,float) or not math.isfinite(component)
            for component in vector)):
        raise ValueError('FEA 총하중 또는 하중 방향이 유효하지 않습니다.')
    if not triangles:raise ValueError('하중 면에 삼각형 요소가 없습니다.')
    weights={}
    for tri in triangles:
        if len(tri)!=3 or any(i not in nodes for i in tri):raise ValueError('하중 면 노드 데이터 오류')
        area=triangle_area(*(nodes[i] for i in tri))
        if area<=1e-12:raise ValueError('비정상적 표면 삼각형')
        for n in tri:weights[n]=weights.get(n,0.0)+area/3.0
    # The edges of adjacent loaded/fixed surfaces share FE mesh nodes.
    # Applying load and Dirichlet constraints to the same node is contradictory.
    # Exclude fixed nodes and re-normalize the REMAINING surface shape weights.
    # This is an approximation of an equivalent applied resultant and should
    # be disclosed in FEA metadata, not confused with uniform pressure.
    for n in exclude_nodes:
        weights.pop(n,None)
    total=sum(weights.values())
    if total<=1e-9:raise ValueError('고정 노드 제외 후 하중 면에 남는 자유 노드가 없습니다.')
    loads={n:[force_n*w/total*d for d in vector] for n,w in weights.items()}
    for i in range(3):
        if abs(sum(f[i] for f in loads.values())-force_n*vector[i])>max(1e-7,force_n*1e-7):
            raise ValueError('총하중 분배 보존 실패')
    return loads,total


def audit_surface_load(nodes, triangles, loads, fixed_nodes, requested_force_n, direction):
    """Audit nodal applied loads against the exact original CAD load-surface area.

    No solver loads are altered here. An area/3 nodal distribution on the
    complete triangular surface preserves both total force and first moment;
    removing nodes shared with the fixture can displace its load centroid.
    This audit reports that physical approximation rather than concealing it.
    All positions are mm, forces N, and moments N*mm.
    """
    if not triangles or not loads or len(direction) != 3:
        raise ValueError('하중 검증에 필요한 삼각형, 힘 또는 방향 정보가 없습니다.')
    if (type(requested_force_n) not in (int,float) or
        not math.isfinite(requested_force_n) or requested_force_n <= 0 or
        any(type(v) not in (int,float) or not math.isfinite(v) for v in direction)):
        raise ValueError('하중 검증의 총힘 또는 방향 값이 유효하지 않습니다.')
    area_total=0.0
    moment_area=[0.0,0.0,0.0]
    all_nodes=set()
    seen_triangles=set()
    for tri in triangles:
        if len(tri)!=3 or len(set(tri))!=3 or any(n not in nodes for n in tri):
            raise ValueError('하중 검증에 사용할 메시 삼각형 데이터가 잘못됐습니다.')
        signature=tuple(sorted(tri))
        if signature in seen_triangles:
            raise ValueError('동일한 하중 메시 삼각형이 중복 입력됐습니다.')
        seen_triangles.add(signature)
        area=triangle_area(*(nodes[n] for n in tri))
        if not math.isfinite(area) or area<=1e-12:
            raise ValueError('하중 검증에서 퇴화된 삼각형을 발견했습니다.')
        area_total+=area
        for k in range(3):
            moment_area[k]+=area*sum(nodes[n][k] for n in tri)/3.0
        all_nodes.update(tri)
    centroid=[p/area_total for p in moment_area]
    desired=[requested_force_n*v for v in direction]
    applied=[sum(force[k] for force in loads.values()) for k in range(3)]
    if any(n not in nodes or n not in all_nodes or n in fixed_nodes or
           len(force)!=3 or any(not math.isfinite(v) for v in force)
           for n,force in loads.items()):
        raise ValueError('FEA 하중이 선택 면의 자유 노드 밖에 적용됐습니다.')
    tolerance=max(1e-7,requested_force_n*1e-7)
    difference=math.dist(desired,applied)
    if difference>tolerance:
        raise ValueError('면 하중의 총 벡터 합이 요청 하중과 일치하지 않습니다.')
    norm=sum(v*v for v in direction)
    if abs(norm-1.0)>1e-6:
        raise ValueError('하중 방향이 단위 벡터가 아닙니다.')
    # Project each actual nodal force back onto the common load direction.
    # Consistent surface weighting guarantees these projections are positive.
    projections={n:sum(force[k]*direction[k] for k in range(3))
                 for n,force in loads.items()}
    if any(p<=0 or any(abs(force[k]-p*direction[k])>tolerance for k in range(3))
           for n,p in projections.items() for force in (loads[n],)):
        raise ValueError('예상하지 않은 하중 방향 또는 음수 분배가 있습니다.')
    projected=sum(projections.values())
    if projected<=0:
        raise ValueError('하중 검증에 필요한 분배 노드가 없습니다.')
    actual_center=[sum(nodes[n][k]*w for n,w in projections.items())/projected
                   for k in range(3)]
    def cross(a,b):
        return [a[1]*b[2]-a[2]*b[1],
                a[2]*b[0]-a[0]*b[2],
                a[0]*b[1]-a[1]*b[0]]
    required_moment=cross(centroid,desired)
    actual_moment=[sum(cross(nodes[n],force)[k] for n,force in loads.items()) for k in range(3)]
    moment_error=math.dist(required_moment,actual_moment)
    # Local scale, not global coordinates, avoids origin-dependent thresholds.
    moment_tol=max(1e-6,requested_force_n*math.sqrt(area_total)*1e-8)
    excluded=all_nodes.intersection(fixed_nodes)
    return {'schema':'geofield-load-equilibrium-audit-v1',
            'source':'actual_gmsh_loaded_surface_and_inp_cload_weights',
            'units':{'force':'N','length':'mm','moment':'N_mm','pressure':'N_per_mm2'},
            'surface_triangle_count':len(triangles),
            'surface_node_count':len(all_nodes),
            'load_node_count':len(loads),
            'shared_fixed_load_nodes_excluded':len(excluded),
            'surface_area_mm2':area_total,
            'nominal_uniform_pressure_n_per_mm2':requested_force_n/area_total,
            'requested_resultant_n':desired,
            'applied_resultant_n':applied,
            'resultant_difference_n':difference,
            'surface_area_centroid_mm':centroid,
            'applied_force_centroid_mm':actual_center,
            'centroid_shift_mm':math.dist(centroid,actual_center),
            'nominal_moment_about_origin_n_mm':required_moment,
            'applied_moment_about_origin_n_mm':actual_moment,
            'moment_difference_n_mm':moment_error,
            'moment_equivalent_within_roundoff':moment_error<=moment_tol,
            'nominal_surface_pressure_exactly_preserved':not excluded,
            'status':('resultant_and_moment_verified' if moment_error<=moment_tol else
                      'resultant_verified_moment_shift_due_to_excluded_fixed_nodes'),
            'interpretation':('총힘은 보존되지만 공유 고정 절점 제외로 하중 작용 중심이 달라질 수 있습니다.'
                              if moment_error>moment_tol else
                              '표면 하중의 총힘과 모멘트가 면적 가중치 기준에 일치합니다.')}



def verify_written_inp_cload(path, nodes, intended_loads, fixed_nodes, audit):
    """Independently re-read serialized CLOAD cards before invoking the solver.

    This does not alter the deck or approximate a corrected load. It ensures
    the run metadata is grounded in forces actually written to CalculiX,
    including resultant, application centroid, and first moment (N*mm).
    """
    path=Path(path)
    if not path.is_file() or path.stat().st_size>96*1024*1024:
        raise ValueError('FEA INP 하중 원본 파일이 없거나 크기가 비정상입니다.')
    seen=set(); actual={}; section=''; load_sections=0
    with path.open(encoding='ascii') as source:
        for raw in source:
            line=raw.strip()
            if not line or line.startswith('**'):continue
            if line.startswith('*'):
                section=line.split(',')[0].strip().upper()
                if section=='*CLOAD':load_sections+=1
                continue
            if section!='*CLOAD':continue
            parts=[v.strip() for v in line.split(',')]
            if len(parts)!=3:raise ValueError('INP CLOAD 카드 필드 개수 오류')
            try:
                idx=int(parts[0]);axis=int(parts[1]);value=float(parts[2])
            except (ValueError,OverflowError) as exc:
                raise ValueError('INP CLOAD 카드 수치 형식 오류') from exc
            if (idx not in nodes or idx in fixed_nodes or axis not in (1,2,3) or
                not math.isfinite(value) or (idx,axis) in seen):
                raise ValueError('INP CLOAD 하중 노드·방향 중복 또는 비정상 값')
            seen.add((idx,axis))
            actual.setdefault(idx,[0.0,0.0,0.0])[axis-1]=value
    if load_sections!=1 or set(actual)!=set(intended_loads):
        raise ValueError('INP CLOAD 누락·중복 또는 노드 집합 불일치')
    for idx,want in intended_loads.items():
        if any(abs(actual[idx][k]-want[k])>max(1e-9,abs(want[k])*1e-8)
               for k in range(3)):
            raise ValueError('INP 저장 하중과 원래 면적 가중 분배가 다릅니다.')
    resultant=[math.fsum(v[k] for v in actual.values()) for k in range(3)]
    def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    moment=[math.fsum(cross(nodes[n],v)[k] for n,v in actual.items()) for k in range(3)]
    nominal=audit['requested_resultant_n']
    reference=audit['applied_moment_about_origin_n_mm']
    force_tol=max(1e-7,math.dist(nominal,[0,0,0])*1e-7)
    moment_scale=max(1.0, math.sqrt(audit['surface_area_mm2']))
    moment_tol=max(1e-5, force_tol*moment_scale)
    if math.dist(resultant,nominal)>force_tol or math.dist(moment,reference)>moment_tol:
        raise ValueError('INP 실제 합력/모멘트와 사전 하중 검증 정보가 불일치합니다.')
    unit=[x/math.dist(nominal,[0,0,0]) for x in nominal]
    projections={n:sum(v[i]*unit[i] for i in range(3)) for n,v in actual.items()}
    total=math.fsum(projections.values())
    if total<=0 or any(v<=0 for v in projections.values()):
        raise ValueError('INP 절점 하중 방향이 물리적 분배와 일치하지 않습니다.')
    centroid=[math.fsum(nodes[n][k]*v for n,v in projections.items())/total for k in range(3)]
    return {'written_inp_cload_verified':True,
            'inp_applied_node_count':len(actual),
            'inp_applied_resultant_n':resultant,
            'inp_applied_force_centroid_mm':centroid,
            'inp_applied_moment_n_mm':moment}

def gmsh_mesh(step_file, signatures, fixed_ids, loaded_ids, size_mm):
    try:import gmsh
    except ImportError as e:raise FEAUnavailable('Gmsh Python 모듈이 없습니다.') from e
    started=False
    try:
        gmsh.initialize(['-nopopup']);started=True
        gmsh.option.setNumber('General.Terminal',0)
        gmsh.model.add('geofield_step_analysis')
        imported=gmsh.model.occ.importShapes(str(step_file),highestDimOnly=False)
        gmsh.model.occ.synchronize()
        solids=gmsh.model.getEntities(3)
        if len(solids)!=1:
            raise ValueError(f'단일 솔리드만 해석 지원 (현재 {len(solids)}개).')
        surface_entities=gmsh.model.getEntities(2)
        gmsh_surfaces=[{'tag':tag,
                        'center_mm':list(gmsh.model.occ.getCenterOfMass(2,tag)),
                        'area_mm2':float(gmsh.model.occ.getMass(2,tag))}
                       for dim,tag in surface_entities]
        mapping=match_surfaces(signatures,gmsh_surfaces,set(fixed_ids)|set(loaded_ids))
        gmsh.option.setNumber('Mesh.CharacteristicLengthMin',size_mm)
        gmsh.option.setNumber('Mesh.CharacteristicLengthMax',size_mm)
        gmsh.option.setNumber('Mesh.ElementOrder',1)
        gmsh.model.mesh.generate(3)
        tags,coords,_=gmsh.model.mesh.getNodes()
        if not 4<=len(tags)<=MAX_NODES:
            raise ValueError('FEA 노드 수 초과 또는 비어 있음')
        nodes={int(n):[float(coords[i*3+j]) for j in range(3)] for i,n in enumerate(tags)}
        e_types,e_tags,e_nodes=gmsh.model.mesh.getElements(3)
        tets=[]
        for typ,ids,conn in zip(e_types,e_tags,e_nodes):
            if int(typ)!=4:raise ValueError(f'지원하지 않는 체적 요소 타입 {typ} (C3D4만 지원)')
            for i,eid in enumerate(ids):
                tet=[int(n) for n in conn[4*i:4*i+4]]
                if any(n not in nodes for n in tet):raise ValueError('체적 메시 노드 누락')
                tets.append((int(eid),tet))
        if not 1<=len(tets)<=MAX_TETS:raise ValueError('FEA 사면체 요소 수 초과 또는 비어 있음')
        validate_volume_mesh(nodes,tets)
        # For each mapped CAD surface gather all 3-node mesh triangles.
        surface_triangles={}
        for fid,tag in mapping.items():
            ty,et,conn=gmsh.model.mesh.getElements(2,tag)
            tris=[]
            for t,ids,ns in zip(ty,et,conn):
                if int(t)!=2:raise ValueError('지원되지 않는 표면 요소 타입')
                tris.extend([list(map(int,ns[3*i:3*i+3])) for i in range(len(ids))])
            if not tris:raise ValueError(f'CAD 면 {fid}에 2D 메시 요소 없음')
            surface_triangles[fid]=tris
        return nodes,tets,surface_triangles,mapping
    finally:
        if started:gmsh.finalize()


def write_inp(path,nodes,tets,fixed_nodes,loads,young,poisson,gravity=None):
    validate_volume_mesh(nodes,tets)
    if any(n not in nodes or len(force) != 3 or any(
        type(component) not in (int,float) or not math.isfinite(component)
        for component in force) for n,force in loads.items()):
        raise ValueError('FEA 하중 값 또는 노드 번호 오류')
    if any(n not in nodes for n in fixed_nodes):
        raise ValueError('FEA 고정 노드 번호 오류')
    if not fixed_nodes or not loads or set(fixed_nodes)&set(loads):
        # Note nodes at edges can belong to both surfaces; fixed/loaded sets
        # would then generate conflicting forces. Conservative rejection.
        raise ValueError('고정 면과 하중 면의 노드가 겹치거나 비어 있습니다. 다른 면을 선택하세요.')
    if not 0<young<1e7 or not -.999<poisson<.499:raise ValueError('탄성 재료 수치 오류')
    with Path(path).open('w',encoding='ascii') as f:
        f.write('*HEADING\nGeoField - verified STEP case (N, mm, MPa)\n*NODE\n')
        for n,pos in sorted(nodes.items()):f.write(f'{n}, {pos[0]:.10g}, {pos[1]:.10g}, {pos[2]:.10g}\n')
        f.write('*ELEMENT, TYPE=C3D4, ELSET=VOLUME\n')
        for eid,tet in tets:f.write(f'{eid}, '+', '.join(str(t) for t in tet)+'\n')
        f.write('*MATERIAL, NAME=ISOTROPIC\n*ELASTIC\n')
        f.write(f'{young:.10g}, {poisson:.10g}\n')
        if gravity is not None:
            f.write('*DENSITY\n')
            f.write(f'{gravity["density_tonne_mm3"]:.13g}\n')
        f.write('*SOLID SECTION, ELSET=VOLUME, MATERIAL=ISOTROPIC\n')
        f.write('*STEP\n*STATIC\n1., 1.\n*BOUNDARY\n')
        for n in sorted(fixed_nodes):f.write(f'{n}, 1, 3, 0.\n')
        f.write('*CLOAD\n')
        for n,forces in sorted(loads.items()):
            for ax,val in enumerate(forces,1):
                if abs(val)>1e-15:f.write(f'{n}, {ax}, {val:.13g}\n')
        if gravity is not None:
            f.write('*DLOAD\nVOLUME, GRAV, 9806.65, 0., 0., -1.\n')
        f.write('*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n')


def parse_frd_results(path, expected_nodes, include_fields=False):
    """Read ASCII CalculiX FRD U and S from the final complete increment.

    FRD numeric fields use adjacent E12.5 values (including negative values),
    and -2 records may continue the previous -1 record. A fresh result block
    replaces the same field from an earlier increment, never merging stale data.
    Binary FRD is deliberately unsupported. All mesh nodes must have results.
    """
    content = Path(path).read_bytes()
    if not content or b'\x00' in content:
        raise ValueError('FEA 결과가 비어 있거나 바이너리 FRD입니다.')
    if len(content) > 300*1024*1024:
        raise ValueError('FRD 결과 파일이 크기 제한을 초과했습니다.')
    lines = content.decode('ascii', errors='strict').splitlines()
    # Fully written CalculiX ASCII FRD must end at the official terminal record.
    # Small synthetic fragment fixtures used by older unit tests remain supported.
    if any(re.match(r'^1C(?:\s|$)', line.strip()) for line in lines[:15]):
        if not lines or lines[-1].strip() != '9999':
            raise ValueError('FRD 원본 종료 기록 9999 누락 또는 후행 손상')
    expected_nodes = set(expected_nodes)
    if not expected_nodes or any(type(n) is not int or n <= 0 for n in expected_nodes):
        raise ValueError('요구한 FEA 노드 목록이 올바르지 않습니다.')

    current = None
    labels = []
    # GeoField R20.1 FRD-authoritative result integrity
    result = {'DISP': {}, 'STRESS': {}}
    block_counts = {'DISP': 0, 'STRESS': 0}
    pending_node = None
    pending_values = []

    def values_from_line(line, prefix):
        """Parse adjacent scientific-notation values, with no whitespace needed."""
        rest = line[prefix:]
        vals = []
        offset = 0
        for match in EXP_RE.finditer(rest):
            if rest[offset:match.start()].strip():
                raise ValueError('FRD 수치 뒤 허용되지 않은 문자가 포함됐습니다.')
            number = float(match.group().replace('D','E').replace('d','E'))
            if not math.isfinite(number):
                raise ValueError('FRD 수치가 유한하지 않습니다.')
            vals.append(number)
            offset = match.end()
        if rest[offset:].strip() or not vals:
            raise ValueError('FRD 수치 행이 잘렸거나 손상됐습니다.')
        return vals

    def flush_record():
        nonlocal pending_node, pending_values
        if pending_node is None:
            return
        if len(pending_values) != len(labels):
            raise ValueError(f'FRD {current} 결과 성분 수 불일치: '
                             f'{len(pending_values)} / {len(labels)}')
        if pending_node in result[current]:
            raise ValueError(f'FRD {current} 중복 노드 번호 {pending_node}')
        result[current][pending_node] = dict(zip(labels, pending_values))
        pending_node = None
        pending_values = []

    for line in lines:
        s = line.strip()
        if s.startswith('-4'):
            if current is not None:
                raise ValueError('FRD 결과 블록 종료(-3) 누락: 새 블록 앞에서 발견')
            flush_record()
            words = s.split()
            current = words[1].upper() if len(words) > 1 else None
            labels = []
            if current in result:
                # Every -4 is a new field block: never reuse stale nodes from
                # an earlier step after a partly written later step.
                result[current] = {}
                block_counts[current] += 1
        elif s.startswith('-5') and current in result:
            fields = s.split()
            if len(fields) < 2:
                raise ValueError('FRD 성분 이름 누락')
            # CalculiX marks derived DISP ALL (length) as calculated:
            # it has a -5 descriptor but no corresponding -1 numeric value.
            if fields[1].upper() != 'ALL':
                labels.append(fields[1].upper())
        elif s.startswith('-1') and current in result:
            flush_record()
            match = re.match(r'^\s*-1\s+(\d+)', line)
            if not match:
                raise ValueError('FRD 노드 ID 파싱 실패')
            pending_node = int(match.group(1))
            if pending_node not in expected_nodes:
                raise ValueError(f'FRD {current}에서 알 수 없는 노드 {pending_node}')
            pending_values = values_from_line(line, match.end())
        elif s.startswith('-2') and current in result:
            if pending_node is None:
                raise ValueError('FRD -2 연속 행의 앞부분이 없습니다.')
            match = re.match(r'^\s*-2\s*', line)
            pending_values.extend(values_from_line(line, match.end()))
        elif s.startswith('-3'):
            flush_record()
            current = None
            labels = []
        elif s.startswith('100C') and current is not None:
            # A new increment cannot begin before the previous block's -3.
            raise ValueError('FRD 결과 증분이 이전 블록 종료(-3) 전에 시작했습니다.')

    if current is not None:
        raise ValueError('FRD 결과 마지막 블록 종료(-3) 누락: 불완전한 계산 파일')
    flush_record()
    if block_counts['DISP'] == 0 or block_counts['STRESS'] == 0:
        raise ValueError('FEA 변위 또는 응력 결과 블록 누락')
    if block_counts['DISP'] != block_counts['STRESS']:
        raise ValueError('FEA 변위와 응력의 결과 증분 수가 다릅니다.')
    u = result['DISP']
    stress = result['STRESS']
    if set(u) != expected_nodes or set(stress) != expected_nodes:
        raise ValueError('FEA 최종 증분의 변위/응력 노드가 전체 메시와 일치하지 않습니다.')

    disp = []
    mises = []
    for v in u.values():
        components = [v.get(k) for k in ('D1', 'D2', 'D3')]
        if any(x is None for x in components):
            raise ValueError('변위 X/Y/Z 누락')
        disp.append(math.sqrt(sum(x*x for x in components)))
    for v in stress.values():
        # CalculiX STRESS: SXX SYY SZZ SXY SYZ SZX, averaged at nodes.
        a, b, c, d, e, f = (v.get(k) for k in ('SXX','SYY','SZZ','SXY','SYZ','SZX'))
        if any(x is None for x in (a,b,c,d,e,f)):
            raise ValueError('응력 텐서 성분 누락')
        vm = math.sqrt(max(0., ((a-b)**2+(b-c)**2+(c-a)**2)/2 + 3*(d*d+e*e+f*f)))
        mises.append(vm)
    output={'maximum_displacement_mm':max(disp), 'maximum_nodal_von_mises_mpa':max(mises),
            'parsed_nodes':len(u), 'stress_interpretation':'extrapolated_nodal_stress_not_integration_point',
            'displacement_units':'mm', 'stress_units':'MPa'}
    if include_fields:
        # Store actual solver values. Never interpolate a global maximum into a fake field.
        output['nodal_displacements_mm']={node:[float(v[k]) for k in ('D1','D2','D3')]
                                           for node,v in u.items()}
        output['nodal_von_mises_mpa']={node:float(math.sqrt(max(0.,
            ((v['SXX']-v['SYY'])**2+(v['SYY']-v['SZZ'])**2+(v['SZZ']-v['SXX'])**2)/2+
            3*(v['SXY']**2+v['SYZ']**2+v['SZX']**2)))) for node,v in stress.items()}
    return output

def exterior_faces_from_tets(nodes,tets):
    """Return ONLY real exterior tetrahedron triangles with outward winding.

    Uses FEM tetrahedra rather than the CAD preview mesh, so field contours
    cannot accidentally refer to unrelated geometry or invented values.
    """
    counts={}
    for _,tet in tets:
        if len(tet)!=4 or len(set(tet))!=4 or any(n not in nodes for n in tet):
            raise ValueError('FEA 체적 요소의 노드가 올바르지 않습니다.')
        for opposite in range(4):
            face=[tet[j] for j in range(4) if j!=opposite]
            key=tuple(sorted(face))
            if key in counts:
                prev,num=counts[key]
                counts[key]=(prev,num+1)
            else:
                counts[key]=((face,tet[opposite]),1)
    surface=[]
    for key,(entry,count) in counts.items():
        if count==2:continue
        if count!=1:raise ValueError('FEA 체적 메시에 비다양체 면이 있습니다.')
        face,other=entry
        a,b,c=[nodes[n] for n in face]; d=nodes[other]
        u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        normal=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        if sum(normal[i]*(d[i]-a[i]) for i in range(3))>0:
            face=[face[0],face[2],face[1]]
        surface.append(face)
    if not surface:raise ValueError('FEA 표면을 생성할 수 없습니다.')
    return surface


def solver_surface_field(nodes,tets,values,case):
    """Create a viewable surface only from a successful, full nodal solve."""
    all_faces=exterior_faces_from_tets(nodes,tets)
    if len(all_faces)>180000:
        return None  # too large to safely send as an interactive browser field
    boundary=sorted({node for tri in all_faces for node in tri})
    displacement=values.get('nodal_displacements_mm') or {}
    stresses=values.get('nodal_von_mises_mpa') or {}
    if any(n not in displacement or n not in stresses for n in boundary):
        raise ValueError('FEA 표면에 필요한 실제 솔버 절점 결과가 누락됐습니다.')
    coords=[nodes[n] for n in boundary]
    disps=[displacement[n] for n in boundary]
    vm=[stresses[n] for n in boundary]
    if any(len(v)!=3 or any(not math.isfinite(float(x)) for x in v) for v in coords+disps):
        raise ValueError('FEA 좌표 또는 변위에 비정상 수치가 포함됐습니다.')
    if any(not math.isfinite(float(x)) or x<0 for x in vm):
        raise ValueError('FEA 응력에 비정상 수치가 포함됐습니다.')
    index={n:i for i,n in enumerate(boundary)}
    return {'schema':'geofield-fea-surface-field-v1','cad_sha256':case['cad_sha256'],
            'case_sha256':case['case_sha256'],'source':'actual_calculix_ascii_frd',
            'stress_interpretation':'extrapolated_nodal_stress_not_integration_point',
            'positions_mm':coords,'displacements_mm':disps,'von_mises_mpa':vm,
            'triangles':[[index[n] for n in face] for face in all_faces],
            'stress_units':'MPa','displacement_units':'mm',
            'visual_scale_factor':1.0}


def run_real_fea(step_file,case,analysis_model,workdir,ccx_exe=None):
    """Run a real solver or RAISE; no partially successful results are returned."""
    step_file=Path(step_file);workdir=Path(workdir);workdir.mkdir(parents=True,exist_ok=True)
    if sha256(step_file)!=case['cad_sha256'] or analysis_model['sha256']!=case['cad_sha256']:
        raise ValueError('STEP 원본과 분석/해석 조건의 SHA-256이 다릅니다.')
    if case.get('schema')!='geofield-fea-case-v1' or case.get('status')!='configuration_prepared_solver_not_connected':
        raise ValueError('검증되지 않은 FEA 설정입니다.')
    if not detect_ccx(ccx_exe):raise FEAUnavailable('CalculiX(ccx) 실행 파일을 찾지 못했습니다.')
    source_face_signatures(analysis_model)
    bc=case['boundary_conditions'];mat=case['material']
    fixed=bc['fixed_face_ids'];loaded=bc['load_face_ids']
    nodes,tets,surfaces,mapping=gmsh_mesh(step_file,source_face_signatures(analysis_model),fixed,loaded,
                                           case['mesh_request']['target_element_size_mm'])
    fixed_nodes={n for fid in fixed for tri in surfaces[fid] for n in tri}
    load_tris=[tri for fid in loaded for tri in surfaces[fid]]
    loads,area=weighted_surface_force(nodes,load_tris,bc['total_force_n'],bc['force_direction_unit'],fixed_nodes)
    load_audit=audit_surface_load(nodes,load_tris,loads,fixed_nodes,bc['total_force_n'],bc['force_direction_unit'])
    gravity=gravity_spec(case)
    mesh_volume=validate_volume_mesh(nodes,tets)['tetrahedral_volume_mm3'] if gravity else None

    target=workdir/'geofield_case'
    write_inp(target.with_suffix('.inp'),nodes,tets,fixed_nodes,loads,
              mat['young_modulus_mpa'],mat['poisson_ratio'],gravity=gravity)
    gravity_input_validation(target.with_suffix('.inp'),case)
    load_audit.update(verify_written_inp_cload(target.with_suffix('.inp'),nodes,loads,fixed_nodes,load_audit))
    exe=detect_ccx(ccx_exe)
    try:
        proc=subprocess.run([exe,'-i',target.name],cwd=str(workdir),capture_output=True,
                            timeout=MAX_SECONDS,check=False)
    except subprocess.TimeoutExpired as e:raise TimeoutError('FEA 솔버 실행이 제한 시간(180초)을 초과했습니다.') from e
    (workdir/'ccx_execution.log').write_text(
        'exit_code: '+str(proc.returncode)+'\nSTDOUT:\n'+proc.stdout.decode('utf-8','replace')[-30000:]+
        '\nSTDERR:\n'+proc.stderr.decode('utf-8','replace')[-15000:],encoding='utf-8')
    if proc.returncode!=0:raise RuntimeError(f'CalculiX 종료 코드 {proc.returncode}. ccx_execution.log 확인 필요')
    sta=target.with_suffix('.sta')
    if not sta.is_file() or not sta.stat().st_size:
        raise RuntimeError('CalculiX 상태(.sta)가 없거나 비어 있습니다.')
    sta_text=sta.read_text(errors='replace').upper()
    # Some official CCX builds write a completed STEP/INC job summary but do
    # not print the exact success sentence used by other builds.
    # The summary alone is NOT solver validation: exit 0 and a fully parsed
    # displacement/stress FRD from this workdir are additionally mandatory.
    if not ('THE ANALYSIS HAS COMPLETED SUCCESSFULLY' in sta_text or
            'SUMMARY OF JOB INFORMATION' in sta_text):
        raise RuntimeError('CalculiX 상태(.sta)에 완료 요약이 없습니다. 계산 상태를 확인하세요.')
    if re.search(r'(?m)^\s*(?:\*+\s*)?(?:FATAL|ERROR)\b',sta_text):
        raise RuntimeError('CalculiX 상태(.sta)에 오류가 기록됐습니다.')
    frd=target.with_suffix('.frd')
    if not frd.is_file() or not frd.stat().st_size:
        raise RuntimeError('CalculiX 결과(.frd)가 없거나 비어 있습니다. .sta 요약만으로 계산 성공 판정 불가')
    values=parse_frd_results(frd,set(nodes),include_fields=True)
    if values['maximum_displacement_mm']<=0 or values['maximum_nodal_von_mises_mpa']<=0:
        raise RuntimeError('유효한 응력 또는 변위가 없습니다. 모델과 경계조건을 확인하세요.')
    field=solver_surface_field(nodes,tets,values,case)
    # A field is written only after the actual solver has succeeded and all
    # nodal data has passed validation. The full node field is not part of the
    # light-weight polling/status response.
    if field:
        field_file=workdir/'geofield_fea_surface_field.json'
        field_file.write_text(json.dumps(field,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf-8')
    values={k:v for k,v in values.items() if not k.startswith('nodal_')}
    result={'schema':'geofield-fea-result-v1','status':'solver_executed_result_parsed',
            'validated_engineering_design':False,
            'cad_sha256':case['cad_sha256'],'case_sha256':case['case_sha256'],
            'solver':'CalculiX ccx','mesher':'Gmsh Python API/OpenCASCADE',
            'mesh':{'node_count':len(nodes),'tetrahedron_count':len(tets),
                    'fixed_nodes':len(fixed_nodes),'loaded_nodes':len(loads),
                    'load_surface_free_node_weight_mm2':area,
                    'shared_fixed_load_nodes_excluded':bool(load_audit['shared_fixed_load_nodes_excluded'])},
            'self_weight_applied':bool(gravity),
            'self_weight_evidence':({'density_kg_m3':gravity['density_kg_m3'],'acceleration_mm_s2':9806.65,
                'mesh_volume_mm3':mesh_volume,
                'mesh_based_self_weight_n':(mesh_volume*gravity['density_kg_m3']*1e-9*9.80665)} if gravity else None),
            'load_equilibrium_audit':load_audit,
            'boundary_face_mapping':mapping,
            'results':values,
            'field_visualization':{'available':bool(field),
                                   'surface_triangles':len(field['triangles']) if field else 0,
                                   'node_count':len(field['positions_mm']) if field else 0,
                                   'artifact':'geofield_fea_surface_field.json' if field else '',
                                   'reason':'' if field else '큰 메시로 브라우저 3D 필드 표시 제한'},
            'warnings':['응력은 절점 외삽 결과이며 응력 특이점/메시 수렴은 검증하지 않았습니다.',
                        'C3D4 1차 사면체만 사용했습니다. 설계 안전 승인에 사용하지 마세요.',
                        '고정 면과 하중 면이 모서리를 공유하면 고정 노드를 하중 분배에서 제외해 결과력을 보존합니다. 이는 근사 하중 분배입니다.'] +
                       (['공유 고정 절점 제외로 하중의 작용 중심과 모멘트가 바뀌었습니다. load_equilibrium_audit를 확인하세요.']
                         if not load_audit['moment_equivalent_within_roundoff'] else []),
            'artifacts':{'ccx_log':'ccx_execution.log','input_deck':'geofield_case.inp'}}
    return result

# GeoField R17.9 coordinated FEA environment and verified restoration
