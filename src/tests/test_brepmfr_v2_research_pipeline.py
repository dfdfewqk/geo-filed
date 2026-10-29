"""B07 BrepMFR-v2 research data-leakage, label and training readiness tests.

No private converter, STEP assets, original epoch43 weights, installed runtime,
external model or real solver are needed for these source/contract regressions.
"""
from __future__ import annotations
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
CODE=ROOT/"research"/"brepmfr_v2"
sys.path.insert(0,str(CODE))
import prepare_corpus as prep
import train_research as training

try:
    import numpy as np
except ImportError:
    np=None


class ResearchCorpusContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="geofield-new-bore-v2-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.dataset=self.root/"source";self.dataset.mkdir()
        (self.dataset/"steps").mkdir()
        families={"train":["plate"],"val":["raised_edge"],"test":["l_support"]}
        rows=[]
        for s,groups in families.items():
            for family in groups:
                for i,intent in enumerate(prep.CLASS_IDS):
                    sid=f"{s}_{family}_{i:02}_{intent}"
                    p=self.dataset/"steps"/(sid+".step")
                    p.write_bytes(("ISO-10303-21; "+sid*3).encode())
                    rows.append({"id":sid,"family":family,"split":s,
                                 "label":intent,"geometry_id":f"{family}_{i}",
                                 "ground_truth":"scripted_CAD_cut_intent",
                                 "source":"synthetic_parametric_CAD_not_production",
                                 "step":"steps/"+p.name,"sha256":prep.sha256(p),
                                 "parameters":{"w":50.,"h":30.,"t":8.,"radius":2.75}})
        self.m={"schema":"geofield_hole_research_dataset_v1",
                "families":families,"rows":rows}
        self.save_manifest()

    def save_manifest(self):
        (self.dataset/"manifest.json").write_text(
            json.dumps(self.m),encoding="utf-8")

    def test_honest_family_heldout_generator_rows(self):
        verified,counts=prep.verify_rows(self.dataset,self.m)
        self.assertEqual(len(verified),9)
        for split in prep.SPLITS:
            self.assertEqual(set(counts[split]),set(prep.CLASS_IDS))
            self.assertEqual(sum(counts[split].values()),3)

    def test_family_leakage_or_fake_labels_or_duplicate_digest_blocked(self):
        for func in (
            lambda m: m["families"]["test"].append("plate"),
            lambda m: m["rows"][0].update(ground_truth="predicted_by_brepmfr"),
            lambda m: m["rows"][0].update(split="test"),
            lambda m: m["rows"][1].update(sha256=m["rows"][0]["sha256"]),
            lambda m: m["rows"][1].update(step="../private.step"),
            lambda m: m["rows"][0].update(label="rectangular_pocket"),
            lambda m: m["rows"][0].update(parameters={"radius":float("nan")}),
        ):
            m=deepcopy(self.m);func(m)
            with self.subTest(case=str(m["rows"][0]["id"])):
                with self.assertRaises(ValueError):
                    prep.verify_rows(self.dataset,m)

    def test_modified_step_and_symlink_rejected(self):
        m=deepcopy(self.m);p=self.dataset/m["rows"][0]["step"]
        p.write_bytes(p.read_bytes()+b"tamper")
        with self.assertRaises(ValueError):
            prep.verify_rows(self.dataset,m)
        p.write_bytes(("ISO-10303-21; "+m["rows"][0]["id"]*3).encode())
        linked=self.dataset/"steps"/"linked.step"
        try:linked.symlink_to(p)
        except (OSError,NotImplementedError):return
        m["rows"][0]["step"]="steps/linked.step"
        with self.assertRaises(ValueError):
            prep.verify_rows(self.dataset,m)

    def test_research_output_cannot_overwrite_existing_dataset(self):
        with self.assertRaises(ValueError):
            prep.prepare(self.dataset,self.dataset/"converter.py",self.dataset/"out")

    @unittest.skipUnless(np is not None,"numpy optional in core CI")
    def test_graph_manifest_ingestion_and_tamper_detection(self):
        root=self.root/"research";(root/"graphs").mkdir(parents=True)
        rows=[]
        for r in self.m["rows"]:
            labels=np.array([0]*5 if r["label"]=="no_hole" else
                            [-1]*4+[prep.CLASS_IDS[r["label"]]],dtype=np.int64)
            graph=root/"graphs"/(r["id"]+".npz")
            np.savez_compressed(graph,
                face_attr=np.zeros((5,14),dtype=np.float32),
                face_grid=np.zeros((5,7,10,10),dtype=np.float32),
                edge_attr=np.zeros((4,15),dtype=np.float32),
                edge_grid=np.zeros((4,12,10),dtype=np.float32),
                edge_index=np.array([[0,1,2,3],[1,2,3,4]],dtype=np.int64),
                target=labels)
            rows.append({"id":r["id"],"family":r["family"],
                         "geometry_id":r["geometry_id"],"split":r["split"],
                         "intent":r["label"],"step_sha256":r["sha256"],
                         "graph_path":"graphs/"+graph.name,
                         "graph_sha256":prep.sha256(graph),
                         "faces":5,"supervised_faces":int((labels>=0).sum()),
                         "target_face_ordinal_zero_based":
                             None if r["label"]=="no_hole" else 4,
                         "label_authority":"generator_intent_not_model_prediction",
                         "face_order_proof":
                             "same_archived_converter_type_area_centroid_checked"})
        manifest={"schema":prep.SCHEMA,"converter_sha256":prep.CONVERTER_SHA256,
                  "families":self.m["families"],"split_policy":"disjoint_geometry_families",
                  "other_faces_on_positive_cad":"ignored_-1",
                  "research_only":True,"eligible_for_production":False,"rows":rows}
        (root/"corpus.json").write_text(json.dumps(manifest),encoding="utf8")
        _,ds=training.validate_corpus(root)
        self.assertEqual({k:len(v) for k,v in ds.items()},
                         {"train":3,"val":3,"test":3})
        target=root/rows[0]["graph_path"];target.write_bytes(target.read_bytes()+b"tamper")
        with self.assertRaises(ValueError):
            training.validate_corpus(root)

    def test_not_epoch43_and_not_in_signed_windows_release(self):
        source=(CODE/"train_research.py").read_text(encoding="utf8")
        self.assertIn("eligible_for_production\":False",source)
        self.assertIn("held_out_test_used_for_hyperparameter_search\":False",source)
        self.assertIn("no 27-class model",source)
        self.assertNotIn("model.load_state_dict(torch.load",source)
        release=(ROOT/"build_integration_candidate.py").read_text(encoding="utf8")
        self.assertNotIn("brepmfr_v2",release)


if __name__=="__main__":
    unittest.main()
