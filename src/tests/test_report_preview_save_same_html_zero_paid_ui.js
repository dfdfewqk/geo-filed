'use strict';
// Run the actual Preview / Save button handlers against one frozen, validated
// report string. This is a UI flow test, not a claim about real Windows WebGL.
// No solver, ML, SQLite writes, archive replacement, or external paid tokens.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const start=source.indexOf("$('resultsReportBtn').onclick=async()=>{");
const end=source.indexOf("$('gfMeshFollowupBtn').onclick",start);
assert(start>0&&end>start,'native Preview/Save handlers required');
const html='<!doctype html><html lang="ko"><body><section id="geofield-a08-evidence">'+
 '실제 FEA 14.758 MPa / 0.0264 mm</section>'+
 '<section id="geofield-ai-mesh-followup-report">3개 메시 솔버 결과</section></body></html>';
const UID='1'.repeat(32),SHA='a'.repeat(64),RUN='2'.repeat(32),
 CASE='b'.repeat(64),STUDY='3'.repeat(32);
function make({badBuilder=false,changeCadDuringBuild=false,meshBusy=false,
               includeAI=false,baseArchiveOk=true}={}){
 const seen={builder:[],fetch:[],links:[],blobs:[],tabs:[],confirm:0};
 const nodes={
  resultsReportBtn:{disabled:false},
  resultsReportSaveBtn:{disabled:false},
  resultsReportStatus:{textContent:''},
  resultsReportSavedPath:{textContent:''},
  reportAiIncludeToggle:{checked:includeAI}};
 const ctx={
  String,Boolean,Error,Number,Promise,Date,encodeURIComponent,setTimeout:()=>0,
  jobId:UID,current:{sha256:SHA},meshSeriesBusy:meshBusy,
  latestSummary:{fea_case_provenance:{verified_run_id:RUN,
                                      solved_case_sha256:CASE}},
  $:id=>nodes[id]??null,
  gfReportReady:()=>true,
  gfReportSelectionCurrent:(uid,sha,run,caseSha)=>
   uid===ctx.jobId&&sha===ctx.current.sha256&&run===RUN&&caseSha===CASE,
  gfInteractiveReportBlockedMessage:()=> 'selection changed',
  gfMeshFollowupSelection:()=>({id:STUDY}),
  gfReportStatusTab:(_tab,title,message)=>seen.tabs.at(-1).status=[title,message],
  gfBuildVisibleReport:async(...args)=>{
   seen.builder.push(args);
   if(badBuilder)throw Error('실제 FEA HTML 수치 검증 실패');
   if(changeCadDuringBuild)ctx.current.sha256='f'.repeat(64);
   return html;
  },
  Blob:class {
   constructor(parts,options){this.parts=parts;this.type=options.type;seen.blobs.push(this)}
  },
  URL:{createObjectURL:()=> 'blob:geofield-test',revokeObjectURL:()=>{}},
  document:{
   body:{append:()=>{}},
   createElement:tag=>{
    assert.equal(tag,'a');
    return {href:'',download:'',
     click(){seen.links.push({href:this.href,download:this.download})},
     remove(){}};
   }
  },
  window:{
   confirm:()=>{seen.confirm++;return true;},
   open:()=>{
    const tab={closed:false,opener:null,writes:[],
      document:{open(){},write(value){tab.writes.push(value)},close(){}}};
    seen.tabs.push(tab);return tab;
   }
  },
  fetch:async(url,options)=>{
   seen.fetch.push({url,options});
   assert.equal(url,'/api/results/report-save/'+UID,
    'the export handler must not call a paid agent or a second FEA solve');
   assert.equal(options.method,'POST');
   assert.equal(options.headers['X-GeoField-Report-Export'],'EXPLICIT_SAVE');
   return {ok:baseArchiveOk,json:async()=>baseArchiveOk?{
     ok:true,format:'html',run_id:RUN,sha256:'c'.repeat(64),
     saved:true,path:'local-base-only-archive'}:{error:'archive server unavailable'}};
  }
 };
 vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
 return{seen,nodes,ctx,
  preview:()=>nodes.resultsReportBtn.onclick(),
  save:()=>nodes.resultsReportSaveBtn.onclick()};
}
(async()=>{
 const success=make();
 await success.preview();
 assert.equal(success.seen.tabs.length,1);
 assert.equal(success.seen.tabs[0].writes.at(-1),html);
 assert.equal(success.seen.fetch.length,0,
  'free preview has zero archive writes and zero paid requests');
 await success.save();
 assert.equal(success.seen.confirm,1);
 assert.equal(success.seen.builder.length,2);
 assert.deepEqual(success.seen.builder[0].slice(0,5),
  [UID,SHA,RUN,CASE,false]);
 assert.deepEqual(success.seen.builder[1],
  [UID,SHA,RUN,CASE,false,true],
  'save must demand linked 3-mesh proof from the canonical builder');
 assert.equal(success.seen.blobs.length,1);
 assert.equal(success.seen.blobs[0].parts.join(''),success.seen.tabs[0].writes.at(-1),
  'downloaded HTML bytes must match the visible verified preview');
 assert.equal(success.seen.fetch.length,1);
 assert.equal(success.seen.links.length,1);
 assert.match(success.seen.links[0].download,/^GeoField_Integrated_Verified_/);
 assert.match(success.nodes.resultsReportStatus.textContent,/AI OFF.*다운로드 요청 완료/);
 assert.equal(success.nodes.reportAiIncludeToggle.checked,false);
 const missing=make({badBuilder:true});
 await missing.save();
 assert.equal(missing.seen.fetch.length,0,
  'invalid actual HTML must not be archived or downloaded');
 assert.equal(missing.seen.blobs.length,0);
 assert.match(missing.nodes.resultsReportStatus.textContent,/다운로드 실패/);
 const switched=make({changeCadDuringBuild:true});
 await switched.save();
 assert.equal(switched.seen.fetch.length,0);
 assert.equal(switched.seen.blobs.length,0,
  'a new CAD selection cannot download a report for the old FEA');
 const running=make({meshBusy:true});
 await running.save();
 assert.equal(running.seen.builder.length,0);
 assert.equal(running.seen.fetch.length,0);
 assert.equal(running.seen.blobs.length,0);
 const noBaseArchive=make({baseArchiveOk:false});
 await noBaseArchive.save();
 assert.equal(noBaseArchive.seen.blobs.length,1,
  'failed separate server archive must not delete the already verified browser HTML');
 assert.match(noBaseArchive.nodes.resultsReportStatus.textContent,/별도 보관 실패/);
 const paidOptIn=make({includeAI:true});
 await paidOptIn.save();
 assert.equal(paidOptIn.seen.builder[0][4],true,
  'only the explicit ON selection may forward a paid request to the builder');
 assert.equal(paidOptIn.nodes.reportAiIncludeToggle.checked,false,
  'explicit paid opt-in is consumed exactly once');
 assert.equal(paidOptIn.seen.fetch.length,0,
  'AI ON browser export must not overwrite immutable base FEA archive');
 console.log('PASS: Preview and Save real button handlers produce the SAME verified HTML, AI OFF zero paid calls, stale/error blocks downloads, no base overwrite');
})().catch(err=>{console.error(err);process.exitCode=1});