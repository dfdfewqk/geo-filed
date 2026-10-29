// Real production watcher extracted from cad.js; no browser, model or network.
// The active L-bracket must not poll forever after backend rejects stale ML.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const file=path.join(__dirname,'..','payload','frontend','cad.js');
const raw=fs.readFileSync(file,'utf8');
const from=raw.indexOf('async function watchAutoMl(');
const to=raw.indexOf('async function watchAutoR12(',from);
assert(from>=0 && to>from,'Production ML auto watcher missing');
const extracted=raw.slice(from,to);

const ID='a'.repeat(32),SHA='b'.repeat(64);
async function probe(status){
  let calls=0,sleeps=0,reloads=0,branches=0;
  const output={textContent:''};
  const scope=vm.createContext({
    $:id=>{assert.equal(id,'brepMlResults');return output;},
    jobId:ID,current:{sha256:SHA},autoMlGeneration:10,
    get:async url=>{
      assert.equal(url,'/api/ml/latest/'+ID);
      calls++;
      return {status,message:'ML face evidence was blocked',
              id:'c'.repeat(32),cad_job_id:ID,cad_sha256:SHA};
    },
    sleep:async()=>{sleeps++;if(sleeps>2)throw Error('Unexpected repeated poll');},
    loadCurrentResults:async()=>{reloads++;},
    watchAutoR12:()=>{branches++;}
  });
  vm.runInContext(extracted,scope);
  await scope.watchAutoMl(ID,SHA,10,true);
  return {output:output.textContent,calls,sleeps,reloads,branches};
}

(async()=>{
  const rejected=await probe('evidence_rejected');
  assert.match(rejected.output,/evidence_rejected/);
  assert.equal(rejected.calls,1);
  assert.equal(rejected.sleeps,0);
  assert.equal(rejected.reloads,1);
  assert.equal(rejected.branches,0);
  const failed=await probe('failed');
  assert.match(failed.output,/failed/);
  assert.equal(failed.calls,1);
  assert.equal(failed.sleeps,0);
  console.log('L-bracket auto-ML evidence-rejected terminal state PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
