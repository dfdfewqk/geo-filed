// Exercise the PRODUCTION CAD dimensions handler against an in-memory DOM.
// This does not run OCC/ML or invent a UI face-id mapping.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const a=code.indexOf("$('geometryDimBtn').onclick=async()=>{");
const b=code.indexOf('function renderBrepResult(',a);
assert(a>=0&&b>a);
const script=code.slice(a,b);
const SHA='a'.repeat(64),ID='1'.repeat(32);
function dom(){
 const elements=new Map();
 const $=id=>{
  if(!elements.has(id))elements.set(id,{
   children:[],textContent:'',disabled:false,
   append(...items){this.children.push(...items);}
  });
  return elements.get(id);
 };
 return {$,elements};
}
function trial(holeResult){
 const {$}=dom();
 const calls=[];
 const scope=vm.createContext({
  $, document:{createElement:tag=>({tag,textContent:'',className:''})},
  jobId:ID,current:{sha256:SHA},stepSelectionVersion:1,app:{mesh:null},
  get:async url=>{
   calls.push(url);
   if(url.startsWith('/api/geometry/dimensions/'))
    return {cad_sha256:SHA,parts:[],candidates:[]};
   return holeResult;
  }
 });
 vm.runInContext(script,scope);
 return {scope,$,calls};
}
(async()=>{
 const proof={cad_job_id:ID,sha256:SHA,status:'complete',
  source:'local_ocp_solid_occupancy_not_ml',
  viewer_face_mapping_verified:false,
  decision_usage:'cad_diagnostic_only_not_fea_or_safety',
  faces:[
   {face_ordinal:7,state:'through_hole',radius_mm:2.5},
   {face_ordinal:9,state:'blind_hole',radius_mm:3.0},
   {face_ordinal:10,state:'unverified'}]};
 let t=trial(proof);
 await t.$('geometryDimBtn').onclick();
 let text=t.$('geometryDimResults').children.map(v=>v.textContent).join(' ');
 assert.match(text,/B-Rep 솔리드 점유 판정/);
 assert.match(text,/관통홀/);
 assert.match(text,/막힌홀/);
 assert.match(text,/미확정/);
 assert.match(text,/ML 아님/);
 assert.equal(t.calls[1],'/api/geometry/hole-evidence/'+ID);
 t=trial({...proof,sha256:'b'.repeat(64)});
 await t.$('geometryDimBtn').onclick();
 text=t.$('geometryDimResults').children.map(v=>v.textContent).join(' ');
 assert.match(text,/추가 B-Rep 홀 판정 확인 불가/);
 assert.equal(t.$('geometryDimResults').children.length,2,
   'core dimensions remain visible after geometry proof mismatch');
 t=trial({...proof,status:'unavailable',faces:[]});
 await t.$('geometryDimBtn').onclick();
 text=t.$('geometryDimResults').children.map(v=>v.textContent).join(' ');
 assert.match(text,/B-Rep 보수적 홀 판정 미지원/);
 console.log('PASS: 3 production B-Rep hole display + stale SHA cases');
})().catch(err=>{console.error(err);process.exitCode=1;});
