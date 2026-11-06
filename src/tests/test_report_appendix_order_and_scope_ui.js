'use strict';
// Production HTML layout audit: reuse original verified nodes instead of
// generating duplicate ML/FEA data. No solver, API calls, disk mutations.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8').replace(/\r\n/g,'\n');
const start=source.indexOf('function gfAppendEvidenceScope(');
const end=source.indexOf('// GEOFIELD_VERIFIED_FEA_REPORT_VIEWS_20261105',start);
const orderStart=source.indexOf('function gfArrangeVerifiedReportSections(');
const orderEnd=source.indexOf('function gfConsolidateReportNarrative(',orderStart);
assert(start>0&&end>start&&orderStart>0&&orderEnd>orderStart);
const makeDocument=()=>{
 const ids=[
  'geofield-a08-evidence','geofield-local-hole-evidence',
  'geofield-external-llm-report','geofield-d6-design-observation',
  'geofield-ai-mesh-followup-report','geofield-verified-fea-3d-views',
  'geofield-r12-research-evidence-report',
  'geofield-brepmfr-research-evidence-report',
  'geofield-engineering-evidence-scope'
 ];
 const nodes=new Map(),flow=[],inserted=[];
 const register=(id,tag='section')=>{
  const x={id,tag,textContent:'',children:[],style:{},
   append(...v){this.children.push(...v)},
   insertAdjacentElement(direction,item){
    assert.equal(direction,'afterend');
    const prev=flow.indexOf(item);if(prev>=0)flow.splice(prev,1);
    const pivot=flow.indexOf(this);assert(pivot>=0);
    flow.splice(pivot+1,0,item);
    inserted.push({anchor:this.id,item:item.id});
    if(item.id)nodes.set(item.id,item);
   }};
  nodes.set(id,x);flow.push(x);return x;
 };
 for(const id of ids)register(id);
 const doc={getElementById:id=>nodes.get(id)||null,
  createElement:tag=>({id:'',tag,textContent:'',style:{},children:[],
   append(...v){this.children.push(...v)}}),
  body:{append(x){flow.push(x);if(x.id)nodes.set(x.id,x)}}};
 return {doc,flow,nodes,inserted};
};
const ctx={meshSeriesBusy:false,
 gfEngineeringStage2Review:()=>[
  '메시 수치 변화: 실제 수치(상세는 비교 부록)',
  '응력 집중 원인: CAD-FRD 면 대응 미검증',
  '재료/안전율: 항복강도 확인 필요',
  'ML 정확도: 독립 정답 분리셋 없음'
 ]};
vm.createContext(ctx);
vm.runInContext(source.slice(start,end)+'\n'+source.slice(orderStart,orderEnd),ctx);
{
 const p=makeDocument();
 ctx.gfArrangeVerifiedReportSections(p.doc,p.doc.getElementById('geofield-a08-evidence'));
 const ids=p.flow.map(x=>x.id);
 assert.deepEqual(ids,[
  'geofield-a08-evidence','geofield-local-hole-evidence',
  'geofield-engineering-evidence-scope',
  'geofield-brepmfr-research-evidence-report',
  'geofield-r12-research-evidence-report',
  'geofield-verified-fea-3d-views',
  'geofield-ai-mesh-followup-report',
  'geofield-d6-design-observation',
  'geofield-external-llm-report']);
 assert.equal(new Set(ids).size,ids.length,'ordered nodes must not duplicate');
 ctx.gfArrangeVerifiedReportSections(p.doc,p.doc.getElementById('geofield-a08-evidence'));
 assert.deepEqual(p.flow.map(x=>x.id),ids,'opening a report again must preserve order');
}
{
 const p=makeDocument(),anchor=p.doc.getElementById('geofield-local-hole-evidence');
 ctx.gfAppendEvidenceScope(p.doc,p.doc.getElementById('geofield-a08-evidence'),null,null);
 const section=p.doc.getElementById('geofield-engineering-evidence-scope');
 const strings=section.children.map(x=>x.textContent).join(' ');
 assert.match(strings,/동일 실행 INP·STA·FRD/);
 assert.match(strings,/메시 3회 비교: 이 보고서에 연결된 완료 기록이 없습니다/);
 assert.doesNotMatch(strings,/D6|Ø6.0|추가 실행 필요|고정 영역 경계 최대 변화/);
 assert.doesNotMatch(strings,/추세:|응력 변화율:|메시 수치 변화:/);
 assert.match(strings,/CAD-FRD 면 대응 미검증/);
 assert.match(strings,/항복강도 확인 필요/);
 assert.match(strings,/독립 정답 분리셋 없음/);
 assert(section===p.nodes.get('geofield-engineering-evidence-scope'));
}
{
 const p=makeDocument();
 ctx.gfAppendEvidenceScope(p.doc,p.doc.getElementById('geofield-a08-evidence'),
  {id:'verified-3-solves'},{id:{original:'1',variant:'2'}});
 const section=p.doc.getElementById('geofield-engineering-evidence-scope');
 const text=section.children.map(x=>x.textContent).join(' ');
 assert.match(text,/메시 3회 비교: 별도 실제 CalculiX 실행 기록 3개/);
 assert.match(text,/D6 비교: 두 STEP의 실제 계산/);
 assert.doesNotMatch(text,/메시 수치 변화:|최대 von Mises 응력 추세:/);
}
{
 const selectedMissing=makeDocument();
 ctx.gfAppendEvidenceScope(selectedMissing.doc,
  selectedMissing.doc.getElementById('geofield-a08-evidence'),null,null,null,true);
 const selectionNote=selectedMissing.doc.getElementById('geofield-engineering-evidence-scope').children.map(x=>x.textContent).join(' ');
 assert.match(selectionNote,/선택한 이전 결과 D6 비교: 현재 FEA 실행·기록 수치·변화율을 재검증하지 못해/);
}
console.log('PASS: verified report order = evidence > scope > BrepMFR > R12 > 3D > mesh > optional D6 > AI; no duplicate appendix nodes or phantom D6-not-run warnings');
