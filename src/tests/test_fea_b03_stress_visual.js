// B03: real frontend functions with synthetic data; no fake solver success.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),
 vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
function part(start,end){
 const a=source.indexOf(start),b=source.indexOf(end,a+start.length);
 assert(a>=0&&b>a,'Cannot extract original frontend '+start);
 return source.slice(a,b);
}
const selected=part('function gfFeaFieldSummaryCheck(', 'function resetFeaField(');
const nodes={feaContourMode:{disabled:true,value:'none'},
 feaDeformToggle:{disabled:true},feaDeformScale:{disabled:true},
 feaContourStatus:{textContent:''}};
const id='1'.repeat(32),job='2'.repeat(32),sha='a'.repeat(64),caseSha='b'.repeat(64);
const camera={rotation:[.1,.2,.3,.9],zoom:2.3,pan:[.4,-.2]};
const ctx={Math,Number,String,Object,Array,Error,Boolean,console,
 app:{mesh:{modelTransform:{center:[0,0,0],size:10}},...camera},
 current:{sha256:sha},jobId:job,feaPreparedCaseSha:caseSha,
 feaField:null,feaContourMode:'none',feaFieldRunId:null,feaActualLoadMarkers:null,
 $:name=>{assert(nodes[name],name);return nodes[name]},
 clearFeaGL:()=>{},feaStressReference:()=>({upper:10}),feaStressScaleStatus:()=>{},draw:()=>{ctx.draws++},draws:0};
vm.createContext(ctx);
vm.runInContext(selected,ctx);
const result={maximum_nodal_von_mises_mpa:13,maximum_displacement_mm:.04};
const base=()=>({
 schema:'geofield-fea-surface-field-v1',source:'actual_calculix_ascii_frd',
 run_id:id,cad_job_id:job,cad_sha256:sha,case_sha256:caseSha,
 stress_units:'MPa',displacement_units:'mm',
 stress_interpretation:'extrapolated_nodal_stress_not_integration_point',
 positions_mm:[[0,0,0],[1,0,0],[0,1,0]],triangles:[[0,1,2]],
 von_mises_mpa:[2,8,3],displacements_mm:[[0,0,0],[0,.01,0],[0,0,.02]],
 surface_evidence:{
  source:'reverified_actual_calculix_frd_surface_nodes',
  run_id:id,cad_sha256:sha,case_sha256:caseSha,
  stress_units:'MPa',displacement_units:'mm',positions_units:'mm',
  surface_max_von_mises_mpa:8,global_max_von_mises_mpa:13,
  surface_max_displacement_mm:.02,global_max_displacement_mm:.04,
  surface_displacement_peak_position_mm:[0,1,0],
  surface_stress_peak_position_mm:[1,0,0],
  cad_face_correspondence_verified:false,
  stress_concentration_cause_verified:false,safety_certified:false
 }
});
const run=f=>ctx.setFeaField(f,sha,caseSha,id,result);
const valid=base(),snapshot=JSON.stringify(valid);
run(valid);
assert.equal(JSON.stringify(valid),snapshot,'solver data must not be changed');
assert.equal(ctx.feaField.peakEvidence.index,1);
assert.equal(ctx.feaField.peakEvidence.surfaceMax,8);
assert.equal(ctx.feaField.peakEvidence.globalMax,13);
assert.equal(ctx.feaField.peakEvidence.globalPositionVerified,false);
assert.match(nodes.feaContourStatus.textContent,/전체 절점 최대 13/);
assert.match(nodes.feaContourStatus.textContent,/전체 최대 위치 미검증/);
assert.match(nodes.feaContourStatus.textContent,/\(1.00, 0.00, 0.00\) mm/);
assert.equal(nodes.feaContourMode.value,'stress');
assert.deepEqual(ctx.app.rotation,camera.rotation);
assert.deepEqual(ctx.app.pan,camera.pan);
assert.equal(ctx.app.zoom,camera.zoom);
let rejected=0;
for(const change of [
 f=>delete f.surface_evidence,
 f=>f.surface_evidence.run_id='3'.repeat(32),
 f=>f.surface_evidence.case_sha256='c'.repeat(64),
 f=>f.surface_evidence.stress_units='Pa',
 f=>f.stress_units='Pa',
 f=>f.surface_evidence.global_max_von_mises_mpa=8,
 f=>f.surface_evidence.surface_max_von_mises_mpa=12,
 f=>f.surface_evidence.surface_stress_peak_position_mm=[9,9,9],
 f=>f.surface_evidence.surface_stress_peak_position_mm=[0,0,0],
 f=>f.surface_evidence.cad_face_correspondence_verified=true,
 f=>f.surface_evidence.safety_certified=true,
 f=>f.von_mises_mpa[1]=14
]){
 const f=base();change(f);
 assert.throws(()=>run(f),Error,'corrupted field must not render');rejected++;
}
assert.equal(ctx.feaField.peakEvidence.surfaceMax,8,'invalid input cannot overwrite prior verified field');
assert(source.includes("e=vec3(224.,40.,40.)/255."),'GPU must render high stress red');
assert(source.includes("FRD 표면 절점 (2D 투영)"),'overlay must disclose projected coordinates');
assert(source.includes("feaField.displacementEvidence:feaField.peakEvidence"),'marker must use verified A06 stress/displacement peaks');
console.log('B03: verified surface/global distinctions, camera, units, invalid evidence ('+rejected+') passed');
