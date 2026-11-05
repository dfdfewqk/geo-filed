'use strict';
// Production source regression: classify actual evidence, unverified research
// and design-safety boundaries without running STEP, solvers or paid AI.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const js=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../payload/frontend/index.html'),'utf8');
const a=js.indexOf('// GEOFIELD_PREACCEPTANCE_EVIDENCE_STATUS_20261105');
const b=js.indexOf('function gfFeaVerificationSummary(',a);
assert(a>0&&b>a);
assert.equal((html.match(/id="gfEvidenceChecklist"/g)||[]).length,1);
const nodes={gfEvidenceChecklist:{textContent:''}};
const fn=new Function('$','gfReportReady',js.slice(a,b)+
 ';return {lines:gfEvidenceChecklistLines,render:gfRenderEvidenceChecklist}')(
 id=>nodes[id]||null,
 (s,sha)=>s?.fea_case_provenance?.verified_run_id==='1'.repeat(32)&&
  s?.fea_case_provenance?.summary_numbers_crosschecked===true&&s?.cad?.sha256===sha);
const SHA='a'.repeat(64),RUN='1'.repeat(32),CASE='b'.repeat(64);
const verified={
 cad:{sha256:SHA,parts:[{bbox_mm:{x:50,y:30,z:50}}]},
 fea:{state:'complete',maximum_von_mises_mpa:18.517,
      maximum_displacement_mm:0.0344},
 fea_case_provenance:{verified_run_id:RUN,solved_case_sha256:CASE,
  summary_numbers_crosschecked:true},
 ml:{state:'complete'},
 r12_research_status:{state:'failed'}
};
const get=(v,mesh)=>fn.lines(v,SHA,mesh).join('\n');
const base=get(verified);
assert.match(base,/CAD · 현재 STEP SHA와 실제 형상 측정 기록 확인/);
assert.match(base,/FEA · 실제 INP\/STA\/FRD 독립 재검증 완료/);
assert.match(base,/3회 메시 · 이번 실행에 연결된 완료\/검증 근거 없음 또는 검사 진행 중/);
assert.match(base,/BrepMFR · 연구 추론 완료 · 모델 정확도는 별도 검증/);
assert.match(base,/R12 · 실행 실패 또는 결과 근거 검증 실패/);
assert.match(base,/구조 안전성 · 미판정/);
assert.doesNotMatch(base,/구조 안전성 · 검증 완료/);
const withStudy=get(verified,{runs:[1,2,3],steps:[1,2]});
assert.match(withStudy,/3회 메시 · 3개 실제 솔버 기록 재검증 완료 · 수렴 인증 아님/);
const otherCAD=get({...verified,cad:{...verified.cad,sha256:'c'.repeat(64)}},
 {runs:[1,2,3],steps:[1,2]});
assert.doesNotMatch(otherCAD,/FEA · 실제 INP\/STA\/FRD 독립 재검증 완료/);
assert.doesNotMatch(otherCAD,/3회 메시 · 3개 실제 솔버 기록 재검증 완료/);
const unverified=get({...verified,fea_case_provenance:{
 ...verified.fea_case_provenance,summary_numbers_crosschecked:false}},
 {runs:[1,2,3],steps:[1,2]});
assert.doesNotMatch(unverified,/3회 메시 · 3개 실제 솔버 기록 재검증 완료/);
const missing=get({...verified,ml:{state:'not_run'},r12_research_status:{state:'unavailable'}});
assert.match(missing,/BrepMFR · 실행 전 또는 자동 실행 대상 아님/);
assert.match(missing,/R12 · 환경 미준비 또는 사용자가 해제/);
fn.render(verified,SHA,{runs:[1,2,3],steps:[1,2]});
assert.equal(nodes.gfEvidenceChecklist.textContent,withStudy);
for(const route of [
 'gfRenderEvidenceChecklist(result,expectedSha);',
 'gfRenderEvidenceChecklist(result,expectedSha,verifiedMesh);',
 'gfRenderEvidenceChecklist(latestSummary,sha,verified);'
])assert(js.includes(route),'Missing current-run checklist refresh: '+route);
assert(js.includes('if($('+"'gfEvidenceChecklist'"+'))'), 'Must invalidate checklist on new STEP');
console.log('PASS: evidence states distinguish current STEP+FEA, independently rechecked mesh study, research inference vs ML accuracy, safety limits');
