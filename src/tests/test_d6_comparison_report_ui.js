'use strict';
// Native report A/B cross-geometry integration, synthetic independently verified
// server response only. No real file writes, FEA solve or paid network.
const assert=require('node:assert/strict'),fs=require('node:fs'),
      vm=require('node:vm'),path=require('node:path');
const js=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const a=js.indexOf('function gfReportReady('),b=js.indexOf("$('collapseBtn').onclick",a);
assert(a>0&&b>a&&js.slice(a,b).includes('GEOFIELD_D6_REPORT_FEEDBACK_V1'));
const A='3'.repeat(32),B='4'.repeat(32),R1='1'.repeat(32),R2='2'.repeat(32);
const SHA1='a'.repeat(64),SHA2='b'.repeat(64),CASE='c'.repeat(64),UID='5'.repeat(32);
const pair={
 original:A,variant:B,cadJobId:UID,
 variantSHA:SHA2,variantRun:R2,variantCaseSHA:CASE};
function summary(){return {cad:{sha256:SHA2},
 fea:{state:'complete',result_run_id:R2,result_case_sha256:CASE,
  maximum_von_mises_mpa:18.,maximum_displacement_mm:.027,
  node_count:1250,tetrahedron_count:4400},
 fea_case_provenance:{source_verification:'INP_STA_FRD_reverified',
 summary_numbers_crosschecked:true,verified_run_id:R2,solved_case_sha256:CASE,
 verified_mesh:{nodes:1250,tetrahedra:4400}}}}
const proof=()=>({
 schema:'geofield-d6-two-geometry-descriptive-v1',
 status:'two_different_cad_real_solver_runs_descriptive_only',
 source:'original_and_server_generated_D6_step_sha_bound',
 read_only:true,
 original:{snapshot_id:A,run_id:R1,cad_sha256:SHA1,case_sha256:'d'.repeat(64),
  max_stress_mpa:20.,max_displacement_mm:.030,
  mesh_node_count:1000,mesh_tetrahedron_count:3500},
 variant:{snapshot_id:B,run_id:R2,cad_sha256:SHA2,case_sha256:CASE,
  max_stress_mpa:18.,max_displacement_mm:.027,
  mesh_node_count:1250,mesh_tetrahedron_count:4400},
 fixed_and_loaded_surface_equivalence_verified:false,
 reaction_and_applied_moment_equivalence_verified:false,
 support_location_screen_passed:true,
 applied_load_moment_screen_passed:true,
 physical_load_screen:{
  support_bbox_max_drift_mm:0.01,load_bbox_max_drift_mm:0.02,
  load_center_distance_mm:0.03,resultant_drift_n:0.001,
  load_moment_change_n_mm:0.02,
  load_moment_equivalent_lever_arm_change_mm:0.001},
 design_improvement_verified:false,mesh_convergence_certified:false,
 structural_safety_certified:false,
 stress_change:{original:20,variant:18,absolute_difference:-2,percent_vs_original:-10},
 displacement_change:{original:.03,variant:.027,absolute_difference:-.003,percent_vs_original:-10}
});
function parsed(){
 const children=[],legacy={textContent:'DeepSeek 설명: 표시 불가',remove(){this.textContent=''}};
 const anchor={querySelectorAll:()=>[legacy],insertAdjacentElement:(where,x)=>children.push(x)};
 const p={
  body:{firstChild:{},insertBefore:x=>children.push(x),append:x=>children.push(x)},
  createElement:tag=>({tag,id:'',textContent:'',style:{},children:[],
     append(...xs){this.children.push(...xs)}}),
  getElementById:id=>id==='geofield-a08-evidence'?anchor:null};
 const desc=x=>[x.textContent||'',...(x.children||[]).map(desc)].join(' ');
 p.documentElement={get outerHTML(){
  return '<html><body>real FEA '+legacy.textContent+' '+
    children.map(desc).join(' ')+'</body></html>'}};
 return p;
}
const nodes={
 resultsReportBtn:{disabled:false},resultsReportSaveBtn:{disabled:false},
 resultsReportStatus:{textContent:''},resultsReportSavedPath:{textContent:''},
 reportAiIncludeToggle:{checked:false},
 gfMeshFollowupBtn:{disabled:false},gfMeshFollowupStatus:{textContent:''},
 gfD6VariantBtn:{disabled:false},gfD6VariantStatus:{textContent:''}};
const calls={paid:[],read:[],tabs:[]};
let response=proof();
const ctx={String,Number,Math,Date,Promise,Error,URLSearchParams,encodeURIComponent,
 jobId:UID,current:{sha256:SHA2},latestSummary:summary(),
 feaRunId:null,meshSeriesBusy:false,
 $:id=>nodes[id]||null,
 window:{open:()=>{const tab={closed:false,writes:[],document:{
 open(){},close(){},write(t){tab.writes.push(t)},getElementById:()=>({textContent:''})}};
 calls.tabs.push(tab);return tab;},confirm:()=>true},
 DOMParser:class{parseFromString(){return parsed()}},
 fetch:async()=>({ok:true,text:async()=>'<html><body>'+
  'VERIFIED CAD FEA REPORT '.repeat(15)+'</body></html>'}),
 get:async(url,t,headers)=>{
  if(url==='/api/ml/latest/'+UID)return {status:'not_run',cad_job_id:UID,cad_sha256:SHA2};
  if(url.startsWith('/api/history/fea-d6-geometry-compare?')){
   calls.read.push(url);return response;
  }
  if(url.startsWith('/api/agent/evidence/')){
   calls.paid.push({url,headers});return {
    schema:'geofield-evidence-agent-v1',cad_sha256:SHA2,
    fea:{status:'INP_STA_FRD_reverified',run_id:R2,case_sha256:CASE},
    mode:'rules_plus_llm',
    llm:{connected:true,executed:true,provider:'deepseek',
     status:'external_explanation_only',explanation:'실제 원본/변경본 수치 검토. 개선 미검증.'}};
  }
  throw Error('unexpected GET '+url);
 },
 document:{body:{append(){}},createElement:()=>({click(){},remove(){}})},
 URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},
 setTimeout(){}};
// The production report now includes the shared conservative engineering
// review helper; load it in the isolated DOM test before the report handlers.
const step2Start=js.indexOf('function gfEngineeringStage2Review(');
const step2End=js.indexOf('function gfEvidenceChecklistLines(',step2Start);
assert(step2Start>0&&step2End>step2Start);
vm.createContext(ctx);
vm.runInContext(js.slice(step2Start,step2End)+'\n'+js.slice(a,b),ctx);
 // This is a D6 readback test; the real paid report evidence gate has
 // dedicated bad-input tests to ensure it cannot be bypassed in production.
 assert(js.includes('gfRequireCompletePaidReportEvidence(parsed,meshFollowup,brepProof,r12Proof,uid,sha,run,caseSha)'));
 ctx.gfRequireCompletePaidReportEvidence=()=>true;
 assert(js.includes('gfVerifyFeaHtmlNumericReadback(parsed,uid,sha,run,caseSha)'));
 ctx.gfVerifyFeaHtmlNumericReadback=()=>true;
const setPair=()=>vm.runInContext(
 'gfD6PairForReport='+JSON.stringify(pair),ctx);
// Review the REAL D6 validator rather than trusting a copied status/percentage.
// All changes here are in-memory test responses; no FEA/LLM or user records.
assert.equal(ctx.gfD6ReverifiedNumericReport(proof()),true);
for(const [name,bad] of [
 ['stale variant stress',{variant:{max_stress_mpa:18.4}}],
 ['stale variant displacement',{variant:{max_displacement_mm:.029}}],
 ['wrong variant node count',{variant:{mesh_node_count:1251}}],
 ['wrong variant element count',{variant:{mesh_tetrahedron_count:4401}}],
 ['bad original mesh',{original:{mesh_node_count:0}}],
 ['wrong stress baseline',{stress_change:{original:19}}],
 ['wrong stress variant',{stress_change:{variant:19}}],
 ['wrong signed stress delta',{stress_change:{absolute_difference:2}}],
 ['wrong stress percent',{stress_change:{percent_vs_original:-7}}],
 ['wrong disp baseline',{displacement_change:{original:.04}}],
 ['wrong disp delta',{displacement_change:{absolute_difference:0}}],
 ['wrong disp percent',{displacement_change:{percent_vs_original:-20}}],
 ['missing delta',{stress_change:{absolute_difference:null}}]
 ]){
 const v=proof();for(const [key,values] of Object.entries(bad))
  v[key]={...v[key],...values};
 assert.equal(ctx.gfD6ReverifiedNumericReport(v),false,name);
}
{
 const z=proof();z.original.max_stress_mpa=0;
 z.stress_change={original:0,variant:18,absolute_difference:18,percent_vs_original:null};
 assert.equal(ctx.gfD6ReverifiedNumericReport(z),true,'zero baseline is undefined percentage');
 z.stress_change.percent_vs_original=0;
 assert.equal(ctx.gfD6ReverifiedNumericReport(z),false,'zero baseline cannot claim 0%');
}
(async()=>{
 await nodes.resultsReportBtn.onclick();
 assert.equal(calls.read.length,0);
 assert.equal(calls.paid.length,0);
 assert.doesNotMatch(calls.tabs.at(-1).writes.at(-1),/별도 형상 재해석/);
 setPair();
 await nodes.resultsReportBtn.onclick();
 assert.equal(calls.read.length,1);
 assert.equal(calls.paid.length,0);
 assert.match(calls.tabs.at(-1).writes.at(-1),/별도 형상 재해석/);
 assert.match(calls.tabs.at(-1).writes.at(-1),/20\.00000 MPa/);
 assert.match(calls.tabs.at(-1).writes.at(-1),/원본\/변경본 D6 비교: 두 STEP의 실제 계산/);
 assert.match(calls.tabs.at(-1).writes.at(-1),/동등성/);
 nodes.reportAiIncludeToggle.checked=true;
 await nodes.resultsReportBtn.onclick();
 assert.equal(calls.paid.length,1);
 assert(calls.paid[0].url.includes('d6_original='+A));
 assert(calls.paid[0].url.includes('d6_variant='+B));
 assert.equal(calls.paid[0].headers['X-GeoField-LLM-Opt-In'],'1');
 assert.equal(nodes.reportAiIncludeToggle.checked,false);
 assert.match(calls.tabs.at(-1).writes.at(-1),/별도 형상 재해석/);
 assert.match(calls.tabs.at(-1).writes.at(-1),/실제 원본\/변경본 수치/);
 // False server claim must be omitted from the report and provider prompt.
 response={...proof(),support_location_screen_passed:false};
 await nodes.resultsReportBtn.onclick();
 assert.doesNotMatch(calls.tabs.at(-1).writes.at(-1),/별도 형상 재해석/);
 assert.equal(calls.paid.length,1);
 nodes.reportAiIncludeToggle.checked=true;
 await nodes.resultsReportBtn.onclick();
 assert.equal(calls.paid.length,1,
  'An explicitly selected FAILED D6 comparison must not spend external AI tokens');
 assert.match(nodes.resultsReportStatus.textContent,/유료 AI 호출 차단/);
 response={...proof(),stress_change:{...proof().stress_change,percent_vs_original:-20}};
 nodes.reportAiIncludeToggle.checked=true;
 await nodes.resultsReportBtn.onclick();
 assert.equal(calls.paid.length,1,
  'Inconsistent B-A percentage must also block an explicitly selected paid D6 analysis');
 response=proof();
 nodes.reportAiIncludeToggle.checked=true;
 await nodes.resultsReportBtn.onclick();
 assert.equal(calls.paid.length,2,'Validated D6 must be sent only after it is repaired');
 assert(calls.paid[1].url.includes('d6_original='+A));
 // New selected CAD/run cannot reuse historical A/B context.
 ctx.latestSummary={...summary(),fea_case_provenance:{
  ...summary().fea_case_provenance,verified_run_id:'9'.repeat(32)}};
 assert.equal(await ctx.gfReverifiedD6ReportPair(UID,SHA2,R2,CASE),null);
 console.log('PASS: D6 comparison in same HTML report, OFF no paid call, ON one scoped DeepSeek, stale rejected');
})().catch(e=>{console.error(e);process.exitCode=1});
