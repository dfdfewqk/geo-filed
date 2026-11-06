'use strict';
// Execute the REAL final A08 HTML numeric/provenance acceptance gate.
// Synthetic DOM only; no FEA runs, no LLM tokens or user archive mutations.
const assert=require('node:assert/strict'),fs=require('node:fs');
const path=require('node:path'),vm=require('node:vm');
const js=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8').replace(/\r\n/g,'\n');
const backend=fs.readFileSync(path.join(__dirname,'../fea_report_a08.py'),'utf8');
const a=js.indexOf('// GEOFIELD_FEA_HTML_NUMERIC_READBACK_20261106');
const b=js.indexOf('async function gfBuildVisibleReport(',a);
assert(a>0&&b>a,'real source numeric gate is required');
const builder=js.slice(b,js.indexOf('// GEOFIELD_AI_MESH_FEEDBACK_UI_V1',b));
const gate=builder.indexOf('gfVerifyFeaHtmlNumericReadback(parsed,uid,sha,run,caseSha)');
const paid=builder.indexOf("await get('/api/agent/evidence/");
assert(gate>=0&&paid>gate,'full stress/disp identity gate must precede ANY token-consuming request');
for(const label of [
 'CAD 원본 SHA-256','검증된 실행 ID','FEA 조건 SHA-256',
 '전체 절점 최대 von Mises 응력','전체 절점 최대 변위',
 '검증된 노드 / 사면체 요소'
])assert(backend.includes('row("'+label+'"'),'server must write real '+label);
assert(backend.includes('format(value, ".8g")'),'A08 significant-digit precision must remain known');
const JOB='1'.repeat(32),SHA='a'.repeat(64),RUN='2'.repeat(32),CASE='b'.repeat(64);
const summary=()=>({
 fea:{state:'complete',result_run_id:RUN,result_case_sha256:CASE,
  maximum_von_mises_mpa:14.758,maximum_displacement_mm:.0264,
  node_count:7303,tetrahedron_count:26079},
 cad:{sha256:SHA},fea_case_provenance:{
  verified_run_id:RUN,solved_case_sha256:CASE,
  source_verification:'INP_STA_FRD_reverified',summary_numbers_crosschecked:true,
  verified_mesh:{nodes:7303,tetrahedra:26079}
 }
});
const rows=()=>[
 ['CAD 원본 SHA-256',SHA],['검증된 실행 ID',RUN],['FEA 조건 SHA-256',CASE],
 ['전체 절점 최대 von Mises 응력','14.758 MPa'],
 ['전체 절점 최대 변위','0.0264 mm'],
 ['검증된 노드 / 사면체 요소','7303 / 26079']
];
let current=true;
const ctx={String,Map,Array,Number,Math,Error,
 latestSummary:summary(),gfReportSelectionCurrent:()=>current};
vm.createContext(ctx);vm.runInContext(js.slice(a,b),ctx);
const doc=(data=rows())=>{
 const section={
  querySelectorAll(sel){
   assert.equal(sel,'tr');
   return data.map(([key,value])=>({
    querySelector(which){if(which==='th')return {textContent:key};
     if(which==='td')return {textContent:value};
     return null;}
   }));
  }
 };
 return {getElementById:id=>id==='geofield-a08-evidence'?section:null};
};
const verify=data=>ctx.gfVerifyFeaHtmlNumericReadback(doc(data),JOB,SHA,RUN,CASE);
assert.equal(verify(rows()),true,'valid A08 signed FEA rows must pass');
assert.equal(verify(rows().map(([k,v])=>k==='전체 절점 최대 von Mises 응력'?
 [k,'14.7580002 MPa']:[k,v])),true,'actual server .8g formatting is tolerant of insignificant rounding');
for(const [label,invalid,pattern] of [
 ['missing stress',rows().filter(x=>x[0]!=='전체 절점 최대 von Mises 응력'),/누락/],
 ['missing displacement',rows().filter(x=>x[0]!=='전체 절점 최대 변위'),/누락/],
 ['missing CAD SHA',rows().filter(x=>x[0]!=='CAD 원본 SHA-256'),/누락/],
 ['missing mesh',rows().filter(x=>x[0]!=='검증된 노드 \/ 사면체 요소'),/누락/],
 ['duplicate verified stress',rows().concat([['전체 절점 최대 von Mises 응력','14.758 MPa']]),/중복/],
 ['different STEP',rows().map(([k,v])=>[k,k==='CAD 원본 SHA-256'?'f'.repeat(64):v]),/식별값 불일치/],
 ['different solve',rows().map(([k,v])=>[k,k==='검증된 실행 ID'?'4'.repeat(32):v]),/식별값 불일치/],
 ['different boundary',rows().map(([k,v])=>[k,k==='FEA 조건 SHA-256'?'f'.repeat(64):v]),/식별값 불일치/],
 ['different mesh',rows().map(([k,v])=>[k,k==='검증된 노드 / 사면체 요소'?'7302 / 26079':v]),/식별값 불일치/],
 ['incorrect stress',rows().map(([k,v])=>[k,k==='전체 절점 최대 von Mises 응력'?'14.9 MPa':v]),/FRD 원본 수치 불일치/],
 ['incorrect disp',rows().map(([k,v])=>[k,k==='전체 절점 최대 변위'?'0.0304 mm':v]),/FRD 원본 수치 불일치/],
 ['wrong stress unit',rows().map(([k,v])=>[k,k==='전체 절점 최대 von Mises 응력'?'14.758 mm':v]),/단위 불일치/],
 ['wrong disp unit',rows().map(([k,v])=>[k,k==='전체 절점 최대 변위'?'0.0264 MPa':v]),/단위 불일치/],
 ['nonfinite stress',rows().map(([k,v])=>[k,k==='전체 절점 최대 von Mises 응력'?'NaN MPa':v]),/단위 불일치/],
 ['untrusted HTML',[],/누락/]
]){
 assert.throws(()=>verify(invalid),pattern,label);
}
current=false;
assert.throws(()=>verify(rows()),/현재 FEA 실행이 변경/, 'selection cannot change during report production');
current=true;
const summaryBefore=JSON.stringify(ctx.latestSummary);
assert.equal(verify(rows()),true);
assert.equal(JSON.stringify(ctx.latestSummary),summaryBefore,
 'FEA HTML proof must not modify solver summary values');
console.log('PASS: 6 real A08 HTML identity/stress/displacement/mesh rows pass; 15 corrupt/missing/stale scenarios fail closed BEFORE paid AI or report export');
