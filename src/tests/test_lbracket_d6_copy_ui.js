'use strict';
// Exercise the native optional geometry export handler; no live STEP, solver,
// SQLite, private data or paid model call. Browser output hash is mandatory.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const {createHash,webcrypto}=require('node:crypto');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../payload/frontend/index.html'),'utf8');
const a=src.indexOf('function gfReportReady('),b=src.indexOf("$('collapseBtn').onclick",a);
assert(a>0&&b>a&&src.slice(a,b).includes('GEOFIELD_LBRACKET_D6_COPY_UI_V1'));
assert.equal((html.match(/id="gfD6VariantBtn"/g)||[]).length,1);
const SHA='a'.repeat(64),CASE='b'.repeat(64),JOB='1'.repeat(32),RUN='2'.repeat(32);
const output=Buffer.from('ISO-10303-21;\nDATA;\nFAKE-GEOMETRY-CANDIDATE-FOR-UNIT-TEST-ONLY;\nENDSEC;\n');
const newSha=createHash('sha256').update(output).digest('hex');
const valid=()=>({cad:{sha256:SHA},fea:{state:'complete',result_run_id:RUN,
 result_case_sha256:CASE,maximum_von_mises_mpa:18.4,
 maximum_displacement_mm:0.033,node_count:400,tetrahedron_count:1500},
 fea_case_provenance:{source_verification:'INP_STA_FRD_reverified',
 summary_numbers_crosschecked:true,verified_run_id:RUN,solved_case_sha256:CASE,
 verified_mesh:{nodes:400,tetrahedra:1500}}});
const nodes={gfD6VariantBtn:{disabled:false},gfD6VariantStatus:{textContent:''},
 resultsReportBtn:{disabled:false},resultsReportSaveBtn:{disabled:false},
 resultsReportStatus:{textContent:''},resultsReportSavedPath:{textContent:''},
 gfMeshFollowupBtn:{disabled:false},gfMeshFollowupStatus:{textContent:''},
 reportAiIncludeToggle:{checked:false}};
const calls={fetch:[],download:[],paid:[],confirm:0,revoke:0};
let decision=true,reply=null,injectChange=false;
function good(){return {status:'geometry_only_verified_no_fea',source_sha256:SHA,
 variant_sha256:newSha,source_hole_diameter_mm:5.5,variant_hole_diameter_mm:6,
 through_cylindrical_faces:4,needs_new_face_selection:true,
 structural_improvement_verified:false,step_base64:output.toString('base64')} }
const ctx={String,Number,Math,Error,Promise,Date,encodeURIComponent,Blob,
 Uint8Array,Array,jobId:JOB,current:{sha256:SHA},latestSummary:valid(),
 feaRunId:null,meshSeriesBusy:false,file:{name:'L_bracket.step',size:35000},
 $:id=>nodes[id]||null,
 window:{confirm(){calls.confirm++;return decision},crypto:webcrypto,
 atob:v=>Buffer.from(v,'base64').toString('binary')},
 DOMParser:class{},
 fetch:async(url,opt)=>{calls.fetch.push({url,opt});
  if(injectChange)ctx.current={sha256:'f'.repeat(64)};
  return {ok:true,status:200,json:async()=>reply||good()}},
 get:async()=>{calls.paid.push('call');throw Error('unexpected paid agent call')},
 URL:{createObjectURL:()=> 'blob:test-geometry-copy',revokeObjectURL(){calls.revoke++}},
 document:{body:{append(){}},createElement:()=>({href:'',download:'',
  click(){calls.download.push(this.download)},remove(){}})},
 setTimeout(){}};
vm.createContext(ctx);
vm.runInContext(src.slice(a,b),ctx);
(async()=>{
 // No implicit call: constructing the results pane never creates a CAD variant.
 assert.equal(calls.fetch.length,0);
 decision=false;
 await nodes.gfD6VariantBtn.onclick();
 assert.equal(calls.fetch.length,0);
 decision=true;
 await nodes.gfD6VariantBtn.onclick();
 assert.equal(calls.fetch.length,1);
 assert.equal(calls.fetch[0].url,'/api/cad/variant/lbracket-d6/'+JOB);
 assert.equal(calls.fetch[0].opt.headers['X-GeoField-Variant-Confirm'],
              'CREATE_D6_SEPARATE_STEP_ONLY');
 assert.equal(calls.fetch[0].opt.headers['X-GeoField-CAD-SHA256'],SHA);
 assert.equal(calls.fetch[0].opt.body,ctx.file);
 assert.equal(calls.download.length,1);
 assert.match(calls.download[0],/^L_bracket_D6_separate_[a-f0-9]{12}\.step$/);
 assert.equal(calls.revoke,1);
 assert.equal(calls.paid.length,0);
 assert.match(nodes.gfD6VariantStatus.textContent,/고정·하중 면을 다시 선택/);
 // Do not accept a mismatched or forged output digest.
 reply={...good(),variant_sha256:'f'.repeat(64)};
 await nodes.gfD6VariantBtn.onclick();
 assert.equal(calls.download.length,1);
 assert.match(nodes.gfD6VariantStatus.textContent,/SHA-256 검증 실패/);
 reply=null;ctx.file.name='other.step';
 await nodes.gfD6VariantBtn.onclick();
 assert.equal(calls.fetch.length,2);
 assert.match(nodes.gfD6VariantStatus.textContent,/원본 L_bracket.step/);
 // Do not send any bytes if there is active solver work.
 ctx.file.name='L_bracket.step';ctx.meshSeriesBusy=true;
 await nodes.gfD6VariantBtn.onclick();
 assert.equal(calls.fetch.length,2);
 // Stale selections while an HTTP reply is in flight must not be downloaded.
 ctx.meshSeriesBusy=false;injectChange=true;
 await nodes.gfD6VariantBtn.onclick();
 assert.equal(calls.fetch.length,3);
 assert.equal(calls.download.length,1);
 console.log('PASS: explicit D6 STEP copy, SHA256 check, no paid calls, stale/solver rejection');
})().catch(e=>{console.error(e);process.exitCode=1});
