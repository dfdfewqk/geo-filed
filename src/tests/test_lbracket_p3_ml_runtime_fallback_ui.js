// P3: actual auto BrepMFR watcher shows worker failure before existing R12 fallback.
// Synthetic backend statuses only; no STEP, installed model, real network or FEA.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),
      vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const a=source.indexOf('async function watchAutoMl(');
const b=source.indexOf('async function watchAutoR12(',a+1);
assert(a>=0&&b>a,'Automatic production ML watcher unavailable');
const snippet=source.slice(a,b);
const CAD='1'.repeat(32),SHA='a'.repeat(64),RID='2'.repeat(32);
async function run(status,message,{switchCAD=false}={}){
 const results={textContent:''},called=[];
 const scope=vm.createContext({
   jobId:CAD,current:{sha256:SHA},autoMlGeneration:7,
   $:id=>{assert.equal(id,'brepMlResults');return results;},
   get:async url=>{
     assert.equal(url,'/api/ml/latest/'+CAD);
     called.push('get');
     if(switchCAD)scope.current={sha256:'b'.repeat(64)};
     return {id:RID,cad_job_id:CAD,cad_sha256:SHA,status,message,
             automatic:true};
   },
   watchAutoR12:(...args)=>called.push(['r12',...args]),
   sleep:async()=>{throw Error('Unexpected poll after terminal fallback state')},
   loadCurrentResults:async()=>called.push('summary'),
   gfAutoResearchDisplay:()=>{}, // production-global status formatter is outside extracted watcher
 });
 vm.runInContext(snippet,scope);
 await scope.watchAutoMl(CAD,SHA,7,true);
 return {label:results.textContent,called};
}
(async()=>{
 const fallback=await run('r12_fallback','BrepMFR 실행 실패: 실제 모델 파일 불러오기 불가');
 assert.match(fallback.label,/BrepMFR 실행 실패/);
 assert.match(fallback.label,/R12 연구용 분류 확인/);
 assert.deepEqual(fallback.called,['get',['r12',CAD,SHA,7]]);
 const failed=await run('failed','BrepMFR failed; automatic fallback failed');
 assert.match(failed.label,/BrepMFR failed/);
 assert.equal(failed.called.includes('summary'),true);
 assert.equal(failed.called.some(x=>Array.isArray(x)&&x[0]==='r12'),false);
 const changed=await run('r12_fallback','BrepMFR failed',{switchCAD:true});
 assert.equal(changed.label,'BrepMFR 자동 실행 준비 중 (실험적 분석 · 안전 판단에 사용 안 함)');
 assert.deepEqual(changed.called,['get']);
 console.log('P3 L-bracket runtime worker failure to R12 UI and stale SHA suppression PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
