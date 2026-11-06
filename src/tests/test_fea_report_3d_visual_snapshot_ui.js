'use strict';
// Real production visualization capture code, isolated browser canvas stubs.
// This does NOT solve FEA, modify FRD, write SQLite or call a paid service.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const src=fs.readFileSync(path.join(__dirname,'../payload/frontend/cad.js'),'utf8');
const begin=src.indexOf('// GEOFIELD_VERIFIED_FEA_REPORT_VIEWS_20261105');
const end=src.indexOf('async function gfBuildVisibleReport(',begin);
assert(begin>0&&end>begin,'report image capture must use the existing verified-FRD viewer source');
const actual=src.slice(begin,end);
const JOB='1'.repeat(32),SHA='a'.repeat(64),RUN='2'.repeat(32),CASE='b'.repeat(64);
function make({useWebGL=true,field=true,run=RUN,caseSha=CASE,validSummary=true,
               failRead=false,blankFramebuffer=false,wrongOverlay=false,staleSelection=false}={}){
 const images=[],frames=[],draws=[],reads=[],composites=[],pixelCopies=[];
 const scene={width:2,height:2};
 const overlay={width:wrongOverlay?1:2,height:2};
 const created=[];
 const node=(tag)=>({tag,id:'',src:'',alt:'',style:{cssText:''},attrs:{},children:[],textContent:'',
  setAttribute(k,v){this.attrs[k]=v},getAttribute(k){return this.attrs[k]},
  append(...values){this.children.push(...values)},
  insertAdjacentElement(_where,value){this.children.push(value)},
  querySelectorAll(selector){
   if(selector==='img')return this.children.flatMap(x=>x.children||[]).filter(x=>x.tag==='img');
   return [];
  }});
 const anchor=node('section'),body=node('body');
 const reportDoc={
  createElement:node,
  getElementById:id=>id==='geofield-a08-evidence'?anchor:
    anchor.children.find(x=>x.id===id)||body.children.find(x=>x.id===id)||null,
  body
 };
 const gl={
  RGBA:6408,UNSIGNED_BYTE:5121,
  isContextLost:()=>false,
  readPixels(_x,_y,w,h,_format,_type,pixels){
   reads.push([w,h]);
   if(failRead&&reads.length===1)throw Error('mock GPU readback failure');
   if(blankFramebuffer){pixels.fill(0);return;}
   // WebGL row 0 is bottom (red); row 1 is top (green).
   pixels.set([255,0,0,255,255,0,0,255,0,255,0,255,0,255,0,255]);
  }
 };
 const state={
  Math,Number,String,Array,Uint8Array,Error,Promise,document:{
   createElement(tag){
    assert.equal(tag,'canvas');
    const made={
     width:0,height:0,getContext(kind){
      assert.equal(kind,'2d');
      return{
       createImageData(w,h){return{data:new Uint8ClampedArray(w*h*4)}},
       putImageData(image){pixelCopies.push(Array.from(image.data))},
       drawImage(source){composites.push(source)},
      };
     },
     toDataURL(mime){
      const data='data:image/png;base64,'+
       Buffer.from('verified-'+state.feaContourMode).toString('base64');
      images.push({mode:state.feaContourMode,mime,data});
      return data;
     }
    };
    created.push(made);
    return made;
   }
  },
  gfReportSelectionCurrent:()=>!staleSelection,
  app:{ready:true,mesh:{drawCount:12},gl:useWebGL?gl:null,fallback2d:!useWebGL},
  canvas:scene,overlay,
  jobId:JOB,current:{sha256:SHA},feaPreparedCaseSha:caseSha,
  feaFieldRunId:run,
  feaField:field?{
   cadSha:SHA,peakEvidence:{globalMax:validSummary?14.758:10,
    surfaceMax:12.5,positionMm:[5,3,2]},
   displacementEvidence:{globalMax:.0264,surfaceMax:.023,
    positionMm:[4,2,1]}
  }:null,
  latestSummary:{
   fea_case_provenance:{verified_run_id:RUN,solved_case_sha256:CASE},
   fea:{maximum_von_mises_mpa:14.758,maximum_displacement_mm:.0264}
  },
  active:'fea',feaContourMode:'stress',
  draw(){draws.push(state.feaContourMode)}
 };
 vm.createContext(state);vm.runInContext(actual,state);
 return {state,reads,images,frames,composites,pixelCopies,draws,anchor,body,
  capture:()=>state.gfCaptureFeaReportViews(JOB,SHA,RUN,CASE),
  append:()=>state.gfAppendFeaReportViews(reportDoc,anchor,JOB,SHA,RUN,CASE)};
}
{
 const t=make();
 const result=t.capture();
 assert.equal(result.images.length,2,'3D stress and displacement require both snapshots');
 assert.deepEqual(Array.from(result.images,x=>x.mode),['stress','displacement']);
 assert.equal(t.reads.length,2,'WebGL must be read immediately after each real draw');
 assert.equal(t.composites.filter(x=>x===t.state.overlay).length,2,
  'FEA color legend and verified surface maxima overlay must appear in both snapshots');
 assert.equal(t.pixelCopies.length,2);
 assert.deepEqual(t.pixelCopies[0].slice(0,4),[0,255,0,255],
  'readPixels must flip Y to match HTML canvas top-down row order');
 assert.deepEqual(t.pixelCopies[0].slice(8,12),[255,0,0,255]);
 assert.equal(t.state.feaContourMode,'stress','preserve original user selection');
 assert.equal(t.state.active,'fea','preserve visible application tab');
 assert.deepEqual(t.draws,['stress','displacement','stress']);
 const oldSource=t.state.feaField;
 const inserted=t.append();
 assert.equal(inserted,true);
 assert.equal(t.state.feaField,oldSource,'never overwrite verified solver field');
 const section=t.anchor.children.find(x=>x.id==='geofield-verified-fea-3d-views');
 assert(section);
 assert.equal(section.querySelectorAll('img').length,2);
 assert.match(section.children[2].children[0].textContent,/표면 최대 12\.50000 MPa.*전체 절점 최대 14\.75800 MPa/);
 const sectionImages=section.querySelectorAll('img');
 assert.deepEqual(sectionImages.map(x=>x.getAttribute('data-gf-field-mode')),
  ['stress','displacement']);
 assert(sectionImages.every(x=>x.getAttribute('data-gf-verified-run')===RUN));
 assert(sectionImages.every(x=>x.getAttribute('data-gf-verified-case')===CASE));
 assert(section.querySelectorAll('img').every(x=>x.src.startsWith('data:image/png;base64,')));
 assert.match(section.children[1].textContent,/별개의 단일 검증 실행/);
}
{
 const t=make({useWebGL:false});
 const r=t.capture();
 assert.equal(r.images.length,2,'Canvas 2D fallback still provides honestly labeled images');
 assert.match(r.note,/Canvas 2D 대체/);
 assert.equal(t.reads.length,0);
 assert.equal(t.composites.filter(x=>x===t.state.canvas).length,2);
}
for(const problem of [
 {field:false},{run:'4'.repeat(32)},{caseSha:'c'.repeat(64)},
 {validSummary:false},{staleSelection:true}
]){
 const t=make(problem),r=t.capture();
 assert.equal(r.images.length,0,JSON.stringify(problem));
 assert.equal(t.draws.length,0,'stale/missing 3D field must never be captured');
 assert.match(r.note,/실제 FRD 3D 표면 필드/);
}
{
 const t=make({blankFramebuffer:true});
 const r=t.capture();
 assert.equal(r.images.length,0,'a blank-but-encodable WebGL frame is never valid FEA evidence');
 assert.match(r.note,/FEA 색상 분포/);
 assert.equal(t.state.active,'fea');
 assert.equal(t.state.feaContourMode,'stress');
}
{
 const t=make({failRead:true});
 const r=t.capture();
 assert.equal(r.images.length,0,'never include only one image of a required pair');
 assert.match(r.note,/응력 화면 캡처 실패/);
 assert.equal(t.state.feaContourMode,'stress','render errors must restore viewer mode');
 assert.equal(t.state.active,'fea','render errors must restore viewer tab');
}
{
 const t=make({wrongOverlay:true});
 const r=t.capture();
 assert.equal(r.images.length,0,'missing legend must block misleading snapshots');
 assert.match(r.note,/색상 범례/);
 const inserted=t.append();
 assert.equal(inserted,false,'numbers-only HTML must remain valid');
 const section=t.anchor.children.find(x=>x.id==='geofield-verified-fea-3d-views');
 assert(section);
 assert.match(section.children.at(-1).textContent,/이미지 2장 미포함/);
}
assert(src.includes('gfAppendFeaReportViews(parsed,evidence,uid,sha,run,caseSha)'),
 'Both preview and saved HTML must use the single existing report builder');
assert(src.includes('const visualCount=visualSection?.querySelectorAll?.('),
 'Auto Stage3 must distinguish actual embedded images from the missing-image note');
console.log('PASS: report embeds both same-run verified FRD WebGL/2D screenshots, merged scale overlays, restores the viewer, and omits invalid/partial images without changing numbers');
