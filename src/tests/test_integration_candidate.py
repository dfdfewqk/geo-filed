"""A+B real source packaging exercise. Requires A branch in SCRATCH checkout.

All installations are performed only inside a temporary synthetic Windows
GeoField root. Tests do not load the user's CAD/SQLite/FRD or execute ccx.
"""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import installer
import build_integration_candidate as candidate


class IntegrationCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="geofield-ab-stage-")
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.stage = self.tmp / "staged"
        self.manifest = candidate.build(self.stage)
        self.root = self.tmp / "user_simulation" / "GeoFieldCAD"
        self.runtime = self.root / "onefile_runtime" / self.manifest["runtime_id"]
        self.runtime.mkdir(parents=True)
        self.engine_original = b"retained_engine"
        (self.runtime / "engine_runtime.py").write_bytes(self.engine_original)
        self.legacy = {}
        for name, meta in self.manifest["files"].items():
            if name == "fea_load_moment.py":
                self.assertTrue(meta["allow_missing_from"])
                continue
            source_name = name if name in candidate.SOURCE_AT_ROOT else "payload/" + name
            original = candidate.original_main(source_name)
            self.assertIn(installer.sha(original),
                          [meta.get("from"), meta["to"]] + list(meta.get("compatible_from", [])),
                          "Unrecognized base version: " + name)
            f = self.runtime / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(original)
            self.legacy[name] = original
        self.protected = {
            "CAD/L_bracket.step": b"owned-step-file",
            "history/geofield.sqlite3": b"owned-sqlite-file",
            "fea_runs/caseA/geofield_case.inp": b"owned-INP",
            "fea_runs/caseA/geofield_case.sta": b"owned-STA",
            "fea_runs/caseA/geofield_case.frd": b"owned-FRD",
            "ml/owned-model.joblib": b"owned-ML-model",
        }
        for name, original in self.protected.items():
            p = self.runtime / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(original)

    def assert_protected(self):
        for name, expected in self.protected.items():
            with self.subTest(evidence=name):
                self.assertEqual((self.runtime / name).read_bytes(), expected)
        self.assertEqual((self.runtime / "engine_runtime.py").read_bytes(), self.engine_original)

    def test_verified_candidate_exact_17_files(self):
        out = installer.verify_bundle(installer.DirectoryBundle(self.stage))
        self.assertEqual(len(out["files"]), 17)
        self.assertEqual(set(out["files"]), installer.ALLOWED_TARGETS)
        for name in candidate.NEW_RUNTIME:
            self.assertTrue((self.stage / "payload" / name).is_file())
            target = self.stage / "payload" / name
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), out["files"][name]["to"])

    def test_generated_verify_script_detects_payload_change(self):
        command = [sys.executable, str(self.stage / "verify_package.py")]
        good = subprocess.run(command, cwd=self.stage, capture_output=True, text=True, timeout=35)
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        payload = self.stage / "payload" / "fea_solver.py"
        payload.write_bytes(payload.read_bytes() + b"tampered")
        denied = subprocess.run(command, cwd=self.stage, capture_output=True, text=True, timeout=35)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("Unverified candidate file", denied.stdout)
        self.assert_protected()

    def test_real_integration_candidate_apply_noop_rollback(self):
        receipt = {}
        pkg = installer.DirectoryBundle(self.stage)
        self.assertEqual(installer.apply(pkg, localappdata=self.tmp / "user_simulation", receipt=receipt), 0)
        self.assertEqual((self.runtime / "fea_load_moment.py").read_bytes(),
                         (self.stage / "payload" / "fea_load_moment.py").read_bytes())
        for name in candidate.NEW_RUNTIME:
            self.assertEqual((self.runtime / name).read_bytes(),
                             (self.stage / "payload" / name).read_bytes())
        self.assert_protected()
        second = {}
        self.assertEqual(installer.apply(pkg, localappdata=self.tmp / "user_simulation", receipt=second), 0)
        self.assertEqual(second["changed"], [])
        self.assertEqual(installer.rollback_install(receipt), len(receipt["changed"]))
        self.assertFalse((self.runtime / "fea_load_moment.py").exists())
        for name, old in self.legacy.items():
            self.assertEqual((self.runtime / name).read_bytes(), old)
        self.assert_protected()

    def test_unknown_old_A_module_blocks_whole_install(self):
        filename = self.runtime / "fea_convergence.py"
        filename.write_text("unexpected-local-customization")
        before = {n:(self.runtime / n).read_bytes() for n in self.legacy}
        with self.assertRaisesRegex(RuntimeError, "installed file differs"):
            installer.apply(installer.DirectoryBundle(self.stage), localappdata=self.tmp / "user_simulation")
        for name, data in before.items():
            self.assertEqual((self.runtime / name).read_bytes(), data)
        self.assertFalse((self.runtime / "fea_load_moment.py").exists())
        self.assert_protected()

    def test_unknown_existing_new_dependency_is_preserved_and_blocks(self):
        filename = self.runtime / "fea_load_moment.py"
        filename.write_bytes(b"preexisting-custom-user-module")
        with self.assertRaisesRegex(RuntimeError, "installed file differs"):
            installer.apply(installer.DirectoryBundle(self.stage), localappdata=self.tmp / "user_simulation")
        self.assertEqual(filename.read_bytes(), b"preexisting-custom-user-module")
        self.assert_protected()

    def _prepare_windows_backend_check_runtime(self):
        """Use actual old runtime Python source, with only CAD discovery simulated.

        Actual baseline and integrated Python backends run --check through the
        real CMD and bootstrap. This is not a CAD/Gmsh/CalculiX execution.
        """
        assert os.name == "nt"
        ref = candidate.HISTORICAL_BASE
        listing = subprocess.run(
            ["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", ref,
             "--", "src/payload", "src"],
            check=True, capture_output=True, text=True, timeout=25).stdout.splitlines()
        copied = 0
        for name in listing:
            if not name.endswith(".py") or not name.startswith("src/"):
                continue
            if name.startswith("src/payload/"):
                rel = name[len("src/payload/"):]
            elif name.count("/") == 1:
                rel = name[len("src/"):]
            else:
                continue
            if not rel or rel == "GeoField_CAD_Analysis.py" or rel in installer.ALLOWED_TARGETS:
                continue
            target = self.runtime / rel
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(candidate.original_main(name[len("src/"):]))
            copied += 1
        # Private installed engine_runtime.py is not published on GitHub.
        # Supply a clearly synthetic, read-only import stub for --check ONLY.
        # It never runs Gmsh, OCP, FreeCAD or CalculiX.
        self.engine_original = (
            "def gmsh_python_status(*args, **kwargs):\\n"
            "    return {'ok': False, 'error': 'synthetic engine unavailable'}\\n"
            "def prepare_python_environment(*args, **kwargs):\\n"
            "    return {'ok': False, 'error': 'synthetic engine unavailable'}\\n"
        ).encode("utf-8").replace(b"\\\\n", b"\\n")
        (self.runtime / "engine_runtime.py").write_bytes(self.engine_original)
        self.assertGreater(copied, 5)
        # --check needs an available CAD engine to choose Python. In CI this is
        # a marker only; no CAD operation or real engine validation is claimed.
        for package in ("cadquery", "OCP"):
            place = self.runtime / package
            place.mkdir(parents=True, exist_ok=True)
            (place / "__init__.py").write_text("# simulation for --check ONLY\\n")
        # A verified baseline must exist before running a real CMD upgrade.
        self.assertTrue((self.runtime / "cad_common.py").exists())
        self.assertTrue((self.runtime / "fea_compare.py").exists())
        return copied

    def _run_windows_cmd_install_only(self):
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(self.tmp / "user_simulation")
        env["GF_DIAG"] = str(self.tmp / "cmd_diagnostics")
        env["GEOFIELD_PYTHON"] = sys.executable
        env["PYTHONPATH"] = str(self.runtime)
        cmd = self.stage / "GeoField_Start.cmd"
        return subprocess.run('"' + str(cmd) + '" --install-only',
                              cwd=self.stage, shell=True, input="\\n",
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=100, env=env)

    @unittest.skipUnless(os.name == "nt", "Actual CMD invocation requires Windows")
    def test_real_windows_cmd_install_only_checks_original_and_updated_backend(self):
        self._prepare_windows_backend_check_runtime()
        reply = self._run_windows_cmd_install_only()
        self.assertEqual(reply.returncode, 0, reply.stdout + reply.stderr)
        self.assertIn("Installed code passed backend --check", reply.stdout)
        self.assertIn("session finished normally", reply.stdout)
        self.assertTrue((self.tmp / "cmd_diagnostics" / "bootstrap_latest.log").exists())
        for name in candidate.NEW_RUNTIME:
            self.assertEqual((self.runtime / name).read_bytes(),
                             (self.stage / "payload" / name).read_bytes())
        for name in self.manifest["files"]:
            self.assertEqual((self.runtime / name).read_bytes(),
                             (self.stage / "payload" / name).read_bytes())
        self.assert_protected()
        # Repeat the actual CMD path: now every file is already installed.
        reply2 = self._run_windows_cmd_install_only()
        self.assertEqual(reply2.returncode, 0, reply2.stdout + reply2.stderr)
        self.assertIn("ALREADY_INSTALLED", reply2.stdout)
        self.assert_protected()

    def _run_windows_cmd_verify_only(self):
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(self.tmp / "user_simulation")
        env["GF_DIAG"] = str(self.tmp / "cmd_diagnostics")
        cmd = self.stage / "GeoField_Start.cmd"
        # Execute the real checked-in Windows launcher, not a mocked entrypoint.
        # A single newline answers its final PAUSE without user interaction.
        return subprocess.run('"' + str(cmd) + '" --verify-only',
                              cwd=self.stage, shell=True, input="\\n",
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=55, env=env)

    @unittest.skipUnless(os.name == "nt", "Actual CMD invocation requires Windows")
    def test_real_windows_cmd_verify_only_preserves_runtime(self):
        before = {name:(self.runtime / name).read_bytes() for name in self.legacy}
        result = self._run_windows_cmd_verify_only()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Package integrity verified", result.stdout)
        self.assertIn("session finished normally", result.stdout)
        self.assertTrue((self.tmp / "cmd_diagnostics" / "bootstrap_latest.log").exists())
        for name, data in before.items():
            self.assertEqual((self.runtime / name).read_bytes(), data)
        self.assertFalse((self.runtime / "fea_load_moment.py").exists())
        self.assert_protected()

    @unittest.skipUnless(os.name == "nt", "Actual CMD invocation requires Windows")
    def test_real_windows_cmd_blocks_corrupt_package_before_bootstrap(self):
        payload = self.stage / "payload" / "fea_solver.py"
        payload.write_bytes(payload.read_bytes() + b"tampered after packaging")
        result = self._run_windows_cmd_verify_only()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Package verification failed", result.stdout)
        # The failed launcher never invokes bootstrap or the installer.
        self.assertFalse((self.tmp / "cmd_diagnostics" / "bootstrap_latest.log").exists())
        self.assertFalse((self.runtime / "fea_load_moment.py").exists())
        for name, data in self.legacy.items():
            self.assertEqual((self.runtime / name).read_bytes(), data)
        self.assert_protected()

    def test_staged_zip_round_trip(self):
        dest = self.tmp / "candidate.zip"
        candidate.zip_candidate(self.stage, dest)
        extracted = self.tmp / "extracted"
        with __import__("zipfile").ZipFile(dest) as archive:
            for item in archive.infolist():
                self.assertFalse(item.filename.startswith("/"))
                self.assertNotIn("..", Path(item.filename).parts)
            archive.extractall(extracted)
        self.assertEqual(installer.verify_bundle(installer.DirectoryBundle(extracted))["files"],
                         self.manifest["files"])
        self.assert_protected()


if __name__ == "__main__":
    unittest.main()
