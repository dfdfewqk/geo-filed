'use strict';
// Regression: restart may recover an ID, never a solver result or a verdict.
// No real Gmsh/CalculiX, FEA, SQLite, or paid AI calls in this unit test.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const js=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8').replace(/\r\n/g,'\n');
const from=js.indexOf('let gfVerifiedMeshFollowup=null;');
const to=js.indexOf('// Stage 6:',from);
assert(from>0&&to>from,'verified mesh readback and cache source required');
const methods=js.slice(from,to);
const JOB='1'.repeat(32),SHA='a'.repeat(64),RUN='2'.repeat(32),
 CASE='b'.repeat(64),STUDY='3'.repeat(32),KEY='geofield_verified_mesh_links_v1';
const state=()=>({
 id:STUDY,cad_job_id:JOB,cad_sha256:SHA,
 status:'complete',mesh_study_verified:true,
 study_analysis:{
  status:'verified_three_mesh_sensitivity_only',same_physical_case:true,
  solver_evidence:'each_calculix_run_revalidated',
  convergence_certified:false,safety_certified:false,
  runs_coarse_to_fine:[
   {cad_sha256:SHA,mesh_target_mm:3,max_stress_mpa:10,max_displacement_mm:.1},
   {cad_sha256:SHA,mesh_target_mm:2,max_stress_mpa:11,max_displacement_mm:.11},
   {cad_sha256:SHA,mesh_target_mm:1,max_stress_mpa:11.5,max_displacement_mm:.115}
  ],
  adjacent_changes:[
   {stress_relative_change_percent:Math.abs(11-10)/11*100,
    displacement_relative_change_percent:Math.abs(.11-.1)/.11*100},
   {stress_relative_change_percent:Math.abs(11.5-11)/11.5*100,
    displacement_relative_change_percent:Math.abs(.115-.11)/.115*100}
  ]
 }
});
function make(storage,server=()=>state()){
 const requests=[],context={
  Math,Number,JSON,String,Array,Error,Promise,meshSeriesBusy:false,
  localStorage:{
   getItem:key=>storage.get(key)??null,
   setItem:(key,value)=>storage.set(key,value)
  },
  gfReportSelectionCurrent:(uid,sha,run,caseSha)=>
   uid===JOB&&sha===SHA&&run===RUN&&caseSha===CASE,
  get:async url=>{requests.push(url);return server();}
 };
 vm.createContext(context);
 vm.runInContext(methods,context);
 return{context,requests,
  choose:(uid=JOB,sha=SHA,run=RUN,caseSha=CASE)=>
   context.gfMeshFollowupSelection(uid,sha,run,caseSha),
  fetch:()=>context.gfFetchMeshFollowup(JOB,SHA,RUN,CASE)};
}
(async()=>{
 const storage=new Map();
 const original=make(storage);
 // A server 'complete' response alone is never persisted as verified.
 vm.runInContext(`gfVerifiedMeshFollowup={
   id:'${STUDY}',jobId:'${JOB}',cadSha:'${SHA}',runId:'${RUN}',caseSha:'${CASE}'
 }`,original.context);
 assert.equal(storage.has(KEY),false);
 const first=await original.fetch();
 assert.equal(first?.runs?.length,3);
 assert.equal(storage.has(KEY),true,'verified link should survive the next browser session');
 assert.equal(JSON.parse(storage.get(KEY)).links.length,1);
 const restored=make(storage);
 assert.equal(restored.choose()?.id,STUDY,'matching run should recover prior ID');
 assert.equal(restored.choose(JOB,SHA,'4'.repeat(32),CASE),null);
 assert.equal(restored.choose(JOB,'c'.repeat(64),RUN,CASE),null);
 assert.equal(restored.choose(JOB,SHA,RUN,'d'.repeat(64)),null);
 assert.equal(restored.choose('5'.repeat(32),SHA,RUN,CASE),null);
 assert.equal(restored.requests.length,0,'stored ID alone must not run solver or prove FEA');
 const genuine=await restored.fetch();
 assert.equal(genuine?.runs?.length,3,'actual server must be rechecked after restart');
 assert.deepEqual(restored.requests,['/api/fea/mesh-series/status/'+STUDY]);
 const fake=make(storage,()=>({...state(),cad_sha256:'c'.repeat(64)}));
 assert.equal(await fake.fetch(),null,'changed backend CAD must be rejected');
 const badDelta=make(storage,()=>{
  const x=state();x.study_analysis.adjacent_changes[0].stress_relative_change_percent=0;return x;
 });
 assert.equal(await badDelta.fetch(),null,'fabricated percentage must be rejected');
 const missing=make(storage,()=>{throw Error('server unavailable')});
 assert.equal(await missing.fetch(),null,'network errors are not verification');
 storage.set(KEY,JSON.stringify({version:1,links:[{
  id:'javascript:evil',jobId:JOB,cadSha:SHA,runId:RUN,caseSha:CASE}]}));
 assert.equal(make(storage).choose(),null,'malformed client cache cannot become a run ID');
 storage.set(KEY,'not-json');
 assert.equal(make(storage).choose(),null,'corrupted cache must fail closed');
 const blocked=make(new Map());
 blocked.context.localStorage.setItem=()=>{throw Error('private mode');};
 vm.runInContext(`gfVerifiedMeshFollowup={
   id:'${STUDY}',jobId:'${JOB}',cadSha:'${SHA}',runId:'${RUN}',caseSha:'${CASE}'
 }`,blocked.context);
 assert.equal((await blocked.fetch())?.runs?.length,3,'storage unavailable must not block live proof');
 console.log('PASS: three-mesh ID survives restart with exact SHA/run/case binding; original solver archives are always reverified');
})().catch(e=>{console.error(e);process.exitCode=1;});
