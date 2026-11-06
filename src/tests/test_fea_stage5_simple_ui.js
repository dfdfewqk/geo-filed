'use strict';
// Stage 5: visible one-click UI vs. preserved advanced diagnostics.
// Static production-file checks; never open a user's STEP, solver or paid API.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../payload/frontend/index.html'),'utf8');
const js=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const once=id=>assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id+' unique');
const order=(...terms)=>{const indexes=terms.map(x=>html.indexOf(x));assert(indexes.every(x=>x>=0));assert(indexes.every((x,i)=>i===0||x>indexes[i-1]),terms.join(' -> '));};
for(const id of [
 'stepFile','importBtn','feaMaterialPreset','feaSetFixed','feaSetLoad','feaLoadQuantity',
 'feaDirectionMode','feaRunBtn','feaStressValue','feaDispValue','resultsReportBtn',
 'resultsReportSaveBtn','reportAiIncludeToggle','agentResult','gfAutoUnifiedStatus',
 'feaArchivedSelect','feaQuickComparePanel','feaQuickCompareOutput',
 'gfHistoryComparisonOverview','gfOptionalManualAgent','gfOptionalDesignExperiment',
 'gfOptionalDetailedAutoProgress','feaOptionalManualCompare','feaOptionalArchiveProof',
 'feaOptionalArchiveSort','feaOptionalPeakControls','feaOptionalManualResultLink'
])once(id);
assert.equal((html.match(/data-tab="/g)||[]).length,4);
assert.equal((html.match(/data-pane="/g)||[]).length,4);
order('id="stepFile"','id="importBtn"','data-pane="fea"','id="feaRunBtn"',
      'data-pane="integration"','id="resultsReportBtn"','data-pane="records"',
      'id="feaArchivedSelect"');
order('id="reportAiIncludeToggle"','id="resultsReportBtn"',
      'id="gfOptionalManualAgent"','id="agentLLMOptIn"',
      'id="agentRunBtn"','id="agentResult"');
order('id="gfOptionalDesignExperiment"','id="gfD6VariantBtn"',
      'id="resultsReportSaveBtn"');
order('id="feaOptionalArchiveSort"','id="feaArchiveSort"',
      'id="feaArchivedSelect"');
order('id="feaOptionalManualCompare"','id="feaQuickCompareBtn"',
      'id="feaQuickCompareOutput"');
for(const id of [
 'gfOptionalManualAgent','gfOptionalDesignExperiment','gfOptionalDetailedAutoProgress',
 'feaOptionalManualCompare','feaOptionalArchiveSort','feaOptionalArchiveProof',
 'feaOptionalPeakControls','feaOptionalManualResultLink'
])assert(!html.includes('id="'+id+'" open'),id+' must start closed');
assert(html.includes('외부 AI 설명 추가 (선택)'));
assert(html.includes('과거 FEA 기록을 하나 선택하면 현재 분석과 자동 비교합니다'));
for(const handler of ["$('feaRunBtn').onclick","$('feaPrepareBtn').onclick",
 "$('resultsReportBtn').onclick","$('agentRunBtn').onclick",
 "$('feaArchivedRestoreBtn').onclick","$('feaQuickCompareBtn').onclick",
 "feaArchiveSelector.onchange","gfAutoStage2Verification(","gfStage3CompleteReport(",
 "gfStage4CompareWithPast()"])assert(js.includes(handler),'preserved '+handler);
assert(js.includes("const externalOptIn=!automaticLocal&&$('agentLLMOptIn')?.checked===true;"));
assert(js.includes('await gfBuildVisibleReport(uid,sha,run,caseSha,false,requireMesh)'),
 'one-click uses the same verified HTML builder with mandatory 3-mesh flag');
assert(js.includes("await gfStage4CompareWithPast();"));
console.log('PASS: Stage 5 compact main controls, advanced feature preservation, one-click handoff and paid-AI opt-in safety');
