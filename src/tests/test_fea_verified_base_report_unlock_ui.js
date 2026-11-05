'use strict';
// Regression for the user's 2026-11-05 Windows video: the real CalculiX
// stress/3D view was present, but the integrated HTML report button stayed grey.
// Synthetic browser only: no STEP overwrite, solver restart, SQLite or paid API.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const js=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const JOB='1'.repeat(32),SHA='a'.repeat(64),RUN='2'.repeat(32),CASE='b'.repeat(64);
const OTHER='3'.repeat(32);
const a=js.indexOf('function gfReportReady(');
const b=js.indexOf('function gfInteractiveReportBlockedMessage(',a);
const c=js.indexOf('async function loadCurrentResults()');
const d=js.indexOf('const gfAutoResearchState=',c);
assert(a>0&&b>a&&c>b&&d>c,'Production report and Results tab contracts must exist');
assert.match(js,/meshSeriesBusy=true;meshSeriesStatusUnknown=false;[\s\S]{0,440}void loadCurrentResults\(\);/,
 'Start of optional mesh study must recheck verified base report');
assert.match(js,/meshSeriesReset\(\);[\s\S]{0,250}void loadCurrentResults\(\);/,
 'Terminal end of optional mesh study must recheck final report eligibility');
const base=()=>({cad:{sha256:SHA,parts:[],hole_candidates:[]},
 ml:{state:'complete',face_count:24,status_text:'done'},
 r12_research_status:{state:'complete',candidate_count:3},
 fea:{state:'complete',result_run_id:RUN,result_case_sha256:CASE,
  maximum_von_mises_mpa:22.632,maximum_displacement_mm:0.03971,
  node_count:400,tetrahedron_count:1200,missing_tools:[],
  conditions_saved:true,setup:{material:'steel',force_n:58.84,target_mesh_mm:1.8}},
 fea_case_provenance:{source_verification:'INP_STA_FRD_reverified',
  summary_numbers_crosschecked:true,verified_run_id:RUN,
  solved_case_sha256:CASE,result_matches_saved:true,
  verified_mesh:{nodes:400,tetrahedra:1200}}});
function make({busy=false,run=RUN,summary=base(),summaryError=false}={}){
 const elements=new Map(),trace=[],nextSteps=[],summaryGets=[];
 const $=id=>{
  if(!elements.has(id))elements.set(id,{disabled:false,textContent:'',append(){},children:[]});
  return elements.get(id);
 };
 const ctx={
  String,Number,Math,Error,Promise,jobId:JOB,current:{sha256:SHA},
  latestSummary:null,feaRunId:run,meshSeriesBusy:busy,file:{name:'L_bracket.step'},
  $,
  get:async url=>{
   trace.push(url);
   if(url==='/api/results/summary/'+JOB){
    summaryGets.push(url);
    if(summaryError)throw Error('synthetic backend failure');
    return summary;
   }
   if(url==='/api/geometry/hole-evidence/'+JOB)throw Error('optional OCP unavailable');
   throw Error('Unexpected network request '+url);
  },
  gfRenderEvidenceChecklist:()=>{},
  gfFeaVerificationSummary:()=>{},
  gfMeshFollowupSelection:()=>null,
  gfFetchMeshFollowup:async()=>{throw Error('No three-mesh result in this test');},
  gfSetFeaResultNextStep:state=>nextSteps.push(state),
  textKV:(label,value)=>({label,value}),
  document:{createElement:()=>({className:'',textContent:''})},
 };
 vm.createContext(ctx);
 vm.runInContext('let resultsRequestGeneration=0;\n'+
  js.slice(a,b)+'\n'+js.slice(b,c).slice(0,js.slice(b,c).indexOf('function gfReportStatusTab('))+
  '\n'+js.slice(c,d),ctx);
 return{ctx,$,trace,nextSteps,summaryGets,refresh:()=>ctx.loadCurrentResults()};
}
(async()=>{
 const runningMesh=make({busy:true});
 assert.equal(await runningMesh.refresh(),true);
 assert.equal(runningMesh.$('resultsReportBtn').disabled,false,
  'VERIFIED base FEA report must be clickable while three-mesh is running');
 assert.equal(runningMesh.$('resultsReportSaveBtn').disabled,true,
  'Incomplete three-mesh result must not be exported as completed');
 assert.equal(runningMesh.$('gfMeshFollowupBtn').disabled,true);
 assert.match(runningMesh.$('resultsReportStatus').textContent,/보기 가능/);
 assert.equal(runningMesh.summaryGets.length,1);
 assert.equal(runningMesh.trace.filter(x=>x.startsWith('/api/agent')).length,0);
 const completedMesh=make();
 assert.equal(await completedMesh.refresh(),true);
 assert.equal(completedMesh.$('resultsReportBtn').disabled,false);
 assert.equal(completedMesh.$('resultsReportSaveBtn').disabled,false);
 for(const opt of [
  {run:'RUNNING',label:'New base solver in progress'},
  {run:OTHER,label:'Different FEA execution'},
  {summary:(()=>{const s=base();s.fea_case_provenance.summary_numbers_crosschecked=false;return s;})(),
   label:'Unverified FEA numbers'},
  {summary:(()=>{const s=base();s.fea_case_provenance.verified_run_id=OTHER;return s;})(),
   label:'Provenance is for another FEA run'},
  {summaryError:true,label:'Summary endpoint failed'},
 ]){
  const caseTest=make({...opt,busy:true});
  await caseTest.refresh();
  assert.equal(caseTest.$('resultsReportBtn').disabled,true,opt.label);
  assert.equal(caseTest.$('resultsReportSaveBtn').disabled,true,opt.label);
 }
 console.log('PASS: real-report button unlocks on verified base solve, remains locked on stale FEA, mesh export waits, source refreshes at both transitions');
})().catch(err=>{console.error(err);process.exitCode=1});
