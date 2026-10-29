"""P5 Windows: read-only compatibility audit must not claim ready with missing APIs.

Runs actual bootstrap.main with synthetic static audit results. No installed
GeoField, user engineering data, port operations or external network is used.
"""
from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))
import bootstrap


class ReadOnlyCompatibilityGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="geofield-p5-compat-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.user_marker = self.root / "original_L_bracket.step"
        self.user_marker.write_bytes(b"KEEP ORIGINAL STEP UNTOUCHED")

    def check(self, *, hashes=True, engine=True, runtime=True, imports=True):
        compat = {"safe_to_install": hashes,
                  "blocking_files": [] if hashes else ["frontend/cad.js"],
                  "file_versions": {} if hashes else {
                      "frontend/cad.js": {"status": "unrecognized_local_source",
                                          "installed_sha256": "a" * 64}},
                  "explicit_code_migration_possible": not hashes,
                  "explicit_code_migration_files": [] if hashes else ["frontend/cad.js"],
                  "explicit_reference_report_migration_files": []}
        output = io.StringIO()
        with (patch.dict(os.environ, {"LOCALAPPDATA": str(self.root)}),
              patch.object(bootstrap, "DirectoryBundle", return_value=object()),
              patch.object(bootstrap, "verify_bundle",
                           return_value={"runtime_id": "8a9ac53a821a0eb5"}),
              patch.object(bootstrap, "assess_compatibility", return_value=compat),
              patch.object(bootstrap, "write_compatibility_report") as saved,
              patch.object(bootstrap, "audit_engine_runtime_contract",
                           return_value={"compatible": engine, "missing_exports": []}),
              patch.object(bootstrap, "audit_runtime",
                           return_value={"ready_for_update": runtime}),
              patch.object(bootstrap, "audit_backend_import_contract",
                           return_value={"compatible": imports}),
              patch.object(bootstrap, "wait_for_port_release") as port,
              patch.object(bootstrap, "apply") as install,
              patch("builtins.input") as consent,
              patch.object(bootstrap, "emit") as emit,
              contextlib.redirect_stdout(output)):
            code = bootstrap.main(["bootstrap.py", "--audit-compatibility"])
            port.assert_not_called()
            install.assert_not_called()
            consent.assert_not_called()
            saved.assert_called_once()
            self.assertEqual(saved.call_args.args[0]["engine_api_contract"]["compatible"], engine)
            self.assertEqual(saved.call_args.args[0]["source_api_contract"]["compatible"], imports)
            # This diagnostic emits its normal STEP 1/5 log line, but
            # performs no source migration, port stop or solver operation.
            emit.assert_called_once()
        self.assertEqual(self.user_marker.read_bytes(), b"KEEP ORIGINAL STEP UNTOUCHED")
        return code, output.getvalue()

    def test_all_static_contracts_pass_returns_source_only_ready(self):
        code, stdout = self.check()
        self.assertEqual(code, 0)
        self.assertIn("static API names passed", stdout)
        self.assertIn("Windows operation remain unverified", stdout)

    def test_engine_exports_missing_never_returns_ready(self):
        code, stdout = self.check(engine=False)
        self.assertEqual(code, 26)
        self.assertIn("AUDIT BLOCKED", stdout)
        self.assertNotIn("[READY]", stdout)

    def test_required_runtime_modules_missing_never_returns_ready(self):
        code, stdout = self.check(runtime=False)
        self.assertEqual(code, 27)
        self.assertNotIn("[READY]", stdout)

    def test_installed_module_import_contract_missing_never_returns_ready(self):
        code, stdout = self.check(imports=False)
        self.assertEqual(code, 27)
        self.assertNotIn("[READY]", stdout)

    def test_unknown_hashes_remain_blocked_even_if_apis_pass(self):
        code, stdout = self.check(hashes=False)
        self.assertEqual(code, 25)
        self.assertIn("Source hashes differ", stdout)
        self.assertNotIn("[READY]", stdout)


if __name__ == "__main__":
    unittest.main()
