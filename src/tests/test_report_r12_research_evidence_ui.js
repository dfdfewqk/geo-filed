'use strict';
// Use actual current-report R12 bridge and renderer: synthetic response only.
// No model retraining, original STEP reads/writes, FEA solves or paid APIs.
const assert=require('node:assert/strict'),fs=require('node:fs'),
 vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const anchor=source.indexOf('// GEOFIELD_R12_RESEARCH_REPORT_EVIDENCE_20261105');
const end=source.indexOf('async function gfBuildVisibleReport(',anchor);
assert(anchor>0&&end>anchor,'production R12 report source missing');
assert(source.includes('gfAppendR12ReportProof(parsed,evidence,r12Proof,uid,sha)'),
 'preview/download/Stage3 common builder must append the real R12 research readback');
const production=source.slice(anchor,end),JOB='1'.repeat(32),SHA='a'.repeat(64),
 RUN='2'.repeat(32),CASE='b'.repeat(64),R12='3'.repeat(32);
const prediction=(face=7,extra={})=>({
 face_index:face,raw_ml_top_class:'through_hole',
 raw_ml_thresholded:'through_hole',predicted_hole_type:'through_hole',
 topology_evidence:'through_hole',decision_basis:'model_and_brep_topology_agree',
 uncalibrated_model_score:.82,status:'research_unverified',...extra
});
const result=(predictions=[prediction()])=>({
 cad_sha256:SHA,decision_usage:'blocked_diagnostic_only',
 status:'research_not_for_production',is_independent_r12_research:true,
 fea_calculated:false,geometry_certified:false,
 candidate_count:predictions.length,predictions
});
const task=(r=result())=>({id:R12,cad_job_id:JOB,cad_sha256:SHA,
 status:'complete',result:r});
const expected=(count=1)=>({state:'complete',mode:'research_only',cad_sha256:SHA,
 run_id:R12,candidate_count:count,fea_calculated:false});
function make({summary=expected(),response=task(),fetchFailure=null,
               changedAfterFetch=false,selection=true}={}){
 const calls=[];
 class Node{
  constructor(tag){this.tag=tag;this.textContent='';this.children=[];
   this.attrs={};this.style={};this.id='';this.alt='';this.src='';}
  setAttribute(key,value){this.attrs[key]=String(value)}
  getAttribute(key){return this.attrs[key]??null}
  append(...children){this.children.push(...children)}
  insertAdjacentElement(_where,value){this.children.push(value)}
 }
 const anchorNode=new Node('section'),body=new Node('body');
 const page={
  createElement:t=>new Node(t),
  getElementById:id=>id==='geofield-a08-evidence'?anchorNode:null,body
 };
 const state={String,Number,Array,Math,Set,Error,Promise,encodeURIComponent,
  jobId:JOB,current:{sha256:SHA},latestSummary:{r12_research_status:summary},
  gfReportSelectionCurrent:()=>selection,
  get:async(url,timeout)=>{
   calls.push({url,timeout});
   if(fetchFailure)throw Error(fetchFailure);
   if(changedAfterFetch)selection=false;
   return response;
  }};
 vm.createContext(state);vm.runInContext(production,state);
 const verify=t=>state.gfR12ValidatedReportProof(t,summary,JOB,SHA,RUN,CASE);
 const fetch=()=>state.gfFetchR12ReportProof(JOB,SHA,RUN,CASE);
 const append=r=>state.gfAppendR12ReportProof(page,anchorNode,r,JOB,SHA);
 const section=()=>anchorNode.children.find(x=>x.id==='geofield-r12-research-evidence-report');
 return{state,calls,verify,fetch,append,section};
}
(async()=>{
 const good=make();
 const got=await good.fetch();
 assert(got.proof,'server-verified same-STEP R12 result must be accepted');
 assert.equal(good.calls.length,2,
  'one R12 per-STEP source read and one separate source-recomputed synthetic evaluation read');
 assert.equal(good.calls[0].url,'/api/ml/r12/latest/'+JOB);
 assert.equal(good.calls[1].url,'/api/ml/r12/evaluation/'+JOB);
 assert.equal(got.evaluation,null,
  'an unverified synthetic evaluation response must not be presented as accuracy');
 assert.equal(good.append(got),true);
 const panel=good.section();
 assert(panel);
 assert.equal(panel.getAttribute('data-gf-r12-research-id'),R12);
 const joined=panel.children.map(x=>x.textContent).join(' ');
 assert.match(joined,/모델 점수는 교정된 확률이나 정확도가 아닙니다/);
 assert.match(joined,/R12 내부 면 번호와 CAD 3D 선택 면 ID의 대응도 검증되지 않았습니다/);
 assert.match(joined,/전체 후보 1개/);
 const table=panel.children.find(x=>x.tag==='table');
 assert(table&&table.children.length===2,'header plus one actual research row');
 assert.match(table.children[1].children.map(x=>x.textContent).join(' '),/82\.0% \(미보정\)/);
 assert(!table.children[1].children.some(x=>x.textContent.includes('정확도 82')),
   'R12 uncalibrated score must never be described as accuracy');

 const zero=make({summary:expected(0),response:task(result([]))});
 const zeroProof=await zero.fetch();
 assert(zeroProof.proof&&zeroProof.proof.candidateCount===0);
 assert.equal(zero.append(zeroProof),true);
 assert.match(zero.section().children.map(x=>x.textContent).join(' '),/실제 홀 없음의 증거는 아닙니다/);

 const conflicts=make({
  summary:expected(3),
  response:task(result([
    prediction(1),
    prediction(2,{raw_ml_top_class:'blind_hole',raw_ml_thresholded:'blind_hole',
      topology_evidence:'through_hole',predicted_hole_type:'unverified',
      decision_basis:'model_topology_conflict',uncalibrated_model_score:.45}),
    prediction(3,{raw_ml_top_class:'blind_hole',raw_ml_thresholded:'unverified',
      topology_evidence:null,predicted_hole_type:'unverified',
      decision_basis:'insufficient_brep_evidence',uncalibrated_model_score:.13})
  ]))
 });
 const cp=await conflicts.fetch();assert(cp.proof);
 conflicts.append(cp);
 assert.match(conflicts.section().children.map(x=>x.textContent).join(' '),
   /관통홀 후보 1개 \/ 막힌홀 후보 0개 \/ 판정 보류 2개/);

 for(const [name,invalid] of [
  ['stale CAD hash',{...task(),cad_sha256:'f'.repeat(64)}],
  ['stale R12 job id',{...task(),id:'4'.repeat(32)}],
  ['untrusted worker status',task({...result(),status:'production_verified'})],
  ['FEA claim',task({...result(),fea_calculated:true})],
  ['ML accuracy disguised as score',task(result([prediction(7,{uncalibrated_model_score:1.5})]))],
  ['duplicate face ordinal',task(result([prediction(7),prediction(7)]))],
  ['topology conflict falsely certified',task(result([
    prediction(7,{decision_basis:'model_topology_conflict',
      raw_ml_top_class:'blind_hole',topology_evidence:'through_hole',
      predicted_hole_type:'through_hole'})
  ]))],
  ['unverified basis falsely certified',task(result([
    prediction(7,{decision_basis:'insufficient_brep_evidence',
      topology_evidence:null,predicted_hole_type:'through_hole'})
  ]))]
 ]){
  const one=make({summary:expected(invalid.result.candidate_count),response:invalid});
  const checked=await one.fetch();
  assert.equal(checked.proof,null,name);
  one.append(checked);
  assert.equal(one.section().getAttribute('data-gf-r12-research-id'),null,name);
 }

 const failed=make({fetchFailure:'temporary offline'});
 const unavailable=await failed.fetch();
 assert.equal(unavailable.proof,null,'R12 outage cannot remove a valid FEA report');
 assert.match(unavailable.note,/서버 재조회 실패/);
 failed.append(unavailable);
 const notRun=make({summary:{state:'not_run',cad_sha256:SHA}});
 assert.equal((await notRun.fetch()).proof,null);
 assert.equal(notRun.calls.length,0,'not-run does not invent a worker output');
 const stale=make({changedAfterFetch:true});
 await assert.rejects(stale.fetch(),/현재 CAD\/FEA 원본이 변경/);

 const cappedPred=Array.from({length:33},(_,i)=>prediction(i));
 const capped=make({summary:expected(33),response:task(result(cappedPred))});
 const detail=await capped.fetch();assert(detail.proof);
 capped.append(detail);
 const t=capped.section().children.find(x=>x.tag==='table');
 assert.equal(t.children.length,31,'table is capped to 30 research candidates plus header');
 assert.match(capped.section().children.map(x=>x.textContent).join(' '),/앞 30개만 표시/);
 console.log('PASS: current STEP SHA/run-bound R12 predictions, honest research score, zero/contradictions/stale/bad evidence rejection, 30-row cap, no rerun or AI API');
})().catch(e=>{console.error(e);process.exitCode=1});
