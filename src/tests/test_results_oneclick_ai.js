'use strict';
// Exercise actual Results navigation + one-click local agent behavior against
// synthetic HTTP responses. Never calls CAD/FEA, models or paid services.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
function extract(a,b){
 const start=source.indexOf(a),end=source.indexOf(b,start);
 assert(start>=0&&end>start,'missing production region: '+a);
 return source.slice(start,end);
}
const nav=extract("const gfPrimaryMenus=['cad','fea','integration','records'];","async function loadFeaPreflight()");
const auto=extract('function gfMaybeAutoAnalyze(){','// Read-only evidence-based agent');
const handler=extract("$('agentRunBtn').onclick=async()=>{","$('reviewBtn').onclick=async()=>{");
const SHA='a'.repeat(64),JOB='b'.repeat(32),RUN='c'.repeat(32),CASE='d'.repeat(64);
function start(){
 const urls=[],calls=[];
 const btn={disabled:false,dataset:{}};
 const nodes={agentRunBtn:btn,agentLLMOptIn:{checked:true},
   agentResult:{textContent:'',append(){}},agentConnection:{textContent:''},
   optionalResearchAndExternal:{open:true},agentOptionalExternal:{open:true},
   sidebar:{scrollTop:4},recordAllAnalysisHistory:{open:false}};
 const panes=['cad','fea','integration','records'].map(name=>({
   dataset:{pane:name},classList:{toggle(){}}
 }));
 const tabs=['cad','fea','integration','records'].map(name=>({
   dataset:{tab:name},classList:{toggle(){}}
 }));
 const ctx={console,Promise,String,Number,Array,Error,
   tabs,document:{querySelectorAll:()=>panes,createElement:()=>({append(){}})},
   $:id=>nodes[id]??={disabled:false,textContent:'',append(){}},
   jobId:JOB,current:{sha256:SHA},stepSelectionVersion:1,
   feaRestoreGeneration:0,gfAgentGeneration:0,gfRestoredRunId:null,
   feaRunId:RUN,feaPreparedCaseSha:CASE,meshSeriesBusy:false,
   gfAiStatusGeneration:0,gfAiStatusVerified:null,gfAiConnectionHint:code=>'status '+code,
   feaArchiveInitialized:true,loadArchive(){},loadFeaArchive(){},
   loadFeaPreflight(){},loadCurrentResults:async()=>{calls.push('summary');return true;},
   draw(){calls.push('draw');},textKV:(k,v)=>({k,v}),
   get:(url,timeout,headers)=>{
    urls.push({url,timeout,headers});
    return Promise.reject(Error('synthetic response blocked (no HTTP sent)'));
   }
 };
 vm.createContext(ctx);
 vm.runInContext("let active='cad';let gfLastAutoAnalysisKey=null;\n"+nav+auto+handler+
   "\nthis.go=tabTo;this.auto=gfMaybeAutoAnalyze;this.select=()=>({active, gfLastAutoAnalysisKey});",ctx);
 return {ctx,btn,nodes,urls,calls};
}
async function flush(){await Promise.resolve();await Promise.resolve();await Promise.resolve();await Promise.resolve();}
(async()=>{
 const t=start();
 t.ctx.go('integration');await flush();
 assert.equal(t.calls[0],'summary');
 assert.equal(t.urls.length,1,'Results navigation must start local agent automatically');
 assert.equal(t.urls[0].url,'/api/agent/evidence/'+JOB);
 assert.equal(t.urls[0].headers,undefined,'Auto request must NOT transmit paid API opt-in');
 assert.equal(t.nodes.agentLLMOptIn.checked,true,'Auto request must preserve unused explicit consent');
 assert.equal(t.btn.dataset.gfAutoLocalOnly,undefined,'One-shot internal flag cleaned up');
 t.ctx.go('integration');await flush();
 assert.equal(t.urls.length,1,'Repeated navigation must not duplicate a CAD/FEA analysis');
 t.ctx.feaRunId='e'.repeat(32);
 t.ctx.go('integration');await flush();
 assert.equal(t.urls.length,2,'A different actual FEA run must be analyzed again');
 t.ctx.feaRunId='RUNNING';
 t.ctx.go('integration');await flush();
 assert.equal(t.urls.length,2,'Never auto-analyze a running FEA');
 t.ctx.feaRunId=RUN;
 t.nodes.agentLLMOptIn.checked=true;
 await t.btn.onclick();
 assert.equal(t.urls.at(-1).url,'/api/agent/evidence/'+JOB+'?llm=1',
   'Only a direct, explicitly consented click can request external explanation');
 assert.equal(t.urls.at(-1).headers['X-GeoField-LLM-Opt-In'],'1');
 assert.equal(t.nodes.agentLLMOptIn.checked,false,'Manual consent must reset after use');
 console.log('PASS: tab-to-local-AI once, FEA rerun, no auto-LLM, manual explicit opt-in');
})().catch(e=>{console.error(e);process.exitCode=1;});
