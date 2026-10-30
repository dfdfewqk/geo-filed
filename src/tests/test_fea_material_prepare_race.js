'use strict';
// Browser regression for material selection and async FEA prepare identity.
// Uses the production handler; data here are synthetic contract fixtures,
// not real CAD or CalculiX results.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const base=path.join(__dirname,'..','payload','frontend');
const script=fs.readFileSync(path.join(base,'cad.js'),'utf8');
const html=fs.readFileSync(path.join(base,'index.html'),'utf8');
const JOB='1'.repeat(32),OTHER='2'.repeat(32),SHA='a'.repeat(64),CASE='b'.repeat(64);
function extract(a,b){const i=script.indexOf(a),j=script.indexOf(b,i+a.length);
 assert(i>=0&&j>i,a+' missing');return script.slice(i,j);}
const mark=extract('function gfRefreshMaterialRequirement(){','function refreshEasyMaterial(){');
const handler=extract("$('feaPrepareBtn').onclick=async()=>{","$('feaImportPreviousBtn').onclick=async()=>{");
let passed=0;
function defer(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject};}
function elem(v=''){
 let members=new Set(),attrs={};
 return {value:v,disabled:false,hidden:false,textContent:'',checked:false,
   classList:{toggle(k,on){on?members.add(k):members.delete(k)},contains(k){return members.has(k)}},
   setAttribute(k,v){attrs[k]=v},getAttribute(k){return attrs[k]},
   selectedOptions:[{textContent:'SUS304 · 참고 물성'}],
   focus(){this.focusCount=(this.focusCount||0)+1},
   scrollIntoView(){this.scrollCount=(this.scrollCount||0)+1}};
}
function fixture(material=''){
 const nodes={},promises=[],statuses=[],actions=[];
 const $=id=>nodes[id]||(nodes[id]=elem());
 $('feaMaterialPreset').value=material;
 $('feaOwnWeight').checked=false;
 $('feaElementMode').value='c3d10_full';
 $('feaMeshQuality').value='fine';
 $('feaLoadMode').value='mass_kg';
 $('feaLoadQuantity').value='32';
 $('feaDirectionMode').value='+z';
 $('feaMaterialPreset').selectedOptions=[{textContent:'스테인리스 SUS304'}];
 let posted=0,results=0;
 const state={
  $,
  window:{confirm:()=>true},
  status:(...a)=>statuses.push(a),
  post:()=>{posted++;const x=defer();promises.push(x);return x.promise;},
  get:async()=>({detail:'검증된 과거 결과 없음'}),
  gfInvalidateAgentFeaEvidence:()=>actions.push('agent-invalidated'),
  meshSeriesReset:()=>actions.push('mesh-reset'),
  meshSeriesBusy:false,
  resetFeaField:()=>actions.push('field-reset'),
  loadCurrentResults:async()=>{results++},
  materialPresets:{sus304:{label:'SUS304',e:193000,nu:.29}},
 };
 vm.createContext(state);
 vm.runInContext(
   'let current={sha256:"'+SHA+'"},jobId="'+JOB+'",file={name:"L_bracket.step"},'+
   'stepSelectionVersion=1,feaPrepareGeneration=0,feaPrepared=false,'+
   'feaPreparedCaseSha=null,feaRunId=null,feaReady=true,'+
   'feaFixed=[1],feaLoaded=[3];\n'+mark+handler+'\nthis.materialHint=gfRefreshMaterialRequirement;',state);
 return {state,$,statuses,promises,actions,get posted(){return posted},get results(){return results},
  go:()=>vm.runInContext("$('feaPrepareBtn').onclick()",state),
  cancel:()=>vm.runInContext("++feaPrepareGeneration;feaPrepared=false;feaPreparedCaseSha=null; $('feaPrepareBtn').disabled=false;",state),
  switchCad:()=>vm.runInContext("++feaPrepareGeneration;stepSelectionVersion++;jobId='"+OTHER+"';current={sha256:'"+SHA+"'};feaPrepared=false;feaPreparedCaseSha=null;",state)
 };
}
function success(){return {cad_sha256:SHA,case_sha256:CASE,material:{name:'SUS304',young_modulus_mpa:193000,poisson_ratio:.29},mesh_request:{element_type:'C3D10',traction_model:'straight_tri6_full_consistent',target_element_size_mm:1.7},boundary_conditions:{total_force_n:313.8128}};}
async function tests(){
 assert.match(html,/id="feaMaterialRequiredHint"/);
 assert.match(html,/aria-describedby="feaMaterialRequiredHint"/);
 passed++;
 {
   const x=fixture();
   assert.equal(x.state.materialHint(),false);
   assert.match(x.$('feaMaterialRequiredHint').textContent,/필수.*재료/);
   assert.equal(x.$('feaMaterialPreset').getAttribute('aria-invalid'),'true');
   assert.equal(x.$('feaMaterialPreset').value,'','must not invent a material');
   await x.go();
   assert.equal(x.posted,0,'do not send a calculation case without material');
   assert.equal(x.$('feaMaterialPreset').focusCount,1);
   assert.equal(x.$('feaMaterialPreset').scrollCount,1);
   assert.match(x.$('feaPrepared').textContent,/재료/);
   passed++;
 }
 {
   const x=fixture('sus304');
   assert.equal(x.state.materialHint(),true);
   assert.equal(x.$('feaMaterialPreset').getAttribute('aria-invalid'),'false');
   const task=x.go();
   assert.equal(x.posted,1);
   assert.equal(x.$('feaPrepareBtn').disabled,true);
   x.promises[0].resolve(success()); await task;
   assert.equal(vm.runInContext('feaPrepared',x.state),true);
   assert.equal(vm.runInContext('feaPreparedCaseSha',x.state),CASE);
   assert.equal(x.$('feaRunBtn').disabled,false);
   assert.equal(x.$('feaPrepareBtn').disabled,false);
   assert.match(x.$('feaPrepared').textContent,/조건 저장/);
   passed++;
 }
 {
   const x=fixture('sus304');
   const task=x.go();
   x.cancel(); // User edited kg, direction, material or faces while pending.
   x.$('feaPrepared').textContent='현재 수정된 조건 대기';
   x.promises[0].resolve(success());await task;
   assert.equal(vm.runInContext('feaPrepared',x.state),false);
   assert.equal(vm.runInContext('feaPreparedCaseSha',x.state),null);
   assert.equal(x.$('feaPrepared').textContent,'현재 수정된 조건 대기');
   assert.equal(x.results,0);
   passed++;
 }
 {
   const x=fixture('sus304');
   const task=x.go();
   x.switchCad();
   x.$('feaPrepared').textContent='다른 STEP CAD 선택';
   x.promises[0].reject(Error('old request error')); await task;
   assert.equal(x.$('feaPrepared').textContent,'다른 STEP CAD 선택');
   assert.equal(x.results,0);
   passed++;
 }
 {
   const x=fixture('sus304');
   const old=x.go();x.cancel();
   const fresh=x.go();
   x.promises[1].resolve(success());await fresh;
   x.promises[0].resolve(success());await old;
   assert.equal(vm.runInContext('feaPreparedCaseSha',x.state),CASE);
   assert.equal(x.results,1,'old response must not refresh latest results');
   passed++;
 }
 {
   const x=fixture('sus304');
   vm.runInContext('feaPrepared=true;feaPreparedCaseSha="'+CASE+'";',x.state);
   const task=x.go();
   x.promises[0].reject(Error('FEA 실행 중에는 해석 조건을 수정할 수 없습니다.'));
   await task;
   assert.equal(vm.runInContext('feaPrepared',x.state),true,'calculation-busy 409 must not clear signed case');
   assert.equal(vm.runInContext('feaPreparedCaseSha',x.state),CASE);
   assert.equal(x.actions.includes('field-reset'),false);
   assert.match(x.$('feaPrepared').textContent,/저장된 조건을 유지/);
   passed++;
 }
 {
   const x=fixture('sus304');
   vm.runInContext('feaRunId="RUNNING";',x.state);
   await x.go();
   assert.equal(x.posted,0,'saving during a live solver must never POST');
   assert.match(x.$('feaPrepared').textContent,/진행 상태/);
   passed++;
 }
 {
   const x=fixture('sus304');
   x.state.meshSeriesBusy=true;
   await x.go();
   assert.equal(x.posted,0,'saving during mesh study must never POST');
   passed++;
 }
 assert.match(script,/function invalidateFea\(message\)\{[\s\S]*?\+\+feaPrepareGeneration/);
 assert.match(script,/function resetModel\(options=\{\}\)\{\+\+resultsRequestGeneration;\+\+feaPrepareGeneration/);
 passed++;
 console.log('Material required + actual FEA prepare race tests:',passed,'passed');
}
tests().catch(e=>{console.error(e);process.exitCode=1;});
