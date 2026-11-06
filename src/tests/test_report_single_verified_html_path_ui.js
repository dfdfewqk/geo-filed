'use strict';
// Canonical report builder is shared by preview, auto Stage3 and explicit save.
// Synthetic DOM and responses only: no Gmsh/CalculiX, SQLite mutation or paid API.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8').replace(/\r\n/g,'\n');
const backend=fs.readFileSync(path.join(__dirname,'../payload/GeoField_CAD_Analysis.py'),'utf8');
const begin=src.indexOf('async function gfBuildVisibleReport(');
const end=src.indexOf('// GEOFIELD_AI_MESH_FEEDBACK_UI_V1',begin);
const proofStart=src.indexOf('function gfThreeMeshRequiredReportRows(');
const proofEnd=src.indexOf('function gfAppendMeshFollowup(',proofStart);
const stageStart=src.indexOf('async function gfStage3CompleteReport(');
const stageEnd=src.indexOf('let gfOneClickPreparing=false;',stageStart);
const saveStart=src.indexOf("$('resultsReportSaveBtn').onclick=async()=>{");
const saveEnd=src.indexOf("$('gfMeshFollowupBtn').onclick",saveStart);
assert(begin>0&&end>begin&&proofStart>0&&proofEnd>proofStart);
assert(stageStart>0&&stageEnd>stageStart&&saveStart>0&&saveEnd>saveStart);
assert(!src.slice(stageStart,stageEnd).includes('await gfFetchMeshFollowup('),
 'Stage3 must never issue a second, divergent 3-mesh solver readback');
assert(!src.slice(saveStart,saveEnd).includes('await gfFetchMeshFollowup('),
 'Save must never issue a second solver readback after HTML rendering');
assert(src.slice(saveStart,saveEnd).includes('gfBuildVisibleReport(uid,sha,run,caseSha,false,requireMesh)'));
assert(src.slice(stageStart,stageEnd).includes('gfBuildVisibleReport(uid,sha,run,caseSha,false,requireMesh)'));
assert(backend.includes('def gf_current_verified_report('));
assert(backend.includes('gf_current_verified_report(uid,as_html=html_requested,include_ai=include_ai)'));
assert(backend.includes('gf_current_verified_report(uid,as_html=True)'));
const narrativeStart=src.indexOf('function gfArrangeVerifiedReportSections(');
assert(narrativeStart>0&&narrativeStart<begin&&
 src.slice(narrativeStart,begin).includes('function gfConsolidateReportNarrative('),
 'Report builder must include both production section ordering and narrative cleanup helpers');
const code=src.slice(narrativeStart,end)+'\n'+src.slice(proofStart,proofEnd);
const JOB='1'.repeat(32),SHA='a'.repeat(64),CASE='b'.repeat(64),RUN='2'.repeat(32),STUDY='3'.repeat(32);
const raw='<!doctype html><html lang="ko"><body>'+('verified base FEA origin '.repeat(20))+'</body></html>';
const proof=()=>({id:STUDY,
 runs:[{mesh:3,stress:10,disp:.1},{mesh:2,stress:11,disp:.11},{mesh:1,stress:11.5,disp:.115}],
 steps:[{stress:100/11,disp:100/11},{stress:50/11.5,disp:100*(.115-.11)/.115}]});
function make({mesh=true,requireStudy=false,missingRow=false,wrongValue=false,wrongStudy=false,
               duplicated=false,staleAgent=false,staleExternal=false,unverifiedSection=false,
               changedSelection=false}={}){
 const calls={fetch:[],mesh:[],paid:[],visual:[]},elements=new Map();
 const evidence={querySelectorAll:()=>[],
  insertAdjacentElement(_where,node){elements.set(node.id,node)}};
 elements.set('geofield-a08-evidence',evidence);
 for(const id of staleAgent?['geofield-agent-report']:[])elements.set(id,{remove(){elements.delete(id)}});
 if(staleExternal)elements.set('geofield-external-llm-report',{remove(){elements.delete('geofield-external-llm-report')}});
 const parsed={body:{firstChild:{},append(x){elements.set(x.id,x)},insertBefore(x){elements.set(x.id,x)}},
  getElementById:id=>elements.get(id)||null,
  createElement(tag){return{tag,id:'',textContent:'',style:{},children:[],append(...items){this.children.push(...items)}}}};
 parsed.documentElement={get outerHTML(){
   const section=elements.get('geofield-ai-mesh-followup-report');
   return '<html><body>'+raw+
    (section?'<section id="geofield-ai-mesh-followup-report">'+
     section.querySelectorAll('p').map(x=>x.textContent).join('|')+'</section>':'')+
    '</body></html>';
 }};
 if(unverifiedSection)elements.set('geofield-ai-mesh-followup-report',{
   getAttribute:()=>STUDY,querySelectorAll:()=>[]});
 const context={
  Math,Number,Array,String,JSON,Error,Promise,encodeURIComponent,
  DOMParser:class{parseFromString(){return parsed}},
  gfReportSelectionCurrent:()=>!changedSelection,
  gfInteractiveReportBlockedMessage:()=> 'stale CAD/FEA',
  // The real FRD rehydration helper is in the builder; this isolated HTML
  // dispatcher has no WebGL field, so it safely stays on its numeric path.
  gfFeaReportFieldMatches:()=>false,
  jobId:JOB,current:{sha256:SHA},feaRunId:RUN,meshSeriesBusy:false,
  fetch:async(url,options)=>{calls.fetch.push({url,options});return {ok:true,status:200,text:async()=>raw}},
  gfFetchMeshFollowup:async()=>{calls.mesh.push('current-run');return mesh?proof():null},
  gfReverifiedD6ReportPair:async()=>null,
  gfAppendD6ComparisonReport:()=>{},
  gfAppendEvidenceScope:()=>{},
  gfFetchR12ReportProof:async()=>({proof:null,note:'연구용 결과 없음'}),
  gfAppendR12ReportProof:()=>false,
  // Stage 5 is an additional read-only, optional visual appendix. This
  // isolated unit tests the canonical builder; renderer has its own test.
  gfAppendFeaReportViews:(_parsed,_evidence,uid,sha,run,caseSha)=>{
   calls.visual.push({uid,sha,run,caseSha});return false;
  },
  gfAppendMeshFollowup:(_parsed,_anchor,study)=>{
   if(!study)return;
   const rows=Array.from(context.gfThreeMeshRequiredReportRows(study));
   if(missingRow)rows.splice(1,1);
   if(wrongValue)rows[1]=rows[1].replace('11.00000','12.00000');
   if(duplicated)rows.push(rows[2]);
   const section={getAttribute:key=>key==='data-gf-mesh-study-id'?
    (wrongStudy?'4'.repeat(32):STUDY):null,
    querySelectorAll:sel=>sel==='p'?rows.map(textContent=>({textContent})):[]};
   elements.set('geofield-ai-mesh-followup-report',section);
  },
  get:async(url,timeout,headers)=>{
   if(url==='/api/ml/latest/'+JOB)return {status:'not_run',cad_job_id:JOB,cad_sha256:SHA};
   calls.paid.push({url,timeout,headers});
   return {schema:'geofield-evidence-agent-v1',cad_sha256:SHA,mode:'rules_plus_llm',
     fea:{status:'INP_STA_FRD_reverified',run_id:RUN,case_sha256:CASE},
     llm:{connected:true,executed:true,status:'external_explanation_only',
       provider:'deepseek',explanation:'explicit one-shot review'}}
  }
 };
 vm.createContext(context);vm.runInContext(code,context);
 // The full source guard is tested with missing/mismatched research and
 // FRD in test_report_completeness_paid_ai_guard_ui.js. Keep builder
 // dispatch / opt-in counting fixture independent of those external data.
 assert(src.includes('gfRequireCompletePaidReportEvidence(parsed,meshFollowup,brepProof,r12Proof,uid,sha,run,caseSha)'));
 context.gfRequireCompletePaidReportEvidence=()=>true;
 return{context,calls,
  build:(includeExternal=false,mandatory=requireStudy)=>
   context.gfBuildVisibleReport(JOB,SHA,RUN,CASE,includeExternal,mandatory)};
}
(async()=>{
 const base=make({mesh:false,staleAgent:true,staleExternal:true});
 const basicHtml=await base.build();
 assert.match(basicHtml,/verified base FEA origin/);
 assert.equal(base.calls.fetch.length,1);
 assert.equal(base.calls.mesh.length,1);
 assert.equal(base.calls.paid.length,0,'AI OFF must not call paid service');
 const requiredMissing=make({mesh:false});
 await assert.rejects(requiredMissing.build(false,true),/3회 메시 원본 재검증/);
 assert.equal(requiredMissing.calls.paid.length,0);
 const valid=make();
 const rich=await valid.build(false,true);
 for(const row of valid.context.gfThreeMeshRequiredReportRows(proof()))
  assert(rich.includes(row),'verified numeric row missing: '+row);
 assert.equal(valid.calls.fetch.length,1);
 assert.equal(valid.calls.mesh.length,1,'one report = one server mesh readback');
 assert.equal(valid.calls.visual.length,1,'verified view section follows the same canonical report path');
 assert.equal(valid.calls.visual[0].run,RUN,'visual selection must use the same actual FEA run');
 assert.equal(valid.calls.paid.length,0);
 for(const scenario of [
  {missingRow:true},{wrongValue:true},{wrongStudy:true},{duplicated:true}
 ]){
  const test=make(scenario);
  await assert.rejects(test.build(false,true),/5개 행/,JSON.stringify(scenario));
  assert.equal(test.calls.mesh.length,1);
  assert.equal(test.calls.paid.length,0);
 }
 const malicious=make({mesh:false,unverifiedSection:true});
 await assert.rejects(malicious.build(),/검증되지 않은 과거 메시 연구/);
 const stale=make({changedSelection:true});
 await assert.rejects(stale.build(),/CAD 또는 FEA 원본 실행이 변경/);
 const explicit=make();
 const withAi=await explicit.build(true,true);
 assert.match(withAi,/geofield-ai-mesh-followup-report/);
 assert.equal(explicit.calls.paid.length,1);
 assert.equal(explicit.calls.paid[0].headers['X-GeoField-LLM-Opt-In'],'1');
 assert.equal(explicit.calls.fetch[0].url,'/api/results/report/'+JOB+'?include_ai=1');
 console.log('PASS: one verified HTML builder, one mesh readback, five numeric rows, AI OFF, explicitly opted-in ON, preview/save/Stage3 contracts');
})().catch(error=>{console.error(error);process.exitCode=1});
