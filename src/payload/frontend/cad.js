// GeoField R20.1 opt-in physically applied gravity 2026-10-19
/* GeoField 3D viewer: dependency-free local WebGL; no CDN, no fake bracket.
   v8.2.3's imported STEP CAD (through FreeCAD/OCCT) is the ONLY view source. */
'use strict';
const $=id=>document.getElementById(id);
const tabs=[...document.querySelectorAll('[data-tab]')];
let active='cad', file=null, current=null, findings=[], jobId=null, trashMode=false, trashCount=0, recordsRequestSeq=0;
let stepSelectionVersion=0; // Ignore late responses for a previously selected STEP.
let cadImportGeneration=0; // Keep old uploads from overwriting new import status.
let feaRestoreGeneration=0; // A second restore invalidates the first response.
let gfAgentGeneration=0; // Late agent explanations cannot cross STEP/FEA changes.
let gfRestoredRunId=null; // A restored FEA remains read-only and must be reverified before AI display.
let feaFixed=[],feaLoaded=[],feaReady=false,feaRunId=null,feaPrepared=false,feaPreparedCaseSha=null;
let brepReady=false,brepRunning=false,autoMlGeneration=0;let r12Ready=false,r12Running=false,r12Generation=0;let latestSummary=null,feaField=null,feaContourMode='none';
// Display-only MPa scale reference: one reference per STEP digest, never a solver threshold.
const feaStressReferences=new Map();let feaFieldRunId=null,feaActualLoadMarkers=null;
// R12.13-QA: explicit build marker so an old browser/server is not mistaken for the new UI.
const GF_FRONTEND_BUILD='R12.13-QA4';

const app={gl:null,ctx:null,fallback2d:false,mesh:null,ready:false,rotation:[-.22,-.28,0,.91],pan:[0,0],zoom:1,selected:[],clip:false,clipValue:0.25,drag:null};
function status(head,detail,error=false){$('statusText').textContent=head;$('statusDetail').textContent=detail;$('statusText').style.color=error?'#af3d29':'#223c5c';}
// Four primary menus; old geometry-focused feature clicks remain valid.
const gfPrimaryMenus=['cad','fea','integration','records'];
function tabTo(t){
 const pane=t==='geometry'?'cad':t; // historical face/feature links now target CAD.
 if(!gfPrimaryMenus.includes(pane))return;
 const changed=active!==pane;active=pane;
 if(changed)$('sidebar').scrollTop=0;
 tabs.forEach(b=>b.classList.toggle('active',b.dataset.tab===pane));
 document.querySelectorAll('[data-pane]').forEach(p=>p.classList.toggle('hidden',p.dataset.pane!==pane));
 if(pane==='records')loadArchive();
 if(pane==='fea')loadFeaPreflight();
 if(pane==='integration')loadCurrentResults();
 // Viewer canvas and WebGL context live in persistent <main>, outside panes.
 draw();
}
async function loadFeaPreflight(){
 const el=$('feaPreflight');
 try{
  const d=await get('/api/fea/preflight');feaReady=Boolean(d.enabled);
  const runtime=d.gmsh_python_executable?` · Gmsh 검사 Python: ${d.gmsh_python_executable}`:'';
  const issue=d.gmsh_import_error?` · 실제 import 오류: ${d.gmsh_import_error}`:'';
  const where=d.gmsh_environment_source?` · 환경: ${d.gmsh_environment_source}`:'';
  el.textContent=`실제 FEA 경로: ${feaReady?'실행 도구 탐지됨':'실행 도구 미탐지'} · FreeCAD ${d.freecad_detected?'탐지':'선택'} · Gmsh Python ${d.gmsh_python_detected?'탐지':'미탐지'} · CalculiX ${d.calculix_executable_detected?'탐지':'미탐지'}.${runtime}${where}${issue} · 실제 계산 성공 여부는 실행·결과 검사 후 판정합니다.`;
  $('feaRunBtn').disabled=!feaReady||!current||!feaPrepared||!file || feaRunId==='RUNNING';
  $('feaImportPreviousBtn').disabled=!current||!feaPrepared || feaRunId==='RUNNING';
 }catch(e){feaReady=false;$('feaRunBtn').disabled=true;$('feaImportPreviousBtn').disabled=true;el.textContent='FEA 환경 진단 실패: '+e.message;}
}

tabs.forEach(b=>b.addEventListener('click',()=>tabTo(b.dataset.tab)));
$('summaryJumpBtn').onclick=()=>{tabTo('integration');$('sidebar').scrollTop=0;};
$('resultsRefreshBtn').onclick=loadCurrentResults;
$('resultsReportBtn').onclick=()=>{if(jobId&&current)window.open('/api/results/report/'+jobId,'_blank','noopener');};
$('collapseBtn').onclick=()=>{const s=$('sidebar');s.classList.toggle('collapsed');$('collapseBtn').textContent=s.classList.contains('collapsed')?'▶ 패널':'◀ 패널';setTimeout(resize,100)};
$('stepFile').onchange=e=>{
 stepSelectionVersion++;feaRestoreGeneration++;cadImportGeneration++;
 const selected=e.target.files?.[0]||null;
 if(current||jobId){resetModel();} // Selected STEP is not the CAD currently shown.
 file=selected;
 $('pickedFile').textContent=file?`${file.name} (${(file.size/1024/1024).toFixed(2)} MB)`:'파일을 선택하지 않았습니다';
 $('importBtn').disabled=!file;
 if(file)status('새 STEP 선택됨','이전 CAD·FEA 화면을 비웠습니다. 형상 검사를 실행해야 새 STEP 결과를 볼 수 있습니다.');
};
// R17.3: Network errors are not empty SQLite records or missing FEA output.
// Do not silently send requests to a different port or replay a POST.
function geoApiError(err){
 const msg=String(err?.message||err);
 if(err?.name==='AbortError')return Error('로컬 GeoField API 응답이 12초를 넘었습니다. 실행 중인 FEA가 있다면 완료를 기다린 뒤 기록을 다시 조회하세요.');
 if(err instanceof TypeError||/Failed to fetch|NetworkError|Load failed/i.test(msg)){
  return Error('GeoField 로컬 서버 연결이 끊어졌습니다. 현재 서버 CMD가 실행 중인지 확인하고, 종료 후 최신 GeoField CMD를 실행하여 새로 열린 화면에서 조회하세요. (현재 주소: '+location.origin+')');
 }
 return err;
}
async function get(url,timeoutMs=12000,headers={}){
 try{
  const controller=new AbortController();
  const deadline=setTimeout(()=>controller.abort(),timeoutMs);
  let r;
  try{r=await fetch(url,{cache:'no-store',signal:controller.signal,headers});}
  finally{clearTimeout(deadline);}
  const type=(r.headers.get('content-type')||'').toLowerCase();
  if(!type.includes('application/json'))throw Error('GeoField API 대신 다른 페이지가 응답했습니다 (HTTP '+r.status+'). 서버 주소를 확인하세요.');
  const v=await r.json();if(!r.ok)throw Error(v.error||`HTTP ${r.status}`);return v;
 }catch(err){throw geoApiError(err);}
}
async function post(url,body){
 try{
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const type=(r.headers.get('content-type')||'').toLowerCase();
  if(!type.includes('application/json'))throw Error('GeoField 서버가 API 대신 다른 화면을 응답했습니다.');
  const v=await r.json();if(!r.ok)throw Error(v.error||`HTTP ${r.status}`);return v;
 }catch(err){throw geoApiError(err);}
}
let geofieldServerInstance=null;
async function geofieldConnectionWatch(){
 if(document.hidden)return;
 try{
  const info=await get('/api/status');
  if(!info?.ok)throw Error('GeoField 상태 API가 정상 응답하지 않았습니다.');
  if(geofieldServerInstance && info.server_instance && info.server_instance!==geofieldServerInstance){
   status('서버가 다시 시작됐습니다','이전 3D/FEA 세션은 더 이상 유효하지 않습니다. 페이지를 새로고침한 뒤 기록·비교 탭에서 검증 복원하세요.',true);
  }
  if(!geofieldServerInstance)geofieldServerInstance=info.server_instance||null;
 }catch(err){status('GeoField 서버 연결 오류',geoApiError(err).message,true);}
}
setInterval(geofieldConnectionWatch,15000);
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function loadCurrentResults(){
 const target=$('resultsOverview');if(!target)return;
 if(!jobId||!current){target.textContent='먼저 STEP CAD를 불러오세요.';return;}
 const expectedId=jobId,expectedSha=current.sha256;
 try{
  const result=await get('/api/results/summary/'+expectedId);
  if(jobId!==expectedId||current?.sha256!==expectedSha||result.cad.sha256!==expectedSha)throw Error('현재 CAD 해시가 변경됐습니다.');
  latestSummary=result;target.textContent='';
  const dim=result.cad.parts?.[0]?.bbox_mm;
  const area=result.cad.parts?.[0]?.surface_area_mm2;
  const pairs=[['CAD 실제 측정',dim?`${dim.x} × ${dim.y} × ${dim.z} mm / 표면적 ${area} mm²`:'측정된 CAD 없음'],
   ['원통형 홀 후보',`${result.cad.hole_candidates.length}개 · 관통 여부 미확인`],
   ['기존 BrepMFR 연구 모델',result.ml.state==='complete'?`완료 · 모델 내부 면 ${result.ml.face_count}개 · 정확도 미검증`:`${result.ml.status_text} · 신규 R12와 별개`],
   ['FEA 조건',result.fea.conditions_saved?(result.fea.setup?`${result.fea.setup.material} · ${result.fea.setup.force_n}N · 메시 ${result.fea.setup.target_mesh_mm}mm (추천)`: '저장됨'):'미설정'],
   ['FEA 응력 / 변위',result.fea.state==='complete'?`${result.fea.maximum_von_mises_mpa} MPa / ${result.fea.maximum_displacement_mm} mm (실제 CalculiX 계산 완료 · 안전성은 별도 검증)`:`${result.fea.status_text || 'FEA 미실행'} (실제 계산 수치 없음)`],
   ['FEA 계산 출처',result.fea_case_provenance?.verified_run_id?('검증된 실행 '+result.fea_case_provenance.verified_run_id+' · 메시 노드 '+(result.fea_case_provenance.verified_mesh?.nodes??'미기록')+'개 / 사면체 '+(result.fea_case_provenance.verified_mesh?.tetrahedra??'미기록')+'개 · 실제 FRD 재검증 (수렴 판정 별도)'):'이 화면의 실제 FEA 실행 ID를 재검증하지 못했습니다. 이전 수치를 현재 계산으로 사용하지 않습니다.'],
   ['R12 연구 모델 실행',result.r12_research_status?.state==='complete'?('현재 STEP의 실제 R12 추론 완료 · 후보 '+result.r12_research_status.candidate_count+'개 · FEA와 별개'):result.r12_research_status?.state==='not_run'?'현재 STEP에서 아직 실행하지 않음':('연구용 상태: '+(result.r12_research_status?.state||'미확인')+' · 결과 확정 아님')],
   ['FEA 결과·마지막 저장 조건 일치',result.fea_case_provenance?.result_matches_saved===false?'불일치: 표시 수치는 검증된 과거 계산이며 마지막 저장 조건의 신규 계산값이 아닙니다.':result.fea_case_provenance?.result_matches_saved===true?'일치: 같은 해석 조건 식별값 (수치의 원본 검증 상태는 별도 확인)':'확인 대기: 계산 결과 또는 저장 조건의 대응 정보가 없습니다.'],
   ['해석 실행 도구',result.fea.missing_tools.length?`미탐지: ${result.fea.missing_tools.join(', ')}`:'Gmsh·CalculiX 탐지됨 (실행 성공 별도 확인)'],
   ['STEPFeatureNet / AI', '학습 가중치 미확보 / Stage B·LLM 미연결']];
  for(const [key,value] of pairs)target.append(textKV(key,value));
  const notice=document.createElement('div');notice.className='notice warn';notice.textContent='CAD 직접 측정은 결과값입니다. ML 분류는 진단용이며 FEA 미실행 시 응력과 변위는 제공하지 않습니다.';target.append(notice);
 }catch(err){if(jobId===expectedId && current?.sha256===expectedSha)target.textContent='통합 결과 조회 실패: '+err.message+' · FEA 결과 파일 존재 여부는 저장된 실제 계산 기록에서 별도로 확인하세요.';}
}

const autoMlToggle=$('autoMlToggle');
try{autoMlToggle.checked=localStorage.getItem('geofield_auto_ml_enabled')==='true';}catch(_){autoMlToggle.checked=false;}
autoMlToggle.onchange=()=>{try{localStorage.setItem('geofield_auto_ml_enabled',autoMlToggle.checked?'true':'false');}catch(_){}};
$('importBtn').onclick=async()=>{
 if(!file)return;
 $('importBtn').disabled=true;
 const selectedFile=file,selectionVersion=stepSelectionVersion,importGeneration=++cadImportGeneration;
 resetModel();status('CAD 분석 시작',`${selectedFile.name} · STEP 형상 읽는 중`);
 try{
  const r=await fetch('/api/cad/import?filename='+encodeURIComponent(selectedFile.name)+'&auto_ml='+(autoMlToggle.checked?'1':'0'),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:selectedFile});
  const result=await r.json();if(!r.ok)throw Error(result.error||`HTTP ${r.status}`);
  if(stepSelectionVersion!==selectionVersion||cadImportGeneration!==importGeneration)throw Error('새 STEP 파일이 선택되어 이전 분석 응답을 적용하지 않습니다. 새 파일로 다시 분석하세요.');
  const requestedJobId=result.id;jobId=requestedJobId;
  for(let i=0;i<240;i++){
   const s=await get('/api/jobs/'+requestedJobId);
   if(stepSelectionVersion!==selectionVersion || cadImportGeneration!==importGeneration || jobId!==requestedJobId || s.id!==requestedJobId)
     throw Error('STEP 선택 또는 활성 분석 요청이 변경되어 이전 응답을 차단했습니다.');
   if(s.status==='failed')throw Error(s.message);
   if(s.status==='complete'){
      const obj=await get(s.mesh_url);
      if(stepSelectionVersion!==selectionVersion || cadImportGeneration!==importGeneration || jobId!==requestedJobId || !s.analysis?.sha256)
        throw Error('3D 메시 조회 중 STEP 선택이 변경되어 이전 모델을 차단했습니다.');
      if(obj.sha256!==s.analysis.sha256)throw Error('표시 메시와 CAD 결과의 파일 해시가 다릅니다.');
      // Commit the CAD state only after the awaited 3D response is validated.
      current=s.analysis;findings=s.findings||[];
      loadMesh(obj.mesh);
      renderInfo(current);renderFindings();$('resultsRefreshBtn').disabled=false;$('resultsReportBtn').disabled=false;loadCurrentResults();$('feaSetFixed').disabled=false;$('feaSetLoad').disabled=false;$('feaPrepareBtn').disabled=false;$('reviewBtn').disabled=false;$('agentRunBtn').disabled=false;$('geometryDimBtn').disabled=false;if($('optionalMlTools').open)loadBrepPreflight();void watchAutoMl(jobId,current.sha256,autoMlGeneration);$('integrationReview').textContent='검사 완료. 통합 분석 탭에서 현재 CAD의 검토 근거를 볼 수 있습니다.';
      $('modelTitle').textContent=selectedFile.name;
      $('empty3d').classList.add('hidden');
      status('STEP 형상 검사 완료',`${obj.engine} · 실제 CAD 삼각형 ${obj.mesh.triangles.length.toLocaleString()}개${app.fallback2d?' · Canvas 2D 대체 표시':''}`);
      return;
   }
   status('STEP 검사 중',s.message||'FreeCAD 분석 대기 중');await sleep(1000);
  }
  throw Error('결과를 기다리는 시간이 초과됐습니다. 기존 CAD 원본은 변경하지 않았습니다.');
 }catch(e){if(cadImportGeneration===importGeneration){status('형상 검사 실패',e.message,true);$('empty3d').classList.remove('hidden');$('empty3d').querySelector('strong').textContent='STEP 파일을 표시하지 못했습니다';}}
 finally{if(cadImportGeneration===importGeneration)$('importBtn').disabled=!file;}
};
function resetModel(options={}){gfRestoredRunId=null;++gfAgentGeneration;if($('agentLLMOptIn'))$('agentLLMOptIn').checked=false;if($('agentRunBtn'))$('agentRunBtn').disabled=true;if($('agentResult'))$('agentResult').textContent='새 CAD/FEA 선택: 이전 에이전트 설명 무효';if($('agentConnection'))$('agentConnection').textContent='현재 CAD의 에이전트 연결 확인 전 · 외부 LLM 미검증';if(!options.preserveRestore)++feaRestoreGeneration;r186ClearView();feaArchiveVerified=null;++feaArchiveSelectedGeneration;$('feaArchive3DPreviewBtn').disabled=true;feaStressReferences.clear();meshSeriesReset();autoMlGeneration++;resetFeaField();latestSummary=null;$('resultsRefreshBtn').disabled=true;$('resultsReportBtn').disabled=true;$('resultsOverview').textContent='새 CAD 분석 결과를 기다리는 중입니다.';brepReady=false;brepRunning=false;r12Generation++;r12Ready=false;r12Running=false;$('r12RunBtn').disabled=true;$('r12Result').textContent='새 STEP CAD를 불러온 뒤 다시 분석하세요.';$('geometryDimBtn').disabled=true;$('brepMlRunBtn').disabled=true;$('geometryDimResults').textContent='새 STEP 파일의 측정값을 기다리는 중입니다.';$('brepMlResults').textContent='새 CAD: 이전 ML 진단 결과는 무효입니다.';feaFixed=[];feaLoaded=[];feaPrepared=false;feaPreparedCaseSha=null;feaRunId=null;$('feaRunBtn').disabled=true;$('feaImportPreviousBtn').disabled=true;$('feaRunStatus').textContent='새 CAD: 이전 FEA 결과와 조건은 무효입니다.';$('feaStressValue').textContent='미해석';$('feaDispValue').textContent='미해석';$('feaBCValue').textContent='미설정';$('feaFixedIds').textContent='미설정';$('feaLoadIds').textContent='미설정';$('feaPrepared').textContent='새 CAD를 불러왔습니다. 기존 FEA 조건은 무효입니다.';$('feaSetFixed').disabled=true;$('feaSetLoad').disabled=true;$('feaPrepareBtn').disabled=true;$('reviewBtn').disabled=true;$('integrationReview').textContent='새 CAD 검사를 기다리는 중입니다.';current=null;findings=[];app.mesh=null;app.ready=false;app.selected=[];app.focusPoint=null;$('featurePin').classList.add('hidden');jobId=null;$('modelTitle').textContent='CAD 확인 중';$('empty3d').classList.remove('hidden');$('empty3d').querySelector('strong').textContent='STEP 형상 확인 중';$('stats').textContent='';$('findings').textContent='';draw();}
function textKV(k,v){const d=document.createElement('div');d.className='kv';const s=document.createElement('span');s.textContent=k;const b=document.createElement('b');b.textContent=String(v);d.append(s,b);return d;}
function renderInfo(data){const target=$('stats');target.textContent='';target.append(textKV('파일',data.source),textKV('분석 엔진',data.engine),textKV('길이 단위',data.unit||'mm'));
 const parts=data.parts||[];target.append(textKV('솔리드 수',parts.reduce((a,p)=>a+(p.solid_count||0),0)));
 parts.forEach((p,i)=>{const dim=p.bbox_mm||{};target.append(textKV(`부품 ${i+1} 외형`,`${dim.x} × ${dim.y} × ${dim.z} mm`));target.append(textKV('체적',`${p.volume_mm3} mm³`));target.append(textKV('면 / 모서리',`${p.faces} / ${p.edges}`));target.append(textKV('원통형 홀 후보',(p.holes||[]).length));});
 target.append(textKV('FEA','미해석'));
}
function renderFindings(){const t=$('findings');t.textContent='';if(!findings.length){const p=document.createElement('div');p.className='emptyline';p.textContent='검출된 안쪽 원통면 홀 후보가 없습니다. 이는 형상 결함이 없다는 판정을 뜻하지 않습니다.';t.append(p);return;}
 findings.forEach((f,i)=>{const b=document.createElement('button');b.className='finding';b.dataset.index=i;
  const title=document.createElement('strong');title.textContent=f.title;const desc=document.createElement('small');desc.textContent=`${f.evidence} · ${f.suggestion}`;b.append(title,desc);
  b.onclick=()=>{document.querySelectorAll('.finding').forEach(x=>x.classList.remove('active'));b.classList.add('active');app.selected=f.face_ids||[];
   if(f.position_mm && app.mesh?.modelTransform){const tr=app.mesh.modelTransform;app.focusPoint=f.position_mm.map((v,i)=>(v-tr.center[i])/tr.size*1.65);$('featurePin').textContent=f.title.split(' · ')[0];}
   else app.focusPoint=null;
   refreshSelected();tabTo('geometry');status('CAD 면 강조',`${f.title} · 위험 판정이 아니라 형상 후보 표시입니다.`)};
  t.append(b);});}
// QUATERNION/VIEW: unlike OrbitControls polar clamp, rotation is unbounded over all axes.
function qMul(a,b){return [a[3]*b[0]+a[0]*b[3]+a[1]*b[2]-a[2]*b[1],a[3]*b[1]-a[0]*b[2]+a[1]*b[3]+a[2]*b[0],a[3]*b[2]+a[0]*b[1]-a[1]*b[0]+a[2]*b[3],a[3]*b[3]-a[0]*b[0]-a[1]*b[1]-a[2]*b[2]]}
function qAxis(x,y,z,theta){const h=theta/2,s=Math.sin(h);return[x*s,y*s,z*s,Math.cos(h)]}
function matFromQ(q){const [x,y,z,w]=q;return new Float32Array([1-2*y*y-2*z*z,2*x*y+2*z*w,2*x*z-2*y*w,2*x*y-2*z*w,1-2*x*x-2*z*z,2*y*z+2*x*w,2*x*z+2*y*w,2*y*z-2*x*w,1-2*x*x-2*y*y]);}
function defaultView(){app.rotation=qMul(qAxis(1,0,0,-0.36),qAxis(0,1,0,0.55));app.pan=[0,0];app.zoom=1;draw();}
function setView(q){app.rotation=q;app.pan=[0,0];app.zoom=1;draw()}
$('fitBtn').onclick=defaultView;$('frontBtn').onclick=()=>setView(qAxis(1,0,0,Math.PI/2));$('sideBtn').onclick=()=>setView(qAxis(0,1,0,Math.PI/2));$('topBtn').onclick=()=>setView([0,0,0,1]);
$('clipToggle').onchange=e=>{app.clip=e.target.checked;$('clipRange').disabled=!app.clip;draw()};$('clipRange').oninput=e=>{app.clipValue=Number(e.target.value)/100;draw()};
const canvas=$('scene'),overlay=$('feaOverlay');canvas.addEventListener('contextmenu',e=>e.preventDefault());
canvas.addEventListener('pointerdown',e=>{app.drag={x:e.clientX,y:e.clientY,button:e.button,moved:0};canvas.setPointerCapture(e.pointerId);canvas.classList.add('grabbing');});
canvas.addEventListener('pointermove',e=>{if(!app.drag)return;const d=app.drag;let dx=e.clientX-d.x,dy=e.clientY-d.y;d.x=e.clientX;d.y=e.clientY;d.moved+=Math.abs(dx)+Math.abs(dy);
 if(d.button===2 || e.shiftKey){app.pan[0]+=dx/canvas.clientHeight*2;app.pan[1]-=dy/canvas.clientHeight*2;}
 else{app.rotation=qMul(qAxis(0,1,0,dx*.009),qMul(qAxis(1,0,0,dy*.009),app.rotation));const q=app.rotation,mag=Math.hypot(...q);app.rotation=q.map(x=>x/mag);}draw();});
canvas.addEventListener('pointerup',e=>{if(app.drag&&app.drag.moved<7&&app.drag.button===0)pickFace(e);app.drag=null;canvas.classList.remove('grabbing')});
canvas.addEventListener('pointercancel',()=>{app.drag=null;canvas.classList.remove('grabbing')});
canvas.addEventListener('wheel',e=>{e.preventDefault();app.zoom=Math.max(.25,Math.min(10,app.zoom*Math.exp(-e.deltaY*.001)));draw();},{passive:false});
// The solver's nodal scalars are interpolated by the GPU, not replaced by a
// triangle mean. FEM and CAD share the camera and depth buffer.
const SHADER_V=`attribute vec3 aPos;attribute vec3 aNormal;attribute float aHighlight;attribute float aScalar;uniform mat3 uRot;uniform vec2 uPan;uniform float uZoom;uniform float uAspect;varying vec3 vNormal;varying float vHighlight;varying float vSlice;varying float vScalar;void main(){vec3 p=uRot*aPos;float eyeZ=p.z-3.5;float n=.05,f=20.;gl_Position=vec4((p.x*uZoom+uPan.x)*2.1/uAspect,(p.y*uZoom+uPan.y)*2.1,((f+n)/(n-f))*eyeZ+(2.*f*n)/(n-f),-eyeZ);vNormal=normalize(uRot*aNormal);vHighlight=aHighlight;vSlice=aPos.x;vScalar=aScalar;}`;
const SHADER_F=`precision highp float;varying vec3 vNormal;varying float vHighlight;varying float vSlice;varying float vScalar;uniform float uClip;uniform float uClipValue;uniform float uFieldEnabled;uniform float uFieldMaximum;vec3 contour(float t){t=clamp(t,0.,1.);vec3 a=vec3(35.,77.,181.)/255.,b=vec3(57.,184.,219.)/255.,c=vec3(242.,223.,77.)/255.,d=vec3(241.,131.,49.)/255.,e=vec3(193.,55.,46.)/255.;if(t<.25)return mix(a,b,t*4.);if(t<.5)return mix(b,c,(t-.25)*4.);if(t<.75)return mix(c,d,(t-.5)*4.);return mix(d,e,(t-.75)*4.);}void main(){if(uClip>.5 && vSlice>uClipValue) discard;float light=.48+.52*abs(dot(normalize(vNormal),normalize(vec3(.5,.8,.7))));if(uFieldEnabled>.5){vec3 tone=contour(vScalar/max(uFieldMaximum,0.0000000001));gl_FragColor=vec4(tone*(.86+.14*light),1.);return;}vec3 base=vec3(.59,.68,.78)*light;if(vHighlight>.5)base=mix(base,vec3(1.,.57,.19),.87);if(vHighlight>1.5 && vHighlight<2.5)base=vec3(.14,.46,.95)*light;if(vHighlight>2.5)base=vec3(1.,.53,.15)*light;gl_FragColor=vec4(base,1.);}`;
function shader(gl,type,source){const sh=gl.createShader(type);gl.shaderSource(sh,source);gl.compileShader(sh);if(!gl.getShaderParameter(sh,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(sh));return sh;}
function initGL(){try{const gl=canvas.getContext('webgl',{antialias:true,alpha:false,depth:true});if(!gl)throw Error('WebGL 비활성');const pr=gl.createProgram();gl.attachShader(pr,shader(gl,gl.VERTEX_SHADER,SHADER_V));gl.attachShader(pr,shader(gl,gl.FRAGMENT_SHADER,SHADER_F));gl.linkProgram(pr);if(!gl.getProgramParameter(pr,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(pr));gl.useProgram(pr);gl.enable(gl.DEPTH_TEST);gl.disable(gl.CULL_FACE);app.gl=gl;app.program=pr;app.loc={};for(const n of ['aPos','aNormal','aHighlight','aScalar'])app.loc[n]=gl.getAttribLocation(pr,n);for(const n of ['uRot','uPan','uZoom','uAspect','uClip','uClipValue','uFieldEnabled','uFieldMaximum'])app.loc[n]=gl.getUniformLocation(pr,n);return true;}catch(err){
  const ctx=canvas.getContext('2d');
  if(ctx){app.ctx=ctx;app.fallback2d=true;console.warn('GeoField: WebGL 불가. 실제 CAD 메시용 Canvas 2D 대체 뷰어 사용.');return true;}
  status('3D 뷰어 사용 불가',err.message,true);return false;
}}
function setAttr(name,buffer,data,components){const gl=app.gl;if(buffer===null)buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);gl.enableVertexAttribArray(app.loc[name]);gl.vertexAttribPointer(app.loc[name],components,gl.FLOAT,false,0,0);return buffer;}
function loadMesh(mesh){if(!app.gl&&!app.fallback2d&&!initGL())throw Error('3D 렌더러 사용 불가');if(!mesh.positions?.length||!mesh.triangles?.length||mesh.face_ids?.length!==mesh.triangles.length)throw Error('CAD 3D 메시가 비어 있거나 잘못되었습니다.');
 const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];for(const p of mesh.positions)for(let j=0;j<3;j++){lo[j]=Math.min(lo[j],p[j]);hi[j]=Math.max(hi[j],p[j]);}
 const center=lo.map((v,i)=>(v+hi[i])/2),size=Math.max(...hi.map((v,i)=>v-lo[i]))||1;
 const normalized=mesh.positions.map(p=>p.map((v,i)=>(v-center[i])/size*1.65));
 const pos=[],norm=[],high=[];const faceIDs=[];const faceSums=new Map();
 for(let it=0;it<mesh.triangles.length;it++){
  const [a,b,c]=mesh.triangles[it];if(!normalized[a]||!normalized[b]||!normalized[c])throw Error('CAD 메시 인덱스 오류');
  const va=normalized[a],vb=normalized[b],vc=normalized[c];const d=vb.map((v,i)=>v-va[i]),e=vc.map((v,i)=>v-va[i]);
  const n=[d[1]*e[2]-d[2]*e[1],d[2]*e[0]-d[0]*e[2],d[0]*e[1]-d[1]*e[0]];const l=Math.hypot(...n)||1;
  for(const ix of [a,b,c]){pos.push(...normalized[ix]);norm.push(...n.map(x=>x/l));high.push(0);}
  faceIDs.push(mesh.face_ids[it]);
  const fid=mesh.face_ids[it],acc=faceSums.get(fid)||[0,0,0,0];
  for(const ix of [a,b,c]){const point=normalized[ix];for(let j=0;j<3;j++)acc[j]+=point[j];acc[3]++;}
  faceSums.set(fid,acc);
 }
 app.mesh={positions:normalized,triangles:mesh.triangles,faceIDs,drawCount:pos.length/3,highlights:new Float32Array(high),faceCenters:Object.fromEntries([...faceSums].map(([id,v])=>[id,v.slice(0,3).map(n=>n/v[3])])),modelTransform:{center,size}};
 if(app.gl){
  clearFeaGL();const gl=app.gl;app.buffers=app.buffers||{};
  app.buffers.position=setAttr('aPos',app.buffers.position||null,new Float32Array(pos),3);
  app.buffers.normal=setAttr('aNormal',app.buffers.normal||null,new Float32Array(norm),3);
  app.buffers.highlight=setAttr('aHighlight',app.buffers.highlight||null,app.mesh.highlights,1);
 }
 app.ready=true;defaultView();resize();
}
function refreshSelected(){if(!app.mesh)return;const ids=new Set(app.selected),hi=app.mesh.highlights;for(let i=0;i<app.mesh.faceIDs.length;i++){const face=app.mesh.faceIDs[i];const v=feaLoaded.includes(face)?3:feaFixed.includes(face)?2:ids.has(face)?1:0;hi[3*i]=v;hi[3*i+1]=v;hi[3*i+2]=v;}
 if(app.gl){const gl=app.gl;gl.bindBuffer(gl.ARRAY_BUFFER,app.buffers.highlight);gl.bufferSubData(gl.ARRAY_BUFFER,0,hi);}draw();}
function resize(){if(!app.gl&&!app.fallback2d)return;const d=Math.min(window.devicePixelRatio||1,2),w=Math.round(canvas.clientWidth*d),h=Math.round(canvas.clientHeight*d);if(w<1||h<1)return;if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}if(overlay.width!==w||overlay.height!==h){overlay.width=w;overlay.height=h;}if(app.gl)app.gl.viewport(0,0,w,h);draw();}
function updateFeaturePin(){const pin=$('featurePin');if(active==='fea'&&(feaFixed.length||feaLoaded.length)){pin.classList.add('hidden');return;}if(!app.focusPoint){pin.classList.add('hidden');return;}const p=project(app.focusPoint);pin.style.left=((p[0]+1)*50)+'%';pin.style.top=((1-p[1])*50)+'%';pin.classList.remove('hidden');}
// Dispose GPU copies when switching STEP or FEA run. Never modify FRD arrays.
function clearFeaGL(){
 const gl=app.gl,c=app.feaGLBuffers;if(gl&&c)for(const b of [c.position,c.normal,c.scalar])if(b)gl.deleteBuffer(b);
 app.feaGLBuffers=null;
}
function bindGLAttribute(name,buffer,components){
 const gl=app.gl,loc=app.loc[name];if(loc<0)return;
 gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.enableVertexAttribArray(loc);
 gl.vertexAttribPointer(loc,components,gl.FLOAT,false,0,0);
}
function createFeaGLMesh(multiplier){
 const gl=app.gl,field=feaField;if(!gl||!field)return null;
 const cache=app.feaGLBuffers;
 if(cache&&cache.field===field&&cache.multiplier===multiplier)return cache;
 clearFeaGL();
 const coordinates=field.positions,indices=field.triangles,scalars=feaContourMode==='displacement'?field.dispmag:field.stress;
 const n=indices.length*3,vertex=new Float32Array(n*3),normal=new Float32Array(n*3),values=new Float32Array(n);
 let k=0;
 for(const t of indices){
  const points=t.map(i=>coordinates[i].map((v,j)=>v+multiplier*field.displacements[i][j]/field.originalSize*1.65));
  const u=points[1].map((x,j)=>x-points[0][j]),v=points[2].map((x,j)=>x-points[0][j]);
  const cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]],len=Math.hypot(...cross)||1;
  for(let j=0;j<3;j++,k++){
   vertex.set(points[j],3*k);normal.set(cross.map(x=>x/len),3*k);values[k]=scalars[t[j]];
  }
 }
 const mk=(data)=>{const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);return b;};
 app.feaGLBuffers={field,multiplier,mode:feaContourMode,count:n,
  position:mk(vertex),normal:mk(normal),scalar:mk(values)};
 return app.feaGLBuffers;
}
function draw(){
 if(app.fallback2d)return drawFallback();const gl=app.gl;if(!gl)return;
 gl.clearColor(.952,.968,.983,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
 if(!app.ready||!app.mesh)return;
 gl.useProgram(app.program);gl.uniformMatrix3fv(app.loc.uRot,false,matFromQ(app.rotation));
 gl.uniform2fv(app.loc.uPan,new Float32Array(app.pan));gl.uniform1f(app.loc.uZoom,app.zoom);
 gl.uniform1f(app.loc.uAspect,canvas.width/Math.max(canvas.height,1));
 gl.uniform1f(app.loc.uClip,app.clip?1:0);gl.uniform1f(app.loc.uClipValue,app.clipValue);
 const fieldActive=active==='fea'&&feaField&&feaContourMode!=='none';
 if(fieldActive){
  const deform=$('feaDeformToggle').checked?Number($('feaDeformScale').value):0;
  // Cached geometry; changes to the MPa legend do not alter physical values.
  let c=createFeaGLMesh(deform);
  if(c.mode!==feaContourMode){clearFeaGL();c=createFeaGLMesh(deform);}
  const reference=feaContourMode==='stress'?feaStressScale(feaField.maxStress,feaField.cadSha,feaFieldRunId):null;
  const ceiling=reference?(reference.error?null:reference.upper):Math.max(feaField.maxDisp,1e-12);
  if(ceiling&&Number.isFinite(ceiling)){
   bindGLAttribute('aPos',c.position,3);bindGLAttribute('aNormal',c.normal,3);
   bindGLAttribute('aScalar',c.scalar,1);
   gl.disableVertexAttribArray(app.loc.aHighlight);gl.vertexAttrib1f(app.loc.aHighlight,0);
   gl.uniform1f(app.loc.uFieldEnabled,1);gl.uniform1f(app.loc.uFieldMaximum,ceiling);
   gl.drawArrays(gl.TRIANGLES,0,c.count);
  }
 }else{
  bindGLAttribute('aPos',app.buffers.position,3);bindGLAttribute('aNormal',app.buffers.normal,3);
  bindGLAttribute('aHighlight',app.buffers.highlight,1);
  gl.disableVertexAttribArray(app.loc.aScalar);gl.vertexAttrib1f(app.loc.aScalar,0);
  gl.uniform1f(app.loc.uFieldEnabled,0);gl.uniform1f(app.loc.uFieldMaximum,1);
  gl.drawArrays(gl.TRIANGLES,0,app.mesh.drawCount);
 }
 updateFeaturePin();drawFeaOverlay();
}
function drawFallback(){
 const ctx=app.ctx;if(!ctx||canvas.width<1||canvas.height<1)return;
 const w=canvas.width,h=canvas.height;ctx.fillStyle='#eef3f8';ctx.fillRect(0,0,w,h);
 if(!app.ready||!app.mesh)return;
 const tr=app.mesh.triangles,pts=app.mesh.positions;const stride=Math.max(1,Math.ceil(tr.length/12000));
 const projected=new Map();function point(ix){let p=projected.get(ix);if(!p){p=project(pts[ix]);projected.set(ix,p)}return p;}
 const list=[];
 for(let i=0;i<tr.length;i+=stride){
  const [a,b,c]=tr[i],pa=point(a),pb=point(b),pc=point(c);
  if(app.clip && [a,b,c].every(ix=>pts[ix][0]>app.clipValue))continue;
  const cx=(pa[0]+pb[0]+pc[0])/3,cy=(pa[1]+pb[1]+pc[1])/3;
  if(!Number.isFinite(cx+cy))continue;
  list.push([i,(pa[2]+pb[2]+pc[2])/3,pa,pb,pc]);
 }
 list.sort((a,b)=>a[1]-b[1]);
 for(const [idx,z,a,b,c] of list){
  const face=app.mesh.faceIDs[idx],selected=app.selected.includes(face),fixed=feaFixed.includes(face),loaded=feaLoaded.includes(face);
  const tone=Math.max(0,Math.min(1,(z+1.5)/3));const shade=Math.round(156+35*tone);
  ctx.fillStyle=loaded?'#ee9b47':fixed?'#578acb':selected?'#f3a253':`rgb(${shade-12},${shade-5},${shade+5})`;
  ctx.strokeStyle=ctx.fillStyle;ctx.lineWidth=0.5;
  ctx.beginPath();ctx.moveTo((a[0]+1)*w/2,(1-a[1])*h/2);
  ctx.lineTo((b[0]+1)*w/2,(1-b[1])*h/2);
  ctx.lineTo((c[0]+1)*w/2,(1-c[1])*h/2);ctx.closePath();ctx.fill();ctx.stroke();
 }
 ctx.fillStyle='#677e9b';ctx.font=`${Math.max(11,Math.round(h/65))}px sans-serif`;
 ctx.fillText('Canvas 2D CAD viewer (WebGL 대체 · 표시 삼각형 '+Math.ceil(tr.length/stride).toLocaleString()+'개)',16,26);
 updateFeaturePin();drawFeaOverlay();
}
function project(v){const m=matFromQ(app.rotation),a=m[0]*v[0]+m[3]*v[1]+m[6]*v[2],b=m[1]*v[0]+m[4]*v[1]+m[7]*v[2],c=m[2]*v[0]+m[5]*v[1]+m[8]*v[2],depth=3.5-c;
 const aspect=canvas.clientWidth/Math.max(canvas.clientHeight,1);return[(a*app.zoom+app.pan[0])*2.1/(aspect*depth),(b*app.zoom+app.pan[1])*2.1/depth,c];}
function loadDirection(){
 const key=$('feaDirectionMode').value,sign=key[0]==='-'?-1:1,axis={x:0,y:1,z:2}[key[1]];
 const vector=[0,0,0];if(axis!==undefined)vector[axis]=sign;return vector;
}
function displayForce(){
 const kind=$('feaLoadMode').value,val=Number($('feaLoadQuantity').value);
 if(kind==='example_100n')return {force:100,mass:null,example:true};
 if(!Number.isFinite(val)||val<=0)return null;
 return kind==='mass_kg'?{force:val*9.80665,mass:val,example:false}:{force:val,mass:null,example:false};
}
function bodyMass(){
 const densities={steel_generic:7850,sus304:7930,al6061_t6:2700};
 const density=densities[$('feaMaterialPreset').value];
 const vol=current?.parts?.reduce((n,p)=>n+Number(p.volume_mm3||0),0);
 if(!density||!vol||!Number.isFinite(vol))return null;
 return {mass:vol*1e-9*density,density};
}
function forceText(){
 const f=displayForce();return f?(f.example?'예시 하중 · ':f.mass!==null?`${f.mass} kg → `:'')+`${f.force.toFixed(2)} N · ${$('feaDirectionMode').value.toUpperCase()}`:'하중 크기 미입력';
}
function refreshLoadLegend(){
 const own=bodyMass();let text='고정: 파랑 · 하중: 주황';
 if(feaLoaded.length)text+=' · '+forceText();
 if(own)text+=` · 브래킷 자체 질량 약 ${(own.mass*1000).toFixed(1)}g (`+($('feaOwnWeight').checked?'FEA 자중 포함 −Z':'자중 미적용')+')';
 $('feaVisualLegend').textContent=text;
}

function fieldColor(r){
 // Blue → cyan → yellow → orange → red. Only actual per-node solver values.
 const stops=[[35,77,181],[57,184,219],[242,223,77],[241,131,49],[193,55,46]];
 const a=Math.max(0,Math.min(0.99999,r))*4,i=Math.floor(a),t=a-i;
 const c=stops[i].map((v,j)=>Math.round(v*(1-t)+stops[i+1][j]*t));
 return `rgb(${c[0]},${c[1]},${c[2]})`;
}
// Actual FEM stress values stay untouched. A common scale is required to compare
// physically different applied loads: per-result normalization masks amplitudes.
function niceStressCeiling(value){
 if(!Number.isFinite(value)||value<=0)return 1;
 const mag=Math.pow(10,Math.floor(Math.log10(value)));
 for(const multiple of [1,2,5,10])if(value<=multiple*mag*(1+1e-12))return multiple*mag;
 return 10*mag;
}
function feaStressReference(cadSha,observedMax,runId){
 if(!cadSha || !Number.isFinite(observedMax) || observedMax<0)return null;
 if(!feaStressReferences.has(cadSha)){
  const upper=niceStressCeiling(Math.max(observedMax*3,1e-9));
  feaStressReferences.set(cadSha,{upper,initialMax:observedMax,runId:runId||'미확인'});
 }
 return feaStressReferences.get(cadSha);
}
function feaStressScale(observedMax,cadSha,runId){
 const mode=$('feaStressScaleMode').value;
 if(mode==='auto')return {upper:observedMax>0?observedMax:1,mode:'결과별 자동',clipped:false};
 if(mode==='manual'){
  const upper=Number($('feaStressScaleMax').value);
  if(!Number.isFinite(upper)||upper<=0)return {upper:null,mode:'수동',error:'고정 색상 최대 MPa는 0보다 큰 숫자로 지정하세요.'};
  return {upper,mode:'수동 고정',clipped:observedMax>upper};
 }
 const ref=feaStressReference(cadSha,observedMax,runId);
 if(!ref)return {upper:null,mode:'비교 고정',error:'실제 계산 또는 CAD 출처를 확인할 수 없습니다.'};
 return {upper:ref.upper,mode:'같은 STEP 기준 고정',clipped:observedMax>ref.upper,refRunId:ref.runId};
}
function feaStressScaleStatus(){
 const el=$('feaStressScaleStatus');if(!el)return;
 $('feaStressScaleMax').disabled=$('feaStressScaleMode').value!=='manual';
 const data=feaField&&feaContourMode==='stress'?{max:feaField.maxStress,sha:feaField.cadSha,run:feaFieldRunId}:null;
 if(!data){
  const ref=current?feaStressReferences.get(current.sha256):null;
  el.textContent=ref?'이 STEP의 비교 색상 기준 0–'+ref.upper.toPrecision(5)+' MPa 보존 · 다음 계산에도 유지':
   '실제 FEA 결과를 읽으면 고정 비교 범위가 설정됩니다. 실제 계산값은 그대로 유지됩니다.';
  return;
 }
 const scale=feaStressScale(data.max,data.sha,data.run);
 el.textContent=scale.error||('범례 0–'+scale.upper.toPrecision(5)+' MPa · 실제 현재 최대 '+data.max.toPrecision(5)+' MPa · '+scale.mode+
  (scale.clipped?' · 범위 초과 부분은 빨강으로 포화됨 (계산값은 유지)':''));
}
// A restored browser form value must never silently select the fixed comparison scale.
$('feaStressScaleMode').value='auto';
$('feaStressScaleMode').addEventListener('change',()=>{feaStressScaleStatus();draw();if(r185PreviewField)r185Draw();});
$('feaStressScaleMax').addEventListener('input',()=>{feaStressScaleStatus();draw();if(r185PreviewField)r185Draw();});
$('feaStressScaleReset').addEventListener('click',()=>{
 if(!current){$('feaStressScaleStatus').textContent='STEP을 먼저 불러오세요.';return;}
 feaStressReferences.delete(current.sha256);
 if(feaField)feaStressReference(feaField.cadSha,feaField.maxStress,feaFieldRunId);
 $('feaStressScaleMode').value='compare';feaStressScaleStatus();draw();if(r185PreviewField)r185Draw();
});
// QA4: Reconcile the exact surface field to the *same run's* full FRD summary.
// A surface peak can be less than an interior-node maximum, but never greater.
// This is a read-only check; it does not scale, clip, or replace solver values.
function gfFeaFieldSummaryCheck(field,expectedResults){
 const globalStress=expectedResults?.maximum_nodal_von_mises_mpa;
 const globalDisp=expectedResults?.maximum_displacement_mm;
 if(typeof globalStress!=='number'||!Number.isFinite(globalStress)||globalStress<0||
    typeof globalDisp!=='number'||!Number.isFinite(globalDisp)||globalDisp<0)
  throw Error('동일 실행의 실제 FRD 전체 최대 응력/변위 근거가 없습니다. 3D 표시를 차단합니다.');
 const stresses=field?.von_mises_mpa,displacements=field?.displacements_mm;
 if(!Array.isArray(stresses)||!stresses.length||!Array.isArray(displacements)||displacements.length!==stresses.length||
    stresses.some(x=>typeof x!=='number'||!Number.isFinite(x)||x<0)||
    displacements.some(v=>!Array.isArray(v)||v.length!==3||v.some(x=>typeof x!=='number'||!Number.isFinite(x))))
  throw Error('3D 표면 응력·변위 필드가 유효하지 않습니다.');
 let peakStress=0,peakDisp=0;
 for(const v of stresses)peakStress=Math.max(peakStress,v);
 for(const v of displacements)peakDisp=Math.max(peakDisp,Math.hypot(v[0],v[1],v[2]));
 const toleranceStress=Math.max(1e-6,globalStress*1e-5);
 const toleranceDisp=Math.max(1e-9,globalDisp*1e-5);
 if(peakStress>globalStress+toleranceStress || peakDisp>globalDisp+toleranceDisp)
  throw Error('3D 표면 최댓값이 같은 실행의 FRD 전체 최댓값보다 큽니다. 계산 수치와 색상 표시 연결을 확인하세요.');
 return {globalStress,globalDisp,surfaceStress:peakStress,surfaceDisp:peakDisp,
         surfaceStressBelowGlobal:peakStress<globalStress-toleranceStress,
         surfaceDispBelowGlobal:peakDisp<globalDisp-toleranceDisp};
}
function setFeaField(field,expectedSha,expectedCase,verifiedRunId=null,expectedResults=null){
 if(!/^[0-9a-f]{32}$/.test(String(verifiedRunId||'')) ||
    !/^[0-9a-f]{32}$/.test(String(jobId||'')) ||
    field?.run_id!==verifiedRunId || field?.cad_job_id!==jobId ||
    current?.sha256!==expectedSha || feaPreparedCaseSha!==expectedCase)
  throw Error('FEA 3D 필드의 실행 ID·활성 CAD·저장 조건이 현재 화면과 일치하지 않습니다.');
 if(!field||field.schema!=='geofield-fea-surface-field-v1'||field.source!=='actual_calculix_ascii_frd'||field.cad_sha256!==expectedSha||field.case_sha256!==expectedCase)
  throw Error('FEA 필드 출처 또는 해석 조건이 일치하지 않습니다.');
 if(!app.mesh||!Array.isArray(field.positions_mm)||!Array.isArray(field.triangles)||!field.positions_mm.length||!field.triangles.length||field.triangles.length>180000)
  throw Error('FEA 표면 메시가 없거나 너무 큽니다.');
 const n=field.positions_mm.length,stress=field.von_mises_mpa,disp=field.displacements_mm;
 if(stress?.length!==n||disp?.length!==n||field.triangles.some(a=>a.length!==3||a.some(x=>!Number.isInteger(x)||x<0||x>=n)))throw Error('FEA 필드 인덱스·길이 불일치');
 if(stress.some(v=>!Number.isFinite(v)||v<0)||disp.some(v=>v.length!==3||v.some(x=>!Number.isFinite(x))))throw Error('FEA 필드 비정상 수치');
 const match=gfFeaFieldSummaryCheck(field,expectedResults);
 const tr=app.mesh.modelTransform;
 const positions=field.positions_mm.map(v=>{
  if(v.length!==3||v.some(x=>!Number.isFinite(x)))throw Error('FEA 메시 좌표 오류');
  return v.map((x,j)=>(x-tr.center[j])/tr.size*1.65);
 });
 const dispmag=disp.map(v=>Math.hypot(v[0],v[1],v[2]));
 clearFeaGL();
 feaField={cadSha:expectedSha,positions,triangles:field.triangles,stress,dispmag,displacements:disp,originalSize:tr.size,
           maxStress:stress.reduce((a,b)=>Math.max(a,b),0),
           maxDisp:dispmag.reduce((a,b)=>Math.max(a,b),0)};
 feaFieldRunId=verifiedRunId;feaStressReference(expectedSha,feaField.maxStress,verifiedRunId);
 feaActualLoadMarkers=null;
 const lm=field.load_node_markers;
 if(lm && lm.schema==='geofield-verified-inp-cload-markers-v1' &&
    lm.source==='reverified_actual_calculix_inp_cload' &&
    lm.cad_sha256===expectedSha && lm.case_sha256===expectedCase &&
    Number.isInteger(lm.applied_node_count) && lm.applied_node_count>0 &&
    Array.isArray(lm.markers) && lm.markers.length>0 && lm.markers.length<=24 &&
    lm.shown_node_count===lm.markers.length && lm.shown_node_count<=lm.applied_node_count &&
    lm.markers.every(m=>Array.isArray(m.position_mm)&&m.position_mm.length===3&&
      m.position_mm.every(Number.isFinite)&&Array.isArray(m.force_n)&&m.force_n.length===3&&
      m.force_n.every(Number.isFinite)&&Math.hypot(...m.force_n)>0) &&
    Array.isArray(lm.total_force_n)&&lm.total_force_n.length===3&&lm.total_force_n.every(Number.isFinite)){
    feaActualLoadMarkers={cadSha:expectedSha,caseSha:expectedCase,runId:verifiedRunId,
      total:lm.applied_node_count,arrows:lm.markers.map(m=>({
       p:m.position_mm.map((v,j)=>(v-tr.center[j])/tr.size*1.65),
       direction:m.force_n.map(v=>v/Math.hypot(...m.force_n))}))};
 }

 $('feaContourMode').disabled=false;$('feaDeformToggle').disabled=false;$('feaDeformScale').disabled=false;
 $('feaContourMode').value='stress';feaContourMode='stress';
 $('feaContourStatus').textContent='실제 CalculiX FRD 단일 실행'+(verifiedRunId?' '+verifiedRunId:' (실행 ID 미확인)')+' · 3D 표면 최대 '+match.surfaceStress.toPrecision(6)+' MPa / 전체 절점 최대 '+match.globalStress.toPrecision(6)+' MPa · '+(match.surfaceStressBelowGlobal?'전체 최댓값은 표면 밖에 있음 · ':'')+'동일 실행 수치 교차 검증 완료 · 메시 수렴 미검증';
 feaStressScaleStatus();
 draw();
}
function resetFeaField(){
 clearFeaGL();feaActualLoadMarkers=null;
 feaField=null;feaFieldRunId=null;feaContourMode='none';
 $('feaContourMode').value='none';$('feaContourMode').disabled=true;$('feaDeformToggle').checked=false;$('feaDeformToggle').disabled=true;$('feaDeformScale').disabled=true;
 $('feaContourStatus').textContent='실제 CalculiX 계산이 완료되어야 3D 색상 분포를 볼 수 있습니다.';
 feaStressScaleStatus();
 draw();
}
$('feaContourMode').onchange=e=>{feaContourMode=feaField?e.target.value:'none';clearFeaGL();feaStressScaleStatus();draw();};
$('feaDeformToggle').onchange=draw;$('feaDeformScale').onchange=draw;
function paintFeaField(ctx,w,h){
 if(!feaField||feaContourMode==='none'||active!=='fea')return;
 const deform=$('feaDeformToggle').checked;
 const multiplier=deform?Number($('feaDeformScale').value):0;
 const tri=feaField.triangles;
 const pts=deform?feaField.positions.map((pt,i)=>pt.map((v,j)=>v+feaField.displacements[i][j]/feaField.originalSize*1.65*multiplier)):feaField.positions;
 const scalar=feaContourMode==='stress'?feaField.stress:feaField.dispmag;
 const scale=feaContourMode==='stress'?feaStressScale(feaField.maxStress,feaField.cadSha,feaFieldRunId):null;
 if(scale?.error){$('feaStressScaleStatus').textContent=scale.error;return;}
 const maximum=feaContourMode==='stress'?scale.upper:Math.max(feaField.maxDisp,1e-12);
 const observedMaximum=feaContourMode==='stress'?feaField.maxStress:feaField.maxDisp;
 // WebGL provides interpolated, depth-tested surface colors. A very limited
 // Canvas2D fallback remains for devices without WebGL.
 let projected=null,order=[];
 if(!app.gl){
  projected=pts.map(project);
  for(let i=0;i<tri.length;i++){
   const [a,b,c]=tri[i];
   if(app.clip && [a,b,c].every(j=>pts[j][0]>app.clipValue))continue;
   order.push([i,(projected[a][2]+projected[b][2]+projected[c][2])/3]);
  }
  order.sort((a,b)=>a[1]-b[1]);
 }
 ctx.globalAlpha=1;
 if(!app.gl)for(const [i] of order){
  const [ia,ib,ic]=tri[i],a=projected[ia],b=projected[ib],c=projected[ic];
  // Canvas-only fallback: interpolate VERIFIED nodal values, like the
  // WebGL barycentric interpolation. Bounded for low-end computers.
  const screen=[[a[0],a[1]],[b[0],b[1]],[c[0],c[1]]].map(v=>[(v[0]+1)*w/2,(1-v[1])*h/2]);
  const subdivisions=tri.length<=3000?4:tri.length<=12000?2:1;
  gfPaintArchiveNodalTriangle(ctx,screen,[scalar[ia],scalar[ib],scalar[ic]],maximum,subdivisions);
 }
 const barW=Math.min(250,w*.46),x=18,y=h-66;
 const bar=ctx.createLinearGradient(x,0,x+barW,0);
 for(let i=0;i<=12;i++)bar.addColorStop(i/12,fieldColor(i/12));
 ctx.fillStyle='rgba(255,255,255,.94)';ctx.fillRect(x-9,y-34,barW+18,88);
 ctx.fillStyle=bar;ctx.fillRect(x,y,barW,12);
 ctx.fillStyle='#21354c';ctx.font='bold 11px sans-serif';
 ctx.fillText((feaContourMode==='stress'?'실제 FEA von Mises (MPa)':'실제 FEA 변위 크기 (mm)')+(deform?` · 변형 ${multiplier}배 표시`:''),x,y-9);
 ctx.fillText('0',x,y+26);ctx.fillText(maximum.toPrecision(5),x+barW-83,y+26);
 ctx.font='10px sans-serif';
 ctx.fillText((scale?scale.mode:'변위 자동')+' · 실제 최대 '+observedMaximum.toPrecision(5)+(feaContourMode==='stress'?' MPa':' mm'),x,y+43);
 if(scale?.clipped){ctx.fillStyle='#a22c2c';ctx.fillText('범위 초과: 빨강 포화 · 계산값 보존',x,y-22);}
 if(feaContourMode==='stress'&&feaField.maxStress>0){
  let peak=0;for(let i=1;i<feaField.stress.length;i++)if(feaField.stress[i]>feaField.stress[peak])peak=i;
  const pt=pts[peak];
  if(pt&&!(app.clip&&pt[0]>app.clipValue)){
   const projectedPeak=project(pt),px=(projectedPeak[0]+1)*w/2,py=(1-projectedPeak[1])*h/2;
   if(px>=7&&px<w-7&&py>=7&&py<h-7){
    ctx.beginPath();ctx.arc(px,py,5,0,Math.PI*2);ctx.fillStyle='#fff';ctx.fill();
    ctx.lineWidth=2;ctx.strokeStyle='#b12525';ctx.stroke();
    ctx.font='bold 11px sans-serif';
    const message='FRD 표면 최대 '+feaField.maxStress.toPrecision(4)+' MPa';
    const tw=ctx.measureText(message).width+12,bx=Math.max(5,Math.min(w-tw-5,px+9)),by=Math.max(6,py-26);
    ctx.fillStyle='#fffbf2';ctx.fillRect(bx,by,tw,20);
    ctx.fillStyle='#7f2a26';ctx.fillText(message,bx+6,by+14);
   }
  }
 }
}
// R12.12 Stage 2: arrows are display markers, not substitute FEA loads.
function gfCadSurfaceArrowSamples(mesh,faceIds,maxArrows=12){
 if(!mesh||!faceIds.length)return [];
 const faceSet=new Set(faceIds),tri=[];let areaSum=0;
 for(let i=0;i<mesh.triangles.length;i++){
  if(!faceSet.has(mesh.faceIDs[i]))continue;
  const verts=mesh.triangles[i].map(idx=>mesh.positions[idx]);
  if(verts.some(x=>!x))continue;
  if(app.clip&&verts.every(p=>p[0]>app.clipValue))continue;
  const u=verts[1].map((x,j)=>x-verts[0][j]);
  const v=verts[2].map((x,j)=>x-verts[0][j]);
  const a=Math.hypot(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])/2;
  if(a<=1e-12||!Number.isFinite(a))continue;
  areaSum+=a;tri.push({area:a,verts});
 }
 if(!tri.length)return [];
 const count=Math.min(maxArrows,12),out=[];
 let n=0,cumulative=0;
 for(const item of tri){
  const prev=cumulative;cumulative+=item.area;
  while(n<count && areaSum*(n+.5)/count<=cumulative){
   if(areaSum*(n+.5)/count>=prev){
    // Low-discrepancy barycentric points avoid stacking many arrows at
    // one centroid when a large surface has only a few CAD triangles.
    const u=(.23+n*.61803398875)%1,v=(.37+n*.41421356237)%1,root=Math.sqrt(u);
    out.push([0,1,2].map(j=>(1-root)*item.verts[0][j]+root*(1-v)*item.verts[1][j]+root*v*item.verts[2][j]));
   }
   n++;
  }
 }
 return out;
}
function gfDrawForceArrow(ctx,p,direction,w,h,lengthPx=27){
 if(app.clip && p[0]>app.clipValue)return;
 const start=project(p),dest=project(p.map((v,j)=>v+direction[j]*.45));
 let dx=(dest[0]-start[0])*w/2,dy=-(dest[1]-start[1])*h/2;
 let mag=Math.hypot(dx,dy);
 // Edge-on direction: mark as projected, not as a true off-axis vector.
 if(mag<3){dx=0;dy=direction[2]<0?1:-1;mag=1;}
 if(!Number.isFinite(mag)||mag===0)return;
 const sx=(start[0]+1)*w/2,sy=(1-start[1])*h/2;
 const ex=sx+dx/mag*lengthPx,ey=sy+dy/mag*lengthPx;
 if(![sx,sy,ex,ey].every(Number.isFinite))return;
 const theta=Math.atan2(ey-sy,ex-sx);
 // Contrast against the ORANGE load face and BLUE stress field.
 ctx.strokeStyle='#ffffff';ctx.lineWidth=5;
 ctx.beginPath();ctx.moveTo(sx,sy);ctx.lineTo(ex,ey);ctx.stroke();
 ctx.strokeStyle='#2a304e';ctx.fillStyle='#2a304e';ctx.lineWidth=2.5;
 ctx.beginPath();ctx.moveTo(sx,sy);ctx.lineTo(ex,ey);ctx.stroke();
 ctx.beginPath();ctx.moveTo(ex,ey);
 ctx.lineTo(ex-8*Math.cos(theta-.52),ey-8*Math.sin(theta-.52));
 ctx.lineTo(ex-8*Math.cos(theta+.52),ey-8*Math.sin(theta+.52));
 ctx.closePath();ctx.fill();
}
function gfForceArrowPlan(mesh,loaded,actual,sha,caseSha,runId){
 if(!loaded.length)return {kind:'none',arrows:[],text:'하중 면을 선택하면 하중 적용 방향을 표시합니다.'};
 if(actual&&actual.cadSha===sha&&actual.caseSha===caseSha&&actual.runId===runId){
  return {kind:'inp',arrows:actual.arrows,text:'실제 INP CLOAD '+actual.total+'개 노드 중 '+actual.arrows.length+'개 위치 표시 · 화살표 길이는 힘 크기 아님'};
 }
 const pts=gfCadSurfaceArrowSamples(mesh,loaded);
 return {kind:'preview',arrows:pts.map(p=>({p,direction:loadDirection()})),
  text:'CAD 선택 면의 방향 미리보기 '+pts.length+'곳 · 실제 하중 노드 아님 (계산 후 INP 검증)'};
}
function drawFeaOverlay(){
 if(!overlay)return;const ctx=overlay.getContext('2d');if(!ctx)return;
 const w=overlay.width,h=overlay.height;ctx.clearRect(0,0,w,h);
 paintFeaField(ctx,w,h);
 refreshLoadLegend();
 if(!app.ready||!app.mesh)return;
 // Camera-synchronised triad: direction is expressed in CAD axes.
 const cx=w-48,cy=h-48,origin=[0,0,0],mag=.23;
 ctx.lineWidth=Math.max(2,w/500);
 for(const [axis,v,color] of [['X',[mag,0,0],'#d65b43'],['Y',[0,mag,0],'#218963'],['Z',[0,0,mag],'#3573c6']]){
  const a=project(origin),b=project(v),dx=(b[0]-a[0])*w/2,dy=-(b[1]-a[1])*h/2;
  const scale=22/Math.max(4,Math.hypot(dx,dy));const ex=cx+dx*scale,ey=cy+dy*scale;
  ctx.strokeStyle=color;ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(ex,ey);ctx.stroke();ctx.font='bold 11px sans-serif';ctx.fillText(axis,ex+3,ey-3);
 }
 function center(ids){const faceCenters=app.mesh.faceCenters||{},valid=ids.map(i=>faceCenters[i]).filter(Boolean);if(!valid.length)return null;return [0,1,2].map(i=>valid.reduce((n,p)=>n+p[i],0)/valid.length);}
 const pin=(pt)=>{const p=project(pt);return [(p[0]+1)*w/2,(1-p[1])*h/2];};
 const label=(point,title,bg)=>{
  const [x,y]=pin(point);ctx.font='bold 12px sans-serif';const bw=Math.min(w-16,ctx.measureText(title).width+22);
  ctx.fillStyle='#ffffffef';ctx.strokeStyle=bg;ctx.lineWidth=2;ctx.beginPath();ctx.roundRect(Math.max(8,Math.min(x+9,w-bw-8)),Math.max(12,y-40),bw,27,7);ctx.fill();ctx.stroke();
  ctx.fillStyle='#26394f';ctx.fillText(title,Math.max(8,Math.min(x+9,w-bw-8))+9,Math.max(12,y-40)+18);
 };
 const fix=center(feaFixed);if(fix){const [x,y]=pin(fix);ctx.strokeStyle='#2874d1';ctx.lineWidth=3;ctx.strokeRect(x-9,y-9,18,18);label(fix,'고정 면 · '+feaFixed.join(','),'#2d7ed8');}
 const load=center(feaLoaded);if(load && active==='fea'){
  const plan=gfForceArrowPlan(app.mesh,feaLoaded,feaActualLoadMarkers,
   current?.sha256,feaPreparedCaseSha,feaFieldRunId);
  for(const mark of plan.arrows)gfDrawForceArrow(ctx,mark.p,mark.direction,w,h,27);
  $('feaForceDistributionStatus').textContent=GF_FRONTEND_BUILD+' · '+plan.text;
  // Always-visible annotation: a single center label is NOT the applied load distribution.
  ctx.font='bold 12px sans-serif';
  const note=plan.kind==='inp'?'검증된 INP 하중 절점 대표 '+plan.arrows.length+'곳':'하중 면 분산 표시(미리보기) '+plan.arrows.length+'곳';
  const xnote=16,ynote=58,notew=Math.min(w-30,ctx.measureText(note).width+20);
  ctx.fillStyle='rgba(255,255,255,.94)';ctx.fillRect(xnote,ynote-17,notew,24);
  ctx.fillStyle='#28334c';ctx.fillText(note,xnote+10,ynote);
  label(load,forceText(),'#e57920');
 }else $('feaForceDistributionStatus').textContent=feaLoaded.length?'FEA 탭에서 하중 분포를 표시합니다.':'하중 면을 선택하면 방향 화살표가 나타납니다.';

}
function pickFace(e){if(!app.mesh)return;const rect=canvas.getBoundingClientRect(),x=2*(e.clientX-rect.left)/rect.width-1,y=1-2*(e.clientY-rect.top)/rect.height;const proj=app.mesh.positions.map(project);let depth=-Infinity,found=null;
 for(let it=0;it<app.mesh.triangles.length;it++){
  const [ia,ib,ic]=app.mesh.triangles[it],a=proj[ia],b=proj[ib],c=proj[ic],den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);
  if(Math.abs(den)<1e-10)continue;const u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den;
  const v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den;const w=1-u-v;
  if(u>=0&&v>=0&&w>=0){const xModel=u*app.mesh.positions[ia][0]+v*app.mesh.positions[ib][0]+w*app.mesh.positions[ic][0];if(app.clip&&xModel>app.clipValue)continue;const z=u*a[2]+v*b[2]+w*c[2];if(z>depth){depth=z;found=app.mesh.faceIDs[it];}}
 }
 if(found!==null){app.selected=[found];refreshSelected();const f=findings.find(x=>(x.face_ids||[]).includes(found));status('CAD 면 선택',f?`${f.title} — ${f.evidence}`:`CAD 면 ID ${found} · 원본 STEP 메시`);}
}
window.addEventListener('resize',resize);
async function loadRecords(){const request=++recordsRequestSeq;const viewingTrash=trashMode;const target=$('recordList');target.textContent='';const empty=$('emptyTrashRecords');trashCount=0;empty.hidden=!viewingTrash;empty.disabled=true;try{const data=await get('/api/records'+(viewingTrash?'?trash=1':''));if(request!==recordsRequestSeq)return;const items=data.records||[];trashCount=viewingTrash?items.length:0;empty.disabled=!viewingTrash||trashCount===0;empty.textContent=viewingTrash?'휴지통 비우기 ('+trashCount+')':'휴지통 비우기';if(!items.length){$('recordsCount').textContent='0건 (전체 0건)';target.innerHTML='<div class="emptyline">해당 기록이 없습니다.</div>';return;}
 const term=($('recordsSearch').value||'').trim().toLocaleLowerCase();
 const filtered=items.filter(rec=>!term||[rec.name,rec.kind,rec.created_at].some(x=>String(x||'').toLocaleLowerCase().includes(term)));
 $('recordsCount').textContent=`${filtered.length}건 검색됨 (전체 ${items.length}건)`+(filtered.length>200?' · 최대 200건 표시':'');
 if(!filtered.length){target.textContent='검색어와 일치하는 기록이 없습니다.';return;}
 filtered.slice(0,200).forEach(rec=>{const d=document.createElement('div');d.className='rec';const title=document.createElement('strong');title.textContent=rec.name;const sub=document.createElement('small');sub.textContent=`${rec.kind==='cad'?'CAD':'기존 생성 실험'} · ${rec.created_at}`;d.append(title,sub);
 const bar=document.createElement('div');bar.className='recrow';const a=document.createElement('button');a.textContent='상세';a.onclick=async()=>{try{const obj=await get('/api/record/'+rec.id);status('기록 조회',`${obj.name} · 현재 모델의 3D 데이터를 복구하려면 CAD 파일을 다시 불러오세요.`)}catch(e){status('기록 오류',e.message,true)}};bar.append(a);
 if(!trashMode){const rpt=document.createElement('button');rpt.textContent='보고서';rpt.onclick=()=>window.open('/api/report/'+rec.id,'_blank','noopener');bar.append(rpt);}
 const b=document.createElement('button');b.textContent=trashMode?'복원':'휴지통';b.onclick=async()=>{if(!trashMode&&!window.confirm('기록을 휴지통으로 이동할까요? 원본 CAD는 삭제되지 않습니다.'))return;try{await post(trashMode?'/api/records/restore':'/api/records/trash',trashMode?{id:rec.id}:{ids:[rec.id]});loadRecords();}catch(e){status('기록 처리 오류',e.message,true)}};bar.append(b);d.append(bar);target.append(d);});
 }catch(e){target.textContent='기록 조회 실패: '+e.message;
   status('기존 SQLite 기록 조회 실패',e.message,true);}}
$('activeRecords').onclick=()=>{trashMode=false;$('activeRecords').classList.add('selected');$('trashRecords').classList.remove('selected');loadRecords();};
$('trashRecords').onclick=()=>{trashMode=true;$('trashRecords').classList.add('selected');$('activeRecords').classList.remove('selected');loadRecords();};$('reloadRecords').onclick=loadRecords;
$('emptyTrashRecords').onclick=async()=>{
 if(!trashMode||trashCount<1)return;
 const count=trashCount;
 if(!window.confirm('휴지통의 '+count+'개 기록을 영구 삭제할까요?\n이 작업은 되돌릴 수 없습니다.\n원본 STEP, 실제 FEA 계산 파일과 별도로 내보낸 보고서는 삭제하지 않습니다.'))return;
 const empty=$('emptyTrashRecords');empty.disabled=true;
 try{
  const result=await post('/api/records/empty-trash',{confirm:'EMPTY_TRASH',expected_count:count});
  status('휴지통 비우기 완료',result.deleted+'개 휴지통 기록만 영구 삭제했습니다. 원본 CAD와 FEA 결과는 그대로 유지됩니다.');
 }catch(err){status('휴지통 비우기 실패',err.message,true);}
 finally{await loadRecords();}
};
(async()=>{initGL();resize();defaultView();try{const s=await get('/api/status');geofieldServerInstance=s.server_instance||null;const cap=s.capabilities;$('engineChip').textContent=cap.step_engine==='missing'?'CAD 엔진 미탐지':cap.step_engine+' · CAD 준비';if(!cap.cad_analysis)status('CAD 엔진 미탐지','기존 FreeCAD.exe를 지정한 뒤 실행하세요.',true);else status('CAD 대기 중','기존 STEP(.step/.stp) 파일을 불러오세요.');}catch(e){status('서버 상태 확인 실패',e.message,true)}})();


// Evidence integration layer: no ML models or solvers are silently executed.
async function loadBrepPreflight(){
 const targetJob=jobId,targetSha=current?.sha256,selection=stepSelectionVersion,mlGeneration=autoMlGeneration;
 const sameCad=()=>jobId===targetJob&&current?.sha256===targetSha&&
                    stepSelectionVersion===selection&&autoMlGeneration===mlGeneration;
 try{
  const state=await get('/api/ml/preflight');
  if(!sameCad())return;
  brepReady=Boolean(state.available);
  const pythonInfo=state.python_executable?` · ML 검사 Python: ${state.python_executable}`:'';
  const failures=state.python_errors&&Object.keys(state.python_errors).length?' · 모듈 import 오류: '+Object.entries(state.python_errors).map(([k,v])=>k+': '+v).join('; '):'';
  $('brepMlPreflight').textContent=(brepReady
   ?'기존 BrepMFR epoch43 가중치 SHA 확인 · CPU 추론 가능. 인식 정확도 미검증으로 참고용입니다.'
   :'실험적 ML 진단 비활성: '+state.missing.join(', ')+'. 기존 기하학적 치수 검사는 정상 작동합니다.')+pythonInfo+failures;
  $('brepMlRunBtn').disabled=!brepReady||!current||!file||brepRunning;
 }catch(err){
  if(!sameCad())return;
  brepReady=false;$('brepMlRunBtn').disabled=true;$('brepMlPreflight').textContent='ML 진단 상태 확인 실패: '+err.message;
 }
}
$('geometryDimBtn').onclick=async()=>{
 const out=$('geometryDimResults');out.textContent='';
 if(!jobId||!current){out.textContent='현재 분석된 CAD가 없습니다.';return;}
 const expectedJob=jobId,expectedSha=current.sha256,selection=stepSelectionVersion;
 const stillCurrent=()=>jobId===expectedJob&&current?.sha256===expectedSha&&stepSelectionVersion===selection;
 try{
  const result=await get('/api/geometry/dimensions/'+expectedJob);
  if(!stillCurrent())return; // Re-import of even the same STEP has different face IDs.
  if(result.cad_sha256!==expectedSha)throw Error('CAD 해시 불일치');
  const title=document.createElement('div');title.className='notice';
  title.textContent='실측 CAD 외형·체적 및 원통형 홀 후보 '+result.candidates.length+'개 · 학습된 STEPFeatureNet 모델 사용 안 함';out.append(title);
  for(const part of result.parts){const v=part.bbox_mm;const e=document.createElement('div');e.className='finding';
   e.textContent=`실측 외형 ${v.x} × ${v.y} × ${v.z} mm · 체적 ${part.volume_mm3} mm³ · 면적 ${part.surface_area_mm2} mm²`;out.append(e);}
  for(const c of result.candidates){const btn=document.createElement('button');btn.className='finding';
   const nearest=c.measurements.find(m=>m.name==='nearest_parallel_axis_distance');
   btn.textContent=c.id+' · 원통 지름 '+c.diameter_mm+' mm'+(nearest?' · 다른 평행 구멍 축 간 '+nearest.value+' mm':'')+(c.through_state==='verified_through'?' · 관통 확인 (B-Rep)':' · 관통 여부 미확인');
   btn.onclick=()=>{if(!stillCurrent()||!app.mesh)return;const valid=new Set(app.mesh.faceIDs);if(!Array.isArray(c.face_ids)||c.face_ids.some(id=>!valid.has(id)))return;app.selected=c.face_ids;refreshSelected();status('기하 측정 면 강조',c.id+' · 실제 CAD 면 · 안전 판정 아님');};out.append(btn);}
 }catch(err){if(stillCurrent())out.textContent='CAD 치수 계산 오류: '+err.message;}
};

function renderBrepResult(end,expectedSha=current?.sha256){
 const output=$('brepMlResults');output.textContent='';
 const faces=end?.variants?.topology_trimmed?.faces;
 if(!expectedSha||current?.sha256!==expectedSha||end?.sha256!==expectedSha||
    end?.decision_usage!=='blocked_diagnostic_only'||!Array.isArray(faces)||
    faces.length>100000||faces.some(f=>!Number.isInteger(f?.face_ordinal)||
     f.face_ordinal<0||!Number.isFinite(f.model_score_uncalibrated)||
     typeof f.geometry_surface!=='string'||typeof f.model_class!=='string')){
  output.textContent='ML 결과 CAD SHA·면 정보·진단 모드 검증 실패. 예측 표시 차단';
  return false;
 }
 const note=document.createElement('div');note.className='notice warn';
 note.textContent='BrepMFR 실험 추론 완료 · 정확도 미검증 · 내부 면 번호와 CAD 면 매핑 미검증 · 안전 판단에 사용하지 않음';
 output.append(note);
 for(const f of faces){
  const row=document.createElement('div');row.className='finding';
  row.textContent=`ML 면 ${f.face_ordinal} · 표면 ${f.geometry_surface} · 예측 ${f.model_class} · 미보정 점수 ${f.model_score_uncalibrated}`;
  output.append(row);
 }
 return true;
}
async function watchAutoMl(cadId,expectedSha,generation){
 const output=$('brepMlResults');
 const sameCad=()=>jobId===cadId&&current?.sha256===expectedSha&&generation===autoMlGeneration;
 if(!sameCad())return;
 if(!autoMlToggle.checked){output.textContent='자동 진단 꺼짐 · 원하면 수동 실행 버튼을 누르세요.';return;}
 output.textContent='BrepMFR 자동 실행 준비 중 (실험적 분석 · 안전 판단에 사용 안 함)';
 for(let i=0;i<180;i++){
  if(jobId!==cadId||current?.sha256!==expectedSha||generation!==autoMlGeneration)return;
  try{
   const task=await get('/api/ml/latest/'+cadId);
   if(jobId!==cadId||current?.sha256!==expectedSha||generation!==autoMlGeneration)return;
   if(task.status==='complete'){
    if(task.result?.sha256===expectedSha && task.result?.decision_usage==='blocked_diagnostic_only'){
     if(renderBrepResult(task.result,expectedSha))await loadCurrentResults();
    }else output.textContent='ML 결과 해시 또는 검증 게이트 오류';
    return;
   }
   if(['failed','unavailable','disabled_by_user'].includes(task.status)){
    output.textContent='ML 자동 분석: '+task.status+' · '+(task.message||'환경 또는 실행 상태를 확인하세요.');
    await loadCurrentResults();return;
   }
   output.textContent='BrepMFR 자동 진단 '+(task.status||'대기')+' · '+(task.message||'');
  }catch(err){if(sameCad())output.textContent='ML 자동 진단 상태 확인 실패: '+err.message;return;}
  await sleep(1000);
 }
 if(sameCad())output.textContent='ML 자동 진단 대기 시간 초과. 수동 실행으로 다시 시도할 수 있습니다.';
}

$('brepMlRunBtn').onclick=async()=>{
 const output=$('brepMlResults');output.textContent='';
 if(!current||!jobId||!file||!brepReady){output.textContent='현재 CAD 또는 추론 준비 상태가 올바르지 않습니다.';return;}
 const cadAtStart=jobId,shaAtStart=current.sha256,selectedFile=file,generation=autoMlGeneration;
 const stillCurrent=()=>jobId===cadAtStart&&current?.sha256===shaAtStart&&file===selectedFile&&generation===autoMlGeneration;
 brepRunning=true;$('brepMlRunBtn').disabled=true;
 output.textContent='기존 학습 가중치로 추론 실행 중입니다. CAD 사실 및 FEA 결과는 변경하지 않습니다.';
 try{
  const res=await fetch('/api/ml/run/'+cadAtStart,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:selectedFile});
  const request=await res.json();if(!res.ok)throw Error(request.error||`HTTP ${res.status}`);
  if(!stillCurrent())return;
  let end=null;
  for(let i=0;i<240;i++){
   await sleep(1000);if(!stillCurrent())return;
   const state=await get('/api/ml/status/'+request.id);
   if(!stillCurrent())return;
   if(state.status==='failed')throw Error(state.message);
   if(state.status==='complete'){end=state.result;break;}
   output.textContent='BrepMFR CPU 추론 중… '+(state.message||'');
  }
  if(!stillCurrent())return;
  if(!end)throw Error('BrepMFR 응답 제한시간 초과');
  if(!renderBrepResult(end,shaAtStart))throw Error('ML 결과 안전성/해시/면 정보 검증 실패');
  status('실험 ML 추론 완료','BrepMFR 예측을 참고용으로 표시했습니다. 확정 구조 판정은 하지 않습니다.');
 }catch(err){if(stillCurrent()){output.textContent='실험 ML 진단 실패: '+err.message;status('ML 진단 실패',err.message,true);}}
 finally{if(generation===autoMlGeneration){brepRunning=false;loadBrepPreflight();loadCurrentResults();}}
};
// Read-only evidence-based agent; no real LLM or solver call.
$('agentRunBtn').onclick=async()=>{
 const target=$('agentResult'),btn=$('agentRunBtn');
 const expected=jobId,sha=current?.sha256,selection=stepSelectionVersion;
 const externalOptIn=$('agentLLMOptIn')?.checked===true;
 if($('agentLLMOptIn'))$('agentLLMOptIn').checked=false; // One explicit consent per request.
 const restore=feaRestoreGeneration,generation=++gfAgentGeneration;
 const restoredRunAtRequest=gfRestoredRunId;
 const same=()=>jobId===expected&&current?.sha256===sha&&
                  stepSelectionVersion===selection&&feaRestoreGeneration===restore&&
                  gfAgentGeneration===generation&&gfRestoredRunId===restoredRunAtRequest;
 if(!expected||!sha){target.textContent='STEP CAD를 먼저 분석하세요.';return;}
 btn.disabled=true;target.textContent='현재 CAD·ML·FEA 원본 근거를 다시 검증하고 있습니다.';
 try{
  const data=externalOptIn?
    await get('/api/agent/evidence/'+expected+'?llm=1',20000,
              {'X-GeoField-LLM-Opt-In':'1'}):
    await get('/api/agent/evidence/'+expected);
  if(!same())return;
  const llm=data?.llm||{};
  const externalConnected=(data?.mode==='rules_plus_llm'&&externalOptIn&&
    llm.connected===true&&llm.executed===true&&llm.provider==='openai'&&
    llm.status==='external_explanation_only'&&
    typeof llm.explanation==='string'&&llm.explanation.length>0&&llm.explanation.length<=1600);
  const rulesOnly=(data?.mode==='rules_only'&&llm.connected===false&&llm.executed===false);
  if(data?.schema!=='geofield-evidence-agent-v1'||data.cad_sha256!==sha||
     (!rulesOnly&&!externalConnected)||data.fea?.safety_certified!==false)
   throw Error('에이전트의 CAD 원본·실행 모드·출처 계약이 올바르지 않습니다.');
  target.textContent='';
  $('agentConnection').textContent=externalConnected?
    '규칙 검증 완료 · 외부 LLM 설명 요청 성공 (계산 수치와 별도)':
    '근거 분석 엔진 연결 확인 · rules_only (규칙 기반) · 외부 LLM 미연결';
  target.append(textKV('연결 상태',externalConnected?
    '규칙 검증 + 외부 LLM 참고 설명 (구조 승인 아님)':
    '규칙 기반 분석 · 외부 LLM 미연결'));
  target.append(textKV('CAD 원본 SHA',sha));
  const restored=data.restore_evidence;
  if(restoredRunAtRequest){
   if(restored?.schema!=='geofield-agent-restored-context-v1'||
      restored.status!=='verified_restored_read_only'||
      restored.read_only!==true||restored.ml_history_restored!==false||
      restored.run_id!==restoredRunAtRequest||restored.cad_sha256!==sha||
      restored.case_sha256!==data.fea?.case_sha256||
      restored.run_id!==data.fea?.run_id||
      data.fea?.status!=='INP_STA_FRD_reverified')
    throw Error('복원된 과거 FEA의 원본 실행 ID·조건 SHA 검증 실패: AI 결과 표시 차단');
   target.append(textKV('FEA 복원 출처',
      '읽기 전용 과거 계산 · 원본 재검증 완료 · 신규 계산 아님'));
   target.append(textKV('복원된 연구 ML 기록',
      '현재 실행에서 미확인 · 복원했다고 간주하지 않음'));
  }else if(restored){
   if(restored.schema!=='geofield-agent-restored-context-v1'||
      restored.status!=='not_restored'||restored.read_only!==false)
    throw Error('현재 세션과 응답의 FEA 복원 상태가 일치하지 않습니다.');
  }
  const features=data.cad_features;
  if(!features||features.schema!=='geofield-agent-cad-features-v1'||
     features.cad_sha256!==sha||features.cad_job_id!==expected||
     features.ml_face_ordinals_are_cad_face_ids!==false||
     features.fea_hotspots_verified!==false||
     !Array.isArray(features.candidates)||
     features.candidates.length!==features.candidate_count)
    throw Error('에이전트 형상 후보의 CAD 원본·면 대응 검증 계약 오류');
  target.append(textKV('CAD 실측 검토 후보',features.candidate_count+'개 · 위험 확정 아님'));
  const present=new Set(app.mesh?.faceIDs||[]);
  features.candidates.slice(0,12).forEach(feature=>{
   const faceIDs=feature.face_ids;
   const linkable=feature.face_mapping_status==='verified_in_current_cad_mesh'&&
     Array.isArray(faceIDs)&&faceIDs.length>0&&faceIDs.length<=128&&
     faceIDs.every(x=>Number.isInteger(x)&&x>=0&&present.has(x));
   const card=document.createElement(linkable?'button':'div');card.className='finding';
   const title=document.createElement('strong');title.textContent=String(feature.title||'CAD 검토 후보');
   const measured=document.createElement('small');
   measured.textContent='CAD 측정 근거: '+String(feature.measured_evidence||'미확인');
   const mapping=document.createElement('small');
   mapping.textContent=linkable?'현재 CAD 3D 면 검증됨 · 선택하면 강조':
       '3D 면 위치 미검증 · 면 선택 차단';
   const note=document.createElement('small');
   note.textContent='확인 방법: '+String(feature.next_check||'별도 검증 필요');
   card.append(title,measured,mapping,note);
   if(linkable)card.onclick=()=>{
     if(!same()||!app.mesh||faceIDs.some(id=>!app.mesh.faceIDs.includes(id)))return;
     app.selected=faceIDs.slice();refreshSelected();tabTo('geometry');
     status('CAD 측정 검토 위치',String(feature.title||'CAD 특징')+' · 실제 위험 판정 아님');
   };
   target.append(card);
  });
  const ml=data.ml||{};
  target.append(textKV('ML','연구용 '+(ml.status||'미실행')+' · 안전 판단에 미사용'));
  const mlCompare=ml.cad_comparison;
  if(mlCompare){
   if(mlCompare.face_mapping_verified!==false||
      mlCompare.cad_fea_conclusion_allowed!==false)
    throw Error('ML과 CAD 면 대응 검증 계약 위반');
   if(mlCompare.status==='aggregate_only_no_face_correspondence'){
    if(!Number.isInteger(mlCompare.cad_review_candidate_count)||
       mlCompare.cad_review_candidate_count<0||
       !Number.isInteger(mlCompare.ml_predicted_face_count)||
       mlCompare.ml_predicted_face_count<0||
       ml.model_version_verified!==false)
     throw Error('ML 연구용 결과의 개수·모델 검증 상태 오류');
    target.append(textKV('CAD·ML 후보 비교',
      'CAD 실측 검토 '+mlCompare.cad_review_candidate_count+'개 · ML 내부 예측 면 '+
      mlCompare.ml_predicted_face_count+'개 (서로 다른 단위 · 일치율 아님)'));
    target.append(textKV('ML 모델 버전',
      String(ml.model_version||'not_reported')+' · 보고값, 가중치·정확도 미검증'));
    target.append(textKV('형상 예측 검증 상태',
      'CAD 3D 면 ↔ ML 내부 face_ordinal 대응 미검증 · 구조 판단 차단'));
   }
  }
  const fea=data.fea||{};
  if(fea.status==='INP_STA_FRD_reverified'){
   if(!(/^[0-9a-f]{32}$/.test(String(fea.run_id||'')))||
      !(/^[0-9a-f]{64}$/.test(String(fea.case_sha256||'')))||
      !Number.isFinite(fea.maximum_von_mises_mpa)||fea.maximum_von_mises_mpa<0||
      !Number.isFinite(fea.maximum_displacement_mm)||fea.maximum_displacement_mm<0)
     throw Error('FEA 실행·수치 식별값 오류');
   target.append(textKV('실제 FEA 실행',fea.run_id+' · '+fea.element_type));
   target.append(textKV('최대 응력 / 변위',
       fea.maximum_von_mises_mpa+' MPa / '+fea.maximum_displacement_mm+' mm'));
  }else target.append(textKV('실제 FEA','동일 실행 재검증 미완료 · 수치 표시 차단'));
  const spatial=data.fea_spatial;
  if(spatial?.status==='verified_frd_surface_peak_positions'){
   if(fea.status!=='INP_STA_FRD_reverified'||
      spatial.run_id!==fea.run_id||spatial.case_sha256!==fea.case_sha256||
      spatial.cad_sha256!==sha||spatial.cad_face_attribution_verified!==false)
     throw Error('FEA 표면 위치와 실제 계산의 실행 ID·CAD·조건이 다릅니다.');
   for(const [name,peak] of [['FRD 표면 최대 응력 위치',spatial.stress_peak],
                              ['FRD 표면 최대 변위 위치',spatial.displacement_peak]]){
    if(!peak||!Array.isArray(peak.position_mm)||peak.position_mm.length!==3||
       peak.position_mm.some(x=>!Number.isFinite(x))||
       !Number.isFinite(peak.value)||peak.value<0||
       !peak.cad_face_proximity)
      throw Error('원본 FEA 절점 위치·값의 형식이 올바르지 않습니다.');
    const proximity=peak.cad_face_proximity;
    const face=(proximity.status==='geometric_proximity_candidate_only'&&
                Number.isInteger(proximity.cad_face_id_candidate)&&
                app.mesh?.faceIDs?.includes(proximity.cad_face_id_candidate))?
               (' · 가까운 CAD 면 후보 '+proximity.cad_face_id_candidate+
                ' (좌표 근접일 뿐 검증된 귀속 아님)'):
               ' · CAD 면 귀속 미확인';
    target.append(textKV(name,peak.position_mm.map(v=>v.toFixed(4)).join(', ')+
               ' mm · '+peak.value+' '+peak.unit+face));
   }
  }else target.append(textKV('FEA 집중 위치','원본 FRD 표면 위치 검증 자료 없음 · 좌표·면 대응 미표시'));
  target.append(textKV('메시 수렴','별도 실제 메시 수렴 검증 필요'));
  if(!Array.isArray(data.findings))throw Error('에이전트 근거 목록 오류');
  data.findings.slice(0,30).forEach(entry=>{
   const item=document.createElement('div');item.className='finding';
   const title=document.createElement('strong');title.textContent=String(entry.title||'검토 항목');
   const basis=document.createElement('small');basis.textContent='근거: '+String(entry.evidence||'없음');
   const next=document.createElement('small');next.textContent='추가 확인: '+String(entry.next_check||'없음');
   item.append(title,basis,next);target.append(item);
  });
  if(externalConnected){
   target.append(textKV('외부 LLM 참고 설명 · 검증되지 않은 문장',llm.explanation));
  }else if(externalOptIn){
   target.append(textKV('외부 LLM 상태','연결하지 못했거나 인증 설정 없음 · '+String(llm.status||'rules_only')+' · 기존 규칙 분석 유지'));
  }
  const notice=document.createElement('div');notice.className='notice warn';
  notice.textContent='FEA 수치와 CAD 근거는 규칙 검증값만 사용합니다. 외부 LLM 문장은 구조적 안전·설계 개선 효과의 검증 근거가 아닙니다.';
  target.append(notice);
 }catch(error){if(same()){$('agentConnection').textContent='에이전트 응답 확인 실패 · LLM 상태도 미검증';target.textContent='에이전트 근거 검증 실패: '+error.message;}}
 finally{if(same())btn.disabled=!current||!jobId;}
};

$('reviewBtn').onclick=async()=>{
 const target=$('integrationReview');target.textContent='';
 if(!current||!jobId){target.textContent='먼저 STEP 파일을 불러오세요.';return;}
 const expectedJob=jobId,expectedSha=current.sha256,selection=stepSelectionVersion;
 const stillCurrent=()=>jobId===expectedJob&&current?.sha256===expectedSha&&stepSelectionVersion===selection;
 try{
  const r=await get('/api/integration/decision/'+expectedJob);
  if(!stillCurrent())return;
  if(r.cad_sha256!==expectedSha)throw Error('검증 결과와 현재 CAD의 식별자가 다릅니다.');
  const summary=document.createElement('div');summary.className='notice';
  summary.textContent=`측정 확인 ${r.measured_findings_count}개 · 구조 판단: FEA 미실행 · 가공성 판단: 공정 기준 없음 · ML 진단 결과는 자동 판정에서 차단`;
  target.append(summary);
  if(!r.items.length){const e=document.createElement('div');e.className='emptyline';e.textContent='추출된 형상 후보가 없습니다. 안전 또는 가공 가능 판정은 아닙니다.';target.append(e);}
  r.items.forEach(item=>{
   const d=document.createElement('button');d.className='finding';
   const strong=document.createElement('strong');strong.textContent='추가 검토 · '+item.where;
   const measured=document.createElement('small');measured.textContent='실제 CAD 측정: '+item.measured_evidence;
   const reason=document.createElement('small');reason.textContent='왜 확인?: '+item.why;
   const issue=document.createElement('small');issue.textContent='가능한 문제(미확인): '+item.possible_issue;
   const next=document.createElement('small');next.textContent='검증 방법: '+item.next_check;
   d.append(strong,measured,reason,issue,next);
   d.onclick=()=>{if(!stillCurrent()||!app.mesh)return;const ids=item.face_ids||[],valid=new Set(app.mesh.faceIDs);if(!Array.isArray(ids)||ids.some(id=>!valid.has(id)))return;app.selected=ids;refreshSelected();status('검토 위치',item.where+' · CAD 실제 면 강조 · 위험 판정 아님');};
   target.append(d);
  });
 }catch(err){if(stillCurrent())target.textContent='검증 판단 실패: '+err.message;}
};

// Simple FEA wizard. Physical load and boundary constraints remain user inputs.
const materialPresets={
 steel_generic:{label:'일반 구조용 강재',e:200000,nu:0.30},
 sus304:{label:'SUS304',e:193000,nu:0.29},
 al6061_t6:{label:'알루미늄 6061-T6',e:68900,nu:0.33}
};
function invalidateFea(message){
 resetFeaField();feaRunId=null;feaPrepared=false;feaPreparedCaseSha=null;$('feaRunBtn').disabled=true;$('feaImportPreviousBtn').disabled=true;$('feaPreviousHint').textContent='설정이 변경됐습니다. 조건을 다시 저장하세요.';
 $('feaStressValue').textContent='미해석';$('feaDispValue').textContent='미해석';$('feaBCValue').textContent='조건 변경';
 gfFeaTableClear('현재 조건이 변경됐습니다. 실제 FEA 계산을 실행해야 새로운 응력·변위를 확인할 수 있습니다.');
 feaArchiveVerified=null; ++feaArchiveSelectedGeneration;
 $('feaArchive3DPreviewBtn').disabled=true; $('feaArchivedRestoreBtn').disabled=true;
 r186ClearView();
 $('feaRunStatus').textContent=message||'조건 변경: 저장된 해석 조건이 무효입니다. 다시 저장하세요.';draw();
}
function refreshEasyMaterial(){
 const id=$('feaMaterialPreset').value,material=materialPresets[id];
 $('feaAdvanced').hidden=id!=='custom';
 $('feaMaterialInfo').textContent=material?`${material.label} 참고 물성: E ${material.e.toLocaleString()} MPa · ν ${material.nu}. 실제 재료의 등급·상태를 확인하세요.`:id==='custom'?'사용자 지정 재료의 이름·탄성계수·포아송비를 고급 설정에 입력하세요.':'사용한 재료를 선택하세요. STEP 형상만으로 소재를 판단하지 않습니다.';draw();
}
function refreshEasyLoad(){
 const mode=$('feaLoadMode').value,ex=mode==='example_100n',byMass=mode==='mass_kg';
 $('feaLoadQuantityLabel').hidden=ex;
 $('feaLoadQuantityLabel').firstChild.textContent=byMass?'장착 물체 질량 (kg)':'실제 하중 (N)';
 $('feaLoadQuantity').placeholder=byMass?'예: 2 (2kg)':'예: 100';
 $('feaForceInfo').textContent=ex?'시연용 100N입니다. 실제 물건의 하중이나 구조 안전성을 나타내지 않습니다.':byMass?'질량(kg) × 9.80665로 정적인 중력 하중(N)을 계산합니다. 충격·가속도 미포함.':'실제 사용 조건에서 계산하거나 측정한 총 힘(N)을 입력하세요.';draw();
}
$('feaOwnWeight').addEventListener('change',()=>{invalidateFea('자중 적용 설정이 변경되어 FEA 조건을 다시 저장해야 합니다.');refreshLoadLegend();});
$('feaMaterialPreset').addEventListener('change',()=>{refreshEasyMaterial();invalidateFea();});
$('feaLoadMode').addEventListener('change',()=>{refreshEasyLoad();invalidateFea();});
for(const id of ['feaLoadQuantity','feaDirectionMode','feaMeshQuality','feaMaterial','feaYoung','feaPoisson'])$(id).addEventListener('input',()=>invalidateFea());
refreshEasyMaterial();refreshEasyLoad();
function markFeaFaces(which){
 if(!current||!app.mesh){status('CAD 필요','먼저 STEP 파일을 불러오세요.',true);return;}
 const valid=new Set(app.mesh.faceIDs);const choices=[...new Set(app.selected)];
 if(!choices.length||choices.some(x=>!valid.has(x))){status('면 선택 필요','3D 화면에서 CAD 면을 먼저 클릭하세요.',true);return;}
 const other=which==='fixed'?feaLoaded:feaFixed;
 if(choices.some(x=>other.includes(x))){
  const error='고정 면과 하중 면이 겹칩니다. 고정되는 부분과 힘을 받는 다른 면을 각각 선택해야 합니다.';
  $('feaPrepared').textContent=error;status('FEA 면 설정 오류',error,true);return;
 }
 if(which==='fixed'){feaFixed=choices;$('feaFixedIds').textContent=choices.join(', ')}
 else{feaLoaded=choices;$('feaLoadIds').textContent=choices.join(', ')}
 invalidateFea('선택 면이 변경되어 FEA 조건을 다시 저장해야 합니다.');
 $('feaPrepared').textContent=feaFixed.length&&feaLoaded.length?'고정 면 '+feaFixed.join(', ')+' · 하중 면 '+feaLoaded.join(', ')+' · 면 설정 정상 · 조건 저장을 눌러 주세요.':'고정 면 '+(feaFixed.join(', ')||'미설정')+' · 하중 면 '+(feaLoaded.join(', ')||'미설정')+' · 남은 면을 선택해 주세요.';
 refreshSelected();status('FEA 면 지정',which==='fixed'?'고정 면 '+choices.join(', '):'하중 면 '+choices.join(', '));
}
$('feaSetFixed').onclick=()=>markFeaFaces('fixed');
$('feaSetLoad').onclick=()=>markFeaFaces('loaded');
$('feaPrepareBtn').onclick=async()=>{
 if(!current||!jobId){status('CAD 필요','먼저 STEP 파일을 분석하세요.',true);return;}
 if(!feaFixed.length||!feaLoaded.length){$('feaPrepared').textContent='3D 화면에서 고정 면과 하중 면을 각각 지정해 주세요.';return;}
 if(feaFixed.some(x=>feaLoaded.includes(x))){$('feaPrepared').textContent='고정 면과 하중 면은 서로 달라야 합니다.';return;}
 const material_key=$('feaMaterialPreset').value;
 if(!material_key){$('feaPrepared').textContent='사용한 재료를 선택하세요.';return;}
 if($('feaOwnWeight').checked&&material_key==='custom'){$('feaPrepared').textContent='직접 입력 재료는 검증된 밀도 입력 전 자중 계산을 지원하지 않습니다.';return;}
 const load_mode=$('feaLoadMode').value;
 const request={material_key,load_mode,direction_key:$('feaDirectionMode').value,mesh_quality:$('feaMeshQuality').value,fixed_face_ids:feaFixed,load_face_ids:feaLoaded,apply_self_weight:$('feaOwnWeight').checked};
 if(material_key==='custom'){
  if(!['feaMaterial','feaYoung','feaPoisson'].every(k=>$(k).value.trim())){$('feaPrepared').textContent='사용자 지정 재료 물성을 모두 입력하세요.';return;}
  Object.assign(request,{material:$('feaMaterial').value.trim(),young_modulus_mpa:Number($('feaYoung').value),poisson_ratio:Number($('feaPoisson').value)});
 }
 if(load_mode!=='example_100n'){
  const value=$('feaLoadQuantity').value.trim();
  if(!value||!Number.isFinite(Number(value))||Number(value)<=0){$('feaPrepared').textContent='실제 질량(kg) 또는 총하중(N)을 입력하세요.';return;}
  if(load_mode==='mass_kg')request.mass_kg=Number(value);else request.total_force_n=Number(value);
 }
 try{
  const out=await post('/api/fea/prepare/'+jobId,request);
  if(out.cad_sha256!==current.sha256)throw Error('다른 CAD의 조건이 전달되었습니다.');
  feaPrepared=true;feaPreparedCaseSha=out.case_sha256;meshSeriesReset();
  $('feaStressValue').textContent='미해석';$('feaDispValue').textContent='미해석';$('feaBCValue').textContent='설정 저장';
  feaRunId=null;resetFeaField();
  $('feaRunBtn').disabled=!feaReady||!file;$('feaImportPreviousBtn').disabled=false;
  const previewJob=jobId,previewCase=feaPreparedCaseSha;
  $('feaPreviousHint').textContent='기존 계산의 저장 조건을 확인하고 있습니다.';
  get('/api/fea/previous_overview/'+previewJob).then(info=>{
    if(jobId===previewJob&&feaPreparedCaseSha===previewCase){
      $('feaPreviousHint').textContent=info.detail;
    }
  }).catch(e=>{
    if(jobId===previewJob&&feaPreparedCaseSha===previewCase)
      $('feaPreviousHint').textContent='이전 결과 검색 오류: '+e.message;
  });
  $('feaRunStatus').textContent=feaReady?'현재 CAD로 실제 FEA를 실행할 수 있습니다. 결과는 조건과 메시 품질에 따라 달라집니다.':'Gmsh Python + CalculiX가 미탐지되어 계산은 실행할 수 없습니다. 조건 저장만 완료했습니다.';
  const mat=out.material;
  const magnitude=out.boundary_conditions.total_force_n;
  const size=out.mesh_request.target_element_size_mm;
  $('feaPrepared').textContent=`조건 저장 · ${mat.name} (E ${mat.young_modulus_mpa.toLocaleString()} MPa, ν ${mat.poisson_ratio}) · 하중 ${magnitude} N · 메시 약 ${size} mm (초기 자동 추천) · 고정 면 ${feaFixed.join(',')} / 하중 면 ${feaLoaded.join(',')} · 미해석`;
  status('FEA 조건 준비 완료','물성·방향·메시를 적용했습니다. 솔버 계산은 별도 실행해야 합니다.');await loadCurrentResults();
 }catch(err){invalidateFea();$('feaPrepared').textContent='FEA 조건 오류: '+err.message;status('FEA 조건 검증 실패',err.message,true)}
};

$('feaImportPreviousBtn').onclick=async()=>{
 if(!jobId||!current||!feaPrepared||!feaPreparedCaseSha)return;
 const originalId=jobId,originalCase=feaPreparedCaseSha,originalSha=current.sha256;
 const selection=stepSelectionVersion,restore=feaRestoreGeneration;
 const sameSelection=()=>jobId===originalId&&current?.sha256===originalSha&&
   feaPrepared===true&&feaPreparedCaseSha===originalCase&&
   stepSelectionVersion===selection&&feaRestoreGeneration===restore;
 $('feaImportPreviousBtn').disabled=true;
 $('feaRunStatus').textContent='이전 실제 CalculiX 계산의 입력(.inp)·상태(.sta)·절점 결과(.frd)를 다시 검증하고 있습니다.';
 try{
  const linked=await post('/api/fea/import_previous/'+originalId,{});
  if(!sameSelection())return;
  if(!/^[0-9a-f]{32}$/.test(String(linked?.id||'')))throw Error('이전 계산 실행 ID가 올바르지 않습니다.');
  const task=await get('/api/fea/status/'+linked.id);
  if(!sameSelection())return;
  const result=task.result;
  if(task.id!==linked.id||task.cad_job_id!==originalId||task.cad_sha256!==originalSha||task.case_sha256!==originalCase||
     task.status!=='complete'||result?.cad_sha256!==originalSha||result?.case_sha256!==originalCase)
    throw Error('현재 CAD/FEA 설정과 가져온 계산 결과가 일치하지 않습니다.');
  resetFeaField();
  $('feaStressValue').textContent=result.results.maximum_nodal_von_mises_mpa.toFixed(3)+' MPa';
  $('feaDispValue').textContent=result.results.maximum_displacement_mm.toFixed(6)+' mm';
  $('feaRunStatus').textContent='이전 실제 CalculiX 결과를 검증 후 연결했습니다. 새 해석을 실행한 것은 아닙니다. · 최대 응력 '+result.results.maximum_nodal_von_mises_mpa.toFixed(3)+' MPa · 최대 변위 '+result.results.maximum_displacement_mm.toFixed(6)+' mm · 구조 안전·메시 수렴 검증 아님';
  if(result.field_visualization?.available){
   try{const field=await get('/api/fea/field/'+linked.id);if(!sameSelection())return;setFeaField(field,originalSha,originalCase,linked.id,result.results);}
   catch(e){if(sameSelection())$('feaContourStatus').textContent='수치 결과는 연결됐으나 3D 분포를 열지 못했습니다: '+e.message;}
  }
  if(!sameSelection())return;
  feaRunId=linked.id;$('feaPreviousHint').textContent='검증 완료: 실제 CalculiX 파일을 현재 조건에 연결했습니다.';await loadCurrentResults();status('이전 실제 FEA 결과 연결','기존 솔버 근거 파일 검증 성공 · 다시 계산한 결과 아님');
 }catch(e){if(sameSelection()){$('feaRunStatus').textContent='기존 결과 연결 불가: '+e.message;$('feaPreviousHint').textContent=e.message;status('FEA 결과 연결 실패',e.message,true);}}
 finally{if(sameSelection())$('feaImportPreviousBtn').disabled=!feaPrepared||!current;}
};
// GeoField R18.8 explicitly approved serial real mesh jobs
let meshSeriesId=null,meshSeriesPlan=null,meshSeriesBusy=false;
function gfMeshSensitivityLabel(analysis){
 if(!analysis || analysis.status!=='verified_three_mesh_sensitivity_only' ||
    analysis.solver_evidence!=='each_calculix_run_revalidated' ||
    analysis.same_physical_case!==true)return '메시 민감도 검증 자료 없음 · 계산 완료를 수렴으로 볼 수 없습니다.';
 const d=analysis.numeric_stability_diagnostic||{};
 const steps=analysis.adjacent_changes;
 if(!Array.isArray(steps)||steps.length!==2||d.threshold_percent!==5 || typeof d.passes!=='boolean')
  return '메시 진단 값 불완전 · 수렴 판정 불가';
 const values=steps.flatMap(x=>[x?.stress_relative_change_percent,x?.displacement_relative_change_percent]);
 if(values.some(x=>!Number.isFinite(x)||x<0))return '메시 진단 수치 누락 · 수렴 판정 불가';
 // Cross-branch FEA contract: A's real-solver screen ALSO requires
 // measured INP refinement and equal force/moment application across meshes.
 // Legacy results lacking either check cannot be labelled stable.
 const load=analysis.actual_load_moment_comparability||{},mesh=analysis.actual_mesh_resolution_diagnostic||{};
 if(load.status!=='evaluated_from_three_verified_inp_decks'||
    mesh.status!=='measured_from_three_verified_inp_meshes'||
    typeof load.moment_comparable_for_mesh_only_review!=='boolean'||
    typeof mesh.effective_mean_edge_refinement!=='boolean'||
    typeof d.actual_inp_load_screen_passes!=='boolean')
  return '실제 INP 하중 모멘트·메시 세분화 근거 부족 · 5% 수치 안정성 판정 보류';
 if(d.actual_inp_load_screen_passes!==load.moment_comparable_for_mesh_only_review)
  return '메시 진단 값 충돌 · 실제 INP 하중 검증 결과를 다시 확인하세요.';
 const expectedPass=analysis.mesh_count_increases_with_refinement===true &&
    analysis.node_count_increases_with_refinement===true &&
    load.moment_comparable_for_mesh_only_review===true &&
    mesh.effective_mean_edge_refinement===true && values.every(x=>x<=5);
 if(d.passes!==expectedPass)return '메시 진단 값 충돌 · 실제 INP 근거와 5% 진단 조건이 다릅니다.';
 const last=steps[1],stress=last.stress_relative_change_percent,disp=last.displacement_relative_change_percent;
 const label=d.passes?'5% 수치 안정성 진단 기준 충족 (수렴 증명 아님)':'5% 수치 안정성 진단 기준 미충족 · 추가 메시 검증 필요';
 const issues=(!load.moment_comparable_for_mesh_only_review?' · 하중 모멘트 불일치':'')+
    (!mesh.effective_mean_edge_refinement?' · 실제 사면체 평균 변 길이 감소 미확인':'');
 return label+issues+' · 2→3단계 응력 '+stress.toFixed(3)+'%, 변위 '+disp.toFixed(3)+'% · 구조 안전성 판단 불가';
}

function gfMeshSpatialEvidence(analysis){
 const sp=analysis?.spatial_peak_diagnostic;
 if(!sp || sp.status==='not_evaluable' || sp.peak_positions_verified!==true)
   return '응력 집중 위치의 메시별 안정성은 확인하지 못했습니다.'+(sp?.reason?' · '+sp.reason:'');
 if(sp.status!=='verified_surface_peak_positions_only' ||
    sp.source!=='three_separately_reverified_calculix_frd_surface_fields' ||
    !Array.isArray(sp.runs_coarse_to_fine)||sp.runs_coarse_to_fine.length!==3 ||
    !Array.isArray(sp.adjacent_peak_distances_mm)||sp.adjacent_peak_distances_mm.length!==2 ||
    sp.adjacent_peak_distances_mm.some(x=>!Number.isFinite(x)||x<0) ||
    sp.runs_coarse_to_fine.some(x=>!Array.isArray(x.surface_peak_position_mm)||
      x.surface_peak_position_mm.length!==3||x.surface_peak_position_mm.some(v=>!Number.isFinite(v)) ||
      !Number.isFinite(x.surface_max_stress_mpa)))return '고응력 집중 위치 검증 자료가 불완전합니다.';
 const coords=sp.runs_coarse_to_fine.map((x,i)=>
   `${i+1}단계 표면 최고 ${x.surface_max_stress_mpa.toFixed(4)} MPa · 좌표 (${x.surface_peak_position_mm.map(v=>v.toFixed(2)).join(', ')}) mm`);
 return '실제 FRD 표면 최고 응력 위치: '+coords.join(' / ')+
   ' · 이동 거리 1→2 '+sp.adjacent_peak_distances_mm[0].toFixed(3)+
   'mm, 2→3 '+sp.adjacent_peak_distances_mm[1].toFixed(3)+
   'mm · 위치 변화만을 나타내며 수렴 증명은 아닙니다.';
}

function meshSeriesReset(){meshSeriesPlan=null;$('feaMeshSeriesStartBtn').disabled=true;$('feaMeshSeriesPlanText').textContent='현재 FEA 조건으로 메시 계획을 다시 확인하세요.';}
$('feaMeshSeriesPlanBtn').onclick=async()=>{
 meshSeriesReset();try{
  if(!jobId||!current||!feaPrepared||!file)throw Error('원본 STEP과 현재 FEA 조건을 먼저 저장하세요.');
  const d=await get('/api/fea/mesh-series/plan/'+jobId);
  if(d.cad_sha256!==current.sha256 || d.base_case_sha256!==feaPreparedCaseSha)throw Error('CAD/FEA 조건 식별자가 변경됐습니다.');
  meshSeriesPlan=d;
  $('feaMeshSeriesPlanText').textContent='메시 굵음 '+d.sizes_mm[0]+'mm → 기준 '+d.sizes_mm[1]+'mm → 미세 '+d.sizes_mm[2]+'mm. 실제 실행 시간·메모리 사용량은 사전 확정할 수 없습니다.';
  $('feaMeshSeriesStartBtn').disabled=false;
 }catch(e){$('feaMeshSeriesProgress').textContent='계획 준비 실패: '+e.message;}
};
$('feaMeshSeriesStartBtn').onclick=async()=>{
 if(meshSeriesBusy||!meshSeriesPlan||!current||!jobId||!file||!feaPrepared)return;
 const uid=jobId,sha=current.sha256;
 if(meshSeriesPlan.cad_sha256!==sha||meshSeriesPlan.base_case_sha256!==feaPreparedCaseSha){meshSeriesReset();return;}
 if(!window.confirm('실제 Gmsh·CalculiX 계산을 최대 3회 순차 실행합니다. 컴퓨터 사용량과 실행 시간이 증가하며 원본 STEP과 현재 FEA 조건 파일은 변경하지 않습니다. 진행할까요?'))return;
 meshSeriesBusy=true;$('feaMeshSeriesStartBtn').disabled=true;
 let terminalSeen=false;
 try{
  const r=await fetch('/api/fea/mesh-series/start/'+uid,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-GeoField-Mesh-Study-Confirm':'START_THREE_REAL_SOLVES','X-GeoField-Case-SHA256':meshSeriesPlan.base_case_sha256},body:file});
  const d=await r.json();if(!r.ok)throw Error(d.error||'FEA 메시 계산 시작 거절');
  meshSeriesId=d.id;$('feaMeshSeriesCancelBtn').disabled=false;
  let statusFailures=0;  for(let i=0;i<1300;i++){
   let state;
   try{
    state=await get('/api/fea/mesh-series/status/'+meshSeriesId,15000);
    statusFailures=0;
   }catch(pollError){
    statusFailures++;
    $('feaMeshSeriesProgress').textContent='상태 조회 일시 실패 ('+statusFailures+'/5): '+pollError.message+
      '\n서버에서 CalculiX 계산이 계속 진행 중일 수 있습니다. 중복 실행하지 마세요.';
    if(statusFailures>=5)throw Error('상태 조회 연속 실패. CalculiX 계산이 중단됐다는 의미는 아닙니다. 기존 실행 ID로 재확인해야 합니다.');
    await sleep(2000);
    continue;
   }
   $('feaMeshSeriesProgress').textContent='상태: '+state.status+'\n완료: '+state.completed+'/'+state.total+'\n현재 단계: '+((state.current_index??0)+1)+'\n'+state.message+(state.error?'\n오류: '+state.error:'')+'\n성공 기록: '+(state.analysis_snapshot_ids||[]).join(', ');
   if(['complete','cancelled','failed','verification_failed'].includes(state.status)){
    terminalSeen=true;
    if(state.status==='verification_failed'){
     $('feaMeshSeriesProgress').textContent+='\n[결과 검증 실패] '+(state.verification_warning||'실제 INP/STA/FRD 및 계산 기록을 확인해야 합니다.')+'\n저장된 개별 계산 결과는 삭제되지 않았습니다.';
    }
    if(state.status==='complete'){
     const analysis=state.study_analysis;if(analysis?.adjacent_changes){
      for(const [j,x] of analysis.adjacent_changes.entries()){
       const pct=(v)=>typeof v==='number'&&Number.isFinite(v)&&v>=0?v.toFixed(3)+'%':'계산 불가';
       $('feaMeshSeriesProgress').textContent+='\n'+(j+1)+'→'+(j+2)+' 단계 응력 변화율: '+pct(x.stress_relative_change_percent)+', 변위 변화율: '+pct(x.displacement_relative_change_percent);
      }
      if(analysis.warning)$('feaMeshSeriesProgress').textContent+='\n'+analysis.warning;
     }
     $('feaMeshSeriesProgress').textContent+='\n[메시 진단] '+gfMeshSensitivityLabel(analysis);
     $('feaMeshSeriesProgress').textContent+='\n[응력 위치] '+gfMeshSpatialEvidence(analysis);
     if(state.verification_warning)$('feaMeshSeriesProgress').textContent+='\n[재검증] '+state.verification_warning;
     $('feaMeshSeriesProgress').textContent+='\n3개 실행은 각각 별개 메시 결과입니다. 3D 컬러 화면은 별도로 표시한 단일 실행의 결과입니다. 메시 연구의 마지막 단계로 자동 전환되는 것은 아닙니다.';
    }
    break;
   }
   await sleep(1000);
  }
  if(!terminalSeen)$('feaMeshSeriesProgress').textContent+='\n상태 확인이 종료됐지만 서버 계산의 종료는 확인되지 않았습니다. 중복 시작하지 마세요.';
 }catch(e){$('feaMeshSeriesProgress').textContent='연속 계산 요청/상태 조회 실패: '+e.message+'\n서버가 계속 계산 중일 수 있습니다. 새 계산을 중복 시작하지 마세요.';}
 finally{
  meshSeriesBusy=false;
  // A failed HTTP poll is not a cancelled/finished solver run.
  // Keep the existing cancel action available until a terminal state was observed.
  $('feaMeshSeriesCancelBtn').disabled=terminalSeen || !meshSeriesId;
  meshSeriesReset();
 }
};
$('feaMeshSeriesCancelBtn').onclick=async()=>{
 if(!meshSeriesId)return;
 if(!window.confirm('현재 실행 중인 CalculiX 계산은 강제 종료하지 않고, 완료 후 나머지 단계만 중단합니다. 진행할까요?'))return;
 try{const r=await post('/api/fea/mesh-series/cancel/'+meshSeriesId,{confirm:'STOP_AFTER_CURRENT'});$('feaMeshSeriesProgress').textContent+='\n'+r.message;}
 catch(e){$('feaMeshSeriesProgress').textContent+='\n중단 요청 실패: '+e.message;}
};

$('feaRunBtn').onclick=async()=>{
 if(!current||!jobId||!file||!feaReady||!feaPrepared||feaRunId==='RUNNING')return;
 const jobAtStart=jobId,shaAtStart=current.sha256,caseAtStart=feaPreparedCaseSha;
 const selectedAtStart=stepSelectionVersion,restoreAtStart=feaRestoreGeneration;
 const sameSelection=()=>jobId===jobAtStart&&current?.sha256===shaAtStart&&
    feaPrepared===true&&feaPreparedCaseSha===caseAtStart&&
    stepSelectionVersion===selectedAtStart&&feaRestoreGeneration===restoreAtStart;
 const sameRun=()=>sameSelection()&&feaRunId==='RUNNING';
 if(!window.confirm('현재 CAD에서 실제 Gmsh/CalculiX FEA를 실행할까요? 선택한 면·재료·하중에 따라 결과가 달라지며, 구조 안전 인증으로 사용할 수 없습니다.'))return;
 resetFeaField();feaRunId='RUNNING';$('feaRunBtn').disabled=true;$('feaImportPreviousBtn').disabled=true;$('feaStressValue').textContent='해석 중';$('feaDispValue').textContent='해석 중';
 $('feaRunStatus').textContent='원본 STEP 해시 재검증 및 실제 메시·해석 실행 대기 중';
 try{
  const response=await fetch('/api/fea/run/'+jobAtStart,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
  const run=await response.json();
  if(!sameRun())return;
  if(!response.ok)throw Error(run.error||'FEA 요청 거절');
  if(!/^[0-9a-f]{32}$/.test(String(run.id||''))||run.cad_sha256!==shaAtStart)throw Error('해석 실행 ID 또는 대상 CAD 식별 오류');
  for(let i=0;i<240;i++){
    if(!sameRun())return;
    const state=await get('/api/fea/status/'+run.id);
    if(!sameRun())return;
    if(state.id!==run.id||state.cad_job_id!==jobAtStart||state.cad_sha256!==shaAtStart||state.case_sha256!==caseAtStart)
      throw Error('FEA 상태의 CAD·조건·실행 식별자가 다릅니다.');
    if(state.status==='failed')throw Error(state.message);
    if(state.status==='complete'){
      const d=state.result;
      if(!sameRun()||d.cad_sha256!==shaAtStart||d.case_sha256!==caseAtStart)
        throw Error('FEA 조건 변경 또는 결과 식별자 불일치');
      if(!Number.isFinite(d.results?.maximum_nodal_von_mises_mpa)||!Number.isFinite(d.results?.maximum_displacement_mm)||
         d.results.maximum_nodal_von_mises_mpa<0||d.results.maximum_displacement_mm<0)
        throw Error('실제 FRD 응력·변위 수치가 유효하지 않습니다.');
      $('feaStressValue').textContent=String(d.results.maximum_nodal_von_mises_mpa)+' MPa';$('feaDispValue').textContent=String(d.results.maximum_displacement_mm)+' mm';
      gfFeaTableShow('현재 CAD · 실제 CalculiX 새 계산',d.results.maximum_nodal_von_mises_mpa,d.results.maximum_displacement_mm,d.mesh?.tetrahedron_count,d.mesh?.node_count,run.id,d.field_visualization?.available,d.load_equilibrium_audit);
      const loadSummary=gfLoadAuditSummary(d.load_equilibrium_audit);
      $('feaRunStatus').textContent=`실제 CalculiX 결과: 최대 절점 von Mises ${String(d.results.maximum_nodal_von_mises_mpa)} MPa · 최대 변위 ${String(d.results.maximum_displacement_mm)} mm · ${d.mesh.tetrahedron_count}개 사면체 / ${d.mesh.node_count}개 노드. 메시 수렴·응력 특이점 미검증으로 안전 판정은 보류합니다.`+(loadSummary?.shifted?' · 하중 중심/모멘트 이동 확인: 아래 결과표 참조':'');
      status('FEA 계산 완료 · 인증 아님','실제 솔버 결과 파싱 성공 · 별도 검증 필요');
      if(d.field_visualization?.available){
        try{
          const contour=await get('/api/fea/field/'+run.id);
          if(!sameRun())return;
          setFeaField(contour,shaAtStart,caseAtStart,run.id,d.results);
        }catch(fieldError){if(sameRun())$('feaContourStatus').textContent='FEA 수치 계산은 완료됐지만 3D 분포 로딩 불가: '+fieldError.message;}
      }else{$('feaContourStatus').textContent='계산은 완료됐지만 이 메시에는 표시 가능한 3D 필드가 없습니다.';}
      if(!sameRun())return;
      feaRunId=run.id;await loadCurrentResults();return;
    }
    if(!sameRun())return;
    $('feaRunStatus').textContent=state.message||'실제 솔버 실행 중';await sleep(1000);
  }
  throw Error('FEA 상태 확인 제한 시간 초과. 솔버 상태 및 오류 로그를 확인하세요.');
 }catch(err){if(sameRun()){$('feaStressValue').textContent='미해석';$('feaDispValue').textContent='미해석';$('feaRunStatus').textContent='FEA 해석 실패 또는 차단: '+err.message;status('FEA 완료 실패',err.message,true);feaRunId=null;}}
 finally{if(sameSelection()){$('feaRunBtn').disabled=!feaReady||!feaPrepared||!current;void loadCurrentResults();}}
};




// GeoField R18.4 independently verified numerical FEA history view
// GeoField R18.3 FEA direct verified history access
async function restoreArchivedFea(item,trigger){
     if(feaRunId==='RUNNING'){status('복원 불가','FEA 계산이 진행 중입니다.',true);return;}
     const selectionVersion=stepSelectionVersion,restoreGeneration=++feaRestoreGeneration;
     const requireSameSelection=()=>{
      if(stepSelectionVersion!==selectionVersion||feaRestoreGeneration!==restoreGeneration)
       throw Error('복원 검증 중 다른 STEP/이전 결과를 선택했습니다. 기존 응답은 표시하지 않습니다.');
     };
     let compared='', historicalRun=null;
     try{
      const snapshot=await get('/api/history/item/'+item.id);
      requireSameSelection();
      if(snapshot?.cad?.sha256!==item.cad_sha256 || snapshot?.fea?.state!=='complete')
       throw Error('저장 기록의 CAD SHA 또는 완료 상태가 목록과 일치하지 않습니다.');
      const setup=snapshot?.fea?.setup;
      if(!setup)throw Error('보존된 계산 조건 요약을 읽지 못했습니다.');
      historicalRun=snapshot?.fea?.result_run_id;
      if(!/^[0-9a-f]{32}$/.test(String(historicalRun||'')))
       throw Error('기록의 실제 CalculiX 실행 ID가 누락됐습니다. 다른 결과를 추측해 사용하지 않습니다.');
      const oldMass=setup.external_mass_kg===null||setup.external_mass_kg===undefined?'사용자 입력 힘':setup.external_mass_kg+' kg';
      const nowMass=$('feaLoadMode').value==='mass_kg'?$('feaLoadQuantity').value+' kg':'사용자 입력 힘';
      compared='이전 계산 재료: '+String(setup.material)+'\n이전 질량: '+oldMass+'\n이전 고정/하중 면: '+(setup.fixed_faces||[]).join(',')+' / '+(setup.load_faces||[]).join(',')+'\n현재 설정 재료: '+$('feaMaterialPreset').selectedOptions[0]?.textContent+'\n현재 입력 질량: '+nowMass+'\n현재 고정/하중 면: '+feaFixed.join(',')+' / '+feaLoaded.join(',')+'\n\n';
     }catch(e){
       if(stepSelectionVersion!==selectionVersion||feaRestoreGeneration!==restoreGeneration)return;
       status('복원 조건 비교 실패',e.message,true);return;
     }
     if(!window.confirm(compared+'이전 계산의 검증된 조건으로 현재 화면을 교체할까요?\n원본 STEP·계산 파일·저장된 기록은 삭제하지 않습니다.'))return;
     trigger.disabled=true;status('과거 계산 검증','저장된 CAD와 CalculiX INP·STA·FRD를 확인 중입니다.');
     try{
      const exactRun='?run_id='+encodeURIComponent(historicalRun);
      const preview=await get('/api/fea/restore_preview/'+item.job_id+exactRun);
      requireSameSelection();
      if(preview?.run_id!==historicalRun || preview?.cad_sha256!==item.cad_sha256 ||
         (snapshot.fea.result_case_sha256!=null && preview?.case_sha256!==snapshot.fea.result_case_sha256))
       throw Error('과거 기록과 복원 CAD/조건/실행 ID의 연결이 일치하지 않습니다.');
      if(preview?.job?.sha256!==preview.cad_sha256||preview?.model?.sha256!==preview.cad_sha256||
         preview?.case?.case_sha256!==preview.case_sha256||preview?.task?.status!=='complete')
       throw Error('복원 사전 검사에서 CAD 또는 해석 케이스가 일치하지 않습니다.');
      if(!preview.model.mesh||!Array.isArray(preview.model.mesh.positions)||!Array.isArray(preview.model.mesh.triangles))
       throw Error('복원 사전 검사 중 CAD 표면 메시가 누락됐습니다.');
      if(preview.has_3d_field){
       const f=preview.field,n=f?.positions_mm?.length;
       if(!f||f.source!=='actual_calculix_ascii_frd'||f.schema!=='geofield-fea-surface-field-v1'||
          f.cad_sha256!==preview.cad_sha256||f.case_sha256!==preview.case_sha256||
          !Number.isInteger(n)||n<1||!Array.isArray(f.triangles)||!f.triangles.length||
          f.von_mises_mpa?.length!==n||f.displacements_mm?.length!==n||
          f.positions_mm.some(v=>!Array.isArray(v)||v.length!==3||v.some(x=>!Number.isFinite(x)))||
          f.von_mises_mpa.some(v=>!Number.isFinite(v)||v<0)||
          f.displacements_mm.some(v=>!Array.isArray(v)||v.length!==3||v.some(x=>!Number.isFinite(x)))||
          f.triangles.some(t=>!Array.isArray(t)||t.length!==3||t.some(x=>!Number.isInteger(x)||x<0||x>=n)))
        throw Error('복원 전 실제 FEA 메시·응력·변위·CAD 해시 검증 실패');
      }
      const recovered=await post('/api/fea/recover_bundle/'+item.job_id+exactRun,{});
      requireSameSelection();
      if(recovered.run_id!==historicalRun||recovered.run_id!==preview.run_id||recovered.case_sha256!==preview.case_sha256||
         recovered.cad_sha256!==preview.cad_sha256)throw Error('검증 중 계산 결과 식별자가 바뀌었습니다.');
      const recoveredJob=recovered.job;
      const model=recovered.model;
      const saved=recovered.case;
      const task=recovered.task;
      if(recoveredJob.sha256!==recovered.cad_sha256||model.sha256!==recovered.cad_sha256||
         saved.case_sha256!==recovered.case_sha256||task.status!=='complete'||
         task.result?.cad_sha256!==recovered.cad_sha256||task.result?.case_sha256!==recovered.case_sha256){
       throw Error('복원된 CAD/FEA 식별자 불일치');
      }
      if(!model.mesh||!Array.isArray(model.mesh.positions)||!Array.isArray(model.mesh.triangles))
       throw Error('복원된 3D CAD 메시 형식 오류');
      if(recovered.has_3d_field){
       const f=recovered.field,n=f?.positions_mm?.length;
       if(!f||f.schema!=='geofield-fea-surface-field-v1'||f.source!=='actual_calculix_ascii_frd'||
          f.cad_sha256!==recovered.cad_sha256||f.case_sha256!==recovered.case_sha256||
          !Number.isInteger(n)||n<1||!Array.isArray(f.triangles)||!f.triangles.length||f.triangles.length>180000||
          f.von_mises_mpa?.length!==n||f.displacements_mm?.length!==n||
          f.positions_mm.some(v=>!Array.isArray(v)||v.length!==3||v.some(x=>!Number.isFinite(x)))||
          f.von_mises_mpa.some(v=>!Number.isFinite(v)||v<0)||
          f.displacements_mm.some(v=>!Array.isArray(v)||v.length!==3||v.some(x=>!Number.isFinite(x)))||
          f.triangles.some(t=>!Array.isArray(t)||t.length!==3||t.some(x=>!Number.isInteger(x)||x<0||x>=n)))
        throw Error('복원된 실제 FEA 필드 구조·해시·절점 검증 실패');
      }
      // The new server returns the entire already-verified bundle in ONE response.
      // Reset and redraw only after every required field passed validation.
      requireSameSelection();cadImportGeneration++;resetModel({preserveRestore:true});file=null;$('stepFile').value='';$('pickedFile').textContent='원본 STEP 미보관 · 새 계산은 원본 파일 다시 선택';$('importBtn').disabled=true;
      jobId=recovered.cad_job_id;gfRestoredRunId=recovered.run_id;current=recoveredJob.analysis;findings=recoveredJob.findings||[];
      loadMesh(model.mesh);renderInfo(current);renderFindings();
      $('empty3d').classList.add('hidden');$('modelTitle').textContent=current.source||'복원된 CAD';
      $('resultsRefreshBtn').disabled=false;$('resultsReportBtn').disabled=false;
      $('feaSetFixed').disabled=false;$('feaSetLoad').disabled=false;$('feaPrepareBtn').disabled=false;
      $('reviewBtn').disabled=false;$('agentRunBtn').disabled=false;$('geometryDimBtn').disabled=false;
      const bc=saved.boundary_conditions||{};
      feaFixed=bc.fixed_face_ids||[];feaLoaded=bc.load_face_ids||[];
      feaPrepared=true;feaPreparedCaseSha=saved.case_sha256;feaRunId=recovered.run_id;
      $('feaFixedIds').textContent=feaFixed.join(', ')||'미설정';
      $('feaLoadIds').textContent=feaLoaded.join(', ')||'미설정';
      $('feaBCValue').textContent='고정 '+feaFixed.join(',')+' / 하중 '+feaLoaded.join(',');
      $('feaPrepared').textContent='저장된 FEA 조건 복원 · 원본 STEP은 재업로드 전까지 없음';
      $('feaRunBtn').disabled=true;$('feaImportPreviousBtn').disabled=false;
      // Restore *display* inputs from the verified solver case, not the newer
      // editable 5kg/other-material case stored on disk.
      const material=saved.material||{}, preset=saved.preset_metadata||{}, bcVals=saved.boundary_conditions||{};
      const materialKey=preset.material_key||'';
      if(['steel_generic','sus304','al6061_t6','custom'].includes(materialKey)){
       $('feaMaterialPreset').value=materialKey;
      }else{
       const materialName=String(material.name||'');
       $('feaMaterialPreset').value=materialName.includes('SUS304')?'sus304':materialName.includes('6061')?'al6061_t6':materialName.includes('구조용 강재')?'steel_generic':'custom';
      }
      if(preset.mass_kg!==undefined&&preset.mass_kg!==null){
       $('feaLoadMode').value='mass_kg';$('feaLoadQuantity').value=String(preset.mass_kg);
      }else{
       $('feaLoadMode').value='force_n';$('feaLoadQuantity').value=String(bcVals.total_force_n??'');
      }
      const vectors={'+x':[1,0,0],'-x':[-1,0,0],'+y':[0,1,0],'-y':[0,-1,0],'+z':[0,0,1],'-z':[0,0,-1]};
      const direction=bcVals.force_direction_unit||[];
      for(const [key,vector] of Object.entries(vectors)){
       if(vector.every((x,i)=>Math.abs(x-Number(direction[i]))<1e-8)){$('feaDirectionMode').value=key;break;}
      }
      refreshLoadLegend();refreshSelected();
      $('feaPrepared').textContent='복원된 실제 해석 조건 · '+String(material.name||'')+' · '+String(bcVals.total_force_n)+' N · 새 FEA 계산은 원본 STEP 재업로드 필요';
      const vals=task.result.results||{};
      if(!Number.isFinite(vals.maximum_nodal_von_mises_mpa)||!Number.isFinite(vals.maximum_displacement_mm))throw Error('검증된 결과에 응력 또는 변위값이 없습니다.');
      $('feaStressValue').textContent=String(Number(vals.maximum_nodal_von_mises_mpa))+' MPa';
      $('feaDispValue').textContent=String(Number(vals.maximum_displacement_mm))+' mm';
      $('feaRunStatus').textContent='실제 CalculiX 근거를 재검증하여 과거 계산을 복원했습니다. 새 계산이 아닙니다.';
      $('feaPreviousHint').textContent='복원 완료 · 새로운 FEA 실행은 원본 STEP을 다시 불러오세요.';
      let fieldRestored=false;
      if(task.result.field_visualization?.available){
       try{const field=recovered.field;
           if(jobId!==recovered.cad_job_id||feaPreparedCaseSha!==recovered.case_sha256)throw Error('복원 중 CAD/조건이 변경됐습니다.');
           if(!field)throw Error('검증된 3D FEA 필드가 누락됐습니다.');
           setFeaField(field,recovered.cad_sha256,recovered.case_sha256,recovered.run_id,vals);
           fieldRestored=true;
       }catch(e){$('feaContourStatus').textContent='수치 결과는 복원됐으나 3D 필드는 열리지 않았습니다: '+e.message;}
      }
      tabTo('fea');
      try{await loadCurrentResults();requireSameSelection();}catch(e){
        if(stepSelectionVersion!==selectionVersion||feaRestoreGeneration!==restoreGeneration)return;
        status('복원 완료 · 보고서 갱신 지연',e.message,true);
      }
      // Restore never auto-opts into any external paid API. The agent
      // rechecks the selected historical run/case using rules_only.
      requireSameSelection();
      if($('agentRunBtn') && gfRestoredRunId===recovered.run_id){
       void $('agentRunBtn').onclick();
      }
      status(fieldRestored?'FEA 수치·3D 필드 복원 완료':'FEA 수치 복원 완료',
              fieldRestored?'실제 FEA 표면 필드를 연결했습니다. 브라우저 응력·변위 표시를 확인하세요.':'실제 계산 수치는 복원됐지만 3D 필드 표시까지 확인되지 않았습니다. 아래 상태 메시지를 확인하세요.');
     }catch(e){
       if(stepSelectionVersion!==selectionVersion||feaRestoreGeneration!==restoreGeneration)return;
       status('FEA 복원 실패',e.message,true);
       try{const live=await get('/api/status');
         if(live.current?.job_id===item.job_id)status('복원은 서버에 적용됨 · 화면 재동기화 필요','화면 갱신 중 오류가 발생했습니다. 새로고침한 뒤 기록에서 결과를 다시 조회하세요.',true);
       }catch(_){/* Network is already unavailable; keep the original error. */}
     }
     finally{if(stepSelectionVersion===selectionVersion&&feaRestoreGeneration===restoreGeneration)trigger.disabled=false;}

}
let feaArchiveItems=[],feaArchiveOffset=0,feaArchiveTotal=0,feaArchiveRequest=0;
let feaArchiveInitialized=false; // GeoField R20 core workflow stabilization — retain verified archive when changing tabs
let feaArchiveVerified=null,feaArchiveSelectedGeneration=0;
const feaArchiveSelector=$('feaArchivedSelect');
// GeoField R18.5 read-only real FEA 3D archive preview
let r185PreviewField=null,r185PreviewProof=null,r185PreviewYaw=-0.65,r185PreviewPitch=0.4,r185PreviewZoom=1,r185PreviewDrag=null;
const r185Modal=$('feaArchivePreviewModal'),r185Canvas=$('feaArchivePreviewCanvas');
function r185Color(r){
 const stops=[[35,77,181],[57,184,219],[242,223,77],[241,131,49],[193,55,46]];
 const x=Math.max(0,Math.min(0.999999,r))*4,k=Math.floor(x),t=x-k;
 const c=stops[k].map((v,j)=>Math.round(v*(1-t)+stops[k+1][j]*t));
 return 'rgb('+c.join(',')+')';
}
function gfPaintArchiveNodalTriangle(ctx,screen,raw,ceiling,N){
 const [a,b,c]=screen;
 function at(i,j){const u=i/N,v=j/N;return [a[0]+(b[0]-a[0])*u+(c[0]-a[0])*v,a[1]+(b[1]-a[1])*u+(c[1]-a[1])*v,raw[0]+(raw[1]-raw[0])*u+(raw[2]-raw[0])*v];}
 function cell(x,y,z){
  const avg=(x[2]+y[2]+z[2])/3;
  ctx.fillStyle=r185Color(ceiling>0?avg/ceiling:0);
  ctx.beginPath();ctx.moveTo(x[0],x[1]);ctx.lineTo(y[0],y[1]);ctx.lineTo(z[0],z[1]);ctx.closePath();ctx.fill();
 }
 for(let i=0;i<N;i++)for(let j=0;j<N-i;j++){
  cell(at(i,j),at(i+1,j),at(i,j+1));
  if(i+j<N-1)cell(at(i+1,j),at(i+1,j+1),at(i,j+1));
 }
}
function r185Close(){r185Modal.hidden=true;r185Modal.style.display='none';r185PreviewField=null;r185PreviewProof=null;}
function r185Draw(){
 if(!r185PreviewField||r185Modal.hidden)return;
 const rect=r185Canvas.getBoundingClientRect(),dpr=Math.min(2,window.devicePixelRatio||1);
 const w=Math.max(350,Math.round(rect.width*dpr)),h=Math.max(260,Math.round(rect.height*dpr));
 if(r185Canvas.width!==w||r185Canvas.height!==h){r185Canvas.width=w;r185Canvas.height=h;}
 const ctx=r185Canvas.getContext('2d');if(!ctx)throw Error('2D Canvas를 시작할 수 없습니다.');
 ctx.clearRect(0,0,w,h);
 const data=r185PreviewField,p=data.positions_mm,tri=data.triangles;
 const vals=$('feaArchivePreviewMode').value==='stress'?data.von_mises_mpa:data.displacements_mm.map(v=>Math.hypot(...v));
 const unit=$('feaArchivePreviewMode').value==='stress'?'MPa':'mm';
 const maxima=vals.reduce((m,n)=>Math.max(m,n),0),factor=Number($('feaArchivePreviewDeform').value);
 const reference=unit==='MPa'?feaStressScale(maxima,r185PreviewProof?.cad_sha256,r185PreviewProof?.run_id):null;
 const colorMax=reference?(reference.upper||1):Math.max(maxima,1e-12);
 if(reference?.error){$('feaArchivePreviewLegend').textContent=reference.error;return;}
 const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
 for(const v of p)for(let k=0;k<3;k++){lo[k]=Math.min(lo[k],v[k]);hi[k]=Math.max(hi[k],v[k]);}
  const center=(r191FocusPosition&&r191HotspotInfo&&r185PreviewProof?.snapshot_id===r191HotspotInfo.snapshot_id)?r191FocusPosition:lo.map((x,i)=>(x+hi[i])/2),size=Math.max(1e-9,...lo.map((x,i)=>hi[i]-x));
 const cy=Math.cos(r185PreviewYaw),sy=Math.sin(r185PreviewYaw),cp=Math.cos(r185PreviewPitch),sp=Math.sin(r185PreviewPitch);
 const scale=Math.min(w,h)*.65/size*r185PreviewZoom;
 const projected=p.map((v,i)=>{
  const q=v.map((x,k)=>x+factor*data.displacements_mm[i][k]-center[k]);
  const xx=q[0]*cy-q[1]*sy,depth=q[0]*sy+q[1]*cy;
  return [w/2+xx*scale,h/2-(q[2]*cp-depth*sp)*scale,q[2]*sp+depth*cp];
 });
 const order=tri.map((t,i)=>[i,(projected[t[0]][2]+projected[t[1]][2]+projected[t[2]][2])/3]);
 order.sort((a,b)=>a[1]-b[1]);
 for(const [index] of order){
  const t=tri[index],a=projected[t[0]],b=projected[t[1]],c=projected[t[2]];
  // Canvas-only archive preview: bounded barycentric interpolation from the
  // three VERIFIED nodal values, never invent an interior solver maximum.
  const divisions=tri.length<=4000?4:tri.length<=16000?2:1;
  gfPaintArchiveNodalTriangle(ctx,[a,b,c],t.map(ix=>vals[ix]),colorMax,divisions);
 }
 r191Paint(ctx,projected,w,h);
 // Gradient and unit legend are tied to surface data, not hard-coded solver maxima.
 const bw=Math.min(260*dpr,w*.6),x=24*dpr,y=h-35*dpr,g=ctx.createLinearGradient(x,0,x+bw,0);
 for(let k=0;k<=16;k++)g.addColorStop(k/16,r185Color(k/16));
 ctx.fillStyle='rgba(255,255,255,.92)';ctx.fillRect(x-9*dpr,y-24*dpr,bw+18*dpr,57*dpr);
 ctx.fillStyle=g;ctx.fillRect(x,y,bw,12*dpr);
 ctx.fillStyle='#20384d';ctx.font=`${12*dpr}px sans-serif`;
 ctx.fillText('0',x,y+25*dpr);ctx.fillText(colorMax.toPrecision(5)+' '+unit,x+bw-105*dpr,y+25*dpr);
 const proof=r185PreviewProof;
 $('feaArchivePreviewLegend').textContent='계산 ID '+proof.run_id+' · '+(proof.conditions.material||'재료 미상')+' · '+(proof.conditions.mass_kg??'별도 입력')+' kg\n'+
  '검증된 전체 최대 응력 '+String(proof.maximum_von_mises_mpa)+' MPa · 최대 변위 '+String(proof.maximum_displacement_mm)+' mm\n'+
  '화면 표면 최대 '+maxima.toPrecision(6)+' '+unit+' · 변형 배율 '+factor+'배 · 기존 CAD 작업은 변경되지 않음\n'+
  '색상 기준 '+(reference?.mode||'변위 결과별 자동')+' · 0–'+colorMax.toPrecision(6)+' '+unit+(reference?.clipped?' · 상한 초과는 빨강 포화':'')+' · 표면 노드 보간 참고 · 메시 수렴/구조 안전 판정 아님';
}
$('feaArchivePreviewClose').onclick=r185Close;
r185Modal.addEventListener('click',e=>{if(e.target===r185Modal)r185Close();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!r185Modal.hidden)r185Close();});
$('feaArchivePreviewMode').onchange=r185Draw;
$('feaArchivePreviewDeform').onchange=r185Draw;
$('feaArchivePreviewReset').onclick=()=>{r185PreviewYaw=-.65;r185PreviewPitch=.4;r185PreviewZoom=1;r191FocusPosition=null;r185Draw();};
r185Canvas.addEventListener('pointerdown',e=>{r185PreviewDrag=[e.clientX,e.clientY];r185Canvas.setPointerCapture(e.pointerId);});
r185Canvas.addEventListener('pointermove',e=>{if(!r185PreviewDrag)return;r185PreviewYaw+=(e.clientX-r185PreviewDrag[0])*.008;r185PreviewPitch=Math.max(-1.5,Math.min(1.5,r185PreviewPitch+(e.clientY-r185PreviewDrag[1])*.008));r185PreviewDrag=[e.clientX,e.clientY];r185Draw();});
for(const name of ['pointerup','pointercancel'])r185Canvas.addEventListener(name,()=>{r185PreviewDrag=null;});
r185Canvas.addEventListener('wheel',e=>{e.preventDefault();r185PreviewZoom=Math.max(.4,Math.min(4,r185PreviewZoom*(e.deltaY>0?.89:1.12)));r185Draw();},{passive:false});
$('feaArchive3DPreviewBtn').onclick=async()=>{
 const selected=feaArchiveSelector.value,proof=feaArchiveVerified,generation=feaArchiveSelectedGeneration;
 const stillSelected=()=>selected===feaArchiveSelector.value&&generation===feaArchiveSelectedGeneration&&feaArchiveVerified===proof;
 const btn=$('feaArchive3DPreviewBtn'),hint=$('feaArchive3DHint');
 if(!proof||proof.snapshot_id!==selected||!proof.three_d_field_verified)return;
 btn.disabled=true;hint.textContent='실제 INP·STA·FRD 및 3D 필드 재검증 중…';
 try{
  const answer=await get('/api/fea/verified_archive_field/'+encodeURIComponent(selected),90000);
  if(!stillSelected())return;
  if(!answer.ok||!answer.read_only||answer.snapshot_id!==selected||answer.run_id!==proof.run_id||
     answer.cad_sha256!==proof.cad_sha256||answer.case_sha256!==proof.case_sha256)
   throw Error('계산 ID/해시가 현재 검증 기록과 일치하지 않습니다.');
  const f=answer.field,n=f?.positions_mm?.length;
  if(!Array.isArray(f?.triangles)||!Number.isInteger(n)||n<3||n>35000||
     f.triangles.length<1||f.triangles.length>100000||
     f.von_mises_mpa?.length!==n||f.displacements_mm?.length!==n||
     f.positions_mm.some(v=>!Array.isArray(v)||v.length!==3||v.some(x=>!Number.isFinite(x)))||
     f.triangles.some(t=>!Array.isArray(t)||t.length!==3||
       t.some(x=>!Number.isInteger(x)||x<0||x>=n)||new Set(t).size!==3))
   throw Error('FRD 3D 필드 구조를 검증할 수 없습니다.');
  for(const key of ['maximum_von_mises_mpa','maximum_displacement_mm']){
   const v=answer[key],old=proof[key];
   if(!Number.isFinite(v)||!Number.isFinite(old)||
      Math.abs(v-old)>Math.max(1e-4,Math.abs(old)*1e-4))
    throw Error('저장된 계산 수치와 새 3D 필드 검증 결과가 다릅니다.');
  }
  gfFeaFieldSummaryCheck(f,{
   maximum_nodal_von_mises_mpa:answer.maximum_von_mises_mpa,
   maximum_displacement_mm:answer.maximum_displacement_mm
  });
  if(!stillSelected())return;
  // Always use the solver-backed field for coloring, never estimated stress.
  r185PreviewField=f;r185PreviewProof=answer;r185PreviewYaw=-.65;r185PreviewPitch=.4;r185PreviewZoom=1;
  r185Modal.hidden=false;r185Modal.style.display='flex';
  $('feaArchivePreviewStatus').textContent='FRD 검증 완료 · '+n+'개 표면 노드 · '+f.triangles.length+'개 삼각형 · 읽기 전용';
  r185Draw();hint.textContent='검증된 3D 미리보기 열림 · 현재 CAD/FEA 조건 변경 없음';
 }catch(e){if(stillSelected()){r185Close();hint.textContent='실제 3D 결과 표시 실패: '+e.message;}}
 finally{if(stillSelected())btn.disabled=!proof.three_d_field_verified;}
};

async function loadFeaArchive(append=false){
 const request=++feaArchiveRequest, q=$('feaArchivedSearch').value.trim();
 const info=$('feaArchivedDetail'), more=$('feaArchivedMoreBtn');
 if(!append){$('feaArchive3DPreviewBtn').disabled=true;r185Close();}
 if(!append){gfFeaTableClear('저장된 실제 계산 기록을 검색하는 중입니다.');}
 if(!append){feaArchiveVerified=null;++feaArchiveSelectedGeneration;$('feaArchivedNumbers').textContent='실제 계산 기록을 선택하면 검증된 수치가 표시됩니다.';}
 if(!append){feaArchiveItems=[];feaArchiveOffset=0;feaArchiveSelector.replaceChildren(new Option('조회 중…',''));}
 info.textContent='실제 FEA 성공 기록을 검색하는 중입니다. 기록 조회만으로 수치가 검증되지는 않습니다.';
 try{
  const data=await get('/api/history/search?'+new URLSearchParams({stage:'fea_result',q,offset:String(feaArchiveOffset),limit:'50'}));
  if(request!==feaArchiveRequest)return;
  if(!Array.isArray(data.items)||!Number.isInteger(data.total))throw Error('기록 검색 응답 형식 오류');
  feaArchiveInitialized=true;
  if(!append)feaArchiveSelector.replaceChildren(new Option('계산 기록을 선택하세요',''));
  for(const item of data.items){
   if(!/^[a-f0-9]{32}$/.test(item.id||'')||!/^[a-f0-9]{32}$/.test(item.job_id||''))continue;
   feaArchiveItems.push(item);
   const title=(item.cad_name||'CAD')+' · '+(item.created_at||'')+' · '+item.id.slice(0,8);
   feaArchiveSelector.add(new Option(title,item.id));
  }
  feaArchiveOffset+=data.items.length;feaArchiveTotal=data.total;
  if(!append&&feaArchiveItems.length>0){feaArchiveSelector.value='';} // No implicit past-result validation/display.
  if(!append&&feaArchiveItems.length===0){gfFeaTableClear('검증할 완료된 FEA 기록이 없습니다. 새 계산은 Gmsh·CalculiX 실행이 필요합니다.');}
  // Current result flow auto-selects newest completed record once.
  more.hidden=feaArchiveOffset>=feaArchiveTotal;more.disabled=false;
  $('feaArchivedRestoreBtn').disabled=true;
  info.textContent='계산 성공 기록 '+feaArchiveItems.length+'건 표시 / 검색 결과 전체 '+feaArchiveTotal+'건. 선택하면 당시 조건을 미리 볼 수 있습니다.';
 }catch(e){if(request===feaArchiveRequest){more.disabled=true;info.textContent='기록 조회 실패: '+e.message+' · 서버의 기록·비교 탭 상태도 확인하세요.';}}
}
$('feaArchivedSearchBtn').onclick=()=>loadFeaArchive(false);
$('feaArchivedMoreBtn').onclick=()=>loadFeaArchive(true);
$('feaArchivedSearch').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();loadFeaArchive(false);}});
// Verification-only archived history identity: never relabel another
// run's response as the selected saved result or the active CAD.
function gfArchivedNumbersIdentityCheck(verified,choice,item){
 if(!item||!verified||verified.ok!==true||verified.read_only!==true||
    verified.current_session_unchanged!==true||
    verified.verification!=='rechecked_actual_inp_sta_frd'||
    verified.snapshot_id!==choice||verified.cad_job_id!==item.job_id||
    verified.cad_sha256!==item.cad_sha256||
    !/^[0-9a-f]{32}$/.test(String(verified.run_id||''))||
    !/^[0-9a-f]{64}$/.test(String(verified.case_sha256||'')))
  throw Error('저장 기록과 실제 INP·STA·FRD 재검증 응답의 실행·CAD·조건 식별자가 일치하지 않습니다.');
 if(item.result_run_id!=null && item.result_run_id!==verified.run_id)
  throw Error('저장 기록과 재검증된 CalculiX 실행 ID가 다릅니다.');
 if(item.result_case_sha256!=null && item.result_case_sha256!==verified.case_sha256)
  throw Error('저장 기록과 재검증된 해석 조건 SHA가 다릅니다.');
 if(!Number.isFinite(verified.maximum_von_mises_mpa)||verified.maximum_von_mises_mpa<0||
    !Number.isFinite(verified.maximum_displacement_mm)||verified.maximum_displacement_mm<0)
  throw Error('실제 FEA 응력·변위 수치를 검증할 수 없습니다.');
 const mesh=verified.mesh||{};
 if(!Number.isInteger(mesh.nodes)||mesh.nodes<1||
    !Number.isInteger(mesh.tetrahedra)||mesh.tetrahedra<1)
  throw Error('실제 FEA 실행의 노드·사면체 수가 누락됐습니다.');
 return true;
}
feaArchiveSelector.onchange=async()=>{
 const generation=++feaArchiveSelectedGeneration;
 const choice=feaArchiveSelector.value,item=feaArchiveItems.find(x=>x.id===choice);
 const info=$('feaArchivedDetail'), numbers=$('feaArchivedNumbers');
 feaArchiveVerified=null;$('feaArchivedRestoreBtn').disabled=true;gfFeaTableClear('선택한 계산의 INP·STA·FRD 검증 중입니다.');$('feaArchive3DPreviewBtn').disabled=true;r185Close();
 if(!item){numbers.textContent='복원할 실제 계산 기록을 선택하세요.';return;}
 info.textContent='선택한 계산의 실제 INP·STA·FRD와 저장 기록을 검증합니다.';
 numbers.textContent='실제 CalculiX 결과 검증 중…';
 try{
  const verified=await get('/api/fea/verified_archive_numbers/'+encodeURIComponent(choice),60000);
  if(feaArchiveSelector.value!==choice||generation!==feaArchiveSelectedGeneration)return;
  gfArchivedNumbersIdentityCheck(verified,choice,item);
  feaArchiveVerified=verified;
  gfFeaTableShow('저장된 과거 실제 FEA · 현재 CAD와 분리',verified.maximum_von_mises_mpa,verified.maximum_displacement_mm,verified.mesh?.tetrahedra,verified.mesh?.nodes,verified.run_id,verified.three_d_field_verified);
  const c=verified.conditions||{};
  info.textContent='검증된 과거 계산 · '+(c.material||'재료 미상')+' · '+(c.mass_kg===null||c.mass_kg===undefined?'별도 입력 하중':c.mass_kg+' kg')+' · 고정 '+(c.fixed_faces||[]).join(',')+' / 하중 '+(c.load_faces||[]).join(',')+' · 실행 ID '+verified.run_id;
  numbers.textContent='검증된 과거 CalculiX 결과: 최대 von Mises '+String(verified.maximum_von_mises_mpa)+' MPa · 최대 변위 '+String(verified.maximum_displacement_mm)+' mm · 하중 '+c.force_n+' N · 3D 근거 파일 '+(verified.three_d_field_verified?'검증됨':'없음')+' · 현재 입력 조건은 그대로 유지됨 · 구조 안전 인증 아님';
  $('feaArchivedRestoreBtn').disabled=false;
  $('feaArchive3DPreviewBtn').disabled=!verified.three_d_field_verified;
  $('feaArchive3DHint').textContent='과거 계산을 선택했습니다. 3D 결과를 보려면 표시 버튼을 직접 누르세요. 새 하중 계산이 아닙니다.';
 }catch(error){
  if(feaArchiveSelector.value===choice&&generation===feaArchiveSelectedGeneration){
    info.textContent='선택한 계산의 실제 결과를 표시할 수 없습니다.';
    numbers.textContent='검증 실패: '+error.message+' · 원본 파일과 진단 로그를 확인하세요. 다른 조건의 수치로 대체하지 않습니다.';
    gfFeaTableClear('저장된 실제 계산 확인 실패: '+error.message);
  }
 }
};
$('feaArchivedRestoreBtn').onclick=async()=>{
 const item=feaArchiveItems.find(x=>x.id===feaArchiveSelector.value);
 if(!item||!feaArchiveVerified||feaArchiveVerified.snapshot_id!==item.id)return;
 await restoreArchivedFea(item,$('feaArchivedRestoreBtn'));
};


// GeoField R18.6 embedded verified archive FEA view
const r186Host=$('feaArchiveInlineHost'),r186Mount=$('feaArchiveInlineMount');
const r186Provenance=$('feaArchiveInlineProvenance'),r186Expand=$('feaArchiveInlineExpand');
const r186Back=$('feaArchiveInlineBack'),r186OriginalParent=r185Modal.parentNode;
const r186PreviewButton=$('feaArchive3DPreviewBtn');
const r186OriginalPreviewClick=r186PreviewButton.onclick;
function r186InlinePresentation(){
 r186Mount.appendChild(r185Modal);
 r185Modal.style.position='static';r185Modal.style.inset='auto';r185Modal.style.zIndex='auto';
 r185Modal.style.padding='0';r185Modal.style.background='transparent';
 r185Modal.style.width='100%';r185Modal.style.maxHeight='none';
 const section=r185Modal.querySelector('section');
 section.setAttribute('role','region');section.setAttribute('aria-modal','false');
 section.style.width='100%';section.style.maxHeight='none';section.style.overflow='visible';
 section.style.background='transparent';section.style.padding='4px';
 r185Canvas.style.height='min(54vh,520px)';
}
function r186FullscreenPresentation(){
 document.body.appendChild(r185Modal);
 r185Modal.style.position='fixed';r185Modal.style.inset='0';r185Modal.style.zIndex='9000';
 r185Modal.style.padding='12px';r185Modal.style.background='rgba(12,27,47,.85)';
 r185Modal.style.width='auto';r185Modal.style.maxHeight='none';
 const section=r185Modal.querySelector('section');
 section.setAttribute('role','dialog');section.setAttribute('aria-modal','true');
 section.style.width='min(94vw,1000px)';section.style.maxHeight='95vh';
 section.style.overflow='auto';section.style.background='#f6f9fc';section.style.padding='14px';
 r185Canvas.style.height='min(60vh,540px)';
}
function r186ClearView(){
 r186Host.hidden=true;
 if(!r185Modal.hidden)r185Close();
}
// Existing R18.5 button and real FRD verification are deliberately reused.
r186PreviewButton.onclick=async()=>{
 r186Host.hidden=false;
 r186InlinePresentation();
 r186Provenance.textContent='기존 실제 CalculiX 계산 파일을 다시 검증하는 중…';
 try {
   await r186OriginalPreviewClick();
   if(r185Modal.hidden){r186Host.hidden=true;return;}
   const p=r185PreviewProof;
   r186Provenance.textContent='검증된 과거 결과 · 실행 ID '+p.run_id+' · '+(p.conditions?.material||'재료 미상')+
     ' · '+(p.conditions?.mass_kg??'별도 하중')+' kg · 응력 '+String(p.maximum_von_mises_mpa)+
     ' MPa · 변위 '+String(p.maximum_displacement_mm)+' mm';
   // Wait for layout to settle after main viewport replaces the CAD canvas.
   requestAnimationFrame(()=>r185Draw());
 }catch(e){r186ClearView();$('feaArchive3DHint').textContent='과거 계산 3D 표시 실패: '+e.message;}
};
r186Back.onclick=r186ClearView;
r186Expand.onclick=()=>{
 if(r185Modal.hidden)return;
 r186Host.hidden=true;r186FullscreenPresentation();r185Modal.style.display='flex';
 requestAnimationFrame(()=>r185Draw());
};
$('feaArchivePreviewClose').addEventListener('click',()=>{r186Host.hidden=true;});
// Closing by ESC and record change must also restore the current CAD viewport.
const r186VisibilityObserver=new MutationObserver(()=>{
 if(r185Modal.hidden && !r186Host.hidden)r186Host.hidden=true;
});
r186VisibilityObserver.observe(r185Modal,{attributes:true,attributeFilter:['hidden']});
// Returning from the fullscreen overlay preserves the old CAD data untouched.
document.addEventListener('keydown',e=>{
 if(e.key==='Escape' && !r186Host.hidden){r186ClearView();}
});

// Append-only analysis history + bundled past research, distinct from legacy records.
const historyNames={cad:'CAD 형상 검사',ml:'BrepMFR 진단',ml_failed:'BrepMFR 진단 실패',fea_case:'FEA 조건 저장',fea_result:'FEA 실제 결과',fea_failed:'FEA 실행 실패'};
let historyQueryGeneration=0;
let historyNextOffset=0, historyTotal=0, historyLoading=false;
let historyQueryTimer=null;
const currentHistoryFilter=()=>$('historyStage').value;
const historyText=()=>($('historySearch').value||'').trim().toLocaleLowerCase();
const historyMaterial=()=>($('historyMaterial').value||'').trim();
const historyMass=()=>($('historyMass').value||'').trim();
$('legacyRecordTools').addEventListener('toggle',()=>{
 if($('legacyRecordTools').open)loadRecords();
});
$('previousResearchTools').addEventListener('toggle',()=>{
 if($('previousResearchTools').open)loadResearch();
});
function recordHistoryRefresh(){clearTimeout(historyQueryTimer);historyQueryTimer=setTimeout(loadArchive,180);}
$('historyStage').addEventListener('change',()=>loadArchive());
$('historySearch').addEventListener('input',recordHistoryRefresh);
$('historyMaterial').addEventListener('change',()=>loadArchive());
$('historyMass').addEventListener('input',recordHistoryRefresh);
$('recordsSearch').addEventListener('input',loadRecords);
$('historyLoadMore').onclick=()=>loadArchive(true);
$('historyDiagnostics').onclick=async()=>{
 const detail=$('historyDiagnosticDetail');detail.textContent='서버 기록 상태 점검 중…';
 try{const data=await get('/api/diagnostics/integrated');
   const parts=Object.entries(data.collections||{}).map(([k,v])=>k+': '+(v.ok?'OK ('+v.count+')':'오류 '+v.error));
   detail.textContent='서버 '+(data.version||'?')+' · '+parts.join(' · ');
   if(!data.ok)status('기록 조회 일부 실패',detail.textContent,true);
 }catch(e){detail.textContent='진단 실패: '+e.message;status('서버 진단 불가',e.message,true);}
};
async function loadArchive(append=false){
 const area=$('historyList');if(!area)return;
 const request=append?historyQueryGeneration:++historyQueryGeneration,mode=currentHistoryFilter(),term=historyText();
 if(historyLoading && append)return;
 if(!append){area.textContent='조회 중…';historyNextOffset=0;$('historyLoadMore').hidden=true;}
 historyLoading=true;
 const more=$('historyLoadMore');more.disabled=true;
 try{
  const url='/api/history/search?'+new URLSearchParams({stage:mode,q:term,material:historyMaterial(),mass_kg:historyMass(),offset:String(append?historyNextOffset:0),limit:'30'});
  const data=await get(url);
  if(request!==historyQueryGeneration)return;
  const matched=data.items||[];
  historyNextOffset=data.offset+matched.length;historyTotal=data.total;
  $('historyCount').textContent=`${historyNextOffset}건 표시 · 검색 결과 전체 ${historyTotal}건 · 실제 계산 파일은 복원 시 재검증`;
  if(!append)area.textContent='';
  if(!matched.length&&!append){area.textContent='검색 조건에 해당하는 기록이 없습니다.';}
  more.hidden=!data.has_more;
  more.disabled=!data.has_more;
  for(const item of matched){
   const d=document.createElement('div');d.className='rec';const title=document.createElement('strong');title.textContent=`${historyNames[item.stage]||item.stage} · ${item.cad_name}`;
   const info=document.createElement('small');info.textContent=`${item.created_at} · CAD SHA ${item.cad_sha256.slice(0,12)}…`+(item.stage==='fea_result'?' · 결과 ID '+item.job_id:'');
   const bar=document.createElement('div');bar.className='recrow';const view=document.createElement('button');view.textContent='분석 내용';
   view.onclick=async()=>{try{const s=await get('/api/history/item/'+item.id);const d=$('historyDetail');d.hidden=false;d.textContent=[`원본: ${s.cad.name}`,`해시: ${s.cad.sha256}`,`측정 부품: ${s.cad.parts.length} · 홀 후보: ${s.cad.hole_candidates.length}`,`BrepMFR: ${s.ml.status_text}`,`FEA: ${s.fea.status_text}`,s.fea.conditions_saved?`FEA 조건: ${JSON.stringify(s.fea.setup,null,2)}`:'FEA 조건: 미설정', '이전 분석 기록이며 현재 CAD의 검증 결과와 별개입니다.'].join('\n');}catch(e){status('보존 기록 조회 실패',e.message,true);}};
   // GeoField R19.3 read-only verified multi-evidence report

   const report=document.createElement('button');report.textContent='당시 보고서';report.onclick=()=>window.open('/api/history/report/'+item.id,'_blank','noopener');
   if(item.stage==='fea_result'){
      const verifiedReport=document.createElement('button');verifiedReport.type='button';
      verifiedReport.textContent='실제 근거 검증 통합 보고서';
      verifiedReport.title='저장된 CAD/ML 기록과 INP·STA·FRD 재검증 결과를 구분하는 읽기 전용 보고서';
      verifiedReport.onclick=()=>window.open('/api/history/verified-report/'+encodeURIComponent(item.id),'_blank','noopener');
      // GeoField R19.4 validated evidence-guided improvement review
      const improvementReview=document.createElement('button');improvementReview.type='button';
      improvementReview.textContent='근거별 개선 검토 후보';
      improvementReview.title='CAD 원본을 수정하지 않고 검증된 실제 FEA 결과를 바탕으로 다음 점검 항목만 제안합니다.';
      improvementReview.onclick=()=>window.open('/api/history/review/'+encodeURIComponent(item.id),'_blank','noopener');
      // GeoField R19.5 verified FEA to CAD geometry spatial comparison
      const spatialReview=document.createElement('button');spatialReview.type='button';
      spatialReview.textContent='CAD·고응력 공간 대조';
      spatialReview.title='실제 계산 FRD의 고응력 절점과 저장된 CAD 원통면 삼각 메시까지의 거리를 비교합니다. 원본 STEP 재분석이나 원인 판정은 하지 않습니다.';
      spatialReview.onclick=()=>window.open('/api/history/geometry-spatial/'+encodeURIComponent(item.id),'_blank','noopener');
      bar.append(spatialReview);
      bar.append(improvementReview);
      bar.append(verifiedReport);
   }
   if(item.stage==='fea_result'){
    const restore=document.createElement('button');restore.textContent='CAD·3D FEA 검증 복원';
    restore.onclick=()=>restoreArchivedFea(item,restore);bar.append(restore);
   }
   if(item.stage==='fea_result'){
     const hotspotButton=document.createElement('button');hotspotButton.type='button';hotspotButton.textContent='고응력 위치';
     hotspotButton.onclick=()=>displayVerifiedHotspots(item.id,hotspotButton);
     bar.append(hotspotButton);
   }
   if(item.stage==='fea_result'){
     const qualityButton=document.createElement('button');qualityButton.type='button';qualityButton.textContent='메시 품질';
     qualityButton.onclick=()=>displayVerifiedMeshQuality(item.id,qualityButton);
     // GeoField R19.2 verified hotspot-to-C3D4 incident element quality
     const linkButton=document.createElement('button');linkButton.type='button';linkButton.textContent='응력·메시 연계';
     linkButton.onclick=()=>displayVerifiedStressMesh(item.id,linkButton);
     bar.append(linkButton);
     bar.append(qualityButton);
   }
   if(item.stage==='fea_result'){
     for(const side of ['coarse','medium','fine']){
      const b=document.createElement('button');
      b.textContent=side==='coarse'?'메시 굵음':side==='medium'?'메시 중간':'메시 미세';
      b.type='button';b.onclick=()=>{feaMeshStudyPick[side]=item.id;feaMeshStudyUpdate();};
      bar.append(b);
     }
    }
   if(item.stage==='fea_result'){
     for(const side of ['left','right']){
      const b=document.createElement('button');b.textContent=side==='left'?'비교 A':'비교 B';
      b.onclick=()=>{feaComparePick[side]=item.id;
       $('feaCompareSelection').textContent='A: '+(feaComparePick.left||'미선택')+' / B: '+(feaComparePick.right||'미선택');
       $('feaCompareRun').disabled=!(feaComparePick.left&&feaComparePick.right&&feaComparePick.left!==feaComparePick.right);
      };bar.append(b);
     }
    }
   bar.append(view,report);d.append(title,info,bar);area.append(d);
  }
  }catch(e){if(request===historyQueryGeneration){if(!append)area.textContent='분석 이력 오류: '+e.message+' · 서버 진단을 확인하세요.';status('분석 이력 조회 실패',e.message,true);}}
  finally{historyLoading=false;}
}
async function loadResearch(){
 const area=$('researchList');if(!area)return;area.textContent='자료 불러오는 중…';
 try{const {items}=await get('/api/research');area.textContent='';for(const it of items){
  const b=document.createElement('button');b.className='finding';b.textContent=it.title+' · 이전 연구 자료';
  b.onclick=async()=>{try{const entry=await get('/api/research/item/'+it.id);const target=$('researchDetail');target.hidden=false;target.textContent=`${entry.title}\n${entry.type}\n\n${entry.content}`;}catch(e){status('자료 조회 오류',e.message,true);}};
  area.append(b);
  }}catch(e){area.textContent='연구 자료 오류: '+e.message;
   status('연구 자료 조회 실패',e.message,true);}
}
$('reloadHistory').onclick=()=>{loadArchive();if($('previousResearchTools')?.open)loadResearch();};


// Read-only evidence-verified comparison; never replaces the current CAD/FEA session.
const feaComparePick={left:null,right:null};
$('feaCompareClear').onclick=()=>{feaComparePick.left=null;feaComparePick.right=null;
 $('feaCompareSelection').textContent='성공 기록에서 비교 A와 비교 B를 선택하세요.';
 $('feaCompareRun').disabled=true;
 $('feaCompareOutput').textContent='기존 계산 파일만 읽어 비교합니다. 새로운 FEA 계산은 하지 않습니다.';};
// GeoField R19 genuine FRD high-stress surface candidates
// GeoField R19.1 solver-verified 3D high-stress region overlay
let r191HotspotInfo=null,r191ActiveRegion=0,r191Opening=false;
const r191OpenButton=$('feaHotspotOpen3D'),r1913DStatus=$('feaHotspot3DStatus');
const r191Controls=$('feaHotspotInlineControls'),r191Regions=$('feaHotspotRegionSelect');
function r191CheckRegions(info,n){
 if(!info||!info.read_only||info.status!=='verified_solver_extrapolated_nodal_hotspot_candidates'||
    !/^[0-9a-f]{32}$/.test(info.snapshot_id||'')||!/^[0-9a-f]{32}$/.test(info.run_id||'')||
    !/^[0-9a-f]{64}$/.test(info.cad_sha256||'')||!/^[0-9a-f]{64}$/.test(info.case_sha256||''))
  throw Error('FEA 출처/결과 식별자가 올바르지 않습니다.');
 const groups=info.metrics?.regions;
 if(!Array.isArray(groups)||groups.length<1||groups.length>8||info.metrics?.surface_node_count!==n)
  throw Error('3D 표면 노드와 응력 후보의 정합이 없습니다.');
 for(const group of groups){
  const ix=group.surface_node_indices,peak=group.peak_surface_node_index;
  if(!Array.isArray(ix)||ix.length===0||ix.length!==group.surface_node_count||
      ix.some(v=>!Number.isInteger(v)||v<0||v>=n)||new Set(ix).size!==ix.length||
      !Number.isInteger(peak)||!ix.includes(peak))throw Error('고응력 영역의 노드 인덱스가 유효하지 않습니다.');
 }
}
function r191Paint(ctx,projected,w,h){
 if(!r191HotspotInfo||!r185PreviewField||!r185PreviewProof||
    r191HotspotInfo.snapshot_id!==r185PreviewProof.snapshot_id||
    r191HotspotInfo.run_id!==r185PreviewProof.run_id||
    r191HotspotInfo.case_sha256!==r185PreviewProof.case_sha256||
    r191HotspotInfo.cad_sha256!==r185PreviewProof.cad_sha256||
    $('feaArchivePreviewMode').value!=='stress')return;
 const g=r191HotspotInfo.metrics.regions[r191ActiveRegion];if(!g)return;
 const scale=Math.min(2,window.devicePixelRatio||1);
 ctx.save();
 // Sparse, exact surface node overlay; never imply interpolated or simulated values.
 const indices=g.surface_node_indices,step=Math.max(1,Math.ceil(indices.length/700));
 ctx.fillStyle='rgba(240,30,185,.67)';ctx.strokeStyle='#ffffff';ctx.lineWidth=Math.max(1,scale);
 for(let k=0;k<indices.length;k+=step){
  const p=projected[indices[k]];if(!p)continue;
  ctx.beginPath();ctx.arc(p[0],p[1],Math.max(2,2.3*scale),0,Math.PI*2);ctx.fill();
 }
 const q=projected[g.peak_surface_node_index];
 if(q){ctx.strokeStyle='#fff';ctx.lineWidth=3*scale;ctx.beginPath();ctx.arc(q[0],q[1],10*scale,0,Math.PI*2);ctx.stroke();
  ctx.strokeStyle='#df169e';ctx.lineWidth=2*scale;ctx.beginPath();ctx.arc(q[0],q[1],14*scale,0,Math.PI*2);ctx.stroke();
  ctx.fillStyle='#211c2e';ctx.font=`bold ${Math.round(12*scale)}px sans-serif`;
  const px=Math.min(w-180,Math.max(6,q[0]+16*scale)),py=Math.max(17,Math.min(h-10,q[1]-8*scale));
  ctx.fillText('후보 '+(r191ActiveRegion+1)+' · '+Number(g.peak_mpa).toFixed(3)+' MPa',px,py);
 }
 ctx.restore();
}
function r191Focus(){
 if(!r191HotspotInfo||!r185PreviewField)return;
 const g=r191HotspotInfo.metrics.regions[r191ActiveRegion];
 if(!g)return;
 // The 3D viewer projects about its current box centre; set a temporary read-only focal point.
 const bb=g.bounding_box_mm,lo=bb?.min,hi=bb?.max;
 if(!Array.isArray(lo)||!Array.isArray(hi)||lo.length!==3||hi.length!==3||
     [...lo,...hi].some(v=>!Number.isFinite(v)))return;
 r191FocusPosition=lo.map((v,i)=>(v+hi[i])/2);
 const coords=r185PreviewField.positions_mm,mins=[Infinity,Infinity,Infinity],maxs=[-Infinity,-Infinity,-Infinity];
 for(const p of coords)for(let i=0;i<3;i++){mins[i]=Math.min(mins[i],p[i]);maxs[i]=Math.max(maxs[i],p[i]);}
 const full=Math.max(1e-9,...mins.map((v,i)=>maxs[i]-v));
 const extent=Math.max(1e-9,...lo.map((v,i)=>hi[i]-v));
 r185PreviewZoom=Math.min(3,Math.max(.8,full/Math.max(extent*3,full*.25)));
 r185Draw();
}
let r191FocusPosition=null;
r191Regions.onchange=()=>{r191ActiveRegion=Number(r191Regions.value)||0;r191FocusPosition=null;r185Draw();};
$('feaHotspotFocus').onclick=r191Focus;
$('feaHotspotClear').onclick=()=>{r191HotspotInfo=null;r191FocusPosition=null;r191Controls.hidden=true;r185Draw();};
r191OpenButton.onclick=async()=>{
 if(!r191HotspotInfo||r191Opening)return;
 const info=r191HotspotInfo,sid=info.snapshot_id;r191Opening=true;r191OpenButton.disabled=true;
 r1913DStatus.textContent='같은 FEA 실행 ID의 INP·STA·FRD·3D 필드를 다시 검증하는 중…';
 try{
  const proof=await get('/api/fea/verified_archive_numbers/'+sid,90000);
  if(!proof.ok||!proof.read_only||!proof.three_d_field_verified||proof.snapshot_id!==sid||
      proof.run_id!==info.run_id||proof.case_sha256!==info.case_sha256||proof.cad_sha256!==info.cad_sha256)
   throw Error('고응력 분석과 3D 결과의 출처/해시가 다릅니다.');
  const result=await get('/api/fea/verified_archive_field/'+sid,90000);
  if(!result.ok||!result.read_only||result.snapshot_id!==sid||result.run_id!==info.run_id||
    result.case_sha256!==info.case_sha256||result.cad_sha256!==info.cad_sha256)
   throw Error('3D 필드 검증 응답과 고응력 분석이 다릅니다.');
  const field=result.field,n=field?.positions_mm?.length;
  if(!Number.isInteger(n)||n<3||field?.von_mises_mpa?.length!==n||field?.displacements_mm?.length!==n||
    !Array.isArray(field?.triangles))throw Error('표면 메시·응력·변위 배열이 잘못되었습니다.');
  r191CheckRegions(info,n);
  for(const peak of info.metrics.regions){
   const idx=peak.peak_surface_node_index;
   if(!Number.isFinite(field.von_mises_mpa[idx])||
      Math.abs(field.von_mises_mpa[idx]-peak.peak_mpa)>Math.max(1e-4,peak.peak_mpa*1e-5)||
      !Array.isArray(peak.peak_position_mm)||peak.peak_position_mm.length!==3||
      peak.peak_position_mm.some((v,k)=>!Number.isFinite(v)||Math.abs(v-field.positions_mm[idx][k])>1e-4))
     throw Error('FRD 응력·위치와 강조 대상이 일치하지 않습니다.');
  }
  if(r191HotspotInfo!==info)throw Error('선택된 분석 기록이 변경되었습니다.');
  // Switching to FEA tab refreshes the archive list and closes open previews. Do this BEFORE rendering.
  tabTo('fea');
  r185PreviewField=field;r185PreviewProof=result;r185PreviewYaw=-.65;r185PreviewPitch=.4;r185PreviewZoom=1;
  r191ActiveRegion=0;r191FocusPosition=null;
  r191Regions.replaceChildren(...info.metrics.regions.map((g,i)=>new Option('후보 '+(i+1)+' · '+g.peak_mpa.toFixed(3)+' MPa',String(i))));
  r191Regions.value='0';r191Controls.hidden=false;
  r186Host.hidden=false;r186InlinePresentation();r185Modal.hidden=false;r185Modal.style.display='flex';
  $('feaArchivePreviewMode').value='stress';$('feaArchivePreviewDeform').value='0';
  $('feaArchivePreviewStatus').textContent='실제 FRD 검증 완료 · P90 고응력 절점 강조(분석 후보, 안전 판정 아님)';
  r186Provenance.textContent='실제 FRD/INP 재검증 · '+info.run_id+' · 후보 '+info.metrics.connected_region_count+'곳 · 읽기 전용';
  requestAnimationFrame(()=>r185Draw());
  r1913DStatus.textContent='검증된 3D 강조 화면을 열었습니다. FEA 탭에서 후보를 선택해 시점을 이동할 수 있습니다.';
 }catch(e){r1913DStatus.textContent='고응력 3D 강조 실패 (원본 데이터 보존): '+e.message;}
 finally{r191Opening=false;r191OpenButton.disabled=!r191HotspotInfo;}
};
let stressHotspotGeneration=0;
async function displayVerifiedHotspots(snapshotId,button){
 const out=$('feaStressHotspotOutput'),token=++stressHotspotGeneration;
 if(!out||!button)return;
 out.textContent='실제 CalculiX FRD·INP 및 표면 응력 정합 검증 중…';r191HotspotInfo=null;r191OpenButton.disabled=true;r1913DStatus.textContent='고응력 후보 검증 중…';button.disabled=true;
 try{
  const r=await get('/api/history/fea-stress-hotspots?id='+encodeURIComponent(snapshotId),90000);
  if(token!==stressHotspotGeneration)return;
  if(!r.read_only||r.status!=='verified_solver_extrapolated_nodal_hotspot_candidates'||r.snapshot_id!==snapshotId||!r.metrics)
   throw Error('응력 검증 결과 출처 또는 형식이 올바르지 않습니다.');
  r191HotspotInfo=r;r191ActiveRegion=0;r191FocusPosition=null;r191OpenButton.disabled=false;
  const m=r.metrics;
  if(m.metric!=='extrapolated_nodal_von_mises_mpa_surface'||!Array.isArray(m.regions))throw Error('실제 표면 응력 정보 누락');
  const f=(n,dec=4)=>Number.isFinite(n)?Number(n).toFixed(dec):'미기록';
  const coord=p=>Array.isArray(p)&&p.length===3?'('+p.map(x=>f(x,3)).join(', ')+') mm':'미기록';
  const lines=[
   '실제 계산 재검증: '+r.status,
   'CAD: '+r.cad_name+' · 재료: '+r.material+' · 실제 실행 ID: '+r.run_id,
   '고정 면 '+(r.fixed_faces||[]).join(',')+' · 하중 면 '+(r.load_faces||[]).join(',')+' · 힘 '+f(r.force_n)+' N',
   'FRD 전체 노드 최대 응력: '+f(r.global_maximum_nodal_von_mises_mpa)+' MPa',
   '실제 3D 표면 노드 '+m.surface_node_count+'개 · 표면 최대 '+f(m.surface_maximum_mpa)+' MPa',
   '표면 P50/P90/P95/P99: '+[m.p50_mpa,m.p90_mpa,m.p95_mpa,m.p99_mpa].map(x=>f(x)).join(' / ')+' MPa',
   '탐색 구간: 표면 노드의 P90 이상('+f(m.threshold_mpa)+' MPa), 선택 '+m.selected_node_count+'개',
   '연결된 고응력 후보 '+m.connected_region_count+'곳 (최대 '+m.regions_reported+'곳 표시)',
  ];
  for(const [index,g] of m.regions.entries()){
   lines.push((index+1)+'. 최대 '+f(g.peak_mpa)+' MPa · 위치 '+coord(g.peak_position_mm)+
    ' · 실제 INP 절점 '+(g.peak_inp_node_id||'미확인')+
    ' · 연결 절점 '+g.surface_node_count+'개 ('+f(g.fraction_surface_nodes_percent,2)+'%)');
   lines.push('   영역 좌표 '+coord(g.bounding_box_mm?.min)+' ~ '+coord(g.bounding_box_mm?.max));
   if(g.touches_fixed_nodes||g.touches_loaded_nodes)lines.push('   경계 노드 접촉: '+(g.touches_fixed_nodes?'고정 ':'')+(g.touches_loaded_nodes?'하중':'')+' / 특이점 가능성 별도 검증 필요');
  }
  lines.push(...m.warnings.map(w=>'주의: '+w));
  lines.push('결과는 읽기 전용이며 실제 결함·국부 응력 집중계수·구조 안전성을 확정하지 않습니다.');
  out.textContent=lines.join('\n');
  out.closest('section')?.scrollIntoView({behavior:'smooth',block:'nearest'});
 }catch(err){if(token===stressHotspotGeneration){r191HotspotInfo=null;r191OpenButton.disabled=true;r1913DStatus.textContent='3D 강조 불가: 고응력 검증 실패';out.textContent='고응력 위치 검사 실패 (기존 데이터 보존): '+err.message;out.closest('section')?.scrollIntoView({behavior:'smooth',block:'nearest'});}}
 finally{button.disabled=false;}
}

// GeoField R19.2 verified hotspot-to-C3D4 incident element quality
let r192Token=0;
async function displayVerifiedStressMesh(snapshotId,button){
 const out=$('feaStressMeshLinkOutput');const token=++r192Token;
 if(!out||!button)return;
 out.textContent='실제 FRD·INP·STA·CAD·메시 정합을 검증하고 연결된 요소의 품질 계산 중…';button.disabled=true;
 try{
  const r=await get('/api/history/fea-stress-mesh-link?id='+encodeURIComponent(snapshotId),120000);
  if(token!==r192Token)return;
  if(!r.read_only||r.status!=='verified_solver_hotspot_mesh_incidence_context'||
     r.snapshot_id!==snapshotId||!/^[0-9a-f]{32}$/.test(r.run_id||'')||
     !/^[0-9a-f]{64}$/.test(r.inp_sha256||'')||
     !Array.isArray(r.regions)||r.regions.length<1||r.regions.length>8||
     r.region_count_reported!==r.regions.length||
     r.mesh_convergence_certified!==false||r.structural_safety_certified!==false)
    throw Error('실제 데이터의 식별자·검증 상태·분석 결과 불일치');
  const f=(v,d=4)=>Number.isFinite(v)?Number(v).toFixed(d):'미기록';
  const global=r.global_mesh_quality;
  if(!global||!Number.isInteger(global.tetrahedron_count)||global.tetrahedron_count<=0||
     !Number.isFinite(global.below_0_20_percent))throw Error('전체 메시 품질 참조 오류');
  const lines=[
   '검증 상태: '+r.status,
   'CAD: '+r.cad_name+' · 재료 '+r.material+' · 동일 실행 ID '+r.run_id,
   'INP SHA-256: '+r.inp_sha256,
   '실제 전체 사면체: '+global.tetrahedron_count+'개 · 최소 품질 '+f(global.minimum_mean_ratio)+
    ' · 품질 < 0.20 '+f(global.below_0_20_percent,2)+'%',
   '연계 규칙: 후보 표면 절점과 하나 이상의 꼭짓점을 공유하는 실제 C3D4 요소',
   '고응력 후보 '+r.total_hotspot_regions+'개 중 '+r.region_count_reported+'개 분석'
  ];
  for(const g of r.regions){
    if(!Number.isInteger(g.region_index)||!Number.isInteger(g.incident_tetra_count)||g.incident_tetra_count<1||
       !Number.isFinite(g.minimum_mean_ratio)||!Number.isFinite(g.below_0_20_percent)||
       !Array.isArray(g.worst_five_elements)||!Array.isArray(g.observations))
       throw Error('후보 요소의 품질 검증 형식 오류');
    lines.push('['+g.region_index+'번 후보] 실제 최대 '+f(g.peak_mpa)+' MPa · 최고 응력 INP 노드 '+g.peak_inp_node_id);
    lines.push(' 연결 표면 절점 '+g.hotspot_surface_nodes+'개 · 연결 사면체 '+g.incident_tetra_count+'개'+
      ' · Mean-ratio 최소 '+f(g.minimum_mean_ratio)+' / 중앙값 '+f(g.median_mean_ratio));
    lines.push(' 품질 0.10 미만 '+g.below_0_10_count+'개 · 0.20 미만 '+g.below_0_20_count+
      '개 ('+f(g.below_0_20_percent,2)+'%)');
    lines.push(' 품질이 낮은 실제 요소 ID: '+g.worst_five_elements.map(e=>e.element_id+'('+f(e.mean_ratio)+')').join(', '));
    lines.push(...g.observations.map(s=>' 참고: '+s));
  }
  lines.push(...(r.warnings||[]).map(s=>'주의: '+s));
  out.textContent=lines.join('\n');
  out.closest('section')?.scrollIntoView({behavior:'smooth',block:'nearest'});
 }catch(e){if(token===r192Token)out.textContent='연계 분석 중단 (기존 데이터 보존): '+e.message;}
 finally{button.disabled=false;}
}

// GeoField R18.9 verified actual C3D4 mesh quality
let meshQualityRequestToken=0;
async function displayVerifiedMeshQuality(snapshotId,button){
 const output=$('feaMeshQualityOutput');const token=++meshQualityRequestToken;
 if(!output||!button)return;
 output.textContent='실제 CalculiX 계산 파일과 C3D4 사면체 품질 검증 중…';button.disabled=true;
 try{
  const data=await get('/api/history/fea-mesh-quality?id='+encodeURIComponent(snapshotId),90000);
  if(token!==meshQualityRequestToken)return;
  if(!data.read_only||data.status!=='verified_solver_mesh_descriptive_quality'||data.snapshot_id!==snapshotId)
   throw Error('서버 메시 품질 결과 식별자 또는 상태 오류');
  const v=data.metrics;if(!v||v.element_type!=='C3D4'||v.quality_metric!=='tetrahedral_mean_ratio_normalized_0_to_1')
   throw Error('지원하지 않는 메시 품질 결과');
  const f=n=>Number.isFinite(n)?Number(n).toFixed(5):'미기록';
  output.textContent=[
   '실제 증거 재검증: '+data.status,
   '모델: '+data.cad_name+' · 재료: '+data.material+' · 목표 메시 '+f(data.mesh_target_mm)+' mm',
   'CalculiX 실행 ID: '+data.run_id,
   'INP SHA-256: '+data.inp_sha256,
   '실제 노드 '+v.node_count+' · 사면체 '+v.tetrahedron_count+'개',
   'Mean-ratio 품질 (0=퇴화, 1=정사면체): 최소 '+f(v.minimum_quality)+' · 중앙값 '+f(v.median_quality),
   '하위 5% '+f(v.p05_quality)+' · 평균 '+f(v.mean_quality),
   '품질 0.10 미만 '+v.quality_bands.below_0_10+'개 / 0.10~0.20 미만 '+v.quality_bands.from_0_10_below_0_20+'개',
   '0.20 미만 비율 '+f(v.fraction_below_0_20_percent)+'%',
   '최소 사면체 체적 '+f(v.smallest_tetra_volume_mm3)+' mm³',
   ...v.warnings.map(x=>'참고: '+x),
   '주의: 이 구간 기준은 진단용이며 메시 수렴·응력 특이점·구조 안전성을 판정하지 않습니다.'
  ].join('\n');
 }catch(err){if(token===meshQualityRequestToken)output.textContent='메시 품질 검사 실패 (기존 기록 변경 없음): '+err.message;}
 finally{button.disabled=false;}
}

// GeoField R18.7 genuine FEA mesh sensitivity study
const feaMeshStudyPick={coarse:null,medium:null,fine:null};
function feaMeshStudyUpdate(){
 const list=[feaMeshStudyPick.coarse,feaMeshStudyPick.medium,feaMeshStudyPick.fine];
 $('feaMeshStudySelection').textContent='굵음: '+(list[0]||'미선택')+' · 중간: '+(list[1]||'미선택')+' · 미세: '+(list[2]||'미선택');
 $('feaMeshStudyRun').disabled=!(list.every(Boolean) && new Set(list).size===3);
}
$('feaMeshStudyClear').onclick=()=>{feaMeshStudyPick.coarse=null;feaMeshStudyPick.medium=null;feaMeshStudyPick.fine=null;feaMeshStudyUpdate();$('feaMeshStudyOutput').textContent='기존 계산 파일은 그대로 유지됩니다. 별도 FEA 재실행 없음.';};
$('feaMeshStudyRun').onclick=async()=>{
 const output=$('feaMeshStudyOutput');const ids=[feaMeshStudyPick.coarse,feaMeshStudyPick.medium,feaMeshStudyPick.fine];
 if(ids.some(x=>!x)||new Set(ids).size!==3)return;
 output.textContent='서로 다른 CalculiX 3건을 실제 파일에서 검증 중…';$('feaMeshStudyRun').disabled=true;
 try{
  const url='/api/history/fea-mesh-study?'+ids.map(x=>'id='+encodeURIComponent(x)).join('&');
  const data=await get(url,90000);
  const fmt=v=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(5):'계산 불가';
  const lines=['검증 상태: '+data.status,'실제 CalculiX 실행 파일 재검증: '+data.solver_evidence];
  for(const [i,r] of data.runs_coarse_to_fine.entries()){
   lines.push(`${i+1}단계 · 메시 ${fmt(r.mesh_target_mm)} mm · 사면체 ${r.mesh_tetrahedron_count} · 노드 ${r.mesh_node_count}`);
   lines.push('    응력 '+fmt(r.max_stress_mpa)+' MPa · 변위 '+fmt(r.max_displacement_mm)+' mm · 실행 '+r.run_id);
  }
  for(const [i,r] of data.adjacent_changes.entries()){
   lines.push(`${i+1}→${i+2}단계 · 최대응력 변화 ${fmt(r.stress_relative_change_percent)}% · 최대변위 변화 ${fmt(r.displacement_relative_change_percent)}%`);
  }
  lines.push('[메시 진단] '+gfMeshSensitivityLabel(data));
  lines.push('[응력 위치] '+gfMeshSpatialEvidence(data));
  if(data.warning)lines.push('주의: '+data.warning);
  lines.push('메시 수렴 인증: 아님 · 구조 안전 인증: 아님');lines.push(data.message);
  output.textContent=lines.join('\n');
 }catch(e){output.textContent='메시 민감도 연구를 수행할 수 없습니다: '+e.message;}
 finally{feaMeshStudyUpdate();}
};

$('feaCompareRun').onclick=async()=>{
 const leftPick=feaComparePick.left,rightPick=feaComparePick.right;
 const stillSelected=()=>feaComparePick.left===leftPick&&feaComparePick.right===rightPick;
 const out=$('feaCompareOutput');out.textContent='두 실제 계산 파일을 재검증하는 중…';$('feaCompareRun').disabled=true;
 try{
  const v=await get('/api/history/fea-compare?'+new URLSearchParams({left:leftPick,right:rightPick}));
  if(!stillSelected())return;
  if(v?.status!=='verified_read_only_comparison'||!v.left||!v.right||
     v.left.snapshot_id!==leftPick||v.right.snapshot_id!==rightPick)
   throw Error('원본 검증된 비교 기록 ID/출처 계약 오류');
  const fmt=x=>typeof x==='number'&&Number.isFinite(x)?x.toFixed(6):String(x??'미기록');
  const a=v.left,b=v.right;
  const lines=[
   '검증 상태: '+v.status,
   '                        A                         B',
   'CAD: '+a.cad_name+' / '+b.cad_name,
   '계산 ID: '+a.run_id+' / '+b.run_id,
   '재료: '+a.material+' / '+b.material,
   '질량(kg): '+fmt(a.external_mass_kg)+' / '+fmt(b.external_mass_kg),
   '하중(N): '+fmt(a.force_n)+' / '+fmt(b.force_n),
   '고정 면: '+(a.fixed_faces||[]).join(',')+' / '+(b.fixed_faces||[]).join(','),
   '하중 면: '+(a.load_faces||[]).join(',')+' / '+(b.load_faces||[]).join(','),
   '응력(MPa): '+fmt(a.max_stress_mpa)+' / '+fmt(b.max_stress_mpa),
   '변위(mm): '+fmt(a.max_displacement_mm)+' / '+fmt(b.max_displacement_mm),
   '응력 차이 B-A: '+fmt(v.stress_change.absolute_difference)+' MPa',
   '변위 차이 B-A: '+fmt(v.displacement_change.absolute_difference)+' mm',
   '동일 CAD: '+(v.same_cad?'예':'아니오')+' · 동일 재료: '+(v.same_material?'예':'아니오'),
   '동일 경계조건/하중: '+(v.same_boundary_conditions?'예':'아니오'),
   v.message
  ];
  const agent=v.agent_review;
  if(agent){
   if(agent.schema!=='geofield-agent-fea-comparison-v1'||
      agent.causal_effect_verified!==false||
      agent.structural_safety_verified!==false||
      agent.mesh_convergence_verified!==false)
    throw Error('에이전트 조건 비교 검증 계약 오류');
   if(agent.status==='same_cad_verified_runs_descriptive_comparison'){
    if(agent.left_run_id!==a.run_id||agent.right_run_id!==b.run_id||
       agent.cad_sha256!==a.cad_sha256||agent.cad_sha256!==b.cad_sha256||
       !Array.isArray(agent.changes)||!Array.isArray(agent.unverified_condition_groups)||
       !Number.isFinite(agent.stress_change?.absolute_difference)||
       !Number.isFinite(agent.displacement_change?.absolute_difference)||
       Math.abs(agent.stress_change.absolute_difference-v.stress_change.absolute_difference)>1e-8||
       Math.abs(agent.displacement_change.absolute_difference-v.displacement_change.absolute_difference)>1e-8)
     throw Error('에이전트가 원본 FEA 수치나 실행 ID와 다르게 설명했습니다.');
    const names={material:'재료',fixed_faces:'고정면',load_faces:'하중면',
      force:'하중/방향',external_mass:'외부 질량',self_weight:'자중 조건',
      mesh:'메시 설정/규모',solver_settings:'솔버/분석 조건'};
    if(agent.changes.some(k=>!Object.hasOwn(names,k))||
       agent.unverified_condition_groups.some(k=>!Object.hasOwn(names,k)))
     throw Error('FEA 비교 조건 분류 계약 오류');
    lines.push('','[AI 에이전트 · 규칙 기반 비교]',
      '기록상 달라진 조건: '+(agent.changes.map(k=>names[k]).join(', ')||'확인된 차이 없음'),
      '누락되어 대조하지 못한 조건: '+
        (agent.unverified_condition_groups.map(k=>names[k]).join(', ')||'없음'),
      '요소 종류(C3D4/C3D10)·메시 수렴: 별도 검증 필요',
      String(agent.note),String(agent.next_check));
   }else if(agent.status==='different_cad_not_comparable'||
            agent.status==='not_verified'){
    lines.push('','[AI 에이전트 판단 보류] '+String(agent.note));
   }else throw Error('알 수 없는 AI 에이전트 FEA 비교 상태');
  }else lines.push('','AI 근거 비교 미제공: 현재 엔진 버전에서 확인할 수 없습니다.');
  if(!stillSelected())return;
  out.textContent=lines.join('\n');
  status('실제 FEA 비교 완료','서로 다른 실제 계산 파일을 검증해 읽었습니다. 구조 안전성 판단은 별도입니다.');
 }catch(err){if(stillSelected()){out.textContent='비교할 수 없습니다: '+err.message;status('FEA 비교 실패',err.message,true);}}
 finally{$('feaCompareRun').disabled=!(feaComparePick.left&&feaComparePick.right&&feaComparePick.left!==feaComparePick.right);}
};


// GeoField R18 verified FEA comparison

// GeoField R18.1 historical exact-run verified FEA result restoration

// GeoField core FRD and surface numerical consistency


// GeoField focus verified FEA numerical table 20261019
function gfFeaTableClear(message){
 const body=$('feaVerifiedTableBody');if(body)body.textContent=String(message);
}
function gfLoadAuditSummary(a){
 if(!a || a.schema!=='geofield-load-equilibrium-audit-v1' ||
    !Number.isFinite(a.resultant_difference_n) ||
    !Number.isFinite(a.centroid_shift_mm) ||
    !Number.isFinite(a.moment_difference_n_mm) ||
    !Number.isInteger(a.load_node_count) || a.load_node_count<1 ||
    typeof a.moment_equivalent_within_roundoff!=='boolean')return null;
 const evidence=a.written_inp_cload_verified===true?'INP 교차 검증':'면적 가중 분배 진단';
 const force='합력 검증 · '+a.load_node_count+'개 하중 노드 · '+evidence;
 const moment=a.moment_equivalent_within_roundoff?
   '면적 가중 기준 모멘트 일치':
   '모멘트 차이 '+a.moment_difference_n_mm.toFixed(3)+' N·mm / 작용 중심 이동 '+a.centroid_shift_mm.toFixed(3)+' mm (주의: 하중 근사)';
 return {force,moment,shifted:!a.moment_equivalent_within_roundoff};
}
function gfFeaTableShow(kind,stress,disp,tets,nodes,runId,hasField,loadAudit){
 if(!Number.isFinite(stress)||!Number.isFinite(disp)||stress<0||disp<0)throw Error('실제 FEA 수치가 유효하지 않아 표를 작성하지 않았습니다.');
 const area=$('feaVerifiedTableBody');if(!area)return;
 area.textContent='';
 const subtitle=document.createElement('div');subtitle.className='mini';subtitle.textContent=kind;
 const table=document.createElement('table');table.className='gf-fea-evidence-table';
 const lines=[['최대 절점 von Mises 응력',String(stress)+' MPa'],
              ['최대 변위',String(disp)+' mm'],
              ['C3D4 요소',Number.isInteger(tets)?String(tets)+'개':'자료 없음'],
              ['전체 노드',Number.isInteger(nodes)?String(nodes)+'개':'자료 없음'],
              ['실행 ID',String(runId||'')],
              ['3D 응력 분포',hasField?'실제 FRD 필드 사용 가능 · 3D 결과 보기':'실제 표면 필드 검증 불가']];
 const loadSummary=gfLoadAuditSummary(loadAudit);
 if(loadSummary)lines.push(['하중 합력',loadSummary.force],['모멘트 / 작용점',loadSummary.moment]);
 for(const [key,value] of lines){const tr=document.createElement('tr');const label=document.createElement('th');const num=document.createElement('td');label.textContent=key;num.textContent=value;tr.append(label,num);table.append(tr);}
 const foot=document.createElement('div');foot.className='mini';foot.textContent='실제 CalculiX 수치 표시 · 메시 수렴 및 구조 안전 인증과는 별개입니다.';
 area.append(subtitle,table,foot);
}


// GeoField minimal FEA workflow and auto verified surface 20261019
// DOM-only reorganization: every legacy element keeps its ID, handler and data.
function gfFocusOrganizeUI(){
 // The four static header tabs stay visible. Never move Records or
 // Results/AI into a runtime-generated extra navigation menu.
 const archive=$('feaArchivedResults');
 if(archive&&!archive.closest('#feaOptionalHistory')&&!$('gfFocusArchiveDetails')){
  const advanced=document.createElement('details');advanced.id='gfFocusArchiveDetails';advanced.className='gf-focus-collapse';
  const summary=document.createElement('summary');summary.textContent='이전 계산 검색 · 필요할 때만 열기';
  archive.parentNode.insertBefore(advanced,archive);advanced.append(summary,archive);
 }
 const mode=$('feaContourMode'),state=$('feaContourStatus');
 if(mode&&state&&!$('gfFocusDisplayDetails')){
  const more=document.createElement('details');more.id='gfFocusDisplayDetails';more.className='gf-focus-collapse';
  const summary=document.createElement('summary');summary.textContent='3D 표시 방식 조정 (기본: 실제 응력 분포)';
  more.appendChild(summary);
  const controls=[$('feaDeformToggle')?.closest('label'),$('feaDeformScale')?.closest('label')];
  for(const el of controls)if(el&&el.parentNode&&el!==more&&!more.contains(el))more.appendChild(el);
  state.parentNode.insertBefore(more,state.nextSibling);
 }
 // Make the existing force-to-result workflow visible; do not add analysis controls.
 const prep=$('feaPrepared'), prepare=$('feaPrepareBtn'), run=$('feaRunBtn'), result=$('feaRunStatus');
 if(prep&&prepare&&run&&result){
  prepare.textContent='④ FEA 조건 저장 (실제 계산 전)';
  run.textContent='⑤ 실제 FEA 계산 실행';
  run.classList.add('primary');
  prep.insertAdjacentElement('afterend',run);
  run.insertAdjacentElement('afterend',result);
 }
 const pane=document.querySelector('[data-pane="fea"]');
 const hint=pane?.querySelector('.notice.warn');
 if(hint){
  const heading=hint.querySelector('strong'), body=hint.querySelector('p');
  if(heading)heading.textContent='힘과 고정 위치를 지정한 다음, 실제 해석을 실행하세요';
  if(body)body.textContent='① 3D에서 고정 면·하중 면 선택 → ② 소재 선택 → ③ 하중 크기·방향 입력 → ④ 조건 저장 → ⑤ 실제 응력·변위 계산 실행. 기존 결과는 자동 측정하지 않습니다.';
 }
 const archiveLabel=$('gfFocusArchiveDetails')?.querySelector('summary');
 if(archiveLabel)archiveLabel.textContent='과거 계산 보기 (현재 힘의 계산 결과가 아님)';
 // The current FEA maximum stress/displacement remain visible here.
 // The more detailed historical table is in an optional closed panel:
 // never hide these values on the main FEA calculation screen.
}
gfFocusOrganizeUI();
// GeoField R12: deliberately opt-in, research-only STEP bore candidates.
async function loadR12Preflight(){
 const text=$('r12Preflight'),btn=$('r12RunBtn');
 try{
  const d=await get('/api/ml/r12/preflight');r12Ready=Boolean(d.available);
  text.textContent=r12Ready?('R12 연구 모델 준비 완료 · 선택 Python: '+(d.python||'미확인')+' · 기존 BrepMFR와 별개 · 산업용 정확도 미검증'):('R12 연구 모델 실행 불가: '+(d.missing||[]).join('; ')+(d.python_error?' · '+d.python_error:'')+'. 기존 CAD·FEA는 사용 가능합니다.');
 }catch(e){r12Ready=false;text.textContent='R12 상태 확인 실패: '+e.message;}
 btn.disabled=!r12Ready||!current||!file||r12Running;
}
$('optionalMlTools').addEventListener('toggle',()=>{
 if($('optionalMlTools').open){loadBrepPreflight();loadR12Preflight();}
});
$('r12RunBtn').onclick=async()=>{
 const btn=$('r12RunBtn'),out=$('r12Result');
 if(r12Running||!r12Ready||!current||!jobId||!file)return;
 const targetJob=jobId, targetSha=current.sha256, targetFile=file, runGeneration=r12Generation;
 const sameRun=()=>runGeneration===r12Generation && jobId===targetJob && current?.sha256===targetSha && file===targetFile;
 r12Running=true;btn.disabled=true;out.textContent='R12 연구용 분류를 시작합니다…';
 try{
  const response=await fetch('/api/ml/r12/run/'+targetJob,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:targetFile});
  const data=await response.json();if(!response.ok)throw Error(data.error||`HTTP ${response.status}`);
  if(!sameRun())return; // A new STEP has invalidated this asynchronous request.
  if(typeof data.id!=='string'||!(/^[a-f0-9]{32}$/i).test(data.id))throw Error('R12 작업 응답 ID 오류');
  let completed=null;
  for(let t=0;t<180;t++){
   await sleep(1000);
   if(!sameRun())return; // Do not show stale results/errors after switching CAD.
   const task=await get('/api/ml/r12/status/'+data.id);
   if(task.status==='complete'){completed=task.result;break;}
   if(task.status==='failed')throw Error(task.message||'R12 분석 실패');
  }
  if(!sameRun())return;
  if(!completed)throw Error('R12 분석 시간 제한 초과');
  if(completed.cad_sha256!==targetSha||completed.decision_usage!=='blocked_diagnostic_only')throw Error('R12 결과 출처 검증 실패');
  if(!Array.isArray(completed.predictions)||completed.predictions.length!==completed.candidate_count)throw Error('R12 후보 결과 개수 검증 실패');
  out.textContent='';
  const header=document.createElement('div');header.className='notice';
  header.textContent='R12 실험 결과 · 원통형 내부 면 후보 '+completed.candidate_count+'개 · R12 면 참조번호는 3D 선택 면 ID와 대응 검증 전 · FEA에 사용되지 않음';out.append(header);
  if(!completed.predictions?.length){const p=document.createElement('div');p.textContent='분석한 STEP에서 단순 원통형 홀 후보를 찾지 못했습니다. 홀 없음이 확정된 것은 아닙니다.';out.append(p);}
  for(const item of completed.predictions||[]){
   const row=document.createElement('div');row.className='finding';
   const state=({through_hole:'관통홀 후보',blind_hole:'막힌홀 후보',unverified:'미검증'})[item.predicted_hole_type]||'알 수 없는 값';
   const label=document.createElement('strong');label.textContent='R12 내부면 참조 '+item.face_index+' · '+state;
   const detail=document.createElement('small');
   detail.textContent='근거: '+(item.decision_basis||'미확인')+' · 모델 예측: '+(item.raw_ml_top_class||'없음')+' · 참고 점수: '+(Number(item.uncalibrated_model_score)*100).toFixed(1)+'% (교정된 확률 아님)';
   row.append(label,detail);out.append(row);
  }
 }catch(e){if(sameRun())out.textContent='R12 실행 실패/취소: '+geoApiError(e).message;}
 finally{if(runGeneration===r12Generation){r12Running=false;btn.disabled=!r12Ready||!current||!file;}}
};
