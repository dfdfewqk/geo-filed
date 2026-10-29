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
from ml_runtime_source_review import collect, CKPT, FIXED_SOURCE


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
