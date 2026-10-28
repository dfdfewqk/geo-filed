'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../payload/frontend/cad.js'), 'utf8');
const take = (begin, end) => {
 const a = source.indexOf(begin), b = source.indexOf(end, a + begin.length);
 assert.ok(a >= 0 && b > a, 'missing production source boundaries: ' + begin);
 return source.slice(a, b);
};
const labelCode = take('function gfFeaHistorySaveLabel(task){', 'let geofieldServerInstance=null;');
const deleteCode = take('function gfFeaDeleteIdentity(item,entry){', '// Append-only analysis history');
const SID='2'.repeat(32), UID='1'.repeat(32), RID='3'.repeat(32), CAD='a'.repeat(64), CASE='b'.repeat(64);
const item={id:SID,stage:'fea_result',job_id:UID,cad_sha256:CAD};
const entry={cad:{sha256:CAD},fea:{state:'complete',result_run_id:RID,result_case_sha256:CASE}};
function harness({record=entry, confirm=true, typed=SID.slice(-8), status=200}={}){
 const calls=[],alerts=[],elems={};
 const el=id=>elems[id]??(elems[id]={textContent:'',disabled:false,value:'',open:id==='recordAllAnalysisHistory'});
 let lookups=0, posts=0;
 const ctx={
  '$':el,window:{confirm:()=>confirm,prompt:()=>typed},
  feaRunId:null,gfRestoredRunId:null,meshSeriesBusy:false,
  feaArchiveInitialized:true,feaArchiveSelectedGeneration:0,feaArchiveVerified:null,
  feaComparePick:{left:null,right:null},jobId:null,current:null,
  get:async url=>{lookups++;assert.equal(url,'/api/history/item/'+SID);return record;},
  fetch:async (url,options)=>{
   posts++;calls.push({url,options});
   return {ok:status===200,headers:{get:()=> 'application/json'},
    json:async()=>status===200?{
     ok:true,permanent:true,other_records_preserved:true,
     deleted_snapshot_id:SID,deleted_run_id:RID,cad_sha256:CAD,
     temporary_cleanup:'complete'
    }:{error:'server rejected'}};
  },
  status:(...args)=>alerts.push(args),
  geoApiError:err=>err,
  r185Close:()=>{},
  loadFeaArchive:async()=>{elems.archiveReload=(elems.archiveReload||0)+1;},
  loadArchive:async()=>{elems.historyReload=(elems.historyReload||0)+1;},
  resetFeaField:()=>{},
  gfInvalidateAgentFeaEvidence:()=>{},
  loadCurrentResults:async()=>{},
 };
 const methods=vm.runInNewContext(labelCode+'\n'+deleteCode+
   '\n({label:gfFeaHistorySaveLabel,target:gfFeaDeleteIdentity,remove:gfDeleteArchivedFeaHistory})',ctx);
 return {ctx,methods,calls,alerts,elems,button:{disabled:false,isConnected:true},stats:()=>({lookups,posts})};
}
(async()=>{
 const h=harness(); const label=h.methods.label;
 assert.match(label({status:'running'}),/진행 중/);
 assert.match(label({status:'complete',history_archive_status:'saved',history_snapshot_id:SID}),/저장 완료/);
 assert.match(label({status:'complete',history_archive_status:'failed'}),/저장에 실패/);
 assert.doesNotMatch(label({status:'complete'}),/저장 완료/);
 assert.match(label({status:'failed'}),/계산 실패/);
 assert.deepEqual(JSON.parse(JSON.stringify(h.methods.target(item,entry))),
  {snapshot_id:SID,run_id:RID,cad_sha256:CAD});
 assert.throws(()=>h.methods.target(item,{...entry,cad:{sha256:'f'.repeat(64)}}),/확인할 수 없습니다/);
 assert.throws(()=>h.methods.target(item,{...entry,fea:{...entry.fea,result_run_id:'x'}}),/확인할 수 없습니다/);
 for(const scenario of [
   {record:{...entry,cad:{sha256:'f'.repeat(64)}}},
   {confirm:false},
   {typed:'WRONG'},
 ]) {
  const f=harness(scenario); await f.methods.remove(item,f.button);
  assert.equal(f.stats().posts,0,'must never POST without valid target and consent');
  assert.equal(f.button.disabled,false);
 }
 const done=harness();
 done.ctx.feaComparePick.left=SID;
 await done.methods.remove(item,done.button);
 assert.equal(done.stats().lookups,1);
 assert.equal(done.stats().posts,1);
 assert.equal(done.calls[0].url,'/api/history/fea-delete/'+SID);
 assert.equal(done.calls[0].options.method,'POST');
 assert.equal(done.calls[0].options.headers['X-GeoField-FEA-Delete'],'EXPLICIT_PERMANENT_DELETE');
 assert.equal(done.calls[0].options.headers['Content-Type'],'application/json');
 assert.deepEqual(JSON.parse(done.calls[0].options.body),{
   run_id:RID,cad_sha256:CAD,confirm:'PERMANENT_DELETE_FEA_RESULT'});
 assert.equal(done.elems.archiveReload,1);
 assert.equal(done.elems.historyReload,1);
 assert.equal(done.ctx.feaComparePick.left,null);
 assert.equal(done.button.disabled,false);
 const rejected=harness({status:409});
 await rejected.methods.remove(item,rejected.button);
 assert.equal(rejected.stats().posts,1,'failed destructive POST must not retry');
 assert.match(rejected.alerts.at(-1)[0],/실패/);
 assert.equal(rejected.elems.archiveReload,undefined);
 const busy=harness();busy.ctx.feaRunId='RUNNING';
 await busy.methods.remove(item,busy.button);
 assert.equal(busy.stats().lookups,0);
 assert.equal(busy.stats().posts,0);
 console.log('FEA history UI: archive label, identity, confirmation, once-only POST, compare cleanup, failure and busy guards OK');
})().catch(err=>{console.error(err);process.exitCode=1;});
