// Exercise the ACTUAL GeoField web AI-agent handler with delayed synthetic HTTP.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'..','payload','frontend','cad.js'),'utf8');
const start=src.indexOf("$('agentRunBtn').onclick=async()=>{");
const end=src.indexOf("$('reviewBtn').onclick=async()=>{",start);
assert(start>=0&&end>start,'real production AI-agent handler missing');
const handler=src.slice(start,end);
const SHA='a'.repeat(64),JOB='1'.repeat(32),RUN='2'.repeat(32),CASE='b'.repeat(64);
const defer=()=>{let yes,no;const promise=new Promise((a,b)=>{yes=a;no=b});return {promise,resolve:yes,reject:no}};
const valid=()=>({schema:'geofield-evidence-agent-v1',cad_sha256:SHA,mode:'rules_only',
 llm:{connected:false,executed:false,provider:null},
 ml:{status:'research_unverified'},
 cad_features:{schema:'geofield-agent-cad-features-v1',cad_sha256:SHA,cad_job_id:JOB,
  ml_face_ordinals_are_cad_face_ids:false,fea_hotspots_verified:false,
  candidate_count:0,candidates:[]},
 fea:{status:'INP_STA_FRD_reverified',run_id:RUN,case_sha256:CASE,
      maximum_von_mises_mpa:14.5,maximum_displacement_mm:0.057,
      element_type:'C3D4',safety_certified:false,convergence:'not_independently_verified'},
 findings:[{title:'원통형 홀 후보',evidence:'실측 내경',next_check:'실제 응력 교차 확인'}]});
function harness(){
 const nodes={agentRunBtn:{disabled:false},agentLLMOptIn:{checked:false},agentResult:{textContent:'',items:[],append(...args){this.items.push(...args)}}};
 const pending=[];
 const ctx={Error,String,Number,Array,Promise,
  $:n=>nodes[n]??={disabled:false,textContent:'',items:[],append(...args){this.items.push(...args)}},
  jobId:JOB,current:{sha256:SHA},stepSelectionVersion:5,feaRestoreGeneration:1,gfAgentGeneration:0,
  app:{mesh:{faceIDs:[6,7,7,11]},selected:[]},refreshSelected:()=>{},tabTo:()=>{},status:()=>{},
  get:(url,timeout,headers)=>{const v=defer();pending.push({url,timeout,headers,...v});return v.promise;},
  textKV:(title,value)=>({title,value}),
  document:{createElement:tag=>({tag,children:[],textContent:'',append(...x){this.children.push(...x)}})}
 };
 vm.createContext(ctx);vm.runInContext(handler,ctx);
 return {ctx,nodes,pending,changeCad:()=>vm.runInContext("jobId='3'.repeat(32);current={sha256:'c'.repeat(64)};stepSelectionVersion++;gfAgentGeneration++;",ctx)};
}
let count=0;
async function checkSuccessful(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 assert.equal(t.pending.length,1);assert.equal(t.pending[0].url,'/api/agent/evidence/'+JOB);
 t.pending[0].resolve(valid());await work;
 assert.equal(t.nodes.agentRunBtn.disabled,false);
 assert(t.nodes.agentResult.items.some(x=>x.title==='최대 응력 / 변위'));
 assert(t.nodes.agentResult.items.some(x=>x.title==='연결 상태'));
 assert(t.nodes.agentResult.items.some(x=>x.title==='메시 수렴'));
 count++;
}
async function checkMLMeasuredVsResearchSeparation(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();
 data.ml={status:'research_unverified',model_version:'research-v1',
  model_version_verified:false,cad_comparison:{
    status:'aggregate_only_no_face_correspondence',
    cad_review_candidate_count:2,ml_predicted_face_count:11,
    face_mapping_verified:false,cad_fea_conclusion_allowed:false}};
 t.pending[0].resolve(data);await work;
 assert(t.nodes.agentResult.items.some(x=>x.title==='CAD·ML 후보 비교'&&
   x.value.includes('실측 검토 2개')&&x.value.includes('예측 면 11개')&&
   x.value.includes('일치율 아님')));
 assert(t.nodes.agentResult.items.some(x=>x.title==='ML 모델 버전'&&
   x.value.includes('정확도 미검증')));
 assert(t.nodes.agentResult.items.some(x=>x.title==='최대 응력 / 변위'));
 count++;
}
async function checkMLCannotClaimVerifiedFaceJoin(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();
 data.ml.cad_comparison={status:'aggregate_only_no_face_correspondence',
  cad_review_candidate_count:1,ml_predicted_face_count:1,
  face_mapping_verified:true,cad_fea_conclusion_allowed:false};
 t.pending[0].resolve(data);await work;
 assert.match(t.nodes.agentResult.textContent,/계약 위반/);
 count++;
}
async function checkCurrentCadFaceMapping(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.cad_features.candidates=[{
  title:'실측 홀 후보',measured_evidence:'원통형 면 측정 자료',
  next_check:'FEA 면 위치 별도 확인',face_mapping_status:'verified_in_current_cad_mesh',
  face_ids:[6,11]}];data.cad_features.candidate_count=1;
 t.pending[0].resolve(data);await work;
 const card=t.nodes.agentResult.items.find(x=>x.tag==='button' && x.children[0].textContent==='실측 홀 후보');
 assert(card,'valid CAD mesh faces must provide selectable candidate');
 card.onclick();
 assert.equal(Array.from(t.ctx.app.selected).join(','),'6,11');
 count++;
}
async function checkUnknownCadFaceCannotSelect(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.cad_features.candidates=[{
  title:'미검증 형상',measured_evidence:'측정값 있으나 면 매핑 없음',
  face_mapping_status:'verified_in_current_cad_mesh',face_ids:[999]}];
 data.cad_features.candidate_count=1;t.pending[0].resolve(data);await work;
 assert(t.nodes.agentResult.items.some(x=>x.tag==='div' && x.children[0].textContent==='미검증 형상'));
 assert(!t.nodes.agentResult.items.some(x=>x.tag==='button' && x.children[0].textContent==='미검증 형상'));
 count++;
}
async function checkMLOrdinalCannotBeMarkedAsCad(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.cad_features.ml_face_ordinals_are_cad_face_ids=true;
 t.pending[0].resolve(data);await work;
 assert.match(t.nodes.agentResult.textContent,/계약 오류|근거 검증 실패/);
 count++;
}
async function checkFeatureIdentityMismatch(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.cad_features.cad_sha256='f'.repeat(64);
 t.pending[0].resolve(data);await work;
 assert.match(t.nodes.agentResult.textContent,/계약 오류/);
 count++;
}
async function checkUnverifiedMappingIsNeverClickable(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.cad_features.candidates=[{
  title:'얇은 구간 미검증 후보',measured_evidence:'측정 근거만 존재',
  face_mapping_status:'not_verified',face_ids:[]}];
 data.cad_features.candidate_count=1;t.pending[0].resolve(data);await work;
 assert(!t.nodes.agentResult.items.some(x=>x.tag==='button' && x.children[0].textContent==='얇은 구간 미검증 후보'));
 count++;
}
async function checkVerifiedSurfacePeakPosition(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();
 data.fea_spatial={schema:'geofield-agent-fea-spatial-v1',status:'verified_frd_surface_peak_positions',
   cad_sha256:SHA,case_sha256:CASE,run_id:RUN,cad_face_attribution_verified:false,
   stress_peak:{position_mm:[7,6,0],value:14.5,unit:'MPa',
     cad_face_proximity:{status:'geometric_proximity_candidate_only',cad_face_id_candidate:6}},
   displacement_peak:{position_mm:[4,2,0],value:.2,unit:'mm',
     cad_face_proximity:{status:'no_close_cad_triangle',cad_face_id_candidate:null}}};
 t.pending[0].resolve(data);await work;
 assert(t.nodes.agentResult.items.some(x=>x.title==='FRD 표면 최대 응력 위치'&&
                                      x.value.includes('7.0000, 6.0000, 0.0000')&&
                                      x.value.includes('좌표 근접일 뿐')));
 assert(t.nodes.agentResult.items.some(x=>x.title==='FRD 표면 최대 변위 위치'&&
                                      x.value.includes('CAD 면 귀속 미확인')));
 count++;
}
async function checkUnverifiedSurfacePeakHidden(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.fea_spatial={schema:'geofield-agent-fea-spatial-v1',
   status:'not_verified',stress_peak:null,displacement_peak:null,cad_face_attribution_verified:false};
 t.pending[0].resolve(data);await work;
 assert(t.nodes.agentResult.items.some(x=>x.title==='FEA 집중 위치'&&x.value.includes('미표시')));
 assert(!t.nodes.agentResult.items.some(x=>x.title==='FRD 표면 최대 응력 위치'));
 count++;
}
async function checkSpatialWrongRunBlocked(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();
 data.fea_spatial={status:'verified_frd_surface_peak_positions',
    run_id:'f'.repeat(32),case_sha256:CASE,cad_sha256:SHA,
    cad_face_attribution_verified:false,
    stress_peak:{position_mm:[7,6,0],value:14.5,unit:'MPa',cad_face_proximity:{status:'no_close_cad_triangle'}},
    displacement_peak:{position_mm:[4,2,0],value:.2,unit:'mm',cad_face_proximity:{status:'no_close_cad_triangle'}}};
 t.pending[0].resolve(data);await work;
 assert.match(t.nodes.agentResult.textContent,/실행 ID/);
 count++;
}
async function checkSpatialNonFiniteCoordinateBlocked(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();
 data.fea_spatial={status:'verified_frd_surface_peak_positions',
    run_id:RUN,case_sha256:CASE,cad_sha256:SHA,cad_face_attribution_verified:false,
    stress_peak:{position_mm:[NaN,6,0],value:14.5,unit:'MPa',cad_face_proximity:{status:'no_close_cad_triangle'}},
    displacement_peak:{position_mm:[4,2,0],value:.2,unit:'mm',cad_face_proximity:{status:'no_close_cad_triangle'}}};
 t.pending[0].resolve(data);await work;
 assert.match(t.nodes.agentResult.textContent,/절점 위치/);
 count++;
}
async function checkNoFea(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.fea={status:'not_verified',safety_certified:false};
 t.pending[0].resolve(data);await work;
 assert(t.nodes.agentResult.items.some(x=>x.title==='실제 FEA'));
 assert(!t.nodes.agentResult.items.some(x=>x.title==='최대 응력 / 변위'));
 count++;
}
async function checkStale(throws=false){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 t.changeCad();t.nodes.agentResult.textContent='new STEP must stay';
 if(throws)t.pending[0].reject(Error('stale prior FEA error'));
 else t.pending[0].resolve(valid());
 await work;
 assert.equal(t.nodes.agentResult.textContent,'new STEP must stay');
 assert.equal(t.nodes.agentResult.items.length,0);
 count++;
}
async function checkRestoreRace(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 vm.runInContext('feaRestoreGeneration++;gfAgentGeneration++',t.ctx);
 t.nodes.agentResult.textContent='restored result in progress';
 t.pending[0].resolve(valid());await work;
 assert.equal(t.nodes.agentResult.textContent,'restored result in progress');
 count++;
}
async function checkOptionalLLMConsented(){
 const t=harness();t.nodes.agentLLMOptIn.checked=true;
 const work=t.ctx.$('agentRunBtn').onclick();
 assert.equal(t.pending[0].url,'/api/agent/evidence/'+JOB+'?llm=1');
 assert.equal(t.pending[0].headers['X-GeoField-LLM-Opt-In'],'1');
 assert.equal(t.nodes.agentLLMOptIn.checked,false,'consent not reused');
 const data=valid();data.mode='rules_plus_llm';
 data.llm={connected:true,executed:true,provider:'openai',
           status:'external_explanation_only',explanation:'검증되지 않은 참고 문장'};
 t.pending[0].resolve(data);await work;
 assert(t.nodes.agentResult.items.some(x=>String(x.title||'').includes('외부 LLM 참고 설명')&&
                                      x.value.includes('검증되지 않은')));
 assert(t.nodes.agentResult.items.some(x=>x.title==='최대 응력 / 변위'));
 count++;
}
async function checkOptInWithoutProviderPreservesRules(){
 const t=harness();t.nodes.agentLLMOptIn.checked=true;
 const work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.llm={connected:false,executed:false,
                                 status:'not_configured',provider:null};
 t.pending[0].resolve(data);await work;
 assert(t.nodes.agentResult.items.some(x=>x.title==='외부 LLM 상태'&&
                                      x.value.includes('not_configured')));
 assert(t.nodes.agentResult.items.some(x=>x.title==='최대 응력 / 변위'));
 count++;
}
async function checkExternalClaimWithoutConsentRejected(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.mode='rules_plus_llm';
 data.llm={connected:true,executed:true,provider:'openai',
           status:'external_explanation_only',explanation:'arbitrary'};
 t.pending[0].resolve(data);await work;
 assert.match(t.nodes.agentResult.textContent,/계약/);
 count++;
}
async function checkUnverifiedLLM(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.llm.connected=true;
 t.pending[0].resolve(data);await work;
 assert.match(t.nodes.agentResult.textContent,/연결|계약/);
 assert.equal(t.nodes.agentResult.items.length,0);
 count++;
}
async function checkBadCad(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.cad_sha256='f'.repeat(64);
 t.pending[0].resolve(data);await work;
 assert.match(t.nodes.agentResult.textContent,/식별|계약|원본/);
 count++;
}
async function checkNoFakeNumber(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 const data=valid();data.fea.maximum_von_mises_mpa=NaN;
 t.pending[0].resolve(data);await work;
 assert.match(t.nodes.agentResult.textContent,/실행·수치/);
 count++;
}
async function checkApiFailure(){
 const t=harness(),work=t.ctx.$('agentRunBtn').onclick();
 t.pending[0].reject(Error('offline engine'));
 await work;assert.match(t.nodes.agentResult.textContent,/offline engine/);
 assert.equal(t.nodes.agentRunBtn.disabled,false);count++;
}
(async()=>{await checkSuccessful();await checkMLMeasuredVsResearchSeparation();await checkMLCannotClaimVerifiedFaceJoin();await checkVerifiedSurfacePeakPosition();await checkUnverifiedSurfacePeakHidden();await checkSpatialWrongRunBlocked();await checkSpatialNonFiniteCoordinateBlocked();await checkCurrentCadFaceMapping();await checkUnknownCadFaceCannotSelect();await checkMLOrdinalCannotBeMarkedAsCad();await checkFeatureIdentityMismatch();await checkUnverifiedMappingIsNeverClickable();await checkNoFea();await checkStale();await checkStale(true);
 await checkRestoreRace();await checkOptionalLLMConsented();await checkOptInWithoutProviderPreservesRules();await checkExternalClaimWithoutConsentRejected();await checkUnverifiedLLM();await checkBadCad();
 await checkNoFakeNumber();await checkApiFailure();
 assert(src.includes("++gfAgentGeneration;if($('agentRunBtn'))$('agentRunBtn').disabled=true"),
        'Reset must invalidate pending agent result and button');
 assert(src.includes("$('agentRunBtn').disabled=false"),'CAD import/restore must re-enable agent');
 count++;
 console.log('PASS: '+count+' real GeoField AI-agent UI and stale-evidence tests');
})().catch(e=>{console.error(e);process.exitCode=1});
