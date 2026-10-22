// Guard archived FEA recovery from delayed responses after new STEP import.
// Extract the REAL browser handler; no simulated solver data is accepted.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const src = fs.readFileSync(path.join(__dirname, '..', 'payload','frontend','cad.js'),'utf8');
const start = src.indexOf('async function restoreArchivedFea(');
const end = src.indexOf('let feaArchiveItems=', start);
const resetStart = src.indexOf('function resetModel(');
const resetEnd = src.indexOf('function textKV(', resetStart);
assert(start>=0 && end>start && resetStart>=0 && resetEnd>resetStart);
const handler = src.slice(start,end);
const reset=src.slice(resetStart,resetEnd);
assert.match(reset,/if\(!options\.preserveRestore\)\+\+feaRestoreGeneration/);
assert.match(handler,/resetModel\(\{preserveRestore:true\}\)/);

function context() {
 const events=[],logs=[],requests=[],trigger={disabled:false};
 const ui={
  feaLoadMode:{value:'mass_kg'},
  feaLoadQuantity:{value:'5'},
  feaMaterialPreset:{selectedOptions:[{textContent:'steel'}]},
 };
 const scope={
  Promise,Error,Number,Math,Array,Object,JSON,encodeURIComponent,
  feaRunId:null,stepSelectionVersion:1,feaRestoreGeneration:0,
  feaFixed:[],feaLoaded:[],
  window:{confirm:()=>true},
  status:(...args)=>logs.push(args),
  $:id=>ui[id]||{value:'',textContent:'',disabled:false},
  get:url=>new Promise((resolve,reject)=>requests.push({url,resolve,reject})),
  post:url=>new Promise((resolve,reject)=>requests.push({url,resolve,reject})),
 };
 vm.createContext(scope);
 vm.runInContext(handler,scope);
 const item={id:'a'.repeat(32),cad_sha256:'b'.repeat(64),job_id:'d'.repeat(32)};
 const snapshot={
  cad:{sha256:item.cad_sha256},
  fea:{state:'complete',setup:{material:'steel',fixed_faces:[1],load_faces:[3],external_mass_kg:5},
       result_run_id:'c'.repeat(32),result_case_sha256:'e'.repeat(64)}
 };
 return {scope,logs,requests,trigger,item,snapshot,events};
}
let count=0;
async function flush(){await Promise.resolve(); await Promise.resolve();}
async function checkFreshCancellation(flip,reject=false){
 const c=context(),run=c.scope.restoreArchivedFea(c.item,c.trigger);
 await flush();assert.equal(c.requests.length,1);
 flip(c);
 if(reject)c.requests[0].reject(new Error('test-only old response error'));
 else c.requests[0].resolve(c.snapshot);
 await run;
 assert.equal(c.logs.length,0,'stale history response must not write a UI status');
 assert.equal(c.requests.length,1,'stale history response must not trigger a preview');
 assert.equal(c.trigger.disabled,false);
 count++;
}
(async()=>{
 await checkFreshCancellation(c=>vm.runInContext('feaRestoreGeneration++',c.scope));
 await checkFreshCancellation(c=>vm.runInContext('stepSelectionVersion++',c.scope));
 await checkFreshCancellation(c=>vm.runInContext('feaRestoreGeneration++',c.scope),true);
 {
  const c=context(),run=c.scope.restoreArchivedFea(c.item,c.trigger);
  await flush();c.requests[0].reject(new Error('genuine archive network failure'));await run;
  assert.equal(c.logs.length,1,'current archive error should remain visible');
  assert.match(String(c.logs[0][0]),/복원 조건 비교 실패/);
  count++;
 }
 {
  const c=context(),run=c.scope.restoreArchivedFea(c.item,c.trigger);
  await flush();c.requests[0].resolve(c.snapshot);await flush();
  assert.equal(c.requests.length,2,'live verified archive must reach preview');
  assert.equal(c.trigger.disabled,true);
  vm.runInContext('feaRestoreGeneration++',c.scope);
  c.requests[1].resolve({run_id:'not-this-run'});
  await run;
  assert.equal(c.logs.length,1,'stale preview must not report restore error over the new CAD');
  assert.equal(c.trigger.disabled,true,'cancelled preview must not re-enable stale restore button');
  count++;
 }
 {
  const c=context(),run=c.scope.restoreArchivedFea(c.item,c.trigger);
  await flush();c.requests[0].resolve(c.snapshot);await flush();
  assert.equal(c.requests.length,2);
  vm.runInContext('stepSelectionVersion++',c.scope);
  c.requests[1].reject(new Error('old preview timed out'));
  await run;
  assert.equal(c.logs.length,1);
  assert.equal(c.trigger.disabled,true);
  count++;
 }
 assert.match(handler,/if\(stepSelectionVersion!==selectionVersion\|\|feaRestoreGeneration!==restoreGeneration\)return;/);
 count++;
 console.log('PASS: '+count+' actual archived FEA restore stale-response guards');
})().catch(e=>{console.error(e);process.exitCode=1;});
