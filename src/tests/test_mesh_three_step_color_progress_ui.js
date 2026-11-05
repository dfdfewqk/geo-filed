'use strict';
// Colored three-step progress is display-only, never solver evidence or convergence.
// Test real production functions with synthetic DOM. No API, STEP, ML or SQLite writes.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8').replace(/\r\n/g,'\n');
const html=fs.readFileSync(path.join(__dirname,'../payload/frontend/index.html'),'utf8');
const a=src.indexOf('function gfMeshProgressModel(');
const b=src.indexOf('async function gfRecheckUnknownMeshSeries()',a);
assert(a>0&&b>a,'Production progress model and recovery handler must exist');
for(const id of ['feaMeshProgressVisual','resultsMeshProgressVisual']){
 assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1);
}
assert.match(html,/aria-live="polite"[^>]*>0\/3 · 결과 분석 전/);
assert.match(src,/!gfRenderMeshProgress\(state,uid,sha,meshSeriesId\)/);
assert.match(src,/gfMarkMeshProgressUnknown\('실제 계산 종료 미확인'\)/);
assert.match(html,/수렴·구조 안전 인증은 아닙니다/);
const UID='a'.repeat(32),SHA='b'.repeat(64),STUDY='c'.repeat(32);
const ids=['1'.repeat(32),'2'.repeat(32),'3'.repeat(32)];
function dom(){
 const tiles=[0,1,2].map(()=>({
  attrs:{'data-state':'pending'},
  label:{textContent:'○ 대기'},
  setAttribute(k,v){this.attrs[k]=v},
  getAttribute(k){return this.attrs[k]},
  querySelector(k){return k==='span'?this.label:null}
 }));
 const total={textContent:'0/3 · 결과 분석 전'};
 return{tiles,total,querySelector(sel){
  if(sel==='[data-mesh-total]')return total;
  const m=sel.match(/^\[data-mesh-step="([123])"\]$/);
  return m?tiles[Number(m[1])-1]:null;
 }};
}
const left=dom(),right=dom(),panels={feaMeshProgressVisual:left,resultsMeshProgressVisual:right};
const ctx={jobId:UID,current:{sha256:SHA},meshSeriesId:STUDY,$:id=>panels[id]||null};
vm.createContext(ctx);
vm.runInContext(src.slice(a,b),ctx);
const saved=steps=>steps.map(x=>x.getAttribute('data-state'));
function states(steps){return steps.map(x=>x.attrs['data-state'])}
function check(expected,total){
 assert.deepEqual(states(left.tiles),expected);
 assert.deepEqual(states(right.tiles),expected);
 assert.match(left.total.textContent,total);
 assert.equal(left.total.textContent,right.total.textContent);
}
function state(completed,current_index,status='running',extra={}){
 return {id:STUDY,cad_job_id:UID,cad_sha256:SHA,completed,total:3,
  current_index,status,analysis_snapshot_ids:ids.slice(0,completed),
  mesh_study_verified:false,...extra};
}
assert.equal(ctx.gfRenderMeshProgress(null),true);
check(['pending','pending','pending'],/0\/3/);
assert.equal(ctx.gfRenderMeshProgress(state(0,0)),true);
check(['running','pending','pending'],/0\/3/);
assert.equal(ctx.gfRenderMeshProgress(state(1,1)),true);
check(['calculated','running','pending'],/1\/3/);
assert.match(left.tiles[0].label.textContent,/전체 재검증 대기/);
assert.equal(ctx.gfRenderMeshProgress(state(2,2)),true);
check(['calculated','calculated','running'],/2\/3/);
// Three calculations alone are never "green" until the server confirms
// separately revalidated actual INP/STA/FRD evidence.
assert.equal(ctx.gfRenderMeshProgress(state(3,2,'complete')),true);
check(['calculated','calculated','calculated'],/재검증 불완전/);
const aVerified={status:'verified_three_mesh_sensitivity_only',
 same_physical_case:true,solver_evidence:'each_calculix_run_revalidated',
 convergence_certified:false,safety_certified:false,
 numeric_stability_diagnostic:{passes:false}};
assert.equal(ctx.gfRenderMeshProgress(state(3,2,'complete',{
 mesh_study_verified:true,study_analysis:aVerified})),true);
check(['verified','verified','verified'],/3\/3 계산 및 원본 재검증 완료/);
assert.match(left.total.textContent,/미충족 또는 미평가/);
assert.match(left.total.textContent,/수렴·구조 안전 인증 아님/);
assert.match(left.tiles[2].label.textContent,/원본 재검증 완료/);
assert.equal(ctx.gfRenderMeshProgress(state(3,2,'complete',{
 mesh_study_verified:true,study_analysis:{...aVerified,numeric_stability_diagnostic:{passes:true}}
})),true);
check(['verified','verified','verified'],/5% 수치 안정성 선별 통과/);
// Full recorded count + falsely asserted mesh_study_verified is insufficient.
ctx.gfRenderMeshProgress(state(3,2,'complete',{
 mesh_study_verified:true,study_analysis:{...aVerified,solver_evidence:'unverified'}
}));
check(['calculated','calculated','calculated'],/재검증 불완전/);
ctx.gfRenderMeshProgress(state(2,2,'failed'));
check(['calculated','calculated','failed'],/중단 또는 실패/);
// HTTP failures leave evidence unresolved rather than claiming cancelled.
ctx.gfRenderMeshProgress(state(1,1));
ctx.gfMarkMeshProgressUnknown('응답 확인 불가');
check(['calculated','unknown','pending'],/중복 실행하지 마세요/);
const before=left.total.textContent;
assert.equal(ctx.gfRenderMeshProgress({...state(3,2,'complete'),cad_sha256:'f'.repeat(64)}),false);
assert.equal(left.total.textContent,before,'Stale STEP must not update progress');
assert.equal(ctx.gfRenderMeshProgress({...state(3,2,'complete'),analysis_snapshot_ids:[ids[0],ids[0],ids[2]]}),false);
assert.equal(left.total.textContent,before,'Duplicated archives must not color progress green');
assert.equal(ctx.gfRenderMeshProgress({...state(3,2,'complete'),id:'9'.repeat(32)}),false);
assert.equal(left.total.textContent,before,'Older study must not update current progress');
// A brand new current CAD execution resets stale green cards.
ctx.gfRenderMeshProgress(state(3,2,'complete',{
 mesh_study_verified:true,study_analysis:aVerified
}));
ctx.gfRenderMeshProgress(null);
check(['pending','pending','pending'],/0\/3/);
console.log('PASS: 1/3 and 2/3 amber, live blue, 3/3 verified green, fail red, timeout unknown, stale evidence blocked, both panes synchronized');
