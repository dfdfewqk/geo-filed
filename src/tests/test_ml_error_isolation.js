// Run the REAL ML status and preflight callbacks with delayed synthetic HTTP.
// Never invoke an ML model, CAD parser, real user file, or FEA solver.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
function extract(start){
 const a=source.indexOf(start);assert(a>=0,'production function missing: '+start);
 const b=source.indexOf('\n}',a);
 assert(b>a,'production function end missing: '+start);
 return source.slice(a,b+2);
}
const code=extract('async function loadBrepPreflight(')+'\n'+extract('async function watchAutoMl(');
function defer(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};}
function harness(){
 const elements=new Map(),pending=[],calls={render:0,summary:0},ui={
  brepMlRunBtn:{disabled:true},brepMlPreflight:{textContent:''},
  brepMlResults:{textContent:''}
 };
 const scope={
  Promise, Error, Boolean, Object, Number,
  jobId:'1'.repeat(32),current:{sha256:'a'.repeat(64)},file:{name:'part.step'},
  stepSelectionVersion:1,autoMlGeneration:0,brepReady:false,brepRunning:false,
  autoMlToggle:{checked:true},
  $:id=>ui[id]??={textContent:'',disabled:false},
  get:url=>{const d=defer();pending.push({url,...d});return d.promise;},
  renderBrepResult:()=>{calls.render++;return true;},
  loadCurrentResults:async()=>{calls.summary++;},
  sleep:async()=>{},
 };
 vm.createContext(scope);vm.runInContext(code,scope);
 return {scope,ui,pending,calls,
  switchCad(){vm.runInContext("jobId='2'.repeat(32);current={sha256:'b'.repeat(64)};stepSelectionVersion++;autoMlGeneration++;",scope);}
 };
}
const state=()=>({available:true,python_executable:'synthetic',python_errors:{},missing:[]});
let passes=0;
async function currentCheck(){
 const h=harness(),work=h.scope.loadBrepPreflight();
 assert.equal(h.pending.length,1);h.pending[0].resolve(state());await work;
 assert.equal(h.scope.brepReady,true);assert.equal(h.ui.brepMlRunBtn.disabled,false);passes++;
}
async function delayedPreflight(change,throws=false){
 const h=harness(),work=h.scope.loadBrepPreflight();
 change(h);if(throws)h.pending[0].reject(Error('old preflight fail'));
 else h.pending[0].resolve(state());
 await work;
 assert.equal(h.ui.brepMlPreflight.textContent,'');
 assert.equal(h.ui.brepMlRunBtn.disabled,true);
 assert.equal(h.scope.brepReady,false);passes++;
}
async function currentFailure(){
 const h=harness(),work=h.scope.loadBrepPreflight();h.pending[0].reject(Error('ML unavailable'));
 await work;assert.match(h.ui.brepMlPreflight.textContent,/ML unavailable/);
 assert.equal(h.scope.brepReady,false);passes++;
}
async function oldStatusReject(){
 const h=harness(),work=h.scope.watchAutoMl(h.scope.jobId,h.scope.current.sha256,0);
 assert.equal(h.pending.length,1);h.switchCad();
 h.ui.brepMlResults.textContent='new STEP: FEA untouched';
 h.pending[0].reject(Error('old model response fail'));
 await work;assert.equal(h.ui.brepMlResults.textContent,'new STEP: FEA untouched');
 assert.equal(h.calls.render,0);assert.equal(h.calls.summary,0);passes++;
}
async function oldStatusSuccess(){
 const h=harness(),work=h.scope.watchAutoMl(h.scope.jobId,h.scope.current.sha256,0);
 h.switchCad();h.ui.brepMlResults.textContent='new STEP';
 h.pending[0].resolve({status:'complete',result:{sha256:'a'.repeat(64),decision_usage:'blocked_diagnostic_only'}});
 await work;assert.equal(h.ui.brepMlResults.textContent,'new STEP');
 assert.equal(h.calls.render,0);passes++;
}
async function currentStatusFailure(){
 const h=harness(),work=h.scope.watchAutoMl(h.scope.jobId,h.scope.current.sha256,0);
 h.pending[0].resolve({status:'failed',message:'missing model'});
 await work;assert.match(h.ui.brepMlResults.textContent,/missing model/);
 assert.equal(h.calls.render,0);passes++;
}
async function disabledStaleGeneration(){
 const h=harness();vm.runInContext('autoMlGeneration++',h.scope);
 await h.scope.watchAutoMl(h.scope.jobId,h.scope.current.sha256,0);
 assert.equal(h.pending.length,0);assert.equal(h.ui.brepMlResults.textContent,'');passes++;
}
(async()=>{
 await currentCheck();
 await delayedPreflight(h=>h.switchCad());
 await delayedPreflight(h=>h.switchCad(),true);
 await currentFailure();
 await oldStatusReject();
 await oldStatusSuccess();
 await currentStatusFailure();
 await disabledStaleGeneration();
 console.log('PASS: '+passes+' ML delayed response and CAD/FEA UI isolation checks');
})().catch(e=>{console.error(e);process.exitCode=1;});
