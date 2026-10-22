"""GeoField: opt-in, serial three-mesh CalculiX study.

Never edits the active .fea_case.json or original STEP; each job has its own
signed case, run folder, verified FRD evidence, and append-only history snapshot.
No convergence/safety certification. Stop requests act BETWEEN actual solver runs.
"""
from __future__ import annotations
import copy, hashlib, json, math, os, subprocess, sys, threading, uuid
from pathlib import Path

ACTIVE={'queued','running'}
# GeoField mesh evidence completion 2026-10-19: verified status contains actual 3-mesh values.


def mesh_cases(base):
    if not isinstance(base,dict) or not isinstance(base.get('mesh_request'),dict):
        raise ValueError('저장된 FEA 메시 설정이 없습니다.')
    size=base['mesh_request'].get('target_element_size_mm')
    if type(size) not in (float,int) or not math.isfinite(size) or not .5 <= size <= 18:
        raise ValueError('기존 목표 메시 크기가 허용 범위를 벗어납니다.')
    sizes=[round(size*1.4,3),round(size,3),round(size*.75,3)]
    if min(sizes)<.5 or max(sizes)>18 or len(set(sizes))!=3:
        raise ValueError('메시 3단계 생성이 불가능합니다. 초기 메시 크기를 조정하세요 (각 단계 0.5~18mm).')
    cases=[]
    for ix,s in enumerate(sizes):
        c=copy.deepcopy(base)
        c['mesh_request']['target_element_size_mm']=s
        c['mesh_request']['auto_estimated']=False
        c['mesh_request']['series_origin']='explicit_user_mesh_sensitivity_run'
        if isinstance(c.get('preset_metadata'),dict):
            c['preset_metadata']['mesh_quality']=['study_coarse','study_baseline','study_fine'][ix]
            c['preset_metadata']['mesh_provenance']='USER_APPROVED_R18_8_SENSITIVITY_STUDY_NOT_CONVERGED'
        c.pop('case_sha256',None)
        c['case_sha256']=hashlib.sha256(json.dumps(c,sort_keys=True,ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()
        cases.append(c)
    return cases


def atomic_json(path, payload):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        os.replace(tmp,p)
    finally: tmp.unlink(missing_ok=True)


def public_state(study):
    keys=('id','cad_job_id','cad_sha256','status','sizes_mm','completed','total','current_index','error','cancel_requested','analysis_snapshot_ids','mesh_study_verified','study_analysis','message')
    return {k:study.get(k) for k in keys}


def run_one(root, step, case, model, folder, ccx, gmsh_runtime):
    """Use exactly the existing real solver or its existing separate-Python worker."""
    from fea_solver import run_real_fea
    from engine_runtime import prepare_python_environment
    root=Path(root);folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    py=gmsh_runtime.get('path') if gmsh_runtime.get('ok') else sys.executable
    if not py:raise RuntimeError('Gmsh Python 실행 경로를 확인하지 못했습니다.')
    if os.path.normcase(os.path.abspath(py))==os.path.normcase(os.path.abspath(sys.executable)):
        result=run_real_fea(step,case,model,folder,ccx)
    else:
        atomic_json(folder/'worker_case.json',case)
        atomic_json(folder/'worker_model.json',model)
        cmd=[py,str(root/'fea_engine_worker.py'),'--step',str(step), '--case',str(folder/'worker_case.json'),
             '--model',str(folder/'worker_model.json'),'--workdir',str(folder),'--ccx',str(ccx),
             '--result',str(folder/'worker_result.json')]
        kwargs={'creationflags':getattr(subprocess,'CREATE_NO_WINDOW',0)} if os.name=='nt' else {}
        p=subprocess.run(cmd,cwd=str(root),capture_output=True,text=True,errors='replace',timeout=240,
                         env=prepare_python_environment(py),**kwargs)
        (folder/'worker.log').write_text((p.stdout or '')[-14000:]+'\n'+(p.stderr or '')[-14000:],encoding='utf-8')
        if p.returncode or not (folder/'worker_result.json').is_file():
            raise RuntimeError('별도 Gmsh Python 해석 실패: '+(p.stderr or p.stdout or '')[-700:])
        result=json.loads((folder/'worker_result.json').read_text(encoding='utf-8'))
    if result.get('cad_sha256')!=case['cad_sha256'] or result.get('case_sha256')!=case['case_sha256']:
        raise ValueError('메시 작업 계산 결과와 CAD·조건 SHA 불일치')
    atomic_json(folder/'case.json',case)
    atomic_json(folder/'result.json',result)
    from fea_previous_import import verify_directory
    actual,_field=verify_directory(folder,case,case['cad_sha256'])
    if actual.get('case_sha256')!=case['case_sha256']:
        raise ValueError('실제 CalculiX 파일 검증 결과가 현재 조건과 다릅니다.')
    return actual


def execute_series(study, root, jobs_dir, history_db, jobs, ml_jobs, lock, run_one_fn=None):
    """Background thread: sequential real runs; partial successes remain identifiable."""
    from geometry_dimensions import measure_geometry
    from integrated_results import build_summary
    from history_store import save as archive_save
    from fea_solver import status as fea_status
    root=Path(root); jobs_dir=Path(jobs_dir); study_folder=jobs_dir/'fea_mesh_series'/study['id']
    manifest=study_folder/'manifest.json'
    save=lambda: atomic_json(manifest,public_state(study))
    study['status']='running';study['message']='실제 FEA 순차 계산 시작';save()
    try:
        runner=run_one_fn or run_one
        with lock:
            job=copy.deepcopy(jobs.get(study['cad_job_id']) or {})
            ml=[dict(v) for v in ml_jobs.values() if v.get('cad_job_id')==study['cad_job_id']]
        if job.get('status')!='complete' or job.get('sha256')!=study['cad_sha256']:
            raise ValueError('계산 시작 전에 CAD 작업이 변경됐습니다.')
        model=json.loads((jobs_dir/(study['cad_job_id']+'.json')).read_text(encoding='utf-8'))
        if model.get('sha256')!=study['cad_sha256']:
            raise ValueError('저장된 CAD 모델 SHA 불일치')
        geometry=measure_geometry(job['analysis'],model['mesh']['face_ids'])
        for i,case in enumerate(study['cases']):
            if study.get('cancel_requested'):
                study['status']='cancelled';study['message']='다음 메시 계산 시작 전 사용자 요청으로 중단';save();return
            with lock:
                if jobs.get(study['cad_job_id'],{}).get('sha256')!=study['cad_sha256']:
                    raise ValueError('실행 중 CAD가 변경됐습니다. 남은 메시 계산을 중단합니다.')
            rid=uuid.uuid4().hex
            study['current_index']=i;study['message']=f'{i+1}/3 메시 {study["sizes_mm"][i]}mm CalculiX 계산 중';save()
            folder=jobs_dir/'fea_runs'/rid
            try:
                result=runner(root,study_folder/'input.step',case,model,folder,study['ccx'],study['gmsh_runtime'])
                task={'id':rid,'cad_job_id':study['cad_job_id'],'cad_sha256':study['cad_sha256'],
                      'case_sha256':case['case_sha256'],'status':'complete','result':result}
                summary=build_summary(job,geometry,ml[-1] if ml else None,task,case,fea_status())
                if summary['fea']['state']!='complete':
                    raise ValueError('메시 계산 결과와 보고서 검증이 일치하지 않습니다.')
                sid=archive_save(history_db,'fea_result',study['cad_job_id'],summary)
                study['analysis_snapshot_ids'].append(sid)
                study['completed']+=1;save()
            except Exception as exc:
                study['error']=str(exc)[:900]
                if folder.is_dir(): (folder/'mesh_series_error.log').write_text(str(exc),encoding='utf-8')
                raise
        # Once all runs exist, independently reverify all three from archived evidence.
        from fea_convergence import assess
        verified=assess(history_db,jobs_dir,study['analysis_snapshot_ids'])
        study['mesh_study_verified']=verified['status']=='verified_three_mesh_sensitivity_only'
        study['study_analysis']={
            'status':verified['status'],
            'mesh_count_increases_with_refinement':verified['mesh_count_increases_with_refinement'],
            'node_count_increases_with_refinement':verified['node_count_increases_with_refinement'],
            'numeric_stability_diagnostic':verified['numeric_stability_diagnostic'],
            'actual_load_moment_comparability':verified.get('actual_load_moment_comparability'),
            'actual_mesh_resolution_diagnostic':verified.get('actual_mesh_resolution_diagnostic'),
            'verified_result_rows':verified['verified_result_rows'],
            'adjacent_changes':verified['adjacent_changes'], 'warning':verified['warning'],
            'convergence_certified':False, 'safety_certified':False,
        }
        study['status']='complete';study['message']='실제 계산 3건과 민감도 검사 완료 (수렴·안전 인증 아님)';save()
    except Exception as exc:
        study['status']='failed';study['error']=str(exc)[:900]
        study['message']='실제 메시 계산 또는 검증 실패; 성공했던 작업은 개별 보존';save()
    finally:
        # Do not delete the submitted STEP copy until the calculations end.
        (study_folder/'input.step').unlink(missing_ok=True)
        study.pop('cases',None);study.pop('gmsh_runtime',None);study.pop('ccx',None)


def start_series(studies,lock,root,jobs_dir,history_db,jobs,ml_jobs,uid,case,source,sha,ccx,gmsh_runtime):
    """Called only after verified STEP upload and explicit UI confirmation."""
    if source.is_symlink() or not source.is_file():raise ValueError('검증된 STEP 복사본이 없습니다.')
    cases=mesh_cases(case)
    with lock:
        if any(s.get('status') in ACTIVE for s in studies.values()):
            raise ValueError('다른 메시 3단계 계산이 실행 중입니다.')
        if jobs.get(uid,{}).get('status')!='complete' or jobs[uid].get('sha256')!=sha:
            raise ValueError('현재 CAD 작업과 원본 STEP이 일치하지 않습니다.')
        sid=uuid.uuid4().hex
        study={'id':sid,'cad_job_id':uid,'cad_sha256':sha,'status':'queued','total':3,'completed':0,
               'current_index':None,'sizes_mm':[c['mesh_request']['target_element_size_mm'] for c in cases],
               'cases':cases,'ccx':ccx,'gmsh_runtime':gmsh_runtime,'cancel_requested':False,
               'analysis_snapshot_ids':[],'mesh_study_verified':False,'study_analysis':None,'error':'','message':'대기'}
        folder=Path(jobs_dir)/'fea_mesh_series'/sid
        folder.mkdir(parents=True,exist_ok=False)
        os.replace(source,folder/'input.step')
        atomic_json(folder/'manifest.json',public_state(study))
        studies[sid]=study
        thread=threading.Thread(target=execute_series,args=(study,root,jobs_dir,history_db,jobs,ml_jobs,lock),daemon=True)
        thread.start()
        return public_state(study)
