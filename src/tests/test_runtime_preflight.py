"""Read-only GeoField installation inventory and missing module regressions."""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bootstrap
import installer
import runtime_preflight as rp


class RuntimeDependencyAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="geofield-runtime-inventory-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / "GeoFieldCAD" / "onefile_runtime" / "8a9ac53a821a0eb5"
        self.runtime.mkdir(parents=True)
        self.sources = rp.EXISTING_REQUIRED + rp.UPDATABLE_REQUIRED_BEFORE_INSTALL
        for name in self.sources:
            p = self.runtime / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(("original-startup:" + name).encode("utf8"))
        self.personal = {
            "cad_models/owned.step":b"untouched private CAD",
            "geofield_v81.sqlite3":b"untouched sqlite bytes",
            "cad_analysis_jobs/fea_runs/example/geofield_case.frd":b"FRD evidence",
            "ml/owned-model.joblib":b"protected model",
        }
        for name, data in self.personal.items():
            p = self.runtime / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

    def assert_personal_untouched(self):
        for name, data in self.personal.items():
            self.assertEqual((self.runtime / name).read_bytes(), data)

    def test_present_modules_report_presence_not_solver_success(self):
        report = rp.audit_runtime(self.runtime)
        self.assertTrue(report["ready_for_update"])
        self.assertTrue(report["runtime_found"])
        self.assertEqual(report["required_count"], 26)
        self.assertEqual(len(report["module_states"]), 26)
        self.assertEqual(report["missing"], [])
        self.assertIn("Does not verify Python imports", report["note"])
        self.assertIn("NOT verified", rp.status_summary(report))
        self.assert_personal_untouched()

    def test_outdated_engine_runtime_api_is_reported_without_execution(self):
        old = self.runtime / "engine_runtime.py"
        old.write_text(
            "REQUIRED_ML = ()\n"
            "def engine_python(*args): return None\n",
            encoding="utf8")
        state = rp.audit_engine_runtime_contract(self.runtime)
        self.assertFalse(state["compatible"])
        self.assertEqual(state["reason"], "required_api_names_absent")
        self.assertEqual(state["missing_exports"], sorted([
            "REQUIRED_GMSH", "gmsh_python_status", "prepare_python_environment"]))
        self.assertFalse(state["installed_code_executed"])
        self.assert_personal_untouched()
        old.write_text(
            "REQUIRED_ML = ()\nREQUIRED_GMSH = ()\n"
            "def engine_python(*args): pass\n"
            "def gmsh_python_status(*args): pass\n"
            "def prepare_python_environment(*args): pass\n",
            encoding="utf8")
        good = rp.audit_engine_runtime_contract(self.runtime)
        self.assertTrue(good["compatible"])
        self.assertFalse(good["verified_imports_or_solver"])
        self.assert_personal_untouched()

    def test_invalid_old_engine_api_blocks_install_before_port_termination(self):
        (self.runtime / "engine_runtime.py").write_text(
            "def engine_python(*args): pass\n", encoding="utf8")
        output = io.StringIO()
        with (patch.dict(os.environ, {"LOCALAPPDATA": str(self.root),
                                     "GF_DIAG": str(self.root / "diagnostics")}),
              patch.object(bootstrap, "verify_bundle",
                           return_value={"runtime_id":self.runtime.name}),
              patch.object(bootstrap, "DirectoryBundle",
                           return_value=object()),
              patch.object(bootstrap, "assess_compatibility",
                           return_value={"safe_to_install": True, "blocking_files":[]}),
              patch.object(bootstrap, "write_compatibility_report",
                           return_value=None),
              patch.object(bootstrap, "wait_for_port_release",
                           side_effect=AssertionError("must not terminate before API audit")),
              patch.object(bootstrap, "apply",
                           side_effect=AssertionError("must not install incompatible runtime")),
              contextlib.redirect_stdout(output)):
            rc = bootstrap.main(["bootstrap.py","--install-only"])
        self.assertEqual(rc,26)
        self.assertIn("prepare_python_environment",output.getvalue())
        self.assert_personal_untouched()

    def test_missing_installed_dependency_blocks_preflight_with_exact_name(self):
        (self.runtime / "cad_common.py").unlink()
        report = rp.audit_runtime(self.runtime)
        self.assertFalse(report["ready_for_update"])
        self.assertEqual(report["missing"], ["cad_common.py"])
        with self.assertRaisesRegex(RuntimeError,"cad_common.py"):
            bootstrap.check_mesh_series_runtime(self.runtime)
        self.assert_personal_untouched()

    def test_empty_file_blocks_preflight(self):
        (self.runtime / "fea_compare.py").write_bytes(b"")
        report = rp.audit_runtime(self.runtime)
        self.assertEqual(report["empty_or_unreadable"],["fea_compare.py"])
        self.assertFalse(report["ready_for_update"])
        with self.assertRaisesRegex(RuntimeError, "fea_compare.py"):
            bootstrap.check_mesh_series_runtime(self.runtime)
        self.assert_personal_untouched()

    def test_linked_parent_is_never_treated_as_verified_module(self):
        original = Path.is_symlink
        fake_parent = self.runtime / "legacy"
        def checker(obj):
            return obj == fake_parent or original(obj)
        with patch.object(Path, "is_symlink", checker):
            report = rp.audit_runtime(self.runtime)
        self.assertIn("legacy/geofield_v823_extension.py", report["unsafe"])
        self.assertFalse(report["ready_for_update"])
        self.assert_personal_untouched()

    def test_missing_runtime_reports_without_creating_directories(self):
        missing_root = self.root / "new_install" / "never_made"
        self.assertFalse(missing_root.exists())
        report = rp.audit_runtime(missing_root)
        self.assertFalse(report["ready_for_update"])
        self.assertFalse(report["runtime_found"])
        self.assertEqual(report["missing"], ["runtime_root"])
        self.assertFalse(missing_root.exists())
        self.assert_personal_untouched()

    def test_cli_diagnostic_does_not_start_port_or_touch_data(self):
        # A genuine API-shaped module is required; plain file presence alone
        # is no longer sufficient to report upgrade readiness.
        (self.runtime / "engine_runtime.py").write_text(
            "REQUIRED_ML = ()\nREQUIRED_GMSH = ()\n"
            "def engine_python(*args): pass\n"
            "def gmsh_python_status(*args): pass\n"
            "def prepare_python_environment(*args): pass\n",
            encoding="utf8")
        local = self.root
        root = local / "GeoFieldCAD" / "onefile_runtime" / "8a9ac53a821a0eb5"
        self.assertEqual(root, self.runtime)
        output = io.StringIO()
        with (patch.dict(os.environ, {"LOCALAPPDATA":str(local)}),
              patch.object(bootstrap, "verify_bundle", return_value={"runtime_id":root.name}),
              patch.object(bootstrap, "DirectoryBundle", return_value=object()),
              patch.object(bootstrap, "audit_backend_import_contract",
                           return_value={"compatible":True,"read_only":True}),
              patch.object(bootstrap, "wait_for_port_release", side_effect=AssertionError("port access forbidden")),
              patch.object(bootstrap, "apply", side_effect=AssertionError("install forbidden")),
              contextlib.redirect_stdout(output)):
            rc = bootstrap.main(["bootstrap.py", "--audit-runtime"])
        self.assertEqual(rc, 0)
        report = json.loads(output.getvalue())
        self.assertTrue(report["ready_for_update"])
        self.assertTrue(report["ready_for_compatible_update"])
        self.assertTrue(report["engine_api_contract"]["compatible"])
        self.assertTrue(report["source_api_contract"]["compatible"])
        self.assertEqual(report["required_count"],26)
        self.assertFalse((self.root / "GeoFieldCAD" / "diagnostics").exists())
        self.assert_personal_untouched()

    def test_cli_missing_module_returns_nonzero_before_any_install(self):
        (self.runtime / "history_store.py").unlink()
        output=io.StringIO()
        with (patch.dict(os.environ, {"LOCALAPPDATA":str(self.root)}),
              patch.object(bootstrap, "verify_bundle", return_value={"runtime_id":self.runtime.name}),
              patch.object(bootstrap, "DirectoryBundle", return_value=object()),
              patch.object(bootstrap, "wait_for_port_release", side_effect=AssertionError("port access forbidden")),
              patch.object(bootstrap, "apply", side_effect=AssertionError("install forbidden")),
              contextlib.redirect_stdout(output)):
            rc = bootstrap.main(["bootstrap.py", "--audit-runtime"])
        self.assertEqual(rc,24)
        self.assertEqual(json.loads(output.getvalue())["missing"],["history_store.py"])
        self.assert_personal_untouched()

    def test_direct_backend_imports_are_covered_by_manifest_or_audit(self):
        module_names = {n.removesuffix(".py").replace("/", ".") for n in self.sources}
        module_names |= set(installer.ALLOWED_TARGETS)
        payload = ROOT / "payload"
        staged = {n.removesuffix(".py").replace("/", ".") for n in installer.ALLOWED_TARGETS}
        known_stdlib = set(sys.stdlib_module_names)
        for path in (payload / "GeoField_CAD_Analysis.py",payload / "fea_solver.py"):
            source = ast.parse(path.read_text(encoding="utf8"))
            for node in source.body:
                mod = None
                if isinstance(node,ast.ImportFrom):
                    mod = node.module
                elif isinstance(node,ast.Import):
                    mod = node.names[0].name
                if mod and mod.split(".")[0] not in known_stdlib and mod not in ("cadquery","OCP","gmsh"):
                    head = mod.split(".")[0]
                    self.assertTrue(mod in module_names or mod in staged or head in ("ml",),
                                    f"Startup import not covered by dependency audit: {path.name}: {mod}")
        self.assert_personal_untouched()

if __name__ == "__main__":
    unittest.main()
