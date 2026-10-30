# -*- coding: utf-8 -*-
"""Read-only strict B07 research-readiness review, NEVER a production release gate.

The new synthetic holdout can be perfect yet fail rigid-pose or external CAD.
No checkpoint deserialization, imports of the private converter or ML inference.
All weights, CAD, FEA and user data remain unchanged.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

CONVERTER_SHA256 = "6df10d368bc038a4cf66bea5184d8775082231a47b2248dfff6518915b56cb46"
TRAIN_SCHEMA = "geofield-v2.2-cad-family-disjoint-research-result"
STRESS_SCHEMA = "geofield-v2.2-postfit-ood-probes-v1"
HOLES = ("through_hole", "blind_hole")


def _read_json(path):
    p=Path(path)
    if not p.is_file() or p.is_symlink() or not 0 < p.stat().st_size <= 2_000_000:
        raise ValueError("Absent, linked or oversized research evidence")
    return json.loads(p.read_text(encoding="utf-8"))


def _digest(path):
    p=Path(path)
    if not p.is_file() or p.is_symlink() or not 0 < p.stat().st_size <= 100_000_000:
        raise ValueError("Untrusted research model path")
    h=hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def _recall(hit,total):
    if (type(hit) is not int or type(total) is not int or
        total < 1 or hit < 0 or hit > total):
        raise ValueError("Malformed class support or correct count")
    return round(hit/total,6)


def review(training,stress,checkpoint_sha256):
    """Require raw held-out confusion AND separately frozen rigid-pose stress.

    Even perfect research data NEVER authorizes production or epoch43 replacement
    without independently labeled *real* CAD evidence and safety review.
    """
    if not isinstance(training,dict) or not isinstance(stress,dict):
        raise ValueError("Missing evidence objects")
    if training.get("schema")!=TRAIN_SCHEMA or stress.get("schema")!=STRESS_SCHEMA:
        raise ValueError("Unknown evidence schema")
    if (training.get("research_only") is not True or
        training.get("eligible_for_production") is not False or
        stress.get("production_eligible") is not False):
        raise ValueError("Cannot review unlabeled production-claimed data")
    if (type(checkpoint_sha256) is not str or len(checkpoint_sha256)!=64 or
        any(c not in "0123456789abcdef" for c in checkpoint_sha256) or
        training.get("new_model_checkpoint_sha256")!=checkpoint_sha256 or
        stress.get("checkpoint_sha256")!=checkpoint_sha256):
        raise ValueError("Stale or mismatched checkpoint SHA")
    if stress.get("source_exact_archived_converter_sha256")!=CONVERTER_SHA256:
        raise ValueError("Converter provenance mismatch")
    family_groups=[training.get(k) for k in
                   ("train_families","validation_families","frozen_holdout_families")]
    if any(not isinstance(x,(tuple,list)) or not x or
           any(type(y) is not str or not y for y in x) for x in family_groups):
        raise ValueError("Geometry-family splits absent")
    sets=[set(x) for x in family_groups]
    if any(sets[i]&sets[j] for i in range(3) for j in range(i+1,3)):
        raise ValueError("Previously evaluated families leak across splits")
    if (training.get("prior_test_reused_as_train") is not True or
        training.get("test_evaluated_once_after_epoch_selected") is not True):
        raise ValueError("Train and test history unverified")
    measured=training.get("test")
    cm=measured.get("confusion_matrix") if isinstance(measured,dict) else None
    if (not isinstance(cm,list) or len(cm)!=3 or
        any(not isinstance(row,list) or len(row)!=3 or
            any(type(v) is not int or v<0 for v in row) for row in cm)):
        raise ValueError("Three-class confusion matrix invalid")
    test_n={};test_r={}
    for i,name in ((1,"through_hole"),(2,"blind_hole")):
        n=sum(cm[i]);test_n[name]=n;test_r[name]=_recall(cm[i][i],n)
    cases=stress.get("transformed_fixed_holdout_cad")
    if not isinstance(cases,list) or not 0<len(cases)<=1000:
        raise ValueError("Rigid-pose stress missing")
    stress_n={k:0 for k in HOLES};stress_good={k:0 for k in HOLES}
    for row in cases:
        if not isinstance(row,dict) or row.get("expected") not in stress_n:
            raise ValueError("Missing generator-intent transform label")
        name=row["expected"];cylinders=row.get("cylinders")
        if not isinstance(cylinders,list) or len(cylinders)!=1:
            raise ValueError("Stress cylinder missing or ambiguous")
        pred=cylinders[0].get("prediction")
        if pred not in ("other",*HOLES) or row.get("correct_cylinders")!=int(pred==name):
            raise ValueError("Stress prediction/count mismatch")
        stress_n[name]+=1;stress_good[name]+=int(pred==name)
    stress_r={k:_recall(stress_good[k],stress_n[k]) for k in HOLES}
    failures=[]
    for key in HOLES:
        if test_n[key]<10:failures.append("insufficient_new_family_"+key)
        if test_r[key]<.9:failures.append("low_new_family_recall_"+key)
        if stress_n[key]<6:failures.append("insufficient_rigid_pose_"+key)
        if stress_r[key]<.9:failures.append("rotation_stress_fail_"+key)
    synthetic_gate_pass=not failures
    failures.append("independently_labeled_real_industrial_cad_missing")
    return {"schema":"geofield-brepmfr-v2-nonproduction-readiness-review-v1",
            "model_sha256":checkpoint_sha256,
            "fresh_synthetic_test_support":test_n,
            "synthetic_holdout_recall":test_r,
            "postfit_rigid_transform_support":stress_n,
            "postfit_rigid_transform_recall":stress_r,
            "synthetic_robustness_gate_passed":synthetic_gate_pass,
            "production_eligible":False,
            "eligible_to_replace_epoch43":False,
            "can_drive_fea_or_engineering_safety":False,
            "failed_gates":failures,
            "note":"Research-only; model/class scores are uncalibrated. No test tuning."}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--training-report",required=True,type=Path)
    p.add_argument("--stress-report",required=True,type=Path)
    p.add_argument("--checkpoint",required=True,type=Path)
    args=p.parse_args(argv)
    result=review(_read_json(args.training_report),
                  _read_json(args.stress_report),_digest(args.checkpoint))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
