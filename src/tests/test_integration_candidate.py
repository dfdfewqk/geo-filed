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
        self.engine_original = (
            b"REQUIRED_ML = ()\nREQUIRED_GMSH = ()\n"
            b"def engine_python(*args, **kwargs): pass\n"
            b"def gmsh_python_status(*args, **kwargs): pass\n"
            b"def prepare_python_environment(*args, **kwargs): pass\n"
        )
        (self.runtime / "engine_runtime.py").write_bytes(self.engine_original)
        self.legacy = {}
        for name, meta in self.manifest["files"].items():
            if name == "fea_load_moment.py" or (name in candidate.B06_NEW_TARGETS and name != "fea_compare.py"):
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

    def test_ml_review_helper_is_signed_root_artifact_without_private_weights(self):
        for name in ("GeoField_ML_Source_Review.cmd", "ml_runtime_source_review.py",
                     "GeoField_ML_Environment_Check.cmd", "acceptance_probe.py"):
            self.assertTrue((self.stage/name).is_file(),name)
            self.assertEqual((self.stage/name).read_bytes(),
                             (ROOT/name).read_bytes(),name)
        self.assertFalse((self.stage/"payload/ml/brepmfr_worker.py").exists())
        self.assertFalse((self.stage/"payload/ml/weights/best-epoch43-f1_0.8626.ckpt").exists())
        self.assertEqual(subprocess.run(
            [sys.executable,str(self.stage/"verify_package.py")],
            capture_output=True,text=True).returncode,0)

    def test_verified_candidate_exact_26_files(self):
        out = installer.verify_bundle(installer.DirectoryBundle(self.stage))
        self.assertEqual(len(out["files"]), 26)
        self.assertEqual(set(out["files"]), installer.ALLOWED_TARGETS)
        for name in candidate.NEW_RUNTIME + candidate.B06_NEW_ROOT + candidate.B06_NEW_PAYLOAD:
            self.assertTrue((self.stage / "payload" / name).is_file())
            target = self.stage / "payload" / name
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), out["files"][name]["to"])

    def test_user_screenshot_fifteen_unrecognized_files_migrate_as_one_backed_up_set(self):
        # Actual case observed on 2026-10-28: all fifteen paths were present
        # with unrecognized hashes, including bundled report.json.
        from runtime_compatibility import assess_compatibility
        names=(
            "GeoField_CAD_Analysis.py","fea_convergence.py",
            "fea_load_moment.py","fea_mesh_series.py",
            "fea_result_trust_gate.py","fea_solver.py",
            "frontend/cad.js","frontend/index.html",
            "ml/r12_research/build_data.py","ml/r12_research/features.py",
            "ml/r12_research/report.json","ml/r12_research/train_eval.py",
            "ml/r12_research/worker.py","ml_env_resolver.py","ml_r12_bridge.py",
        )
        original={}
        for name in names:
            local=self.runtime/name
            local.parent.mkdir(parents=True,exist_ok=True)
            original[name]=("user-installed unknown version "+name).encode()
            local.write_bytes(original[name])
        diagnostic=assess_compatibility(self.runtime,self.manifest)
        self.assertEqual(set(diagnostic["blocking_files"]),set(names))
        self.assertEqual(diagnostic["explicit_reference_report_migration_files"],
                         ["ml/r12_research/report.json"])
        self.assertTrue(diagnostic["explicit_code_migration_possible"])
        self.assertEqual(set(diagnostic["explicit_migration_files"]),set(names))
        # Fail closed until there is an explicit exact snapshot approval.
        with self.assertRaisesRegex(RuntimeError,"Refusing to overwrite unknown source"):
            installer.apply(installer.DirectoryBundle(self.stage),
                            localappdata=self.tmp/"user_simulation")
        self.assert_protected()
        approved={name:diagnostic["file_versions"][name]["installed_sha256"]
                  for name in diagnostic["explicit_migration_files"]}
        receipt={}
        self.assertEqual(installer.apply(installer.DirectoryBundle(self.stage),
                         localappdata=self.tmp/"user_simulation",
                         approved_unknown_hashes=approved,receipt=receipt),0)
        for name in names:
            self.assertEqual((self.runtime/name).read_bytes(),
                             (self.stage/"payload"/name).read_bytes())
            self.assertEqual((Path(receipt["backup"])/name).read_bytes(),original[name])
        self.assert_protected()
        installer.rollback_install(receipt)
        for name in names:
            self.assertEqual((self.runtime/name).read_bytes(),original[name])
        self.assert_protected()

    def test_missing_original_r12_research_files_can_be_added_without_migration(self):
        # The old 14-entry manifest had from=null for these known additive
        # entries but forgot allow_missing_from, blocking an older Windows app.
        for name in candidate.R12_ADD_IF_MISSING:
            self.assertTrue(self.manifest["files"][name]["allow_missing_from"], name)
            (self.runtime / name).unlink()
        pkg = installer.DirectoryBundle(self.stage)
        receipt = {}
        self.assertEqual(installer.apply(pkg, localappdata=self.tmp / "user_simulation",
                                         receipt=receipt), 0)
        for name in candidate.R12_ADD_IF_MISSING:
            self.assertEqual((self.runtime / name).read_bytes(),
                             (self.stage / "payload" / name).read_bytes())
        self.assert_protected()
        self.assertEqual(installer.rollback_install(receipt),len(receipt["changed"]))
        for name in candidate.R12_ADD_IF_MISSING:
            self.assertFalse((self.runtime / name).exists(),name)
        self.assert_protected()

    def test_existing_unrecognized_r12_model_is_never_overwritten(self):
        name = "ml/r12_research/research_model.joblib"
        current = self.runtime / name
        current.write_bytes(b"unknown user-modified research-model bytes")
        before = {n:(self.runtime / n).read_bytes() for n in self.legacy}
        with self.assertRaisesRegex(RuntimeError, "installed file differs"):
            installer.apply(installer.DirectoryBundle(self.stage),
                            localappdata=self.tmp / "user_simulation")
        self.assertEqual(current.read_bytes(),b"unknown user-modified research-model bytes")
        self.assertEqual({n:(self.runtime / n).read_bytes() for n in self.legacy},before)
        self.assert_protected()

    def test_missing_mandatory_main_or_solver_still_blocks_update(self):
        for name in ("GeoField_CAD_Analysis.py","fea_solver.py"):
            path = self.runtime / name
            old = path.read_bytes()
            path.unlink()
            try:
                # Missing fea_solver is rejected earlier by the installed
                # runtime identity guard; missing main reaches the hash gate.
                reason = ("not the matching GeoField runtime" if name == "fea_solver.py"
                          else "installed file differs")
                with self.assertRaisesRegex(RuntimeError, reason):
                    installer.apply(installer.DirectoryBundle(self.stage),
                                    localappdata=self.tmp / "user_simulation")
                self.assertFalse(path.exists())
                self.assert_protected()
            finally:
                path.write_bytes(old)

    def test_candidate_pins_actual_a_b_main_revisions_and_exact_payload_hashes(self):
        lock = json.loads((self.stage / "CANDIDATE_SOURCE_LOCK.json").read_text(encoding="utf8"))
        self.assertEqual(lock["schema"], "geofield-ab-source-lock-v1")
        self.assertEqual(lock["status"], "TEST_CANDIDATE_NOT_FINAL")
        self.assertFalse(lock["production_release_approved"])
        self.assertEqual(lock["required_payload_count"], 26)
        self.assertEqual(lock["source_revisions"]["b_branch_checkout"], candidate._revision("HEAD"))
        self.assertEqual(lock["source_revisions"]["a_fea_branch"],
                         candidate._revision("refs/remotes/origin/work/fea-validation"))
        self.assertEqual(lock["source_revisions"]["historical_main_baseline"],
                         candidate._revision(candidate.HISTORICAL_BASE))
        for name, meta in self.manifest["files"].items():
            self.assertEqual(lock["payload_sha256"][name], meta["to"])
            self.assertEqual(lock["payload_sha256"][name],
                             hashlib.sha256((self.stage / "payload" / name).read_bytes()).hexdigest())
        self.assert_protected()

    def test_generated_verifier_repeated_calls_do_not_create_bytecode_cache(self):
        command = [sys.executable, str(self.stage / "verify_package.py")]
        for _ in range(3):
            status = subprocess.run(command, cwd=self.stage, capture_output=True,
                                    text=True, timeout=35)
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        self.assertFalse(any(p.name == "__pycache__" for p in self.stage.rglob("*")))
        self.assert_protected()

    def test_candidate_integrity_rejects_added_file_and_edited_source_lock(self):
        command = [sys.executable, str(self.stage / "verify_package.py")]
        extra = self.stage / "payload" / "unexpected.py"
        extra.write_text("print('untrusted extra file')", encoding="utf8")
        denied = subprocess.run(command, cwd=self.stage, capture_output=True,
                                text=True, timeout=35)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("Candidate inventory differs", denied.stdout)
        extra.unlink()
        protected = self.stage / "CANDIDATE_SOURCE_LOCK.json"
        before = protected.read_bytes()
        try:
            protected.write_bytes(before + b"tampered")
            denied = subprocess.run(command, cwd=self.stage, capture_output=True,
                                    text=True, timeout=35)
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("Unverified candidate file", denied.stdout)
        finally:
            protected.write_bytes(before)
        approved = subprocess.run(command, cwd=self.stage, capture_output=True,
                                  text=True, timeout=35)
        self.assertEqual(approved.returncode, 0, approved.stdout + approved.stderr)
        self.assert_protected()

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
        for name in candidate.NEW_RUNTIME + candidate.B06_NEW_ROOT + candidate.B06_NEW_PAYLOAD:
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

    def _prepare_sandbox_backend_probe(self):
        """Simulated --check only, but real CMD, manifest and installer code.

        Proprietary engine_runtime/cad_common/other modules are not in the
        public GitHub checkout. Never claim this tests real CAD/FEA backends.
        A test-only sitecustomize intercepts ONLY Python subprocess.run of the
        `GeoField_CAD_Analysis.py --check` command inside bootstrap. This
        interpreter hook exists in a separate temp directory, not the package.
        """
        assert os.name == "nt"
        hook = self.tmp / "mock_health_only"
        hook.mkdir()
        target_hash = self.manifest["files"]["GeoField_CAD_Analysis.py"]["to"]
        source = r'''# TEST HARNESS ONLY. No real CAD/FEA health probe is being made.
import hashlib
import json
import os
from pathlib import Path
import subprocess
_orig_run = subprocess.run
def _fake_backend_health(command, *args, **kwargs):
    if (isinstance(command, (tuple, list)) and "--check" in command and
        any(str(x).endswith("GeoField_CAD_Analysis.py") for x in command)):
        script = next(Path(x) for x in command if str(x).endswith("GeoField_CAD_Analysis.py"))
        installed = hashlib.sha256(script.read_bytes()).hexdigest() == os.environ["GF_TEST_UPDATED_BACKEND_SHA"]
        with open(os.environ["GF_TEST_CHECK_TRACE"], "a", encoding="utf8") as out:
            out.write(("updated" if installed else "baseline") + chr(10))
        if installed and os.environ.get("GF_TEST_POSTCHECK_FAILURE") == "1":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="synthetic post-install failure")
        payload = {"capabilities": {"step_engine":"OpenCASCADE/CadQuery", "cad_analysis": True,
                                  "synthetic_preflight": True}}
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")
    return _orig_run(command, *args, **kwargs)
subprocess.run = _fake_backend_health
'''
        (hook / "sitecustomize.py").write_text(source, encoding="utf-8")
        # Test-only source stubs model the *symbols* required by today's
        # backend; never pretend these fake API declarations can execute CAD,
        # FEA or ML. The real CMD + preflight verifies the static API before
        # the synthetic subprocess --check health interception is reached.
        import ast
        from runtime_preflight import EXISTING_REQUIRED
        required={}
        for candidate_name in ('GeoField_CAD_Analysis.py','fea_solver.py'):
            tree=ast.parse((self.stage/'payload'/candidate_name).read_text(encoding='utf8'))
            for node in tree.body:
                if isinstance(node,ast.ImportFrom) and node.module:
                    filename=node.module.replace('.','/')+'.py'
                    if filename in EXISTING_REQUIRED:
                        required.setdefault(filename,set()).update(
                            alias.name for alias in node.names)
        for name in EXISTING_REQUIRED:
            if name in ('engine_runtime.py','fea_compare.py'):
                continue  # retain original engine / reviewed historical comparator source
            p=self.runtime/name
            p.parent.mkdir(parents=True,exist_ok=True)
            declared=sorted(required.get(name,set()))
            p.write_text(
                '# SANDBOX-ONLY AST API names, NEVER real CAD/FEA implementations\n'+
                ''.join(symbol+' = None\n' for symbol in declared if symbol!='*'),
                encoding='utf8')
        # Production UI serves this existing CSS file directly, but it is
        # NOT a Python module or an update payload target.
        from runtime_preflight import FRONTEND_REQUIRED
        for name in FRONTEND_REQUIRED:
            p=self.runtime/name
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text("/* disposable preflight fixture; no user styles */\n",encoding="utf8")
        return hook

    def _run_windows_cmd_install_only(self):
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(self.tmp / "user_simulation")
        env["GF_DIAG"] = str(self.tmp / "cmd_diagnostics")
        env["GEOFIELD_PYTHON"] = sys.executable
        env["PYTHONPATH"] = str(self._health_hook)
        env["GF_TEST_UPDATED_BACKEND_SHA"] = self.manifest["files"]["GeoField_CAD_Analysis.py"]["to"]
        env["GF_TEST_CHECK_TRACE"] = str(self.tmp / "check_trace.txt")
        if getattr(self, "_postcheck_fail", False):
            env["GF_TEST_POSTCHECK_FAILURE"] = "1"
        cmd = self.stage / "GeoField_Start.cmd"
        return subprocess.run('"' + str(cmd) + '" --install-only',
                              cwd=self.stage, shell=True, input="\\n",
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=100, env=env)

    @unittest.skipUnless(os.name == "nt", "Actual CMD invocation requires Windows")
    def test_real_windows_cmd_install_only_checks_original_and_updated_backend(self):
        self._health_hook = self._prepare_sandbox_backend_probe()
        reply = self._run_windows_cmd_install_only()
        self.assertEqual(reply.returncode, 0, reply.stdout + reply.stderr)
        self.assertIn("Installed code passed backend --check", reply.stdout)
        self.assertIn("session finished normally", reply.stdout)
        self.assertTrue((self.tmp / "cmd_diagnostics" / "bootstrap_latest.log").exists())
        for name in self.manifest["files"]:
            self.assertEqual((self.runtime / name).read_bytes(),
                             (self.stage / "payload" / name).read_bytes())
        self.assert_protected()
        self.assertEqual((self.tmp / "check_trace.txt").read_text().splitlines(),
                         ["baseline", "updated"])
        # Repeat actual CMD: installed code must remain unchanged (idempotent).
        reply2 = self._run_windows_cmd_install_only()
        self.assertEqual(reply2.returncode, 0, reply2.stdout + reply2.stderr)
        self.assertIn("ALREADY_INSTALLED", reply2.stdout)
        self.assertEqual((self.tmp / "check_trace.txt").read_text().splitlines(),
                         ["baseline", "updated", "updated", "updated"])
        self.assertFalse(any(p.name == "__pycache__" for p in self.stage.rglob("*")))
        self.assert_protected()

    @unittest.skipUnless(os.name == "nt", "Actual CMD invocation requires Windows")
    def test_real_windows_cmd_install_only_failed_updated_health_rolls_back(self):
        self._health_hook = self._prepare_sandbox_backend_probe()
        self._postcheck_fail = True
        before = {name:(self.runtime / name).read_bytes() for name in self.legacy}
        reply = self._run_windows_cmd_install_only()
        self.assertNotEqual(reply.returncode, 0)
        self.assertIn("synthetic post-install failure", reply.stdout)
        self.assertIn("[ROLLBACK]", reply.stdout)
        self.assertEqual((self.tmp / "check_trace.txt").read_text().splitlines(),
                         ["baseline", "updated"])
        for name, old in before.items():
            self.assertEqual((self.runtime / name).read_bytes(), old)
        self.assertFalse((self.runtime / "fea_load_moment.py").exists())
        self.assert_protected()
        journals = list((self.root / "backups").glob("*/install_journal.json"))
        self.assertEqual(len(journals), 1)
        self.assertEqual(json.loads(journals[0].read_text())["state"], "reverted")

    def _run_windows_cmd_audit_runtime(self):
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(self.tmp / "user_simulation")
        env["GF_DIAG"] = str(self.tmp / "cmd_diagnostics")
        cmd = self.stage / "GeoField_Start.cmd"
        return subprocess.run('"' + str(cmd) + '" --audit-runtime',
                              cwd=self.stage, shell=True, input="\n",
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=55, env=env)

    @unittest.skipUnless(os.name == "nt", "Actual CMD invocation requires Windows")
    def test_real_cmd_runtime_audit_fails_before_install_for_missing_modules(self):
        originals = {name:(self.runtime/name).read_bytes() for name in self.legacy}
        result = self._run_windows_cmd_audit_runtime()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('"ready_for_update": false', result.stdout)
        self.assertIn('"cad_common.py": "missing"', result.stdout)
        self.assertIn('"engine_runtime.py": "present_unverified"', result.stdout)
        self.assertFalse((self.tmp / "cmd_diagnostics" / "bootstrap_latest.log").exists())
        self.assertFalse((self.runtime / "fea_load_moment.py").exists())
        for name,old in originals.items():
            self.assertEqual((self.runtime/name).read_bytes(),old)
        self.assert_protected()

    @unittest.skipUnless(os.name == "nt", "Actual CMD invocation requires Windows")
    def test_real_cmd_runtime_audit_never_installs_even_when_all_files_present(self):
        self._prepare_sandbox_backend_probe()  # synthetic private dependency markers
        originals = {name:(self.runtime/name).read_bytes() for name in self.legacy}
        result = self._run_windows_cmd_audit_runtime()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"ready_for_update": true', result.stdout)
        self.assertIn('"ready_for_compatible_update": true', result.stdout)
        self.assertIn('"source_api_contract"', result.stdout)
        self.assertIn("Required file presence only", result.stdout)
        self.assertFalse((self.tmp / "cmd_diagnostics" / "bootstrap_latest.log").exists())
        self.assertFalse((self.runtime / "fea_load_moment.py").exists())
        for name,old in originals.items():
            self.assertEqual((self.runtime/name).read_bytes(),old)
        self.assert_protected()

    @unittest.skipUnless(os.name == "nt", "Actual CMD invocation requires Windows")
    def test_real_cmd_refuses_private_restore_module_with_missing_export(self):
        self._prepare_sandbox_backend_probe()
        # File is present and valid Python but lacks the actual API.
        (self.runtime/"fea_restore.py").write_text(
            "def outdated_restore(): pass\\n",encoding="utf8")
        result=self._run_windows_cmd_audit_runtime()
        self.assertNotEqual(result.returncode,0)
        self.assertIn('"fea_restore.py"',result.stdout)
        self.assertIn('"restore_payload"',result.stdout)
        self.assertFalse((self.tmp/"cmd_diagnostics"/"bootstrap_latest.log").exists())
        self.assertFalse((self.runtime/"fea_load_moment.py").exists())
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
