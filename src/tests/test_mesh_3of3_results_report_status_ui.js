'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8').replace(/\r\n/g,'\n');
const html=fs.readFileSync(path.join(__dirname,'../payload/frontend/index.html'),'utf8');
const i=src.indexOf('function gfMeshProgressModel('),j=src.indexOf('async function gfRecheckUnknownMeshSeries()',i);
assert(i>0&&j>i);
assert.match(html,/id="gfMeshVerifiedNumbers"/);
const uid='1'.repeat(32),sha='a'.repeat(64),study='2'.repeat(32),ids=['3'.repeat(32),'4'.repeat(32),'5'.repeat(32)];
const rows={textContent:''};
const ctx={jobId:uid,current:{sha256:sha},meshSeriesId:study,$:name=>name==='gfMeshVerifiedNumbers'?rows:null};
vm.createContext(ctx);vm.runInContext(src.slice(i,j),ctx);
const state={id:study,cad_job_id:uid,cad_sha256:sha,status:'verifying',total:3,
 completed:3,current_index:2,analysis_snapshot_ids:ids,mesh_study_verified:false,
 study_analysis:null};
const m=ctx.gfMeshProgressModel(state,uid,sha,study);
assert.equal(m.valid,true);
assert.deepEqual(Array.from(m.steps),['calculated','calculated','calculated']);
assert.match(m.text,/3\/3 CalculiX 계산 저장 완료/);
assert.match(m.text,/원본 재검증 진행 중/);
ctx.gfRenderMeshProgress(state,uid,sha,study);
assert.match(rows.textContent,/3\/3 CalculiX 계산 저장 완료/);
const bad={...state,status:'verification_failed',verification_warning:'FRD hash mismatch'};
ctx.gfRenderMeshProgress(bad,uid,sha,study);
assert.match(rows.textContent,/FRD hash mismatch/);
const real={runs:[
 {mesh:4,stress:18.5,disp:0.033},
 {mesh:3,stress:18.6,disp:0.034},
 {mesh:2.2,stress:18.7,disp:0.0344}
 ],steps:[{stress:0.538,disp:2.941},{stress:0.535,disp:1.163}]};
assert.equal(ctx.gfMeshNumbersDisplay(real),true);
for(const text of ['① 굵음','② 기준','③ 미세','18.5000 MPa','0.034400 mm','2→3','수렴·구조 안전 인증은 아닙니다'])assert(rows.textContent.includes(text),text);
const before=rows.textContent;
assert.equal(ctx.gfMeshNumbersDisplay({runs:[{mesh:4,stress:'999',disp:0}]}),false);
assert.equal(rows.textContent,before);
ctx.gfRenderMeshProgress(null);
assert.match(rows.textContent,/검사 전/);
assert.match(src,/gfLastMeshStatus\?\.completed===3/);
assert.match(src,/실제 계산 기록 저장 완료 · INP·STA·FRD 최종 원본 검증 진행 중/);
assert.match(src,/if\(verified\)gfMeshNumbersDisplay\(verified\)/);
assert.match(src,/if\(verifiedMesh\)gfMeshNumbersDisplay\(verifiedMesh\)/);
assert.match(src,/gfAppendMeshFollowup\(parsed,evidence,meshFollowup\)/);
assert.match(src,/parsed\.getElementById\('geofield-a08-evidence'\)/); // keep independently verified FEA evidence
console.log('PASS: 3/3 verifies distinctly, exposes actual three numerical rows only after verified proof, shows failures and clears stale data');
