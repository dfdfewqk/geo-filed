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
