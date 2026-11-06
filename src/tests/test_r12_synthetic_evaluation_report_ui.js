'use strict';
// Test the PRODUCTION source-verified synthetic R12 evaluation validator.
// Not a user STEP accuracy claim; no model, solver, paid provider or disk writes.
const assert=require('node:assert/strict'),fs=require('node:fs'),
 path=require('node:path'),vm=require('node:vm');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const start=src.indexOf('function gfR12SyntheticEvaluationProof(');
const end=src.indexOf('async function gfFetchR12ReportProof(',start);
assert(start>0&&end>start,'production holdout validator must exist');
const sha='a'.repeat(64),uid='1'.repeat(32),r12='3'.repeat(32);
const model='df51d702ee77fb9efdc2de730f679f62d18e652c9d6279736e4deef353535dd0';
const labels=['no_hole','through_hole','blind_hole','unverified'];
const matric=(parts,wrong=0)=>{
 const n=parts/3;
 return [[n,0,0,0],[0,n-wrong,0,wrong],[0,0,n,0],[0,0,0,0]];
};
const split=(parts,wrong,families)=>{
 const matrix=matric(parts,wrong),aided=matric(parts,0);
 return {parts,correct:parts-wrong,topology_assisted_correct:parts,
  accuracy:(parts-wrong)/parts,topology_assisted_accuracy:1,
  families,confusion_labels:labels,confusion_matrix:matrix,
  topology_assisted_confusion_matrix:aided};
};
const sample=()=>({schema:'geofield-r12-synthetic-holdout-source-recomputed-v1',
 status:'source_recomputed_synthetic_family_holdout_only',
 model_sha256:model,cad_job_id:uid,cad_sha256:sha,r12_run_id:r12,
 split_policy:'by_geometry_family',independent_real_cad_accuracy_verified:false,
 production_eligible:false,
 training:split(54,1,['plate','rounded_plate','notched_plate']),
 validation:split(18,0,['raised_edge']),
 test:split(36,1,['l_support','chamfer_plate'])});
const ctx={Number,Math,Array,String,Set,Error,Promise,encodeURIComponent};
vm.createContext(ctx);vm.runInContext(src.slice(start,end),ctx);
const valid=ctx.gfR12SyntheticEvaluationProof(sample(),uid,sha,r12);
assert(valid&&valid.test.correct===35&&valid.test.parts===36);
assert.equal(valid.test.topology_assisted_correct,36);
const wrong=[
 ['model hash',d=>d.model_sha256='f'.repeat(64)],
 ['run ID',d=>d.r12_run_id='8'.repeat(32)],
 ['cad',d=>d.cad_sha256='b'.repeat(64)],
 ['faked accuracy',d=>d.test.accuracy=1],
 ['faked confusion',d=>d.test.confusion_matrix[1][3]=0],
 ['overlapping splits',d=>d.test.families[0]='plate'],
 ['unsupported real-CAD claim',d=>d.independent_real_cad_accuracy_verified=true],
 ['production claim',d=>d.production_eligible=true],
 ['faked correct count',d=>d.test.correct=36],
 ['invented sample',d=>d.test.parts=37]
];
for(const [name,mutate] of wrong){
 const d=sample();mutate(d);
 assert.equal(ctx.gfR12SyntheticEvaluationProof(d,uid,sha,r12),null,name);
}
assert(src.includes("quality.id='geofield-r12-synthetic-holdout-evidence'"));
assert(src.includes('R12 학습·검증 시험 근거'));
assert(src.includes('합성 형상 연구 평가이며 이번 실제 STEP 정확도'));
console.log('PASS: source-recomputed R12 synthetic family holdout is displayed in Results/HTML only with consistent model/run/SHA and raw confusion counts');
