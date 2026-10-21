# -*- coding: utf-8 -*-
"""Reproducible, ground-truth-by-construction CAD dataset for hole-type ML research.

NOT connected to GeoField production predictions or finite element calculations.
For each labeled hole, label originates in generator intent, not model/B-Rep verification.
Split isolation is at geometry FAMILY level, not random STEP or face level.
"""
from __future__ import annotations
import argparse, hashlib, json, random
from pathlib import Path
import cadquery as cq

SEED=20261020
SPLIT_FAMILIES={
    'train': ('plate', 'rounded_plate', 'notched_plate'),
    'val': ('raised_edge',),
    'test': ('l_support', 'chamfer_plate'),
}
CLASSES=('no_hole','through_hole','blind_hole')


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def make_solid(family: str, w: float, h: float, t: float):
    base=cq.Workplane('XY').box(w,h,t)
    if family=='plate': return base
    if family=='rounded_plate': return base.edges('|Z').fillet(min(2.3,t*0.15))
    if family=='notched_plate':
        notch=cq.Workplane('XY').box(w*.17, h*.19, t+2).translate((-w*.48,h*.40,0))
        return base.cut(notch)
    if family=='raised_edge':
        rib=cq.Workplane('XY').box(w*.14,h*.52,t*.7).translate((-w*.41,0,t*.85))
        return base.union(rib)
    if family=='l_support':
        wall=cq.Workplane('XY').box(w*.16,h,t*2.0).translate((-w*.42,0,t*1.5))
        return base.union(wall)
    if family=='chamfer_plate':return base.edges('|Z').chamfer(min(1.2,t*.11))
    raise ValueError(family)


def create_case(family, label, params):
    w,h,t,r=params['w'],params['h'],params['t'],params['radius']
    solid=make_solid(family,w,h,t)
    if label!='no_hole':
        # Bore is away from the raised features for all families.
        hx=w*.17;hy=-h*.09
        depth=t+2 if label=='through_hole' else t*.58
        tool=cq.Solid.makeCylinder(r,depth,cq.Vector(hx,hy,t/2+1 if label=='through_hole' else t/2),cq.Vector(0,0,-1))
        solid=solid.cut(tool)
    shape=solid.val()
    if len(shape.Solids())!=1 or not shape.isValid():
        raise RuntimeError('invalid single-solid '+family+' '+label)
    return shape


def generate(output: Path, n_per_family_class: int=6):
    if n_per_family_class<2:raise ValueError('at least 2 per family/class')
    out=Path(output);step_dir=out/'steps';step_dir.mkdir(parents=True,exist_ok=True)
    rng=random.Random(SEED)
    rows=[]
    for split, families in SPLIT_FAMILIES.items():
        for family in families:
            for i in range(n_per_family_class):
                p={'w':round(rng.uniform(38,68),4),'h':round(rng.uniform(27,51),4),
                   't':round(rng.uniform(8.5,16.0),4),'radius':round(rng.uniform(2.1,3.9),4)}
                # Same base geometry across classes is *within the same split only*.
                for label in CLASSES:
                    stem=f'{split}_{family}_{i:02}_{label}'
                    path=step_dir/(stem+'.step')
                    shape=create_case(family,label,p)
                    cq.exporters.export(shape,str(path),exportType='STEP')
                    rows.append({'id':stem,'family':family,'split':split,'label':label,
                                 'geometry_id':f'{family}_{i:02}','parameters':p,
                                 'step':str(path.relative_to(out)),'sha256':sha256(path),
                                 'generator_version':'v1','ground_truth':'scripted_CAD_cut_intent',
                                 'source':'synthetic_parametric_CAD_not_production'})
    manifest={'schema':'geofield_hole_research_dataset_v1','seed':SEED,
              'unit':'mm','label_method':'generator_intent_not_model_prediction',
              'split_policy':'disjoint_geometry_families','families':SPLIT_FAMILIES,
              'n_per_family_class':n_per_family_class, 'rows':rows,
              'caution':'Synthetic CAD only. Not an engineering-certified hole classifier.'}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--n',type=int,default=6)
    args=ap.parse_args();m=generate(Path(args.out),args.n)
    print('generated',len(m['rows']),'STEP files; split counts:',{s:sum(x['split']==s for x in m['rows']) for s in SPLIT_FAMILIES})
