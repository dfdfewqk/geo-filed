// Fail-closed WebGL provenance checks with the actual production functions.
// Solver values are synthetic fixtures and NEVER described as real FEA output.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const slice=(start,end)=>{
 const a=source.indexOf(start),b=source.indexOf(end,a);
 assert(a>=0 && b>a, 'production function markers are missing');
 return source.slice(a,b);
};
const code=slice('function gfFeaFieldSummaryCheck(', 'function resetFeaField()');
const CAD='a'.repeat(64),CASE='b'.repeat(64),JOB='1'.repeat(32),RUN='2'.repeat(32);
const elements={};
const ctx=vm.createContext({
 app:{mesh:{modelTransform:{center:[0,0,0],size:10}}},
 jobId:JOB,current:{sha256:CAD},feaPreparedCaseSha:CASE,
 feaField:null,feaFieldRunId:null,feaActualLoadMarkers:null,feaContourMode:'none',
 $:id=>(elements[id]??={value:'none',checked:false,disabled:true,textContent:''}),
 clearFeaGL(){},feaStressReference(){},feaStressScaleStatus(){},draw(){}
});
vm.runInContext(code,ctx);
const input=()=>({
 schema:'geofield-fea-surface-field-v1',source:'actual_calculix_ascii_frd',
 cad_sha256:CAD,case_sha256:CASE,cad_job_id:JOB,run_id:RUN,
 positions_mm:[[0,0,0],[1,0,0],[0,1,0]],
 triangles:[[0,1,2]],von_mises_mpa:[1,2,3],
 displacements_mm:[[0,0,0],[0,0,0],[0,0,0]]
});
const results={maximum_nodal_von_mises_mpa:3,maximum_displacement_mm:0};
let checks=0;
function blocked(update, mutateContext){
 const field=input();update(field);
 if(mutateContext)mutateContext();
 assert.throws(()=>ctx.setFeaField(field,CAD,CASE,RUN,results),/실행 ID|활성 CAD|저장 조건|출처|해석 조건/);
 assert.equal(ctx.feaField,null,'a rejected field must not install WebGL state');
 checks++;
}
blocked(f=>{f.run_id='3'.repeat(32);});
blocked(f=>{f.cad_job_id='4'.repeat(32);});
blocked(f=>{f.cad_sha256='e'.repeat(64);});
blocked(f=>{f.case_sha256='e'.repeat(64);});
blocked(()=>{},()=>{ctx.current={sha256:'e'.repeat(64)};});
ctx.current={sha256:CAD};
blocked(()=>{},()=>{ctx.feaPreparedCaseSha='e'.repeat(64);});
ctx.feaPreparedCaseSha=CASE;
const good=input();
ctx.setFeaField(good,CAD,CASE,RUN,results);
assert.equal(ctx.feaFieldRunId,RUN);
assert.equal(ctx.feaField.cadSha,CAD);
assert.equal(ctx.feaField.maxStress,3);
assert.deepEqual(Array.from(ctx.feaField.stress),[1,2,3]);
checks++;
console.log('PASS: '+checks+' verified field identity / WebGL numeric preservation cases');
