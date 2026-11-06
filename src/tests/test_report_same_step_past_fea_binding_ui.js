'use strict';
// Production report linkage for a user-selected SAME-STEP past FEA run.
// Read-only mocked server messages; no solver, SQLite writes, LLM tokens.
const assert=require('node:assert/strict'),fs=require('node:fs');
const path=require('node:path'),vm=require('node:vm');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8').replace(/\r\n/g,'\n');
const a=src.indexOf('// GEOFIELD_PAST_FEA_REPORT_READONLY_20261106');
const b=src.indexOf('async function gfBuildVisibleReport(',a);
const c=src.indexOf('function gfArchivedNumbersIdentityCheck(');
const d=src.indexOf('// GEOFIELD_STAGE4_QUICK_ARCHIVE_COMPARISON_20261105',c);
const e=src.indexOf('function gfStage4ComparisonPresent(');
const f=src.indexOf('async function gfStage4CompareWithPast(',e);
assert(a>0&&b>a&&c>0&&d>c&&e>0&&f>e);
const builder=src.slice(b,src.indexOf('// GEOFIELD_AI_MESH_FEEDBACK_UI_V1',b));
assert(builder.includes('gfFetchPastFeaReportProof(uid,sha,run,caseSha)'));
assert(builder.includes('gfAppendPastFeaReportProof(parsed,evidence,pastFea)'));
assert(builder.includes('if(includeExternal&&pastFea.selected&&!pastFea.proof)'));
assert(builder.indexOf('if(includeExternal&&pastFea.selected&&!pastFea.proof)')<
 builder.indexOf("await get('/api/agent/evidence/"),
 'requested but unverifiable prior comparison must block paid AI');
const UID='1'.repeat(32),SHA='a'.repeat(64),RUN='2'.repeat(32),CASE='b'.repeat(64);
const OLD='3'.repeat(32),CUR='4'.repeat(32),OLD_RUN='5'.repeat(32),OLD_CASE='c'.repeat(64);
const selected={id:OLD,job_id:UID,cad_sha256:SHA,
 result_run_id:OLD_RUN,result_case_sha256:OLD_CASE};
const link=()=>({ok:true,status:'verified_current_fea_snapshot',
 verification:'rechecked_actual_inp_sta_frd',archive_saved:true,read_only:true,
 cad_job_id:UID,cad_sha256:SHA,run_id:RUN,case_sha256:CASE,snapshot_id:CUR});
const archive=()=>({ok:true,read_only:true,current_session_unchanged:true,
 verification:'rechecked_actual_inp_sta_frd',snapshot_id:OLD,
 cad_job_id:UID,cad_sha256:SHA,run_id:OLD_RUN,case_sha256:OLD_CASE,
 maximum_von_mises_mpa:10,maximum_displacement_mm:.020,
 mesh:{nodes:400,tetrahedra:1600}});
const comparison=()=>({
 status:'verified_read_only_comparison',same_cad:true,same_material:true,
 same_boundary_conditions:true,stress_change:{absolute_difference:2,percent_vs_left:20},
 displacement_change:{absolute_difference:.002,percent_vs_left:10},
 left:{snapshot_id:OLD,run_id:OLD_RUN,case_sha256:OLD_CASE,
  cad_sha256:SHA,evidence:'real_solver_files_revalidated',
  max_stress_mpa:10,max_displacement_mm:.02,
  material:'SUS304',force_n:49.03,fixed_faces:[2],load_faces:[7]},
 right:{snapshot_id:CUR,run_id:RUN,case_sha256:CASE,
  cad_sha256:SHA,evidence:'real_solver_files_revalidated',
  max_stress_mpa:12,max_displacement_mm:.022,
  mesh_node_count:600,mesh_tetrahedron_count:2000,
  material:'SUS304',force_n:49.03,fixed_faces:[2],load_faces:[7]}});
let stale=false,requests=[],responses=null,selection={...selected};
const context={String,Number,Array,Math,Object,Error,Promise,Map,URLSearchParams,
 encodeURIComponent,feaArchiveSelector:{value:OLD},feaArchiveItems:[selection],
 latestSummary:{fea:{maximum_von_mises_mpa:12,maximum_displacement_mm:.022,
  node_count:600,tetrahedron_count:2000}},
 gfReportSelectionCurrent:()=>!stale,
 get:async url=>{
  requests.push(url);
  if(url.startsWith('/api/fea/current-snapshot/'))return responses?.link??link();
  if(url.startsWith('/api/fea/verified_archive_numbers/'))return responses?.archive??archive();
  if(url.startsWith('/api/history/fea-compare?'))return responses?.comparison??comparison();
  throw Error('No paid/solver API allowed: '+url);
 }};
vm.createContext(context);
vm.runInContext(src.slice(a,b)+'\n'+src.slice(c,d)+'\n'+src.slice(e,f),context);
const fetch=()=>context.gfFetchPastFeaReportProof(UID,SHA,RUN,CASE);
(async()=>{
 const valid=await fetch();assert(valid.selected&&valid.proof);
 assert.equal(valid.proof.previousRun,OLD_RUN);
 assert.equal(valid.proof.currentRun,RUN);
 assert.deepEqual(requests.map(url=>url.split('?')[0]),[
  '/api/fea/current-snapshot/'+UID,
  '/api/fea/verified_archive_numbers/'+OLD,
  '/api/history/fea-compare'
 ]);
 const tags=new Map();
 const anchor={insertAdjacentElement(_place,node){tags.set(node.id,node)}};
 const doc={getElementById:id=>id==='geofield-a08-evidence'?anchor:tags.get(id)||null,
  createElement:tag=>({tag,id:'',style:{},textContent:'',attrs:{},children:[],
   setAttribute(k,v){this.attrs[k]=v},append(...xs){this.children.push(...xs)}}),
  body:{append(){throw Error('Expected original verified HTML anchor')}}};
 assert.equal(context.gfAppendPastFeaReportProof(doc,anchor,valid),true);
 const section=tags.get('geofield-same-step-past-fea-comparison');
 assert(section);
 assert.equal(section.attrs['data-gf-previous-snapshot'],OLD);
 assert.equal(section.attrs['data-gf-current-snapshot'],CUR);
 assert.equal(section.attrs['data-gf-current-run'],RUN);
 const text=section.children.map(x=>x.textContent).join('\n');
 assert.match(text,/최대 응력.*10\.00000 MPa.*12\.00000 MPa/);
 assert.match(text,/응력 변화.*\+2\.00000 MPa.*20\.000%/);
 assert.match(text,/변위 변화.*\+0\.002000 mm.*10\.000%/);
 assert.match(text,/구조 안전성을 의미하지 않습니다/);
 assert(!requests.some(x=>x.includes('agent/evidence')||x.includes('llm=1')));
 const problems=[
  ['old snapshot substitution',{link:{...link(),snapshot_id:OLD}}],
  ['old result changed',{archive:{...archive(),cad_sha256:'d'.repeat(64)}}],
  ['different CASE',{comparison:{...comparison(),right:{
    ...comparison().right,case_sha256:'d'.repeat(64)}}}],
  ['different current stress',{comparison:{...comparison(),right:{
    ...comparison().right,max_stress_mpa:12.5}}}],
  ['different current mesh',{comparison:{...comparison(),right:{
    ...comparison().right,mesh_node_count:999}}}],
  ['wrong percent',{comparison:{...comparison(),stress_change:{
    ...comparison().stress_change,percent_vs_left:80}}}],
  ['wrong displacement delta',{comparison:{...comparison(),displacement_change:{
    ...comparison().displacement_change,absolute_difference:99}}}],
  ['wrong old run',{comparison:{...comparison(),left:{
    ...comparison().left,run_id:'f'.repeat(32)}}}]
 ];
 for(const [name,payload] of problems){
  responses=payload;
  const bad=await fetch();
  assert.equal(bad.selected,true,name);
  assert.equal(bad.proof,null,name);
  assert.match(bad.note,/재검증 실패|동일한 실행/);
 }
 responses=null;
 selection={...selection,cad_sha256:'e'.repeat(64)};
 context.feaArchiveItems=[selection];
 requests=[];
 const wrongCAD=await fetch();
 assert.equal(wrongCAD.selected,true);
 assert.equal(wrongCAD.proof,null);
 assert.equal(requests.length,0,'different STEP must be rejected before archive readback');
 context.feaArchiveItems=[selected];
 context.feaArchiveSelector.value='';
 const none=await fetch();
 assert.equal(none.selected,false);
 context.feaArchiveSelector.value=OLD;
 stale=true;
 await assert.rejects(fetch(),/현재 CAD\/FEA 실행이 변경/);
 stale=false;
 context.get=async()=>{
  context.feaArchiveSelector.value=CUR;
  return link();
 };
 await assert.rejects(fetch(),/선택이 변경/);
 console.log('PASS: 3 real past/current INP-STA-FRD readbacks, same-STEP 10/12MPa and .02/.022mm, B-A arithmetic, stale/corrupt/missing comparison, zero paid APIs');
})().catch(e=>{console.error(e);process.exitCode=1});
