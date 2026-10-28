"""Non-destructive GeoField updater regression using disposable fake runtimes.

No real Windows installation, STEP/SQLite/INP/STA/FRD, solver, network install,
or private user archive is accessed. Use GitHub Windows CI for OS-specific checks.
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import installer
import bootstrap

RUNTIME_ID = "8a9ac53a821a0eb5"

class DisposableInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="geofield-install-safety-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "GeoFieldCAD"
        self.runtime = self.root / "onefile_runtime" / RUNTIME_ID
        self.runtime.mkdir(parents=True)
        self.engine_original = (
            b"REQUIRED_ML = ()\nREQUIRED_GMSH = ()\n"
            b"def engine_python(*args, **kwargs): pass\n"
            b"def gmsh_python_status(*args, **kwargs): pass\n"
            b"def prepare_python_environment(*args, **kwargs): pass\n"
        )
        (self.runtime / "engine_runtime.py").write_bytes(self.engine_original)
        self.bundle = self.base / "safe_bundle"
        (self.bundle / "payload").mkdir(parents=True)
        self.old = {}
        self.new = {}
        self.meta = {}
        for name in sorted(installer.ALLOWED_TARGETS):
            old = ("original:" + name).encode()
            new = ("update:" + name).encode()
            if name in ("fea_solver.py", "ml/r12_research/research_model.joblib"):
                new = old  # no engineering solver / model weight replacement
            self.old[name] = old
            self.new[name] = new
            target = self.runtime / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(old)
            payload = self.bundle / "payload" / name
            payload.parent.mkdir(parents=True, exist_ok=True)
            payload.write_bytes(new)
            self.meta[name] = {"from": installer.sha(old), "to": installer.sha(new),
                               "bytes": len(new)}
        self.manifest = {"runtime_id": RUNTIME_ID, "title": "Synthetic safety test",
                         "files": self.meta}
        (self.bundle / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        self.protected = {
            "CAD/L_bracket.step": b"step-protected-original",
            "history/geofield.sqlite3": b"sqlite-protected-original",
            "fea_runs/real/geofield_case.inp": b"inp-protected-original",
            "fea_runs/real/geofield_case.sta": b"sta-protected-original",
            "fea_runs/real/geofield_case.frd": b"frd-protected-original",
            "ml/private-model.joblib": b"weight-protected-original",
        }
        for name, data in self.protected.items():
            target = self.runtime / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def package(self):
        return installer.DirectoryBundle(self.bundle)

    def install(self, receipt=None):
        return installer.apply(self.package(), localappdata=self.base, receipt=receipt)

    def assert_originals(self):
        for name, data in self.old.items():
            with self.subTest(file=name):
                self.assertEqual((self.runtime / name).read_bytes(), data)
        self.assert_protected()

    def assert_protected(self):
        for name, data in self.protected.items():
            with self.subTest(protected=name):
                self.assertEqual((self.runtime / name).read_bytes(), data)
        self.assertEqual((self.runtime / "engine_runtime.py").read_bytes(),
                         self.engine_original)

    def test_real_installer_functions_update_noop_then_rollback(self):
        receipt = {}
        self.assertEqual(self.install(receipt), 0)
        self.assertEqual(len(receipt["changed"]),
                         sum(self.old[k] != self.new[k] for k in self.meta))
        for name, data in self.new.items():
            self.assertEqual((self.runtime / name).read_bytes(), data)
        self.assert_protected()
        after = {}
        self.assertEqual(self.install(after), 0)
        self.assertEqual(after["changed"], [])
        self.assertIsNone(after["backup"])
        self.assertEqual(installer.rollback_install(receipt), len(receipt["changed"]))
        self.assert_originals()
        self.assertEqual(json.loads(Path(receipt["journal"]).read_text())["state"], "reverted")

    def test_bad_payload_hash_never_changes_runtime(self):
        (self.bundle / "payload" / "frontend" / "cad.js").write_bytes(b"altered-untrusted-package")
        with self.assertRaisesRegex(RuntimeError, "integrity mismatch"):
            self.install()
        self.assert_originals()

    def test_unknown_installed_hash_refuses_entire_update(self):
        (self.runtime / "frontend" / "cad.js").write_bytes(b"unknown-local-revision")
        with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite unknown source"):
            self.install()
        for name, data in self.old.items():
            if name != "frontend/cad.js":
                self.assertEqual((self.runtime / name).read_bytes(), data)
        self.assertEqual((self.runtime / "frontend" / "cad.js").read_bytes(), b"unknown-local-revision")
        self.assert_protected()

    def test_explicit_snapshot_local_code_migration_preserves_backup_and_rolls_back(self):
        """Only a user-approved exact local source SHA can be replaced."""
        affected=("GeoField_CAD_Analysis.py","frontend/cad.js","frontend/index.html")
        source={}
        approved={}
        for name in affected:
            custom=("private local code "+name).encode("utf8")
            (self.runtime/name).write_bytes(custom)
            source[name]=custom
            approved[name]=installer.sha(custom)
        # Normal updater must still refuse any unknown local code.
        with self.assertRaisesRegex(RuntimeError,"Refusing to overwrite unknown source"):
            self.install()
        self.assert_protected()
        receipt={}
        self.assertEqual(installer.apply(self.package(),localappdata=self.base,
                                         receipt=receipt,approved_unknown_hashes=approved),0)
        self.assertGreaterEqual(len(receipt["changed"]),3)
        for name in affected:
            self.assertEqual((self.runtime/name).read_bytes(),self.new[name])
            self.assertEqual((Path(receipt["backup"])/name).read_bytes(),source[name])
        self.assert_protected()
        installer.rollback_install(receipt)
        for name in affected:self.assertEqual((self.runtime/name).read_bytes(),source[name])
        self.assert_protected()

    def test_bulk_unknown_code_and_r12_reference_report_requires_exact_hash_consent(self):
        names=("GeoField_CAD_Analysis.py","fea_convergence.py","fea_solver.py",
               "frontend/index.html","frontend/cad.js","ml_r12_bridge.py",
               "ml/r12_research/features.py","ml/r12_research/report.json")
        originals={}
        approved={}
        for name in names:
            original=("unrecognized local "+name).encode()
            (self.runtime/name).write_bytes(original)
            originals[name]=original
            approved[name]=installer.sha(original)
        with self.assertRaisesRegex(RuntimeError,"Refusing to overwrite unknown source"):
            self.install()
        self.assert_protected()
        receipt={}
        self.assertEqual(installer.apply(self.package(),localappdata=self.base,
                     receipt=receipt,approved_unknown_hashes=approved),0)
        for name in names:
            self.assertEqual((self.runtime/name).read_bytes(),self.new[name])
            self.assertEqual((Path(receipt["backup"])/name).read_bytes(),originals[name])
        self.assert_protected()
        installer.rollback_install(receipt)
        for name in names:self.assertEqual((self.runtime/name).read_bytes(),originals[name])
        self.assert_protected()

    def test_bulk_explicit_migration_cannot_approve_any_model_weights(self):
        edited="ml/r12_research/research_model.joblib"
        (self.runtime/edited).write_bytes(b"local unknown model weights")
        code="frontend/cad.js"
        (self.runtime/code).write_bytes(b"unknown local code")
        report="ml/r12_research/report.json"
        (self.runtime/report).write_bytes(b"local reference report")
        bad={code:installer.sha(b"unknown local code"),
             report:installer.sha(b"local reference report"),
             edited:installer.sha(b"local unknown model weights")}
        with self.assertRaisesRegex(RuntimeError,"Invalid explicit local source approval map"):
            installer.apply(self.package(),localappdata=self.base,
                            approved_unknown_hashes=bad)
        bad.pop(edited)
        with self.assertRaisesRegex(RuntimeError,"Refusing to overwrite unknown source"):
            installer.apply(self.package(),localappdata=self.base,
                            approved_unknown_hashes=bad)
        self.assertEqual((self.runtime/edited).read_bytes(),b"local unknown model weights")
        self.assert_protected()

    def test_reference_report_migration_rejects_changed_sha_before_install(self):
        name="ml/r12_research/report.json"
        (self.runtime/name).write_bytes(b"report-v1")
        approved={name:installer.sha(b"report-v2")}
        with self.assertRaisesRegex(RuntimeError,"Refusing to overwrite unknown source"):
            installer.apply(self.package(),localappdata=self.base,
                            approved_unknown_hashes=approved)
        self.assertEqual((self.runtime/name).read_bytes(),b"report-v1")
        self.assert_protected()

    def test_standard_launcher_single_consent_for_code_and_reference_report(self):
        changes=("frontend/cad.js","ml/r12_research/report.json")
        original={}
        for name in changes:
            old=("existing "+name).encode()
            (self.runtime/name).write_bytes(old)
            original[name]=old
        with (patch.dict(os.environ, {"LOCALAPPDATA":str(self.base),
                                      "GF_OFFER_MIGRATION":"1"}),
              patch.object(bootstrap,"DirectoryBundle",return_value=self.package()),
              patch.object(bootstrap,"audit_runtime",return_value={"ready_for_update":True}),
              patch.object(bootstrap,"audit_backend_import_contract",return_value={"compatible":True}),
              patch.object(bootstrap,"wait_for_port_release",return_value=True),
              patch.object(bootstrap,"_choose_python_without_installed_app",
                           return_value=(Path(sys.executable),[])),
              patch.object(bootstrap,"check_mesh_series_runtime",return_value=True),
              patch("builtins.input",return_value="MIGRATE CODE") as consent,
              patch.object(bootstrap.subprocess,"run",return_value=SimpleNamespace(
                   returncode=0,stdout='{"capabilities":{}}',stderr="")),
              patch.object(bootstrap,"DIAG",self.base/"diagnostics")):
            self.assertEqual(bootstrap.main(["bootstrap.py","--install-only"]),0)
            consent.assert_called_once()
        for name in changes:
            self.assertEqual((self.runtime/name).read_bytes(),self.new[name])
            backup=list((self.root/"backups").glob("*/"+name))
            self.assertEqual(len(backup),1)
            self.assertEqual(backup[0].read_bytes(),original[name])
        self.assert_protected()

    def test_repair_launcher_rejects_unapproved_code_without_stopping_running_app(self):
        edited="frontend/cad.js"
        (self.runtime/edited).write_bytes(b"unexpected user edition")
        with (patch.dict(os.environ, {"LOCALAPPDATA":str(self.base)}),
              patch.object(bootstrap,"DirectoryBundle",return_value=self.package()),
              patch.object(bootstrap,"audit_runtime",return_value={"ready_for_update":True}),
              patch.object(bootstrap,"audit_backend_import_contract",return_value={"compatible":True}),
              patch.object(bootstrap,"wait_for_port_release") as stop,
              patch.object(bootstrap,"DIAG",self.base/"diagnostics")):
            self.assertEqual(bootstrap.main(["bootstrap.py","--install-only"]),25)
            stop.assert_not_called()
        self.assertEqual((self.runtime/edited).read_bytes(),b"unexpected user edition")
        self.assert_protected()

    def test_repair_launcher_confirms_unknown_code_and_keeps_original_backup(self):
        edited="frontend/cad.js"
        previous=b"private local version saved for rollback"
        (self.runtime/edited).write_bytes(previous)
        with (patch.dict(os.environ, {"LOCALAPPDATA":str(self.base)}),
              patch.object(bootstrap,"DirectoryBundle",return_value=self.package()),
              patch.object(bootstrap,"audit_runtime",return_value={"ready_for_update":True}),
              patch.object(bootstrap,"audit_backend_import_contract",return_value={"compatible":True}),
              patch.object(bootstrap,"wait_for_port_release",return_value=True),
              patch.object(bootstrap,"_choose_python_without_installed_app",
                           return_value=(Path(sys.executable),[])),
              patch.object(bootstrap,"check_mesh_series_runtime",return_value=True),
              patch("builtins.input",return_value="MIGRATE CODE") as consent,
              patch.object(bootstrap.subprocess,"run",return_value=SimpleNamespace(
                 returncode=0,stdout='{"capabilities":{}}',stderr="")),
              patch.object(bootstrap,"_start_backend") as started,
              patch.object(bootstrap,"DIAG",self.base/"diagnostics")):
            self.assertEqual(bootstrap.main(["bootstrap.py","--migrate-local-code","--install-only"]),0)
            consent.assert_called_once()
            started.assert_not_called()
        self.assertEqual((self.runtime/edited).read_bytes(),self.new[edited])
        backups=list((self.root/"backups").glob("*/frontend/cad.js"))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_bytes(),previous)
        self.assert_protected()

    def test_standard_start_offers_safe_code_repair_without_second_launcher(self):
        name="frontend/cad.js"
        original=b"unknown previous frontend source"
        (self.runtime/name).write_bytes(original)
        with (patch.dict(os.environ, {"LOCALAPPDATA":str(self.base),
                                      "GF_OFFER_MIGRATION":"1"}),
              patch.object(bootstrap,"DirectoryBundle",return_value=self.package()),
              patch.object(bootstrap,"audit_runtime",return_value={"ready_for_update":True}),
              patch.object(bootstrap,"audit_backend_import_contract",return_value={"compatible":True}),
              patch.object(bootstrap,"wait_for_port_release",return_value=True),
              patch.object(bootstrap,"_choose_python_without_installed_app",
                           return_value=(Path(sys.executable),[])),
              patch.object(bootstrap,"check_mesh_series_runtime",return_value=True),
              patch("builtins.input",return_value="MIGRATE CODE") as consent,
              patch.object(bootstrap.subprocess,"run",return_value=SimpleNamespace(
                  returncode=0,stdout='{"capabilities":{}}',stderr="")),
              patch.object(bootstrap,"DIAG",self.base/"diagnostics")):
            self.assertEqual(bootstrap.main(["bootstrap.py","--install-only"]),0)
            consent.assert_called_once()
        self.assertEqual((self.runtime/name).read_bytes(),self.new[name])
        backups=list((self.root/"backups").glob("*/frontend/cad.js"))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_bytes(),original)
        self.assert_protected()

    def test_standard_start_declining_repair_does_not_stop_existing_server(self):
        name="frontend/cad.js"
        original=b"keep my custom revision"
        (self.runtime/name).write_bytes(original)
        with (patch.dict(os.environ, {"LOCALAPPDATA":str(self.base),
                                      "GF_OFFER_MIGRATION":"1"}),
              patch.object(bootstrap,"DirectoryBundle",return_value=self.package()),
              patch.object(bootstrap,"audit_runtime",return_value={"ready_for_update":True}),
              patch.object(bootstrap,"audit_backend_import_contract",return_value={"compatible":True}),
              patch.object(bootstrap,"wait_for_port_release") as stop,
              patch.object(bootstrap,"_choose_python_without_installed_app") as probe,
              patch("builtins.input",return_value="NO"),
              patch.object(bootstrap,"DIAG",self.base/"diagnostics")):
            self.assertEqual(bootstrap.main(["bootstrap.py","--install-only"]),28)
            stop.assert_not_called()
            probe.assert_not_called()
        self.assertEqual((self.runtime/name).read_bytes(),original)
        self.assert_protected()

    def test_python_failure_never_stops_running_existing_geofield(self):
        with (patch.dict(os.environ, {"LOCALAPPDATA":str(self.base)}),
              patch.object(bootstrap,"DirectoryBundle",return_value=self.package()),
              patch.object(bootstrap,"audit_runtime",return_value={"ready_for_update":True}),
              patch.object(bootstrap,"audit_backend_import_contract",return_value={"compatible":True}),
              patch.object(bootstrap,"check_mesh_series_runtime",return_value=True),
              patch.object(bootstrap,"_choose_server",side_effect=RuntimeError("old engine unavailable")),
              patch.object(bootstrap,"_choose_python_without_installed_app",
                           side_effect=RuntimeError("no safe python")),
              patch.object(bootstrap,"wait_for_port_release") as stop,
              patch.object(bootstrap,"DIAG",self.base/"diagnostics")):
            with self.assertRaisesRegex(RuntimeError,"no safe python"):
                bootstrap.main(["bootstrap.py","--install-only"])
            stop.assert_not_called()
        self.assert_originals()

    def test_safe_interpreter_probe_does_not_run_user_backend(self):
        calls=[]
        def synthetic(cmd,**kwargs):
            calls.append(list(cmd))
            return SimpleNamespace(returncode=0,
                stdout=json.dumps({"python":[3,12,0],"modules":{
                    "cadquery":True,"OCP":True,"gmsh":True}}),stderr="")
        with (patch.object(bootstrap,"_candidates",return_value=[Path(sys.executable)]),
              patch.object(bootstrap.subprocess,"run",side_effect=synthetic)):
            choice,_=bootstrap._choose_python_without_installed_app()
        self.assertEqual(choice,Path(sys.executable))
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][1:3],["-I","-c"])
        self.assertNotIn("GeoField_CAD_Analysis.py"," ".join(calls[0]))
        self.assert_protected()

    def test_explicit_local_repair_blocks_changed_sha_or_unlisted_model(self):
        name="frontend/cad.js"
        (self.runtime/name).write_bytes(b"local revision")
        approved={name:installer.sha(b"local revision")}
        (self.runtime/name).write_bytes(b"changed during approval")
        with self.assertRaisesRegex(RuntimeError,"Refusing to overwrite unknown source"):
            installer.apply(self.package(),localappdata=self.base,
                            approved_unknown_hashes=approved)
        with self.assertRaisesRegex(RuntimeError,"Invalid explicit local source approval map"):
            installer.apply(self.package(),localappdata=self.base,
                            approved_unknown_hashes={"ml/r12_research/research_model.joblib":"a"*64})
        self.assertEqual((self.runtime/name).read_bytes(),b"changed during approval")
        self.assert_protected()

    def test_missing_runtime_aborts_without_creating_engine(self):
        (self.runtime / "engine_runtime.py").unlink()
        with self.assertRaisesRegex(RuntimeError, "not the matching GeoField runtime"):
            self.install()
        self.assertFalse((self.runtime / "engine_runtime.py").exists())
        for name, data in self.old.items():
            self.assertEqual((self.runtime / name).read_bytes(), data)

    def test_failed_mid_install_restores_all_code_and_evidence(self):
        original_replace = installer.os.replace
        injected = []
        def interrupt(src, dst):
            target = Path(dst)
            if (target == self.runtime / "frontend" / "cad.js" and
                    ".tmp" in Path(src).name and not injected):
                injected.append(str(dst))
                raise OSError("synthetic power-loss during replacement")
            return original_replace(src, dst)
        with patch.object(installer.os, "replace", side_effect=interrupt):
            with self.assertRaisesRegex(OSError, "synthetic power-loss"):
                self.install()
        self.assertEqual(len(injected), 1)
        self.assert_originals()
        journals = list((self.root / "backups").glob("*/install_journal.json"))
        self.assertEqual(len(journals), 1)
        self.assertEqual(json.loads(journals[0].read_text())["state"], "recovered")

    def test_manual_rollback_refuses_modified_updated_file(self):
        receipt = {}
        self.install(receipt)
        changed = receipt["changed"]
        suspect = self.runtime / changed[-1]["path"]
        suspect.write_bytes(b"unexpected-edit-after-install")
        first = self.runtime / changed[0]["path"]
        first_before = first.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "changed since upgrade"):
            installer.rollback_install(receipt)
        self.assertEqual(first.read_bytes(), first_before)
        self.assertEqual(suspect.read_bytes(), b"unexpected-edit-after-install")
        self.assert_protected()

    def _journal(self, tampered=False):
        names = [name for name in self.meta if self.old[name] != self.new[name]][:2]
        folder = self.root / "backups" / "r12-research-integrated-synthetic"
        folder.mkdir(parents=True)
        entries = []
        for index, name in enumerate(names):
            original_backup = folder / name
            original_backup.parent.mkdir(parents=True, exist_ok=True)
            original_backup.write_bytes(self.old[name])
            if index == 0:
                (self.runtime / name).write_bytes(self.new[name])
            elif tampered:
                (self.runtime / name).write_bytes(b"unrecognized-edit")
            entries.append({"path":name, "before_sha256":installer.sha(self.old[name]),
                            "installed_sha256":installer.sha(self.new[name])})
        journal = folder / "install_journal.json"
        journal.write_text(json.dumps({"state":"pending", "runtime_id":RUNTIME_ID,
                                       "entries":entries}), encoding="utf-8")
        return names, journal

    def test_interrupted_install_journal_recovers_old_verified_code(self):
        names, journal = self._journal()
        self.assertEqual(installer.recover_interrupted_install(self.root, self.runtime), 1)
        for name in names:
            self.assertEqual((self.runtime / name).read_bytes(), self.old[name])
        self.assertEqual(json.loads(journal.read_text())["state"], "recovered")
        self.assertEqual(installer.recover_interrupted_install(self.root, self.runtime), 0)
        self.assert_originals()

    def test_corrupt_journal_member_blocks_all_recovery(self):
        names, journal = self._journal(tampered=True)
        first = (self.runtime / names[0]).read_bytes()
        with self.assertRaisesRegex(RuntimeError, "unrecognized edited file"):
            installer.recover_interrupted_install(self.root, self.runtime)
        self.assertEqual((self.runtime / names[0]).read_bytes(), first)
        self.assertEqual(json.loads(journal.read_text())["state"], "pending")
        self.assert_protected()

    def test_bootstrap_failed_backend_check_rolls_back(self):
        with (patch.dict(os.environ, {"LOCALAPPDATA":str(self.base)}),
              patch.object(bootstrap,"DirectoryBundle",return_value=self.package()),
              patch.object(bootstrap,"wait_for_port_release",return_value=True),
              patch.object(bootstrap,"_choose_server",return_value=(Path(sys.executable),[])),
              patch.object(bootstrap,"check_mesh_series_runtime",return_value=True),
              patch.object(bootstrap,"audit_runtime",
                           return_value={"ready_for_update":True}),
              # This test exercises POST-install rollback, not the new
              # separate pre-install static API contract. The real contract
              # is covered in test_runtime_source_api_contract.py.
              patch.object(bootstrap,"audit_backend_import_contract",
                           return_value={"compatible":True}),
              patch.object(bootstrap.subprocess,"run",return_value=SimpleNamespace(
                  returncode=1, stdout="", stderr="synthetic failed backend --check")),
              patch.object(bootstrap,"_start_backend") as launched,
              patch.object(bootstrap,"DIAG",self.base / "test_diagnostics")):
            self.assertEqual(bootstrap.main(["bootstrap.py","--install-only"]), 32)
            launched.assert_not_called()
        self.assert_originals()
        journals = list((self.root / "backups").glob("*/install_journal.json"))
        self.assertEqual(len(journals),1)
        self.assertEqual(json.loads(journals[0].read_text())["state"], "reverted")

    def test_rollback_rejects_unapproved_receipt_target(self):
        receipt = {}
        self.install(receipt)
        manipulated = dict(receipt)
        manipulated["changed"] = [dict(item) for item in receipt["changed"]]
        manipulated["changed"][-1]["path"] = "CAD/L_bracket.step"
        first = self.runtime / receipt["changed"][0]["path"]
        original = first.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "Unsafe rollback relative path"):
            installer.rollback_install(manipulated)
        self.assertEqual(first.read_bytes(), original)
        self.assert_protected()

    def test_rollback_rejects_symlinked_install_parent(self):
        receipt = {}
        self.install(receipt)
        original_link_check = Path.is_symlink
        target_parent = self.runtime / "frontend"
        def pretend_symlink(p):
            return p == target_parent or original_link_check(p)
        first = self.runtime / receipt["changed"][0]["path"]
        before = first.read_bytes()
        with patch.object(Path, "is_symlink", pretend_symlink):
            with self.assertRaisesRegex(RuntimeError, "contains symlink"):
                installer.rollback_install(receipt)
        self.assertEqual(first.read_bytes(), before)
        self.assert_protected()

    def test_rollback_rejects_symlinked_backup_parent(self):
        receipt = {}
        self.install(receipt)
        original_link_check = Path.is_symlink
        backup_parent = Path(receipt["backup"]) / "frontend"
        def pretend_symlink(p):
            return p == backup_parent or original_link_check(p)
        first = self.runtime / receipt["changed"][0]["path"]
        before = first.read_bytes()
        with patch.object(Path, "is_symlink", pretend_symlink):
            with self.assertRaisesRegex(RuntimeError, "backup missing or linked"):
                installer.rollback_install(receipt)
        self.assertEqual(first.read_bytes(), before)
        self.assert_protected()

    def test_interrupted_recovery_rejects_linked_backup_folder(self):
        names, journal = self._journal()
        first = self.runtime / names[0]
        previous = first.read_bytes()
        folder = journal.parent
        original_link_check = Path.is_symlink
        def pretend_symlink(p):
            return p == folder or original_link_check(p)
        with patch.object(Path, "is_symlink", pretend_symlink):
            with self.assertRaisesRegex(RuntimeError, "directory is a symlink"):
                installer.recover_interrupted_install(self.root, self.runtime)
        self.assertEqual(first.read_bytes(), previous)
        self.assertEqual(json.loads(journal.read_text())["state"], "pending")
        self.assert_protected()

    def test_cmd_guard_checks_hashes_before_bootstrap(self):
        script = (ROOT / "GeoField_Start.cmd").read_text(encoding="utf-8")
        verification = script.index("verify_package.py")
        launch = script.index("bootstrap.py")
        self.assertIn("if errorlevel 1 goto :invalid", script)
        self.assertIn('"%GF_PY%" -u "%GF_PACKAGE%verify_package.py"', script)
        self.assertIn('"%GF_PY%" -u "%GF_PACKAGE%bootstrap.py" %*', script)
        self.assertIn("if not defined LOCALAPPDATA goto :no_local", script)
        self.assertNotIn("taskkill /f", script.lower())
        self.assertLess(verification, len(script))
        self.assertLess(launch, len(script))

if __name__ == "__main__":
    unittest.main()
