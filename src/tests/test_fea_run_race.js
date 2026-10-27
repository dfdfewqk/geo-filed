// Exercise the production FEA run callback with delayed and mismatched mock replies.
// No solver calculation: mocked results are synthetic contract fixtures.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const a=src.indexOf("$('feaRunBtn').onclick=async()=>{");
const b=src.indexOf('// GeoField R18.4',a);
assert(a>=0&&b>a);
const runCallback=src.slice(a,b);
const JOB='1'.repeat(32),RUN='2'.repeat(32),NEW='3'.repeat(32),SHA='a'.repeat(64),CASE='b'.repeat(64);
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject};};
const result=()=>({cad_sha256:SHA,case_sha256:CASE,results:{
  maximum_nodal_von_mises_mpa:3,maximum_displacement_mm:0.02},
  mesh:{tetrahedron_count:100,node_count:80},field_visualization:{available:true}});
const task=()=>({id:RUN,cad_job_id:JOB,cad_sha256:SHA,case_sha256:CASE,status:'complete',result:result()});
function makeRunContext({fetch,get}){
 const elements=new Map(),calls={field:0,table:0};
 const $=id=>{if(!elements.has(id))elements.set(id,{disabled:false,textContent:'',value:'',classList:{add(){},remove(){}}});return elements.get(id);};
 const sandbox={
   $,fetch,get,window:{confirm:()=>true},status(){},resetFeaField(){},gfInvalidateAgentFeaEvidence(){},
   gfFeaTableShow(){calls.table++},gfLoadAuditSummary:()=>null,setFeaField(){calls.field++},
   loadCurrentResults:async()=>{},sleep:async()=>{},console
 };
 const ctx=vm.createContext(sandbox);
 vm.runInContext("let current={sha256:'"+SHA+"'},jobId='"+JOB+"',file={name:'part.step'},"+
   "feaReady=true,feaPrepared=true,feaPreparedCaseSha='"+CASE+"',"+
   "feaRunId=null,stepSelectionVersion=1,feaRestoreGeneration=0;"+runCallback,ctx);
 return {ctx,$,calls,start:()=>vm.runInContext("$('feaRunBtn').onclick()",ctx),
   switchStep:()=>{
     vm.runInContext("current={sha256:'"+SHA+"'};jobId='"+NEW+"';stepSelectionVersion++;feaRunId=null;feaPrepared=false;feaPreparedCaseSha=null;",ctx);
     $('feaRunStatus').textContent='새 STEP 상태';
     $('feaContourStatus').textContent='새 STEP 3D 상태';
   },
   switchCase:()=>{vm.runInContext("feaPreparedCaseSha='c'.repeat(64);feaRunId=null;feaPrepared=false;",ctx);$('feaRunStatus').textContent='새 FEA 조건';}
 };
}
async function main(){
 let checks=0;
 // Old POST reply cannot mark the newly imported STEP as failed or complete.
 {
  const gate=deferred(),x=makeRunContext({fetch:()=>gate.promise,get:async()=>{throw Error('unexpected poll')}});
  const pending=x.start();x.switchStep();
  gate.resolve({ok:true,json:async()=>({id:RUN,cad_sha256:SHA})});
  await pending;
  assert.equal(x.$('feaRunStatus').textContent,'새 STEP 상태');
  assert.equal(vm.runInContext('feaRunId',x.ctx),null);
  assert.equal(x.calls.table,0);checks++;
 }
 // Old status response cannot install output after the selection changes while polling.
 {
  const gate=deferred(),x=makeRunContext({fetch:async()=>({ok:true,json:async()=>({id:RUN,cad_sha256:SHA})}),get:()=>gate.promise});
  const pending=x.start();
  await Promise.resolve();await Promise.resolve();await Promise.resolve();
  x.switchStep();gate.resolve(task());await pending;
  assert.equal(x.$('feaRunStatus').textContent,'새 STEP 상태');
  assert.equal(x.calls.table,0);checks++;
 }
 // A changed FEA case blocks a pending calculation result.
 {
  const gate=deferred(),x=makeRunContext({fetch:async()=>({ok:true,json:async()=>({id:RUN,cad_sha256:SHA})}),get:()=>gate.promise});
  const pending=x.start();await Promise.resolve();await Promise.resolve();await Promise.resolve();
  x.switchCase();gate.resolve(task());await pending;
  assert.equal(x.$('feaRunStatus').textContent,'새 FEA 조건');assert.equal(x.calls.table,0);checks++;
 }
 // Current run with matching CAD/run/case status retains existing normal behavior.
 {
  const x=makeRunContext({
   fetch:async()=>({ok:true,json:async()=>({id:RUN,cad_sha256:SHA})}),
   get:async url=>url.includes('/api/fea/status/')?task():{positions_mm:[]}
  });
  await x.start();
  assert.equal(x.calls.table,1);assert.equal(x.calls.field,1);
  assert.equal(vm.runInContext('feaRunId',x.ctx),RUN);checks++;
 }
 // A mismatched status identity is rejected before numerical results enter the UI.
 for(const key of ['id','cad_job_id','cad_sha256','case_sha256']){
  const wrong=task();wrong[key]=(key==='id'||key==='cad_job_id')?NEW:'e'.repeat(64);
  const x=makeRunContext({
   fetch:async()=>({ok:true,json:async()=>({id:RUN,cad_sha256:SHA})}),
   get:async()=>wrong
  });
  await x.start();
  assert.equal(x.calls.table,0);assert.equal(x.calls.field,0);
  assert.equal(vm.runInContext('feaRunId',x.ctx),null);checks++;
 }
 // Old 3D field arriving after a new STEP cannot overwrite the new viewer status.
 {
  const gate=deferred(),x=makeRunContext({
   fetch:async()=>({ok:true,json:async()=>({id:RUN,cad_sha256:SHA})}),
   get:async url=>url.includes('/api/fea/status/')?task():gate.promise
  });
  const pending=x.start();
  for(let i=0;i<6;i++)await Promise.resolve();
  x.switchStep();gate.resolve({});await pending;
  assert.equal(x.$('feaContourStatus').textContent,'새 STEP 3D 상태');
  assert.equal(x.calls.field,0);checks++;
 }
 console.log('PASS: '+checks+' FEA active-run identity and late-status guards');
}
main().catch(e=>{console.error(e);process.exitCode=1});
