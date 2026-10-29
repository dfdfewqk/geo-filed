"""BrepMFR local source review CLI: privacy, allowlist and immutable runtime.

Tests use synthetic temporary files only; no user model is loaded or run.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ml_runtime_source_review import collect, CKPT, FIXED_SOURCE, classify_archived_edge_source, classify_face_attribute_schema, classify_full_input_contract, EDGE_CONVERTER, LEGACY_NETWORK


class MLSourceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="geofield-ml-private-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"runtime"
        self.root.mkdir()
        self.output=Path(self.temp.name)/"local-review.zip"
        self.worker=self.root/FIXED_SOURCE[0]
        self.preprocessor=self.root/FIXED_SOURCE[1]
        self.worker.parent.mkdir(parents=True,exist_ok=True)
        self.preprocessor.parent.mkdir(parents=True,exist_ok=True)
        self.worker.write_text("def worker():\n    return 1\n",encoding="utf-8")
        self.preprocessor.write_text("def preprocess():\n    return 2\n",encoding="utf-8")

    def test_known_ml_python_only_and_checkpoint_hash_without_leak(self):
        included=self.root/"ml"/"brepmfr_core"/"ocp_step_to_graph.py"
        included.write_text("def graph(): return 3\n",encoding="utf-8")
        secrets={
            "ml/weights/best-epoch43-f1_0.8626.ckpt":b"PRIVATE CHECKPOINT BINARY",
            "ml/brepmfr_core/private_keys.env":b"EXPLICIT SECRET",
            "my_design.step":b"PRIVATE USER STEP",
            "history.sqlite":b"PRIVATE SQLITE",
            "run.frd":b"PRIVATE FEA",
            "ml/private.py":b"python-but-not-BrepMFR-core",
        }
        for name,raw in secrets.items():
            path=self.root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(raw)
        original={name:(self.root/name).read_bytes() for name in secrets}
        result=collect(self.root,self.output)
        self.assertTrue(result["can_review_worker_source"])
        self.assertEqual(len(result["source_hashes"]),3)
        self.assertEqual(result["checkpoint"]["status"],"unknown_checkpoint_hash")
        self.assertNotIn("PRIVATE CHECKPOINT",str(result))
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(set(archive.namelist()),
                {"review_manifest.json"}|
                {"source/"+name for name in result["source_hashes"]})
            combined=b"".join(archive.read(x) for x in archive.namelist())
            for secret in secrets.values():
                self.assertNotIn(secret,combined)
            report=json.loads(archive.read("review_manifest.json"))
            self.assertEqual(report,result)
            for name,digest in report["source_hashes"].items():
                self.assertEqual(hashlib.sha256(archive.read("source/"+name)).hexdigest(),digest)
        self.assertEqual({name:(self.root/name).read_bytes() for name in secrets},original)

    def test_read_only_edge_fingerprint_never_promotes_model_accuracy(self):
        # Different known old snapshots are only development provenance.
        fixed={
            "54d1db09193c133e02ae7060ca103b374620e3c10275a99f5626051b26b018e2":
                "archived_20261020_typed_edge_research_candidate",
            "6df10d368bc038a4cf66bea5184d8775082231a47b2248dfff6518915b56cb46":
                "archived_20261020_pre_fix_snapshot",
        }
        source=classify_archived_edge_source(b"unknown valid Python snapshot")
        self.assertEqual(source["state"],"unknown_local_source")
        self.assertFalse(source["verified_model_prediction"])
        self.assertEqual(classify_archived_edge_source(None)["state"],"missing_or_unsafe")
        self.assertFalse(classify_archived_edge_source(None)["verified_model_prediction"])
        self.assertNotEqual(fixed[next(iter(fixed))],source["state"])
        # Real local data isn't read or executed by the classifier itself.
        self.assertIn(EDGE_CONVERTER,"ml/brepmfr_core/ocp_step_to_graph.py")

    def test_archived_face_attribute_remap_is_flagged_without_execution(self):
        code = b"""def graph():
    face_attr_array[:,0] = face_attr_original[:,0]
    face_attr_array[:,1] = face_attr_array[:,9]
    face_attr_array[:,2:5] = face_attr_array[:,11:14]
    return face_attr_array
"""
        self.assertEqual(
            classify_face_attribute_schema(code)["state"],
            "archived_scalar_type_area_centroid_remap_detected")
        self.assertFalse(classify_face_attribute_schema(code)["verified_training_equivalence"])
        self.assertEqual(classify_face_attribute_schema(None)["state"],"missing_or_unsafe")
        self.assertEqual(classify_face_attribute_schema(b"def graph():return 1")["state"],
                         "other_unverified_source_layout")
        self.assertEqual(classify_face_attribute_schema(b"def broken(")["state"],
                         "unreadable_schema")
        p=self.root/EDGE_CONVERTER
        p.write_bytes(code)
        before=p.read_bytes()
        report=collect(self.root,self.output)
        self.assertEqual(report["face_attribute_schema_review"]["state"],
                         "archived_scalar_type_area_centroid_remap_detected")
        with zipfile.ZipFile(self.output) as z:
            self.assertEqual(json.loads(z.read("review_manifest.json")),
                             report)
        self.assertEqual(p.read_bytes(),before)


    def test_known_legacy_input_contract_mismatch_static_only(self):
        converter=b"""def normalize_geometry(face_grid,face_attr,edge_grid,edge_attr):
    new_face_attr[i,surf_type]=1.0
    new_face_attr[i,9]=area
    new_face_attr[i,11]=cx
    new_face_attr[i,12]=cy
    new_face_attr[i,13]=cz
    face_attr=new_face_attr
    return face_grid,face_attr,edge_grid,edge_attr

def step_to_preprocessed_sample(step):
    face_centroids=data["face_attr"][:,2:5]
    face_normals=data["face_attr"][:,7:10]
    return face_centroids
"""
        network=b"""class OldGraphNodeFeature:
    def forward(self,face_grid,face_attr):
        type_idx=face_attr[:,:,0]
        area=face_attr[:,:,1:2]
        centroid=face_attr[:,:,2:5]
        rational=face_attr[:,:,5]
        loop=face_attr[:,:,6:7]
        return centroid
"""
        report=classify_full_input_contract(converter,network)
        self.assertEqual(report["descriptor_source_state"],
                         "wrong_centroid_normal_offsets_after_onehot_conversion")
        self.assertEqual(report["reconstructed_model_stream_state"],
                         "reconstructed_scalar_streams_vs_converter_onehot_tensor")
        self.assertFalse(report["trained_model_equivalence"])
        self.assertFalse(report["real_step_accuracy_verified"])
        new_converter=converter.replace('[:,2:5]','[:,11:14]').replace(
            'face_normals=data["face_attr"][:,7:10]',
            'face_normals=face_grid[:,3:6,:,:].mean(axis=(2,3))')
        fixed=classify_full_input_contract(new_converter,network)
        self.assertEqual(fixed["descriptor_source_state"],
                         "aligned_descriptor_offsets_not_model_verified")
        self.assertFalse(fixed["trained_model_equivalence"])
        self.assertEqual(
            classify_full_input_contract(None,network)["descriptor_source_state"],
            "missing_converter")
        self.assertEqual(
            classify_full_input_contract(b"def broken(",network)["descriptor_source_state"],
            "invalid_converter_or_legacy_python")

        # Inspect local source bytes and private archive state without modifying
        # either and without copying a checkpoint or the experiment data.
        converter_path=self.root/EDGE_CONVERTER
        legacy_path=self.root/LEGACY_NETWORK
        converter_path.write_bytes(converter)
        legacy_path.write_bytes(network)
        existing={p:p.read_bytes() for p in (converter_path,legacy_path)}
        inventory=collect(self.root,self.output)
        self.assertEqual(inventory["full_input_contract_review"],report)
        self.assertEqual({p:p.read_bytes() for p in existing},existing)
        with zipfile.ZipFile(self.output) as z:
            self.assertNotIn("ml/weights",str(z.namelist()))
            self.assertEqual(json.loads(z.read("review_manifest.json")),
                             inventory)

    def test_unrecognized_local_edge_converter_reported_without_replacement(self):
        p=self.root/EDGE_CONVERTER
        p.write_text("def graph():return 3\n",encoding="utf8")
        original=p.read_bytes()
        state=collect(self.root,self.output)
        info=state["edge_converter_research_fingerprint"]
        self.assertEqual(info["state"],"unknown_local_source")
        self.assertFalse(info["verified_model_prediction"])
        self.assertEqual(state["face_attribute_schema_review"]["state"],
                         "other_unverified_source_layout")
        self.assertEqual(p.read_bytes(),original)

    def test_missing_compulsory_source_fails_closed_but_has_private_local_manifest(self):
        self.preprocessor.unlink()
        result=collect(self.root,self.output)
        self.assertFalse(result["can_review_worker_source"])
        self.assertEqual(result["rejected_or_missing"][FIXED_SOURCE[1]],"missing")
        self.assertTrue(self.output.is_file())

    def test_bad_source_not_executed_or_released(self):
        self.worker.write_bytes(b"import invalid syntax 123\n")
        result=collect(self.root,self.output)
        self.assertEqual(result["rejected_or_missing"][FIXED_SOURCE[0]],
                         "unreadable_or_invalid_python")
        self.assertNotIn(FIXED_SOURCE[0],result["source_hashes"])

    def test_refuse_symlink_outside_runtime(self):
        outside=Path(self.temp.name)/"outside.py"
        outside.write_bytes(b"SECRET PRIVATE SOURCE")
        self.worker.unlink()
        try:
            self.worker.symlink_to(outside)
        except (OSError,NotImplementedError):
            self.skipTest("Symlinks unavailable on current runner")
        result=collect(self.root,self.output)
        self.assertEqual(result["rejected_or_missing"][FIXED_SOURCE[0]],
                         "unsafe_path_or_symlink")
        with zipfile.ZipFile(self.output) as z:
            self.assertNotIn("SECRET PRIVATE SOURCE",
                             str(z.namelist()))

    def test_refuse_existing_output_or_output_inside_installed_runtime(self):
        with self.assertRaisesRegex(ValueError,"inside the installed runtime"):
            collect(self.root,self.root/"ml-review.zip")
        collect(self.root,self.output)
        with self.assertRaises(FileExistsError):
            collect(self.root,self.output)

    def test_oversized_core_is_not_archived(self):
        self.worker.write_bytes(b"#" * 2_000_001)
        result=collect(self.root,self.output)
        self.assertEqual(result["rejected_or_missing"][FIXED_SOURCE[0]],
                         "empty_or_oversized")

    def test_binary_or_weight_in_core_never_copied(self):
        path=self.root/"ml"/"brepmfr_core"/"hidden.ckpt"
        path.write_bytes(b"WEIGHTS NOT SOURCE")
        self.worker.write_bytes(b"\x00\x01\x02")
        report=collect(self.root,self.output)
        self.assertEqual(report["rejected_or_missing"][FIXED_SOURCE[0]],
                         "changed_or_non_source")
        with zipfile.ZipFile(self.output) as archive:
            self.assertNotIn("source/ml/brepmfr_core/hidden.ckpt",
                             archive.namelist())


if __name__=="__main__":
    unittest.main()
