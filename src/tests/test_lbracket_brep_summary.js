// Test real summary renderer and B-Rep helper, no real STEP, installed model,
// FEA solve, user data, APIs or browser required.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const start=source.indexOf('function gfIndependentBrepStatus(');
const end=source.indexOf('const autoMlToggle=',start);
assert(start>=0&&end>start,'Expected original production CAD summary code');
const code=source.slice(start,end);
const ID='a'.repeat(32), SHA='b'.repeat(64);
const faces=Array.from({length:4},(_,i)=>({
 face_ordinal:i+1,state:'through_hole',radius_mm:2.75
}));
function proof(overrides={}){
 return {cad_job_id:ID,sha256:SHA,status:'complete',
         source:'local_ocp_solid_occupancy_not_ml',
         viewer_face_mapping_verified:false,
         decision_usage:'cad_diagnostic_only_not_fea_or_safety',
         faces:faces.map(f=>({...f})),...overrides};
}
function summary(){
 return {cad:{sha256:SHA,parts:[{bbox_mm:{x:50,y:30,z:50},surface_area_mm2:6599.27876}],
             hole_candidates:faces.map((_,i)=>({id:'CAD'+i}))},
         ml:{state:'failed',status_text:'BrepMFR 오분류 미검증'},
         fea:{state:'not_run',status_text:'미실행',conditions_saved:false,
              missing_tools:[]},
         r12_research_status:{state:'not_run'},fea_case_provenance:{}};
}
function node(){
 let txt='';return {children:[],disabled:false,
  get textContent(){return txt;},
  set textContent(v){txt=String(v);this.children=[];},
  append(...values){this.children.push(...values);}};
}
async function run({evidence=proof(),fail=false,delayed=false}={}){
 const dom=new Map();
 const $=id=>{if(!dom.has(id))dom.set(id,node());return dom.get(id);};
 let unblock=null,reads=[];
 const scope=vm.createContext({
  $,document:{createElement:()=>node()},textKV:(key,value)=>({key,value}),
  gfReportReady:()=>false,jobId:ID,current:{sha256:SHA},
  get:async route=>{
   reads.push(route);
   if(route==='/api/results/summary/'+ID)return summary();
   assert.equal(route,'/api/geometry/hole-evidence/'+ID);
   if(delayed)await new Promise(resolve=>{unblock=resolve;});
   if(fail)throw Error('OCP unavailable');
   return evidence;
  }
 });
 vm.runInContext(code,scope);
 const pending=scope.loadCurrentResults();
 if(delayed){
  for(let i=0;i<40&&!unblock;i++)await Promise.resolve();
  assert(unblock,'Second request must be reached');
  scope.current={sha256:'c'.repeat(64)};
  unblock();
 }
 await pending;
 const kv=$('resultsOverview').children.filter(x=>x&&typeof x.key==='string');
 return {values:Object.fromEntries(kv.map(x=>[x.key,x.value])),reads,
         count:kv.length,resultNode:$('resultsOverview')};
}
(async()=>{
 const good=await run();
 assert.match(good.values['독립 관통 판정'],/관통 4개/);
 assert.match(good.values['독립 관통 판정'],/CAD 홀 후보 및 3D 면과 대응 미검증/);
 assert.match(good.values['기존 BrepMFR 연구 모델'],/오분류 미검증/);
 assert.equal(good.reads.length,2);
 for(const altered of [
   proof({sha256:'c'.repeat(64)}),
   proof({cad_job_id:'c'.repeat(32)}),
   proof({viewer_face_mapping_verified:true}),
   proof({decision_usage:'can_drive_FEA'}),
   proof({faces:[faces[0],faces[0]]}),
   proof({faces:[{face_ordinal:1,state:'production_safe'}]}),
   proof({status:'complete',source:'legacy_neural_model'})
 ]){
  const bad=await run({evidence:altered});
  assert.match(bad.values['독립 관통 판정'],/미확인/);
  assert.doesNotMatch(bad.values['독립 관통 판정'],/관통 4개/);
 }
 const unavailable=await run({fail:true});
 assert.match(unavailable.values['독립 관통 판정'],/미확인/);
 assert.match(unavailable.values['CAD 실제 측정'],/50 × 30 × 50 mm/);
 const stale=await run({delayed:true});
 assert.equal(stale.count,0,'Switching CAD must not publish stale results');
 console.log('L-bracket P0 CAD SHA-bound four-hole summary / optional OCP fallback PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
