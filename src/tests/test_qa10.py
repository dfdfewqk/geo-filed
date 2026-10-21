"""QA10: in-memory meshing job state inspection; no mock output is represented as CalculiX evidence."""
import hashlib, json, shutil, subprocess, tempfile, unittest, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
JS=(ROOT/'payload/frontend/cad.js').read_text(encoding='utf8')

class StatusPollingTests(unittest.TestCase):
    def test_3d_solver_and_ml_payloads_unchanged_from_qa9(self):
        with zipfile.ZipFile('/mnt/data/GeoField_R12_13_QA10_메시3단계_실행상태안정화_통합보관본.zip') as orig:
            manifest=json.loads((ROOT/'manifest.json').read_text())
            for name in manifest['files']:
                if name in ('frontend/cad.js','GeoField_CAD_Analysis.py'): continue
                self.assertEqual((ROOT/'payload'/name).read_bytes(),orig.read('payload/'+name),name)
            self.assertNotEqual((ROOT/'payload/frontend/cad.js').read_bytes(),orig.read('payload/frontend/cad.js'))
            self.assertNotEqual((ROOT/'payload/GeoField_CAD_Analysis.py').read_bytes(),orig.read('payload/GeoField_CAD_Analysis.py'))

    def test_package_manifest_accepts_previous_qa9_frontend(self):
        with zipfile.ZipFile('/mnt/data/GeoField_R12_13_QA10_메시3단계_실행상태안정화_통합보관본.zip') as orig:
            old=hashlib.sha256(orig.read('payload/frontend/cad.js')).hexdigest()
        from installer import verify_bundle,DirectoryBundle
        record=verify_bundle(DirectoryBundle(ROOT))['files']['frontend/cad.js']
        self.assertTrue(old==record['from'] or old in record['compatible_from'])
        self.assertEqual(record['to'],hashlib.sha256((ROOT/'payload/frontend/cad.js').read_bytes()).hexdigest())

    def test_qa9_to_qa10_upgrade_and_rollback_preserves_data(self):
        import installer
        with tempfile.TemporaryDirectory() as td,zipfile.ZipFile('/mnt/data/GeoField_R12_13_QA10_메시3단계_실행상태안정화_통합보관본.zip') as orig:
            folder=Path(td)/'GeoFieldCAD/onefile_runtime/8a9ac53a821a0eb5'
            folder.mkdir(parents=True)
            for name in json.loads((ROOT/'manifest.json').read_text())['files']:
                p=folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(orig.read('payload/'+name))
            (folder/'engine_runtime.py').write_text('existing runtime')
            protected={n:content for n,content in (('original.step',b'CAD'),('history.sqlite3',b'DB'),('fea_run/run.frd',b'FRD'),('fea_run/run.inp',b'INP'),('ml/checkpoint.pt',b'WEIGHTS'))}
            for name,content in protected.items():
                p=folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content)
            original=(folder/'frontend/cad.js').read_bytes()
            receipt={}
            self.assertEqual(installer.apply(installer.DirectoryBundle(ROOT),localappdata=td,receipt=receipt),0)
            self.assertEqual([x['path'] for x in receipt['changed']],['GeoField_CAD_Analysis.py','frontend/cad.js'])
            self.assertEqual(installer.apply(installer.DirectoryBundle(ROOT),localappdata=td),0)
            for name,content in protected.items():self.assertEqual((folder/name).read_bytes(),content)
            self.assertEqual(installer.rollback_install(receipt),2)
            self.assertEqual((folder/'frontend/cad.js').read_bytes(),original)

    def test_actual_frontend_handler_with_mock_http_dropouts(self):
        if not shutil.which('node'):self.skipTest('node not installed')
        snippet=JS.split("$('feaMeshSeriesStartBtn').onclick=async()=>{",1)[1].split("$('feaMeshSeriesCancelBtn').onclick=async()=>{",1)[0]
        handler="$('feaMeshSeriesStartBtn').onclick=async()=>{"+snippet
        # Only the front-end control flow is mocked. No solver runs or FEA evidence.
        script=r'''const vm=require('node:vm'); const assert=require('node:assert/strict');
const handler=process.argv[1];
async function test(failures,ended,requestFails=false) {
 let count=0; const el={}; const $=id=>(el[id]??={textContent:'',disabled:false});
 const ctx={$,console, file:{},current:{sha256:'cad'},jobId:'job',feaPrepared:true,
  feaPreparedCaseSha:'case', meshSeriesPlan:{cad_sha256:'cad',base_case_sha256:'case'},
  window:{confirm:()=>true}, meshSeriesReset:()=>{},
  fetch:async()=>{if(requestFails)throw Error('upload HTTP failed');return {ok:true,json:async()=>({id:'study'})}},
  get:async()=>{count++;if(count<=failures)throw Error('temporary network');return {status:ended?'complete':'running',completed:ended?3:0,total:3,current_index:0,message:'mock status',analysis_snapshot_ids:[],study_analysis:null}},
  sleep:async()=>{},gfMeshSensitivityLabel:()=> 'diagnostic only',gfMeshSpatialEvidence:()=> 'position not measured'};
 vm.runInNewContext('let meshSeriesId=null, meshSeriesBusy=false;'+handler,ctx);
 if(ended)await el.feaMeshSeriesStartBtn.onclick();
 else if(requestFails)await el.feaMeshSeriesStartBtn.onclick();
 else await el.feaMeshSeriesStartBtn.onclick();
 assert.equal(typeof el.feaMeshSeriesCancelBtn.disabled,'boolean');
 if(ended){assert.equal(el.feaMeshSeriesCancelBtn.disabled,true);assert.ok(count>=failures+1)}
 else if(requestFails){assert.equal(el.feaMeshSeriesCancelBtn.disabled,true);assert.match(el.feaMeshSeriesProgress.textContent,/요청\/상태 조회 실패/)}
 else {assert.equal(el.feaMeshSeriesCancelBtn.disabled,false);assert.ok(count===5);assert.match(el.feaMeshSeriesProgress.textContent,/계산이 중단됐다는 의미는 아닙니다/)}
}
(async()=>{await test(2,true);await test(5,false);await test(0,false,true);console.log('QA10 UI HTTP mock 3 scenarios PASS')})().catch(e=>{console.error(e);process.exit(1)})'''
        r=subprocess.run(['node','-e',script,handler],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stdout+'\n'+r.stderr)

if __name__=='__main__':unittest.main()
