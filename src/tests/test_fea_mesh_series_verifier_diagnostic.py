"""Verify a real-solver success followed by untrusted C3D4/C3D10 re-verification
never becomes a published engineering result. No actual CalculiX is mocked as proven.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'fea_mesh_series.py'
spec=importlib.util.spec_from_file_location('geofield_mesh_series_diagnostic_tests',SOURCE)
mesh=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mesh)
SHA='a'*64
CASE='b'*64

class VerifiedMeshFailureTests(unittest.TestCase):
    def test_rejected_private_verifier_preserves_solver_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            folder=root/'work'/'fea_runs'/'1'*32
            evidence=('geofield_case.inp','geofield_case.sta','geofield_case.frd')
            source_bytes={name:('SYNTHETIC TEST ONLY '+name).encode() for name in evidence}
            def fake_run(step,case,model,dest,ccx):
                for name,data in source_bytes.items():
                    (dest/name).write_bytes(data)
                return {'status':'solver_executed_result_parsed',
                        'cad_sha256':SHA,'case_sha256':CASE}
            def fake_verify(dest,case,sha):
                self.assertTrue(all((dest/name).is_file() for name in evidence))
                raise ValueError('C3D4 요소 형상 오류')
            solver=types.ModuleType('fea_solver')
            solver.run_real_fea=fake_run
            engine=types.ModuleType('engine_runtime')
            engine.prepare_python_environment=lambda exe:{}
            verifier=types.ModuleType('fea_previous_import')
            verifier.verify_directory=fake_verify
            case={'cad_sha256':SHA,'case_sha256':CASE,'mesh_request':{
                'element_type':'C3D10','traction_model':'straight_tri6_full_consistent'}}
            with patch.dict(sys.modules,{'fea_solver':solver,'engine_runtime':engine,
                                         'fea_previous_import':verifier}):
                with self.assertRaisesRegex(RuntimeError,'재검증 실패 \\(C3D10\\)'):
                    mesh.run_one(root,root/'input.step',case,{},folder,'ccx',
                                 {'ok':True,'path':sys.executable})
            self.assertEqual({name:(folder/name).read_bytes() for name in evidence},
                             source_bytes)
            self.assertEqual(json.loads((folder/'case.json').read_text())['case_sha256'],CASE)
            self.assertEqual(json.loads((folder/'result.json').read_text())['status'],
                             'solver_executed_result_parsed')
            diagnosis=json.loads((folder/'verification_diagnostic.json').read_text())
            self.assertEqual(diagnosis['phase'],'independent_inp_sta_frd_reverification')
            self.assertEqual(diagnosis['requested_element_type'],'C3D10')
            self.assertEqual(diagnosis['verification_error'],'C3D4 요소 형상 오류')
            self.assertTrue(all(diagnosis['files_present'].values()))
            self.assertTrue(diagnosis['solver_returned_result'])
            self.assertIn('검증 우회 금지',diagnosis['action'])

if __name__=='__main__':
    unittest.main()
