// Regression for the real FEA controls in the Windows recording on 2026-10-27.
// No simulated solver success; only client-side guards and visual guidance.
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..','payload','frontend');
const src=fs.readFileSync(path.join(root,'cad.js'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
let count=0;
function extract(start,end){
 const a=src.indexOf(start),b=src.indexOf(end,a+start.length);
 assert(a>=0&&b>a,'Missing production section: '+start);
 return src.slice(a,b);
}
const hint=extract('function gfRefreshExternalLoadHint(){','function refreshEasyLoad(){');
const prepare=extract("$('feaPrepareBtn').onclick=async()=>{","$('feaImportPreviousBtn').onclick=async()=>{");
assert.match(html,/id="feaLoadInputHint"/);
assert.match(html,/aria-describedby="feaLoadInputHint"/);
count++;
function makeElement(value=''){
 const state=new Set(),attributes={};
 return {value,disabled:false,hidden:false,textContent:'',firstChild:{textContent:''},
  classList:{toggle(name,present){present?state.add(name):state.delete(name)},
             contains(name){return state.has(name)}},
  setAttribute(k,v){attributes[k]=v},getAttribute(k){return attributes[k]},
  focus(){this.focusCalls=(this.focusCalls||0)+1},
  scrollIntoView(){this.scrollCalls=(this.scrollCalls||0)+1}
 };
}
function setup(){
 const elements={
  feaLoadMode:makeElement('mass_kg'),
  feaLoadQuantity:makeElement(''),
  feaLoadInputHint:makeElement(''),
  feaMaterialPreset:makeElement('sus304'),
  feaOwnWeight:Object.assign(makeElement(),{checked:false}),
  feaElementMode:makeElement('c3d10_full'),
  feaDirectionMode:makeElement('+x'),
  feaMeshQuality:makeElement('fine'),
 };
 let posted=0;
 const statuses=[];
 const $=id=>elements[id]??(elements[id]=makeElement());
 const context={$,
  window:{confirm:()=>true},
  status:(...args)=>statuses.push(args),
  meshSeriesBusy:false,feaRunId:null,
  post:async()=>{posted++;throw Error('Mocked POST not permitted')},
  gfInvalidateAgentFeaEvidence(){},
 };
 vm.createContext(context);
 vm.runInContext('let current={sha256:"a".repeat(64)},jobId="1".repeat(32),feaFixed=[3],feaLoaded=[1];\n'
      +hint+prepare+'\nthis.show=gfRefreshExternalLoadHint;',context);
 return {context,elements,$,statuses,get posted(){return posted}};
}
async function main(){
 const fixture=setup();
 assert.equal(fixture.context.show(),false);
 assert.match(fixture.$('feaLoadInputHint').textContent,/필수 입력.*질량/);
 assert.equal(fixture.$('feaLoadQuantity').getAttribute('aria-invalid'),'true');
 assert(fixture.$('feaLoadQuantity').classList.contains('gf-load-required'));
 assert.equal(fixture.$('feaLoadQuantity').value,'','must not auto-invent external mass');
 count++;
 await fixture.$('feaPrepareBtn').onclick();
 assert.equal(fixture.posted,0,'blank real-world load must never be posted');
 assert.match(fixture.$('feaPrepared').textContent,/하중·방향/);
 assert.equal(fixture.$('feaLoadQuantity').focusCalls,1);
 assert.equal(fixture.$('feaLoadQuantity').scrollCalls,1);
 count++;
 fixture.$('feaLoadQuantity').value='5';
 assert.equal(fixture.context.show(),true);
 assert.match(fixture.$('feaLoadInputHint').textContent,/49\.033/);
 assert.equal(fixture.$('feaLoadQuantity').getAttribute('aria-invalid'),'false');
 assert(!fixture.$('feaLoadQuantity').classList.contains('gf-load-required'));
 count++;
 fixture.$('feaLoadMode').value='force_n';
 fixture.$('feaLoadQuantity').value='';
 assert.equal(fixture.context.show(),false);
 assert.match(fixture.$('feaLoadInputHint').textContent,/필수 입력.*외력/);
 count++;
 fixture.$('feaLoadQuantity').value='100';
 assert.equal(fixture.context.show(),true);
 assert.match(fixture.$('feaLoadInputHint').textContent,/100 N/);
 count++;
 fixture.$('feaLoadMode').value='example_100n';
 fixture.$('feaLoadQuantity').value='';
 assert.equal(fixture.context.show(),true);
 assert.match(fixture.$('feaLoadInputHint').textContent,/시연용/);
 count++;
 assert.match(src,/Switching kg to N[\s\S]{0,210}feaLoadQuantity'\)\.value=''/);
 count++;
 console.log('FEA real-load input / focus regression: '+count+' passed');
}
main().catch(e=>{console.error(e);process.exitCode=1});
