// B05: production deletion button handler with synthetic read-only endpoint responses.
// Exercises confirmation, identity and immediate state invalidation; no user data deleted.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const start=src.indexOf("if(item.stage==='fea_result'){\n    const restore=document.createElement('button')");
const end=src.indexOf("if(item.stage==='fea_result'){\n     const hotspotButton",start);
assert(start>=0&&end>start,'existing FEA history actions not found');
const handler=src.slice(start,end);
const SID='1'.repeat(32),RUN='2'.repeat(32),CAD='a'.repeat(64),JOB='3'.repeat(32);
const base=()=>({id:SID,stage:'fea_result',job_id:JOB,cad_sha256:CAD,result_run_id:RUN});
async function exercise({confirm=true,valid=true,serverOk=true,missingRun=false}={}){
 const item=base();if(missingRun)delete item.result_run_id;
 const calls={get:[],fetch:[],confirmed:0,cleared:0,refreshed:0,status:[]};
 const buttons=[],bar={append(){}},researchBar={append:b=>buttons.push(b)};
 const verified={ok:true,read_only:true,snapshot_id:SID,cad_job_id:JOB,
  cad_sha256:CAD,run_id:valid?RUN:'f'.repeat(32)};
 const ctx={item,bar,researchBar,Error,Array,String,Math,encodeURIComponent,JSON,
  document:{createElement:()=>({disabled:false,type:'',textContent:'',onclick:null})},
  window:{confirm:()=>{calls.confirmed++;return confirm}},
  get:async url=>{calls.get.push(url);return verified},
  gfArchivedNumbersIdentityCheck:(v,s,i)=>{if(!valid||v.snapshot_id!==s||v.cad_sha256!==i.cad_sha256)throw Error('identity mismatch')},
  fetch:async(url,options)=>{calls.fetch.push({url,options});return {
   ok:serverOk,status:serverOk?200:409,json:async()=>serverOk?{
    ok:true,permanent:true,deleted_snapshot_id:SID,deleted_run_id:RUN,
    cad_sha256:CAD,other_records_preserved:true,temporary_cleanup:'complete'}:{error:'server rejected'}
  }},
  status:(...v)=>calls.status.push(v),
  restoreArchivedFea:()=>{},feaComparePick:{left:SID,right:'4'.repeat(32)},
  $:name=>name==='feaCompareClear'?{onclick:()=>{calls.cleared++}}:{disabled:false,textContent:''},
  feaArchiveSelector:{value:''},feaRunId:null,gfRestoredRunId:null,
  loadArchive:async()=>{calls.refreshed++},loadFeaArchive:async()=>{calls.refreshed++},
  current:null,jobId:null
 };
 vm.createContext(ctx);vm.runInContext(handler,ctx);
 const button=buttons.find(x=>x.textContent==='선택 FEA 기록 영구 삭제');
 assert(button,'delete must use advanced history menu');
 assert.equal(button.disabled,false);
 await button.onclick();
 return {calls,button};
}
(async()=>{
 const cancel=await exercise({confirm:false,missingRun:true});
 assert.equal(cancel.calls.get.length,1,'read-only verification before confirmation');
 assert.equal(cancel.calls.confirmed,1);
 assert.equal(cancel.calls.fetch.length,0,'cancelled deletion may not send POST');
 assert.equal(cancel.button.disabled,false);
 const ok=await exercise({missingRun:true});
 assert.equal(ok.calls.fetch.length,1);
 assert.equal(ok.calls.get[0],'/api/fea/verified_archive_numbers/'+SID);
 assert.equal(ok.calls.fetch[0].url,'/api/history/fea-delete/'+SID);
 assert.equal(ok.calls.fetch[0].options.method,'POST');
 assert.equal(ok.calls.fetch[0].options.headers['X-GeoField-FEA-Delete'],'EXPLICIT_PERMANENT_DELETE');
 assert.equal(JSON.parse(ok.calls.fetch[0].options.body).confirm,'PERMANENT_DELETE_FEA_RESULT');
 assert.equal(ok.calls.cleared,1,'invalidated comparator after delete');
 assert.equal(ok.calls.refreshed,2,'reloaded both history views');
 const tamper=await exercise({valid:false});
 assert.equal(tamper.calls.fetch.length,0,'unverified identity cannot delete');
 assert(tamper.calls.status.some(x=>x[0].includes('실패')));
 const refused=await exercise({serverOk:false});
 assert.equal(refused.calls.fetch.length,1);
 assert(refused.calls.status.some(x=>x[0].includes('실패')));
 console.log('B05: confirmed permanent deletion, cancel, identity mismatch, server rejection and history refresh passed');
})().catch(e=>{console.error(e);process.exitCode=1});
