'use strict';
// Stage 2: production orchestrator with synthetic FEA/status responses only.
// No user STEP, solver, local history, Windows installation, or paid provider.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const code=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../payload/frontend/index.html'),'utf8');
const mark='// GEOFIELD_ONE_CLICK_MESH_HOTSPOT_STAGE2_20261104';
const a=code.indexOf(mark),b=code.indexOf('let gfOneClickPreparing=false;',a);
assert(a>0&&b>a);
const stage2=code.slice(a,b);
assert.equal((html.match(/id="gfAutoMeshSummary"/g)||[]).length,1);
assert(code.includes("const verifiedMeshReady=await gfAutoStage2Verification("));
assert(code.includes("if(verifiedMeshReady===true)"));
assert(code.includes("if(launchMode!=='ONE_CLICK_ANALYSIS'&&!window.confirm("));
assert(code.includes("if((terminalConfirmed||!postDispatched||explicitlyRejected)&&!meshSeriesBusy)"),
 "A lost solver POST response must NOT unlock controls or assume a rejected calculation");
const job='1'.repeat(32),sha='a'.repeat(64),caseSha='b'.repeat(64),run='2'.repeat(32);
const verifiedState={status:'complete',mesh_study_verified:true,cad_job_id:job,cad_sha256:sha,
 study_analysis:{status:'verified_three_mesh_sensitivity_only',spatial_peak_diagnostic:{
 status:'verified_surface_peak_positions_only'}}};
function setup({ready=true,planGood=true,studyGood=true,verifiedGood=true,staleAfterPlan=false,transientOnce=false}={}){
 const actions=[],nodes={},state={selected:true,attempts:0};
 const $=id=>nodes[id]??(nodes[id]={textContent:''});
 const context={String,Error,Promise,jobId:job,current:{sha256:sha},
   latestSummary:{cad:{sha256:sha}},
   $:id=>$(id),gfReportReady:()=>ready,gfReportSelectionCurrent:()=>ready,
   meshSeriesId:'3'.repeat(32),sleep:async()=>{},
   get:async()=>({id:'3'.repeat(32),cad_job_id:job,cad_sha256:sha,
     status:'verification_failed',verification_warning:'FRD raw file mismatch'}),
   gfFetchMeshFollowup:async()=>{actions.push('reverify');state.attempts++;
    return verifiedGood&&(!transientOnce||state.attempts>1)?{id:'3'.repeat(32)}:null},
   gfFeaVerificationSummary:(...args)=>actions.push('ui-evidence-summary'),
   gfRenderEvidenceChecklist:(...args)=>actions.push('ui-checklist'),
   gfMeshSensitivityLabel:()=> '3개 실제 메시 변화율 계산됨',
   gfMeshSpatialEvidence:()=> 'FRD 표면 최고 응력 위치 (10.00, 0.00, 2.00) mm'};
 $('feaMeshSeriesProgress').textContent='실행 실패';
 $('feaMeshSeriesPlanBtn').onclick=async()=>{
  actions.push('plan');
  if(staleAfterPlan)state.selected=false;
  return planGood?{cad_sha256:sha,base_case_sha256:caseSha}:null;
 };
 $('feaMeshSeriesStartBtn').onclick=async mode=>{
  actions.push('start:'+mode);
  return studyGood?verifiedState:{...verifiedState,status:'verification_failed',mesh_study_verified:false};
 };
 vm.createContext(context);vm.runInContext(stage2,context);
 const call=()=>context.gfAutoStage2Verification(job,sha,caseSha,run,()=>state.selected);
 return{call,nodes,actions,state};
}
(async()=>{
 const t=setup();
 assert.equal(await t.call(),true);
 assert.deepEqual(t.actions,['plan','start:ONE_CLICK_ANALYSIS','reverify','ui-evidence-summary','ui-checklist']);
 assert.match(t.nodes.gfAutoMeshSummary.textContent,/검증 완료/);
 assert.match(t.nodes.gfAutoMeshSummary.textContent,/FRD 표면 최고 응력 위치/);
 assert.match(t.nodes.gfMeshFollowupStatus.textContent,/자동 연결 완료/);
 for(const params of [
  {ready:false},{planGood:false},{staleAfterPlan:true}
 ]) {
  const x=setup(params);await x.call();
  assert(!x.actions.some(q=>q.startsWith('start:')),
   'Never start a mesh series without fresh verified base FEA and signed case');
 }
 const bad=setup({studyGood:false});assert.equal(await bad.call(),false);
 assert(!bad.actions.includes('reverify'));
 assert.match(bad.nodes.gfAutoMeshSummary.textContent,/미완료\/실패/);
 const transient=setup({transientOnce:true});assert.equal(await transient.call(),true);
 assert.equal(transient.actions.filter(x=>x==='reverify').length,2,
  'Transient status race may only recheck existing study; it must not start another solver');
 assert.equal(transient.actions.filter(x=>x.startsWith('start:')).length,1);
 const missing=setup({verifiedGood:false});assert.equal(await missing.call(),false);
 assert.match(missing.nodes.gfAutoMeshSummary.textContent,/검증·결과 연결 실패/);
 assert.match(missing.nodes.gfAutoMeshSummary.textContent,/FRD raw file mismatch/);
 assert.equal(missing.actions.filter(x=>x.startsWith('start:')).length,1,
  'A verifier failure must never resubmit three CalculiX jobs');
 console.log('PASS: one-click after base FEA auto-runs signed 3-mesh study, gates fresh verified evidence, shows FRD spatial peak, no paid API');
})().catch(e=>{console.error(e);process.exitCode=1});
