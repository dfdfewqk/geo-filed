"""Read-only, fail-closed boundary between CalculiX archives and current result summaries.

This module never runs a solver, modifies an archive or asserts a structural safety
result. Call ONLY for completed tasks before build_summary()/html_report().
"""
from __future__ import annotations
import copy
import math
import re
from pathlib import Path

RUN_ID = re.compile(r'^[0-9a-f]{32}$')
SHA = re.compile(r'^[0-9a-f]{64}$')


def _reject(task, message):
    out = {k: v for k, v in task.items() if k not in ('result', 'field', 'surface_field')}
    out['status'] = 'failed'
    out['message'] = '계산 결과 원본 검증 실패: ' + message[:300]
    return out


def verify_directory_for_case(folder, case, cad_sha):
    """Dispatch on signed solver element; never reinterpret C3D10 as C3D4.

    C3D4 keeps the established independent Windows verifier. Quadratic C3D10
    has its own raw INP/STA/FRD/DAT integrity verifier in fea_solver.
    """
    if not isinstance(case, dict):
        raise ValueError('검증할 FEA 원본 조건이 없습니다.')
    mode = (case.get('mesh_request') or {}).get('element_type', 'C3D4')
    if mode == 'C3D10':
        from fea_solver import verify_c3d10_archive
        return verify_c3d10_archive(folder, case, cad_sha)
    if mode == 'C3D4':
        from fea_previous_import import verify_directory
        return verify_directory(folder, case, cad_sha)
    raise ValueError('FEA 검증할 수 없는 요소 형식: ' + str(mode)[:50])


def reverify_task_for_display(task, case, cad_sha, jobs_dir, *, verifier=None):
    """For a completed FEA task, replace its saved JSON values with verified FRD values.

    Failed/queued/running tasks are returned without results.  A solver JSON
    success flag alone is not trusted.  All paths are fixed by a validated run ID.
    Failures become a clearly failed task, NOT a zero stress or stale reading.
    """
    if not isinstance(task, dict):
        return {'status': 'failed', 'message': '계산 작업의 형식이 잘못되었습니다.'}
    state = task.get('status')
    if state != 'complete':
        # A retry/failed task can retain fields from an earlier successful run.
        # Never pass those numeric fields to summaries or a 3D renderer.
        out = copy.deepcopy(task)
        for key in ('result', 'field', 'surface_field', 'field_visualization'):
            out.pop(key, None)
        out.pop('source_validation', None)
        return out
    try:
        if not isinstance(case, dict):
            raise ValueError('검증할 해석 조건이 없습니다')
        if not isinstance(cad_sha, str) or not SHA.fullmatch(cad_sha):
            raise ValueError('CAD 식별값 형식 오류')
        c_sha = case.get('case_sha256')
        if not isinstance(c_sha, str) or not SHA.fullmatch(c_sha) or case.get('cad_sha256') != cad_sha:
            raise ValueError('CAD·FEA 계산 조건 식별값 불일치')
        task_id = task.get('id')
        if not isinstance(task_id, str) or not RUN_ID.fullmatch(task_id):
            raise ValueError('계산 실행 ID가 누락되었거나 잘못되었습니다')
        if task.get('cad_sha256') != cad_sha:
            raise ValueError('계산 작업 CAD가 현재 CAD와 다릅니다')
        if task.get('case_sha256') not in (None, c_sha):
            raise ValueError('계산 작업의 해석 조건이 현재 조건과 다릅니다')
        folder = Path(jobs_dir) / 'fea_runs' / task_id
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError('실제 계산 폴더를 확인할 수 없습니다')
        for name in ('case.json', 'result.json', 'geofield_case.inp', 'geofield_case.frd', 'geofield_case.sta'):
            item = folder / name
            if item.is_symlink() or not item.is_file():
                raise ValueError('실제 계산 근거가 없거나 심볼릭 링크입니다: ' + name)
        if verifier is None:
            # C3D4 remains on the trusted original verifier; C3D10 re-checks
            # full raw INP/STA/FRD/DAT rather than using the C3D4 parser.
            verifier = verify_directory_for_case
        actual, field = verifier(folder, case, cad_sha)
        if not isinstance(actual, dict):
            raise ValueError('원본 검증 함수가 결과 데이터를 반환하지 않았습니다')
        if (actual.get('schema') != 'geofield-fea-result-v1'
            or actual.get('status') != 'solver_executed_result_parsed'
            or actual.get('cad_sha256') != cad_sha
            or actual.get('case_sha256') != c_sha):
            raise ValueError('검증 결과의 CAD·조건·계산 상태가 일치하지 않습니다')
        mesh = actual.get('mesh') or {}
        values = actual.get('results') or {}
        node_count = mesh.get('node_count')
        element_count = mesh.get('tetrahedron_count')
        if type(node_count) is not int or node_count <= 0 or type(element_count) is not int or element_count <= 0:
            raise ValueError('메시 노드·요소 수가 유효하지 않습니다')
        if values.get('parsed_nodes') != node_count:
            raise ValueError('FRD의 노드 수가 실제 메시와 다릅니다')
        for key in ('maximum_nodal_von_mises_mpa', 'maximum_displacement_mm'):
            v = values.get(key)
            if type(v) not in (float, int) or not math.isfinite(v) or v < 0:
                raise ValueError('원본 FEA 응력·변위 값이 잘못되었습니다')
        out = copy.deepcopy(task)
        out['result'] = copy.deepcopy(actual)
        # Field values are available only when verified by the independent
        # re-import; never expose a stale 3D-ready flag from memory.
        if not isinstance(field, dict):
            out['result']['field_visualization'] = {'available': False, 'reason': '3D 필드 재검증 자료 없음'}
        out['source_validation'] = 'INP_STA_FRD_reverified'
        return out
    except (OSError, ValueError, TypeError, KeyError, OverflowError, UnicodeError, ImportError, RuntimeError) as exc:
        return _reject(task, str(exc))


def verified_archive_summary(entry, snapshot_id, history_db, jobs_dir, *, archive_verifier=None):
    """Fail closed when old HTML reports contain a completed, but stale FEA snapshot.

    CAD/ML parts remain readable, but old FEA numbers are hidden unless every
    archive run artifact is re-validated. Does not modify SQLite or solver files.
    """
    import copy
    copied=copy.deepcopy(entry)
    if not isinstance(copied,dict):
        raise ValueError('보존된 보고서가 올바르지 않습니다.')
    fea=copied.get('fea') or {}
    if not isinstance(fea,dict):
        raise ValueError('보존된 FEA 보고서 형식 오류')
    if fea.get('state')!='complete':
        # Suppress stale numerical evidence from interrupted/failed archives.
        for key in ('maximum_von_mises_mpa','maximum_displacement_mm',
                    'tetrahedron_count','node_count','field_visualization'):
            fea.pop(key,None)
        return copied
    try:
        if archive_verifier is None:
            from fea_compare import _side as archive_verifier
        actual=archive_verifier(history_db,jobs_dir,snapshot_id)
        cad=copied.get('cad') or {}
        if (actual.get('snapshot_id')!=snapshot_id or
            actual.get('cad_sha256')!=cad.get('sha256') or
            actual.get('run_id')!=fea.get('result_run_id') or
            actual.get('case_sha256')!=fea.get('result_case_sha256')):
            raise ValueError('보존된 보고서와 실제 계산 근거 식별자가 다릅니다.')
        # An archived report must already agree with its revalidated FRD.
        # Never silently overwrite a stored stress or displacement value.
        for source_key, report_key, abs_tolerance in (
            ('max_stress_mpa','maximum_von_mises_mpa',1e-8),
            ('max_displacement_mm','maximum_displacement_mm',1e-10)):
            n=actual.get(source_key)
            stored=fea.get(report_key)
            if (type(n) not in (float,int) or type(stored) not in (float,int) or
                not math.isfinite(n) or not math.isfinite(stored) or
                n<0 or stored<0 or
                not math.isclose(n,stored,rel_tol=1e-6,abs_tol=abs_tolerance)):
                raise ValueError('보존 보고서와 FRD 실제 수치 불일치: '+report_key)
        for count_key in ('node_count','tetrahedron_count'):
            known=actual.get('mesh_'+count_key)
            if known is not None and (type(known) is not int or
                                      type(fea.get(count_key)) is not int or
                                      fea[count_key]!=known):
                raise ValueError('보존 보고서와 실제 메시 개수 불일치: '+count_key)
        copied['fea']=fea
        return copied
    except (OSError,ValueError,KeyError,TypeError,OverflowError,RuntimeError,ImportError) as exc:
        invalid=dict(fea)
        for key in ('maximum_von_mises_mpa','maximum_displacement_mm',
                    'tetrahedron_count','node_count','field_visualization'):
            invalid.pop(key,None)
        invalid['state']='failed'
        invalid['status_text']='저장된 FEA 원본 재검증 실패: '+str(exc)[:250]
        copied['fea']=invalid
        return copied
