'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const src=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
function extract(a,b){const i=src.indexOf(a),j=src.indexOf(b,i+a.length);assert(i>=0&&j>i,'missing real callback: '+a);return src.slice(i,j);}
const onchange=extract("$('stepFile').onchange=e=>{","// R17.3: Network errors");
const importer=extract("$('importBtn').onclick=async()=>{","\nfunction resetModel(");
const lock=extract("function gfLockFeaEditing(locked){","function gfMeshSensitivityLabel(");
const preflight=extract("async function loadFeaPreflight(){","tabs.forEach(b=>b.addEventListener");
const fake=()=>({disabled:false,value:'',textContent:'',checked:false,classList:{add(){},remove(){}},setAttribute(){}});
let checks=0;
function make(){
 const els=new Map(),events=[];
 const $=name=>{if(!els.has(name))els.set(name,fake());return els.get(name);};
 const scope={$,
  get:async()=>({enabled:true,gmsh_python_detected:true,calculix_executable_detected:true}),
  status:(...msg)=>events.push(msg),resetModel:()=>{throw Error('must not reset active solver')},
  console};
 vm.createContext(scope);
 vm.runInContext('let feaRunId="RUNNING",meshSeriesBusy=false,current={sha256:"a"},'+
  'jobId="1",file={name:"original.step"},stepSelectionVersion=3,feaRestoreGeneration=2,'+
  'cadImportGeneration=4,feaReady=true,feaPrepared=true,meshSeriesPlan={base_case_sha256:"b"};'+
  'const app={mesh:{}};\n'+onchange+importer+lock+preflight,scope);
 return {scope,$,events};
}
(async()=>{
 const x=make(),changed={target:{value:'C:\\fakepath\\different.step',files:[{name:'different.step'}]}};
 vm.runInContext("$('stepFile').onchange",x.scope)(changed);
 assert.equal(changed.target.value,'');
 assert.equal(vm.runInContext('file.name',x.scope),'original.step');
 assert.equal(vm.runInContext('stepSelectionVersion',x.scope),3);
 assert.match(x.events.at(-1)[0],/FEA 계산 중/);
 checks++;
 await vm.runInContext("$('importBtn').onclick()",x.scope);
 assert.equal(vm.runInContext('jobId',x.scope),'1');
 checks++;
 vm.runInContext('gfLockFeaEditing(true)',x.scope);
 for(const id of ['stepFile','importBtn','feaMaterialPreset','feaRunBtn','feaPrepareBtn','feaMeshSeriesStartBtn']){
  assert.equal(x.$(id).disabled,true,'must lock '+id);
 }
 checks++;
 await vm.runInContext('loadFeaPreflight()',x.scope);
 assert.equal(x.$('feaRunBtn').disabled,true,'preflight must not unlock live solver');
 assert.equal(x.$('feaImportPreviousBtn').disabled,true);
 checks++;
 vm.runInContext('feaRunId=null;gfLockFeaEditing(false)',x.scope);
 assert.equal(x.$('stepFile').disabled,false);
 assert.equal(x.$('importBtn').disabled,false);
 assert.equal(x.$('feaRunBtn').disabled,false);
 checks++;
 // The same guard applies for mesh study, not only single FEA.
 vm.runInContext('meshSeriesBusy=true',x.scope);
 changed.target.value='another.step';
 vm.runInContext("$('stepFile').onchange",x.scope)(changed);
 assert.equal(changed.target.value,'');
 assert.equal(vm.runInContext('stepSelectionVersion',x.scope),3);
 checks++;
 console.log('FEA active solver + STEP switch + preflight controls:',checks,'passed');
})().catch(err=>{console.error(err);process.exitCode=1});
