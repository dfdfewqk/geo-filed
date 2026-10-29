// P5: exercise actual integrated frontend summary and FEA invalidation handlers.
// Synthetic delayed local GET responses only; no real Windows/STEP/FRD/model.
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
function slice(start,end){
 const a=src.indexOf(start),b=src.indexOf(end,a);
 assert(a>=0&&b>a,'Production handler missing: '+start);
 return src.slice(a,b);
}
const handlers=slice('function gfIndependentBrepStatus(','const autoMlToggle=')
 +slice('function gfInvalidateAgentFeaEvidence(reason){','function invalidateFea(message){');
const CAD='a'.repeat(64),ID='1'.repeat(32),RUN='2'.repeat(32);
function summary(state){
 return {cad:{sha256:CAD,parts:[{bbox_mm:{x:50,y:30,z:50},
            surface_area_mm2:6599.27876}],hole_candidates:[]},
  ml:{state:'failed',status_text:'research not verified'},
  fea:{state,status_text:state,conditions_saved:true,
       setup:{material:'steel',force_n:49, target_mesh_mm:1.8},missing_tools:[],
       maximum_von_mises_mpa:state==='complete'?12:null,
       maximum_displacement_mm:state==='complete'?.03:null},
  fea_case_provenance:{verified_run_id:state==='complete'?RUN:null},
  r12_research_status:{state:'not_run'}};
}
function deferred(){let resolve;const promise=new Promise(ok=>{resolve=ok;});return{promise,resolve};}
function node(){
 return {children:[],disabled:false,checked:false,_text:'',
  get textContent(){return this._text;},
  set textContent(v){this._text=String(v);this.children=[];},
  append(...v){this.children.push(...v)}};
}
function harness(fetchSummary){
 const nodes=new Map(),$=key=>{
  if(!nodes.has(key))nodes.set(key,node());
  return nodes.get(key);
 };
 const ctx=vm.createContext({
  $,document:{createElement:()=>node()},
  textKV:(k,v)=>({key:k,value:String(v)}),
  gfReportReady:v=>v?.fea?.state==='complete',
  get:route=>{
   if(route==='/api/results/summary/'+ID)return fetchSummary();
   if(route==='/api/geometry/hole-evidence/'+ID)return {status:'unavailable'};
   throw Error('Unexpected URL '+route);
  }
 });
 vm.runInContext("let jobId='"+ID+"',current={sha256:'"+CAD+"'},latestSummary=null,resultsRequestGeneration=0,gfAgentGeneration=0;"+handlers,ctx);
 return {$,ctx,load:()=>vm.runInContext('loadCurrentResults()',ctx),
  invalidate:()=>vm.runInContext("gfInvalidateAgentFeaEvidence('새 FEA 계산 시작')",ctx),
  state:()=>vm.runInContext('latestSummary?.fea?.state',ctx)};
}
(async()=>{
 let checks=0;
 // The older response for the same CAD must not replace a newer run state.
 {
  const old=deferred();let n=0;
  const x=harness(()=>++n===1?old.promise:summary('queued'));
  const first=x.load();await x.load();
  assert.equal(x.state(),'queued');
  assert.equal(x.$('resultsReportSaveBtn').disabled,true);
  const before=x.$('resultsReportStatus').textContent;
  old.resolve(summary('complete'));await first;
  assert.equal(x.state(),'queued');
  assert.equal(x.$('resultsReportStatus').textContent,before);
  assert.equal(x.$('resultsReportBtn').disabled,true);checks++;
 }
 // FEA start invalidates an in-flight report even when CAD SHA and ID match.
 {
  const old=deferred(),x=harness(()=>old.promise);
  const first=x.load();x.invalidate();
  assert.equal(x.$('resultsReportBtn').disabled,true);
  assert.equal(x.$('resultsReportSaveBtn').disabled,true);
  assert.match(x.$('resultsReportStatus').textContent,/다시 조회/);
  old.resolve(summary('complete'));await first;
  assert.equal(x.state(),undefined);
  assert.match(x.$('resultsOverview').textContent,/이전 FEA 수치/);checks++;
 }
 // The independent B-rep hole probe can also finish after a new result is live.
 {
  const oldProof=deferred();let summaryCount=0,proofCount=0;
  const x=harness(()=>summaryCount++===0?summary('complete'):summary('queued'));
  vm.runInContext(`get=(route=>{
    if(route==='/api/results/summary/'+${JSON.stringify(ID)})return globalThis.getSummary();
    if(route==='/api/geometry/hole-evidence/'+${JSON.stringify(ID)})
      return ++globalThis.proofCount===1?globalThis.pendingProof:{status:'unavailable'};
    throw Error('bad URL');
  })`,x.ctx);
  x.ctx.getSummary=()=>summaryCount++===0?summary('complete'):summary('queued');
  x.ctx.pendingProof=oldProof.promise;x.ctx.proofCount=0;
  const first=x.load();
  for(let i=0;i<8;i++)await Promise.resolve();
  await x.load();assert.equal(x.state(),'queued');
  oldProof.resolve({status:'unavailable'});await first;
  assert.equal(x.state(),'queued');
  assert.equal(x.$('resultsReportBtn').disabled,true);checks++;
 }
 assert.match(src,/function resetModel\(options=\{\}\)\{\+\+resultsRequestGeneration;/,
  'New STEP must cancel pending same-job summary responses');
 console.log('PASS: '+checks+' latest same-STEP FEA summary/ML-probe and report invalidation races');
})().catch(e=>{console.error(e);process.exitCode=1});
