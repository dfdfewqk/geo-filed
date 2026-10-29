// P2: Execute real GeoField stress-scale/status source for original L-bracket.
// No live solver, user STEP, FRD archive, Windows install or data mutations.
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const from=source.indexOf('function niceStressCeiling(');
const to=source.indexOf("// A restored browser form value",from);
assert(from>=0&&to>from,'Production stress legend functions missing');
const code=source.slice(from,to);
const SHA='a'.repeat(64),RUN='1'.repeat(32);
const attrs=new Map([
 ['feaStressScaleStatus',{textContent:''}],
 ['feaStressScaleMax',{value:'5',disabled:false}],
 ['feaStressScaleMode',{value:'auto'}],
]);
const ctx={
  $:key=>{assert(attrs.has(key),'Unknown UI node '+key);return attrs.get(key);},
  current:{sha256:SHA},feaContourMode:'stress',feaFieldRunId:RUN,
  feaField:{cadSha:SHA,maxStress:8,
            peakEvidence:{surfaceMax:8,globalMax:13}},
  feaStressReferences:new Map(),
  Math,Number,String,Map,Object,Error,
};
vm.createContext(ctx);
vm.runInContext(code,ctx);

const before=JSON.stringify(ctx.feaField);
ctx.feaStressScaleStatus();
let label=attrs.get('feaStressScaleStatus').textContent;
assert.match(label,/범례 0–8\.0000 MPa/);
assert.match(label,/표시된 표면 최대 8\.0000 MPa/);
assert.match(label,/전체 절점 최대 13\.000 MPa/);
assert.match(label,/전체 최대 위치 미검증/);
assert.doesNotMatch(label,/실제 현재 최대/);
assert.equal(JSON.stringify(ctx.feaField),before,'Legend cannot modify FRD values');

attrs.get('feaStressScaleMode').value='manual';
ctx.feaStressScaleStatus();
label=attrs.get('feaStressScaleStatus').textContent;
assert.match(label,/범례 0–5\.0000 MPa/);
assert.match(label,/표시된 표면 최대 8\.0000 MPa/);
assert.match(label,/전체 절점 최대 13\.000 MPa/);
assert.match(label,/표면 색상 범위 초과는 빨강으로 포화됨/);
assert.equal(JSON.stringify(ctx.feaField),before);

attrs.get('feaStressScaleMode').value='auto';
ctx.feaField.peakEvidence=null;
ctx.feaStressScaleStatus();
assert.match(attrs.get('feaStressScaleStatus').textContent,/전체 절점 최대 미확인 MPa/);
ctx.feaContourMode='none';
ctx.feaStressScaleStatus();
assert.match(attrs.get('feaStressScaleStatus').textContent,/실제 FEA 결과/);

console.log('P2 L-bracket 3D stress scale surface vs global MPa and no solver mutations PASS');
