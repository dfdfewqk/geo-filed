// B04: actual browser functions; synthetic data exclusively for regression.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
function part(start,end){
 const a=source.indexOf(start),b=source.indexOf(end,a+start.length);
 assert(a>=0&&b>a,'production block missing: '+start);return source.slice(a,b);
}
const code=part('function gfFeaVisualFactor(','function createFeaGLMesh(')+'\n'+
 part('function gfFeaFieldSummaryCheck(','function paintFeaField(');
const run='1'.repeat(32),job='2'.repeat(32),sha='a'.repeat(64),caseSha='b'.repeat(64);
const nodes={feaContourMode:{disabled:true,value:'none'},feaDeformToggle:{disabled:true,checked:false},
 feaDeformScale:{disabled:true,value:'1'},feaContourStatus:{textContent:''}};
const camera={rotation:[.2,.3,.1,.9],pan:[.2,-.4],zoom:2.5,clip:true,clipValue:.3};
const ctx={Math,Number,String,Object,Array,Boolean,Error,console,
 app:{mesh:{modelTransform:{center:[0,0,0],size:10}},...camera},
 current:{sha256:sha},jobId:job,feaPreparedCaseSha:caseSha,
 feaField:null,feaFieldRunId:null,feaActualLoadMarkers:null,feaContourMode:'none',
 $:k=>{assert(nodes[k],'missing '+k);return nodes[k]},
 clearFeaGL:()=>{ctx.cleared++},feaStressReference:()=>({}),feaStressScaleStatus:()=>{},
 draw:()=>{ctx.drawn++},cleared:0,drawn:0};
vm.createContext(ctx);vm.runInContext(code,ctx);
const result={maximum_nodal_von_mises_mpa:13,maximum_displacement_mm:.04};
const base=()=>({
 schema:'geofield-fea-surface-field-v1',source:'actual_calculix_ascii_frd',
 run_id:run,cad_job_id:job,cad_sha256:sha,case_sha256:caseSha,
 stress_units:'MPa',displacement_units:'mm',
 stress_interpretation:'extrapolated_nodal_stress_not_integration_point',
 positions_mm:[[0,0,0],[1,0,0],[0,1,0]],triangles:[[0,1,2]],
 von_mises_mpa:[2,8,3],displacements_mm:[[0,0,0],[0,.01,0],[0,0,.02]],
 surface_evidence:{source:'reverified_actual_calculix_frd_surface_nodes',
  run_id:run,cad_sha256:sha,case_sha256:caseSha,
  stress_units:'MPa',displacement_units:'mm',positions_units:'mm',
  surface_max_von_mises_mpa:8,global_max_von_mises_mpa:13,
  surface_stress_peak_position_mm:[1,0,0],
  surface_max_displacement_mm:.02,global_max_displacement_mm:.04,
  surface_displacement_peak_position_mm:[0,1,0],
  cad_face_correspondence_verified:false,stress_concentration_cause_verified:false,
  safety_certified:false}
});
const field=base(),old=JSON.stringify(field);
ctx.setFeaField(field,sha,caseSha,run,result);
assert.equal(JSON.stringify(field),old,'original physical solver arrays unchanged');
assert.equal(ctx.feaField.displacementEvidence.index,2);
assert.equal(ctx.feaField.displacementEvidence.surfaceMax,.02);
assert.equal(ctx.feaField.displacementEvidence.globalMax,.04);
assert.equal(ctx.feaField.displacementEvidence.globalPositionVerified,false);
assert.equal(ctx.feaField.dispmag[2],.02);
function cameraIsPreserved(){
 assert.deepEqual(ctx.app.rotation,camera.rotation);
 assert.deepEqual(ctx.app.pan,camera.pan);
 assert.equal(ctx.app.zoom,camera.zoom);
 assert.equal(ctx.app.clip,camera.clip);
 assert.equal(ctx.app.clipValue,camera.clipValue);
}
cameraIsPreserved();
nodes.feaContourMode.value='displacement';ctx.$('feaContourMode').onchange({target:nodes.feaContourMode});
cameraIsPreserved();
assert.match(nodes.feaContourStatus.textContent,/표면 최대 0\.0200000 mm/);
assert.match(nodes.feaContourStatus.textContent,/전체 절점 최대 0\.0400000 mm/);
assert.match(nodes.feaContourStatus.textContent,/색상=실제 변위\(mm\), 배율 무관/);
assert.match(nodes.feaContourStatus.textContent,/전체 최대 위치 미검증/);
nodes.feaDeformToggle.checked=true;nodes.feaDeformScale.value='20';
ctx.$('feaDeformScale').onchange();cameraIsPreserved();
assert.match(nodes.feaContourStatus.textContent,/화면에서만 확대/);
assert.equal(ctx.gfFeaVisualFactor(true,'20'),20);
assert.equal(ctx.gfFeaVisualFactor(true,'not-a-scale'),0);
assert.equal(ctx.gfFeaVisualFactor(false,'20'),0);
assert.equal(ctx.feaField.maxDisp,.02,'visual multiplier must not multiply scalar');
nodes.feaContourMode.value='stress';ctx.$('feaContourMode').onchange({target:nodes.feaContourMode});
cameraIsPreserved();assert.match(nodes.feaContourStatus.textContent,/MPa/);
nodes.feaContourMode.value='displacement';ctx.$('feaContourMode').onchange({target:nodes.feaContourMode});
cameraIsPreserved();assert.match(nodes.feaContourStatus.textContent,/0\.0400000 mm/);
let rejected=0;
for(const change of [
 f=>delete f.surface_evidence.surface_max_displacement_mm,
 f=>f.surface_evidence.global_max_displacement_mm=.02,
 f=>f.surface_evidence.surface_max_displacement_mm=.03,
 f=>f.surface_evidence.surface_displacement_peak_position_mm=[1,0,0],
 f=>f.surface_evidence.surface_displacement_peak_position_mm=[44,0,0],
 f=>f.surface_evidence.displacement_units='m',
 f=>f.displacement_units='m',
 f=>f.surface_evidence.run_id='3'.repeat(32),
 f=>f.surface_evidence.case_sha256='c'.repeat(64),
 f=>f.surface_evidence.safety_certified=true
]){
 const bad=base();change(bad);
 assert.throws(()=>ctx.setFeaField(bad,sha,caseSha,run,result),Error);
 rejected++;
}
assert.equal(ctx.feaField.displacementEvidence.surfaceMax,.02,'failed update kept verified field');
assert(source.includes('const deform=gfFeaVisualFactor'),'GPU geometry uses display-only multiplier');
assert(source.includes('const multiplier=gfFeaVisualFactor'),'Canvas geometry uses display-only multiplier');
assert(source.includes("scalars=feaContourMode==='displacement'?field.dispmag:field.stress"),'physical mm scalars used in WebGL');
assert(source.includes("r185PreviewDisplacementEvidence=archivedDisplacement"),'archive binds independent A06 displacement evidence');
assert(source.includes("$('feaArchivePreviewMode').onchange=r185Draw"),'preview changes only draw, does not reset yaw/zoom');
assert(source.includes("$('feaContourMode').onchange=e=>"),'mode switching uses existing camera');
console.log('B04: real mm evidence, independent geometric exaggeration, view preservation and '+rejected+' invalid fields passed');
