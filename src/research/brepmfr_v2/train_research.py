# -*- coding: utf-8 -*-
"""Train a NEW versioned 3-label graph-face research model, never epoch43.

All graph files are produced by prepare_corpus.py with one exact STEP converter.
Groups are split by geometric family BEFORE training. Test is evaluated ONCE
using the validation-selected checkpoint, not tuned by test. No use in FEA/AI.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

from prepare_corpus import CONVERTER_SHA256, SCHEMA, sha256, SPLITS


def validate_corpus(root):
    import numpy as np
    folder=Path(root).resolve()
    manifest_path=folder/"corpus.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Corpus manifest missing or linked")
    m=json.loads(manifest_path.read_text(encoding="utf-8"))
    if (m.get("schema")!=SCHEMA or m.get("converter_sha256")!=CONVERTER_SHA256 or
        m.get("research_only") is not True or m.get("eligible_for_production") is not False or
        m.get("split_policy")!="disjoint_geometry_families" or
        m.get("other_faces_on_positive_cad")!="ignored_-1"):
        raise ValueError("Unrecognized training corpus or unsafe provenance")
    families=m.get("families")
    if not isinstance(families,dict) or set(families)!=set(SPLITS):
        raise ValueError("Missing train/val/test families")
    groups={s:set(families[s]) for s in SPLITS}
    if any(groups[s]&groups[t] for i,s in enumerate(SPLITS) for t in SPLITS[i+1:]):
        raise ValueError("Family leakage")
    by_split={s:[] for s in SPLITS}
    ids=set();graph_shas=set();steps=set();geometries={}
    for row in m.get("rows",[]):
        if not isinstance(row,dict):raise ValueError("Malformed row")
        sid=row.get("id");s=row.get("split");family=row.get("family")
        if (not isinstance(sid,str) or not sid or sid in ids or
            not sid.replace("_","").isalnum() or s not in SPLITS or family not in groups[s]):
            raise ValueError("Duplicate sample/invalid family split")
        ids.add(sid)
        gid=(family,row.get("geometry_id"))
        if gid in geometries and geometries[gid]!=s:raise ValueError("Repeated geometry across splits")
        geometries[gid]=s
        if row.get("label_authority")!="generator_intent_not_model_prediction" or row.get(
            "face_order_proof")!="same_archived_converter_type_area_centroid_checked":
            raise ValueError("Missing grounded face-label authority")
        path=Path(str(row.get("graph_path","")))
        if (not path.parts or path.is_absolute() or ".." in path.parts or
            path.suffix!=".npz" or path.parts[0]!="graphs"):
            raise ValueError("Unsafe graph path")
        filename=(folder/path).resolve()
        if (not filename.is_relative_to(folder) or filename.is_symlink() or
            not filename.is_file() or filename.stat().st_size>40*1024*1024):
            raise ValueError("Unsafe graph file")
        if sha256(filename)!=row.get("graph_sha256") or row["graph_sha256"] in graph_shas:
            raise ValueError("Tampered or duplicate graph")
        graph_shas.add(row["graph_sha256"])
        if row.get("step_sha256") in steps or len(str(row.get("step_sha256","")))!=64:
            raise ValueError("Repeated original STEP content")
        steps.add(row["step_sha256"])
        with np.load(filename,allow_pickle=False) as graph:
            if set(graph.files)!={"face_attr","face_grid","edge_attr",
                                  "edge_grid","edge_index","target"}:
                raise ValueError("Graph field schema mismatch")
            fa=graph["face_attr"];fg=graph["face_grid"]
            ea=graph["edge_attr"];eg=graph["edge_grid"]
            ei=graph["edge_index"];target=graph["target"]
            n=len(fa);e=ei.shape[1] if ei.ndim==2 and ei.shape[0]==2 else -1
            if (n<1 or n>512 or e<1 or e>8192 or fa.shape!=(n,14) or
                fg.shape!=(n,7,10,10) or ea.shape!=(e,15) or
                eg.shape!=(e,12,10) or target.shape!=(n,) or
                ei.dtype.kind not in "iu" or target.dtype.kind not in "iu" or
                ei.min()<0 or ei.max()>=n or
                any(not np.isfinite(a).all() for a in (fa,fg,ea,eg)) or
                not np.isin(target,(-1,0,1,2)).all()):
                raise ValueError("Invalid graph shape, labels or nonfinite tensor")
            positives=np.where(target>0)[0].tolist()
            if row["intent"]=="no_hole":
                if positives or not np.all(target==0):
                    raise ValueError("No-hole negative face labels are not complete")
            else:
                expected={"through_hole":1,"blind_hole":2}.get(row.get("intent"))
                if expected is None or positives!=[row["target_face_ordinal_zero_based"]] or target[
                    positives[0]]!=expected or np.count_nonzero(target>=0)!=1:
                    raise ValueError("Positive STEP must label one confirmed bore face")
            if n!=row.get("faces") or int(np.count_nonzero(target>=0))!=row.get("supervised_faces"):
                raise ValueError("Face-count or supervised-count mismatch")
        by_split[s].append((row,filename))
    if any(not by_split[s] for s in SPLITS):
        raise ValueError("Empty supervised train/val/test")
    for s in SPLITS:
        if {row["intent"] for row,_ in by_split[s]}!={"through_hole","blind_hole","no_hole"}:
            raise ValueError("Every split must evaluate three classes")
    return m,by_split


def _features(graph,device):
    """Raw 14-d face attrs + 7x10x10 UV + edge and neighbor statistics."""
    import torch
    fa=torch.as_tensor(graph["face_attr"],dtype=torch.float32,device=device)
    fg=torch.as_tensor(graph["face_grid"],dtype=torch.float32,device=device)
    edges=torch.as_tensor(graph["edge_index"],dtype=torch.long,device=device)
    edge_attr=torch.as_tensor(graph["edge_attr"],dtype=torch.float32,device=device)
    n=fa.shape[0];src,dst=edges[0],edges[1]
    degrees=torch.zeros(n,1,device=device).index_add(0,dst,torch.ones(
        (len(dst),1),device=device))
    neighbors=torch.zeros_like(fa).index_add(0,dst,fa[src])/degrees.clamp(min=1)
    agg_edge=torch.zeros((n,15),device=device).index_add(0,dst,edge_attr)/degrees.clamp(min=1)
    y=torch.as_tensor(graph["target"],dtype=torch.long,device=device)
    return fa,fg,neighbors,agg_edge,y


def _model():
    import torch.nn as nn
    class NewBrepBoreNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.cnn=nn.Sequential(nn.Conv2d(7,16,3,padding=1),nn.ReLU(),
                                   nn.Conv2d(16,16,3,padding=1),nn.ReLU(),
                                   nn.AdaptiveAvgPool2d(1),nn.Flatten())
            self.head=nn.Sequential(nn.Linear(14+14+15+16,64),nn.ReLU(),
                                    nn.Linear(64,3))
        def forward(self,fa,fg,neigh,edge):
            import torch
            return self.head(torch.cat((fa,self.cnn(fg),neigh,edge),dim=-1))
    return NewBrepBoreNet()


def evaluate(model,entries,device):
    import torch
    from numpy import zeros
    cm=zeros((3,3),dtype=int)
    errors=[]
    model.eval()
    with torch.no_grad():
        for row,path in entries:
            import numpy as np
            with np.load(path,allow_pickle=False) as g:
                features=_features(g,device)
            truth=features[-1]
            scores=model(*features[:-1])
            # Count only explicitly supervised nodes; other face labels on a
            # positive geometry were deliberately left unknown (-1).
            mask=truth>=0
            pred=scores.argmax(-1)
            for actual,predicted in zip(truth[mask].tolist(),pred[mask].tolist()):
                cm[actual,predicted]+=1
            if (pred[mask]!=truth[mask]).any().item():
                errors.append(row["id"])
    per_class={}
    for c,name in enumerate(("other","through_hole","blind_hole")):
        tp=int(cm[c,c]);fn=int(cm[c].sum()-tp);fp=int(cm[:,c].sum()-tp)
        precision=tp/(tp+fp) if tp+fp else 0.
        recall=tp/(tp+fn) if tp+fn else 0.
        f1=2*precision*recall/(precision+recall) if precision+recall else 0.
        per_class[name]={"precision":precision,"recall":recall,"f1":f1,
                         "support":int(cm[c].sum())}
    return {"macro_f1":sum(x["f1"] for x in per_class.values())/3,
            "confusion_matrix":cm.tolist(),"classes":per_class,
            "wrong_sample_ids":errors}


def train(corpus,out,epochs=20,seed=20261029):
    import numpy as np
    import torch
    if not 1<=epochs<=200:raise ValueError("Experimental epoch budget out of bounds")
    m,splits=validate_corpus(corpus)
    output=Path(out).absolute()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Refusing to overwrite existing research model")
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    device=torch.device("cpu")
    net=_model().to(device)
    all_labels=[]
    for _,path in splits["train"]:
        with np.load(path,allow_pickle=False) as g:
            all_labels.extend(int(x) for x in g["target"] if x>=0)
    counts=Counter(all_labels)
    if set(counts)!={0,1,2}:raise ValueError("Missing face-level class training data")
    weight=torch.tensor([(max(counts.values())/counts[i])**.5 for i in range(3)],
                        dtype=torch.float32,device=device)
    optim=torch.optim.AdamW(net.parameters(),lr=0.001)
    chosen=None;best_score=-1;best_epoch=0;best_state=None
    for epoch in range(1,epochs+1):
        net.train()
        samples=list(splits["train"]);random.shuffle(samples)
        for _,path in samples:
            with np.load(path,allow_pickle=False) as g:
                fa,fg,neigh,edges,y=_features(g,device)
            logits=net(fa,fg,neigh,edges)
            active=y>=0
            if not torch.any(active):continue
            loss=torch.nn.functional.cross_entropy(logits[active],y[active],weight=weight)
            if not torch.isfinite(loss):raise ValueError("Nonfinite training loss")
            optim.zero_grad();loss.backward();optim.step()
        val=evaluate(net,splits["val"],device)
        if val["macro_f1"]>best_score:
            best_score=val["macro_f1"];best_epoch=epoch;chosen=val
            best_state={k:v.detach().cpu().clone() for k,v in net.state_dict().items()}
        if epoch-best_epoch>=8:break
    net.load_state_dict(best_state)
    test=evaluate(net,splits["test"],device) # evaluate exactly once after val choice
    output.mkdir(parents=True,exist_ok=True)
    state_file=output/"research_brep_bore_v2.pt"
    torch.save({"architecture":"new_brep_bore_v2_face_uv_edge_neighbor",
                "state_dict":best_state,"converter_sha256":CONVERTER_SHA256,
                "corpus_sha256":sha256(Path(corpus)/"corpus.json"),
                "classes":["other","through_hole","blind_hole"],
                "research_only":True,"eligible_for_production":False},state_file)
    report={"schema":"geofield-brepmfr-v2-training-eval-v1",
            "architecture":"new_brep_bore_v2_face_uv_edge_neighbor",
            "checkpoint_sha256":sha256(state_file),
            "corpus_sha256":sha256(Path(corpus)/"corpus.json"),
            "converter_sha256":CONVERTER_SHA256,
            "family_splits":m["families"],"seed":seed,"selected_epoch":best_epoch,
            "training_epochs_executed":epoch,
            "validation":chosen,"test_held_out":test,
            "held_out_test_used_for_hyperparameter_search":False,
            "model_kind":"new_research_binary_bore_plus_negative_not_epoch43",
            "research_only":True,"eligible_for_production":False,
            "caution":"Synthetic labels by construction; no 27-class model or real CAD accuracy claim",
            "FEA_or_geometry_decisions_allowed":False}
    (output/"report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),
                                      encoding="utf-8")
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--corpus",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--epochs",type=int,default=20)
    a=p.parse_args(argv)
    print(json.dumps(train(a.corpus,a.out,a.epochs),indent=2))

if __name__=="__main__":main()
