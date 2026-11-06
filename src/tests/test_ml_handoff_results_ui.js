// Exercise the real Stage 2 Results handoff block, isolated from WebGL.
// No mocked ML success replaces a real model inference or a production run.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const start=source.indexOf('  // Reuse the Stage 2 current-STEP research handoff in Results, without');
const end=source.indexOf("  const notice=document.createElement('div');notice.className='notice warn';",start);
assert(start>=0 && end>start,'production Results ML handoff block exists');
const block=source.slice(start,end);
const render=new Function('get','expectedId','expectedSha','stillLatest','target','textKV',block);
const UID='a'.repeat(32),SHA='b'.repeat(64);
const proof=()=>({schema:'geofield-ml-handoff-v1',cad_job_id:UID,cad_sha256:SHA,
 research_only:true,structural_authority:false,face_mapping_verified:false,
 fea_calculated:false,resolved:[{model:'brepmfr'}],
 uncertain:[{model:'brepmfr'}],failed:[{model:'r12',status:'failed'}],
 unavailable:[],pending:[]});

async function scenario(data, {fresh=true,error=null}={}) {
 const rows=[], calls=[];
 const get=(url,timeout)=>{
  calls.push({url,timeout});
  return error?Promise.reject(error):Promise.resolve(data);
 };
 render(get,UID,SHA,()=>fresh,{append:x=>rows.push(x)},(key,value)=>({key,value}));
 await new Promise(resolve=>setImmediate(resolve));
 return {rows,calls};
}
(async()=>{
 const good=await scenario(proof());
 assert.deepEqual(good.calls,[{url:'/api/ml/handoff/'+UID,timeout:12000}]);
 assert.equal(good.rows.length,1);
 assert.match(good.rows[0].value,/연구 실행 검증 1개/);
 assert.match(good.rows[0].value,/미확정 연구 모델 1종/);
 assert.match(good.rows[0].value,/실패 r12: failed/);
 assert.match(good.rows[0].value,/CAD 형상 정답·면 대응·구조 안전 판정 아님/);

 for(const mutate of [
  x=>x.cad_sha256='c'.repeat(64),
  x=>x.cad_job_id='d'.repeat(32),
  x=>x.research_only=false,
  x=>x.structural_authority=true,
  x=>x.face_mapping_verified=true,
  x=>x.fea_calculated=true,
  x=>delete x.failed
 ]) {
  const bad=proof();mutate(bad);
  const out=await scenario(bad);
  assert.equal(out.rows.length,1);
  assert.match(out.rows[0].value,/인계 자료의 현재 STEP\/연구 출처 계약 불일치/);
  assert.doesNotMatch(out.rows[0].value,/연구 실행 검증 1개/);
 }
 const stale=await scenario(proof(),{fresh:false});
 assert.equal(stale.rows.length,0,'old CAD response never gets attached to a changed selection');
 const failed=await scenario(proof(),{error:Error('HTTP 409')});
 assert.equal(failed.rows.length,1);
 assert.match(failed.rows[0].value,/HTTP 409/);
 assert.match(failed.rows[0].value,/CAD\/FEA 결과는 유지/);
 assert(!block.includes('llm=1')&&!block.includes('X-GeoField-LLM-Opt-In')&&
        !block.includes('/api/fea/run/')&&!block.includes('fetch('));
 console.log('PASS: live Results ML handoff, stale/forged proof rejected, failed fetch isolated, no paid/FEA calls');
})().catch(e=>{console.error(e);process.exitCode=1;});
