// Historical element label regression: pure production JS, no private runtime.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const start=source.indexOf('function gfRestoreVerifiedElementMode(');
const end=source.indexOf('// GeoField R18.4 independently verified numerical FEA history view',start);
assert(start>0&&end>start,'production C3D10 archive mode validator missing');
const isolated=vm.createContext({});
vm.runInContext(source.slice(start,end)+'\nthis.pick=gfRestoreVerifiedElementMode;',isolated);
let count=0;
const pick=(request,mesh,self_weight_reference)=>
 isolated.pick({mesh_request:request,self_weight_reference},{mesh});
function ok(req,mesh,expected,weight){
 const out=pick(req,mesh,{applied_to_solver:weight});
 assert.equal(out.mode,expected);
 assert.equal(out.ownWeight,weight);
 count++;
}
function block(req,mesh,pattern,weight=false){
 assert.throws(()=>pick(req,mesh,{applied_to_solver:weight}),pattern);
 count++;
}
// Old C3D4 archived cases without new metadata are still readable.
ok({}, {}, 'c3d4',false);
ok({element_type:'C3D4'}, {element_type:'C3D4'}, 'c3d4',true);
ok({element_type:'C3D10'}, {element_type:'C3D10',traction_model:'free_node_moment_equivalent'},'c3d10',false);
ok({element_type:'C3D10',traction_model:'straight_tri6_full_consistent'},
   {element_type:'C3D10',traction_model:'straight_tri6_full_consistent'},'c3d10_full',false);
block({element_type:'C3D10'}, {}, /메시 요소 증거/);
block({element_type:'C3D4'}, {element_type:'C3D10'}, /메시 요소.*일치/);
block({element_type:'C3D10',traction_model:'straight_tri6_full_consistent'},
      {element_type:'C3D10'}, /하중 방식.*근거/);
block({element_type:'C3D10',traction_model:'straight_tri6_full_consistent'},
      {element_type:'C3D10',traction_model:'free_node_moment_equivalent'}, /하중 방식.*일치/);
block({element_type:'C3D4',traction_model:'straight_tri6_full_consistent'},
      {element_type:'C3D4'}, /요소와 하중/);
block({element_type:'C3D10',traction_model:'straight_tri6_full_consistent'},
      {element_type:'C3D10',traction_model:'straight_tri6_full_consistent'}, /자중/,true);
block({element_type:'HEX8'},{element_type:'HEX8'},/요소 종류/);
block({element_type:'C3D10',traction_model:'unsupported'},
      {element_type:'C3D10'}, /하중 방식/);
// Restore must run the integrity check before the current CAD is reset.
const restore=source.slice(source.indexOf('async function restoreArchivedFea('),
                           source.indexOf('let feaArchiveItems=',source.indexOf('async function restoreArchivedFea(')));
assert(restore.indexOf('gfRestoreVerifiedElementMode(saved,task.result)')>=0);
assert(restore.indexOf('gfRestoreVerifiedElementMode(saved,task.result)')<restore.indexOf('resetModel({preserveRestore:true})'));
assert(restore.includes("$('feaElementMode').value=restoredMode.mode"));
assert(restore.includes("$('feaOwnWeight').checked=restoredMode.ownWeight"));
assert(restore.includes("gfFeaTableShow('저장된 FEA · 실제 CalculiX 복원 결과"));
console.log('PASS: '+count+' C3D4/C3D10 historical element/traction guards + form/table restoring');
