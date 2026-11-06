'use strict';
// GeoField Stage8: invariants for the existing linked Draft report fixes.
// Static contracts complement dynamic tests for real HTML, R12, 3D and FEA.
// No user files, ML retraining, solver runs, paid APIs or packaging.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const read=name=>fs.readFileSync(path.join(__dirname,'../payload',name),'utf8')
  .replace(/\r\n/g,'\n');
const src=read('frontend/cad.js');
const backend=read('GeoField_CAD_Analysis.py');
const checkBetween=(first,next,needle)=>{
 const a=src.indexOf(first),b=src.indexOf(next,a+first.length);
 assert(a>0&&b>a,'missing source anchors '+first+' → '+next);
 const part=src.slice(a,b);
 assert(part.includes(needle),'source contract '+needle);
 return part;
};
const builder=checkBetween('async function gfBuildVisibleReport(',
 '// GEOFIELD_AI_MESH_FEEDBACK_UI_V1','gfAssertComposedReport(parsed,meshFollowup,false,requireMesh)');
for(const required of [
 'gfFetchMeshFollowup(uid,sha,run,caseSha)',
 'gfReverifiedD6ReportPair(uid,sha,run,caseSha)',
 'gfFetchR12ReportProof(uid,sha,run,caseSha)',
 'gfAppendR12ReportProof(parsed,evidence,r12Proof,uid,sha)',
 'gfAppendFeaReportViews(parsed,evidence,uid,sha,run,caseSha)',
 'gfConsolidateReportNarrative(parsed)',
 'gfAssertComposedReport(parsed,meshFollowup,true,requireMesh)'
]){
 assert.equal(builder.split(required).length-1,1,'no duplicate/missing report step: '+required);
}
assert.equal(builder.split('gfFetchMeshFollowup(uid,sha,run,caseSha)').length-1,1,
 'every HTML assembly must perform only ONE revalidated mesh readback');
assert(!builder.includes('fixLegacyCopy('));
const preview=checkBetween("$('resultsReportBtn').onclick=async()=>{",
 "$('resultsReportSaveBtn').onclick=async()=>{",'gfBuildVisibleReport(uid,sha,run,caseSha,includeAI)');
const save=checkBetween("$('resultsReportSaveBtn').onclick=async()=>{",
 "$('gfMeshFollowupBtn').onclick",'gfBuildVisibleReport(uid,sha,run,caseSha,false,requireMesh)');
const stage3=checkBetween('async function gfStage3CompleteReport(',
 'let gfOneClickPreparing=false;','gfBuildVisibleReport(uid,sha,run,caseSha,false,requireMesh)');
assert(!stage3.includes('await gfFetchMeshFollowup('),
 'Stage3 must not repeat backend mesh status request');
assert(!save.includes('await gfFetchMeshFollowup('),
 'HTML save must not re-fetch an already verified mesh result');
assert(preview.includes('reportAiIncludeToggle'));
assert(save.includes('X-GeoField-Report-Export'));
assert(stage3.includes('gfAssert')===false,
 'single HTML builder must perform common numeric verification');
assert(src.includes("const requiredRows=gfThreeMeshRequiredReportRows(study)"));
assert(src.includes("section.getAttribute('data-gf-mesh-study-id')!==study.id"));
assert(src.includes("const numeric=paragraphs.filter"));
assert(src.includes("return numeric.length===5"));
assert(src.includes("const proof=gfR12ValidatedReportProof(task,expected,uid,sha,run,caseSha)"));
assert(src.includes('R12 내부 면 번호와 CAD 3D 선택 면 ID의 대응도 검증되지 않았습니다'));
assert(src.includes('const data=gfCopyCurrentFeaFramebuffer()'));
assert(src.includes("images.length!==2"));
assert(src.includes('외부 AI 문장은 INP·STA·FRD로 검증된 계산값과 구분되는'));
assert(src.includes('외부 AI 설명 미확인'));
assert(!src.includes("fixLegacyCopy("));
assert(backend.includes('def gf_current_verified_report('));
assert(backend.includes('gf_current_verified_report(uid,as_html=html_requested,include_ai=include_ai)'));
assert(backend.includes('gf_current_verified_report(uid,as_html=True)'));
assert(backend.includes('규칙 근거 정리 완료 · 안전 판정 아님'));
assert(backend.includes("summary['r12_research_status']=r128_r12_status"));
assert(backend.includes("if path.startswith('/api/ml/r12/latest/'):"));
const testPaths=[
 'test_report_single_verified_html_path_ui.js',
 'test_report_ai_narrative_dedup_ui.js',
 'test_fea_report_3d_visual_snapshot_ui.js',
 'test_report_r12_research_evidence_ui.js',
 'test_fea_stage3_auto_unified_report_ui.js',
 'test_mesh_report_restart_binding_ui.js',
 'test_ai_mesh_feedback_ui.js',
 'test_d6_comparison_report_ui.js'
];
for(const filename of testPaths){
 const file=fs.readFileSync(path.join(__dirname,filename),'utf8');
 assert(file.length>1500,'a real regression script must be present: '+filename);
}
console.log('PASS: Stage8 cumulative source links, one-click/preview/save HTML gate, AI OFF/ON, real FRD/mesh/R12 evidence and test-script coverage');
