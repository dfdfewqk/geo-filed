# -*- coding: utf-8 -*-
"""Research-only STEP -> face-graph corpus builder for a NEW bore classifier.

Consumes the already existing R12 generator's family-split manifest and the
owner-selected EXACT archived OCP STEP converter (kept private/off GitHub).
The same converter SHA must be pinned again at inference. Labels are generator
INTENT, never a prediction from BrepMFR/OCC or a claim of real-world accuracy.

Positive STEP: label only the unambiguously matched bore wall; other faces=-1.
No-hole STEP: label every face OTHER(0) for negative supervision.
This is a 3-label research bore model, NOT a 27-class epoch43 replacement.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path

CONVERTER_SHA256 = "6df10d368bc038a4cf66bea5184d8775082231a47b2248dfff6518915b56cb46"
CLASS_IDS = {"no_hole": 0, "through_hole": 1, "blind_hole": 2}
SPLITS = ("train", "val", "test")
SCHEMA = "geofield-brepmfr-v2-research-corpus-v1"


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def verify_rows(dataset_dir, manifest):
    """Fail closed on label authority, split/family or file provenance."""
    root=Path(dataset_dir).resolve()
    if manifest.get("schema")!="geofield_hole_research_dataset_v1" or not isinstance(manifest.get("rows"),list):
        raise ValueError("Expected the original generator-intent research manifest")
    fams=manifest.get("families")
    if not isinstance(fams,dict) or set(fams)!=set(SPLITS):
        raise ValueError("Missing train/val/test family splits")
    groups={key:set(fams[key]) for key in SPLITS}
    if any(not groups[k] for k in SPLITS):
        raise ValueError("Empty geometry family split")
    if any(groups[a]&groups[b] for i,a in enumerate(SPLITS) for b in SPLITS[i+1:]):
        raise ValueError("Geometry family leakage")
    seen_ids=set();seen_content=set();seen_geometry={}
    counter={split:Counter() for split in SPLITS}
    verified=[]
    for row in manifest["rows"]:
        if not isinstance(row,dict):
            raise ValueError("Invalid manifest row")
        sample_id=row.get("id")
        family=row.get("family");split=row.get("split");label=row.get("label")
        if (not isinstance(sample_id,str) or not sample_id or
            sample_id in seen_ids or not sample_id.replace("_","").isalnum()):
            raise ValueError("Duplicate or unsafe sample ID")
        seen_ids.add(sample_id)
        if split not in groups or family not in groups[split] or label not in CLASS_IDS:
            raise ValueError("Unrecognized split/family/class")
        if row.get("ground_truth")!="scripted_CAD_cut_intent" or row.get("source")!="synthetic_parametric_CAD_not_production":
            raise ValueError("Cannot accept ML/B-Rep-generated or unattributed labels")
        group=f"{family}/{row.get('geometry_id')}"
        if group in seen_geometry and seen_geometry[group]!=split:
            raise ValueError("Shared parametric geometry appears in multiple splits")
        seen_geometry[group]=split
        p=Path(str(row.get("step","")))
        if p.is_absolute() or any(x in ("..",".") for x in p.parts) or not p.parts or p.suffix.lower() not in (".step",".stp"):
            raise ValueError("Unsafe relative STEP path")
        path=(root/p).resolve()
        if not path.is_relative_to(root) or path.is_symlink() or not path.is_file():
            raise ValueError("Missing or unsafe STEP")
        if path.stat().st_size>64*1024*1024 or path.stat().st_size<20:
            raise ValueError("STEP size rejected")
        digest=sha256(path)
        if digest!=row.get("sha256") or digest in seen_content:
            raise ValueError("STEP digest mismatch or duplicate")
        seen_content.add(digest)
        params=row.get("parameters")
        if not isinstance(params,dict) or any(
            type(params.get(k)) not in (int,float) or not math.isfinite(params[k]) or params[k]<=0
            for k in ("w","h","t","radius")):
            raise ValueError("Missing or invalid parametric ground-truth dimensions")
        counter[split][label]+=1
        verified.append((row,path))
    if any(counter[s][k]==0 for s in SPLITS for k in CLASS_IDS):
        raise ValueError("Every split needs through, blind and no-hole examples")
    return verified,counter


def _load_converter(source):
    """Only one explicitly pinned local converter; never retrieve private code."""
    path=Path(source).absolute()
    if not path.is_file() or path.is_symlink() or sha256(path)!=CONVERTER_SHA256:
        raise ValueError("Archived converter SHA mismatch; refusing to import")
    spec=importlib.util.spec_from_file_location("_geofield_private_step_converter",path)
    if spec is None or spec.loader is None:
        raise ValueError("Invalid local converter")
    converter=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(converter)
    for name in ("read_step","get_faces","step_to_graph","compute_face_attributes"):
        if not callable(getattr(converter,name,None)):
            raise ValueError("Converter missing required function "+name)
    return converter


def match_graph_faces(converter, step_path, graph):
    """Prove the graph face row ordering from exact type/area/centroids.

    Distinct faces with same type & area are disambiguated by centroids.
    Matching the scalar normalization center/scale across ALL rows prevents
    trusting a coincidental cylinder face ordinal.
    """
    import numpy as np
    shape=converter.read_step(str(step_path))
    if shape is None:
        raise ValueError("Cannot re-read source STEP")
    faces=converter.get_faces(shape)
    fa=np.asarray(graph.get("face_attr"))
    if fa.ndim!=2 or fa.shape!=(len(faces),14) or not np.isfinite(fa).all():
        raise ValueError("Face attr dimensions or content invalid")
    raw=np.asarray([converter.compute_face_attributes(f) for f in faces])
    # IMPORTANT: this exact archived step_to_graph() rewrites the one-hot
    # fields BACK to the legacy scalar layout before returning its output:
    # [type, normalized_area, normalized_centroid_xyz, ...].
    if raw.shape!=fa.shape or np.any(raw[:,1]<=0) or np.any(fa[:,1]<=0):
        raise ValueError("Face area evidence absent")
    scale=np.sqrt(raw[:,1]/fa[:,1])
    reference=float(np.median(scale))
    if not np.isfinite(reference) or reference<=0 or not np.allclose(scale,reference,rtol=5e-4,atol=1e-5):
        raise ValueError("Face ordinal/area scale mismatch")
    for i in range(len(faces)):
        typ=int(raw[i,0])
        if typ<0 or typ>=6 or not np.isclose(fa[i,0],typ,atol=1e-5):
            raise ValueError("Graph face type/ordinal mismatch")
    origins=raw[:,2:5]-fa[:,2:5]*reference
    if not np.allclose(origins,origins[0],atol=max(1e-3,reference*1e-4)):
        raise ValueError("Graph centroid/face ordinal mismatch")
    return faces


def _one_target(converter,faces,row):
    """Identify a generator-created bore by unique axis line AND radius."""
    if row["label"]=="no_hole":
        return None
    import numpy as np
    expected_radius=float(row["parameters"]["radius"])
    x=float(row["parameters"]["w"])*.17
    y=-float(row["parameters"]["h"])*.09
    hits=[]
    for i,face in enumerate(faces):
        adapter=converter.BRepAdaptor_Surface(face)
        if adapter.GetType()!=converter.GeomAbs_Cylinder:
            continue
        cyl=adapter.Cylinder()
        rad=float(cyl.Radius())
        axis=cyl.Axis()
        direction=axis.Direction(); origin=axis.Location()
        if (abs(rad-expected_radius)<max(1e-4,expected_radius*1e-4) and
            abs(direction.Z())>.99999 and
            math.hypot(origin.X()-x,origin.Y()-y)<1e-3):
            hits.append(i)
    if len(hits)!=1:
        raise ValueError("Bore face/axis mapping not unique: "+row["id"])
    return hits[0]


def _validate_graph(graph,n):
    import numpy as np
    sizes={"face_attr":(n,14),"face_grid":(n,7,10,10)}
    for key,shape in sizes.items():
        array=np.asarray(graph.get(key))
        if array.shape!=shape or not np.isfinite(array).all():
            raise ValueError(key+" shape or finite gate")
    e=np.asarray(graph.get("edge_index"))
    m=e.shape[1] if e.ndim==2 and e.shape[0]==2 else -1
    if m<1 or e.dtype.kind not in "iu" or e.min()<0 or e.max()>=n:
        raise ValueError("Invalid graph face adjacency")
    for key,shape in (("edge_attr",(m,15)),("edge_grid",(m,12,10))):
        a=np.asarray(graph.get(key))
        if a.shape!=shape or not np.isfinite(a).all():
            raise ValueError(key+" shape or finite gate")


def prepare(dataset_dir, converter_path, output):
    """Generate versioned graph assets WITHOUT modifying installed GeoField."""
    import numpy as np
    root=Path(dataset_dir).resolve();dest=Path(output).absolute()
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError("Refusing to overwrite a populated research folder")
    if dest==root or root in dest.parents:
        raise ValueError("Never export inside the source STEP dataset")
    manifest_path=root/"manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("Manifest symlink rejected")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    entries,counts=verify_rows(root,manifest)
    converter=_load_converter(converter_path)
    # First validate all source inputs and graph target mappings; writes then
    # go exclusively into the new user-selected output directory.
    dest.mkdir(parents=True,exist_ok=True)
    (dest/"graphs").mkdir(exist_ok=True)
    records=[]
    for row,step in entries:
        graph=converter.step_to_graph(str(step))
        if not isinstance(graph,dict):
            raise ValueError("Failed to graph "+row["id"])
        faces=match_graph_faces(converter,step,graph)
        _validate_graph(graph,len(faces))
        face_index=_one_target(converter,faces,row)
        labels=np.full(len(faces),-1,dtype=np.int64)
        if row["label"]=="no_hole":
            labels[:]=CLASS_IDS["no_hole"]
        else:
            labels[face_index]=CLASS_IDS[row["label"]]
        name="graphs/"+row["id"]+".npz"
        target=dest/name
        np.savez_compressed(target,
            face_attr=np.asarray(graph["face_attr"],dtype=np.float32),
            face_grid=np.asarray(graph["face_grid"],dtype=np.float32),
            edge_attr=np.asarray(graph["edge_attr"],dtype=np.float32),
            edge_grid=np.asarray(graph["edge_grid"],dtype=np.float32),
            edge_index=np.asarray(graph["edge_index"],dtype=np.int64),
            target=labels)
        records.append({"id":row["id"],"family":row["family"],
            "geometry_id":row["geometry_id"],"split":row["split"],
            "intent":row["label"],"step_sha256":row["sha256"],
            "graph_path":name,"graph_sha256":sha256(target),
            "faces":len(faces),"supervised_faces":int(np.sum(labels>=0)),
            "target_face_ordinal_zero_based":face_index,
            "face_order_proof":"same_archived_converter_type_area_centroid_checked",
            "label_authority":"generator_intent_not_model_prediction"})
    result={"schema":SCHEMA,"model_kind":"NEW_BREP_GRAPH_BORE_RESEARCH_NOT_EPOCH43",
       "classes":{"0":"other_no_hole_geometry","1":"through_hole","2":"blind_hole"},
       "source_manifest_sha256":sha256(manifest_path),
       "converter_sha256":CONVERTER_SHA256,"converter_required_same_at_inference":True,
       "split_policy":"disjoint_geometry_families","families":manifest["families"],
       "rows":records,"counts":{s:dict(counts[s]) for s in SPLITS},
       "other_faces_on_positive_cad":"ignored_-1",
       "negative_other_supervision":"all_faces_on_generator_no_hole_CAD",
       "research_only":True,"eligible_for_production":False,
       "trained_model_accuracy":None,"original_epoch43_checkpoint_untouched":True,
       "limits":"Synthetic generator-intent labels, not independently labeled industrial STEP. 27-class labels not available."}
    (dest/"corpus.json").write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset",required=True,type=Path)
    p.add_argument("--converter",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args(argv)
    r=prepare(args.dataset,args.converter,args.out)
    print("RESEARCH ONLY:",len(r["rows"]),"graph cases, family-isolated train/val/test")
    print("Corpus:",args.out/"corpus.json")


if __name__=="__main__":
    main()
