# -*- coding: utf-8 -*-
"""R12 research-only STEP bore inference bridge. Not used by FEA or CAD truth."""
from pathlib import Path
import hashlib,json,math,os,subprocess
from engine_runtime import prepare_python_environment
from ml_env_resolver import resolve

REQUIRED=('cadquery','OCP','numpy','sklearn','joblib')
EXPECTED_MODEL_SHA256='df51d702ee77fb9efdc2de730f679f62d18e652c9d6279736e4deef353535dd0'

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while True:
            chunk=f.read(1024*1024)
            if not chunk:break
            h.update(chunk)
    return h.hexdigest()

def locations(root):
    base=Path(root)/'ml'/'r12_research'
    return base,base/'research_model.joblib',base/'report.json'

def preflight(root):
    base,model,manifest=locations(root)
    missing=[]
    try:
        if not model.is_file() or not manifest.is_file():
            raise ValueError('R12 연구 모델 파일이 없습니다.')
        info=json.loads(manifest.read_text(encoding='utf8'))
        if (info.get('eligible_for_production') is not False or
            info.get('model_use')!='research_only' or
            info.get('model_sha256')!=EXPECTED_MODEL_SHA256 or
            sha(model)!=EXPECTED_MODEL_SHA256):
            raise ValueError('R12 연구 모델 해시 또는 사용 제한이 일치하지 않습니다.')
        for fname in ('worker.py','features.py','train_eval.py','build_data.py'):
            if not (base/fname).is_file():raise ValueError('R12 모듈 누락: '+fname)
    except (ValueError,OSError,KeyError,json.JSONDecodeError) as e:
        missing.append(str(e)[:280])
    # Missing/changed signed assets cannot be fixed by probing an unrelated
    # Python installation. Probe imports only when trusted model and worker
    # sources are present: the resolver may otherwise wait up to 55 seconds
    # and make a normal CAD/FEA screen appear stalled.
    if missing:
        return {'available':False,'missing':missing,'python':None,
                'python_error':'ML asset check failed; Python probe not run',
                'python_source':'skipped_missing_or_untrusted_assets',
                'python_attempts':[],'modules':{},'mode':'research_only_not_for_fea',
                'note':'원본 모델/파일 점검 실패. 추론 미실행; CAD/FEA는 별개로 유지.'}
    runtime=resolve('GEOFIELD_R12_PYTHON',REQUIRED)
    if not runtime.get('ok'):
        missing.append('R12 Python 필수 모듈 미탐지 (cadquery, OCP, numpy, sklearn, joblib)')
    return {'available':not missing,'missing':missing,'python':runtime.get('path'),
            'python_error':runtime.get('error',''),
            'python_source':runtime.get('source','unknown'),
            'python_attempts':runtime.get('attempts',[]),
            'modules':runtime.get('modules',{}),'mode':'research_only_not_for_fea',
            'note':'실행에 성공해도 실제 산업용 STEP 분류 정확도는 검증되지 않았습니다.'}

def validate_research_result(data, expected_sha):
    """Fail closed on untrusted worker JSON before reporting a research result.

    No score, class or CAD geometry fact is inferred or repaired here.
    """
    if not isinstance(data,dict):raise ValueError('R12 결과 형식 오류')
    if (data.get('cad_sha256')!=expected_sha or
        data.get('decision_usage')!='blocked_diagnostic_only' or
        data.get('status')!='research_not_for_production' or
        data.get('fea_calculated') is not False or
        data.get('geometry_certified') is not False or
        data.get('is_independent_r12_research') is not True):
        raise ValueError('R12 연구 결과 출처·CAD 해시·사용 제한 오류')
    predictions=data.get('predictions');count=data.get('candidate_count')
    if (type(count) is not int or count<0 or count>10_000 or
            not isinstance(predictions,list) or len(predictions)!=count):
        raise ValueError('R12 후보 개수/형식 검증 실패')
    seen=set();classes=('through_hole','blind_hole')
    allowed_basis=('model_and_brep_topology_agree','model_topology_conflict',
                   'insufficient_brep_evidence','coaxial_multisegment_hole_unsupported')
    for item in predictions:
        if not isinstance(item,dict):raise ValueError('R12 후보 항목 형식 오류')
        face=item.get('face_index');score=item.get('uncalibrated_model_score')
        raw=item.get('raw_ml_top_class');predicted=item.get('predicted_hole_type')
        ev=item.get('topology_evidence');basis=item.get('decision_basis')
        thresholded=item.get('raw_ml_thresholded')
        if (type(face) is not int or face<0 or face in seen or
                type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=1 or
                raw not in classes or predicted not in (*classes,'unverified') or
                thresholded not in (*classes,'unverified') or ev not in (*classes,None) or
                basis not in allowed_basis or item.get('status')!='research_unverified'):
            raise ValueError('R12 후보 면·점수·분류·연구 상태 검증 실패')
        seen.add(face)
        if basis=='model_and_brep_topology_agree':
            coherent=(ev==raw and predicted==raw)
        elif basis=='model_topology_conflict':
            coherent=(ev in classes and ev!=raw and predicted=='unverified')
        elif basis=='insufficient_brep_evidence':
            coherent=(ev is None and predicted=='unverified')
        else:
            coherent=predicted=='unverified'
        if not coherent:raise ValueError('R12 모델 예측과 B-Rep 근거가 모순됩니다.')
    return data


def execute(root,step,out_dir):
    root=Path(root);base,model,manifest=locations(root)
    prepared=preflight(root)
    if not prepared['available']:
        raise RuntimeError(' / '.join(prepared['missing']))
    step=Path(step)
    expected_step_sha=sha(step)
    folder=Path(out_dir);folder.mkdir(parents=True,exist_ok=True)
    target=folder/'r12_prediction.json'
    # Never treat a previous run's output as success when a worker exits early.
    if target.exists():raise ValueError('이전 R12 출력이 남아 있어 새 추론을 시작하지 않습니다.')
    cmd=[prepared['python'],'-m','ml.r12_research.worker','--step',str(step),
         '--out',str(target),'--model',str(model),'--manifest',str(manifest)]
    kwargs={'creationflags':getattr(subprocess,'CREATE_NO_WINDOW',0)} if os.name=='nt' else {}
    p=subprocess.run(cmd,cwd=str(root),capture_output=True,text=True,errors='replace',timeout=180,
                     env=prepare_python_environment(prepared['python']),**kwargs)
    (folder/'r12_worker.log').write_text((p.stdout+'\n'+p.stderr)[-8000:],encoding='utf8')
    if p.returncode!=0 or not target.is_file():
        raise RuntimeError('R12 독립 추론 실패: '+(p.stderr or p.stdout)[-600:])
    if target.stat().st_size>2_000_000:
        raise ValueError('R12 결과 파일 크기 제한 초과')
    if sha(step)!=expected_step_sha:
        raise ValueError('R12 추론 도중 STEP 복사본이 변경됐습니다.')
    d=json.loads(target.read_text(encoding='utf8'))
    return validate_research_result(d,expected_step_sha)
