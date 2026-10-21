# -*- coding: utf-8 -*-
"""Deterministic STEP-only B-Rep cylindrical-bore candidate features.

The labels are NEVER produced by this file. Geometry is never modified here.
Outputs ML *candidates*, not engineering facts. Multi-solid/non-solid fail closed.
"""
from __future__ import annotations
import math
from pathlib import Path
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
import numpy as np

FEATURE_NAMES=[
    'radius_relative', 'axial_length_relative', 'cylinder_area_relative',
    'rim_count', 'planar_rim_area_ratio_min', 'planar_rim_area_ratio_max',
    'planar_rim_axis_distance_min', 'planar_rim_axis_distance_max',
    'small_endcap_count', 'cylinder_aspect_ratio',
]


def _axis_distance(point,origin,direction):
    d=np.asarray(point,dtype=float)-np.asarray(origin,dtype=float)
    a=np.asarray(direction,dtype=float)
    return float(np.linalg.norm(d-np.dot(d,a)*a))


def cylinders_from_step(step_path):
    step_path=Path(step_path)
    if not step_path.is_file():raise FileNotFoundError(str(step_path))
    root=cq.importers.importStep(str(step_path));solids=root.solids().vals()
    if len(solids)!=1:raise ValueError('single closed STEP solid required')
    solid=solids[0]
    if not solid.isValid():raise ValueError('invalid STEP solid')
    faces=solid.Faces()
    b=solid.BoundingBox();diag=math.hypot(b.xlen,b.ylen,b.zlen)
    all_area=float(solid.Area())
    if diag<=1e-9 or all_area<=0:raise ValueError('degenerate solid')
    result=[]
    for fi,face in enumerate(faces):
        if face.geomType()!='CYLINDER':continue
        sur=BRepAdaptor_Surface(face.wrapped)
        if sur.GetType()!=GeomAbs_Cylinder:continue
        cy=sur.Cylinder();r=float(cy.Radius());a=cy.Axis().Direction()
        axis=(a.X(),a.Y(),a.Z());loc=cy.Location();origin=(loc.X(),loc.Y(),loc.Z())
        u0,u1,v0,v1=face.uvBounds()
        pt=sur.Value((u0+u1)*.5,(v0+v1)*.5)
        p=cq.Vector(pt.X(),pt.Y(),pt.Z());origin_vec=cq.Vector(*origin);av=cq.Vector(*axis)
        foot=origin_vec.add(av.multiply(p.sub(origin_vec).dot(av)))
        outward=face.normalAt(p);radial=p.sub(foot)
        sign=outward.dot(radial)/max(outward.Length*radial.Length,1e-12)
        # Inward cylindrical bore only, not exterior boss or outside edge round.
        if sign>=-0.35:continue
        rims=[e for e in face.Edges() if e.geomType()=='CIRCLE' and e.Length()>1e-8]
        neighbors=[]
        rim_neighbour_details=[]
        for rim in rims:
            adj=[]
            for j,other in enumerate(faces):
                if j==fi or other.geomType()!='PLANE':continue
                if any(rim.isSame(e) for e in other.Edges()):
                    area=float(other.Area());ratio=area/(math.pi*r*r)
                    cent_dist=_axis_distance(other.Center().toTuple(),origin,axis)/r
                    # A small planar disc exactly on the cylinder axis is an end-cap.
                    # Only geometrical evidence, never a certified topology label.
                    try:
                        norm=other.normalAt(other.Center())
                        parallel=abs(float(norm.dot(av)))
                    except Exception:
                        parallel=0.0
                    adj.append((ratio,cent_dist,j,parallel))
            if adj:
                chosen=min(adj,key=lambda x:x[0])
                neighbors.append(chosen)
                rim_neighbour_details.append({'ratio':float(chosen[0]),
                   'axis_distance_over_radius':float(chosen[1]),
                   'face_index':int(chosen[2]),'axis_normal_alignment':float(chosen[3])})
        ratios=[q[0] for q in neighbors];distances=[q[1] for q in neighbors]
        if len(rims)!=2 or len(neighbors)!=2:
            # Exclude unusual stepped/split/crossed bores rather than invent a label.
            continue
        proj_coords=[]
        rim_centres=[]
        for e in rims:
            c=e.Center().toTuple();rim_centres.append(list(c))
            proj_coords.append(sum((c[k]-origin[k])*axis[k] for k in range(3)))
        axial_span=abs(proj_coords[0]-proj_coords[1])
        if axial_span<1e-6:continue
        aspect=axial_span/max(r,1e-9)
        features=[r/diag,axial_span/diag,float(face.Area())/all_area,len(rims),
                  min(ratios),max(ratios),min(distances),max(distances),
                  sum(0.85<=q<=1.15 for q in ratios),aspect]
        if not all(math.isfinite(x) for x in features):raise ValueError('nonfinite feature')
        is_cap=lambda x: (0.98<=x['ratio']<=1.02 and
                          x['axis_distance_over_radius']<=0.03 and
                          x['axis_normal_alignment']>=0.98)
        caps=[is_cap(q) for q in rim_neighbour_details]
        # Fail closed for ambiguous caps, coincident rim planes or non-annular rims.
        different_plane_faces=len({q['face_index'] for q in rim_neighbour_details})==2
        if different_plane_faces and sum(caps)==1 and all(c or q['ratio']>1.20
                      for q,c in zip(rim_neighbour_details,caps)):
            evidence='blind_hole'
        elif different_plane_faces and not any(caps) and all(q['ratio']>1.20
                      for q in rim_neighbour_details):
            evidence='through_hole'
        else:
            evidence=None
        result.append({'face_index':fi,'radius_mm':r,'features':features,
                       'planar_rim_area_ratios':ratios,
                       'rim_neighbour_details':rim_neighbour_details,
                       'axis_origin':list(origin),'axis_direction':list(axis),
                       'rim_centers_xyz':rim_centres,
                       'topology_evidence':evidence,
                       'candidate_type':'inward_cylindrical_face'})
    return result
