'use strict';
// Actual frontend completeness gate, no paid requests, solver or training.
// Reuses the production read-back/DOM methods rather than duplicating rules.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8').replace(/\r\n/g,'\n');
const a=src.indexOf('// GEOFIELD_REPORT_COMPLETENESS_COST_GATE_20261106');
const b=src.indexOf('async function gfBuildVisibleReport(',a);
assert(a>0&&b>a);
assert(src.includes('gfRequireCompletePaidReportEvidence(parsed,meshFollowup,brepProof,r12Proof,uid,sha,run,caseSha);'));
const builder=src.slice(b,src.indexOf('// GEOFIELD_AI_MESH_FEEDBACK_UI_V1',b));
const gateIndex=builder.indexOf('gfRequireCompletePaidReportEvidence(');
const paidIndex=builder.indexOf("await get('/api/agent/evidence/");
assert(gateIndex>=0&&paidIndex>gateIndex,'completeness gate must run BEFORE token-consuming request');
const UID='1'.repeat(32),SHA='a'.repeat(64),RUN='2'.repeat(32),CASE='b'.repeat(64),BID='3'.repeat(32),RID='4'.repeat(32);
const faces=[{face_ordinal:1,geometry_surface:'Cylinder',model_class:'unknown_hole',
 model_score_uncalibrated:.47},{face_ordinal:2,geometry_surface:'Plane',
 model_class:'non_hole',model_score_uncalibrated:.91}];
const task=(overrides={})=>({
 status:'complete',cad_job_id:UID,cad_sha256:SHA,id:BID,
 result:{sha256:SHA,decision_usage:'blocked_diagnostic_only',
  viewer_face_mapping_verified:false,trained_architecture_equivalence:'not_proven',
  variants:{topology_trimmed:{faces}}},...overrides});
function page(visualCount=2,bid=BID,rid=RID){
 const found=new Map();
 if(visualCount>=0)found.set('geofield-verified-fea-3d-views',{
  querySelectorAll:()=>Array.from({length:visualCount},(_,i)=>({
    tag:'img',src:'data:image/png;base64,c3RyZXNz',
    getAttribute:key=>({'data-gf-field-mode':i===0?'stress':'displacement',
      'data-gf-verified-run':RUN,'data-gf-verified-case':CASE})[key]||null
  }))});
 if(bid)found.set('geofield-brepmfr-research-evidence-report',{
  getAttribute:()=>bid});
 if(rid)found.set('geofield-r12-research-evidence-report',{
  getAttribute:()=>rid});
 const insertions=[];
 class Node{
  constructor(tag){this.tag=tag;this.children=[];this.style={};this.textContent='';this.attributes={};this.id='';}
  append(...items){this.children.push(...items)}
  setAttribute(name,val){this.attributes[name]=val}
  getAttribute(name){return this.attributes[name]||null}
  insertAdjacentElement(_where,el){insertions.push(el);found.set(el.id,el)}
 }
 const evidence=new Node('section');
 found.set('geofield-a08-evidence',evidence);
 return {doc:{body:new Node('body'),createElement:t=>new Node(t),
  getElementById:k=>found.get(k)||null},evidence,insertions};
}
const ctx={String,Array,Number,Math,Set,Object,Error,Promise,encodeURIComponent,
 gfReportSelectionCurrent:()=>true,meshSeriesBusy:false,
 gfThreeMeshRenderedReportComplete:()=>true,
 get:async()=>task()};
vm.createContext(ctx);vm.runInContext(src.slice(a,b),ctx);
(async()=>{
 const checked=ctx.gfBrepReportProof(task(),UID,SHA,RUN,CASE);
 assert(checked&&checked.faces.length===2);
 for(const [label,invalid] of [
  ['wrong SHA',task({cad_sha256:'f'.repeat(64)})],
  ['wrong ID',task({id:'wrong'})],
  ['failed worker',task({status:'failed'})],
  ['wrong model SHA',task({result:{...task().result,sha256:'f'.repeat(64)}})],
  ['wrong mode',task({result:{...task().result,decision_usage:'production_verified'}})],
  ['claimed CAD mapping',task({result:{...task().result,viewer_face_mapping_verified:true}})],
  ['claimed architecture match',task({result:{...task().result,trained_architecture_equivalence:'proven'}})],
  ['invalid score',task({result:{...task().result,variants:{topology_trimmed:{faces:[{...faces[0],model_score_uncalibrated:1.2}]}}}})],
  ['duplicate ordinal',task({result:{...task().result,variants:{topology_trimmed:{faces:[faces[0],faces[0]]}}}})]
 ])assert.equal(ctx.gfBrepReportProof(invalid,UID,SHA,RUN,CASE),null,label);
 let count=0;ctx.get=async url=>{count++;assert.equal(url,'/api/ml/latest/'+UID);return task()};
 const got=await ctx.gfFetchBrepReportProof(UID,SHA,RUN,CASE);
 assert(got.proof&&count===1);
 const p=page(),ok=ctx.gfAppendBrepReportProof(p.doc,p.evidence,got,SHA);
 assert(ok);
 const table=p.insertions[0].children.find(e=>e.tag==='table');
 assert(table&&table.children.length===3);
 assert.match(table.children[1].children.map(x=>x.textContent).join(' '),/47\.0% \(미보정\)/);
 const note=p.insertions[0].children.find(e=>e.tag==='p');
 assert.match(note.textContent,/정답률이 아니며/);
 const r12={proof:{runId:RID}},study={id:'5'.repeat(32)};
 const paid=(doc=p.doc,brep=got,r12proof=r12,mesh=study)=>
  ctx.gfRequireCompletePaidReportEvidence(doc,mesh,brep,r12proof,UID,SHA,RUN,CASE);
 assert.equal(paid(),true);
 assert.throws(()=>paid(page(1).doc),/FRD 이미지/);
 assert.throws(()=>paid(page(0).doc),/FRD 이미지/);
 assert.throws(()=>paid(page(2,null).doc),/BrepMFR/);
 assert.throws(()=>paid(page(2,BID,null).doc),/R12/);
 assert.throws(()=>paid(p.doc,{proof:null}),/BrepMFR/);
 assert.throws(()=>paid(p.doc,got,{proof:null}),/R12/);
 assert.throws(()=>paid(p.doc,got,r12,null),/메시 3회/);
 ctx.meshSeriesBusy=true;
 assert.throws(()=>paid(),/아직 진행 중/);
 ctx.meshSeriesBusy=false;
 ctx.gfThreeMeshRenderedReportComplete=()=>false;
 assert.throws(()=>paid(),/메시 3회/);
 ctx.gfThreeMeshRenderedReportComplete=()=>true;
 ctx.gfReportSelectionCurrent=()=>false;
 assert.throws(()=>paid(),/현재 CAD\/FEA 실행/);
 ctx.gfReportSelectionCurrent=()=>true;
 ctx.get=async()=>{throw Error('no worker archive')};
 const missing=await ctx.gfFetchBrepReportProof(UID,SHA,RUN,CASE);
 assert.equal(missing.proof,null);
 const incomplete=page();
 assert.equal(ctx.gfAppendBrepReportProof(incomplete.doc,incomplete.evidence,missing,SHA),false);
 assert.throws(()=>paid(incomplete.doc,missing),/BrepMFR/);
 assert.equal(count,1,'AI guard must not initiate a model run or paid request');
 // Restoring a missing image may re-read the existing signed FRD, never re-solve.
 let fieldReads=0,fieldSet=0,fieldReady=false;
 ctx.app={ready:true,mesh:{modelTransform:{center:[0,0,0],size:1}}};
 ctx.feaPreparedCaseSha=CASE;
 ctx.latestSummary={fea:{maximum_von_mises_mpa:14.758,maximum_displacement_mm:.0264}};
 ctx.gfFeaReportFieldMatches=()=>fieldReady;
 ctx.get=async url=>{
  assert.equal(url,'/api/fea/field/'+RUN);
  fieldReads++;
  return {schema:'geofield-fea-surface-field-v1',
   source:'actual_calculix_ascii_frd',cad_job_id:UID,run_id:RUN,
   cad_sha256:SHA,case_sha256:CASE};
 };
 ctx.setFeaField=(field,sha,caseSha,run,expected)=>{
  fieldSet++;
  assert.equal(field.cad_job_id,UID);
  assert.equal(sha,SHA);assert.equal(caseSha,CASE);assert.equal(run,RUN);
  assert.equal(expected.maximum_nodal_von_mises_mpa,14.758);
  assert.equal(expected.maximum_displacement_mm,.0264);
  fieldReady=true;
 };
 assert.equal(await ctx.gfRecoverReportFeaField(UID,SHA,RUN,CASE),true);
 assert.equal(fieldReads,1);assert.equal(fieldSet,1);
 assert.equal(await ctx.gfRecoverReportFeaField(UID,SHA,RUN,CASE),true);
 assert.equal(fieldReads,1,'available FRD field must not trigger redundant readback');
 fieldReady=false;ctx.get=async()=>{
  fieldReads++;return {schema:'geofield-fea-surface-field-v1',
    source:'actual_calculix_ascii_frd',cad_job_id:UID,run_id:'5'.repeat(32),
    cad_sha256:SHA,case_sha256:CASE};
 };
 assert.equal(await ctx.gfRecoverReportFeaField(UID,SHA,RUN,CASE),false);
 assert.equal(fieldSet,1,'different FEA field is not installed');
 ctx.gfReportSelectionCurrent=()=>false;
 assert.equal(await ctx.gfRecoverReportFeaField(UID,SHA,RUN,CASE),false);
 ctx.gfReportSelectionCurrent=()=>true;
 console.log('PASS: BrepMFR same-STEP evidence restored in HTML, invalid predictions refused, all paid-AI missing-data cases rejected BEFORE token-consuming call');
})().catch(e=>{console.error(e);process.exitCode=1});
