'use strict';
// Display-only workflow regressions. No solver, STEP, private model or DB data.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'..','payload','frontend');
const js=fs.readFileSync(path.join(root,'cad.js'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
function slice(start,end){
 const a=js.indexOf(start),b=js.indexOf(end,a+start.length);
 assert(a>=0&&b>a,'Cannot find production function: '+start);
 return js.slice(a,b);
}
for(const id of ['feaLoadDirectionWarning','feaQuickConditionSummary',
 'feaVerificationSummary','feaPeakFocusBtn','feaDetailedLoadArrows','resultsReportSavedPath'])
 assert(html.includes('id="'+id+'"'),id+' needs actual UI control');
const nodes={};
function el(id){return nodes[id]??(nodes[id]={value:'',textContent:'',checked:false,
 selectedOptions:[{textContent:'일반 구조용 강재'}]});}
el('feaMaterialPreset').value='steel_generic';
el('feaLoadMode').value='mass_kg';el('feaLoadQuantity').value='5';
el('feaDirectionMode').value='+x';el('feaOwnWeight').checked=false;
const ctx={$:el,Number,Math,Object,String,
 feaFixed:[3],feaLoaded:[9],feaPrepared:true};
vm.createContext(ctx);
vm.runInContext(slice('function gfQuickConditionSummary(){','function gfRefreshMaterialRequirement(){')+
 slice('function gfFeaVerificationSummary(','async function loadCurrentResults(){')+
 'this.quick=gfQuickConditionSummary;this.verify=gfFeaVerificationSummary;',ctx);
ctx.quick();
assert.match(el('feaQuickConditionSummary').textContent,/49\.033 N/);
assert.match(el('feaQuickConditionSummary').textContent,/CAD \+X/);
assert.match(el('feaQuickConditionSummary').textContent,/자중 미포함/);
ctx.verify({fea_case_provenance:{verified_run_id:'a'.repeat(32),restored_record_active:true}},true);
assert.match(el('feaVerificationSummary').textContent,/과거 기록 검증 복원/);
assert.match(el('feaVerificationSummary').textContent,/메시 수렴: 미판정/);
assert.match(el('feaVerificationSummary').textContent,/구조 안전성: 판정하지 않음/);
ctx.verify({},false);assert.match(el('feaVerificationSummary').textContent,/검증 대기/);
// Existing validated applied load markers are never recomputed; only their visual count changes.
const dummy={triangles:[],positions:[],faceIDs:[]};
const actual={cadSha:'a',caseSha:'b',runId:'c',total:31,
 arrows:Array.from({length:12},(_,i)=>({p:[i,0,0],direction:[1,0,0]}))};
const arrowEnv={$:el,app:{clip:false},gfCadSurfaceArrowSamples:()=>[],loadDirection:()=>[1,0,0],Set,Math};
vm.createContext(arrowEnv);
vm.runInContext(slice('function gfForceArrowPlan(','function drawFeaOverlay(){')+
 'this.plan=gfForceArrowPlan;',arrowEnv);
assert.equal(arrowEnv.plan(dummy,[9],actual,'a','b','c').arrows.length,4);
el('feaDetailedLoadArrows').checked=true;
assert.equal(arrowEnv.plan(dummy,[9],actual,'a','b','c').arrows.length,12);
assert.equal(actual.arrows.length,12,'actual verified solver markers remain unchanged');
assert.match(js,/선택한 .*방향은 CAD의 기본 중력 방향 −Z와 다릅니다/);
assert.match(js,/feaPeakFocusBtn'\)\.onclick/);
assert.match(js,/data\.path==='string'/);
assert.match(js,/function defaultView\(\).*app\.zoom=1\.22/);
console.log('PASS: P1/P2/P3/P4/P5/P6 display-only workflow, safety labels and export path');
