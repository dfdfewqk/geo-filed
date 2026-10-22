// Real GeoField UI function against Chat A's documented verified three-mesh response.
// Fixtures are synthetic. Never claim that they are CalculiX convergence results.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const start=source.indexOf('function gfMeshSensitivityLabel(');
const end=source.indexOf('function gfMeshSpatialEvidence(',start);
assert(start>=0&&end>start);
const ctx=vm.createContext({});
vm.runInContext(source.slice(start,end),ctx);
const label=(a)=>ctx.gfMeshSensitivityLabel(a);
function fixture(){
 return {
  status:'verified_three_mesh_sensitivity_only',
  solver_evidence:'each_calculix_run_revalidated',same_physical_case:true,
  mesh_count_increases_with_refinement:true,node_count_increases_with_refinement:true,
  adjacent_changes:[
   {stress_relative_change_percent:1.2,displacement_relative_change_percent:2.1},
   {stress_relative_change_percent:0.8,displacement_relative_change_percent:1.4}],
  actual_load_moment_comparability:{
   status:'evaluated_from_three_verified_inp_decks',
   moment_comparable_for_mesh_only_review:true},
  actual_mesh_resolution_diagnostic:{
   status:'measured_from_three_verified_inp_meshes',effective_mean_edge_refinement:true},
  numeric_stability_diagnostic:{
   threshold_percent:5,passes:true,actual_inp_load_screen_passes:true}
 };
}
let count=0;
{
 const s=label(fixture());
 assert.match(s,/기준 충족/);
 assert.match(s,/수렴 증명 아님/);
 assert.match(s,/구조 안전성 판단 불가/);
 count++;
}
{
 const a=fixture();a.actual_mesh_resolution_diagnostic.effective_mean_edge_refinement=false;
 a.numeric_stability_diagnostic.passes=false;
 const s=label(a);assert.match(s,/기준 미충족/);assert.match(s,/평균 변 길이/);
 assert.doesNotMatch(s,/기준 충족/);count++;
}
{
 const a=fixture();a.actual_load_moment_comparability.moment_comparable_for_mesh_only_review=false;
 a.numeric_stability_diagnostic.actual_inp_load_screen_passes=false;
 a.numeric_stability_diagnostic.passes=false;
 const s=label(a);assert.match(s,/하중 모멘트 불일치/);assert.match(s,/기준 미충족/);count++;
}
{
 const a=fixture();a.numeric_stability_diagnostic.passes=false;
 assert.match(label(a),/진단 값 충돌/);count++;
}
{
 const a=fixture();a.actual_mesh_resolution_diagnostic.effective_mean_edge_refinement=false;
 assert.match(label(a),/진단 값 충돌/);count++;
}
{
 const a=fixture();a.actual_load_moment_comparability.moment_comparable_for_mesh_only_review=false;
 assert.match(label(a),/진단 값 충돌/);count++;
}
{
 const a=fixture();a.actual_load_moment_comparability.moment_comparable_for_mesh_only_review=false;
 a.numeric_stability_diagnostic.actual_inp_load_screen_passes=false;
 assert.match(label(a),/진단 값 충돌/);count++;
}
{
 const a=fixture();delete a.actual_mesh_resolution_diagnostic;
 assert.match(label(a),/근거 부족/);count++;
}
{
 const a=fixture();delete a.actual_load_moment_comparability;
 assert.match(label(a),/근거 부족/);count++;
}
{
 const a=fixture();delete a.numeric_stability_diagnostic.actual_inp_load_screen_passes;
 assert.match(label(a),/근거 부족/);count++;
}
{
 const a=fixture();a.adjacent_changes[1].stress_relative_change_percent=9;
 a.numeric_stability_diagnostic.passes=false;
 assert.match(label(a),/기준 미충족/);count++;
}
{
 const a=fixture();a.mesh_count_increases_with_refinement=false;
 a.numeric_stability_diagnostic.passes=false;
 assert.match(label(a),/기준 미충족/);count++;
}
{
 const a=fixture();a.adjacent_changes[0].displacement_relative_change_percent=null;
 assert.match(label(a),/진단 수치 누락/);count++;
}
console.log('PASS: '+count+' verified three-mesh frontend contract cases');
