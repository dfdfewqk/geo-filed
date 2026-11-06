'use strict';
// Real production CAD OCP-vs-ML aggregate comparison. All evidence is
// synthetic and same-STEP identity-bound. No paid AI, ML worker, FEA or writes.
const assert=require('node:assert/strict'),fs=require('node:fs');
const path=require('node:path'),vm=require('node:vm');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8').replace(/\r\n/g,'\n');
const start=src.indexOf('// GEOFIELD_CAD_ML_EVIDENCE_CONTRAST_20261106');
const end=src.indexOf('async function gfBuildVisibleReport(',start);
const scopeStart=src.indexOf('function gfAppendEvidenceScope(');
const scopeEnd=src.indexOf('// GEOFIELD_VERIFIED_FEA_REPORT_VIEWS_20261105',scopeStart);
assert(start>0&&end>start&&scopeStart>0&&scopeEnd>scopeStart);
const builder=src.slice(end,src.indexOf('// GEOFIELD_AI_MESH_FEEDBACK_UI_V1',end));
assert(builder.includes("await gfFetchOcpHoleReportProof(uid,sha,run,caseSha)"));
assert(builder.includes("gfCadMlResearchContrast(ocpProof,brepProof,r12Proof)"));
assert(builder.indexOf('gfCadMlResearchContrast(')<
       builder.indexOf("await get('/api/agent/evidence/"),
       'free OCP/ML evidence must be reviewed before a potential paid call');
const UID='1'.repeat(32),SHA='a'.repeat(64),RUN='2'.repeat(32),CASE='b'.repeat(64);
const faces=[
 {face_ordinal:1,state:'through_hole',radius_mm:2.75,axial_height_mm:5},
 {face_ordinal:4,state:'through_hole',radius_mm:2.75,axial_height_mm:5},
 {face_ordinal:5,state:'blind_hole',radius_mm:1.5,axial_height_mm:2.5},
 {face_ordinal:8,state:'unverified',reason:'ambiguous_or_stepped_exit'}
];
const ocpData=(override={})=>({
 schema:'geofield-hole-occupancy-v1',status:'complete',
 source:'local_ocp_solid_occupancy_not_ml',cad_job_id:UID,sha256:SHA,
 viewer_face_mapping_verified:false,
 decision_usage:'cad_diagnostic_only_not_fea_or_safety',faces,...override
});
let selection=true,callCount=0,reply=ocpData(),fail=false;
const ctx={String,Array,Object,Number,Math,Set,Map,Error,Promise,
 gfReportSelectionCurrent:()=>selection,meshSeriesBusy:false,
 gfEngineeringStage2Review:()=>[
  '메시 추세 진단 문장(별도)', '응력 집중 원인 검증 제한',
  '재료/안전율 검증 제한','ML 정확도 검증 제한'
 ],
 get:async url=>{
  callCount++;assert.equal(url,'/api/geometry/hole-evidence/'+UID);
  if(fail)throw Error('test readback unavailable');
  return reply;
 }};
vm.createContext(ctx);
vm.runInContext(src.slice(start,end)+'\n'+src.slice(scopeStart,scopeEnd),ctx);
const validated=ctx.gfValidatedOcpHoleReportProof(ocpData(),UID,SHA,RUN,CASE);
assert(validated);
assert.deepEqual(JSON.parse(JSON.stringify(validated.counts)),
 {through_hole:2,blind_hole:1,unverified:1});
assert.equal(validated.total,4);
assert.deepEqual(Array.from(validated.diameters),['3.000','5.500']);
for(const [label,bad] of [
 ['different CAD job',ocpData({cad_job_id:'0'.repeat(32)})],
 ['different STEP hash',ocpData({sha256:'f'.repeat(64)})],
 ['model origin instead of OCP',ocpData({source:'ml_model'})],
 ['unavailable OCP',ocpData({status:'unavailable'})],
 ['unverified face mapping claimed as verified',ocpData({viewer_face_mapping_verified:true})],
 ['fake safety permission',ocpData({decision_usage:'production_ready'})],
 ['duplicate ordinals',ocpData({faces:[faces[0],faces[0]]})],
 ['negative ordinal',ocpData({faces:[{...faces[0],face_ordinal:-1}]})],
 ['unknown topology class',ocpData({faces:[{...faces[0],state:'verified_hole'}]})],
 ['unphysical radius',ocpData({faces:[{...faces[0],radius_mm:-2}]})],
 ['non-numeric height',ocpData({faces:[{...faces[0],axial_height_mm:'bad'}]})]
]){
 assert.equal(ctx.gfValidatedOcpHoleReportProof(bad,UID,SHA,RUN,CASE),null,label);
}
(async()=>{
 const ocp=await ctx.gfFetchOcpHoleReportProof(UID,SHA,RUN,CASE);
 assert(ocp.proof&&callCount===1);
 const brep={proof:{faces:[
  {model_class:'hole_candidate',geometry_surface:'Cylinder'},
  {model_class:'non_hole',geometry_surface:'Plane'},
  {model_class:'hole_candidate',geometry_surface:'Cylinder'}
 ]}};
 const r12={proof:{predictions:[
  {predicted_hole_type:'through_hole',decision_basis:'model_and_brep_topology_agree'},
  {predicted_hole_type:'unverified',decision_basis:'model_topology_conflict'},
  {predicted_hole_type:'blind_hole',decision_basis:'insufficient_brep_evidence'}
 ]}};
 const rows=Array.from(ctx.gfCadMlResearchContrast(ocp,brep,r12));
 assert.equal(rows.length,4);
 assert.match(rows[0],/관통 원통면 2개.*막힌 원통면 1개.*미확정 원통면 1개/);
 assert.match(rows[0],/3\.000, 5\.500 mm/);
 assert.match(rows[1],/BrepMFR.*3개.*hole_candidate 2개.*non_hole 1개/);
 assert.match(rows[2],/R12.*관통 후보 1개.*막힘 후보 1개.*판정 보류 1개/);
 assert.match(rows[2],/충돌 1개/);
 assert.match(rows[3],/숫자가 같아도 실제 CAD 면별 정답 일치/);
 assert.match(rows[3],/R12 자체 모델과 위상 근거/);
 const anchor={insertAdjacentElement(_pos,node){this.inserted=node}};
 const sections=new Map([['geofield-local-hole-evidence',anchor]]);
 const dom={createElement(tag){return {tag,textContent:'',style:{},children:[],
  append(...nodes){this.children.push(...nodes)}}},
  getElementById:id=>sections.get(id)||null,body:{append(){throw Error('expected existing anchor')}}};
 ctx.gfAppendEvidenceScope(dom,null,null,null,rows);
 const panel=anchor.inserted;
 assert.equal(panel.id,'geofield-engineering-evidence-scope');
 const heading=panel.children.find(x=>x.tag==='h3');
 assert.equal(heading.textContent,'CAD 원통면 관찰 ↔ BrepMFR·R12 연구 예측 대조');
 const paragraphs=panel.children.filter(x=>x.tag==='p').map(x=>x.textContent);
 assert.equal(paragraphs.filter(x=>x.startsWith('CAD 독립 OCP')).length,1);
 assert.equal(paragraphs.filter(x=>x.startsWith('R12 연구용')).length,1);
 assert.equal(paragraphs.filter(x=>x.startsWith('BrepMFR 연구용')).length,1);
 assert.equal(paragraphs.filter(x=>x.startsWith('비교 해석:')).length,1);
 assert.doesNotMatch(paragraphs.join(' '),/정확도 [0-9]+%|홀 개수 확정|FEA 안전 인증 통과/);
 const missing=Array.from(ctx.gfCadMlResearchContrast(
  {proof:null,note:'독립 OCP 미지원'}, {proof:null,note:'ML 결과 없음'},
  {proof:null,note:'R12 미실행'}));
 assert.equal(missing.length,4);
 assert.match(missing[0],/미지원/);
 assert.match(missing[1],/ML 결과 없음/);
 assert.match(missing[2],/R12 미실행/);
 reply={status:'unavailable',cad_job_id:UID,sha256:SHA};
 assert.equal((await ctx.gfFetchOcpHoleReportProof(UID,SHA,RUN,CASE)).proof,null);
 fail=true;
 const outage=await ctx.gfFetchOcpHoleReportProof(UID,SHA,RUN,CASE);
 assert.equal(outage.proof,null);
 assert.match(outage.note,/조회 실패/);
 fail=false;
 selection=false;
 await assert.rejects(ctx.gfFetchOcpHoleReportProof(UID,SHA,RUN,CASE),
  /CAD·FEA 실행이 변경/);
 selection=true;
 ctx.get=async()=>{
  selection=false;
  return ocpData();
 };
 await assert.rejects(ctx.gfFetchOcpHoleReportProof(UID,SHA,RUN,CASE),
  /OCP 원통면 조회 중/);
 console.log('PASS: real OCP same-STEP conservative cylinders, BrepMFR/R12 separately verified aggregate comparison, internal R12 conflict counts, missing/mismatched input and stale selection rejected without ML/FEA/AI calls');
})().catch(e=>{console.error(e);process.exitCode=1});
