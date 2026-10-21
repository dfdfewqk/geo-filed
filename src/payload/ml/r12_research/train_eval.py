# -*- coding: utf-8 -*-
"""Train new research-only CAD bore-type classifier with family-isolated holdouts.

No labels from model predictions. Models never make structural safety claims.
No integration with legacy checkpoint / GeoField production/FEA permitted.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from collections import Counter
from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, balanced_accuracy_score
from .build_data import sha256
from .features import FEATURE_NAMES,cylinders_from_step


def load_examples(data_dir:Path):
    data_dir=Path(data_dir);m=json.loads((data_dir/'manifest.json').read_text(encoding='utf8'))
    if m.get('schema')!='geofield_hole_research_dataset_v1':raise ValueError('unknown dataset schema')
    ds={'train':[],'val':[],'test':[]}; parts={'train':[],'val':[],'test':[]}
    families={s:set() for s in ds}
    all_ids=set();all_sha=set()
    for row in m['rows']:
        if row['id'] in all_ids:raise ValueError('duplicate sample id')
        all_ids.add(row['id']);split=row['split'];family=row['family'];label=row['label']
        if split not in ds or family not in m['families'][split]:raise ValueError('split/family mismatch')
        if family in set(sum((list(v) for k,v in m['families'].items() if k!=split), [])):
            raise ValueError('cross-split family leakage')
        families[split].add(family)
        p=(data_dir/row['step']).resolve()
        if not p.is_relative_to(data_dir.resolve()):raise ValueError('path escapes dataset')
        if sha256(p)!=row['sha256']:raise ValueError('STEP SHA mismatch '+row['id'])
        if row['sha256'] in all_sha:raise ValueError('duplicate STEP content '+row['id'])
        all_sha.add(row['sha256'])
        faces=cylinders_from_step(p)
        if label=='no_hole' and faces:raise ValueError('unexpected bore candidates '+row['id'])
        if label!='no_hole' and len(faces)!=1:raise ValueError('expected one bore candidate '+row['id']+' got '+str(len(faces)))
        parts[split].append({'id':row['id'],'family':family,'actual':label,'candidate_count':len(faces)})
        for f in faces:
            ds[split].append({'id':row['id'],'family':family,'target':label,
                              'features':f['features'],'face_index':f['face_index'],
                              'topology_evidence':f.get('topology_evidence')})
    if any(families[a]&families[b] for a in ds for b in ds if a!=b):raise ValueError('family leakage')
    return m,ds,parts


def _decide_candidate(model, candidate, threshold: float):
    """Never call the ML score calibrated; topology is independent CAD evidence.

    The two signals must agree. A low-confidence model may be supported by
    explicit B-Rep bore-end topology, but an ML/topology conflict abstains.
    In all cases this is a research candidate, never a certified hole result.
    """
    probs=model.predict_proba([candidate['features']])[0]
    idx=int(np.argmax(probs));score=float(probs[idx])
    raw=str(model.classes_[idx])
    raw_thresholded=raw if score>=threshold else 'unverified'
    ev=candidate.get('topology_evidence')
    if ev and ev!=raw:
        final='unverified';basis='model_topology_conflict'
    elif ev and ev==raw:
        final=ev;basis='model_and_brep_topology_agree'
    else:
        # An isolated ML score cannot establish geometry of unfamiliar STEP.
        final='unverified';basis='insufficient_brep_evidence'
    return {'predicted_hole_type':final,'raw_ml_top_class':raw,
            'raw_ml_thresholded':raw_thresholded,
            'uncalibrated_model_score':score,'topology_evidence':ev,
            'decision_basis':basis,'status':'research_unverified'}


def _score_parts(model, examples, parts, threshold:float):
    by_id={e['id']:e for e in examples};ys=[];ps=[];assisted=[];records=[]
    for p in parts:
        actual=p['actual']
        if p['candidate_count']==0:
            pred='no_hole';assisted_pred='no_hole';score=None;basis='no_brep_candidate'
        else:
            example=by_id[p['id']]
            chosen=_decide_candidate(model,example,threshold)
            pred=chosen['raw_ml_thresholded'];assisted_pred=chosen['predicted_hole_type']
            score=chosen['uncalibrated_model_score'];basis=chosen['decision_basis']
        ys.append(actual);ps.append(pred);assisted.append(assisted_pred)
        records.append({**p,'predicted':pred,'topology_assisted_predicted':assisted_pred,
                        'decision_basis':basis,'score_uncalibrated':score,
                        'correct':actual==pred,'assisted_correct':actual==assisted_pred})
    classes=['no_hole','through_hole','blind_hole','unverified']
    return {'accuracy_including_abstentions':accuracy_score(ys,ps),
            'topology_assisted_accuracy_including_abstentions':accuracy_score(ys,assisted),
            'part_count':len(parts),'correct_count':sum(a==b for a,b in zip(ys,ps)),
            'topology_assisted_correct_count':sum(a==b for a,b in zip(ys,assisted)),
            'confusion_labels':classes,
            'confusion_matrix':confusion_matrix(ys,ps,labels=classes).tolist(),
            'topology_assisted_confusion_matrix':confusion_matrix(ys,assisted,labels=classes).tolist(),
            'prediction_records':records}


def run_train(data_dir: Path, out_dir:Path):
    m,ds,parts=load_examples(data_dir)
    X=np.asarray([e['features'] for e in ds['train']],dtype='float64')
    y=np.asarray([e['target'] for e in ds['train']])
    if len(set(y))!=2 or len(X)<12:raise ValueError('insufficient balanced training examples')
    model=RandomForestClassifier(n_estimators=128,max_depth=6,min_samples_leaf=2,
                                  random_state=20261020,class_weight='balanced',n_jobs=1)
    model.fit(X,y)
    if not set(model.classes_)=={'blind_hole','through_hole'}:raise AssertionError('missing class')
    # Choose threshold ON VALIDATION ONLY. Never optimize using test split.
    trial=[(.7+0.05*i) for i in range(6)]
    ranked=sorted([(float(_score_parts(model,ds['val'],parts['val'],t)['accuracy_including_abstentions']),t) for t in trial],key=lambda x:(-x[0],-x[1]))
    threshold=ranked[0][1]
    results={s:_score_parts(model,ds[s],parts[s],threshold) for s in ('train','val','test')}
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    filename=out/'research_model.joblib'
    joblib.dump(model,filename,compress=3)
    data_h=sha256(Path(data_dir)/'manifest.json')
    info={'schema':'geofield_research_ml_v1','model_kind':'RandomForestClassifier',
          'model_sha256':sha256(filename),'feature_names':FEATURE_NAMES,
          'feature_version':'step_brep_v1', 'dataset_manifest_sha256':data_h,
          'split_policy':'by_geometry_family','seed':20261020,
          'val_threshold_tuned_only_on_validation':threshold,'threshold_trials':trial,
          'families':m['families'],
          'part_counts':{s:len(parts[s]) for s in parts},
          'bore_candidate_counts':{s:len(ds[s]) for s in ds},
          'metrics':results,
          'model_use':'research_only', 'eligible_for_production':False,
          'claim':'synthetic geometries only; accuracy does not establish accuracy on independent real CAD',
          'model_score_is_calibrated_probability':False,
          'never_provides_FEA_or_strength_results':True,
          'legacy_checkpoint_untouched':True}
    (out/'report.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf8')
    print('TRAIN EVALUATION')
    for k,r in results.items():print(k,r['correct_count'],'/',r['part_count'],'accuracy',r['accuracy_including_abstentions'])
    print('threshold tuned on validation only',threshold)
    print('research_only; no production deploy')
    return info


def _coaxial_multisegment_faces(faces):
    """Recognize adjacent distinct-radius cylinders sharing the same hole axis.

    A stepped/counterbore/countersink assembly is outside the per-face labels.
    Be conservative rather than presenting individual face classifications as
    independent bores. Uses a CAD-length tolerance, not an ML prediction.
    """
    trouble=set()
    for i,left in enumerate(faces):
        for right in faces[i+1:]:
            r1,r2=left['radius_mm'],right['radius_mm']
            if abs(r1-r2)<1e-5:continue
            a=np.asarray(left['axis_direction'],dtype=float)
            b=np.asarray(right['axis_direction'],dtype=float)
            if abs(float(np.dot(a,b)))<0.99999:continue
            o1=np.asarray(left['axis_origin'],dtype=float)
            o2=np.asarray(right['axis_origin'],dtype=float)
            if np.linalg.norm(np.cross(o2-o1,a))>max(1e-4,min(r1,r2)*1e-4):continue
            left_ends=left['rim_centers_xyz'];right_ends=right['rim_centers_xyz']
            if any(np.linalg.norm(np.asarray(x)-np.asarray(y))<1e-3
                       for x in left_ends for y in right_ends):
                trouble.update((left['face_index'],right['face_index']))
    return trouble


EXPECTED_MODEL_SHA256='df51d702ee77fb9efdc2de730f679f62d18e652c9d6279736e4deef353535dd0'

def research_predict(step_path:Path, model_path:Path, report_path:Path):
    """Safe-by-default research prediction; NEVER issues verified hole results."""
    report=json.loads(Path(report_path).read_text(encoding='utf8'))
    if report.get('eligible_for_production') is not False or report.get('model_use')!='research_only':
        raise ValueError('unauthorized model manifest')
    if (sha256(model_path)!=EXPECTED_MODEL_SHA256 or
        report.get('model_sha256')!=EXPECTED_MODEL_SHA256):
        raise ValueError('model checksum mismatch')
    # joblib/pickle deserialization is only allowed for trusted locally produced files.
    model=joblib.load(model_path)
    faces=cylinders_from_step(step_path)
    res=[]
    complex_faces=_coaxial_multisegment_faces(faces)
    for f in faces:
        chosen=_decide_candidate(model,f,report['val_threshold_tuned_only_on_validation'])
        if f['face_index'] in complex_faces:
            chosen['predicted_hole_type']='unverified'
            chosen['decision_basis']='coaxial_multisegment_hole_unsupported'
        res.append({'face_index':f['face_index'],**chosen})
    return {'status':'research_not_for_production','candidate_count':len(faces),
            'predictions':res,'fea_calculated':False,'geometry_certified':False}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--data',required=True);ap.add_argument('--out',required=True)
    args=ap.parse_args();run_train(Path(args.data),Path(args.out))
