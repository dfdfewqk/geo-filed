'use strict';
// Stage 3 uses existing verified server HTML + bounded 3-mesh appendix.
// Runs synthetic browser state only: no STEP, SQLite, solver or external LLM.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const js=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8').replace(/\r\n/g,'\n');
const html=fs.readFileSync(path.join(__dirname,'../payload/frontend/index.html'),'utf8');
const start=js.indexOf('// GEOFIELD_STAGE3_AUTO_UNIFIED_REPORT_20261105');
const end=js.indexOf('let gfOneClickPreparing=false;',start);
assert(start>0&&end>start,'auto report source contract missing');
assert.equal((html.match(/id="gfAutoUnifiedStatus"/g)||[]).length,1);
assert(js.indexOf('await gfAutoStage2Verification(',end)>end);
assert(js.indexOf('await gfStage3CompleteReport(',end)>js.indexOf('await gfAutoStage2Verification(',end));
assert(js.includes('gfStage3Generated=null;\n if($(\'gfAutoUnifiedStatus\'))'));
const contract=js.slice(start,end);
assert(!contract.includes('await gfFetchMeshFollowup(uid,sha,run,caseSha)'),
 'Stage3 must not duplicate the canonical report builder\'s real solver readback');
assert(contract.includes('gfBuildVisibleReport(uid,sha,run,caseSha,false,requireMesh)'),
 'Stage3 must use canonical builder with explicit mandatory mesh contract');
const proofStart=js.indexOf('function gfThreeMeshRequiredReportRows(');
const proofEnd=js.indexOf('function gfAppendMeshFollowup(',proofStart);
assert(proofStart>0&&proofEnd>proofStart,'actual numeric HTML contract required');
const numericProof=js.slice(proofStart,proofEnd);
const JOB='1'.repeat(32),SHA='a'.repeat(64),CASE='b'.repeat(64),RUN='2'.repeat(32),STUDY='3'.repeat(32);
const valid=()=>({cad:{sha256:SHA},ml:{state:'complete'},r12_research_status:{state:'complete'},
 fea:{maximum_von_mises_mpa:14.758,maximum_displacement_mm:.0264},
 fea_case_provenance:{verified_run_id:RUN,solved_case_sha256:CASE}});
const body='<html lang="ko"><body>'+('verified CAD ML FEA local evidence '.repeat(15))+'</body></html>';
const verifiedStudy=()=>({id:STUDY,
 runs:[{mesh:3,stress:10,disp:.1},{mesh:2,stress:11,disp:.11},
       {mesh:1,stress:11.5,disp:.115}],
 steps:[{stress:100/11,disp:100/11},
        {stress:50/11.5,disp:100*(.115-.11)/.115}]});
function make({trusted=true,mesh=true,reportMesh=true,reportAI=false,paidStale=false,
               staleAfterBuild=false,badFaa=false,buildError=false,validMeshReadback=true,
               missingRow=false,wrongNumbers=false,duplicateRow=false,wrongStudyId=false}={}){
 const calls=[],nodes={gfAutoUnifiedStatus:{textContent:''}},selection={current:true};
 const ctx={
  Math,Number,String,Error,Promise,latestSummary:valid(),
  gfResearchEvidenceRevision:0,gfOneClickInProgress:false,
  jobId:JOB,current:{sha256:SHA},feaRunId:RUN,meshSeriesBusy:false,
  $:id=>nodes[id]??null,
  gfReportSelectionCurrent:(uid,sha,run,caseSha)=>trusted&&selection.current&&
   ctx.jobId===uid&&ctx.current?.sha256===sha&&ctx.feaRunId===run&&caseSha===CASE,
  gfMeshFollowupSelection:()=>mesh?{id:STUDY}:null,
  gfFetchMeshFollowup:async()=>mesh&&validMeshReadback?verifiedStudy():null,
  gfBuildVisibleReport:async(...args)=>{
   calls.push(args);
   // Simulate the production builder's uniform final acceptance gate.
   const requireMesh=args[5]===true;
   if(requireMesh&&(!mesh||!validMeshReadback))
    throw Error('3회 메시 원본 재검증을 완료하지 못했습니다.');
   if(mesh&&validMeshReadback){
    // The real canonical builder invokes the SAME numeric DOM proof. A
    // stubbed HTML result must not silently bypass missing/stale run rows.
    const generated=new ctx.DOMParser().parseFromString(body,'text/html');
    if(!ctx.gfThreeMeshRenderedReportComplete(generated,verifiedStudy()))
     throw Error('검증된 3회 메시 수치 5개 행이 통합 HTML에 누락됐습니다.');
   }
   if(staleAfterBuild)selection.current=false;
   if(buildError)throw Error('simulated HTML endpoint unavailable');
   return body;
  },
  DOMParser:class{parseFromString(){
   const study=verifiedStudy();
   const required=[
    '1단계 · 목표 메시 3.000 mm · 최대 응력 10.00000 MPa · 최대 변위 0.100000 mm',
    '2단계 · 목표 메시 2.000 mm · 최대 응력 11.00000 MPa · 최대 변위 0.110000 mm',
    '3단계 · 목표 메시 1.000 mm · 최대 응력 11.50000 MPa · 최대 변위 0.115000 mm',
    '1→2 단계 변화율 · 응력 '+(100/11).toFixed(3)+'% · 변위 '+(100/11).toFixed(3)+'%',
    '2→3 단계 변화율 · 응력 '+(50/11.5).toFixed(3)+'% · 변위 '+(100*(.115-.11)/.115).toFixed(3)+'%'
   ];
   if(missingRow)required.splice(1,1);
   if(wrongNumbers)required[0]=required[0].replace('10.00000','10.50000');
   if(duplicateRow)required.push(required[0]);
   const section={getAttribute:name=>name==='data-gf-mesh-study-id'?
       (wrongStudyId?'4'.repeat(32):study.id):null,
     querySelectorAll:selector=>selector==='p'?required.map(textContent=>({textContent})):[]};
   return{body:{},documentElement:{},getElementById:id=>
      (id==='geofield-a08-evidence'&&!badFaa||
       id==='geofield-agent-report'&&reportAI||
       id==='geofield-external-llm-report'&&paidStale)?{}:
      id==='geofield-ai-mesh-followup-report'&&reportMesh?section:null};
  }}
 };
 vm.createContext(ctx);vm.runInContext(numericProof+'\n'+contract,ctx);
 const call=(requireMesh=false)=>ctx.gfStage3CompleteReport(JOB,SHA,CASE,RUN,()=>selection.current,requireMesh);
 return{ctx,call,calls,nodes,selection};
}
(async()=>{
 const good=make();assert.equal(await good.call(),true);
 assert.equal(good.calls.length,1);
 assert.equal(good.calls[0][4],false,'Automatic report MUST disable paid AI');
 assert.equal(good.calls[0][5],false,'Optional report may be base only');
 assert.match(good.nodes.gfAutoUnifiedStatus.textContent,/자동 통합 보고서 생성 완료/);
 assert.match(good.nodes.gfAutoUnifiedStatus.textContent,/14\.758 MPa/);
 assert.match(good.nodes.gfAutoUnifiedStatus.textContent,/실제 3회 메시 검증/);
 const noStudy=make({mesh:false,reportMesh:false});
 assert.equal(await noStudy.call(),true,'Optional report can show separately verified base FEA');
 assert.equal(await noStudy.call(true),false,'One-click full report must not complete without all three mesh archives');
 assert.equal(noStudy.calls.at(-1)[5],true,'One-click reports must demand three real mesh results');
 assert.match(noStudy.nodes.gfAutoUnifiedStatus.textContent,/3회 메시 원본 재검증/);
 for(const fault of [{missingRow:true},{wrongNumbers:true},{duplicateRow:true},{wrongStudyId:true}]){
  const broken=make(fault);
  assert.equal(await broken.call(true),false,
    'a missing, stale, duplicated or wrong-study numeric mesh row must block complete status');
  assert.match(broken.nodes.gfAutoUnifiedStatus.textContent,/5개 수치 행/);
 }
 const unverifiedStudy=make({mesh:true,validMeshReadback:false,reportMesh:false});
 assert.equal(await unverifiedStudy.call(true),false,
  'One-click mandatory mesh result must fail closed, never be marked complete');
 assert.equal(await unverifiedStudy.call(),true,
  'Optional invalid mesh percentages must not suppress verified original FEA HTML');
 assert.match(unverifiedStudy.nodes.gfAutoUnifiedStatus.textContent,/추가 메시 검증은 이번 보고서에 연결되지 않음/);
 for(const problem of [
  {trusted:false},{mesh:true,reportMesh:false},{reportAI:true},
  {paidStale:true},{badFaa:true},{buildError:true}
 ]){
  const caseTest=make(problem);
  assert.equal(await caseTest.call(),false,JSON.stringify(problem));
  assert.match(caseTest.nodes.gfAutoUnifiedStatus.textContent,/자동 통합 보고서 생성 실패|^$/);
 }
 const stale=make({staleAfterBuild:true});
 assert.equal(await stale.call(),false);
 assert.doesNotMatch(stale.nodes.gfAutoUnifiedStatus.textContent,/생성 완료/);
 assert.equal(vm.runInContext('gfStage3Generated?.run',good.ctx),RUN);
 assert.equal(vm.runInContext('gfStage3Generated',stale.ctx),null);
 // Asynchronous ML/R12 inference may finish after the original unified
 // report completed. Coalesce a read-only, same-run HTML refresh; always OFF.
 good.ctx.gfResearchEvidenceRevision=1;
 assert.equal(await good.ctx.gfStage3RefreshOnResearch(JOB,SHA),true);
 assert.equal(good.calls.length,2,'new ML result should trigger only one new HTML validation');
 assert.equal(good.calls[1][4],false,'background ML refresh must never call paid LLM');
 assert.equal(vm.runInContext('gfStage3Generated.researchRevision',good.ctx),1);
 assert.equal(await good.ctx.gfStage3RefreshOnResearch(JOB,SHA),true);
 assert.equal(good.calls.length,2,'unchanged ML state must not regenerate the report');
 good.ctx.gfOneClickInProgress=true;
 good.ctx.gfResearchEvidenceRevision=2;
 assert.equal(await good.ctx.gfStage3RefreshOnResearch(JOB,SHA),false);
 assert.equal(good.calls.length,2,'no premature report regeneration during live one-click flow');
 good.ctx.gfOneClickInProgress=false;
 assert.equal(await good.ctx.gfStage3RefreshOnResearch(JOB,SHA),true);
 assert.equal(good.calls.length,3);
 assert.equal(good.calls[2][4],false,'refresh after pipeline must remain AI OFF');
 good.ctx.current={sha256:'c'.repeat(64)};
 good.ctx.gfResearchEvidenceRevision=3;
 assert.equal(await good.ctx.gfStage3RefreshOnResearch(JOB,SHA),false);
 assert.equal(good.calls.length,3,'changed STEP must never reuse old report');

 console.log('PASS: stage3 auto-generates run-bound CAD/ML/FEA AI-OFF+mesh HTML, blocks stale/off-contract evidence and never calls paid LLM');
})().catch(e=>{console.error(e);process.exitCode=1});
