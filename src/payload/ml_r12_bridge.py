# -*- coding: utf-8 -*-
"""R12 research-only STEP bore inference bridge. Not used by FEA or CAD truth."""
from pathlib import Path
import hashlib,json,math,os,subprocess
try:
    from engine_runtime import prepare_python_environment
except ImportError:
    def prepare_python_environment(path=None):
        return os.environ.copy()
from ml_env_resolver import resolve

REQUIRED=('cadquery','OCP','numpy','sklearn','joblib')
EXPECTED_MODEL_SHA256='df51d702ee77fb9efdc2de730f679f62d18e652c9d6279736e4deef353535dd0'
# Git blob ID of the original bundled 108-row R12 training/evaluation JSON;
# prevents tampered labels+metrics from passing simple self-consistency checks.
# Git blob bytes use LF; Windows CRLF-only conversion is normalized first.
EXPECTED_EVAL_GIT_BLOB_SHA1='0971ae85e78efbe87c15c7a98a6405ac53f6694b'

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



def verified_synthetic_holdout(root):
    """Recompute the bundled R12 *synthetic* holdout counts from raw records.

    This checks the existing model hash, train/validation/test family
    separation, per-record labels, confusion matrix and recorded accuracy.
    It does NOT execute/retrain a model or claim accuracy on real STEP CAD.
    No paid AI, solver, network or persistent file modifications.
    """
    base, model, manifest = locations(root)
    if not model.is_file() or not manifest.is_file():
        raise ValueError('R12 모델/합성 시험 평가 기록 누락')
    if sha(model) != EXPECTED_MODEL_SHA256:
        raise ValueError('R12 실제 모델 가중치 SHA-256 불일치')
    if manifest.stat().st_size > 5_000_000:
        raise ValueError('R12 평가 기록 크기 제한 초과')
    payload=manifest.read_bytes()
    canonical=payload.replace(b'\r\n',b'\n')
    git_header=b'blob '+str(len(canonical)).encode('ascii')+b'\x00'
    if hashlib.sha1(git_header+canonical).hexdigest()!=EXPECTED_EVAL_GIT_BLOB_SHA1:
        raise ValueError('R12 연구 평가 원본의 고정 Git 블롭 해시 불일치')
    report = json.loads(canonical.decode('utf8'))
    if (report.get('schema') != 'geofield_research_ml_v1' or
        report.get('model_sha256') != EXPECTED_MODEL_SHA256 or
        report.get('split_policy') != 'by_geometry_family' or
        report.get('model_use') != 'research_only' or
        report.get('eligible_for_production') is not False or
        report.get('model_score_is_calibrated_probability') is not False or
        report.get('never_provides_FEA_or_strength_results') is not True):
        raise ValueError('R12 연구용 모델/시험 기록 출처·사용 범위 오류')
    splits=('train','val','test')
    families=report.get('families')
    metrics=report.get('metrics')
    part_counts=report.get('part_counts')
    bore_counts=report.get('bore_candidate_counts')
    if not all(isinstance(x,dict) for x in
               (families,metrics,part_counts,bore_counts)):
        raise ValueError('R12 합성 평가 분할/행렬 누락')
    seen_families=set()
    seen_records=set()
    labels=['no_hole','through_hole','blind_hole','unverified']
    summary={}
    for split in splits:
        group=families.get(split)
        info=metrics.get(split)
        if (not isinstance(group,list) or not group or
            any(type(x) is not str or not x or x in seen_families for x in group) or
            len(set(group))!=len(group) or
            not isinstance(info,dict)):
            raise ValueError('R12 합성 형상 계열 분할 독립성 오류: '+split)
        seen_families.update(group)
        rows=info.get('prediction_records')
        expected_count=part_counts.get(split)
        expected_candidates=bore_counts.get(split)
        if (not isinstance(rows,list) or
            type(expected_count) is not int or not 1<=expected_count<=10000 or
            type(expected_candidates) is not int or
            not 0<=expected_candidates<=expected_count or
            len(rows)!=expected_count or info.get('part_count')!=expected_count or
            info.get('confusion_labels')!=labels):
            raise ValueError('R12 합성 시험 표본수/정답 항목 오류: '+split)
        matrix=[[0]*4 for _ in labels]
        assisted=[[0]*4 for _ in labels]
        correct=0
        assisted_correct=0
        candidates=0
        for row in rows:
            if not isinstance(row,dict):
                raise ValueError('R12 합성 시험 원시 결과 행 오류')
            rid=row.get('id')
            actual=row.get('actual')
            predicted=row.get('predicted')
            predicted_assisted=row.get('topology_assisted_predicted')
            family=row.get('family')
            nc=row.get('candidate_count')
            if (not isinstance(rid,str) or not rid or rid in seen_records or
                family not in group or actual not in labels[:3] or
                predicted not in labels or predicted_assisted not in labels or
                type(nc) is not int or nc<0 or nc>16 or
                type(row.get('correct')) is not bool or
                type(row.get('assisted_correct')) is not bool):
                raise ValueError('R12 합성 시험 원본 행 식별/라벨 불일치')
            seen_records.add(rid)
            candidates+=nc
            a=labels.index(actual)
            matrix[a][labels.index(predicted)]+=1
            assisted[a][labels.index(predicted_assisted)]+=1
            this_correct=(predicted==actual)
            this_assisted=(predicted_assisted==actual)
            if row['correct']!=this_correct or row['assisted_correct']!=this_assisted:
                raise ValueError('R12 합성 시험 개별 정답 판정이 예측값과 다릅니다')
            correct+=this_correct
            assisted_correct+=this_assisted
        if (candidates!=expected_candidates or
            matrix!=info.get('confusion_matrix') or
            assisted!=info.get('topology_assisted_confusion_matrix') or
            info.get('correct_count')!=correct or
            info.get('topology_assisted_correct_count')!=assisted_correct):
            raise ValueError('R12 합성 시험 혼동행렬/정답/후보수 교차검증 실패: '+split)
        def close(a,b):
            return type(a) in (int,float) and math.isfinite(a) and abs(a-b)<=1e-12
        if (not close(info.get('accuracy_including_abstentions'),
                      correct/expected_count) or
            not close(info.get('topology_assisted_accuracy_including_abstentions'),
                      assisted_correct/expected_count)):
            raise ValueError('R12 합성 시험 정확도 재계산 불일치: '+split)
        summary[split]={'parts':expected_count,'correct':correct,
                        'topology_assisted_correct':assisted_correct,
                        'accuracy':correct/expected_count,
                        'topology_assisted_accuracy':assisted_correct/expected_count,
                        'families':list(group),
                        'confusion_labels':labels.copy(),
                        'confusion_matrix':matrix,
                        'topology_assisted_confusion_matrix':assisted}
    return {
        'schema':'geofield-r12-synthetic-holdout-source-recomputed-v1',
        'status':'source_recomputed_synthetic_family_holdout_only',
        'model_sha256':EXPECTED_MODEL_SHA256,
        'split_policy':'by_geometry_family',
        'test':summary['test'],'validation':summary['val'],'training':summary['train'],
        'val_threshold_tuned_only_on_validation':
            report.get('val_threshold_tuned_only_on_validation'),
        'independent_real_cad_accuracy_verified':False,
        'production_eligible':False,
        'scope':'Synthetic geometry families only; no independently labeled real CAD evaluation or safety certification.'
    }

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
