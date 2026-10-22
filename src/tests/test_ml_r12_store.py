"""Filesystem regression for the R12 research archive (no fake real inference)."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "payload"))
import ml_r12_store as archive

CAD = "a" * 64
MODEL = "b" * 64
RUN = "c" * 32


def payload(sha=CAD):
    return {"cad_sha256": sha, "decision_usage": "blocked_diagnostic_only",
            "status": "research_not_for_production",
            "is_independent_r12_research": True, "geometry_certified": False,
            "fea_calculated": False, "candidate_count": 0, "predictions": []}


def validate(data, sha):
    if (data.get("cad_sha256") != sha or
            data.get("decision_usage") != "blocked_diagnostic_only" or
            data.get("status") != "research_not_for_production"):
        raise ValueError("invalid research provenance")


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = self.root / RUN
        self.folder.mkdir()
        self.output = self.folder / "r12_prediction.json"
        self.output.write_text(json.dumps(payload()), encoding="utf-8")

    def save(self):
        return archive.persist(self.folder, RUN, CAD, MODEL, payload(), validate)

    def restore(self, cad=CAD, model=MODEL):
        return archive.restore_latest(self.root, cad, model, validate)

    def test_verified_restore(self):
        record = self.save()
        restored = self.restore()
        self.assertEqual(restored["run_id"], RUN)
        self.assertEqual(restored["result"], payload())
        self.assertEqual(restored["model_version"], record["model_version"])
        self.assertEqual(record["result_sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())

    def test_changed_cad_or_checkpoint_rejected(self):
        self.save()
        self.assertIsNone(self.restore(cad="d" * 64))
        self.assertIsNone(self.restore(model="d" * 64))

    def test_changed_worker_file_rejected(self):
        self.save()
        self.output.write_text('{"cad_sha256": "altered"}', encoding="utf-8")
        self.assertIsNone(self.restore())

    def test_corrupted_metadata_rejected(self):
        self.save()
        (self.folder / "completed.json").write_text("{bad", encoding="utf-8")
        self.assertIsNone(self.restore())

    def test_tampered_checkpoint_metadata_rejected(self):
        self.save()
        target = self.folder / "completed.json"
        record = json.loads(target.read_text(encoding="utf-8"))
        record["model_sha256"] = "f" * 64
        target.write_text(json.dumps(record), encoding="utf-8")
        self.assertIsNone(self.restore())

    def test_partial_run_not_reused(self):
        self.assertIsNone(self.restore())

    def test_mismatched_worker_payload_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            archive.persist(self.folder, RUN, CAD, MODEL, payload("f"*64), validate)

    def test_does_not_overwrite_existing_archive(self):
        self.save()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.save()

    def test_corrupt_newer_run_does_not_hide_valid_archive(self):
        self.save()
        second_id = "d"*32
        folder = self.root / second_id
        folder.mkdir()
        output = folder / "r12_prediction.json"
        output.write_text(json.dumps(payload()), encoding="utf-8")
        archive.persist(folder, second_id, CAD, MODEL, payload(), validate)
        output.write_text("{}", encoding="utf-8")
        self.assertEqual(self.restore()["run_id"], RUN)

    def test_symlink_result_rejected(self):
        self.save()
        original = self.root / "original.json"
        original.write_bytes(self.output.read_bytes())
        self.output.unlink()
        try:
            self.output.symlink_to(original)
        except (OSError, NotImplementedError):
            self.skipTest("symlink not available")
        self.assertIsNone(self.restore())

    def test_unreadable_archive_directory_is_not_fatal(self):
        self.save()
        with mock.patch.object(archive.Path, "iterdir",
                               side_effect=PermissionError("access denied")):
            self.assertIsNone(self.restore())
        # A permissions error must not delete or modify existing data.
        self.assertEqual(self.restore()["run_id"], RUN)

    def test_missing_archive_root_allows_fresh_inference(self):
        other = self.root / "not-yet-created"
        self.assertIsNone(archive.restore_latest(other, CAD, MODEL, validate))

    def test_invalid_utf8_metadata_rejected(self):
        self.save()
        (self.folder / "completed.json").write_bytes(bytes((255,254)))
        self.assertIsNone(self.restore())

    def test_manifest_content_size_is_bounded_at_read(self):
        self.save()
        metadata = self.folder / "completed.json"
        metadata.write_bytes(b" " * (archive.MAX_METADATA_BYTES + 1))
        self.assertIsNone(self.restore())

    def test_oversized_result_rejected(self):
        self.save()
        with self.output.open("ab") as f:
            f.write(b" " * (archive.MAX_RESULT_BYTES + 1))
        self.assertIsNone(self.restore())


if __name__ == "__main__":
    unittest.main()
