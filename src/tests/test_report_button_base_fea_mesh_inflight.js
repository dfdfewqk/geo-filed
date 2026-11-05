'use strict';
// Regression reproducing the user's Windows recording: a real current FEA
// result was displayed while the 3-mesh study made HTML preview unclickable.
// Uses synthetic server state only; never starts FEA, changes SQLite or pays AI.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const assert=require('node:assert/strict');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
function segment(begin,end){
 const a=src.indexOf(begin),b=src.indexOf(end,a+begin.length);
 assert(a>=0&&b>a,'Missing production segment '+begin);
 return src.slice(a,b);
}
const reportGate=segment('function gfReportReady(','function gfReportStatusTab(');
const loader=segment('async function loadCurrentResults(){','const gfAutoResearchState=');
const JOB='1'.repeat(32),SHA='a'.repeat(64),CASE='b'.repeat(64),RUN='2'.repeat(32);
function verified(){
 return {
  cad:{sha256:SHA,parts:[{bbox_mm:{x:50,y:30,z:50},surface_area_mm2:6599}],hole_candidates:[]},
  fea:{state:'complete',result_run_id:RUN,result_case_sha256:CASE,
   maximum_von_mises_mpa:22.632,maximum_displacement_mm:.03971,
   node_count:200,tetrahedron_count:600,conditions_saved:true,
   setup:{material:'steel',force_n:58.84,target_mesh_mm:2},missing_tools:[]},
  fea_case_provenance:{source_verification:'INP_STA_FRD_reverified',
   summary_numbers_crosschecked:true,verified_run_id:RUN,solved_case_sha256:CASE,
   verified_mesh:{nodes:200,tetrahedra:600}},
  ml:{state:'complete',face_count:12},r12_research_status:{state:'complete',candidate_count:4}
 };
}
function make({liveRun=RUN,busy=true}={}){
 const nodes={};let requests=[];
 const $=id=>(nodes[id]??={disabled:true,textContent:'',append(){}});
 const ctx={
  Number,String,Math,Error,Promise,jobId:JOB,current:{sha256:SHA},
  latestSummary:null,resultsRequestGeneration:0,feaRunId:liveRun,
  meshSeriesBusy:busy,file:{name:'L_bracket_correct.step'},$:id=>$(id),
  get:async url=>{requests.push(url);
   if(url==='/api/results/summary/'+JOB)return verified();
   if(url.startsWith('/api/geometry/hole-evidence/'))throw Error('optional geometry evidence unavailable');
   throw Error('Unexpected '+url);},
  gfFeaVerificationSummary:()=>{},gfRenderEvidenceChecklist:()=>{},
  gfMeshFollowupSelection:()=>null,
  gfSetFeaResultNextStep:()=>{},
  textKV:(key,value)=>({key,value}),
  document:{createElement:()=>({textContent:'',className:''})}
 };
 vm.createContext(ctx);
 vm.runInContext(reportGate+'\n'+loader,ctx);
 return {ctx,nodes,requests,call:()=>ctx.loadCurrentResults()};
}
(async()=>{
 const ongoing=make();
 assert.equal(await ongoing.call(),true);
 assert.equal(ongoing.nodes.resultsReportBtn.disabled,false,
  'Verified base CalculiX FEA must unlock REPORT VIEW despite ongoing 3-mesh study');
 assert.equal(ongoing.nodes.resultsReportSaveBtn.disabled,true,
  'Immutable report export must remain locked until mesh study reaches terminal status');
 assert.equal(ongoing.nodes.gfMeshFollowupBtn.disabled,true,
  'Do not allow another mesh study during an existing one');
 assert.match(ongoing.nodes.resultsReportStatus.textContent,/현재 HTML 보고서 보기 가능/);
 assert.match(ongoing.nodes.resultsReportStatus.textContent,/3회 메시 계산 진행 중/);
 assert.equal(ongoing.ctx.gfReportSelectionCurrent(JOB,SHA,RUN,CASE),true);
 const active=make({liveRun:'RUNNING',busy:false});await active.call();
 assert.equal(active.nodes.resultsReportBtn.disabled,true,
  'An active new base solver must hide all previous result actions');
 const stale=make({liveRun:'3'.repeat(32),busy:false});await stale.call();
 assert.equal(stale.nodes.resultsReportBtn.disabled,true,
  'Old same-CAD FEA must never impersonate a newer verified run');
 const done=make({busy:false});await done.call();
 assert.equal(done.nodes.resultsReportBtn.disabled,false);
 assert.equal(done.nodes.resultsReportSaveBtn.disabled,false);
 console.log('PASS: real Results renderer unlocks verified base report while 3 meshes run; protects save, new solver and stale run');
})().catch(err=>{console.error(err);process.exitCode=1});
