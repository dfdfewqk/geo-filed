"""Regression for user screenshot: old fea_compare lacks compare_d6 API.

Pre-upgrade API checker must judge verified candidate code in place of
explicitly migratable source files, while still judging PRIVATE modules from
the installed runtime. Full installer uses exact SHA approval, byte-for-byte
backup, post-install verification and rollback on failure.
Tests are offline; user STEP, SQLite, ML, solver and external API untouched.
"""
from __future__ import annotations
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bootstrap
from runtime_preflight import audit_backend_import_contract


class StagedCandidateAPIContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='gf-source-api-')
        self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name)
        self.installed=base/'onefile_runtime'/'8a9ac53a821a0eb5'
        self.staged=base/'verified_candidate'/'payload'
        self.installed.mkdir(parents=True)
        self.staged.mkdir(parents=True)
        (self.installed/'fea_compare.py').write_text(
            "def compare(*args):return None\n",encoding='utf-8')
        (self.installed/'fea_restore.py').write_text(
            "def restore_payload(*args):return None\n",encoding='utf-8')
        (self.staged/'fea_compare.py').write_text(
            "def compare(*args):return None\n"
            "def compare_d6_geometry_variant(*args):return None\n",
            encoding='utf-8')
        (self.staged/'GeoField_CAD_Analysis.py').write_text(
            "from fea_compare import compare as compare_verified_fea, "
            "compare_d6_geometry_variant as compare_d6_variant_fea\n",
            encoding='utf-8')
        (self.staged/'fea_solver.py').write_text(
            "from fea_restore import restore_payload\n",encoding='utf-8')

    def test_old_installed_api_fails_but_signed_planned_upgrade_passes(self):
        old=audit_backend_import_contract(self.installed,self.staged)
        self.assertFalse(old['compatible'])
        self.assertEqual(old['missing_exports'].get('fea_compare.py'),
                         ['compare_d6_geometry_variant'])
        upgraded=audit_backend_import_contract(
            self.installed,self.staged,planned_update_modules=('fea_compare.py',))
        self.assertTrue(upgraded['compatible'],upgraded)
        self.assertEqual(upgraded['api_source']['fea_compare.py'],
                         'verified_candidate_after_approved_install')
        self.assertEqual(upgraded['api_source']['fea_restore.py'],
                         'installed_unchanged')
        self.assertFalse(upgraded['installed_code_executed'])
        self.assertFalse(upgraded['solver_executed'])

    def test_missing_private_import_never_hidden_by_signed_candidate(self):
        (self.installed/'fea_restore.py').unlink()
        # Even if attacker puts a same-named file in candidate, it is not an
        # installer-allowed module. Non-updatable private runtime stays required.
        (self.staged/'fea_restore.py').write_text(
            'def restore_payload():pass\n',encoding='utf8')
        result=audit_backend_import_contract(
            self.installed,self.staged,planned_update_modules=('fea_compare.py',))
        self.assertFalse(result['compatible'])
        self.assertIn('fea_restore.py',result['missing_or_invalid_modules'])

    def test_old_module_absent_or_unsafe_cannot_be_prospectively_repaired(self):
        (self.installed/'fea_compare.py').unlink()
        result=audit_backend_import_contract(
            self.installed,self.staged,planned_update_modules=('fea_compare.py',))
        self.assertFalse(result['compatible'])
        self.assertIn('fea_compare.py',result['missing_or_invalid_modules'])

    def test_incompatible_candidate_cannot_hide_missing_d6_export(self):
        (self.staged/'fea_compare.py').write_text(
            'def compare(*args):pass\n',encoding='utf8')
        result=audit_backend_import_contract(
            self.installed,self.staged,planned_update_modules=('fea_compare.py',))
        self.assertFalse(result['compatible'])
        self.assertIn('compare_d6_geometry_variant',
                      result['missing_exports']['fea_compare.py'])


class MigrationBootstrapOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='gf-migration-flow-')
        self.addCleanup(self.tmp.cleanup)
        self.local=Path(self.tmp.name)
        self.sha={'fea_compare.py':'1'*64,
                  'frontend/cad.js':'2'*64,
                  'frontend/index.html':'3'*64}
        self.names=list(self.sha)
        self.manifest={'runtime_id':'8a9ac53a821a0eb5',
                       'files':{name:{} for name in self.names}}
        self.checks=[]

    def compatibility(self,root,manifest):
        # On success the newly installed code is verified with exact SHA.
        if self.after_install:
            return {'safe_to_install':True,
                    'explicit_code_migration_possible':False,
                    'blocking_files':[]}
        return {'safe_to_install':False,
                'explicit_code_migration_possible':True,
                'explicit_code_migration_files':list(self.names),
                'explicit_migration_files':list(self.names),
                'explicit_reference_report_migration_files':[],
                'blocking_files':list(self.names),
                'file_versions':{n:{'status':'unrecognized_local_source',
                                     'installed_sha256':self.sha[n]}
                                 for n in self.names}}

    def api(self,root,payload,**kwargs):
        planned=kwargs.get('planned_update_modules',())
        self.checks.append(tuple(planned))
        if not planned and not self.after_install:
            return {'compatible':False,
                    'missing_exports':{'fea_compare.py':['compare_d6_geometry_variant']},
                    'missing_or_invalid_modules':[],'api_source':{}}
        if planned:
            return {'compatible':True,'missing_exports':{},
                    'missing_or_invalid_modules':[],
                    'api_source':{'fea_compare.py':'verified_candidate_after_approved_install'}}
        return {'compatible':True,'missing_exports':{},
                'missing_or_invalid_modules':[],'api_source':{}}

    def run_case(self,answer):
        self.after_install=False
        self.checks=[]
        installed=self.local/'GeoFieldCAD'/'onefile_runtime'/'8a9ac53a821a0eb5'
        installed.mkdir(parents=True,exist_ok=True)
        applied=[]
        def apply_once(_bundle,**kwargs):
            applied.append(kwargs)
            self.after_install=True
            return 0
        with (
            patch.dict(os.environ,{
                'LOCALAPPDATA':str(self.local),
                'GF_DIAG':str(self.local/'readout'),
                'GF_OFFER_MIGRATION':'1'}),
            patch.object(bootstrap,'DIAG',self.local/'readout'),
            patch.object(bootstrap,'verify_bundle',return_value=self.manifest),
            patch.object(bootstrap,'assess_compatibility',side_effect=self.compatibility),
            patch.object(bootstrap,'audit_backend_import_contract',side_effect=self.api),
            patch.object(bootstrap,'audit_engine_runtime_contract',
                         return_value={'compatible':True,'missing_exports':[]}),
            patch.object(bootstrap,'audit_runtime',
                         return_value={'ready_for_update':True,'missing':[],
                                       'unsafe':[],'empty_or_unreadable':[]}),
            patch.object(bootstrap,'write_compatibility_report',
                         side_effect=lambda x,p:p),
            patch.object(bootstrap,'_choose_python_without_installed_app',
                         return_value=(Path(sys.executable),[])),
            patch.object(bootstrap,'check_mesh_series_runtime',return_value=True),
            patch.object(bootstrap,'wait_for_port_release',return_value=True),
            patch.object(bootstrap,'apply',side_effect=apply_once),
            patch.object(bootstrap,'subprocess') as process,
            patch('builtins.input',return_value=answer),
            redirect_stdout(io.StringIO()) as printed
        ):
            process.run.return_value=SimpleNamespace(
                returncode=0,stdout=json.dumps({'capabilities':{}}),stderr='')
            code=bootstrap.main(['bootstrap.py','--install-only'])
        return code,applied,printed.getvalue()

    def test_screenshot_three_file_mismatch_now_offers_and_installs_after_consent(self):
        code,applied,logs=self.run_case('MIGRATE CODE')
        self.assertEqual(code,0,logs)
        self.assertEqual(len(applied),1)
        self.assertEqual(applied[0]['approved_unknown_hashes'],self.sha)
        self.assertIn('[API UPGRADE]',logs)
        self.assertIn('[POST-INSTALL API]',logs)
        self.assertEqual(self.checks[0],())
        self.assertIn('fea_compare.py',self.checks[1])
        self.assertEqual(self.checks[-1],())

    def test_declining_repair_leaves_installed_source_untouched(self):
        code,applied,logs=self.run_case('NO')
        self.assertEqual(code,28,logs)
        self.assertEqual(applied,[])
        self.assertIn('[CANCELLED]',logs)

if __name__=='__main__':
    unittest.main()
