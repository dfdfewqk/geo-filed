// Production R12 automatic research fallback view; simulated DOM and local APIs.
// No model, STEP file, CCX or network usage.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
function snippet(a,b){
 const start=source.indexOf(a),end=source.indexOf(b,start);
 assert(start>=0&&end>start,'missing source R12 UI: '+a);
 return source.slice(start,end);
}
const JOB='a'.repeat(32),SHA='b'.repeat(64);
let htmlCalls=0,getFn=async()=>{throw Error('unset mock route');};
const dom=new Map();
const $=id=>{
 if(!dom.has(id))dom.set(id,{textContent:'',children:[],
   append(...nodes){this.children.push(...nodes);}});
 return dom.get(id);
};
const doc={createElement:tag=>({
 tagName:tag,textContent:'',className:'',children:[],
 append(...items){this.children.push(...items);}
})};
const scope=vm.createContext({
 $,document:doc,jobId:JOB,current:{sha256:SHA},
 autoMlGeneration:0,r12Generation:0,
 get:async path=>getFn(path),sleep:async()=>{},
 loadCurrentResults:async()=>{htmlCalls++;},
 geoApiError:e=>e,
});
vm.runInContext(snippet('async function watchAutoR12(','$('brepMlRunBtn').onclick='),scope);
vm.runInContext(snippet('function renderR12Result(','$('r12RunBtn').onclick='),scope);
function good(){
 return {cad_sha256:SHA,decision_usage:'blocked_diagnostic_only',
  status:'research_not_for_production',is_independent_r12_research:true,
  fea_calculated:false,geometry_certified:false,
  candidate_count:1,predictions:[{face_index:2,predicted_hole_type:'unverified',
   decision_basis:'model_topology_conflict',raw_ml_top_class:'through_hole',
   uncalibrated_model_score:0.4}]};
}
(async()=>{
 scope.renderR12Result(good(),SHA);
 assert.equal($('r12Result').children.length,2);
 assert.match($('r12Result').children[0].textContent,/FEA에 사용되지 않음/);
 for(const tamper of [
  x=>x.cad_sha256='c'.repeat(64),
  x=>x.geometry_certified=true,
  x=>x.fea_calculated=true,
  x=>x.is_independent_r12_research=false,
  x=>x.status='production',
  x=>x.candidate_count=2
 ]){
  const d=good();tamper(d);
  assert.throws(()=>scope.renderR12Result(d,SHA),/계약/);
 }
 let accesses=[];
 getFn=async path=>{
  accesses.push(path);
  return {id:'c'.repeat(32),cad_job_id:JOB,cad_sha256:SHA,
    status:'complete',result:good()};
 };
 dom.set('r12Result',{textContent:'',children:[],append(...parts){this.children.push(...parts);}});
 await scope.watchAutoR12(JOB,SHA,0);
 assert.deepEqual(accesses,['/api/ml/r12/latest/'+JOB]);
 assert.equal($('r12Result').children.length,2);
 assert.equal(htmlCalls,1);
 const previous=$('r12Result').children.length;
 scope.jobId='f'.repeat(32);
 await scope.watchAutoR12(JOB,SHA,0);
 assert.equal($('r12Result').children.length,previous,'stale CAD never inserts research result');
 scope.jobId=JOB;
 getFn=async()=>({id:'c'.repeat(32),cad_job_id:'1'.repeat(32),
                  cad_sha256:SHA,status:'complete',result:good()});
 await scope.watchAutoR12(JOB,SHA,0);
 assert.match($('r12Result').textContent,/불일치/);
 assert.equal($('r12Result').children.length,previous);
 console.log('PASS: R12 manual/automatic UI research-only source and stale CAD gates');
})().catch(e=>{console.error(e);process.exit(1);});
