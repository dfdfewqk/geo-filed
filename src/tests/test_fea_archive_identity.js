// Actual production FEA-history response identity validator, no solver or DB.
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const begin=source.indexOf('function gfArchivedNumbersIdentityCheck(');
const end=source.indexOf('feaArchiveSelector.onchange=',begin);
assert(begin>=0&&end>begin,'Production archive identity validator missing');
assert(source.includes('gfArchivedNumbersIdentityCheck(verified,choice,item);'),
       'Archive response UI must call the validated gate before displaying results.');
const ctx=vm.createContext({Error,Number,String});
vm.runInContext(source.slice(begin,end),ctx);
const id='1'.repeat(32),job='2'.repeat(32),cad='a'.repeat(64),run='3'.repeat(32),caseSha='b'.repeat(64);
const item=()=>({id,job_id:job,cad_sha256:cad,result_run_id:run,result_case_sha256:caseSha});
const result=()=>({
 ok:true,read_only:true,current_session_unchanged:true,
 verification:'rechecked_actual_inp_sta_frd',snapshot_id:id,
 cad_job_id:job,cad_sha256:cad,run_id:run,case_sha256:caseSha,
 maximum_von_mises_mpa:14.5,maximum_displacement_mm:0.057,
 mesh:{nodes:2798,tetrahedra:8611},three_d_field_verified:true
});
let tests=0;
assert.equal(ctx.gfArchivedNumbersIdentityCheck(result(),id,item()),true);tests++;
function reject(mutator,itemMutator){
 const r=result(),it=item();
 mutator?.(r);
 itemMutator?.(it);
 assert.throws(()=>ctx.gfArchivedNumbersIdentityCheck(r,id,it),
               /식별자|실행 ID|조건 SHA|수치|노드/);
 tests++;
}
reject(r=>r.run_id='4'.repeat(32));
reject(r=>r.cad_job_id='4'.repeat(32));
reject(r=>r.cad_sha256='c'.repeat(64));
reject(r=>r.case_sha256='c'.repeat(64));
reject(r=>r.verification='unverified');
reject(r=>r.current_session_unchanged=false);
reject(r=>r.read_only=false);
reject(r=>r.snapshot_id='9'.repeat(32));
reject(r=>r.maximum_von_mises_mpa=NaN);
reject(r=>r.maximum_displacement_mm=-1);
reject(r=>r.mesh.nodes=0);
reject(r=>r.mesh.tetrahedra=null);
reject(()=>{},i=>i.result_run_id='4'.repeat(32));
reject(()=>{},i=>i.result_case_sha256='c'.repeat(64));
const legacy=item();delete legacy.result_run_id;delete legacy.result_case_sha256;
assert.equal(ctx.gfArchivedNumbersIdentityCheck(result(),id,legacy),true);tests++;
console.log('PASS: '+tests+' verified historical FEA CAD/case/run/mesh identity checks');
