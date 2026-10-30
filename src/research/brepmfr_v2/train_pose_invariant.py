# -*- coding: utf-8 -*-
"""Opt-in training of a NEW pose-robust, three-class synthetic CAD research model.

Never load old epoch43 or change the installed GeoField. Previous evaluated
families are development TRAIN only. New validation selects parameters; frozen
held-out test is evaluated exactly once. Repeated rotations are paired samples,
NOT new independent CAD parts. joblib model is a PRIVATE research artifact.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from invariant_features import face_features,supervised_matrix

CONVERTER_SHA256="6df10d368bc038a4cf66bea5184d8775082231a47b2248dfff6518915b56cb46"
CLASSES=("other","through_hole","blind_hole")
SCHEMA="geofield-v3-rigid-invariant-research-eval-v1"


def _sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def _read(path):
    p=Path(path)
    if not p.is_file() or p.is_symlink() or not 0<p.stat().st_size<=3_000_000:
        raise ValueError("Missing or oversized JSON research manifest")
    return json.loads(p.read_text(encoding="utf-8"))


def validate_manifests(previous, new):
    if (previous.get("schema")!="geofield-v2-2-generalization-v1" or
        new.get("schema")!="gf-v3-pose-invariant-v1" or
        previous.get("converter_sha256")!=CONVERTER_SHA256 or
        new.get("model_production_eligible") is not False or
        new.get("old_14_evaluated_families_as_train_only") is not True):
        raise ValueError("Unrecognized research manifest provenance")
    split=new.get("split")
    if not isinstance(split,dict) or set(split)!={"train","val","test"}:
        raise ValueError("Train/validation/test split missing")
    groups={k:set(v) for k,v in split.items()}
    if any(not groups[k] for k in groups) or any(
        groups[a]&groups[b] for a in groups for b in groups if a!=b):
        raise ValueError("New family leakage")
    known={r["family"] for r in previous["rows"]}
    if known&set.union(*groups.values()):
        raise ValueError("Previously evaluated CAD family reused as new holdout")
    names=set();files=set();pose_groups={}
    result={"train":[],"val":[],"test":[]}
    for row in previous["rows"]+new["rows"]:
        if not isinstance(row,dict) or row.get("label") not in (
            "no_hole","through_hole","blind_hole"):
            raise ValueError("Unsupported research class")
        is_new=row in new["rows"]
        s=row.get("split") if is_new else "train"
        if s not in result:
            raise ValueError("Unknown sample split")
        if is_new and row.get("family") not in groups[s]:
            raise ValueError("New CAD family split conflict")
        rid=row.get("id")
        if type(rid) is not str or not rid.replace("_","").isalnum() or rid in names:
            raise ValueError("Duplicate or unsafe row ID")
        names.add(rid)
        g=Path(row["graph_path"])
        if g.suffix!=".npz" or not g.is_file() or g.is_symlink() or not 0<g.stat().st_size<=30_000_000:
            raise ValueError("Missing, linked or oversized graph")
        if g.resolve() in files:
            raise ValueError("Graph copied between samples")
        files.add(g.resolve())
        pose=row.get("pose","original")
        if pose not in ("original","rot90shift"):
            raise ValueError("Unsupported pose marker")
        geom=(row["family"],row["geometry_id"],row["label"])
        if geom in pose_groups and pose_groups[geom]!=s:
            raise ValueError("Pose-copied CAD crosses data splits")
        pose_groups[geom]=s
        result[s].append(row)
    for s in result:
        if {r["label"] for r in result[s]}!={
            "no_hole","through_hole","blind_hole"}:
            raise ValueError("Incomplete split classes")
    # Every new held-out CAD must have its original AND its single rotated
    # clone in the same split; count this as one geometry, not two parts.
    for s in ("val","test"):
        paired={}
        for row in result[s]:
            key=(row["family"],row["geometry_id"],row["label"])
            paired.setdefault(key,set()).add(row.get("pose"))
        if any(v!={"original","rot90shift"} for v in paired.values()):
            raise ValueError("Missing pose pair or duplicate test identity")
    return result


def evaluate(model,entries):
    import numpy as np
    from sklearn.metrics import confusion_matrix,precision_recall_fscore_support
    truth=[];pred=[];fam={};poses={};bore=[]
    for row in entries:
        with np.load(row["graph_path"],allow_pickle=False) as graph:
            x=face_features(graph);y=np.asarray(graph["target"])
        if y.shape!=(len(x),) or y.dtype.kind not in "iu" or not np.isin(y,[-1,0,1,2]).all():
            raise ValueError("Malformed or fabricated model labels")
        p=model.predict(x);mask=y>=0
        truth.extend(y[mask].tolist());pred.extend(p[mask].tolist())
        if row["label"]!="no_hole":
            actual=y[mask].tolist();guess=p[mask].tolist()
            if len(actual)!=1 or actual[0]!=(1 if row["label"]=="through_hole" else 2):
                raise ValueError("No unique generator-labeled cylindrical wall")
            value=(int(actual[0]),int(guess[0]))
            fam.setdefault(row["family"],[]).append(value)
            poses.setdefault(row.get("pose","original"),[]).append(value)
            bore.append({"id":row["id"],"family":row["family"],
                         "geometry_id":row["geometry_id"],"pose":row.get("pose","original"),
                         "actual":value[0],"predicted":value[1]})
    labels=[0,1,2]
    cm=confusion_matrix(truth,pred,labels=labels)
    precision,recall,f1,support=precision_recall_fscore_support(
        truth,pred,labels=labels,zero_division=0)
    return {
        "confusion_matrix":cm.tolist(),
        "precision":[float(v) for v in precision],
        "recall":[float(v) for v in recall],
        "f1":[float(v) for v in f1],
        "hole_macro_f1":float((f1[1]+f1[2])/2),
        "per_family_bore_confusion":{
            k:confusion_matrix([a for a,b in v],[b for a,b in v],labels=[1,2]).tolist()
            for k,v in fam.items()},
        "per_pose_bore_confusion":{
            k:confusion_matrix([a for a,b in v],[b for a,b in v],labels=[1,2]).tolist()
            for k,v in poses.items()},
        "bore_records":bore,
        "other_support_is_supervised_faces_not_parts":True,
    }


def train(previous_manifest,new_manifest,output,seed=712029):
    from sklearn.ensemble import RandomForestClassifier
    import joblib
    prev=_read(previous_manifest);new=_read(new_manifest)
    grouped=validate_manifests(prev,new)
    root=Path(output)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Research output must be a fresh empty directory")
    train_x,train_y=supervised_matrix(grouped["train"])
    if set(train_y.tolist())!={0,1,2}:
        raise ValueError("Missing three supervised classes")
    candidates=((1,4),(2,6),(2,10))
    trials=[];best=None;score=(-1.,-999,-999)
    for leaf,depth in candidates:
        model=RandomForestClassifier(n_estimators=200,max_depth=depth,
            min_samples_leaf=leaf,class_weight="balanced_subsample",
            random_state=seed,n_jobs=2)
        model.fit(train_x,train_y)
        val=evaluate(model,grouped["val"])
        trial_score=(val["hole_macro_f1"],-depth,-leaf)
        trials.append({"leaf":leaf,"depth":depth,
                       "validation_hole_macro_f1":val["hole_macro_f1"]})
        if trial_score>score:
            score=trial_score;best=model;chosen=(leaf,depth,val)
    leaf,depth,val=chosen
    # No held-out test features, predictions or labels were used to choose
    # the architecture, seed, model or decision threshold.
    test=evaluate(best,grouped["test"])
    root.mkdir(parents=True,exist_ok=True)
    destination=root/"research_pose_invariant_rf_v3.joblib"
    joblib.dump(best,destination)
    report={"schema":SCHEMA,
        "model_kind":"pose_robust_engineered_graph_features_random_forest",
        "research_only":True,"eligible_for_production":False,
        "replace_epoch43":False,"FEA_or_AI_evidence_use_allowed":False,
        "new_model_sha256":_sha(destination),
        "converter_sha256":CONVERTER_SHA256,"seed":seed,
        "previous_development_families_used_only_in_train":True,
        "family_splits":new["split"],"selected":{ "min_samples_leaf":leaf,"max_depth":depth},
        "selection_trials":trials,"validation":val,"frozen_new_test":test,
        "test_evaluated_once_after_validation_selection":True,
        "held_out_test_used_for_tuning":False,
        "warning":"SYNTHETIC CAD ONLY. Rotated pairs are NOT independent parts; real CAD unknown. joblib is not safe to load from untrusted sources."}
    (root/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),
                                    encoding="utf-8")
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--previous-manifest",required=True,type=Path)
    p.add_argument("--new-manifest",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args(argv)
    report=train(args.previous_manifest,args.new_manifest,args.out)
    print(json.dumps({"selected":report["selected"],"validation_hole_f1":
        report["validation"]["hole_macro_f1"],"new_test_hole_f1":
        report["frozen_new_test"]["hole_macro_f1"],
        "eligible_for_production":False},indent=2))


if __name__=="__main__":
    main()
