// Exercise the ACTUAL GeoField web AI-agent handler with delayed synthetic HTTP.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const start=src.indexOf("$('agentRunBtn').onclick=async()=>{");
const end=src.indexOf("$('reviewBtn').onclick=async()=>{",start);
assert(start>=0&&end>start,'real production AI-agent handler missing');
const handler=src.slice(start,end);
const SHA='a'.repeat(64),JOB='1'.repeat(32),RUN='2'.repeat(32),CASE='b'.repeat(64);
const defer=()=>{let yes,no;const promise=new Promise((a,b)=>{yes=a;no=b});return {promise,resolve:yes,reject:no}};
const valid=()=>({schema:'geofield-evidence-agent-v1',cad_sha256:SHA,mode:'rules_only',
 llm:{connected:false,executed:false,provider:null},
 ml:{status:'research_unverified'},
 fea:{status:'INP_STA_FRD_reverified',run_id:RUN,case_sha256:CASE,
      maximum_von_mises_mpa:14.5,maximum_displacement_mm:0.057,
      element_type:'C3D4',safety_certified:false,convergence:'not_independently_verified'},
 findings:[{title:'원통형 홀 후보',evidence:'실측 내경',next_check:'실제 응력 교차 확인'}]});
function harness(){
 const nodes={agentRunBtn:{disabled:false},agentResult:{textContent:'',items:[],append(...args){this.items.push(...args)}}};
 const pending=[];
 const ctx={Error,String,Number,Array,Promise,
  $:n=>nodes[n]??={disabled:false,textContent:'',items:[],append(...args){this.items.push(...args)}},
  jobId:JOB,current:{sha256:SHA},stepSelectionVersion:5,feaRestoreGeneration:1,gfAgentGeneration:0,
  get:url=>{const v=defer();pending.push({url,...v});return v.promise;},
  textKV:(title,value)=>({title,value}),
  document:{createElement:tag=>({tag,children:[],textContent:'',append(...x){this.children.push(...x)}})}
 };
 vm.createContext(ctx);vm.runInContext(handler,ctx);
 return {ctx,nodes,pending,changeCad:()=>vm.runInContext("jobId='3'.repeat(32);current={sha256:'c'.repeat(64)};stepSelectionVersion++;gfAgentGeneration++;",ctx)};
}
let count=0;
async function checkSuccessful(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 assert.equal(t.pending.length,1);assert.equal(t.pending[0].url,'/api/agent/evidence/'+JOB);
 t.pending[0].resolve(valid());await work;
 assert.equal(t.nodes.agentRunBtn.disabled,false);
 assert(t.nodes.agentResult.items.some(x=>x.title==='최대 응력 / 변위'));
 assert(t.nodes.agentResult.items.some(x=>x.title==='연결 상태'));
 assert(t.nodes.agentResult.items.some(x=>x.title==='메시 수렴'));
 count++;
}
async function checkNoFea(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.fea={status:'not_verified',safety_certified:false};
 t.pending[0].resolve(data);await work;
 assert(t.nodes.agentResult.items.some(x=>x.title==='실제 FEA'));
 assert(!t.nodes.agentResult.items.some(x=>x.title==='최대 응력 / 변위'));
 count++;
}
async function checkStale(throws=false){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 t.changeCad();t.nodes.agentResult.textContent='new STEP must stay';
 if(throws)t.pending[0].reject(Error('stale prior FEA error'));
 else t.pending[0].resolve(valid());
 await work;
 assert.equal(t.nodes.agentResult.textContent,'new STEP must stay');
 assert.equal(t.nodes.agentResult.items.length,0);
 count++;
}
async function checkRestoreRace(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 vm.runInContext('feaRestoreGeneration++;gfAgentGeneration++',t.ctx);
 t.nodes.agentResult.textContent='restored result in progress';
 t.pending[0].resolve(valid());await work;
 assert.equal(t.nodes.agentResult.textContent,'restored result in progress');
 count++;
}
async function checkUnverifiedLLM(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.llm.connected=true;
 t.pending[0].resolve(data);await work;
 assert.match(t.nodes.agentResult.textContent,/연결|계약/);
 assert.equal(t.nodes.agentResult.items.length,0);
 count++;
}
async function checkBadCad(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.cad_sha256='f'.repeat(64);
 t.pending[0].resolve(data);await work;
 assert.match(t.nodes.agentResult.textContent,/식별|계약|원본/);
 count++;
}
async function checkNoFakeNumber(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.fea.maximum_von_mises_mpa=NaN;
 t.pending[0].resolve(data);await work;
 assert.match(t.nodes.agentResult.textContent,/실행·수치/);
 count++;
}
async function checkApiFailure(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 t.pending[0].reject(Error('offline engine'));
 await work;assert.match(t.nodes.agentResult.textContent,/offline engine/);
 assert.equal(t.nodes.agentRunBtn.disabled,false);count++;
}
(async()=>{await checkSuccessful();await checkNoFea();await checkStale();await checkStale(true);
 await checkRestoreRace();await checkUnverifiedLLM();await checkBadCad();
 await checkNoFakeNumber();await checkApiFailure();
 assert(src.includes("++gfAgentGeneration;if($('agentRunBtn'))$('agentRunBtn').disabled=true"),
        'Reset must invalidate pending agent result and button');
 assert(src.includes("$('agentRunBtn').disabled=false"),'CAD import/restore must re-enable agent');
 count++;
 console.log('PASS: '+count+' real GeoField AI-agent UI and stale-evidence tests');
})().catch(e=>{console.error(e);process.exitCode=1});
