// Exercise actual FEA history comparison UI with synthetic delayed HTTP.
// No solver, file, or SQLite data is involved.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),
      vm=require('node:vm'),path=require('node:path');
const js=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const start=js.indexOf("$('feaCompareRun').onclick=async()=>{");
const end=js.indexOf('// GeoField R18 verified FEA comparison',start);
assert(start>=0&&end>start,'Real FEA compare handler not found');
const code=js.slice(start,end);
const id=n=>String(n).repeat(32),sha=n=>String(n).repeat(64);
const left=id('3'),right=id('4'),RUN1=id('1'),RUN2=id('2'),CAD=sha('a');
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}};
function data(){
 const side=(snapshot_id,run_id,max_stress_mpa,max_displacement_mm)=>({
   snapshot_id,run_id,cad_sha256:CAD,material:'steel',cad_name:'sample',
   external_mass_kg:5,force_n:49.05,fixed_faces:[1],load_faces:[3],
   max_stress_mpa,max_displacement_mm});
 return {status:'verified_read_only_comparison',left:side(left,RUN1,12,.04),
  right:side(right,RUN2,15,.05),
  same_cad:true,same_material:true,same_boundary_conditions:true,
  stress_change:{absolute_difference:3,percent_vs_left:25},
  displacement_change:{absolute_difference:.01,percent_vs_left:25},
  message:'Actual FEA revalidated',
  agent_review:{
   schema:'geofield-agent-fea-comparison-v1',
   status:'same_cad_verified_runs_descriptive_comparison',
   left_run_id:RUN1,right_run_id:RUN2,cad_sha256:CAD,
   changes:['force','external_mass'],unverified_condition_groups:['mesh'],
   stress_change:{absolute_difference:3,percent_vs_left:25},
   displacement_change:{absolute_difference:.01,percent_vs_left:25},
   causal_effect_verified:false,structural_safety_verified:false,
   mesh_convergence_verified:false,
   note:'No causal engineering effect certified',
   next_check:'Hold conditions fixed and recalculate'}};
}
function harness(){
 const nodes={feaCompareRun:{disabled:false},feaCompareOutput:{textContent:''}};
 const pending=[], statuses=[],pick={left,right};
 const ctx={String,Number,Array,Object,Math,URLSearchParams,Promise,Error,
  feaComparePick:pick,$:k=>nodes[k]||={textContent:'',disabled:false},
  get:url=>{const q=deferred();pending.push({url,...q});return q.promise},
  status:(...s)=>statuses.push(s)};
 vm.createContext(ctx);vm.runInContext(code,ctx);
 return {ctx,pending,nodes,statuses,pick};
}
let count=0;
async function checkVerifiedAgent(){
 const h=harness(),work=h.ctx.$('feaCompareRun').onclick();
 assert.equal(h.pending.length,1);
 assert(h.pending[0].url.includes('left='+left));
 h.pending[0].resolve(data());await work;
 assert.match(h.nodes.feaCompareOutput.textContent,/기록상 달라진 조건: 하중\/방향, 외부 질량/);
 assert.match(h.nodes.feaCompareOutput.textContent,/요소 종류\(C3D4\/C3D10\)/);
 assert.match(h.nodes.feaCompareOutput.textContent,/No causal engineering effect certified/);
 assert.match(h.nodes.feaCompareOutput.textContent,/응력 차이 B-A: 3\.000000 MPa/);
 assert.equal(h.nodes.feaCompareRun.disabled,false);
 count++;
}
async function checkTamperedAgentDelta(){
 const h=harness(),work=h.ctx.$('feaCompareRun').onclick();
 const response=data();response.agent_review.stress_change.absolute_difference=500;
 h.pending[0].resolve(response);await work;
 assert.match(h.nodes.feaCompareOutput.textContent,/원본 FEA 수치/);
 count++;
}
async function checkMisidentifiedRun(){
 const h=harness(),work=h.ctx.$('feaCompareRun').onclick();
 const response=data();response.agent_review.left_run_id=id('9');
 h.pending[0].resolve(response);await work;
 assert.match(h.nodes.feaCompareOutput.textContent,/원본 FEA 수치/);
 count++;
}
async function checkFalseCertifiedSafety(){
 const h=harness(),work=h.ctx.$('feaCompareRun').onclick();
 const response=data();response.agent_review.structural_safety_verified=true;
 h.pending[0].resolve(response);await work;
 assert.match(h.nodes.feaCompareOutput.textContent,/계약 오류/);
 count++;
}
async function checkDifferentCad(){
 const h=harness(),work=h.ctx.$('feaCompareRun').onclick();
 const response=data();response.agent_review={
  schema:'geofield-agent-fea-comparison-v1',
  status:'different_cad_not_comparable',causal_effect_verified:false,
  structural_safety_verified:false,mesh_convergence_verified:false,
  note:'Different STEP'};
 h.pending[0].resolve(response);await work;
 assert.match(h.nodes.feaCompareOutput.textContent,/AI 에이전트 판단 보류/);
 assert.match(h.nodes.feaCompareOutput.textContent,/Different STEP/);
 count++;
}
async function checkSelectionRace(){
 const h=harness(),work=h.ctx.$('feaCompareRun').onclick();
 h.pick.right=id('7');
 h.nodes.feaCompareOutput.textContent='new selection must remain';
 h.pending[0].resolve(data());await work;
 assert.equal(h.nodes.feaCompareOutput.textContent,'new selection must remain');
 count++;
}
async function checkUnverifiedSideIdentity(){
 const h=harness(),work=h.ctx.$('feaCompareRun').onclick();
 const response=data();response.left.snapshot_id=id('8');
 h.pending[0].resolve(response);await work;
 assert.match(h.nodes.feaCompareOutput.textContent,/기록 ID/);
 count++;
}
async function checkOldBackendNoReview(){
 const h=harness(),work=h.ctx.$('feaCompareRun').onclick();
 const response=data();delete response.agent_review;
 h.pending[0].resolve(response);await work;
 assert.match(h.nodes.feaCompareOutput.textContent,/AI 근거 비교 미제공/);
 count++;
}
async function checkPercentAndMissing(){
 const x=harness(),work=x.ctx.$('feaCompareRun').onclick();
 x.pending[0].resolve(data());await work;
 assert.match(x.nodes.feaCompareOutput.textContent,/응력 변화율 \(A 기준\): 25\.0000%/);
 assert.match(x.nodes.feaCompareOutput.textContent,/변위 변화율 \(A 기준\): 25\.0000%/);
 count++;
 const y=harness(),again=y.ctx.$('feaCompareRun').onclick();
 const partial=data();
 partial.left.max_stress_mpa=null;partial.right.max_stress_mpa=null;
 partial.stress_change={absolute_difference:null,percent_vs_left:null};
 partial.agent_review={schema:'geofield-agent-fea-comparison-v1',status:'not_verified',
  causal_effect_verified:false,structural_safety_verified:false,mesh_convergence_verified:false,note:'Missing stress'};
 y.pending[0].resolve(partial);await again;
 assert.match(y.nodes.feaCompareOutput.textContent,/응력 차이 B-A: 비교 불가/);
 assert.match(y.nodes.feaCompareOutput.textContent,/응력 변화율 \(A 기준\): 비교 불가/);
 assert.match(y.nodes.feaCompareOutput.textContent,/변위 변화율 \(A 기준\): 25\.0000%/);
 count++;
 const z=harness(),zero=z.ctx.$('feaCompareRun').onclick();
 const base=data();base.left.max_stress_mpa=0;
 base.stress_change={absolute_difference:15,percent_vs_left:null};
 base.agent_review={schema:'geofield-agent-fea-comparison-v1',status:'not_verified',
  causal_effect_verified:false,structural_safety_verified:false,mesh_convergence_verified:false,note:'A equals zero'};
 z.pending[0].resolve(base);await zero;
 assert.match(z.nodes.feaCompareOutput.textContent,/응력 차이 B-A: 15\.000000 MPa/);
 assert.match(z.nodes.feaCompareOutput.textContent,/응력 변화율 \(A 기준\): 비교 불가/);
 count++;
}
(async()=>{await checkVerifiedAgent();await checkTamperedAgentDelta();await checkMisidentifiedRun();
 await checkFalseCertifiedSafety();await checkDifferentCad();await checkSelectionRace();
 await checkUnverifiedSideIdentity();await checkOldBackendNoReview();await checkPercentAndMissing();
 console.log('PASS: '+count+' real GeoField agent verified FEA comparison UI contracts');
})().catch(e=>{console.error(e);process.exitCode=1});
