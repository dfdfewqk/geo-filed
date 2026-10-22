// Run the production CAD geometry/review event handlers with delayed mock HTTP results.
// Synthetic only: not a STEP extraction or a Windows 3D test.
'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const SHA='a'.repeat(64),JOB='1'.repeat(32),NEW='2'.repeat(32);
function callback(start,end){
 const a=source.indexOf(start),b=source.indexOf(end,a);
 assert(a>=0&&b>a,'production handler missing: '+start);
 return source.slice(a,b);
}
const handlers=callback("$('geometryDimBtn').onclick=async()=>{",'function renderBrepResult(')
              +callback("$('reviewBtn').onclick=async()=>{",'// Simple FEA wizard.');
const node=tag=>({
 tag,children:[],className:'',onclick:null,_textContent:'',
 get textContent(){return this._textContent;},
 set textContent(value){this._textContent=String(value);this.children=[];},
 append(...parts){this.children.push(...parts);}
});
function makeContext(api){
 const elements=new Map(),$=id=>{if(!elements.has(id))elements.set(id,node(id));return elements.get(id);};
 let refreshes=0;
 const sandbox={$,document:{createElement:node},get:api,app:{mesh:{faceIDs:[6,7]},selected:[]},
   refreshSelected:()=>refreshes++,status:()=>{}};
 const ctx=vm.createContext(sandbox);
 vm.runInContext("let jobId='"+JOB+"',current={sha256:'"+SHA+"'},stepSelectionVersion=1;"+handlers,ctx);
 return {ctx,$,selected:()=>sandbox.app.selected,refreshes:()=>refreshes,
   run:name=>vm.runInContext("$('"+name+"').onclick()",ctx),
   switchJob:()=>vm.runInContext("jobId='"+NEW+"';current={sha256:'"+SHA+"'};stepSelectionVersion++",ctx)};
}
const geometry=()=>({cad_sha256:SHA,parts:[{bbox_mm:{x:50,y:30,z:50},volume_mm3:8400,surface_area_mm2:6600}],
 candidates:[{id:'bore-1',diameter_mm:5.5,through_state:'unverified',face_ids:[6],measurements:[]}]});
const review=()=>({cad_sha256:SHA,measured_findings_count:1,items:[{
 where:'face-6',measured_evidence:'CAD cylinder',why:'review',possible_issue:'unverified',
 next_check:'verify',face_ids:[6]}]});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
async function main(){
 let checks=0;
 for(const [button,payload,outId] of [
  ['geometryDimBtn',geometry,'geometryDimResults'],
  ['reviewBtn',review,'integrationReview']
 ]){
  const gate=deferred(),x=makeContext(()=>gate.promise),promise=x.run(button);
  x.switchJob();x.$(outId).textContent='새 CAD 결과를 기다리는 중';
  gate.resolve(payload());await promise;
  assert.equal(x.$(outId).textContent,'새 CAD 결과를 기다리는 중');
  assert.equal(x.$(outId).children.length,0);checks++;
 }
 for(const [button,outId] of [['geometryDimBtn','geometryDimResults'],['reviewBtn','integrationReview']]){
  const gate=deferred(),x=makeContext(()=>gate.promise),promise=x.run(button);
  x.switchJob();x.$(outId).textContent='새 CAD';gate.reject(new Error('obsolete'));
  await promise;assert.equal(x.$(outId).textContent,'새 CAD');checks++;
 }
 for(const [button,payload,outId] of [
  ['geometryDimBtn',geometry,'geometryDimResults'],
  ['reviewBtn',review,'integrationReview']
 ]){
  const x=makeContext(async()=>payload());await x.run(button);
  const choices=x.$(outId).children.filter(c=>c.tag==='button');
  assert.equal(choices.length,1);choices[0].onclick();
  assert.equal(x.selected()[0],6);assert.equal(x.refreshes(),1);
  x.switchJob();choices[0].onclick();
  assert.equal(x.refreshes(),1,'old CAD face click must be inert');checks++;
 }
 for(const [button,payload,outId] of [
  ['geometryDimBtn',()=>({...geometry(),candidates:[{...geometry().candidates[0],face_ids:[999]}]}),'geometryDimResults'],
  ['reviewBtn',()=>({...review(),items:[{...review().items[0],face_ids:[999]}]}),'integrationReview']
 ]){
  const x=makeContext(async()=>payload());await x.run(button);
  const choice=x.$(outId).children.find(c=>c.tag==='button');
  assert.ok(choice);choice.onclick();assert.equal(x.refreshes(),0);checks++;
 }
 console.log('PASS: '+checks+' STEP geometry/review stale-reply and face-selection regressions');
}
main().catch(e=>{console.error(e);process.exitCode=1});
