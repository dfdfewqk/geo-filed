'use strict';
// Stage 6: execute extracted PRODUCTION evidence summaries and A/B comparator.
// Synthetic assertions only: no Windows solver, disk mutation or external AI.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../payload/frontend/index.html'),'utf8');
const slice=(from,to)=>{
 const a=src.indexOf(from),b=src.indexOf(to,a+from.length);
 assert(a>=0&&b>a,'Missing production source anchor '+from);
 return src.slice(a,b);
};
const fns=new Function('$',
 slice('function gfFeaVerificationSummary(','async function loadCurrentResults()')+
 'return gfFeaVerificationSummary;');
const summaryNode={textContent:''},render=fns(id=>id==='feaVerificationSummary'?summaryNode:null);
const report={
 fea_case_provenance:{verified_run_id:'2'.repeat(32),restored_record_active:false}
};
render(report,true);
assert.match(summaryNode.textContent,/3단계 검증 근거 없음/);
assert.doesNotMatch(summaryNode.textContent,/별도 메시 민감도 검토 필요/);
render(report,true,{runs:[1,2,3],steps:[1,2]});
assert.match(summaryNode.textContent,/3단계 메시 민감도.*재검증 완료/);
assert.match(summaryNode.textContent,/수렴 인증 아님/);
assert(src.includes('const verifiedMesh=await gfFetchMeshFollowup('),
 'Only independently fetched mesh evidence upgrades the displayed status');
assert(src.includes('if(!stillLatest())return;\n      gfFeaVerificationSummary(result,true,verifiedMesh);'),
 'Do not display stale async proof');
const present=new Function(
 slice('function gfStage4ComparisonPresent(','async function gfStage4CompareWithPast(')+
 'return gfStage4ComparisonPresent;')();
const SHA='a'.repeat(64),SNAP='3'.repeat(32),PAST='6'.repeat(32),
 RUN='2'.repeat(32),OLD='5'.repeat(32);
const prior={snapshot_id:PAST,run_id:OLD,case_sha256:'c'.repeat(64),cad_sha256:SHA};
const now={snapshot_id:SNAP,run_id:RUN,case_sha256:'b'.repeat(64),cad_sha256:SHA};
const comp={
 status:'verified_read_only_comparison',same_cad:true,same_material:true,
 same_boundary_conditions:false,
 left:{...prior,evidence:'real_solver_files_revalidated',material:'steel',
  max_stress_mpa:10,max_displacement_mm:0.03,force_n:null,
  fixed_faces:[1],load_faces:[2]},
 right:{...now,evidence:'real_solver_files_revalidated',material:'steel',
  max_stress_mpa:14.5,max_displacement_mm:0.035,force_n:49,
  fixed_faces:[1],load_faces:[2]},
 stress_change:{absolute_difference:4.5,percent_vs_left:45},
 displacement_change:{absolute_difference:0.005,percent_vs_left:100*(0.005/0.03)}
};
const valid=present(comp,prior,now);
assert.match(valid,/미기록 → 49\.000 N/);
assert.match(valid,/4\.50000 MPa/);
assert.match(valid,/개선 효과 판단 불가/);
const blocked=(wrong)=>{
 assert.throws(()=>present(wrong,prior,now),/비교|FEA/);
};
blocked({...comp,stress_change:{...comp.stress_change,percent_vs_left:40}});
blocked({...comp,displacement_change:{...comp.displacement_change,absolute_difference:0.005009}});
blocked({...comp,left:{...comp.left,max_stress_mpa:null}});
blocked({...comp,right:{...comp.right,run_id:'f'.repeat(32)}});
blocked({...comp,same_cad:false});
assert(src.includes("if($('gfHistoryComparisonOverview'))$('gfHistoryComparisonOverview').textContent="),
 'Changing past selection must clear stale Results comparison');
assert.equal((html.match(/id="gfHistoryComparisonOverview"/g)||[]).length,1);
assert.equal((html.match(/id="feaVerificationSummary"/g)||[]).length,1);
console.log('PASS: independently verified 3-mesh evidence status, bounded numerical A/B deltas, no fabricated 0 N, stale-view invalidation');
