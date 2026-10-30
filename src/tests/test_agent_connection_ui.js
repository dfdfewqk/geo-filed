'use strict';
// Exercise production error explanations and status preservation with mock GET.
// No real external API calls, keys or engineering data.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const raw=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const a=raw.indexOf('function gfAiStatusMatches(state){');
const b=raw.indexOf('// One automatic local analysis per CAD/FEA selection.',a);
assert(a>0&&b>a,'real production AI status helpers must exist');
const section=raw.slice(a,b);
const calls=[],status={textContent:''};
const CAD='a'.repeat(64),JOB='b'.repeat(32),RUN='c'.repeat(32),CASE='d'.repeat(64);
const ctx={
 jobId:JOB,current:{sha256:CAD},feaRunId:RUN,feaPreparedCaseSha:CASE,
 gfAiStatusVerified:null,gfAiStatusGeneration:0,
 $:id=>id==='agentExternalStatus'?status:null,
 get:async endpoint=>{calls.push(endpoint);return {
  agent:{llm_config:{configured:true,configured_provider:'deepseek',
                     selected_model:'deepseek-flash',setup_status:'ready_not_tested'}}};}
};
vm.createContext(ctx);
vm.runInContext(section+'this.check=gfAiStatusMatches;this.reason=gfAiConnectionHint;this.load=gfRefreshAiProviderStatus;',ctx);
assert.match(ctx.reason('authentication_failed'),/401/);
assert.match(ctx.reason('insufficient_balance'),/402/);
assert.match(ctx.reason('rate_limited'),/429/);
assert.match(ctx.reason('timeout'),/시간 초과/);
assert.match(ctx.reason('network_unavailable'),/접속 불가/);
(async()=>{
 ctx.load();
 await Promise.resolve();await Promise.resolve();
 assert.equal(calls[0],'/api/integration/preflight');
 assert.match(status.textContent,/설정 감지됨/);
 assert.match(status.textContent,/실제 응답 미검증/);
 ctx.gfAiStatusVerified={jobId:JOB,cadSha:CAD,runId:RUN,caseSha:CASE,text:'DeepSeek API 실제 응답 성공'};
 ctx.load();
 assert.equal(calls.length,1,'Successful prior reply does not request a fresh preflight');
 assert.equal(status.textContent,'DeepSeek API 실제 응답 성공');
 ctx.feaRunId='e'.repeat(32);
 assert.equal(ctx.check(ctx.gfAiStatusVerified),false,'Old FEA success cannot be shown for new run');
 ctx.load();await Promise.resolve();await Promise.resolve();
 assert.equal(calls.length,2);
 assert.match(status.textContent,/미검증/);
 console.log('PASS: actual API vs configured status, safe diagnostics, per-run identity');
})().catch(e=>{console.error(e);process.exitCode=1;});
