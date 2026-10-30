'use strict';
// Regression of the actual visible Results/AI 3D policy. Synthetic, no GPU or paid API.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../payload/frontend/index.html'),'utf8');
const start=src.indexOf(' const fieldActive=('),end=src.indexOf(';',start);
assert(start>0&&end>start,'WebGL result field policy absent');
const expr=src.slice(start,end+1);
const SHA='a'.repeat(64);
function visible(active,field,mode='stress'){
 const ctx={active,feaField:field,feaContourMode:mode,current:{sha256:SHA}};
 vm.runInNewContext(expr+' this.visible=Boolean(fieldActive);',ctx);
 return ctx.visible;
}
const bound={cadSha:SHA};
assert.equal(visible('fea',bound),true);
assert.equal(visible('integration',bound),true);
assert.equal(visible('cad',bound),false);
assert.equal(visible('records',bound),false);
assert.equal(visible('integration',null),false);
assert.equal(visible('integration',bound,'none'),false);
assert.equal(visible('integration',{cadSha:'b'.repeat(64)}),false);
const paint=src.slice(src.indexOf('function paintFeaField('),src.indexOf('\n}',src.indexOf('function paintFeaField(')));
assert(paint.includes("!['fea','integration'].includes(active)"));
assert(paint.includes('feaField.cadSha!==current?.sha256'));
const ai=src.slice(src.indexOf("$('agentRunBtn').onclick=async()=>{"),src.indexOf("$('reviewBtn').onclick=async()=>{"));
assert(ai.includes('const externalOptIn=!automaticLocal&&'));
assert(ai.includes("$('agentOptionalExternal')?.open===true&&$('agentLLMOptIn')?.checked===true"));
const external=html.indexOf('id="agentOptionalExternal"');
const button=html.indexOf('id="agentRunBtn"');
const research=html.indexOf('id="optionalResearchAndExternal"');
assert(external>0&&button>external&&research>button,'External consent should be next to the real button');
const statusCode=src.slice(src.indexOf('function gfRefreshAiProviderStatus(){'),src.indexOf('// One automatic local analysis'));
assert(statusCode.includes("get('/api/integration/preflight')"));
const calls=[],target={textContent:''};
const sandbox={$:id=>id==='agentExternalStatus'?target:null,
 get:async url=>{calls.push(url);return {agent:{llm_config:{configured:false,configured_provider:'deepseek'}}};}};
vm.runInNewContext(statusCode+' this.run=gfRefreshAiProviderStatus;',sandbox);
(async()=>{
 sandbox.run();await Promise.resolve();await Promise.resolve();
 assert.deepEqual(calls,['/api/integration/preflight']);
 assert.match(target.textContent,/설정 미완료/);
 console.log('PASS: verified FRD stress on Results, old/unverified suppression, paid opt-in boundary, preflight status');
})().catch(err=>{console.error(err);process.exitCode=1});
