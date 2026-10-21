// Exercise the real GeoField import callback with deterministic delayed HTTP replies.
// No browser, FEA solver, CAD files or user data needed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const js = fs.readFileSync(path.join(__dirname, '..', 'payload', 'frontend', 'cad.js'), 'utf8');
const start = js.indexOf("$('importBtn').onclick=async()=>{");
const end = js.indexOf('\nfunction resetModel()', start);
assert(start !== -1 && end > start, 'import callback must exist');
const callback = js.slice(start, end);

function testContext(fetch, get, counters) {
  const elements = new Map();
  const $ = id => {
    if (!elements.has(id)) {
      elements.set(id, {
        disabled: false,
        textContent: '',
        classList: { add() {}, remove() {} },
        querySelector() { return {textContent: ''}; }
      });
    }
    return elements.get(id);
  };
  const sandbox = {
    $, fetch, get,
    resetModel() { counters.reset++; },
    status() {},
    sleep: async() => {},
    loadMesh() { counters.mesh++; },
    console,
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(`let file={name:'old.step',size:128};let stepSelectionVersion=0;let jobId=null;let current=null;let findings=[];const autoMlToggle={checked:false};\n${callback}`, context);
  return { context, start: () => vm.runInContext("$('importBtn').onclick()", context) };
}

async function main() {
  // A new STEP is selected before the HTTP upload completes.
  let completeUpload;
  const upload = new Promise(resolve => { completeUpload = resolve; });
  const counts = {reset: 0, mesh: 0, polls: 0};
  let sent;
  const first = testContext((url, args) => { sent=args; return upload; },
    async() => { counts.polls++; throw Error('stale job should not be polled'); }, counts);
  const work = first.start();
  assert.equal(sent.body.name, 'old.step', 'the request must use the captured original File');
  vm.runInContext("file={name:'new.step',size:140};stepSelectionVersion++", first.context);
  completeUpload({ok: true, json: async() => ({id: '1'.repeat(32)})});
  await work;
  assert.equal(counts.polls, 0, 'late upload response must not activate old CAD');
  assert.equal(vm.runInContext('jobId', first.context), null);
  assert.equal(counts.mesh, 0);

  // The earlier STEP is replaced while the 3D mesh GET is pending.
  let finishMesh, meshRequested;
  const meshReady = new Promise(resolve => { meshRequested = resolve; });
  const meshGate = new Promise(resolve => { finishMesh = resolve; });
  const counts2 = {reset: 0, mesh: 0};
  const second = testContext(
    async() => ({ok: true, json: async() => ({id: '1'.repeat(32)})}),
    async(url) => {
      if (url.startsWith('/api/jobs/'))
        return {id: '1'.repeat(32), status: 'complete',
                analysis: {sha256: 'a'.repeat(64)}, findings: [],
                mesh_url: '/api/model/' + '1'.repeat(32)};
      meshRequested();
      return meshGate;
    }, counts2);
  const work2 = second.start();
  await meshReady;
  assert.equal(vm.runInContext('current', second.context), null,
    'active geometry must not be mutated before asynchronous mesh validation');
  vm.runInContext("file={name:'new.step',size:140};stepSelectionVersion++", second.context);
  finishMesh({sha256: 'a'.repeat(64), mesh: {}});
  await work2;
  assert.equal(counts2.mesh, 0, 'stale mesh must never reach WebGL');
  assert.equal(vm.runInContext('current', second.context), null);
  console.log('PASS: 2 delayed STEP import / model reply race checks');
}
main().catch(err => { console.error(err); process.exitCode = 1; });
