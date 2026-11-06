'use strict';
// Production native report handlers: synthetic HTML, FEA summaries and AI only.
// No real paid calls, solver, SQLite write, browser or Windows installation.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'..','payload','frontend','index.html'),'utf8');
const a=src.indexOf('function gfReportReady('),b=src.indexOf("$('collapseBtn').onclick",a);
assert(a>0&&b>a&&src.slice(a,b).includes('GEOFIELD_UNIFIED_REPORT_AI_V1'));
assert.equal((html.match(/id="reportAiIncludeToggle"/g)||[]).length,1);
assert(html.indexOf('id="reportAiIncludeToggle"')<html.indexOf('id="resultsReportBtn"'));
const CAD='a'.repeat(64),CASE='b'.repeat(64),JOB='1'.repeat(32),RUN='2'.repeat(32);
const valid=()=>({cad:{sha256:CAD},fea:{
 state:'complete',result_run_id:RUN,result_case_sha256:CASE,
 maximum_von_mises_mpa:12.5,maximum_displacement_mm:.03,
 node_count:450,tetrahedron_count:1800},
 fea_case_provenance:{source_verification:'INP_STA_FRD_reverified',
 summary_numbers_crosschecked:true,verified_run_id:RUN,solved_case_sha256:CASE,
 verified_mesh:{nodes:450,tetrahedra:1800}}});
const rawReport='<!doctype html><html lang="ko"><body>verified FEA numbers '.repeat(12)+'</body></html>';
const aiOK=()=>({schema:'geofield-evidence-agent-v1',cad_sha256:CAD,mode:'rules_plus_llm',
 fea:{status:'INP_STA_FRD_reverified',run_id:RUN,case_sha256:CASE},
 llm:{provider:'deepseek',connected:true,executed:true,status:'external_explanation_only',
 explanation:'[1. 응력 집중 검토] 가설 [2. 재료·하중 평가] 확인 [3. 설계 개선 가설] 재해석 [4. 추가 해석·검증 순서] 비교'}});
function fakeDoc(){
 const added=[],oldAi={removed:false,remove(){this.removed=true}};
 const evidence={paragraphs:[{textContent:'DeepSeek 설명: 표시 불가 (과거 안내)',remove(){this.textContent=''}}],
  querySelectorAll(){return this.paragraphs;},
  insertAdjacentElement(pos,item){assert.equal(pos,'afterend');added.push(item);}};
 const body={firstChild:{},insertBefore(item){added.push(item)},append(item){added.push(item)}};
 const parsed={
  body,createElement(tag){return{tag,id:'',textContent:'',children:[],style:{},append(...args){this.children.push(...args)}}},
  getElementById(id){if(id==='geofield-a08-evidence')return evidence;
    if(id==='geofield-optional-external-ai')return oldAi.removed?null:oldAi;
    return null},
 };
 parsed.documentElement={get outerHTML(){
  const describe=n=>[n.textContent||'',...(n.children||[]).map(describe)].join(' ');
  return '<html><body>verified FEA numbers '+evidence.paragraphs[0].textContent+' '+
   added.map(describe).join(' ')+'</body></html>';
 }};
 return parsed;
}
function make(){
 const nodes={resultsReportBtn:{disabled:false},resultsReportSaveBtn:{disabled:false},
  resultsReportStatus:{textContent:''},resultsReportSavedPath:{textContent:''},
  reportAiIncludeToggle:{checked:false},gfMeshFollowupBtn:{disabled:false},gfMeshFollowupStatus:{textContent:''},gfD6VariantBtn:{disabled:false},gfD6VariantStatus:{textContent:''}};
 const tabs=[],requests=[],paid=[],downloads=[],replies=[],errors=[];
 const ctx={
  String,Math,Number,Error,Promise,Date,encodeURIComponent,Blob,
  jobId:JOB,current:{sha256:CAD},latestSummary:valid(),feaRunId:null,meshSeriesBusy:false,
  $:id=>nodes[id],DOMParser:class{parseFromString(){return fakeDoc()}},
  window:{open:()=>{const tab={closed:false,writes:[],document:{
   open(){},write(v){tab.writes.push(v)},close(){},
   getElementById:()=>({textContent:''})}};tabs.push(tab);return tab;},
   confirm:()=>true},
  get:async(url,timeout,headers)=>{
    if(url==='/api/ml/latest/'+JOB)return {status:'not_run',cad_job_id:JOB,cad_sha256:CAD};
    paid.push({url,timeout,headers});
    if(errors.length)throw errors.shift();
    return replies.length?replies.shift():aiOK();},
  fetch:async(url,opt)=>{requests.push({url,opt});
    if(opt?.method==='POST')return {ok:true,status:200,json:async()=>({
     ok:true,format:'html',saved:true,reused:false,run_id:RUN,sha256:'f'.repeat(64),path:'test.html'})};
    return {ok:true,status:200,text:async()=>rawReport};},
  document:{body:{append(){}},createElement:()=>({href:'',download:'',click(){downloads.push(this.download)},remove(){}})},
  URL:{createObjectURL:()=> 'blob:test-report',revokeObjectURL(){}},
  setTimeout:()=>{},
 };
 // The production report now includes the shared conservative engineering
// review helper; load it in the isolated DOM test before the report handlers.
const step2Start=src.indexOf('function gfEngineeringStage2Review(');
const step2End=src.indexOf('function gfEvidenceChecklistLines(',step2Start);
assert(step2Start>0&&step2End>step2Start);
vm.createContext(ctx);
vm.runInContext(src.slice(step2Start,step2End)+'\n'+src.slice(a,b),ctx);
 // This existing test isolates UI click/opt-in behavior. The actual paid
 // completeness gate is checked exhaustively in test_report_completeness_paid_ai_guard_ui.js.
 assert(src.includes('gfRequireCompletePaidReportEvidence(parsed,meshFollowup,brepProof,r12Proof,uid,sha,run,caseSha)'));
 ctx.gfRequireCompletePaidReportEvidence=()=>true;
 return {ctx,nodes,tabs,requests,paid,downloads,replies,errors};
}
(async()=>{
 const t=make();
 assert.equal(t.ctx.gfReportReady(valid(),CAD),true);
 for(const f of [
  d=>d.fea.state='failed',d=>d.fea_case_provenance.summary_numbers_crosschecked=false,
  d=>d.fea.maximum_von_mises_mpa=null,d=>d.fea.maximum_displacement_mm=-1,
  d=>d.fea_case_provenance.verified_mesh.nodes=449,
  d=>d.cad.sha256='c'.repeat(64)
 ]){const d=valid();f(d);assert.equal(t.ctx.gfReportReady(d,CAD),false);}
 t.ctx.latestSummary={...valid(),fea:{...valid().fea,state:'queued'}};
 await t.ctx.$('resultsReportBtn').onclick();
 assert.equal(t.tabs.length,0,'Unverified FEA must not open a report');
 t.ctx.latestSummary=valid();
 // User Windows capture: CalculiX base FEA is already verified and shown in
 // 3D, but the report button remained disabled because three-mesh study ran.
 // Preview the VERIFIED base immediately; do not invent mesh completion or
 // allow an early immutable save. A paid AI request still requires an explicit
 // ON switch AND a direct click; no automatic request is ever made.
 const busy=make();busy.ctx.meshSeriesBusy=true;busy.ctx.feaRunId=RUN;
 assert.equal(busy.ctx.gfReportSelectionCurrent(JOB,CAD,RUN,CASE),true);
 busy.nodes.reportAiIncludeToggle.checked=true;
 await busy.ctx.$('resultsReportBtn').onclick();
 assert.equal(busy.tabs.length,1,'Verified original FEA preview must work during ongoing mesh study');
 assert.equal(busy.paid.length,1,'External AI call is only one explicitly opted-in click');
 assert.match(busy.tabs[0].writes.at(-1),/3단계: 현재 실제 계산 진행 중/);
 assert.doesNotMatch(busy.tabs[0].writes.at(-1),/3단계 실제 FEA 검증 완료/);
 assert.equal(busy.nodes.reportAiIncludeToggle.checked,false,'One-shot AI consent must reset');
 await busy.ctx.$('resultsReportSaveBtn').onclick();
 assert.equal(busy.requests.filter(x=>x.opt?.method==='POST').length,0,
  'Never save incomplete three-mesh report into immutable archive');
 assert.match(busy.nodes.resultsReportStatus.textContent,/저장은 계산 종료 후/);
 busy.ctx.meshSeriesBusy=false;
 await busy.ctx.$('resultsReportBtn').onclick();
 assert.equal(busy.tabs.length,2,'Original verified FEA remains previewable after study terminates');
 assert.equal(busy.paid.length,1,'Automatic mesh completion never charges external AI');
 const pending=make();pending.ctx.feaRunId='RUNNING';
 await pending.ctx.$('resultsReportBtn').onclick();
 assert.equal(pending.tabs.length,0,'Previous result cannot be previewed as a running FEA');
 assert.match(pending.nodes.resultsReportStatus.textContent,/새 실제 FEA 계산 진행 중/);
 assert(src.includes('const reportInteractive=ready&&gfReportSelectionCurrent(expectedId,expectedSha,'),
  'Results panel must disable report/save buttons until same-run evidence and study are ready');
 // OFF: never call a paid AI; the baseline contains verified numbers.
 await t.ctx.$('resultsReportBtn').onclick();
 assert.equal(t.paid.length,0);
 assert.equal(t.requests[0].url,'/api/results/report/'+JOB);
 assert(t.tabs[0].writes.at(-1).includes('verified FEA numbers'));
 assert.match(t.tabs[0].writes.at(-1),/이번 보고서에서 실제 확인한 범위/);
 assert.match(t.tabs[0].writes.at(-1),/실제 INP·STA·FRD 파일과 응력·변위 수치 재검증 완료/);
 assert.match(t.tabs[0].writes.at(-1),/메시 민감도 3단계: 이번 보고서에 연결된 완료 결과 없음/);
 assert.match(t.tabs[0].writes.at(-1),/D6 원본·변경본: 이번 보고서에 연결된 A\/B 완료 기록 없음/);
 assert(!t.tabs[0].writes.at(-1).includes('공학 AI 분석 · 응력/재료'));
 assert(!t.tabs[0].writes.at(-1).includes('DeepSeek 설명: 표시 불가'));
 assert(!t.tabs[0].writes.at(-1).includes('로컬 AI:'));
 // ON: direct click => exactly one opted-in provider request, switch resets.
 t.nodes.reportAiIncludeToggle.checked=true;
 await t.ctx.$('resultsReportBtn').onclick();
 assert.equal(t.paid.length,1);
 assert.equal(t.paid[0].url,'/api/agent/evidence/'+JOB+'?llm=1');
 assert(t.requests.some(x=>x.url==='/api/results/report/'+JOB+'?include_ai=1'));
 assert.equal(t.paid[0].headers['X-GeoField-LLM-Opt-In'],'1');
 assert.equal(t.paid[0].timeout,70000);
 assert.equal(t.nodes.reportAiIncludeToggle.checked,false);
 assert.match(t.tabs[1].writes.at(-1),/공학 AI 분석 · 응력/);
 assert.match(t.tabs[1].writes.at(-1),/응력 집중 검토/);
 assert.match(t.tabs[1].writes.at(-1),/verified FEA numbers/);
 // Provider error must keep report, never present fictitious success.
 t.nodes.reportAiIncludeToggle.checked=true;
 t.errors.push(Error('simulated provider unavailable'));
 await t.ctx.$('resultsReportBtn').onclick();
 assert.equal(t.paid.length,2);
 assert.match(t.tabs[2].writes.at(-1),/외부 AI 설명 미확인/);
 assert.match(t.tabs[2].writes.at(-1),/verified FEA numbers/);
 // If an external model claims unrun D6 screening passed, report the guard
 // explicitly in Korean, without losing the independently verified FEA HTML.
 const rejected=make();
 rejected.nodes.reportAiIncludeToggle.checked=true;
 rejected.replies.push({schema:'geofield-evidence-agent-v1',cad_sha256:CAD,
  mode:'rules_only',fea:{status:'INP_STA_FRD_reverified',run_id:RUN,case_sha256:CASE},
  llm:{provider:'deepseek',executed:false,connected:false,status:'unsupported_claim_blocked'}});
 await rejected.ctx.$('resultsReportBtn').onclick();
 assert.match(rejected.tabs[0].writes.at(-1),/근거 없는 D6\/INP 검사 통과 주장 차단/);
 assert.match(rejected.tabs[0].writes.at(-1),/근거 없는 D6\/INP 검사 통과를 주장하여 설명을 차단/);
 assert.match(rejected.tabs[0].writes.at(-1),/verified FEA numbers/);
 assert.equal(rejected.paid.length,1);
 // OFF save downloads the same assembled HTML as Preview and also retains the
 // separate immutable SERVER base-FEA archive without pretending it contains mesh/D6 additions.
 await t.ctx.$('resultsReportSaveBtn').onclick();
 const post=t.requests.find(x=>x.opt?.method==='POST');
 assert(post);
 assert.equal(post.url,'/api/results/report-save/'+JOB);
 assert.equal(post.opt.headers['X-GeoField-Report-Export'],'EXPLICIT_SAVE');
 assert.equal(t.downloads.length,1,'OFF must download the same unified HTML builder used by Preview');
 assert.match(t.downloads[0],/^GeoField_Integrated_Verified_/);
 assert.match(t.nodes.resultsReportStatus.textContent,/화면과 같은 AI OFF 통합 HTML/);
 assert.match(t.nodes.resultsReportSavedPath.textContent,/서버 기본 파일에는 브라우저 추가 메시\/D6 부록이 포함되지 않습니다/);
 assert.equal(t.paid.length,2,'OFF save must never call external LLM');
 // ON save is a browser download, not persisted into the solver/SQLite archive.
 t.nodes.reportAiIncludeToggle.checked=true;
 await t.ctx.$('resultsReportSaveBtn').onclick();
 assert.equal(t.paid.length,3);
 assert.equal(t.nodes.reportAiIncludeToggle.checked,false);
 assert.equal(t.downloads.length,2);
 assert.match(t.downloads[1],/^GeoField_Engineering_AI_/);
 assert.equal(t.requests.filter(x=>x.opt?.method==='POST').length,1);
 assert.match(src,/2D 투영\(가림 미검증\)/);
 console.log('PASS: report OFF visible-HTML download + separate immutable base archive, explicit ON one-shot, no AI with OFF');
})().catch(e=>{console.error(e);process.exitCode=1});
