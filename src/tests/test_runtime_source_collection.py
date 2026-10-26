"""Validate local-only source recovery against symlinks, missing files and data leakage."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime_preflight import EXISTING_REQUIRED
from runtime_source_collector import collect


class RuntimeSourceCollection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "runtime"
        self.root.mkdir()
        self.out = Path(self.tmp.name) / "review.zip"

    def test_complete_sources_only_no_user_artifacts(self):
        for name in EXISTING_REQUIRED:
            f = self.root.joinpath(*name.split("/"))
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("# tested module\\nA=1\\n", encoding="utf-8")
        (self.root / "my_secret.step").write_bytes(b"PERSONAL CAD MUST NOT LEAK")
        (self.root / "history.sqlite").write_bytes(b"PERSONAL DATA")
        (self.root / "ml" / "weights").mkdir(parents=True, exist_ok=True)
        (self.root / "ml" / "weights" / "model.ckpt").write_bytes(b"PRIVATE WEIGHTS")
        outcome = collect(self.root, self.out)
        self.assertTrue(outcome["complete"])
        self.assertEqual(outcome["recovered_source_modules"], len(EXISTING_REQUIRED))
        with zipfile.ZipFile(self.out) as z:
            names = z.namelist()
            self.assertEqual(set(names), {"source/" + n for n in EXISTING_REQUIRED} | {"review_manifest.json"})
            self.assertFalse(any(n.endswith((".step", ".sqlite", ".ckpt")) for n in names))
            manifest = json.loads(z.read("review_manifest.json"))
            self.assertEqual(manifest, outcome)
            for name, digest in manifest["sha256"].items():
                self.assertEqual(hashlib.sha256(z.read("source/" + name)).hexdigest(), digest)
        with self.assertRaises(FileExistsError):
            collect(self.root, self.out)

    def test_missing_source_is_not_a_complete_runtime(self):
        first = EXISTING_REQUIRED[0]
        (self.root / first).write_bytes(b"# only one module\\n")
        data = collect(self.root, self.out)
        self.assertFalse(data["complete"])
        self.assertEqual(data["recovered_source_modules"], 1)
        self.assertEqual(len(data["missing_or_rejected"]), len(EXISTING_REQUIRED) - 1)

    def test_output_inside_runtime_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "inside the installed runtime"):
            collect(self.root, self.root / "unsafe.zip")
        self.assertFalse((self.root / "unsafe.zip").exists())

    def test_broken_symlink_is_rejected_without_reading_target(self):
        target = Path(self.tmp.name) / "private.py"
        target.write_bytes(b"TOP SECRET")
        link = self.root / EXISTING_REQUIRED[0]
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("No symlink permission available")
        result = collect(self.root, self.out)
        self.assertEqual(result["missing_or_rejected"][EXISTING_REQUIRED[0]], "symlink_refused")
        with zipfile.ZipFile(self.out) as z:
            self.assertNotIn("source/" + EXISTING_REQUIRED[0], z.namelist())


if __name__ == "__main__":
    unittest.main()
