'use strict';
// Exercise the production one-click FEA handler with synthetic inputs only.
// No actual CAD/solver, SQLite mutation or external (paid) model request.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const start=source.indexOf('let gfOneClickPreparing=false;');
const end=source.indexOf('// GeoField R18.4 independently verified numerical FEA history view',start);
assert(start>0&&end>start);
const handler=source.slice(start,end);
const sha='a'.repeat(64),caseSha='b'.repeat(64),job='1'.repeat(32),run='2'.repeat(32);
function make({prepareSucceeds=true,ready=true,readyAfterSummaries=null,alreadyPrepared=false,changeSelection=false}={}) {
 const nodes=Object.create(null),actions=[],requests=[];
 const $=id=>(nodes[id]??={textContent:'',disabled:false});
 const ctx={
  Math,Number,String,Error,Promise,current:{sha256:sha},jobId:job,file:{name:'synthetic.step'},
  feaReady:true,feaPrepared:alreadyPrepared,feaPreparedCaseSha:alreadyPrepared?caseSha:null,
  feaRunId:null,feaRestoreGeneration:0,stepSelectionVersion:1,meshSeriesBusy:false,
  active:'fea',latestSummary:{verified:true},$,
  status:(...v)=>actions.push(['status',...v]),
  gfInvalidateAgentFeaEvidence:()=>actions.push(['invalidate']),
  resetFeaField:()=>{},gfLockFeaEditing:v=>actions.push(['lock',v]),
  gfSetFeaStage:(...v)=>actions.push(['stage',...v]),
  gfFeaTableShow:()=>actions.push(['table']),gfLoadAuditSummary:()=>({shifted:false}),
  gfReportReady:()=>ready||(readyAfterSummaries!==null&&actions.filter(a=>a[0]==='summary').length>=readyAfterSummaries),
  loadCurrentResults:async()=>actions.push(['summary']),
  gfAutoStage2Verification:async()=>actions.push(['autoMesh']),
  gfStage3CompleteReport:async()=>actions.push(['autoReport']),
  gfStage4CompareWithPast:async()=>actions.push(['autoCompare']),
  tabTo:t=>actions.push(['tab',t]),sleep:async()=>{},
  fetch:async(url,opt)=>{requests.push([url,opt]);return{ok:true,json:async()=>({id:run,cad_sha256:sha})}},
  get:async url=>{
   if(url!=='/api/fea/status/'+run)throw Error('Unexpected GET '+url);
   return{id:run,cad_job_id:job,cad_sha256:sha,case_sha256:caseSha,status:'complete',
    result:{cad_sha256:sha,case_sha256:caseSha,
     results:{maximum_nodal_von_mises_mpa:12.3,maximum_displacement_mm:.03},
     mesh:{tetrahedron_count:100,node_count:80},field_visualization:{available:false}}};
  }
 };
 vm.createContext(ctx);vm.runInContext(handler,ctx);
 $('feaPrepareBtn').onclick=async()=>{
  actions.push(['prepare']);
  if(changeSelection){ctx.stepSelectionVersion++;return false;}
  if(!prepareSucceeds)return false;
  ctx.feaPrepared=true;ctx.feaPreparedCaseSha=caseSha;
  return true;
 };
 return{ctx,actions,requests};
}
(async()=>{
 {const t=make({prepareSucceeds:false});await t.ctx.$('feaRunBtn').onclick();
  assert.equal(t.requests.length,0);assert.deepEqual(t.actions.map(x=>x[0]),['prepare']);}
 {const t=make();await t.ctx.$('feaRunBtn').onclick();
  assert.equal(t.requests.length,1);
  assert.equal(t.requests[0][0],'/api/fea/run/'+job);
  assert.equal(t.actions.filter(a=>a[0]==='tab').length,1);
  assert.equal(t.actions.find(a=>a[0]==='tab')[1],'integration');
  assert.equal(t.actions.filter(a=>a[0]==='autoMesh').length,1);
  assert.equal(t.actions.filter(a=>a[0]==='autoReport').length,1);
  assert.equal(t.actions.filter(a=>a[0]==='autoCompare').length,1);}
 {const t=make({alreadyPrepared:true});await t.ctx.$('feaRunBtn').onclick();
  assert.equal(t.requests.length,1);
  assert.equal(t.actions.filter(a=>a[0]==='prepare').length,0);}
 {const t=make({ready:false,readyAfterSummaries:3});await t.ctx.$('feaRunBtn').onclick();
  assert.equal(t.requests.length,1,'delayed SQLite/INP summary must never duplicate solver');
  assert.equal(t.actions.filter(a=>a[0]==='summary').length,4,
   'three readiness reads plus terminal finally refresh');
  assert.equal(t.actions.filter(a=>a[0]==='autoMesh').length,1);
  assert.equal(t.actions.filter(a=>a[0]==='autoReport').length,1);}
 {const t=make({ready:false});await t.ctx.$('feaRunBtn').onclick();
  assert.equal(t.requests.length,1);
  assert.equal(t.actions.filter(a=>a[0]==='summary').length,10,
   'bounded summary retry only: first read, eight rechecks and final refresh');
  assert.equal(t.actions.filter(a=>a[0]==='tab').length,0);
  assert.equal(t.actions.filter(a=>a[0]==='autoMesh').length,0);}
 {const t=make({changeSelection:true});await t.ctx.$('feaRunBtn').onclick();
  assert.equal(t.requests.length,0);}
 console.log('PASS: one-click FEA prepares first, blocks invalid run, shows only independently verified results');
})().catch(e=>{console.error(e);process.exitCode=1});
