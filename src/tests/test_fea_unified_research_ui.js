'use strict';
// Execute the REAL GeoField saved-FEA history row builder with synthetic records.
// No real CalculiX process, private analysis files, filesystem mutation or HTTP.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const a=source.indexOf('function gfShowEvidenceDetails(');
const b=source.indexOf('async function loadResearch(){',a);
assert(a>=0&&b>a,'Production record row and research-menu handlers not found');
const code=source.slice(a,b);
const record={
 id:'1'.repeat(32),job_id:'2'.repeat(32),cad_sha256:'a'.repeat(64),
 cad_name:'L_bracket.step',stage:'fea_result',created_at:'2026-10-26T01:00:00'
};
function element(tag){
 return {tag,children:[],textContent:'',hidden:false,disabled:false,open:false,
  append(...parts){this.children.push(...parts)}};
}
const map=new Map();
const $=id=>{if(!map.has(id))map.set(id,element('div'));return map.get(id)};
const calls=[];
const sandbox={
 $,
 document:{createElement:element},
 URLSearchParams,
 encodeURIComponent,
 historyLoading:false,historyQueryGeneration:0,historyNextOffset:0,historyTotal:0,
 currentHistoryFilter:()=> 'fea_result',
 historyText:()=>'',historyMaterial:()=>'',historyMass:()=>'',historyNames:{fea_result:'실제 FEA 결과'},
 get:async url=>{calls.push(url);return {items:[record],offset:0,total:1,has_more:false}},
 status:(...x)=>{throw Error('Unexpected record error: '+x.join(' '))},
 restoreArchivedFea:()=>calls.push('restore'),
 displayVerifiedHotspots:()=>calls.push('hotspot'),
 displayVerifiedMeshQuality:()=>calls.push('quality'),
 displayVerifiedStressMesh:()=>calls.push('stress-mesh'),
 feaMeshStudyPick:{coarse:null,medium:null,fine:null},
 feaMeshStudyUpdate:()=>calls.push('study-selected'),
 feaComparePick:{left:null,right:null},
 window:{open:()=>calls.push('opened report')}
};
vm.createContext(sandbox);
vm.runInContext(code,sandbox);
(async()=>{
 await sandbox.loadArchive();
 assert.equal(calls.length,1,'Rendering research controls must not fetch extra analysis');
 assert.match(calls[0],/^\/api\/history\/search\?/);
 const cards=$('historyList').children;
 assert.equal(cards.length,1,'Synthetic history returns exactly one record');
 const row=cards[0];
 assert.equal(row.tag,'div');
 const [title,info,toolbar,advanced]=row.children;
 assert.equal(toolbar.tag,'div');
 assert.equal(advanced.tag,'details');
 assert.equal(advanced.open,false,'research controls hidden by default');
 assert.equal(advanced.children[0].tag,'summary');
 assert.equal(advanced.children[1].tag,'div');
 assert.deepEqual(toolbar.children.map(x=>x.textContent),['CAD·3D FEA 검증 복원','분석 내용','당시 보고서']);
 const research=advanced.children[1];
 assert.equal(research.children.length,11,'Preserve existing 11 distinct research/report operations');
 assert(research.children.every(x=>x.tag==='button'));
 assert(!research.children.some(x=>x.textContent==='CAD·3D FEA 검증 복원'));
 // A selected specialist action opens the shared disclosure AND only its
 // evidence section, keeping prior computations read-only.
 for(const [buttonName,detailName,call] of [
  ['고응력 위치','feaHotspotDetails','hotspot'],
  ['메시 품질','feaSingleMeshDetails','quality'],
  ['응력·메시 연계','feaStressMeshDetails','stress-mesh']]){
   const button=research.children.find(x=>x.textContent===buttonName);
   assert(button,buttonName+' button preserved');
   button.onclick();
   assert.equal($('recordResearchTools').open,true);
   assert.equal($('feaEvidenceDetailTools').open,true);
   assert.equal($(detailName).open,true);
   assert.equal(calls.at(-1),call);
 }
 research.children.find(x=>x.textContent==='메시 굵음').onclick();
 assert.equal($('feaMeshStudyDetails').open,true);
 assert.equal(sandbox.feaMeshStudyPick.coarse,record.id);
 assert.equal(calls.at(-1),'study-selected');
 research.children.find(x=>x.textContent==='비교 A').onclick();
 assert.equal(sandbox.feaComparePick.left,record.id);
 assert.equal($('recordResearchTools').open,true);
 toolbar.children[0].onclick();
 assert.equal(calls.at(-1),'restore','Explicit restoration remains accessible in primary row');
 console.log('PASS: actual FEA history row has 3 primary controls, 11 collapsed research controls, verified subgroup reveal, and unchanged explicit restore');
})().catch(e=>{console.error(e);process.exitCode=1});
