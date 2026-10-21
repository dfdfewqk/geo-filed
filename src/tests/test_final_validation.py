"""Final-candidate verification. Simulated states, never fictitious CalculiX runs."""
import ast
import copy
import hashlib
import json
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'payload/GeoField_CAD_Analysis.py').read_text('utf8')
FRONTEND=(ROOT/'payload/frontend/cad.js').read_text('utf8')

class MeshSeriesFailureStates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mod=ast.parse(SOURCE)
        funcs=[n for n in mod.body if isinstance(n,ast.FunctionDef) and n.name=='r1213_mesh_series_verified_public']
        assert len(funcs)==1
        cls.scope={'public_state':lambda st:copy.deepcopy(st),'sqlite3':sqlite3}
        exec(compile(ast.Module(body=funcs,type_ignores=[]),'actual-GeoField-API','exec'),cls.scope)
        cls.check=staticmethod(cls.scope['r1213_mesh_series_verified_public'])
    def setUp(self):
        self.ids=['a'*32,'b'*32,'c'*32]
        self.sizes=[4.2,3.0,2.25]
        self.study={'id':'d'*32,'cad_sha256':'e'*64,'status':'complete','sizes_mm':self.sizes.copy(),
                    'analysis_snapshot_ids':self.ids.copy(),'mesh_study_verified':True,
                    'study_analysis':{'stale':'data'},'completed':3,'total':3}
        self.analysis={'status':'verified_three_mesh_sensitivity_only','runs_coarse_to_fine':[
            {'cad_sha256':'e'*64,'snapshot_id':sid,'mesh_target_mm':sz}
            for sid,sz in zip(self.ids,self.sizes)]}
        self.scope['r1213_verified_mesh_spatial_study']=lambda ids:self.analysis
    def test_verified_result_remains_complete(self):
        out=self.check(self.study)
        self.assertEqual(out['status'],'complete');self.assertTrue(out['mesh_study_verified'])
    def test_missing_archive_is_explicit_failure(self):
        self.study['analysis_snapshot_ids'].pop();original=copy.deepcopy(self.study)
        out=self.check(self.study)
        self.assertEqual(out['status'],'verification_failed');self.assertFalse(out['mesh_study_verified'])
        self.assertIsNone(out['study_analysis']);self.assertEqual(out['completed'],3)
        self.assertEqual(self.study,original)
    def test_corrupt_evidence_is_explicit_failure(self):
        def invalid(_ids):raise ValueError('FRD 원본 손상')
        self.scope['r1213_verified_mesh_spatial_study']=invalid
        out=self.check(self.study)
        self.assertEqual(out['status'],'verification_failed');self.assertIn('FRD',out['verification_warning'])
        self.assertIsNone(out['study_analysis'])
    def test_other_study_evidence_is_not_accepted(self):
        self.analysis['runs_coarse_to_fine'][0]['snapshot_id']='f'*32
        out=self.check(self.study)
        self.assertEqual(out['status'],'verification_failed');self.assertFalse(out['mesh_study_verified'])
    def test_interrupted_study_stays_interrupted(self):
        self.study['status']='interrupted'
        out=self.check(self.study)
        self.assertEqual(out['status'],'interrupted');self.assertFalse(out['mesh_study_verified'])

class FrontendFailureState(unittest.TestCase):
    def test_fail_closed_status_is_terminal_and_reported(self):
        self.assertIn("'failed','verification_failed'].includes(state.status)",FRONTEND)
        self.assertIn("state.status==='verification_failed'",FRONTEND)
        self.assertIn('[결과 검증 실패]',FRONTEND)
    def test_frontend_actual_handler_recognizes_failure_without_reporting_convergence(self):
        snippet=FRONTEND.split("$('feaMeshSeriesStartBtn').onclick=async()=>{",1)[1].split("$('feaMeshSeriesCancelBtn').onclick=async()=>{",1)[0]
        handler="$('feaMeshSeriesStartBtn').onclick=async()=>{"+snippet
        node=r'''const vm=require('vm'),assert=require('node:assert/strict');const fn=process.argv[1];
let btn={},calls=0; const $=id=>(btn[id]??={disabled:false,textContent:''});
const ctx={ $,file:{},current:{sha256:'x'},jobId:'j',feaPrepared:true,
feaPreparedCaseSha:'y', meshSeriesPlan:{cad_sha256:'x',base_case_sha256:'y'},
window:{confirm:()=>true},meshSeriesReset:()=>{}, sleep:async()=>{},
fetch:async()=>({ok:true,json:async()=>({id:'s'})}),
get:async()=>{calls++;return {status:'verification_failed',completed:3,total:3,current_index:2,
message:'unverified',analysis_snapshot_ids:['1','2','3'],verification_warning:'FRD mismatch'}},
gfMeshSensitivityLabel:()=>'',gfMeshSpatialEvidence:()=>'',console};
vm.runInNewContext('let meshSeriesId=null,meshSeriesBusy=false;'+fn,ctx);
btn.feaMeshSeriesStartBtn.onclick().then(()=>{
 assert.equal(calls,1);assert.equal(btn.feaMeshSeriesCancelBtn.disabled,true);
 assert.match(btn.feaMeshSeriesProgress.textContent,/FRD mismatch/);
 assert.match(btn.feaMeshSeriesProgress.textContent,/결과 검증 실패/);
 assert.doesNotMatch(btn.feaMeshSeriesProgress.textContent,/\[메시 진단\]/);
 console.log('VALIDATION_FAILURE_UI_PASS');}).catch(e=>{console.error(e);process.exit(1)});'''
        r=subprocess.run(['node','-e',node,handler],capture_output=True,text=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)

class UpgradePreservesEvidence(unittest.TestCase):
    def test_qa11_to_final_candidate_update_restart_and_rollback(self):
        import installer
        old=Path('/mnt/data/GeoField_R12_13_QA11_계획조건고정_실행전검증_통합보관본.zip')
        with zipfile.ZipFile(old) as z, tempfile.TemporaryDirectory() as tmp:
            runtime=Path(tmp)/'GeoFieldCAD/onefile_runtime/8a9ac53a821a0eb5'
            runtime.mkdir(parents=True)
            for name in json.loads((ROOT/'manifest.json').read_text())['files']:
                f=runtime/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(z.read('payload/'+name))
            (runtime/'engine_runtime.py').write_text('existing engine')
            protected={n:b'evidence:'+n.encode() for n in
                       ('CAD/L_bracket.step','history/geofield.sqlite3','fea_runs/real/geofield_case.inp',
                        'fea_runs/real/geofield_case.sta','fea_runs/real/geofield_case.frd','ml/research_model.joblib')}
            for name,data in protected.items():
                f=runtime/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data)
            receipt={}
            self.assertEqual(installer.apply(installer.DirectoryBundle(ROOT),localappdata=tmp,receipt=receipt),0)
            self.assertEqual([i['path'] for i in receipt['changed']],['GeoField_CAD_Analysis.py','frontend/cad.js'])
            self.assertEqual(installer.apply(installer.DirectoryBundle(ROOT),localappdata=tmp),0)
            for name,data in protected.items():self.assertEqual((runtime/name).read_bytes(),data)
            self.assertEqual(installer.rollback_install(receipt),2)
            for name,data in protected.items():self.assertEqual((runtime/name).read_bytes(),data)
            self.assertEqual((runtime/'frontend/cad.js').read_bytes(),z.read('payload/frontend/cad.js'))

if __name__=='__main__':unittest.main()
