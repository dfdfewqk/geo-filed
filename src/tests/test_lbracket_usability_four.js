'use strict';
// UX 1-4 read-only workflow regression: synthetic browser state, never a solver result.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'..','payload','frontend');
const src=fs.readFileSync(path.join(root,'cad.js'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
function section(a,b){
 const i=src.indexOf(a),j=src.indexOf(b,i+a.length);
 assert(i>=0&&j>i,a+' not found in production source');
 return src.slice(i,j);
}
for(const id of ['feaRepeatGuidance','feaRunStages','feaToResultsBtn','feaResultNextHint',
 'feaArchiveSort','feaArchivedListHint']) assert(html.includes('id="'+id+'"'),id);
const elems={};
function $(k){return elems[k]??(elems[k]={textContent:'',value:'',disabled:false});}
const ctx={$ ,String,Math,Object,Number};vm.createContext(ctx);
vm.runInContext(section('function gfFeaStageText(', "if(typeof document!=='undefined'&&typeof document.getElementById"),ctx);
assert.match(vm.runInContext("gfFeaStageText('verification','실제 원본 재검증')",ctx),/INP·STA·FRD 원본 검증/);
assert.match(vm.runInContext("gfFeaStageText('external_worker','')",ctx),/세부 단계 제공 안 됨/);
assert.match(vm.runInContext("gfFeaStageText('unknown','')",ctx),/종료 여부 확인 불가/);
ctx.gfSetFeaStage('complete','실제 근거 확인');assert.match($('feaRunStages').textContent,/검증 완료/);
ctx.gfSetFeaResultNextStep(false);assert.equal($('feaToResultsBtn').disabled,true);
ctx.gfSetFeaResultNextStep(true);assert.equal($('feaToResultsBtn').disabled,false);
assert.match($('feaResultNextHint').textContent,/동일 실행/);
const selection={value:'',options:[],replaceChildren(...v){this.options=v.slice();},
 add(o){this.options.push(o);}};
const Option=function(text,value){this.text=text;this.value=value;};
ctx.Option=Option;ctx.feaArchiveSelector=selection;
vm.runInContext(
 'let feaArchiveItems=[],feaArchiveOffset=0,feaArchiveTotal=0,feaArchiveRequest=0;'+
 section('// UX2: a read-only SQLite summary','let feaArchiveInitialized='),
 ctx);
const sha='a'.repeat(64);
const x={id:'1'.repeat(32),cad_name:'Bracket Z',created_at:'2026-10-30',cad_sha256:sha};
const y={id:'2'.repeat(32),cad_name:'Bracket A',created_at:'2026-10-29',cad_sha256:sha};
ctx.fixtureA=x;ctx.fixtureB=y;
vm.runInContext('feaArchiveItems=[fixtureA,fixtureB];',ctx);
assert.equal(vm.runInContext("gfSavedHistoryDirection([0,0,-1])",ctx),'-Z');
const entry={cad:{sha256:sha},fea:{setup:{material:'SUS304',external_mass_kg:5,
 force_n:49.03325,direction:[1,0,0]}}};
ctx.entry=entry;
const preview=vm.runInContext('gfSavedHistoryPreview(entry,fixtureA)',ctx);
assert.match(preview,/SUS304.*5kg.*\+X.*원본 미검증/);
assert.equal(vm.runInContext('gfSavedHistoryPreview({cad:{sha256:"b".repeat(64)}},fixtureA)',ctx),null);
vm.runInContext('gfArchiveSavedLabels.set(fixtureA.id,{text:"SUS304 · 5kg · +X · 원본 미검증"});',ctx);
$('feaArchiveSort').value='name';ctx.gfArchiveSortLoadedRecords();
assert.equal(selection.options[1].value,y.id,'name ordering applies only to loaded items');
$('feaArchiveSort').value='newest';ctx.gfArchiveSortLoadedRecords();
assert.equal(selection.options[1].value,x.id);
assert.match(selection.options[1].text,/저장된|원본 미검증/);
assert.match(src,/현재 화면의 재료·면·방향을 확인하고 변경한 하중/);
assert.match(src,/latestSummary.fea_case_provenance\?\.verified_run_id!==feaRunId/);
assert.match(src,/if\(request!==feaArchiveRequest\)return/);
console.log('PASS: four GeoField UX enhancements (repeat guide, trusted stage, archive source distinction, same-run report gate)');
