"""Regression tests for local Windows runtime developer bridge.

No private source is imported, copied to GitHub, or executed in these tests.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import dev_runtime_bridge as bridge


class DevRuntimeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="geofield-readonly-bridge-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / "onefile_runtime" / bridge.RUNTIME_ID
        self.runtime.mkdir(parents=True)
        (self.runtime / "cad_common.py").write_text("def canonicalize(*a): return a\n", encoding="utf8")
        (self.runtime / "engine_runtime.py").write_text("def engine_python(*a): return {}\n", encoding="utf8")
        modules = patch.object(bridge, "EXISTING_REQUIRED", ("cad_common.py", "engine_runtime.py"))
        self.addCleanup(modules.stop)
        modules.start()
        self.runtime_status = patch.object(bridge, "audit_runtime", return_value={"ready_for_update": True})
        self.engine = patch.object(bridge, "audit_engine_runtime_contract", return_value={"compatible": True})
        self.contract = patch.object(bridge, "audit_backend_import_contract", return_value={"compatible": True})
        for item in (self.runtime_status, self.engine, self.contract):
            self.addCleanup(item.stop)
            item.start()

    def test_audit_never_launches_or_modifies_private_source(self):
        before = {n: (self.runtime / n).read_bytes() for n in bridge.EXISTING_REQUIRED}
        with patch.object(bridge.subprocess, "run", side_effect=AssertionError("no launch")):
            report = bridge.inspect(self.runtime)
        self.assertTrue(report["ready"])
        self.assertEqual(report["fingerprinted_module_count"], 2)
        self.assertEqual(before, {n: (self.runtime / n).read_bytes() for n in bridge.EXISTING_REQUIRED})

    def test_missing_runtime_is_fail_closed(self):
        self.assertFalse(bridge.inspect(self.root / "missing")["ready"])
        self.assertEqual(bridge.main(["--runtime", str(self.root / "missing")]), 24)

    def test_missing_file_prevents_ready(self):
        (self.runtime / "cad_common.py").unlink()
        with patch.object(bridge, "audit_runtime", return_value={"ready_for_update": False,
                                                                  "missing": ["cad_common.py"]}):
            report = bridge.inspect(self.runtime)
        self.assertFalse(report["ready"])
        self.assertIn("cad_common.py", report["missing"])

    def test_visible_but_unreadable_source_prevents_ready(self):
        with patch.object(bridge, "_readable_fingerprint", return_value=(False, "cad_common.py")):
            report = bridge.inspect(self.runtime)
        self.assertFalse(report["ready"])
        self.assertIn("cannot be read", report["error"])
        self.assertEqual(report["blocked_module"], "cad_common.py")

    def test_incompatible_static_contract_prevents_ready(self):
        with patch.object(bridge, "audit_backend_import_contract", return_value={"compatible": False,
                                                        "missing_exports": {"history_store.py": ["save"]}}):
            report = bridge.inspect(self.runtime)
        self.assertFalse(report["ready"])
        self.assertIn("history_store.py", report["missing_exports"])

    def test_choose_python_uses_explicit_interpreter_not_bare_python(self):
        exe = self.root / "python.exe"
        exe.touch()
        with patch.dict(os.environ, {"GEOFIELD_PYTHON": str(self.root / "missing.exe")}, clear=True):
            self.assertEqual(bridge.choose_python(self.root, str(exe)), exe.resolve())
            self.assertIsNone(bridge.choose_python(None))

    def test_backend_launch_order_keeps_source_ahead_of_installed_runtime(self):
        python = self.root / "python.exe"
        python.touch()
        captured = {}
        def runner(command, **kwargs):
            captured.update(command=command, **kwargs)
            return types.SimpleNamespace(returncode=0)
        with patch.object(bridge.subprocess, "run", side_effect=runner):
            self.assertEqual(bridge.run_backend(python, self.runtime, check=True), 0)
        self.assertEqual(captured["command"][-1], "--check")
        self.assertEqual(captured["env"]["PYTHONPATH"].split(os.pathsep)[:3],
                         [str(bridge.ROOT / "payload"), str(bridge.ROOT), str(self.runtime)])
        self.assertNotIn("shell", captured)

    def test_occupied_port_never_triggers_process_termination(self):
        python = self.root / "python.exe"
        python.touch()
        with patch.object(bridge.socket, "socket") as sock, patch.object(bridge.subprocess, "run", side_effect=AssertionError("launched")):
            sock.return_value.__enter__.return_value.connect_ex.return_value = 0
            with self.assertRaisesRegex(RuntimeError, "occupied"):
                bridge.run_backend(python, self.runtime, check=False)

    def test_main_audit_never_runs_the_backend(self):
        with patch.object(bridge.subprocess, "run", side_effect=AssertionError("launched")):
            self.assertEqual(bridge.main(["--runtime", str(self.runtime)]), 0)

    def test_windows_one_click_audit_does_not_launch_installer(self):
        script = (ROOT / "GeoField_Dev_Runtime_Check.cmd").read_text(encoding="utf-8")
        self.assertIn("dev_runtime_bridge.py", script)
        self.assertIn('set "GF_MODE=--audit"', script)
        self.assertIn("GEOFIELD_R12_PYTHON", script)
        self.assertNotIn("GeoField_Start.cmd", script)
        self.assertNotIn("bootstrap.py", script)
        self.assertNotIn("GeoField_Repair.cmd", script)
        self.assertNotIn("Stop-Process", script)
        self.assertNotIn("pip install", script)



    def test_source_checkout_start_cmd_blocks_before_verify_package(self):
        script = (ROOT / "GeoField_Start.cmd").read_text(encoding="utf-8")
        guard = 'if exist "%GF_PACKAGE%build_integration_candidate.py" if exist "%GF_PACKAGE%tests\\test_integration_candidate.py" goto :source_checkout'
        self.assertIn(guard, script)
        self.assertLess(script.index(guard), script.index('"%GF_PY%" -u "%GF_PACKAGE%verify_package.py"'))
        self.assertIn("[SOURCE CHECKOUT]", script)
        self.assertIn("GeoField_Dev_Runtime_Check.cmd", script)
        self.assertIn("exit /b 21", script)
        self.assertIn("Do NOT edit manifest.json", script)

    def test_raw_source_manifest_is_not_a_staged_release(self):
        import json
        from installer import ALLOWED_TARGETS
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        # Historical repository manifest is a staging input, not the signed
        # generated 26-target candidate built by build_integration_candidate.py.
        self.assertNotEqual(set(manifest["files"]), set(ALLOWED_TARGETS))




if __name__ == "__main__":
    unittest.main()
