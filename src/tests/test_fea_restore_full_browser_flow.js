"use strict";
// Use the actual production archived-restore handler with a simulated fresh
// browser and API answers. No fake FEA value is claimed as a real CCX result.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const modeStart=source.indexOf('function gfRestoreVerifiedElementMode(');
const modeEnd=source.indexOf('// GeoField R18.4 independently verified numerical FEA history view',modeStart);
const restoreStart=source.indexOf('async function restoreArchivedFea(');
const restoreEnd=source.indexOf('let feaArchiveItems=',restoreStart);
assert(modeStart>0 && modeEnd>modeStart && restoreStart>0 && restoreEnd>restoreStart);
const program=source.slice(modeStart,modeEnd)+'\n'+source.slice(restoreStart,restoreEnd)+'\nthis.run=restoreArchivedFea;';
const CAD='a'.repeat(64),CASE='b'.repeat(64),RUN='c'.repeat(32),JOB='d'.repeat(32),ITEM='e'.repeat(32);
function fixture(mode='c3d10_full',badPreview=false){
 const actual=mode==='c3d4'?'C3D4':'C3D10';
 const traction=mode==='c3d10_full'?'straight_tri6_full_consistent':'free_node_moment_equivalent';
 const saved={cad_sha256:CAD,case_sha256:CASE,material:{name:'SUS304'},
    preset_metadata:{material_key:'sus304',mass_kg:10},
    mesh_request:{element_type:actual,traction_model:traction},
    boundary_conditions:{fixed_face_ids:[3],load_face_ids:[1],total_force_n:98.0665,force_direction_unit:[1,0,0]},
    self_weight_reference:{applied_to_solver:false}};
 const field={schema:'geofield-fea-surface-field-v1',source:'actual_calculix_ascii_frd',
    cad_sha256:CAD,case_sha256:CASE,positions_mm:[[0,0,0],[1,0,0],[0,1,0]],
    von_mises_mpa:[1,2,3],displacements_mm:[[0,0,0],[.1,0,0],[0,.2,0]],triangles:[[0,1,2]]};
 const mesh={positions:[[0,0,0],[1,0,0],[0,1,0]],triangles:[[0,1,2]],face_ids:[1,3]};
 const result={cad_sha256:CAD,case_sha256:CASE,mesh:{element_type:actual,traction_model:traction,
       node_count:3,tetrahedron_count:1},
    results:{maximum_nodal_von_mises_mpa:3,maximum_displacement_mm:.2},
    field_visualization:{available:true},load_equilibrium_audit:{}};
 const task={status:'complete',result};
 const bundle={cad_job_id:JOB,run_id:RUN,cad_sha256:CAD,case_sha256:CASE,
    job:{sha256:CAD,analysis:{sha256:CAD,source:'L_bracket.step'},findings:[]},
    model:{sha256:CAD,mesh},case:saved,task,has_3d_field:true,field};
 const preview=structuredClone(bundle);
 if(badPreview)preview.task.result.mesh.traction_model='free_node_moment_equivalent';
 const record={id:ITEM,job_id:JOB,cad_sha256:CAD};
 const snapshot={cad:{sha256:CAD},fea:{state:'complete',result_run_id:RUN,
      result_case_sha256:CASE,setup:{material:'SUS304',external_mass_kg:10,
      fixed_faces:[3],load_faces:[1]}}};
 const controls={};
 function elt(id){
   if(!controls[id])controls[id]={id,value:'',textContent:'',disabled:false,checked:false,
     classList:{add(){}},selectedOptions:[{textContent:'SUS304'}]};
   return controls[id];
 }
 elt('feaLoadMode').value='mass_kg';
 elt('feaLoadQuantity').value='10';
 elt('feaMaterialPreset').selectedOptions=[{textContent:'SUS304'}];
 elt('feaElementMode').value='c3d4'; // Deliberate old browser setting
 elt('feaOwnWeight').checked=true; // Deliberately stale before restore
 const calls={post:[],get:[],status:[],field:[],table:[],view:0,agent:0,reset:0};
 elt('agentRunBtn').onclick=()=>{calls.agent++;};
 const env={
  console, Promise, Math, Error, String, Number, Object, Array, Set,
  file:{name:'stale.step'},current:null,jobId:null,findings:[],
  gfRestoredRunId:null,feaRunId:null,feaPrepared:false,feaPreparedCaseSha:null,
  feaFixed:[],feaLoaded:[],stepSelectionVersion:1,feaRestoreGeneration:0,cadImportGeneration:0,
  $:elt,
  window:{confirm:()=>true},
  get:async(url)=>{
   calls.get.push(url);
   if(url.startsWith('/api/history/item/'))return structuredClone(snapshot);
   if(url.startsWith('/api/fea/restore_preview/'))return structuredClone(preview);
   if(url==='/api/status')return {current:{job_id:null}};
   throw Error('Unplanned GET '+url);
  },
  post:async(url)=>{
   calls.post.push(url);
   if(url.startsWith('/api/fea/recover_bundle/'))return structuredClone(bundle);
   throw Error('Unplanned POST '+url);
  },
  status:(...args)=>{calls.status.push(args);},
  resetModel:(opts)=>{assert.equal(opts.preserveRestore,true);calls.reset++;},
  loadMesh:()=>{calls.view++;},renderInfo:()=>{},renderFindings:()=>{},
  refreshLoadLegend:()=>{},refreshSelected:()=>{},tabTo:()=>{},
  loadCurrentResults:async()=>{},
  setFeaField:(...a)=>{calls.field.push(a);},
  gfFeaTableShow:(...a)=>{calls.table.push(a);}
 };
 vm.createContext(env);vm.runInContext(program,env);
 return {env,controls,calls,record,trigger:{disabled:false}};
}
(async()=>{
 for(const mode of ['c3d4','c3d10','c3d10_full']){
  const t=fixture(mode);
  await t.env.run(t.record,t.trigger);
  assert.equal(t.calls.post.length,1,'one authenticated existing restore; route trace='+JSON.stringify({statuses:t.calls.status,get:t.calls.get,mode}));
  assert.equal(t.calls.reset,1,'one UI reset after all evidence checks');
  assert.equal(t.calls.field.length,1,'validated FRD 3D field reused');
  assert.equal(t.calls.table.length,1,'restored solver type shown in result table');
  assert.equal(t.calls.table[0][t.calls.table[0].length-1].element_type,
               mode==='c3d4'?'C3D4':'C3D10');
  assert.equal(t.controls.feaElementMode.value,mode);
  assert.equal(t.controls.feaOwnWeight.checked,false);
  assert.equal(t.env.gfRestoredRunId,RUN);
  assert.equal(t.env.feaPreparedCaseSha,CASE);
  assert.equal(t.env.file,null,'restore does not claim original STEP is available');
  assert.equal(t.controls.feaRunBtn.disabled,true,'new FEA not permitted without original STEP');
  assert.equal(t.calls.agent,1,'restored rule-agent refreshed with existing handler');
  assert.equal(t.trigger.disabled,false);
 }
 const mismatch=fixture('c3d10_full',true);
 await mismatch.env.run(mismatch.record,mismatch.trigger);
 assert.equal(mismatch.calls.post.length,0,'mismatched preview must be rejected before server mutation');
 assert.equal(mismatch.calls.reset,0,'bad historical result cannot replace live browser view');
 assert.equal(mismatch.calls.field.length,0);
 assert.match(mismatch.calls.status.map(x=>x.join(' ')).join(' '),/복원 실패/);
 console.log('PASS: simulated fresh browser restores C3D4/C3D10/Full Tri6 with FRD/agent; preflight refuses invalid history before POST');
})().catch(e=>{console.error(e);process.exitCode=1;});
