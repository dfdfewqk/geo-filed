'use strict';
// Exact-run CAD/FEA + background research status synchronization contract.
// Evaluates real production functions; synthetic browser state only.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
function slice(from,to){
 const a=src.indexOf(from),b=src.indexOf(to,a+from.length);
 assert(a>=0&&b>a,'Missing production function '+from);
 return src.slice(a,b);
}
const JOB='1'.repeat(32),SHA='a'.repeat(64),CASE='b'.repeat(64);
const OLD='2'.repeat(32),NEW='3'.repeat(32);
const reportGate=new Function('jobId','current','latestSummary','feaRunId',
 'meshSeriesBusy','gfReportReady',
 slice('function gfReportSelectionCurrent(','// The base FEA may be independently verified')+
 'return gfReportSelectionCurrent;');
const oldSummary={cad:{sha256:SHA},fea_case_provenance:{
 verified_run_id:OLD,solved_case_sha256:CASE}};
const newSummary={cad:{sha256:SHA},fea_case_provenance:{
 verified_run_id:NEW,solved_case_sha256:CASE}};
assert.equal(reportGate(JOB,{sha256:SHA},oldSummary,NEW,false,()=>true)(JOB,SHA,OLD,CASE),
 false,'Verified OLD FEA run must not become new-run proof on identical STEP/CASE');
assert.equal(reportGate(JOB,{sha256:SHA},newSummary,NEW,false,()=>true)(JOB,SHA,NEW,CASE),
 true);
assert.equal(reportGate(JOB,{sha256:SHA},newSummary,NEW,true,()=>true)(JOB,SHA,NEW,CASE),
 true,'Current verified base FEA preview remains available during independent mesh study');
assert.equal(reportGate(JOB,{sha256:SHA},newSummary,'RUNNING',false,()=>true)(JOB,SHA,NEW,CASE),
 false);
assert.equal(reportGate(JOB,{sha256:SHA},newSummary,null,false,()=>true)(JOB,SHA,NEW,CASE),
 true,'Verified historical read-only case with no active new local run is still supported');
const allOneClick=slice("$('feaRunBtn').onclick=async()=>",'// Read-only historical mode');
const gates=allOneClick.match(/gfReportSelectionCurrent\(jobAtStart,shaAtStart,run.id,caseAtStart\)/g)||[];
assert.equal(gates.length,4,
 'The initial check, bounded rechecks and final one-click continuation must all bind to new run ID');
const research= slice('function gfResearchEvidenceUpdated(','// Read-only evidence-based agent;');
function make(){
 const calls=[],btn={disabled:false,dataset:{},onclick:()=>{
  calls.push({automaticLocal:btn.dataset.gfAutoLocalOnly==='1',paidFlag:false});
 }};
 const state={uid:JOB,sha:SHA,active:'integration',feaRunId:NEW,meshSeriesBusy:false,
  jobId:JOB,current:{sha256:SHA},stepSelectionVersion:2,feaPreparedCaseSha:CASE,
  gfRestoredRunId:null};
 const gf=new Function('$','getState',research.replace(
   /function gfResearchEvidenceUpdated\(/,
   'function gfResearchEvidenceUpdated('
 )+ 'return {updated:gfResearchEvidenceUpdated,auto:gfMaybeAutoAnalyze,revision:()=>gfResearchEvidenceRevision,key:()=>gfLastAutoAnalysisKey};');
 // Production functions expect bare source variables as lexical bindings.
 const body= 'let gfResearchEvidenceRevision=0,gfLastAutoAnalysisKey=null;'+
  'let active=state.active,jobId=state.jobId,current=state.current,'+
  'stepSelectionVersion=state.stepSelectionVersion,feaRunId=state.feaRunId,'+
  'feaPreparedCaseSha=state.feaPreparedCaseSha,gfRestoredRunId=state.gfRestoredRunId,'+
  'meshSeriesBusy=state.meshSeriesBusy;'+
  research+
  'return {updated:gfResearchEvidenceUpdated,auto:gfMaybeAutoAnalyze,'+
  'setBusy:x=>{meshSeriesBusy=x},setActive:x=>{active=x},'+
  'revision:()=>gfResearchEvidenceRevision,key:()=>gfLastAutoAnalysisKey};';
 const unit=new Function('state','$',body)(state,id=>id==='agentRunBtn'?btn:null);
 return{calls,btn,unit};
}
const t=make();
t.unit.auto();assert.equal(t.calls.length,1);
assert(t.calls[0].automaticLocal,'Opening Results should ONLY use rules-only mode');
t.unit.auto();assert.equal(t.calls.length,1,'No redundant same-run local AI request');
t.unit.updated(JOB,'f'.repeat(64));assert.equal(t.calls.length,1);
assert.equal(t.unit.revision(),0,'Different CAD SHA must not update local agent');
t.unit.updated(JOB,SHA);assert.equal(t.calls.length,2);
assert(t.calls[1].automaticLocal,'ML completion must not consume paid API opt-in');
t.unit.setBusy(true);t.unit.updated(JOB,SHA);
assert.equal(t.calls.length,2,'Do not refresh while the real mesh study is active');
t.unit.setBusy(false);t.unit.auto();
assert.equal(t.calls.length,3,'Resume after study only in local rules-only mode');
t.btn.disabled=true;t.unit.updated(JOB,SHA);assert.equal(t.calls.length,3);
t.btn.disabled=false;t.unit.auto();assert.equal(t.calls.length,4);
t.unit.setActive('cad');t.unit.updated(JOB,SHA);
assert.equal(t.calls.length,5,'New same-STEP ML result refreshes the local agent even when a different tab is open');
assert.equal(t.calls[4].automaticLocal,true,'Background handoff must remain rules-only without paid opt-in');
assert(src.includes('researchRevisionAtStart!==gfResearchEvidenceRevision'),
 'An in-flight local request must refresh when ML finishes during that request');
for(const callsite of [
 "gfResearchEvidenceUpdated(cadId,expectedSha);"
]) assert(src.includes(callsite),'Research watcher terminal update must invalidate stale local AI');
console.log('PASS: new FEA run cannot reuse prior same-STEP proof; terminal ML/R12 updates only refresh local rules AI, never paid API');
