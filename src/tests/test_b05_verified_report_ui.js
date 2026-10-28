// B05: production frontend report handlers with synthetic verified summaries.
// No actual report creation, solver, paid API or file write.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const a=src.indexOf('function gfReportReady('),b=src.indexOf("$('collapseBtn').onclick",a);
assert(a>=0&&b>a,'real B05 report handlers missing');
const cad='a'.repeat(64),caseSha='b'.repeat(64),job='1'.repeat(32),run='2'.repeat(32);
const valid=()=>({cad:{sha256:cad},fea:{
 state:'complete',result_run_id:run,result_case_sha256:caseSha,
 maximum_von_mises_mpa:12.5,maximum_displacement_mm:.03,
 node_count:450,tetrahedron_count:1800},
 fea_case_provenance:{source_verification:'INP_STA_FRD_reverified',
 summary_numbers_crosschecked:true,verified_run_id:run,solved_case_sha256:caseSha,
 verified_mesh:{nodes:450,tetrahedra:1800}},
 ml:{state:'failed'},ai:{state:'not_started'}});
const nodes={resultsReportBtn:{disabled:true},resultsReportSaveBtn:{disabled:true},resultsReportStatus:{textContent:''}};
const calls={open:[],fetch:[],confirm:0}, replies=[];
const ctx={String,Math,Number,Error,Promise,encodeURIComponent,jobId:job,current:{sha256:cad},latestSummary:valid(),
 $:k=>nodes[k],window:{open:(url,...args)=>calls.open.push([url,...args]),confirm:()=>{calls.confirm++;return true}},
 fetch:async(url,opt)=>{calls.fetch.push({url,opt});return replies.shift()}};
vm.createContext(ctx);vm.runInContext(src.slice(a,b),ctx);
assert.equal(ctx.gfReportReady(valid(),cad),true);
for(const change of [
 d=>d.fea.state='failed',
 d=>d.fea_case_provenance.summary_numbers_crosschecked=false,
 d=>d.fea_case_provenance.source_verification='not_verified',
 d=>d.fea.maximum_von_mises_mpa=null,
 d=>d.fea.maximum_displacement_mm=-1,
 d=>d.fea_case_provenance.verified_mesh.nodes=449,
 d=>d.fea_case_provenance.verified_run_id='3'.repeat(32),
 d=>d.fea_case_provenance.solved_case_sha256='d'.repeat(64),
 d=>d.cad.sha256='c'.repeat(64)
]){const d=valid();change(d);assert.equal(ctx.gfReportReady(d,cad),false);}
ctx.latestSummary={...valid(),fea:{...valid().fea,state:'queued'}};
ctx.$('resultsReportBtn').onclick();
assert.equal(calls.open.length,0,'no preview of incomplete FEA');
ctx.latestSummary=valid();ctx.$('resultsReportBtn').onclick();
assert.equal(calls.open.length,1);
assert.equal(calls.open[0][0],'/api/results/report/'+job);
const reply=(obj,ok=true,status=200)=>({ok,status,json:async()=>obj});
replies.push(reply({ok:true,format:'html',saved:true,reused:false,run_id:run,sha256:'f'.repeat(64)}));
const work=ctx.$('resultsReportSaveBtn').onclick();
Promise.resolve(work).then(async()=>{
 assert.equal(calls.confirm,1);
 assert.equal(calls.fetch.length,1);
 const {url,opt}=calls.fetch[0];
 assert.equal(url,'/api/results/report-save/'+job);
 assert.equal(opt.method,'POST');
 assert.equal(opt.body,'');
 assert.equal(opt.credentials,'same-origin');
 assert.equal(opt.headers['X-GeoField-Report-Export'],'EXPLICIT_SAVE');
 assert.match(nodes.resultsReportStatus.textContent,/저장 완료/);
 replies.push(reply({error:'보고서 안전 저장 거절'},false,409));
 await ctx.$('resultsReportSaveBtn').onclick();
 assert.match(nodes.resultsReportStatus.textContent,/저장 실패/);
 assert.match(nodes.resultsReportStatus.textContent,/기존 파일은 보존/);
 const before=calls.fetch.length;
 ctx.latestSummary={...valid(),fea:{...valid().fea,state:'failed'}};
 await ctx.$('resultsReportSaveBtn').onclick();
 assert.equal(calls.fetch.length,before,'failed FEA cannot save');
 console.log('B05: verified report readiness, opt-in immutable POST, 409 error, no implicit save passed');
}).catch(e=>{console.error(e);process.exitCode=1});
