'use strict';
// Exercise the production read-only mesh-study status recovery, not a fake FEA.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const a=src.indexOf('let meshSeriesId=null,meshSeriesPlan=null,meshSeriesBusy=false;');
const b=src.indexOf('function gfLockFeaEditing(locked){',a);
assert(a>=0&&b>a,'real mesh status recheck code must be present');
const impl=src.slice(a,b);
const RUN='1'.repeat(32),JOB='2'.repeat(32),SHA='a'.repeat(64);
const terminal=['complete','failed','cancelled','verification_failed'];
let checks=0;
function create(status='running'){
 const events=[],elements={},state={id:RUN,cad_job_id:JOB,cad_sha256:SHA,status,
 message:'test-local-status',completed:1,total:3},api={};
 const $=id=>(elements[id]??={textContent:'',disabled:false});
 api.$=$;
 api.get=async()=>state;
 api.gfLockFeaEditing=locked=>events.push(locked);
 vm.createContext(api);
 vm.runInContext("let current={sha256:'"+SHA+"'},jobId='"+JOB+"';"+impl+
   "meshSeriesId='"+RUN+"';meshSeriesJobId='"+JOB+"';meshSeriesCadSha='"+SHA+
   "';meshSeriesBusy=true;meshSeriesStatusUnknown=true;",api);
 return {api,state,events,$,again:()=>vm.runInContext('gfRecheckUnknownMeshSeries()',api)};
}
(async()=>{
 for(const t of terminal){
  const x=create(t);await x.again();
  assert.equal(vm.runInContext('meshSeriesBusy',x.api),false);
  assert.equal(vm.runInContext('meshSeriesStatusUnknown',x.api),false);
  assert.deepEqual(x.events,[false]);
  assert.equal(x.$('feaMeshSeriesCancelBtn').disabled,true);
  checks++;
 }
 {
  const x=create('running');await x.again();
  assert.equal(vm.runInContext('meshSeriesBusy',x.api),true);
  assert.equal(vm.runInContext('meshSeriesStatusUnknown',x.api),true);
  assert.equal(x.events.length,0);
  checks++;
 }
 {
  const x=create('complete');x.state.cad_sha256='b'.repeat(64);await x.again();
  assert.equal(vm.runInContext('meshSeriesBusy',x.api),true);
  assert.equal(x.events.length,0);
  assert.match(x.$('feaMeshSeriesProgress').textContent,/식별값/);
  checks++;
 }
 {
  const x=create('complete');x.api.get=async()=>{throw Error('network disconnected')};
  await x.again();
  assert.equal(vm.runInContext('meshSeriesBusy',x.api),true);
  assert.equal(x.events.length,0);
  checks++;
 }
 assert.match(src,/const uncertain=!terminalSeen&&!startRejected/);
 assert.match(src,/meshSeriesBusy=uncertain;/);
 assert.match(src,/meshSeriesStatusUnknown=uncertain;/);
 checks++;
 console.log('Mesh study lost-poll identity / no re-run / terminal unlock:',checks,'passed');
})().catch(e=>{console.error(e);process.exitCode=1});
