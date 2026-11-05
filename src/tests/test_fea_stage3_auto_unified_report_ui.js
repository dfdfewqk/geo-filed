'use strict';
// Stage 3 uses existing verified server HTML + bounded 3-mesh appendix.
// Runs synthetic browser state only: no STEP, SQLite, solver or external LLM.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const js=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../payload/frontend/index.html'),'utf8');
const start=js.indexOf('// GEOFIELD_STAGE3_AUTO_UNIFIED_REPORT_20261105');
const end=js.indexOf('let gfOneClickPreparing=false;',start);
assert(start>0&&end>start,'auto report source contract missing');
assert.equal((html.match(/id="gfAutoUnifiedStatus"/g)||[]).length,1);
assert(js.indexOf('await gfAutoStage2Verification(',end)>end);
assert(js.indexOf('await gfStage3CompleteReport(',end)>js.indexOf('await gfAutoStage2Verification(',end));
assert(js.includes('gfStage3Generated=null;\n if($(\'gfAutoUnifiedStatus\'))'));
const contract=js.slice(start,end);
const JOB='1'.repeat(32),SHA='a'.repeat(64),CASE='b'.repeat(64),RUN='2'.repeat(32),STUDY='3'.repeat(32);
const valid=()=>({cad:{sha256:SHA},ml:{state:'complete'},r12_research_status:{state:'complete'},
 fea:{maximum_von_mises_mpa:14.758,maximum_displacement_mm:.0264},
 fea_case_provenance:{verified_run_id:RUN,solved_case_sha256:CASE}});
const body='<html lang="ko"><body>'+('verified CAD ML FEA local evidence '.repeat(15))+'</body></html>';
function make({trusted=true,mesh=true,reportMesh=true,reportAI=true,paidStale=false,
               staleAfterBuild=false,badFaa=false,buildError=false}={}){
 const calls=[],nodes={gfAutoUnifiedStatus:{textContent:''}},selection={current:true};
 const ctx={
  Math,Number,String,Error,Promise,latestSummary:valid(),
  $:id=>nodes[id]??null,
  gfReportSelectionCurrent:()=>trusted&&selection.current,
  gfMeshFollowupSelection:()=>mesh?{id:STUDY}:null,
  gfBuildVisibleReport:async(...args)=>{
   calls.push(args);
   if(staleAfterBuild)selection.current=false;
   if(buildError)throw Error('simulated HTML endpoint unavailable');
   return body;
  },
  DOMParser:class{parseFromString(){
   return{body:{},documentElement:{},getElementById:id=>
      (id==='geofield-a08-evidence'&&!badFaa||
       id==='geofield-agent-report'&&reportAI||
       id==='geofield-ai-mesh-followup-report'&&reportMesh||
       id==='geofield-external-llm-report'&&paidStale)?{}:null};
  }}
 };
 vm.createContext(ctx);vm.runInContext(contract,ctx);
 const call=()=>ctx.gfStage3CompleteReport(JOB,SHA,CASE,RUN,()=>selection.current);
 return{ctx,call,calls,nodes,selection};
}
(async()=>{
 const good=make();assert.equal(await good.call(),true);
 assert.equal(good.calls.length,1);
 assert.equal(good.calls[0][4],false,'Automatic report MUST disable paid AI');
 assert.match(good.nodes.gfAutoUnifiedStatus.textContent,/자동 통합 보고서 생성 완료/);
 assert.match(good.nodes.gfAutoUnifiedStatus.textContent,/14\.758 MPa/);
 assert.match(good.nodes.gfAutoUnifiedStatus.textContent,/실제 3회 메시 검증/);
 const noStudy=make({mesh:false,reportMesh:false});
 assert.equal(await noStudy.call(),true);
 assert.match(noStudy.nodes.gfAutoUnifiedStatus.textContent,/추가 메시 검증은 이번 보고서에 연결되지 않음/);
 for(const problem of [
  {trusted:false},{mesh:true,reportMesh:false},{reportAI:false},
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
 console.log('PASS: stage3 auto-generates run-bound CAD/ML/FEA/local-AI+mesh HTML, blocks stale/off-contract evidence and never calls paid LLM');
})().catch(e=>{console.error(e);process.exitCode=1});
