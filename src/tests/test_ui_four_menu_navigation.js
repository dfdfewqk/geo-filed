'use strict';
// Execute production tabTo with a fake DOM to validate side effects without
// FreeCAD, CalculiX, a browser GPU, localhost or user engineering data.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const a=source.indexOf("const gfPrimaryMenus=['cad','fea','integration','records'];");
const b=source.indexOf('async function loadFeaPreflight()',a);
assert(a>=0&&b>a,'Actual production tab switcher must exist');
const production=source.slice(a,b);
const names=['cad','fea','integration','records'];
const calls=[];
function mockElement(name,type){
  let enabled=name==='cad';
  return {
    dataset:{[type]:name},
    classList:{toggle:(key,value)=>{if(key==='active'&&type==='tab')enabled=!!value;if(key==='hidden'&&type==='pane')enabled=!value;}},
    isShown:()=>enabled,
  };
}
const buttons=names.map(n=>mockElement(n,'tab'));
const panes=names.map(n=>mockElement(n,'pane'));
const sidebar={scrollTop:17};
const scene={identity:'unchanged WebGL canvas'};
const allHistory={open:false};
const context={
  tabs:buttons,
  document:{querySelectorAll:sel=>{
    assert.equal(sel,'[data-pane]');
    return panes;
  }},
  $:id=>id==='sidebar'?sidebar:id==='scene'?scene:id==='recordAllAnalysisHistory'?allHistory:null,
  draw:()=>calls.push('draw'),
  feaArchiveInitialized:false,
  loadFeaArchive:()=>{calls.push('verified-archive');context.feaArchiveInitialized=true;},
  loadArchive:()=>calls.push('records'),
  loadFeaPreflight:()=>calls.push('fea'),
  loadCurrentResults:()=>calls.push('results'),
};
vm.runInNewContext("let active='cad';\n"+production+"\nthis.go=tabTo;this.activeTab=()=>active;",context);
function shown(collection){return collection.filter(x=>x.isShown()).map(x=>x.dataset.tab||x.dataset.pane);}
function check(target,expectedCallbacks){
  calls.length=0;context.go(target);
  const pane=target==='geometry'?'cad':target;
  assert.equal(context.activeTab(),pane);
  assert.deepEqual(shown(buttons),[pane]);
  assert.deepEqual(shown(panes),[pane]);
  assert.deepEqual(calls,expectedCallbacks.concat('draw'));
  assert.equal(context.$('scene'),scene,'3D canvas identity must persist');
}
check('fea',['fea']);
assert.equal(sidebar.scrollTop,0);
sidebar.scrollTop=22;
check('integration',['results']);
check('records',['verified-archive']);
check('records',[]);
allHistory.open=true;
check('records',['records']);
check('geometry',[]);
assert.equal(sidebar.scrollTop,0);
assert.equal(names.length,4);
calls.length=0;
context.go('unknown');
assert.equal(context.activeTab(),'cad');
assert.deepEqual(calls,[]);
assert.deepEqual(shown(buttons),['cad']);
console.log('PASS: production four-menu + one-time verified FEA archive + optional full history; WebGL canvas unchanged');
