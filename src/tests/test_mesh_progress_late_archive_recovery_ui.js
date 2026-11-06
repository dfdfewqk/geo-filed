'use strict';
// Production recovery of a 3/3 CalculiX series after old 15s FRD status-poll
// timeout. No replayed solver job, paid model or user file modification.
const assert=require('node:assert/strict'),fs=require('node:fs'),
 vm=require('node:vm'),path=require('node:path');
const js=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const start=js.indexOf('let gfVerifiedMeshFollowup=null;');
const end=js.indexOf('// Stage 6:',start);
assert(start>0&&end>start,'real on-demand mesh recovery source required');
const backend=fs.readFileSync(path.join(__dirname,'../payload/GeoField_CAD_Analysis.py'),'utf8');
const progressRoute=backend.indexOf("if path.startswith('/api/fea/mesh-series/progress/'):");
const verifiedRoute=backend.indexOf("if path.startswith('/api/fea/mesh-series/status/'):",progressRoute);
assert(progressRoute>0&&verifiedRoute>progressRoute,'quick progress and full archive endpoints must be separate');
assert(backend.slice(progressRoute,verifiedRoute).includes("st['mesh_study_verified']=False"),
 'quick progress endpoint must not claim independently verified evidence');
const startHandler=js.slice(js.indexOf("$('feaMeshSeriesStartBtn').onclick=async("),
 js.indexOf("$('feaMeshSeriesCancelBtn').onclick=",js.indexOf("$('feaMeshSeriesStartBtn').onclick=async(")));
assert(startHandler.includes("'/api/fea/mesh-series/progress/'"));
assert(startHandler.includes("'/api/fea/mesh-series/status/'"));
assert(startHandler.includes('120000'));
const UID='1'.repeat(32),SHA='a'.repeat(64),RUN='2'.repeat(32),
 CASE='b'.repeat(64),STUDY='3'.repeat(32);
const solver=()=>({
 id:STUDY,cad_job_id:UID,cad_sha256:SHA,status:'complete',
 completed:3,total:3,mesh_study_verified:true,
 study_analysis:{
  status:'verified_three_mesh_sensitivity_only',same_physical_case:true,
  solver_evidence:'each_calculix_run_revalidated',
  convergence_certified:false,safety_certified:false,
  runs_coarse_to_fine:[
   {cad_sha256:SHA,mesh_target_mm:3,max_stress_mpa:10,max_displacement_mm:0.1},
   {cad_sha256:SHA,mesh_target_mm:2,max_stress_mpa:11,max_displacement_mm:0.11},
   {cad_sha256:SHA,mesh_target_mm:1,max_stress_mpa:11.5,max_displacement_mm:0.115}
  ],
  adjacent_changes:[
   {stress_relative_change_percent:100/11,displacement_relative_change_percent:100/11},
   {stress_relative_change_percent:100*.5/11.5,
    displacement_relative_change_percent:100*(.115-.11)/.115}
  ]
 }
});
const quick=()=>({id:STUDY,cad_job_id:UID,cad_sha256:SHA,
 status:'complete',completed:3,total:3,mesh_study_verified:false,
 verification_pending:true,study_analysis:null});
function make({p=quick(),full=solver(),changedCase=false,changedRun=false}={}){
 const calls=[],store=new Map(),status={textContent:''},view=[];
 const ctx={
  Number,Math,JSON,String,Array,Error,Promise,
  meshSeriesId:STUDY,meshSeriesJobId:UID,meshSeriesCadSha:SHA,
  meshSeriesCaseSha:changedCase?'c'.repeat(64):CASE,
  meshSeriesBaseRun:changedRun?'4'.repeat(32):RUN,
  feaPreparedCaseSha:CASE,meshSeriesBusy:true,
  meshSeriesStatusUnknown:true,
  gfReportSelectionCurrent:(uid,sha,run,c)=>uid===UID&&sha===SHA&&
    run===RUN&&c===CASE,
  gfRenderMeshProgress:(state)=>{view.push(state);return true},
  $:id=>id==='gfMeshFollowupStatus'?status:null,
  localStorage:{
   getItem:key=>store.get(key)??null,
   setItem:(key,value)=>store.set(key,value)
  },
  get:async(url,timeout)=>{
   calls.push({url,timeout});
   if(url==='/api/fea/mesh-series/progress/'+STUDY)return p;
   if(url==='/api/fea/mesh-series/status/'+STUDY)return full;
   throw Error('unexpected request '+url);
  }
 };
 vm.createContext(ctx);vm.runInContext(js.slice(start,end),ctx);
 return{ctx,calls,status,store,view,
  recover:()=>ctx.gfRecoverCompletedMeshForReport(UID,SHA,RUN,CASE)};
}
(async()=>{
 const done=make();
 const proof=await done.recover();
 assert.equal(proof?.runs.length,3);
 assert.equal(done.ctx.meshSeriesBusy,false,'verified completed server status must clear stuck busy flag');
 assert.equal(done.ctx.meshSeriesStatusUnknown,false);
 assert.equal(done.calls.length,2,'light progress plus one full verification; no third expensive read');
 assert.deepEqual(done.calls.map(x=>x.timeout),[18000,120000]);
 assert.match(done.status.textContent,/3\/3 실제 FEA 독립 재검증 완료/);
 assert.equal(done.view.length,1);
 assert(JSON.parse(done.store.get('geofield_verified_mesh_links_v1')).links.some(x=>x.id===STUDY));
 const stillRunning=make({p:{...quick(),status:'running',completed:3}});
 assert.equal(await stillRunning.recover(),null);
 assert.equal(stillRunning.calls.length,1,'3/3 does not itself prove verification is done');
 assert.equal(stillRunning.ctx.meshSeriesBusy,true);
 const failed=make({full:{...solver(),status:'verification_failed',mesh_study_verified:false}});
 assert.equal(await failed.recover(),null);
 assert.equal(failed.ctx.meshSeriesBusy,true);
 assert.equal(failed.store.size,0);
 const mismatch=make({full:{...solver(),study_analysis:{
   ...solver().study_analysis,adjacent_changes:[
    {...solver().study_analysis.adjacent_changes[0],stress_relative_change_percent:0},
    solver().study_analysis.adjacent_changes[1]
   ]}}});
 assert.equal(await mismatch.recover(),null,'contradictory solver delta cannot become report evidence');
 assert.equal(mismatch.ctx.meshSeriesBusy,true);
 for(const changed of [{changedCase:true},{changedRun:true}]){
  const stale=make(changed);
  assert.equal(await stale.recover(),null,'a different base run/case must not borrow the old study');
  assert.equal(stale.calls.length,0);
 }
 console.log('PASS: screen-video 3/3 CalculiX status timeout recovers real signed solver evidence for report; no duplicated FEA or paid API');
})().catch(e=>{console.error(e);process.exitCode=1});
