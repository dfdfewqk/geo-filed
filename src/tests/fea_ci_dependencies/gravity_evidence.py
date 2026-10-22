"""GeoField R20.1: fail-closed, units-consistent, opt-in CalculiX gravity.

N, mm, s system: material density kg/m^3 -> tonne/mm^3 = rho * 1e-12.
CalculiX *DLOAD GRAV uses 9806.65 mm/s^2 in negative model Z.
"""
from __future__ import annotations
import math
from pathlib import Path

G_MM_S2 = 9806.65
G_M_S2 = 9.80665


def gravity_spec(case):
    info=(case or {}).get('self_weight_reference') or {}
    active=info.get('applied_to_solver',False)
    if type(active) is not bool:
        raise ValueError('Self weight setting must be a boolean')
    if not active:
        return None
    density=info.get('reference_density_kg_m3')
    if type(density) not in (int,float) or not math.isfinite(density) or not (100 <= density <= 30000):
        raise ValueError('Valid material density is required for self weight FEA')
    if (case.get('preset_metadata') or {}).get('density_kg_m3') != density:
        raise ValueError('Self weight density and chosen material preset disagree')
    if info.get('gravity_direction') != [0.0,0.0,-1.0] or info.get('gravity_mm_s2') != G_MM_S2:
        raise ValueError('Only standard -Z gravity in the model coordinates is supported')
    return {'density_kg_m3':float(density),'density_tonne_mm3':float(density)*1e-12,
            'gravity_mm_s2':G_MM_S2,'direction':(0.0,0.0,-1.0)}


def gravity_input_validation(inp,case):
    """Validate each actual deck against its signed case. No floating data spoofing.

    Independent of the original INP/FRD parser; this verifies the newly added
    deck directives, but does NOT certify solver convergence or output stresses.
    """
    expected=gravity_spec(case)
    p=Path(inp)
    if not p.is_file() or p.is_symlink() or not 0 < p.stat().st_size <= 300*1024*1024:
        raise ValueError('Actual CalculiX input deck is missing or invalid')
    lines=p.read_text(encoding='ascii',errors='strict').splitlines()
    blocks=[];header=None;data=[]
    for raw in lines:
        s=raw.strip()
        if not s or s.startswith('**'):continue
        if s.startswith('*'):
            if header is not None:blocks.append((header,data))
            header=s.upper().split(',')[0].strip();data=[]
        else:
            if header is None:raise ValueError('Malformed INP file')
            data.append(s)
    if header:blocks.append((header,data))
    names=[tag for tag,_data in blocks]
    # GeoField v1 emits a single isotropic material and a single static step.
    # Card ordering matters: keyword directives after END STEP do not act as loads.
    if names.count('*STEP') != 1 or names.count('*END STEP') != 1 or names[-1] != '*END STEP':
        raise ValueError('단일 CalculiX STEP 종료 순서가 잘못됐습니다.')
    start=names.index('*STEP'); end=names.index('*END STEP')
    if end <= start:
        raise ValueError('CalculiX STEP 범위가 잘못됐습니다.')
    density_positions=[i for i,tag in enumerate(names) if tag=='*DENSITY']
    load_positions=[i for i,tag in enumerate(names) if tag=='*DLOAD']
    if density_positions:
        material=[i for i,tag in enumerate(names) if tag=='*MATERIAL']
        section=[i for i,tag in enumerate(names) if tag=='*SOLID SECTION']
        if len(material)!=1 or len(section)!=1 or any(not(material[0]<i<section[0]<start) for i in density_positions):
            raise ValueError('밀도는 단일 재료 카드 안에 있어야 합니다.')
    if any(not (start < i < end) for i in load_positions):
        raise ValueError('중력 하중 카드가 해석 STEP 밖에 있습니다.')
    density=[data for tag,data in blocks if tag=='*DENSITY']
    grav=[]
    for tag,data in blocks:
        if tag=='*DLOAD':
            grav.extend(tuple(x.strip() for x in line.split(',')) for line in data)
    if expected is None:
        if density or grav:
            raise ValueError('Unsigned/unrequested gravity or material density was found in old FEA result')
        return {'applied':False}
    if len(density)!=1 or len(density[0])!=1 or len(grav)!=1:
        raise ValueError('Gravity FEA requires one material density and exactly one gravity load')
    try:
        rho=float(density[0][0].split(',')[0]);q=grav[0]
        if len(q)!=6 or q[0].upper()!='VOLUME' or q[1].upper()!='GRAV':raise ValueError
        acc,dx,dy,dz=map(float,q[2:])
    except (ValueError,OverflowError):
        raise ValueError('Gravity input card is malformed') from None
    nums=(rho,acc,dx,dy,dz)
    if any(not math.isfinite(n) for n in nums) or not math.isclose(rho,expected['density_tonne_mm3'],rel_tol=1e-9) or not math.isclose(acc,G_MM_S2,rel_tol=1e-9) or (dx,dy,dz)!=(0.0,0.0,-1.0):
        raise ValueError('Actual gravity and material density differ from signed FEA case')
    return {'applied':True,'material_density_kg_m3':expected['density_kg_m3'],
            'gravity_mm_s2':G_MM_S2,'direction':[0,0,-1]}
