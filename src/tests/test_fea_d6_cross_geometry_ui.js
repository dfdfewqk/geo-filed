'use strict';
// Exercise production UI A/B cross-STEP handler with synthetic verified summaries.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../payload/frontend/index.html'),'utf8');
const start=src.indexOf('// GEOFIELD_D6_CROSS_GEOMETRY_UI_V1');
const end=src.indexOf('// GeoField R18 verified FEA comparison',start);
assert(start>0&&end>start);
assert.equal((html.match(/id="feaD6CompareRun"/g)||[]).length,1);
assert(html.indexOf('id="feaCompareRun"')<html.indexOf('id="feaD6CompareRun"'));
const A='3'.repeat(32),B='4'.repeat(32),R1='1'.repeat(32),R2='2'.repeat(32);
const S1='a'.repeat(64),S2='b'.repeat(64);
const base=(snapshot_id,run_id,cad_sha256,cad_name,stress,disp,meshNodeCount,tetraCount)=>({
 snapshot_id,run_id,cad_sha256,cad_name,case_sha256:'c'.repeat(64),
 max_stress_mpa:stress,max_displacement_mm:disp,mesh_target_mm:1.8,
 mesh_node_count:meshNodeCount,mesh_tetrahedron_count:tetraCount});
const valid=()=>({
 schema:'geofield-d6-two-geometry-descriptive-v1',
 status:'two_different_cad_real_solver_runs_descriptive_only',
 read_only:true,source:'original_and_server_generated_D6_step_sha_bound',
 original:base(A,R1,S1,'L_bracket.step',20,.03,1000,3500),
 variant:base(B,R2,S2,'L_bracket_D6.step',18,.027,1250,4400),
 same_material_and_selected_load_magnitude_direction:true,
 same_nominal_mesh_target:true,actual_mesh_counts_may_differ:true,
 fixed_and_loaded_surface_equivalence_verified:false,
 reaction_and_applied_moment_equivalence_verified:false,
 support_location_screen_passed:true,
 applied_load_moment_screen_passed:true,
 physical_load_screen:{
  support_bbox_max_drift_mm:0.01,load_bbox_max_drift_mm:0.02,
  load_center_distance_mm:0.03,resultant_drift_n:0.001,
  load_moment_change_n_mm:0.02,
  load_moment_equivalent_lever_arm_change_mm:0.001},
 hotspot_location_correspondence_verified:false,
 mesh_convergence_certified:false,design_improvement_verified:false,
 structural_safety_certified:false,
 stress_change:{original:20,variant:18,absolute_difference:-2,percent_vs_original:-10},
 displacement_change:{original:.03,variant:.027,absolute_difference:-.003,percent_vs_original:-10},
 message:'서로 다른 STEP 형상에 대한 별도 실제 CalculiX 수치 관찰'}
);
const controls={feaD6CompareRun:{disabled:false},
 feaD6CompareOutput:{textContent:''}};
const query=[],calls=[];
let reply=valid(),consent=true;
const ctx={String,Math,Number,Error,Promise,URLSearchParams,jobId:null,
 $:id=>controls[id]||null,
 window:{confirm:()=>{calls.push('user confirm');return consent;}},
 get:async(url)=>{query.push(url);return reply},
 feaComparePick:{left:A,right:B}};
vm.createContext(ctx);vm.runInContext(src.slice(start,end),ctx);
(async()=>{
 consent=false;
 await controls.feaD6CompareRun.onclick();
 assert.equal(query.length,0,'not approved: zero reads');
 consent=true;
 await controls.feaD6CompareRun.onclick();
 assert.equal(query.length,1);
 assert(query[0].includes('original='+A)&&query[0].includes('variant='+B));
 assert.match(controls.feaD6CompareOutput.textContent,/응력의 관찰된 차이/);
 assert.match(controls.feaD6CompareOutput.textContent,/설계 개선 성공 미확정/);
 assert.equal(controls.feaD6CompareRun.disabled,false);
 assert(!src.slice(start,end).includes('gf_agent_llm_optional('));
 assert(!src.slice(start,end).includes('/api/agent/evidence/'));
 for(const bad of [
  {...valid(),design_improvement_verified:true},
  {...valid(),original:{...valid().original,cad_sha256:S2}},
  {...valid(),stress_change:{...valid().stress_change,original:999}},
  {...valid(),fixed_and_loaded_surface_equivalence_verified:true}
 ]){
  reply=bad;
  await controls.feaD6CompareRun.onclick();
  assert.match(controls.feaD6CompareOutput.textContent,/비교 보류/);
 }
 ctx.feaComparePick.right=null;
 const before=query.length;
 await controls.feaD6CompareRun.onclick();
 assert.equal(query.length,before);
 assert.match(controls.feaD6CompareOutput.textContent,/A에 원본/);
 console.log('PASS: separate A/B geometry comparison, explicit consent, strict evidence flags, no paid LLM');
})().catch(e=>{console.error(e);process.exitCode=1});
