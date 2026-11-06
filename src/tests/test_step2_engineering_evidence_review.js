'use strict';
// Step 2: real production scientific review (synthetic measurements only).
// No CAD, solver, SQLite/model, external provider or physical safety verdict.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),
 assert=require('node:assert/strict');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const start=src.indexOf('function gfEngineeringStage2Review(');
const end=src.indexOf('function gfEvidenceChecklistLines(',start);
assert(start>=0&&end>start);
const review=new Function(src.slice(start,end)+'return gfEngineeringStage2Review;')();
const sample={
 id:'d'.repeat(32),
 runs:[{mesh:2.7,stress:12,disp:.025},{mesh:1.8,stress:13,disp:.027},
       {mesh:1.1,stress:12.8,disp:.0275}],
 steps:[{stress:100/13,disp:100*(.027-.025)/.027},
        {stress:100*(13-12.8)/12.8,disp:100*(.0275-.027)/.0275}],
 actualMeshRefined:true,loadComparable:true,numericStable:false,
 spatial:{peaks:[
  {position:[0,0,0],stress:12},
  {position:[3,4,0],stress:13},
  {position:[3,4,2],stress:12.8}
 ],moves:[5,2]}
};
const diagnostic=review(sample).join('\n');
assert.match(diagnostic,/방향 전환\(비단조\)/);
assert.match(diagnostic,/기존 5% 수치 민감도 선별기준 미충족/);
assert.match(diagnostic,/미세 메시 목표 크기보다 큰 좌표 이동/);
assert.match(diagnostic,/원인 귀속 불가/);
assert.match(diagnostic,/항복강도\/허용응력이 아닙니다/);
assert.match(diagnostic,/안전율 계산·합격 판정 보류/);
assert.match(diagnostic,/독립 정답 라벨/);
assert.doesNotMatch(diagnostic,/안전율 [0-9]|응력 집중 원인 확인|수렴 인증 완료/);
const noStudy=review(null).join('\n');
assert.match(noStudy,/독립 재검증된 3회 메시 자료가 없어 추세 판단 보류/);
const stable=review({...sample,
 runs:[{mesh:3,stress:10,disp:0.03},{mesh:2,stress:10.2,disp:0.0302},
       {mesh:1,stress:10.3,disp:0.0303}],
 steps:[{stress:2,disp:.667},{stress:.98,disp:.331}],
 spatial:null,numericStable:true}).join('\n');
assert.match(stable,/5% 수치 민감도 선별기준 충족 \(수렴 인증 아님\)/);
assert.match(stable,/FRD 표면 최고응력 위치 이동: 이번 실행의 검증된 공간 좌표 근거 부족/);
const changedLoad=review({...sample,numericStable:true,
 steps:[{stress:1,disp:1},{stress:1,disp:1}],
 loadComparable:false}).join('\n');
assert.match(changedLoad,/하중·모멘트 비교 조건 불충족/);
assert.doesNotMatch(changedLoad,/기존 5% 수치 민감도 선별기준 충족/);
assert(src.includes('gfEngineeringStage2Review(meshFollowup)'),
 'Integrated HTML must include read-only scientific review');
assert(src.includes('...gfEngineeringStage2Review(meshVerified?meshProof:null)'),
 'Main Results checklist must include only run-bound trusted mesh diagnostics');
// The original case and three solver files have already been independently
// rechecked by the server before their numbers may enter this frontend.
const fetchStart=src.indexOf('async function gfFetchMeshFollowup(');
const fetchEnd=src.indexOf('// Stage 6: a fully reverified',fetchStart);
assert(fetchStart>=0&&fetchEnd>fetchStart);
const code=src.slice(fetchStart,fetchEnd);
const UID='1'.repeat(32),SHA='a'.repeat(64),RUN='2'.repeat(32),CASE='b'.repeat(64),SID='3'.repeat(32);
const analysis={
 status:'verified_three_mesh_sensitivity_only',same_physical_case:true,
 solver_evidence:'each_calculix_run_revalidated',convergence_certified:false,
 safety_certified:false,
 runs_coarse_to_fine:sample.runs.map(x=>({
  cad_sha256:SHA,mesh_target_mm:x.mesh,max_stress_mpa:x.stress,
  max_displacement_mm:x.disp
 })),
 adjacent_changes:sample.steps.map(x=>({stress_relative_change_percent:x.stress,
  displacement_relative_change_percent:x.disp})),
 actual_mesh_resolution_diagnostic:{effective_mean_edge_refinement:true},
 actual_load_moment_diagnostic:{mesh_only_attribution_supported_by_this_screen:true},
 numeric_stability_diagnostic:{passes:false},
 spatial_peak_diagnostic:{
  status:'verified_surface_peak_positions_only',peak_positions_verified:true,
  source:'three_separately_reverified_calculix_frd_surface_fields',
  runs_coarse_to_fine:sample.spatial.peaks.map(x=>({
   surface_peak_position_mm:x.position,surface_max_stress_mpa:x.stress
  })),adjacent_peak_distances_mm:[5,2]
 }
};
async function fetchStudy({withDrift=false,wrongDelta=false,busy=false,impossiblePeak=false}={}){
 const state={id:SID,cad_job_id:UID,cad_sha256:SHA,status:'complete',
  mesh_study_verified:true,
  study_analysis:{...analysis,
   adjacent_changes:analysis.adjacent_changes.map((x,i)=>wrongDelta&&i===0?{
    ...x,stress_relative_change_percent:0.1}:x),
   spatial_peak_diagnostic:{
   ...analysis.spatial_peak_diagnostic,
   runs_coarse_to_fine:analysis.spatial_peak_diagnostic.runs_coarse_to_fine.map((row,i)=>
    impossiblePeak&&i===0?{...row,surface_max_stress_mpa:100}:row),
   adjacent_peak_distances_mm:withDrift?[5,99]:[5,2]
  }}};
 const scope={Number,String,Math,Promise,meshSeriesBusy:busy,
  gfMeshFollowupSelection:()=>({id:SID,jobId:UID,cadSha:SHA,runId:RUN,caseSha:CASE}),
  gfReportSelectionCurrent:()=>true,get:async()=>state,
  // This scientific trend test does not write browser storage. Assert only
  // the exact reverified run is offered to the real persistence boundary.
  gfRememberVerifiedMeshFollowup:link=>{
   assert.equal(link.id,SID,'only the verified study may be stored');
   assert.equal(link.jobId,UID);
   assert.equal(link.cadSha,SHA);
   assert.equal(link.runId,RUN);
   assert.equal(link.caseSha,CASE);
  }};
 vm.createContext(scope);
 vm.runInContext(code,scope);
 return scope.gfFetchMeshFollowup(UID,SHA,RUN,CASE);
}
(async()=>{
 const completedAfterTimeout=await fetchStudy({busy:true});
 assert.equal(completedAfterTimeout?.runs?.length,3,
  'a stale browser busy flag must not discard three independently reverified solver archives');
 const trusted=await fetchStudy();assert(trusted?.spatial);
 assert.equal(trusted.spatial.moves[1],2);
 const inconsistent=await fetchStudy({withDrift:true});
 assert(inconsistent&&inconsistent.spatial===null,
  'Inconsistent FRD peak-distance claim must be omitted, not echoed');
 assert.equal(inconsistent.runs.length,3,
  'Rejecting one spatial claim must preserve independently verified base FEA data');
 const impossible=await fetchStudy({impossiblePeak:true});
 assert(impossible&&impossible.spatial===null,
  'Surface peak larger than that run\'s full FRD nodal maximum must be omitted');
 assert.equal(impossible.runs.length,3,
  'Inconsistent hotspot claim must not destroy independently reverified 3-mesh numeric rows');
 const falseStability=await fetchStudy({wrongDelta:true});
 assert.equal(falseStability,null,
  'Reported 5% stability percentages must match reverified solver maxima');
 console.log('PASS: conservative three-mesh sensitivity/trend diagnostics, no forged yield/ML confidence, FRD peak-distance cross-check');
})().catch(e=>{console.error(e);process.exitCode=1});
