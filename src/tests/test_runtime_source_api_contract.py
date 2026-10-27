"""Tests: verify installed FEA/ML module export contracts before ANY Windows update.

Never import user's installed modules or modify protected CAD/SQLite/FRD.
"""
from pathlib import Path
import contextlib, io, json, os, sys, tempfile, unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bootstrap
import runtime_preflight as rp


class SourceImportContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='gf-module-api-')
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.runtime=self.folder/'GeoFieldCAD'/'onefile_runtime'/'8a9ac53a821a0eb5'
        self.runtime.mkdir(parents=True)
        self.candidate=self.folder/'candidate'
        self.candidate.mkdir()
        # This fixture models the actual installed-module dependencies of the
        # new backend. Nothing is imported or executed, even when malicious.
        (self.candidate/'GeoField_CAD_Analysis.py').write_text(
            'from history_store import save, read, search_page\n'
            'from fea_restore import restore_payload\n'
            'from fea_unified_report import build as build_report, html_report\n'
            'from ml.brepmfr_worker import KNOWN_CKPT\n'
            'from engine_runtime import engine_python, prepare_python_environment\n',
            encoding='utf8')
        (self.candidate/'fea_solver.py').write_text(
            'from engine_runtime import gmsh_python_status\n'
            'from gravity_evidence import gravity_spec\n',encoding='utf8')
        self.modules={
            'history_store.py':'def save(): pass\ndef read(): pass\ndef search_page(): pass\n',
            'fea_restore.py':'def restore_payload(): pass\n',
            'fea_unified_report.py':'def build(): pass\ndef html_report(): pass\n',
            'ml/brepmfr_worker.py':'KNOWN_CKPT="sha"\n',
            'engine_runtime.py':('REQUIRED_ML=()\nREQUIRED_GMSH=()\n'
                                 'def engine_python(): pass\n'
                                 'def prepare_python_environment(): pass\n'
                                 'def gmsh_python_status(): pass\n'),
            'gravity_evidence.py':'def gravity_spec(): pass\n'}
        for name,text in self.modules.items():
            p=self.runtime/name
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(text,encoding='utf8')
        for name in rp.EXISTING_REQUIRED+rp.UPDATABLE_REQUIRED_BEFORE_INSTALL:
            p=self.runtime/name
            if not p.exists():
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text('# present legacy module\n',encoding='utf8')
        self.personal={
            'cad/owned.step':b'owner STEP must never be read or modified',
            'history/research.sqlite3':b'owner SQLite bytes must never change',
            'fea/solver.frd':b'owner FRD must never change'}
        for name,value in self.personal.items():
            p=self.runtime/name
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(value)
    def assert_no_data_change(self):
        for name,value in self.personal.items():
            self.assertEqual((self.runtime/name).read_bytes(),value)

    def test_good_static_api_only_not_a_fake_real_solver_success(self):
        r=rp.audit_backend_import_contract(self.runtime,self.candidate)
        self.assertTrue(r['compatible'],r)
        self.assertTrue(r['read_only'])
        self.assertFalse(r['installed_code_executed'])
        self.assertFalse(r['solver_executed'])
        self.assertFalse(r['verified_imports_or_solver'])
        self.assertIn('history_store.py',r['required_modules'])
        self.assertEqual(r['missing_exports'],{})
        self.assert_no_data_change()

    def test_existing_filename_but_missing_archive_restore_symbol_fails(self):
        (self.runtime/'fea_restore.py').write_text('def fake_restore(): pass\n',encoding='utf8')
        r=rp.audit_backend_import_contract(self.runtime,self.candidate)
        self.assertFalse(r['compatible'])
        self.assertEqual(r['missing_exports'],{'fea_restore.py':['restore_payload']})
        self.assert_no_data_change()

    def test_older_engine_runtime_api_is_rejected(self):
        (self.runtime/'engine_runtime.py').write_text(
            'def engine_python(): pass\ndef gmsh_python_status(): pass\n',encoding='utf8')
        r=rp.audit_backend_import_contract(self.runtime,self.candidate)
        self.assertFalse(r['compatible'])
        self.assertEqual(r['missing_exports'].get('engine_runtime.py'),['prepare_python_environment'])
        self.assert_no_data_change()

    def test_symlink_or_invalid_python_is_not_trusted(self):
        (self.runtime/'fea_restore.py').write_text('raise SyntaxError(\n',encoding='utf8')
        r=rp.audit_backend_import_contract(self.runtime,self.candidate)
        self.assertFalse(r['compatible'])
        self.assertIn('fea_restore.py',r['missing_or_invalid_modules'])
        self.assert_no_data_change()

    def test_invalid_staged_backend_never_executes_user_sources(self):
        (self.candidate/'GeoField_CAD_Analysis.py').write_text('from fea_restore import (\n',encoding='utf8')
        r=rp.audit_backend_import_contract(self.runtime,self.candidate)
        self.assertFalse(r['compatible'])
        self.assertEqual(r['reason'],'candidate_syntax_or_read_error')
        self.assert_no_data_change()

    def test_installer_refuses_missing_fea_restore_api_before_port_stop(self):
        (self.runtime/'fea_restore.py').write_text('def old_restore(): pass\n',encoding='utf8')
        report=rp.audit_backend_import_contract(self.runtime,self.candidate)
        self.assertFalse(report['compatible'])
        output=io.StringIO()
        # Override only the source location; use actual freshly built API
        # fixture, never substitute a fake "pass" response for it.
        with (patch.dict(os.environ,{'LOCALAPPDATA':str(self.folder),
                                    'GF_DIAG':str(self.folder/'versions')}),
              patch.object(bootstrap,'verify_bundle',
                           return_value={'runtime_id':self.runtime.name}),
              patch.object(bootstrap,'assess_compatibility',
                           return_value={'safe_to_install':True,'blocking_files':[]}),
              patch.object(bootstrap,'write_compatibility_report',return_value=None),
              patch.object(bootstrap,'audit_backend_import_contract',
                           side_effect=lambda r,p:rp.audit_backend_import_contract(r,self.candidate)),
              patch.object(bootstrap,'wait_for_port_release',
                           side_effect=AssertionError('port must not be interrupted')),
              patch.object(bootstrap,'apply',
                           side_effect=AssertionError('installer must not run')),
              contextlib.redirect_stdout(output)):
            result=bootstrap.main(['bootstrap.py','--install-only'])
        self.assertEqual(result,27)
        self.assertIn('fea_restore.py',output.getvalue())
        self.assertIn('restore_payload',output.getvalue())
        self.assert_no_data_change()


if __name__=='__main__':unittest.main()
