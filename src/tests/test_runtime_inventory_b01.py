"""B01 local-only runtime inspection: no source ZIP, CAD, database or upload."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import runtime_inventory_b01 as b01
from runtime_preflight import (
    EXISTING_REQUIRED, UPDATABLE_REQUIRED_BEFORE_INSTALL,
    FRONTEND_REQUIRED, A11_NEW_BACKEND_MODULES,
)


class B01InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="geofield-b01-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "GeoFieldCAD" / "onefile_runtime" / "8a9ac53a821a0eb5"
        self.root.mkdir(parents=True)
        self.src = self.base / "src"
        self.src.mkdir()
        self.payload = self.src / "payload"
        self.payload.mkdir()
        for name in EXISTING_REQUIRED + UPDATABLE_REQUIRED_BEFORE_INSTALL:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("__version__='1.2.3'\n", encoding="utf-8")
        for name in FRONTEND_REQUIRED:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("body{color:black}", encoding="utf-8")
        (self.root / "history_store.py").write_text(
            "__version__='1.2.3'\n"
            "def save(*args): return None\n"
            "def read(*args): return None\n", encoding="utf-8")
        (self.root / "engine_runtime.py").write_text(
            "REQUIRED_ML=()\nREQUIRED_GMSH=()\n"
            "def engine_python(): return None\n"
            "def prepare_python_environment(): return None\n"
            "def gmsh_python_status(): return None\n", encoding="utf-8")
        (self.payload / "GeoField_CAD_Analysis.py").write_text(
            "from history_store import save, read\n"
            "from engine_runtime import engine_python\n", encoding="utf-8")
        (self.payload / "fea_solver.py").write_text(
            "from engine_runtime import gmsh_python_status\n", encoding="utf-8")
        for name in A11_NEW_BACKEND_MODULES:
            (self.src / name).write_text("VERSION='2.0.0'\n", encoding="utf-8")
        self.private = {
            "user_data/owned.step": b"private physical CAD",
            "user_data/protected.sqlite3": b"secret historic SQLite",
            "user_data/FEA.frd": b"verified FEA bytes",
            "ml/weights/protected.joblib": b"private checkpoint",
            "other/passwords.txt": b"no secrets allowed in inventory",
        }
        for name, body in self.private.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)

    def assert_private_untouched(self):
        for name, body in self.private.items():
            self.assertEqual((self.root / name).read_bytes(), body)

    def test_full_known_source_inventory_and_static_api_without_importing(self):
        # Any code inside installed files is PARSED, never executed.
        source = self.root / "history_store.py"
        text = source.read_text()
        source.write_text(text + "raise RuntimeError('must never import this')\n")
        out = b01.inspect_runtime(self.root, self.payload, self.src)
        self.assertTrue(out["runtime_found"])
        self.assertEqual(out["required_installed_count"], 26)
        self.assertEqual(out["fingerprinted_count"], 26)
        self.assertTrue(out["static_source_inventory_complete"])
        self.assertTrue(out["engine_runtime_static_api"]["compatible"])
        self.assertTrue(out["backend_import_static_api"]["compatible"])
        self.assertTrue(out["read_only"])
        self.assertFalse(out["private_source_exported"])
        self.assertFalse(out["network_used"])
        self.assertFalse(out["installed_code_executed"])
        self.assertFalse(out["solver_executed"])
        self.assertFalse(out["safe_to_install_inferred"])
        h = out["inventory"]["history_store.py"]
        self.assertEqual(h["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(h["literal_version_unverified"], "1.2.3")
        self.assertEqual(len(out["new_github_helpers_not_expected_in_old_runtime"]), 4)
        self.assertTrue(all(x["status"] == "present_unverified"
                            for x in out["new_github_helpers_not_expected_in_old_runtime"].values()))
        report = json.dumps(out, ensure_ascii=False)
        for rel, body in self.private.items():
            self.assertNotIn(rel, report)
            self.assertNotIn(body.decode("utf-8"), report)
        self.assertNotIn(str(self.root), report)
        self.assert_private_untouched()

    def test_missing_existing_runtime_is_not_reported_as_ready(self):
        (self.root / "history_store.py").unlink()
        out = b01.inspect_runtime(self.root, self.payload, self.src)
        self.assertIn("history_store.py", out["missing"])
        self.assertFalse(out["static_source_inventory_complete"])
        self.assertFalse(out["safe_to_install_inferred"])
        self.assertEqual(out["inventory"]["history_store.py"]["status"], "missing")
        self.assert_private_untouched()

    def test_unexpected_new_helper_does_not_count_as_old_installed_source(self):
        (self.src / "fea_field_a06.py").unlink()
        out = b01.inspect_runtime(self.root, self.payload, self.src)
        self.assertTrue(out["static_source_inventory_complete"])
        self.assertEqual(
            out["new_github_helpers_not_expected_in_old_runtime"]["fea_field_a06.py"]["status"],
            "missing")
        self.assert_private_untouched()

    def test_missing_candidate_is_explicitly_not_checked_not_implicitly_compatible(self):
        out = b01.inspect_runtime(self.root)
        self.assertEqual(out["backend_import_static_api"]["reason"], "candidate_not_supplied")
        self.assertFalse(out["backend_import_static_api"]["compatible"])
        self.assertEqual(
            out["new_github_helpers_not_expected_in_old_runtime"]["fea_history_a03.py"]["status"],
            "source_not_supplied")
        self.assert_private_untouched()

    def test_legacy_source_present_but_missing_export_is_not_compatible(self):
        (self.root / "history_store.py").write_text("__version__='1.2.3'\ndef save(): pass\n")
        out = b01.inspect_runtime(self.root, self.payload, self.src)
        self.assertTrue(out["static_source_inventory_complete"])
        self.assertFalse(out["backend_import_static_api"]["compatible"])
        self.assertIn("read", out["backend_import_static_api"]["missing_exports"]["history_store.py"])
        self.assert_private_untouched()

    def test_invalid_python_version_secret_and_large_source_are_not_exposed(self):
        source = self.root / "fea_restore.py"
        source.write_text('''VERSION="MY_SUPER_SECRET_DONT_EXPOSE"\ndef broken(:\n''')
        out = b01.inspect_runtime(self.root, self.payload, self.src)
        self.assertEqual(out["inventory"]["fea_restore.py"]["status"], "invalid_python")
        self.assertNotIn("MY_SUPER_SECRET", json.dumps(out))
        self.assertIn("fea_restore.py", out["invalid_or_unsafe"])
        source.write_bytes(b"x" * (b01.MAX_SOURCE_BYTES + 1))
        out = b01.inspect_runtime(self.root, self.payload, self.src)
        self.assertEqual(out["inventory"]["fea_restore.py"]["status"], "empty_or_oversized")
        self.assert_private_untouched()

    def test_symlink_runtime_module_refused_and_private_target_not_read(self):
        p = self.root / "fea_restore.py"
        p.unlink()
        target = self.root / "user_data" / "owned.step"
        try:
            p.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not permitted on this machine")
        out = b01.inspect_runtime(self.root, self.payload, self.src)
        self.assertEqual(out["inventory"]["fea_restore.py"]["status"], "unsafe_symlink")
        self.assertNotIn(target.read_bytes().decode(), json.dumps(out))
        self.assert_private_untouched()

    def test_absent_runtime_does_not_create_it_or_import_installed_modules(self):
        missing = self.base / "not_installed" / "never_made"
        result = b01.inspect_runtime(missing, self.payload, self.src)
        self.assertFalse(result["runtime_found"])
        self.assertEqual(result["fingerprinted_count"], 0)
        self.assertFalse(result["static_source_inventory_complete"])
        self.assertFalse(missing.exists())

    def test_no_default_output_and_optional_explicit_external_json_no_overwrites(self):
        outbuf = io.StringIO()
        with contextlib.redirect_stdout(outbuf):
            rc = b01.main(["--runtime", str(self.root),
                           "--candidate", str(self.payload),
                           "--source-root", str(self.src)])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(outbuf.getvalue())["fingerprinted_count"], 26)
        self.assertEqual(list(self.base.glob("*.json")), [])
        report_path = self.base / "local_b01.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(b01.main(["--runtime", str(self.root),
                                       "--candidate", str(self.payload),
                                       "--source-root", str(self.src),
                                       "--output", str(report_path)]), 0)
        original = report_path.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(b01.main(["--runtime", str(self.root),
                                       "--output", str(report_path)]), 2)
        self.assertEqual(report_path.read_bytes(), original)
        self.assert_private_untouched()

    def test_never_write_report_inside_runtime_or_symlinked_destination(self):
        for path in (self.root / "report.json", self.root / "other" / "report.json"):
            with self.assertRaises(ValueError):
                b01._write_optional_report({"ok": True}, path, self.root)
            self.assertFalse(path.exists())
        self.assert_private_untouched()


if __name__ == "__main__":
    unittest.main()
