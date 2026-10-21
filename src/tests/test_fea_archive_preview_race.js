// Real GeoField archive-preview handler with synthetic delayed FRD responses.
// Confirms numerical consistency and read-only selection binding; no solver executed.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
function block(a,b){
 const i=source.indexOf(a),j=source.indexOf(b,i);
 assert(i>=0&&j>i,'missing production callback: '+a);return source.slice(i,j);
}
const summary=block('function gfFeaFieldSummaryCheck(','function setFeaField(');
const callback=block("$('feaArchive3DPreviewBtn').onclick=async()=>{",'async function loadFeaArchive(');
const SNAP='1'.repeat(32),NEXT='2'.repeat(32),RUN='3'.repeat(32),CAD='a'.repeat(64),CASE='b'.repeat(64);
const proof=()=>({ok:true,read_only:true,three_d_field_verified:true,snapshot_id:SNAP,run_id:RUN,
 cad_sha256:CAD,case_sha256:CASE,maximum_von_mises_mpa:6,maximum_displacement_mm:0.2});
const answer=()=>({ok:true,read_only:true,snapshot_id:SNAP,run_id:RUN,cad_sha256:CAD,case_sha256:CASE,
 maximum_von_mises_mpa:6,maximum_displacement_mm:0.2,
 field:{positions_mm:[[0,0,0],[1,0,0],[0,1,0]],triangles:[[0,1,2]],
 von_mises_mpa:[1,2,3],displacements_mm:[[0,0,0],[0,0,0],[0,0,0]]}});
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}};
function context(get){
 const el=new Map(),calls={draw:0,close:0};
 const $=id=>{if(!el.has(id))el.set(id,{disabled:false,textContent:''});return el.get(id);};
 const sandbox={
  $,get,feaArchiveSelector:{value:SNAP},feaArchiveVerified:proof(),
  feaArchiveSelectedGeneration:1,r185Modal:{hidden:true,style:{}},
  r185PreviewField:null,r185PreviewProof:null,r185PreviewYaw:0,r185PreviewPitch:0,r185PreviewZoom:0,
  r185Close(){calls.close++},r185Draw(){calls.draw++}
 };
 const ctx=vm.createContext(sandbox);
 vm.runInContext(summary+callback,ctx);
 return {ctx,$,calls,start:()=>vm.runInContext("$('feaArchive3DPreviewBtn').onclick()",ctx),
  switch:()=>vm.runInContext("feaArchiveSelector.value='"+NEXT+"';feaArchiveSelectedGeneration++;feaArchiveVerified=null;",ctx)};
}
async function main(){
 let checks=0;
 {
  const x=context(async()=>answer());await x.start();
  assert.equal(x.calls.draw,1);assert.equal(x.calls.close,0);
  assert.equal(x.ctx.r185PreviewProof.run_id,RUN);checks++;
 }
 for(const mismatch of [
  x=>x.run_id=NEXT,
  x=>x.case_sha256='f'.repeat(64),
  x=>x.field.triangles=[[0,1,9]],
  x=>x.field.von_mises_mpa=[1,2,20],
  x=>x.maximum_von_mises_mpa=15,
  x=>x.field.displacements_mm[2]=[0,0,4]
 ]){
  const sample=answer();mismatch(sample);
  const x=context(async()=>sample);await x.start();
  assert.equal(x.calls.draw,0);
  assert.equal(x.calls.close,1);checks++;
 }
 // Stale success or error must not close/overwrite the newly selected result.
 for(const reject of [false,true]){
  const gate=deferred(),x=context(()=>gate.promise),pending=x.start();
  x.switch();x.$('feaArchive3DHint').textContent='new result selection';
  if(reject)gate.reject(new Error('old solver evidence unavailable'));
  else gate.resolve(answer());
  await pending;
  assert.equal(x.calls.close,0);
  assert.equal(x.calls.draw,0);
  assert.equal(x.$('feaArchive3DHint').textContent,'new result selection');checks++;
 }
 console.log('PASS: '+checks+' archived FRD field provenance, maxima and selection-race cases');
}
main().catch(err=>{console.error(err);process.exitCode=1});
