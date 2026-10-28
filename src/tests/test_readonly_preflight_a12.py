"""A12 preflight read-only contract and single-extract inventory.

Exercises production candidate staging indirectly through existing source-lock
unittest suite; avoids invoking Windows CMD on Linux or real user runtime.
"""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

class ReadOnlyPreflightA12(unittest.TestCase):
    def test_read_only_preflight_is_signed_and_only_audits(self):
        build=(ROOT/"build_integration_candidate.py").read_text(encoding="utf-8")
        cmd=(ROOT/"GeoField_Preflight_ReadOnly.cmd").read_text(encoding="utf-8")
        self.assertIn('"GeoField_Preflight_ReadOnly.cmd"',build)
        self.assertIn('"GeoField_Acceptance_Check.cmd"',build)
        self.assertIn('verify_package.py',cmd)
        self.assertIn('bootstrap.py',cmd)
        self.assertIn('--audit-runtime',cmd)
        self.assertIn('PYTHONDONTWRITEBYTECODE=1',cmd)
        self.assertIn('Do NOT start the update or solve',cmd)
        self.assertNotIn('GeoField_Start.cmd" --',cmd)
        self.assertNotIn('--migrate-local-code',cmd)
        self.assertNotIn('pip install',cmd)
        self.assertNotIn('curl ',cmd)
        self.assertNotIn('rm -',cmd)
        self.assertNotIn('del /',cmd)
        self.assertNotIn('taskkill',cmd)
        self.assertNotIn('ccx -',cmd)
    def test_audit_mode_returns_before_install_or_backend_start(self):
        bootstrap=(ROOT/"bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("audit_only = '--audit-runtime' in args[1:]",bootstrap)
        start=bootstrap.index("    if audit_only:")
        end=bootstrap.index("    if '--verify-only' in args[1:]:",start)
        region=bootstrap[start:end]
        self.assertIn('audit_runtime(root)',region)
        self.assertIn('audit_engine_runtime_contract(root)',region)
        self.assertIn('audit_backend_import_contract(root, package / \'payload\')',region)
        self.assertNotIn('installer.apply(',region)
        self.assertNotIn('stop_verified_old_geofield(',region)
        self.assertNotIn('_start_backend(',region)
        self.assertNotIn('subprocess.run(',region)
        self.assertIn('ready_for_compatible_update',region)
    def test_acceptance_rechecks_server_and_solver_summary_without_external_provider(self):
        source=(ROOT/"acceptance_probe.py").read_text(encoding="utf-8")
        self.assertIn('initial_instance=status.get("server_instance")',source)
        self.assertIn('final_status=fetch("/api/status")',source)
        self.assertIn('final_status.get("server_instance")==initial_instance',source)
        self.assertIn('latest=fetch("/api/results/summary/"+job)',source)
        self.assertIn('result.pop(key,None)',source)
        self.assertNotIn('https://',source)
        self.assertNotIn('X-GeoField-LLM-Opt-In',source)

if __name__=="__main__":
    unittest.main()
