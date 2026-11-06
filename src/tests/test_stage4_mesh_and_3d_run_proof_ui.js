'use strict';
// The real UI mesh-proof validation must bind three separately verified INP/
// STA/FRD runs to the same baseline CalculiX run AND signed FEA conditions.
// Synthetic read-only responses only; no solver/network, paid LLM or user data.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const a=source.indexOf('async function gfFetchMeshFollowup(');
const b=source.indexOf('// Stage 6: a fully reverified three-mesh study',a);
assert(a>=0&&b>a);
const body=source.slice(a,b)+'\nreturn gfFetchMeshFollowup;';
const JOB='a'.repeat(32),SHA='b'.repeat(64),RUN='c'.repeat(32),
      CASE='d'.repeat(64),STUDY='e'.repeat(32);
const sizes=[2.8,2,1.5],stress=[9,10,11],disp=[.09,.1,.11];
const percent=(u,v)=>Math.abs(v-u)/Math.abs(v)*100;
function sample(){
 return {id:STUDY,cad_job_id:JOB,cad_sha256:SHA,
  base_run_id:RUN,base_case_sha256:CASE,base_fea_binding_verified:true,
  status:'complete',mesh_study_verified:true,
  study_analysis:{
   status:'verified_three_mesh_sensitivity_only',
   same_physical_case:true,solver_evidence:'each_calculix_run_revalidated',
   convergence_certified:false,safety_certified:false,
   runs_coarse_to_fine:sizes.map((mesh_target_mm,i)=>({
     cad_sha256:SHA,mesh_target_mm,max_stress_mpa:stress[i],
     max_displacement_mm:disp[i]})),
   adjacent_changes:[0,1].map(i=>({
     stress_relative_change_percent:percent(stress[i],stress[i+1]),
     displacement_relative_change_percent:percent(disp[i],disp[i+1])}))}};
}
function harness(options={}){
 const seen=[],requests=[],link={id:STUDY,jobId:JOB,cadSha:SHA,
  runId:RUN,caseSha:CASE};
 let selected=options.selected!==false;
 const evaluate=new Function(
  'gfMeshFollowupSelection','gfReportSelectionCurrent','get',
  'gfRememberVerifiedMeshFollowup','Number','Math','Promise',body)(
  ()=>link,()=>selected,async url=>{requests.push(url);return options.response;},
  value=>seen.push(value),Number,Math,Promise);
 return {evaluate,seen,requests,stale:()=>{selected=false;}};
}
(async()=>{
 const current=harness(),valid=await current.evaluate(JOB,SHA,RUN,CASE,sample());
 assert(valid&&valid.runs.length===3&&valid.steps.length===2);
 assert.equal(valid.runs[0].mesh,2.8);
 assert.equal(valid.steps[1].stress,percent(10,11));
 assert.equal(valid.spatial,null);
 assert.equal(current.seen.length,1);
 assert.equal(current.requests.length,0,'reverified response must be reused, not fetched again');
 const cases=[
  ['wrong base run',x=>x.base_run_id='f'.repeat(32)],
  ['wrong base case',x=>x.base_case_sha256='f'.repeat(64)],
  ['unverified binding',x=>x.base_fea_binding_verified=false],
  ['old manifest missing binding',x=>delete x.base_fea_binding_verified],
  ['old manifest missing run',x=>delete x.base_run_id],
  ['old manifest missing case',x=>delete x.base_case_sha256],
  ['another STEP',x=>x.cad_sha256='f'.repeat(64)],
  ['same CAD, wrong study',x=>x.id='f'.repeat(32)],
  ['unverified solver series',x=>x.mesh_study_verified=false],
  ['not completed',x=>x.status='running'],
  ['forged solver delta',x=>x.study_analysis.adjacent_changes[0].stress_relative_change_percent=123],
  ['mislabeled convergence',x=>x.study_analysis.convergence_certified=true],
 ];
 for(const [title,alter] of cases){
  const x=sample();alter(x);
  const sandbox=harness(),answer=await sandbox.evaluate(JOB,SHA,RUN,CASE,x);
  assert.equal(answer,null,title);
  assert.equal(sandbox.seen.length,0,title+': must not cache invalid verification');
 }
 const stale=harness();stale.stale();
 assert.equal(await stale.evaluate(JOB,SHA,RUN,CASE,sample()),null);
 const fetched=harness({response:sample()});
 assert(await fetched.evaluate(JOB,SHA,RUN,CASE,null));
 assert.deepEqual(fetched.requests,['/api/fea/mesh-series/status/'+STUDY]);
 assert(!body.includes('fetch(')&&!body.includes('/api/fea/run/')&&
        !body.includes('/api/fea/mesh-series/start/')&&
        !body.includes('llm=1')&&!body.includes('localStorage.setItem'));
 console.log('PASS: 3-mesh real source binding to exact original FEA run/case; stale/forged/legacy cases blocked, no re-solve');
})().catch(e=>{console.error(e);process.exitCode=1;});
