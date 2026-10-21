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
    runtime=resolve('GEOFIELD_R12_PYTHON',REQUIRED)
    if not runtime.get('ok'):
        missing.append('R12 Python 필수 모듈 미탐지 (cadquery, OCP, numpy, sklearn, joblib)')
    return {'available':not missing,'missing':missing,'python':runtime.get('path'),
            'python_error':runtime.get('error',''),
            'python_source':runtime.get('source','unknown'),
            'python_attempts':runtime.get('attempts',[]),
            'modules':runtime.get('modules',{}),'mode':'research_only_not_for_fea',
            'note':'실행에 성공해도 실제 산업용 STEP 분류 정확도는 검증되지 않았습니다.'}

def execute(root,step,out_dir):
    root=Path(root);base,model,manifest=locations(root)
    prepared=preflight(root)
    if not prepared['available']:
        raise RuntimeError(' / '.join(prepared['missing']))
    folder=Path(out_dir);folder.mkdir(parents=True,exist_ok=True)
    target=folder/'r12_prediction.json'
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
    d=json.loads(target.read_text(encoding='utf8'))
    if not isinstance(d,dict):raise ValueError('R12 결과 형식 오류')
    if d.get('cad_sha256')!=sha(step) or d.get('decision_usage')!='blocked_diagnostic_only':
        raise ValueError('R12 CAD 해시 또는 진단 모드 검증 실패')
    if (d.get('status')!='research_not_for_production' or
        d.get('fea_calculated') is not False or
        d.get('geometry_certified') is not False or
        d.get('is_independent_r12_research') is not True):
        raise ValueError('R12 결과 상태가 안전하지 않습니다')
    predictions=d.get('predictions')
    count=d.get('candidate_count')
    if (type(count) is not int or count<0 or count>10_000 or
        not isinstance(predictions,list) or len(predictions)!=count):
        raise ValueError('R12 후보 개수/형식 검증 실패')
    seen=set()
    for item in predictions:
        if not isinstance(item,dict):raise ValueError('R12 후보 항목 형식 오류')
        face=item.get('face_index')
        score=item.get('uncalibrated_model_score')
        if (type(face) is not int or face<0 or face in seen or
            item.get('predicted_hole_type') not in ('through_hole','blind_hole','unverified') or
            item.get('raw_ml_top_class') not in ('through_hole','blind_hole') or
            type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=1):
            raise ValueError('R12 후보 면·분류·점수 검증 실패')
        seen.add(face)
    return d
