# -*- coding: utf-8 -*-
"""Pose-robust local face/adjacency features for a NEW research-only bore model.

Research inputs: exact 14/15-feature archived STEP converter graph NPZ.
No absolute centroid XYZ, signed global normals or face ordinal as features.
Geometry is centered and pairwise / normal dot products are rotation and
translation invariant in exact arithmetic. UV parameterization and topology
ordering are NOT guaranteed rigid-invariant in practical OCC STEP imports.
No B-Rep occupancy labels, FEA or model confidence claims.
"""
from __future__ import annotations


def face_features(graph):
    import numpy as np
    fa=np.asarray(graph["face_attr"],dtype=np.float64)
    fg=np.asarray(graph["face_grid"],dtype=np.float64)
    ei=np.asarray(graph["edge_index"])
    ea=np.asarray(graph["edge_attr"],dtype=np.float64)
    n=len(fa)
    if (n<1 or n>512 or fa.shape!=(n,14) or fg.shape!=(n,7,10,10) or
        ei.ndim!=2 or ei.shape[0]!=2 or ei.dtype.kind not in "iu" or
        ei.shape[1]<1 or ei.shape[1]>8192 or
        ea.shape!=(ei.shape[1],15) or ei.min()<0 or ei.max()>=n or
        not all(np.isfinite(x).all() for x in (fa,fg,ea))):
        raise ValueError("Invalid research graph or nonfinite attributes")
    centers=fa[:,2:5]
    normals=fg[:,3:6].mean(axis=(2,3))
    norms=normals/np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-7)
    result=[]
    mean_area=max(float(np.mean(fa[:,1])),1e-8)
    for i in range(n):
        xyz=np.moveaxis(fg[i,:3],0,-1)
        pts=xyz.reshape(-1,3)
        pts=pts-pts.mean(axis=0)
        eigs=np.maximum(np.linalg.eigvalsh(pts.T@pts/len(pts)),0.)
        nn=np.moveaxis(fg[i,3:6],0,-1).reshape(-1,3)
        normal_eigs=np.clip(np.linalg.eigvalsh(nn.T@nn/len(nn)),0.,10.)
        u=(xyz[-1,:,:]-xyz[0,:,:]).mean(axis=0)
        v=(xyz[:,-1,:]-xyz[:,0,:]).mean(axis=0)
        raw_norm=np.moveaxis(fg[i,3:6],0,-1)
        du=float(np.mean(np.linalg.norm(raw_norm[-1,:,:]-raw_norm[0,:,:],axis=1)))
        dv=float(np.mean(np.linalg.norm(raw_norm[:,-1,:]-raw_norm[:,0,:],axis=1)))
        axis=v if dv<=du else u
        axis=axis/max(float(np.linalg.norm(axis)),1e-8)
        indexes=np.where(ei[0]==i)[0]
        neighbors=ei[1,indexes]
        neighbors=neighbors[neighbors!=i]
        delta=centers[neighbors]-centers[i] if len(neighbors) else np.zeros((0,3))
        dist=np.linalg.norm(delta,axis=1)
        axial=np.abs(delta@axis)
        radial=np.sqrt(np.maximum(dist**2-axial**2,0.))
        plane=(fa[neighbors,0]==0) if len(neighbors) else np.array([])
        vector=[
            float(fa[i,0]),float(fa[i,1]),float(fa[i,1]/mean_area),
            *[float(x) for x in eigs],*[float(x) for x in normal_eigs],
            float(np.linalg.norm(u)),float(np.linalg.norm(v)),du,dv,
            float(len(neighbors)),float(len(set(neighbors.tolist()))),
            float(np.sum(plane)),
            float(np.mean(dist)) if len(dist) else 0.,
            float(np.max(dist)) if len(dist) else 0.,
            float(np.mean(axial)) if len(axial) else 0.,
            float(np.mean(radial)) if len(radial) else 0.,
            float(np.mean(np.abs(np.sum(norms[neighbors]*norms[i],axis=1))))
                if len(neighbors) else 0.,
            float(np.mean(np.abs(np.sum(norms[neighbors]*axis,axis=1))))
                if len(neighbors) else 0.,
            float(np.mean(fa[neighbors,1])) if len(neighbors) else 0.,
            float(np.mean(fa[neighbors,0]==0)) if len(neighbors) else 0.,
        ]
        if len(indexes):
            vector.extend(np.mean(ea[indexes],axis=0).tolist())
        else:
            vector.extend([0.]*15)
        result.append(vector)
    arr=np.asarray(result,dtype=np.float32)
    if arr.shape!=(n,39) or not np.isfinite(arr).all():
        raise ValueError("Unexpected invariant feature vector or nonfinite result")
    return arr


def supervised_matrix(entries):
    """Return only label-supervised graph rows, never assign missing labels."""
    import numpy as np
    x=[];y=[]
    for row in entries:
        path=row["graph_path"]
        with np.load(path,allow_pickle=False) as graph:
            features=face_features(graph)
            target=np.asarray(graph["target"])
        if target.shape!=(len(features),) or target.dtype.kind not in "iu" or not np.isin(target,[-1,0,1,2]).all():
            raise ValueError("Unverified research target array")
        mask=target>=0
        x.extend(features[mask])
        y.extend(target[mask])
    if not x:raise ValueError("No supervised faces")
    return np.asarray(x,dtype=np.float32),np.asarray(y,dtype=np.int64)
