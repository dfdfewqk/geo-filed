'use strict';
// Exercise the PRODUCTION Stage-4 auto-compare functions with synthetic responses.
// No local STEP, solver, SQLite mutation, Windows install, or paid AI call.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../payload/frontend/index.html'),'utf8');
const start=src.indexOf('// GEOFIELD_STAGE4_QUICK_ARCHIVE_COMPARISON_20261105');
const end=src.indexOf('feaArchiveSelector.onchange=async()=>',start);
assert(start>0&&end>start);
const code=src.slice(start,end);
assert(!code.includes("method:'POST'"));
for(const id of ['feaQuickComparePanel','feaQuickCompareBtn','feaQuickCompareArchiveStatus',
 'feaQuickCompareOutput','gfHistoryComparisonOverview'])
 assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1);
const SHA='a'.repeat(64),BAD='f'.repeat(64),CASE='b'.repeat(64),OLDCASE='c'.repeat(64),
 JOB='1'.repeat(32),OLDJOB='4'.repeat(32),RUN='2'.repeat(32),OLDRUN='5'.repeat(32),
 CURRENTID='3'.repeat(32),PAST='6'.repeat(32);
const prior={ok:true,read_only:true,current_session_unchanged:true,
 verification:'rechecked_actual_inp_sta_frd',snapshot_id:PAST,cad_job_id:OLDJOB,
 cad_sha256:SHA,run_id:OLDRUN,case_sha256:OLDCASE};
const binding={ok:true,status:'verified_current_fea_snapshot',verification:'rechecked_actual_inp_sta_frd',
 archive_saved:true,read_only:true,snapshot_id:CURRENTID,run_id:RUN,cad_job_id:JOB,
 cad_sha256:SHA,case_sha256:CASE};
const comparison={status:'verified_read_only_comparison',same_cad:true,same_material:true,
 same_boundary_conditions:true,left:{snapshot_id:PAST,run_id:OLDRUN,cad_sha256:SHA,case_sha256:OLDCASE,
 evidence:'real_solver_files_revalidated',max_stress_mpa:10,max_displacement_mm:.03,
 material:'steel',force_n:49,fixed_faces:[1],load_faces:[4]},
 right:{snapshot_id:CURRENTID,run_id:RUN,cad_sha256:SHA,case_sha256:CASE,
 evidence:'real_solver_files_revalidated',max_stress_mpa:14.5,max_displacement_mm:.035,
 material:'steel',force_n:49,fixed_faces:[1],load_faces:[4]},
 stress_change:{absolute_difference:4.5,percent_vs_left:45},
 displacement_change:{absolute_difference:.005,percent_vs_left:16.66666},
 agent_review:{schema:'geofield-agent-fea-comparison-v1',status:'same_cad_verified_runs_descriptive_comparison',
 causal_effect_verified:false,structural_safety_verified:false,mesh_convergence_verified:false,
 left_run_id:OLDRUN,right_run_id:RUN,changes:['mesh']}};
function make({selected=true,selectedSHA=SHA,current=true,bindingReply=binding,compareReply=comparison,
               getPrior=false,changeSelectionOnBinding=false}={}){
 const nodes={},requests=[],selection={value:selected?PAST:''};
 const $=id=>nodes[id]??(nodes[id]={textContent:'',disabled:false});
 const ctx={console,Math,Number,String,Error,Promise,URLSearchParams,encodeURIComponent,
   jobId:JOB,current:{sha256:SHA},feaRunId:current?RUN:null,meshSeriesBusy:false,
   latestSummary:{fea_case_provenance:{verified_run_id:RUN,solved_case_sha256:CASE}},
   feaArchiveSelector:selection,
   feaArchiveItems:selected?[{id:PAST,job_id:OLDJOB,cad_sha256:selectedSHA}]:[],
   feaArchiveVerified:getPrior?null:prior,
   $,
   gfReportReady:()=>true,
   gfArchivedNumbersIdentityCheck:(v,id,item)=>{
    assert.equal(v.snapshot_id,id);assert.equal(v.cad_sha256,item.cad_sha256);
   },
   get:async url=>{
     requests.push(String(url));
     if(String(url).includes('/api/fea/current-snapshot/')){
       if(changeSelectionOnBinding)selection.value='';return bindingReply;
     }
     if(String(url).includes('/api/fea/verified_archive_numbers/'))return prior;
     if(String(url).includes('/api/history/fea-compare?'))return compareReply;
     throw Error('Unexpected endpoint: '+url);
   }
 };
 vm.createContext(ctx);vm.runInContext(code,ctx);
 return{ctx,nodes,requests,selection,run:()=>ctx.gfStage4CompareWithPast()};
}
(async()=>{
 const good=make();assert.equal(await good.run(),true);
 assert.equal(good.requests.length,2);
 assert(good.requests[0].includes('current-snapshot'));
 assert(good.requests[1].includes('fea-compare'));
 assert.match(good.nodes.feaQuickCompareOutput.textContent,/4\.50000 MPa/);
 assert.match(good.nodes.feaQuickCompareOutput.textContent,/규칙 기반 조건 차이/);
 assert.equal(good.nodes.gfHistoryComparisonOverview.textContent,
   good.nodes.feaQuickCompareOutput.textContent);
 assert.match(good.nodes.feaQuickCompareArchiveStatus.textContent,/SQLite에 자동 보관됨/);
 assert.equal(good.nodes.feaQuickCompareBtn.disabled,false);
 const notSelected=make({selected:false});assert.equal(await notSelected.run(),true);
 assert.equal(notSelected.requests.length,1);
 const same=make({bindingReply:{...binding,snapshot_id:PAST}});
 assert.equal(await same.run(),false);assert.equal(same.requests.length,1);
 const cross=make({selectedSHA:BAD});assert.equal(await cross.run(),false);
 assert.match(cross.nodes.feaQuickCompareOutput.textContent,/형상이 다릅니다/);
 assert.equal(cross.requests.length,1);
 const corrupt=make({compareReply:{...comparison,stress_change:{absolute_difference:-200}}});
 assert.equal(await corrupt.run(),false);
 assert.match(corrupt.nodes.feaQuickCompareOutput.textContent,/근거|변화량/);
 const noCurrent=make({current:false});assert.equal(await noCurrent.run(),false);
 assert.equal(noCurrent.requests.length,0);
 const stale=make({changeSelectionOnBinding:true});
 assert.equal(await stale.run(),false);assert.equal(stale.requests.length,1);
 const noProof=make({getPrior:true});assert.equal(await noProof.run(),true);
 assert.equal(noProof.requests.length,3);
 console.log('PASS: one-record-select read-only verified A/B comparison, no data rewrite or paid API, identity & stale protection');
})().catch(e=>{console.error(e);process.exitCode=1});
