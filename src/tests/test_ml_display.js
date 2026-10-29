// Real frontend rendering function, simulated DOM. No model inference occurs here.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
function segment(start,end){
 const a=source.indexOf(start),b=source.indexOf(end,a);
 assert(a>=0&&b>a, 'required production callback missing');
 return source.slice(a,b);
}
const SHA='a'.repeat(64),OTHER='b'.repeat(64),ID='1'.repeat(32);
const dom=new Map(),$=id=>{
 if(!dom.has(id))dom.set(id,{textContent:'',children:[],append(...items){this.children.push(...items);}});
 return dom.get(id);
};
const document={createElement:tag=>({tag,textContent:'',className:''})};
let calls=0;
const scope=vm.createContext({$,document,jobId:ID,current:{sha256:SHA},autoMlToggle:{checked:true},autoMlGeneration:0,
   loadCurrentResults:async()=>{calls++;},sleep:async()=>{}});
vm.runInContext(segment('function renderBrepResult(','async function watchAutoMl('),scope);
function example(){
 return {sha256:SHA,decision_usage:'blocked_diagnostic_only',
         variants:{topology_trimmed:{faces:[{face_ordinal:1,model_class:'research_label',
                    geometry_surface:'CYLINDER',model_score_uncalibrated:.4}]}}};
}
const valid=example();
assert.equal(scope.renderBrepResult(valid,SHA),true);
assert.equal($('brepMlResults').children.length,2);
for(const makeBad of [
 d=>{d.sha256=OTHER;},
 d=>{d.decision_usage='production';},
 d=>{delete d.variants;},
 d=>{d.variants.topology_trimmed.faces[0].model_score_uncalibrated=NaN;},
 d=>{d.variants.topology_trimmed.faces[0].face_ordinal=-3;},
 d=>{d.variants.topology_trimmed.faces[0].model_score_uncalibrated=1.01;},
 d=>{d.variants.topology_trimmed.faces[0].model_score_uncalibrated=-.01;},
 d=>{d.viewer_face_mapping_verified=true;},
 d=>{d.viewer_face_mapping_verified='yes';},
 d=>{d.trained_architecture_equivalence='proven';}
]){
 const bad=example();makeBad(bad);
 assert.equal(scope.renderBrepResult(bad,SHA),false);
 assert.equal($('brepMlResults').children.length,2, 'existing DOM fixture not mutated as evidence');
 assert.match($('brepMlResults').textContent,/검증 실패/);
}
assert.equal(scope.renderBrepResult(example(),OTHER),false);
console.log('PASS: 12 BrepMFR display contract cases');
