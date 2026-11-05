'use strict';
// Real production report narrative normalization/acceptance logic, no FEA,
// no model inference, no filesystem mutations and no external provider calls.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const backend=fs.readFileSync(path.join(__dirname,'../payload/GeoField_CAD_Analysis.py'),'utf8');
assert(backend.includes('규칙 근거 정리 완료 · 안전 판정 아님'));
assert(backend.includes('외부 AI는 사용자가 별도 동의한 이번 요청에서만 호출합니다.'));
assert(!backend.includes('이전에 동의한 외부 답변이 있으면 별도 부록으로 표시'));

const first=src.indexOf('// GEOFIELD_REPORT_NARRATIVE_DEDUP_20261105');
const middle=src.indexOf('async function gfBuildVisibleReport(',first);
const second=src.indexOf('function gfAssertComposedReport(');
const last=src.indexOf('function gfAppendMeshFollowup(',second);
assert(first>0&&middle>first&&second>middle&&last>second,
 'Production AI/3D narrative contract missing');
const ctx={String,Array,Error,Boolean};
vm.createContext(ctx);vm.runInContext(src.slice(first,middle)+'\n'+src.slice(second,last),ctx);
function page({visual=true,agent=false,external=false,legacy=true,
              includeDeepSeek=true}={}){
 const paragraphs=[],sections=new Map();
 const add=(text)=>{const p={textContent:text,remove(){
  const i=paragraphs.indexOf(p);if(i>=0)paragraphs.splice(i,1);
 }};paragraphs.push(p)};
 if(legacy){
  add('로컬 AI: 동일 CAD 기반 규칙 설명 포함 · 해석 승인 아님');
  if(includeDeepSeek)add('DeepSeek 설명: 표시 불가 (구버전 안내)');
  add('3D 화면 이미지: 표시 불가 (별도로 검증된 캡처 파일이 없습니다).');
 }
 add('계산 검증: 실제 CalculiX INP·STA·FRD 근거가 존재합니다.');
 add('실험적 ML 상태: complete · CAD/FEA 수치의 출처에 사용하지 않았습니다.');
 const evidence={querySelectorAll:sel=>sel==='p'?paragraphs:[]};
 sections.set('geofield-a08-evidence',evidence);
 if(visual)sections.set('geofield-verified-fea-3d-views',{querySelectorAll:()=>[{},{}]});
 if(agent)sections.set('geofield-agent-report',{});
 if(external)sections.set('geofield-external-llm-report',{});
 const doc={getElementById:id=>sections.get(id)||null};
 return{doc,paragraphs,sections,text:()=>paragraphs.map(p=>p.textContent).join(' | ')};
}
{
 const good=page();
 ctx.gfConsolidateReportNarrative(good.doc);
 const firstText=good.text();
 assert.doesNotMatch(firstText,/DeepSeek 설명: 표시 불가/);
 assert.doesNotMatch(firstText,/로컬 AI:/);
 assert.doesNotMatch(firstText,/3D 화면 이미지: 표시 불가/);
 assert.match(firstText,/실제 CalculiX INP·STA·FRD/);
 assert.match(firstText,/실험적 ML 상태: complete/);
 assert.equal(ctx.gfAssertComposedReport(good.doc,null,false).meshAttached,false);
 const n=good.paragraphs.length;
 ctx.gfConsolidateReportNarrative(good.doc);
 assert.equal(good.paragraphs.length,n,'rechecking a report must be idempotent');
}
{
 const serverOnly=page({visual:false});
 ctx.gfConsolidateReportNarrative(serverOnly.doc);
 assert.match(serverOnly.text(),/3D 화면 이미지: 표시 불가/,
  'the unchanged base-server HTML must not invent a screenshot');
 assert.doesNotMatch(serverOnly.text(),/DeepSeek 설명: 표시 불가/);
}
{
 const on=page({visual:true,agent:true,external:true});
 ctx.gfConsolidateReportNarrative(on.doc);
 assert.equal(ctx.gfAssertComposedReport(on.doc,null,true).meshAttached,false,
  'explicit AI ON may include rule/external opinion sections');
 assert.doesNotMatch(on.text(),/로컬 AI:|DeepSeek 설명: 표시 불가/);
 assert.throws(()=>ctx.gfAssertComposedReport(on.doc,null,false),
   /AI OFF 보고서에 이전\/현재 AI 설명이 남아/,
   'AI OFF must reject agent sections, even if old placeholders were removed');
}
{
 const lingering=page({visual:true});
 // Mock a corrupted/incomplete legacy paragraph with no remove() behavior.
 lingering.paragraphs[0].remove=()=>{};
 ctx.gfConsolidateReportNarrative(lingering.doc);
 assert.throws(()=>ctx.gfAssertComposedReport(lingering.doc,null,false),
   /과거 AI\/3D 안내 문구/,
   'fail closed when an old AI label survives the cleanup');
}
{
 const broken=page({visual:true});
 broken.sections.delete('geofield-a08-evidence');
 assert.throws(()=>ctx.gfAssertComposedReport(broken.doc,null,false),/INP·STA·FRD/);
}
assert(src.includes('gfConsolidateReportNarrative(parsed);'));
assert(!src.includes("fixLegacyCopy("),'historical duplicated DeepSeek label patching must be gone');
assert(src.includes("gfAssertComposedReport(parsed,meshFollowup,false,requireMesh)"),
 'AI OFF and ON must use one report acceptance gate');
assert(src.includes("gfAssertComposedReport(parsed,meshFollowup,true,requireMesh)"));
console.log('PASS: report ON/OFF separates measured evidence from AI, removes duplicate legacy 3D and DeepSeek notices, rejects stale labels, preserves base-only archive wording');
