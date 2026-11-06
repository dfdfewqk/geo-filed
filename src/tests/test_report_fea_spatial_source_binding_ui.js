'use strict';
// Real report spatial-evidence functions: original source-backed data contract,
// synthetic responses for replay; never solve FEA or call a paid provider.
const assert=require('node:assert/strict'),fs=require('node:fs'),
      path=require('node:path'),vm=require('node:vm');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const start=src.indexOf('function gfVerifiedSpatialReportProof('),
 end=src.indexOf('// GEOFIELD_CAD_ML_EVIDENCE_CONTRAST_20261106',start);
assert(start>0&&end>start,'actual report spatial validator and renderer must exist');
const UID='1'.repeat(32),SHA='a'.repeat(64),RUN='2'.repeat(32),CASE='b'.repeat(64);
function evidence(){
 const peak=(value,unit,position,index,prox)=>({
  source:'reverified_actual_calculix_surface_nodes',
  surface_node_index:index,value,unit,position_mm:position,
  cad_face_proximity:prox
 });
 const close={status:'geometric_proximity_candidate_only',
  cad_face_id_candidate:7,distance_mm:0.0005};
 return {schema:'geofield-evidence-agent-v1',cad_sha256:SHA,
  fea:{status:'INP_STA_FRD_reverified',run_id:RUN,case_sha256:CASE,
   maximum_von_mises_mpa:16,maximum_displacement_mm:.3},
  fea_spatial:{schema:'geofield-agent-fea-spatial-v1',
   status:'verified_frd_surface_peak_positions',cad_sha256:SHA,
   case_sha256:CASE,run_id:RUN,cad_face_attribution_verified:false,
   proximity_tolerance_mm:.005,
   stress_peak:peak(14.5,'MPa',[10,12,14],9,close),
   displacement_peak:peak(.22,'mm',[30,2,3],11,
    {status:'ambiguous_faces',cad_face_id_candidate:null,distance_mm:null})}
 };
}
class Node{
 constructor(tag){this.tag=tag;this.textContent='';this.style={};this.id='';
  this.children=[];}
 append(...items){this.children.push(...items)}
 insertAdjacentElement(_where,item){this.children.push(item)}
}
function make(data=evidence(),same=true){
 const calls=[];
 const anchor=new Node('section'),body=new Node('body');
 const doc={body,createElement:tag=>new Node(tag),
  getElementById:id=>id==='geofield-a08-evidence'?anchor:null};
 const ctx={Number,Math,String,Array,Error,Promise,encodeURIComponent,
  latestSummary:{fea:{maximum_von_mises_mpa:16,maximum_displacement_mm:.3}},
  gfReportSelectionCurrent:()=>same,
  get:async(url,timeout)=>{
   calls.push({url,timeout});return data;
  }};
 vm.createContext(ctx);vm.runInContext(src.slice(start,end),ctx);
 return {calls,ctx,anchor,doc,
  validate:()=>ctx.gfVerifiedSpatialReportProof(data,UID,SHA,RUN,CASE),
  fetch:()=>ctx.gfFetchVerifiedSpatialReportProof(UID,SHA,RUN,CASE),
  append:proof=>ctx.gfAppendVerifiedSpatialReportProof(doc,anchor,proof)};
}
(async()=>{
 const good=make();
 const proof=await good.fetch();
 assert(proof,'actual independently verified FRD 3D values must be linked');
 assert.equal(good.calls.length,1);
 assert.equal(good.calls[0].url,'/api/agent/evidence/'+UID);
 assert.equal(good.calls[0].timeout,45000);
 assert(!good.calls[0].url.includes('llm=1'),'read-only spatial proof never spends tokens');
 assert.equal(proof.stress_peak.value,14.5);
 assert.deepEqual(Array.from(proof.stress_peak.position),[10,12,14]);
 assert.equal(proof.stress_peak.cadCandidate.id,7);
 assert.equal(proof.displacement_peak.cadCandidate,null,
  'ambiguous overlapping CAD face triangles must have no face selection');
 assert.equal(good.append(proof),true);
 const section=good.anchor.children[0];
 assert.equal(section.id,'geofield-verified-fea-surface-spatial-evidence');
 const text=section.children.map(x=>x.textContent).join(' ');
 assert.match(text,/14\.500000 MPa/);
 assert.match(text,/0\.22000000 mm/);
 assert.match(text,/CAD 표면 좌표근접 후보 면 7/);
 assert.match(text,/면 일치\/원인 확정 아님/);
 assert.match(text,/전체 체적\/절점 최대치와 표면 최대치는 다를 수/);
 assert.equal(good.append(null),false);
 assert.equal(good.anchor.children.length,1);
 const tests=[
  ['old CAD SHA',d=>d.cad_sha256='f'.repeat(64)],
  ['old FEA run',d=>d.fea.run_id='3'.repeat(32)],
  ['old solved case',d=>d.fea_spatial.case_sha256='d'.repeat(64)],
  ['unverified source',d=>d.fea_spatial.status='not_verified'],
  ['fake original field',d=>d.fea_spatial.stress_peak.source='saved_json_only'],
  ['surface exceeds actual global stress',d=>d.fea_spatial.stress_peak.value=99],
  ['surface exceeds actual global displacement',d=>d.fea_spatial.displacement_peak.value=.7],
  ['NaN coordinate',d=>d.fea_spatial.stress_peak.position_mm[0]=Number.NaN],
  ['negative invalid source coordinate',d=>d.fea_spatial.stress_peak.position_mm[0]=-1e8],
  ['fake verified CAD face match',d=>d.fea_spatial.cad_face_attribution_verified=true],
  ['no numeric proximity tolerance',d=>d.fea_spatial.proximity_tolerance_mm=NaN],
  ['distance too large for CAD surface',d=>d.fea_spatial.stress_peak.cad_face_proximity.distance_mm=.1],
  ['unverified CAD face ID',d=>d.fea_spatial.stress_peak.cad_face_proximity.cad_face_id_candidate=null],
  ['ambiguous proximity illegally provides face',d=>d.fea_spatial.displacement_peak.cad_face_proximity.cad_face_id_candidate=7],
  ['false displacement unit',d=>d.fea_spatial.displacement_peak.unit='MPa'],
  ['fake whole-body maxima',d=>d.fea.maximum_von_mises_mpa=88]
 ];
 for(const [name,change] of tests){
  const v=evidence();change(v);
  const t=make(v);
  assert.equal(t.validate(),null,name);
  assert.equal(t.append(t.validate()),false);
 }
 const stale=make(evidence(),false);
 assert.equal(await stale.fetch(),null,'same case/run/STEP MUST remain selected');
 assert.equal(stale.calls.length,0);
 assert(src.includes('gfAppendVerifiedSpatialReportProof(parsed,evidence,spatialProof)'),
  'actual unified HTML preview/save/Stage3 builder must include spatial appendix');
 console.log('PASS: source-reverified real FRD stress/displacement 3D coordinates, orthogonal CAD proximity only, 16 forged/mismatched sources blocked, AI OFF');
})().catch(e=>{console.error(e);process.exitCode=1});
