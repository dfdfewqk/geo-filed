"""No-loss cleanup regression for obsolete GeoField QA release notes.

This checks each archived source file by its exact Git blob SHA-1, without
requiring git, installed Windows runtime, network, solver, SQLite or ML models.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT.parent / "docs" / "GeoField_LEGACY_QA_NOTES_ARCHIVE_20261105.md"
OLD = (
    *(f"QA{i}_검증안내.txt" for i in range(3, 12)),
    "FINAL_검증안내.txt",
    "FINAL_통합테스트_체크리스트.txt",
    "PORT8600_수정사항.txt",
)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\\x00" + data).hexdigest()


class LegacySourceNotesCleanup(unittest.TestCase):
    def test_all_old_notes_are_byte_recoverable_from_single_archive(self):
        text = ARCHIVE.read_text(encoding="utf-8")
        self.assertEqual(len(OLD), 12)
        for name in OLD:
            with self.subTest(name=name):
                self.assertFalse((ROOT / name).exists(), "Legacy root note still scattered: " + name)
                pattern = (
                    r"## \\d+\\. 원본: \\x60src/" + re.escape(name) +
                    r"\\x60\\n\\n기존 Git blob SHA: \\x60([0-9a-f]{40})\\x60"
                    r"\\n\\n~~~~text\\n(.*?)~~~~\\n"
                )
                matches = re.findall(pattern, text, flags=re.DOTALL)
                self.assertEqual(len(matches), 1, "Missing/duplicate archive entry: " + name)
                original_sha, copied = matches[0]
                raw = copied.encode("utf-8")
                # A missing terminal newline may be inserted by Markdown
                # fencing. Keep it possible to reconstruct the exact Git blob.
                recoverable = (raw, raw[:-1]) if raw.endswith(b"\\n") else (raw,)
                self.assertIn(original_sha, [git_blob_sha(x) for x in recoverable],
                              "Archive differs from original Git file: " + name)

    def test_no_package_depends_on_archived_notes(self):
        candidates = [
            (ROOT / "manifest.json").read_text(encoding="utf-8"),
            (ROOT / "build_integration_candidate.py").read_text(encoding="utf-8"),
            (ROOT / "bootstrap.py").read_text(encoding="utf-8"),
        ]
        for name in OLD:
            with self.subTest(name=name):
                self.assertFalse(any(name in text for text in candidates))

    def test_empty_looking_legacy_runtime_adapter_is_not_deleted(self):
        # The installed private adapter is not in this repo: preserving this
        # path is essential until the real Windows runtime has been inspected.
        self.assertTrue((ROOT / "payload/legacy/geofield_v823_extension.py").is_file())
        backend = (ROOT / "payload/GeoField_CAD_Analysis.py").read_text(encoding="utf-8")
        self.assertIn("RECORDS=record_module()", backend)
        self.assertIn("RECORDS.register_cad(", backend)
        self.assertIn("RECORDS.list_records(", backend)
        self.assertIn("geofield_v823_extension.py", backend)


if __name__ == "__main__":
    unittest.main()
