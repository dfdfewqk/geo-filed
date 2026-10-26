// Production previous-FEA import callback with delayed synthetic HTTP.
// Never executes CalculiX or changes real STEP/SQLite/FRD data.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const start=source.indexOf("$('feaImportPreviousBtn').onclick=async()=>{");
const end=source.indexOf('// GeoField R18.8',start);
assert(start>=0&&end>start);
const code=source.slice(start,end);
const JOB='1'.repeat(32),RUN='2'.repeat(32),NEXT='3'.repeat(32),SHA='a'.repeat(64),CASE='b'.repeat(64);
const result=()=>({cad_sha256:SHA,case_sha256:CASE,results:{
 maximum_nodal_von_mises_mpa:1.2,maximum_displacement_mm:.003},
 field_visualization:{available:true}});
const status=()=>({id:RUN,cad_job_id:JOB,cad_sha256:SHA,case_sha256:CASE,status:'complete',result:result()});
const defer=()=>{let resolve,reject;const promise=new Promise((ok,no)=>{resolve=ok;reject=no});return {promise,resolve,reject}};
function make({post,get}){
 const elements=new Map(),calls={field:0,reset:0,summary:0};
 const $=id=>{if(!elements.has(id))elements.set(id,{disabled:false,textContent:'',value:''});return elements.get(id);};
 const sandbox={$ ,post,get,status(){},resetFeaField(){calls.reset++},
   setFeaField(){calls.field++},loadCurrentResults:async()=>{calls.summary++}};
 const ctx=vm.createContext(sandbox);
 vm.runInContext("let jobId='"+JOB+"',current={sha256:'"+SHA+"'},"+
   "feaPrepared=true,feaPreparedCaseSha='"+CASE+"',stepSelectionVersion=1,feaRestoreGeneration=0,"+
   "feaRunId=null;"+code,ctx);
 return {ctx,$,calls,start:()=>vm.runInContext("$('feaImportPreviousBtn').onclick()",ctx),
    replace:()=>{vm.runInContext("jobId='"+NEXT+"';current={sha256:'"+SHA+"'};stepSelectionVersion++;feaPrepared=false;feaPreparedCaseSha=null;",ctx);
      $('feaRunStatus').textContent='new CAD';$('feaContourStatus').textContent='new 3D';},
    caseChange:()=>{vm.runInContext("feaPrepared=false;feaPreparedCaseSha='c'.repeat(64);",ctx);$('feaRunStatus').textContent='new case';}};
}
async function main(){
 let checks=0;
 {
  const d=defer(),x=make({post:()=>d.promise,get:async()=>{throw Error('unexpected')}});
  const work=x.start();x.replace();d.resolve({id:RUN});await work;
  assert.equal(x.$('feaRunStatus').textContent,'new CAD');
  assert.equal(x.calls.reset,0);checks++;
 }
 {
  const d=defer(),ready=defer(),x=make({post:async()=>({id:RUN}),get:()=>{ready.resolve();return d.promise}});
  const work=x.start();await ready.promise;
  x.replace();d.resolve(status());await work;
  assert.equal(x.$('feaRunStatus').textContent,'new CAD');assert.equal(x.calls.reset,0);checks++;
 }
 {
  const d=defer(),ready=defer(),x=make({post:async()=>({id:RUN}),get:()=>{ready.resolve();return d.promise}});
  const work=x.start();await ready.promise;
  x.caseChange();d.reject(new Error('old status failed'));await work;
  assert.equal(x.$('feaRunStatus').textContent,'new case');checks++;
 }
 {
  const d=defer(),ready=defer(),x=make({post:async()=>({id:RUN}),get:async url=>url.includes('/status/')?status():(ready.resolve(),d.promise)});
  const work=x.start();await ready.promise;
  x.replace();d.resolve({});await work;
  assert.equal(x.$('feaContourStatus').textContent,'new 3D');assert.equal(x.calls.field,0);checks++;
 }
 {
  const x=make({post:async()=>({id:RUN}),get:async()=>status()});
  await x.start();assert.equal(x.calls.reset,1);assert.equal(x.calls.summary,1);
  assert.equal(vm.runInContext('feaRunId',x.ctx),RUN);checks++;
 }
 for(const key of ['id','cad_job_id','cad_sha256','case_sha256']){
  const t=status();t[key]=['id','cad_job_id'].includes(key)?NEXT:'c'.repeat(64);
  const x=make({post:async()=>({id:RUN}),get:async()=>t});
  await x.start();assert.equal(x.calls.reset,0);assert.equal(x.calls.field,0);checks++;
 }
 const resetStart=source.indexOf('function resetModel(options={}){');
 const resetEnd=source.indexOf('function textKV(',resetStart);
 assert(resetStart>=0&&resetEnd>resetStart,'real model reset handler must exist');
 const reset=source.slice(resetStart,resetEnd);
 assert(reset.includes('if(!options.preserveRestore)++feaRestoreGeneration;r186ClearView();feaArchiveVerified=null;++feaArchiveSelectedGeneration;'),
   'model change must still invalidate archived FEA 3D and selected history');
 assert(reset.includes('gfRestoredRunId=null;++gfAgentGeneration;'),
   'model change must also invalidate stale AI evidence and restore identity');
 assert(source.includes("resetModel({preserveRestore:true})"));
 checks++;
 console.log('PASS: '+checks+' previous FEA re-link and archived viewport reset guards');
}
main().catch(e=>{console.error(e);process.exitCode=1});
