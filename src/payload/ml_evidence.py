# -*- coding: utf-8 -*-
"""Read-only GeoField ML evidence contract; never a structural safety verdict.

This module validates the provenance of an already executed optional research
worker. It is intentionally independent of CAD/FEA solver and UI code.
"""
from __future__ import annotations
import math

_SCHEMA = 'geofield-ml-evidence-v1'
_STATES = frozenset(('queued', 'running', 'complete', 'failed', 'unavailable', 'not_run'))


def select_current_task(cad_job_id, cad_sha256, active_run_id, brep_tasks, r12_tasks):
    """Choose only the current CAD's requested run, never stale cross-provider data.

    The automatic run ID is authoritative. An absent/mismatching active run
    cannot silently fall back to an older success or another provider. Manual
    runs are considered only when no automatic run ID was selected.
    """
    valid_cad=(isinstance(cad_job_id,str) and len(cad_job_id)==32 and
        all(c in '0123456789abcdef' for c in cad_job_id) and
        isinstance(cad_sha256,str) and len(cad_sha256)==64 and
        all(c in '0123456789abcdef' for c in cad_sha256))
    if not valid_cad:
        raise ValueError('Invalid current CAD identity for ML task selection')
    if active_run_id is not None and (not isinstance(active_run_id,str) or
        len(active_run_id)!=32 or any(c not in '0123456789abcdef' for c in active_run_id)):
        raise ValueError('Invalid active ML run identity')
    matches=[]
    for provider,tasks in (('brepmfr',brep_tasks),('r12',r12_tasks)):
        if not isinstance(tasks,list):
            raise ValueError('Invalid ML task collection')
        for task in tasks:
            if (not isinstance(task,dict) or
                task.get('cad_job_id')!=cad_job_id or
                task.get('cad_sha256')!=cad_sha256):
                continue
            ident=task.get('id')
            if (not isinstance(ident,str) or len(ident)!=32 or
                any(c not in '0123456789abcdef' for c in ident)):
                continue
            matches.append((provider,task))
    if active_run_id is not None:
        selected=[entry for entry in matches if
                  entry[1]['id']==active_run_id and entry[1].get('automatic') is True]
        if len(selected)>1:
            raise ValueError('Ambiguous active ML run identity')
        return selected[0] if selected else None
    # Explicit/manual requests do not resurrect an older automatic result.
    manual=[entry for entry in matches if entry[1].get('automatic') is not True]
    return manual[-1] if manual else None


def build_evidence(cad_job_id, cad_sha256, *, task=None, provider=None, model_sha256=None, message='', status='not_run'):
    """Return restricted evidence for the selected CAD, rejecting stale successes.

    Fails closed on any unexpected schema/ID or unverifiable research response.
    The API is diagnostic only. It must never become a structural safety input.
    """
    if (not isinstance(cad_job_id, str) or len(cad_job_id) != 32 or
        any(c not in '0123456789abcdef' for c in cad_job_id) or
        not isinstance(cad_sha256, str) or len(cad_sha256) != 64 or
        any(c not in '0123456789abcdef' for c in cad_sha256)):
        raise ValueError('ML CAD identity must be an immutable SHA-256/UUID pair')
    if task is None:
        if status not in ('not_run','unavailable','failed','disabled_by_user'):
            raise ValueError('Invalid unavailable ML evidence state')
        return {'schema': _SCHEMA, 'cad_job_id': cad_job_id, 'cad_sha256': cad_sha256,
                'provider': 'none', 'status': status, 'research_only': True,
                'geometry_certified': False, 'fea_calculated': False,
                'eligible_for_structural_decision': False, 'predictions': [],
                'message': str(message)[:320]}
    if not isinstance(task, dict) or provider not in ('r12', 'brepmfr'):
        raise ValueError('Unrecognized ML evidence provider')
    if task.get('cad_job_id') != cad_job_id or task.get('cad_sha256') != cad_sha256:
        raise ValueError('ML task belongs to a different CAD')
    status=task.get('status')
    if status not in _STATES:
        raise ValueError('Unexpected ML task status')
    run_id=task.get('id')
    if (not isinstance(run_id,str) or len(run_id)!=32 or
        any(c not in '0123456789abcdef' for c in run_id)):
        raise ValueError('ML run ID is invalid')
    restored=task.get('restored_from_run_id')
    if restored is not None and (not isinstance(restored,str) or len(restored)!=32 or
        any(c not in '0123456789abcdef' for c in restored)):
        raise ValueError('ML restored run ID is invalid')
    if not isinstance(model_sha256, str) or len(model_sha256)!=64 or any(c not in '0123456789abcdef' for c in model_sha256):
        raise ValueError('ML checkpoint fingerprint is required')
    base={'schema': _SCHEMA, 'cad_job_id': cad_job_id, 'cad_sha256': cad_sha256,
          'run_id': task.get('id'), 'provider': provider, 'model_sha256': model_sha256,
          'status': status, 'research_only': True, 'geometry_certified': False,
          'fea_calculated': False, 'eligible_for_structural_decision': False,
          'uncalibrated_scores': True, 'predictions': [], 'message':str(task.get('message') or '')[:320],
          'model_version': (('r12-research-' if provider=='r12' else 'brepmfr-checkpoint-') +
                             model_sha256[:12]),
          'completed_at': task.get('completed_at') if status=='complete' else None,
          'restored_from_run_id': restored if status=='complete' else None}
    if status=='complete' and task.get('completed_at') is not None:
        t=task['completed_at']
        if not isinstance(t,str) or len(t)>64 or not t.endswith('+00:00'):
            raise ValueError('ML completed timestamp is invalid')
    if status != 'complete':
        return base
    data=task.get('result')
    if not isinstance(data,dict) or data.get('decision_usage')!='blocked_diagnostic_only':
        raise ValueError('ML result is not explicitly restricted to research')
    if provider=='r12':
        if (data.get('cad_sha256')!=cad_sha256 or
            data.get('status')!='research_not_for_production' or
            data.get('is_independent_r12_research') is not True or
            data.get('geometry_certified') is not False or
            data.get('fea_calculated') is not False):
            raise ValueError('R12 model provenance is missing or not research-only')
        predictions=data.get('predictions')
        if (not isinstance(predictions,list) or len(predictions)>10000 or
            data.get('candidate_count')!=len(predictions)):
            raise ValueError('R12 candidate count mismatch')
        seen=set()
        for item in predictions:
            if not isinstance(item,dict):raise ValueError('Invalid R12 prediction')
            face=item.get('face_index');score=item.get('uncalibrated_model_score')
            if (type(face)!=int or face<0 or face in seen or type(score) not in (int,float) or
                not math.isfinite(score) or not 0<=score<=1 or
                item.get('predicted_hole_type') not in ('through_hole','blind_hole','unverified') or
                item.get('status')!='research_unverified'):
                raise ValueError('Invalid R12 candidate identity or uncalibrated score')
            seen.add(face)
        base['predictions']=[{'face_index':item['face_index'],
                              'predicted_hole_type':item['predicted_hole_type'],
                              'decision_basis':item.get('decision_basis'),
                              'uncalibrated_model_score':item['uncalibrated_model_score'],
                              'status':'research_unverified'} for item in predictions]
    else:
        if data.get('sha256') != cad_sha256:
            raise ValueError('BrepMFR model result CAD mismatch')
        variants=data.get('variants')
        topo=variants.get('topology_trimmed') if isinstance(variants,dict) else None
        faces=topo.get('faces') if isinstance(topo,dict) else None
        if not isinstance(faces,list) or len(faces)>10000:
            raise ValueError('BrepMFR missing or excessive faces')
        seen=set()
        for face in faces:
            if not isinstance(face,dict):raise ValueError('Invalid BrepMFR face')
            ordinal=face.get('face_ordinal');score=face.get('model_score_uncalibrated')
            if (type(ordinal)!=int or ordinal<0 or ordinal in seen or
                type(score) not in (int,float) or not math.isfinite(score) or
                not isinstance(face.get('model_class'),str) or not isinstance(face.get('geometry_surface'),str)):
                raise ValueError('BrepMFR face identity/score invalid')
            seen.add(ordinal)
        base['predictions']=[{'face_ordinal':item['face_ordinal'],
                             'model_class':item['model_class'],
                             'geometry_surface':item['geometry_surface'],
                             'uncalibrated_model_score':item['model_score_uncalibrated'],
                             'status':'research_unverified'} for item in faces]
    return base
