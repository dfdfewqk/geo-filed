'use strict';
// Exercising the real report handlers with a synthetic DOM. Never run FEA or paid API.
const assert=require('node:assert/strict'),fs=require('node:fs'),
      vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../payload/frontend/index.html'),'utf8');
const a=src.indexOf('function gfReportReady('),b=src.indexOf("$('collapseBtn').onclick",a);
assert(a>0&&b>a&&src.slice(a,b).includes('GEOFIELD_AI_MESH_FEEDBACK_UI_V1'));
assert.equal((html.match(/id="gfMeshFollowupBtn"/g)||[]).length,1);
const SHA='a'.repeat(64),CASE='b'.repeat(64),JOB='1'.repeat(32),RUN='2'.repeat(32),STUDY='3'.repeat(32);
const summary=()=>({cad:{sha256:SHA},fea:{state:'complete',result_run_id:RUN,
 result_case_sha256:CASE,maximum_von_mises_mpa:14.5,
 maximum_displacement_mm:.022,node_count:800,tetrahedron_count:3300},
 fea_case_provenance:{source_verification:'INP_STA_FRD_reverified',
 summary_numbers_crosschecked:true,verified_run_id:RUN,solved_case_sha256:CASE,
 verified_mesh:{nodes:800,tetrahedra:3300}}});
const study=()=>({id:STUDY,cad_job_id:JOB,cad_sha256:SHA,status:'complete',
 mesh_study_verified:true,study_analysis:{status:'verified_three_mesh_sensitivity_only',
 same_physical_case:true,solver_evidence:'each_calculix_run_revalidated',
 convergence_certified:false,safety_certified:false,
 runs_coarse_to_fine:[0,1,2].map(i=>({cad_sha256:SHA,mesh_target_mm:2-i*.5,
 max_stress_mpa:14+i,max_displacement_mm:.02+i*.002})),
 // Use the backend's documented *finer mesh* denominator; these are
 // genuine relative deltas, not invented 'stable' fixture percentages.
 adjacent_changes:[{stress_relative_change_percent:100/15,displacement_relative_change_percent:100*(.022-.020)/.022},
 {stress_relative_change_percent:100/16,displacement_relative_change_percent:100*(.024-.022)/.024}],
 actual_mesh_resolution_diagnostic:{effective_mean_edge_refinement:true},
 actual_load_moment_diagnostic:{mesh_only_attribution_supported_by_this_screen:true},
 numeric_stability_diagnostic:{passes:false},
 spatial_peak_diagnostic:{
  status:'verified_surface_peak_positions_only',peak_positions_verified:true,
  source:'three_separately_reverified_calculix_frd_surface_fields',
  runs_coarse_to_fine:[0,1,2].map(i=>({
   surface_peak_position_mm:[10+i,1,3],surface_max_stress_mpa:13+i})),
  adjacent_peak_distances_mm:[1,1]
 }}});
function snapshot(){
 const added=[],notice={textContent:'DeepSeek 설명: 표시 불가 (old)',remove(){this.textContent=''}};
 const anchor={querySelectorAll:()=>[notice],insertAdjacentElement:(p,x)=>added.push(x)};
 const parsed={body:{firstChild:{},append:x=>added.push(x),insertBefore:x=>added.push(x)},
 createElement:tag=>({tag,id:'',textContent:'',style:{},children:[],attributes:{},
   append(...v){this.children.push(...v)},insertAdjacentElement:(p,v)=>added.push(v),
   setAttribute(key,value){this.attributes[key]=String(value)},
   getAttribute(key){return this.attributes[key]??null},
   querySelectorAll(sel){return sel==='p'?this.children.filter(x=>x.tag==='p'):[]}}),
 getElementById:id=>id==='geofield-a08-evidence'?anchor:added.find(x=>x.id===id)||null};
 const walk=x=>[x.textContent||'',...(x.children||[]).map(walk)].join(' ');
 parsed.documentElement={get outerHTML(){
 return '<html><body>VERIFIED FEA '+notice.textContent+' '+added.map(walk).join(' ')+'</body></html>'}};
 return parsed;
}
const nodes={resultsReportBtn:{disabled:false},resultsReportSaveBtn:{disabled:false},
 resultsReportStatus:{textContent:''},gfMeshFollowupBtn:{disabled:false},
 gfMeshFollowupStatus:{textContent:''},gfD6VariantBtn:{disabled:false},gfD6VariantStatus:{textContent:''},resultsReportSavedPath:{textContent:''},
 reportAiIncludeToggle:{checked:false},
 feaMeshSeriesPanel:{closest:()=>({open:false})},
 feaMeshSeriesPlanBtn:{focus(){this.focused=true},scrollIntoView(){this.scrolled=true}},
 feaMeshSeriesProgress:{textContent:''}};
const calls={get:[],paid:[],tabs:[],pane:[]};
let remoteStudy=study();
const ctx={String,Math,Number,Error,Date,Promise,encodeURIComponent,Blob,
 jobId:JOB,current:{sha256:SHA},latestSummary:summary(),feaRunId:null,
 meshSeriesBusy:false,feaPrepared:true,feaPreparedCaseSha:CASE,file:{name:'sample.step'},
 $:id=>nodes[id]||null,tabTo:p=>calls.pane.push(p),
 DOMParser:class{parseFromString(){return snapshot()}},
 window:{open:()=>{const tab={closed:false,writes:[],document:{
 open(){},close(){},write(x){tab.writes.push(x)},getElementById:()=>({textContent:''})}};
 calls.tabs.push(tab);return tab;},confirm:()=>true},
 fetch:async()=>({ok:true,text:async()=>'<html><body>'+
 'VERIFIED ENGINEERING REPORT '.repeat(20)+'</body></html>'}),
 get:async(url,t,headers)=>{
 calls.get.push(url);
 if(url==='/api/fea/mesh-series/status/'+STUDY)return remoteStudy;
 if(url==='/api/ml/latest/'+JOB)return {status:'not_run',cad_job_id:JOB,cad_sha256:SHA};
 if(url==='/api/geometry/hole-evidence/'+JOB)return {status:'unavailable',cad_job_id:JOB,sha256:SHA};
 if(url.startsWith('/api/agent/evidence/')){
  calls.paid.push({url,headers});
  return {schema:'geofield-evidence-agent-v1',cad_sha256:SHA,
   mode:'rules_plus_llm',fea:{status:'INP_STA_FRD_reverified',run_id:RUN,case_sha256:CASE},
   llm:{connected:true,executed:true,provider:'deepseek',status:'external_explanation_only',
   explanation:'3회 실제 계산을 재검토했습니다. CAD 형상 변경은 아직 없습니다.'}}}
 throw Error('unknown GET '+url)},
 document:{body:{append(){}},createElement:()=>({click(){},remove(){}})},
 URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},
 setTimeout(){}};
// The production report now includes the shared conservative engineering
// review helper; load it in the isolated DOM test before the report handlers.
const step2Start=src.indexOf('function gfEngineeringStage2Review(');
const step2End=src.indexOf('function gfEvidenceChecklistLines(',step2Start);
assert(step2Start>0&&step2End>step2Start);
vm.createContext(ctx);
vm.runInContext(src.slice(step2Start,step2End)+'\n'+src.slice(a,b),ctx);
 // Consent/mesh interactions are independent of the real completeness gate,
 // which is tested in test_report_completeness_paid_ai_guard_ui.js.
 assert(src.includes('gfRequireCompletePaidReportEvidence(parsed,meshFollowup,brepProof,r12Proof,uid,sha,run,caseSha)'));
 ctx.gfRequireCompletePaidReportEvidence=()=>true;
const setStudy=()=>vm.runInContext(
 "gfVerifiedMeshFollowup={id:'"+STUDY+"',jobId:'"+JOB+"',cadSha:'"+
 SHA+"',caseSha:'"+CASE+"',runId:'"+RUN+"'}",ctx);
(async()=>{
 ctx.$('gfMeshFollowupBtn').onclick();
 assert.deepEqual(calls.pane,['fea']);
 assert.equal(calls.get.length,0);
 assert.match(nodes.feaMeshSeriesProgress.textContent,/실제 3회 FEA/);
 assert.equal(nodes.feaMeshSeriesPlanBtn.focused,true);
 await ctx.$('resultsReportBtn').onclick();
 // A free BrepMFR evidence readback now runs for a complete report.
 // It must not be counted as either a mesh re-solve or a paid AI call.
 assert.deepEqual(calls.get,['/api/ml/latest/'+JOB,
  '/api/geometry/hole-evidence/'+JOB]);
 assert.equal(calls.paid.length,0);
 assert.doesNotMatch(calls.tabs.at(-1).writes.at(-1),/3단계 실제 FEA/);
 setStudy();
 const proof=await ctx.gfFetchMeshFollowup(JOB,SHA,RUN,CASE);
 assert(proof);assert.equal(proof.runs.length,3);
 await ctx.$('resultsReportBtn').onclick();
 assert.equal(calls.paid.length,0);
 assert.match(calls.tabs.at(-1).writes.at(-1),/3단계 실제 FEA/);
 const meshHtml=calls.tabs.at(-1).writes.at(-1);
 // Assert the real report renderer outputs each of 3 solves and 2 deltas.
 for(const row of [
  /1단계 · 목표 메시 2\.000 mm · 최대 응력 14\.00000 MPa · 최대 변위 0\.020000 mm/,
  /2단계 · 목표 메시 1\.500 mm · 최대 응력 15\.00000 MPa · 최대 변위 0\.022000 mm/,
  /3단계 · 목표 메시 1\.000 mm · 최대 응력 16\.00000 MPa · 최대 변위 0\.024000 mm/,
  /1→2 단계 변화율 · 응력 6\.667% · 변위 9\.091%/,
  /2→3 단계 변화율 · 응력 6\.250% · 변위 8\.333%/
 ])assert.match(meshHtml,row,'a separately verified mesh numeric line is missing');
 assert.match(calls.tabs.at(-1).writes.at(-1),/실제 FRD 표면 최고응력 위치/);
 assert.match(calls.tabs.at(-1).writes.at(-1),/좌표 이동/);
 nodes.reportAiIncludeToggle.checked=true;
 await ctx.$('resultsReportBtn').onclick();
 assert.equal(calls.paid.length,1);
 assert.equal(calls.paid[0].url,
  '/api/agent/evidence/'+JOB+'?llm=1&mesh_study='+STUDY);
 assert.equal(calls.paid[0].headers['X-GeoField-LLM-Opt-In'],'1');
 assert.equal(nodes.reportAiIncludeToggle.checked,false);
 remoteStudy={...study(),mesh_study_verified:false};
 assert.equal(await ctx.gfFetchMeshFollowup(JOB,SHA,RUN,CASE),null);
 await ctx.$('resultsReportBtn').onclick();
 assert.doesNotMatch(calls.tabs.at(-1).writes.at(-1),/14\.00000 MPa/);
 assert.equal(await ctx.gfFetchMeshFollowup(JOB,SHA,RUN,'f'.repeat(64)),null);
 console.log('PASS: real report UI one-click FEA navigation, reverified 3-run mesh, optional AI reassessment');
})().catch(e=>{console.error(e);process.exitCode=1});
