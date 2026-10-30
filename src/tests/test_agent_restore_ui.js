// Exercise actual post-restore auto-agent invocation without a solver or browser.
// No real Windows, SQLite, third-party LLM API or user files are involved.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),
      vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const start=src.indexOf('      // Restore never auto-opts into any external paid API.');
const end=src.indexOf("      status(fieldRestored?'FEA 수치",start);
assert(start>=0&&end>start,'Production restore-to-agent callback not found');
const code=src.slice(start,end);
const handler=src.slice(src.indexOf('async function restoreArchivedFea('),src.indexOf('let feaArchiveItems='));
const agent=src.slice(src.indexOf("$('agentRunBtn').onclick=async()=>{"),src.indexOf("$('reviewBtn').onclick=async()=>{"));
assert(handler.includes('resetModel({preserveRestore:true})'));
assert(handler.includes('gfRestoredRunId=recovered.run_id'));
assert(src.includes('gfRestoredRunId=null;++gfAgentGeneration'));
assert(agent.includes("const externalOptIn=!automaticLocal&&"));
assert(!agent.includes("$('optionalResearchAndExternal')?.open===true"), 'Only the visible per-request paid opt-in disclosure is required');
assert(agent.includes("$('agentOptionalExternal')?.open===true&&$('agentLLMOptIn')?.checked===true"));
assert(agent.includes("if(!automaticLocal&&$('agentLLMOptIn'))$('agentLLMOptIn').checked=false"));
assert(agent.includes("gfRestoredRunId===restoredRunAtRequest"));
let count=0;
function fire({sessionMatches=true,runMatches=true,buttonExists=true}={}){
 let sent=0;
 const button={dataset:{},onclick:()=>{assert.equal(button.dataset.gfAutoLocalOnly,'1','restored auto-analysis must be local');sent++;return Promise.resolve()}};
 const scope={
  recovered:{run_id:'1'.repeat(32)},gfRestoredRunId:runMatches?'1'.repeat(32):'2'.repeat(32),
  requireSameSelection:()=>{if(!sessionMatches)throw Error('stale selection')},
  $:()=>buttonExists?button:null
 };
 vm.createContext(scope);
 const execute=()=>vm.runInContext('(function(){'+code+'})()',scope);
 return {execute,wasCalled:()=>sent};
}
{
 const t=fire();t.execute();assert.equal(t.wasCalled(),1);count++;
}
{
 const t=fire({runMatches:false});t.execute();assert.equal(t.wasCalled(),0);count++;
}
{
 const t=fire({sessionMatches:false});
 assert.throws(t.execute,/stale selection/);assert.equal(t.wasCalled(),0);count++;
}
{
 const t=fire({buttonExists:false});t.execute();assert.equal(t.wasCalled(),0);count++;
}
console.log('PASS: '+count+' real restore-to-agent auto-refresh and no-stale-call checks');
