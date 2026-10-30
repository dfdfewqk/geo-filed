"""A08: evidence-labelled current FEA HTML and immutable atomic export.

No STEP/FRD/ML source files, images, archived SQLite records, private runtime
modules, API keys or remote services are accessed by this pure report module.
"""
from __future__ import annotations

from html import escape
import hashlib
import math
import os
from pathlib import Path
import re
import tempfile

RUN = re.compile(r"^[0-9a-f]{32}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
MAX_HTML = 4 * 1024 * 1024


def _text(value, *, limit=160):
    if value is None:
        return "확인 불가"
    if isinstance(value, (str, int, float)) and len(str(value)) <= limit:
        return escape(str(value), quote=True)
    return "확인 불가"


def _number(value, label, suffix):
    if type(value) not in (float,int) or not math.isfinite(value) or value < 0:
        raise ValueError("보고서 " + label + "의 검증된 계산 수치가 없습니다.")
    return escape(format(value, ".8g")) + " " + suffix


def _identified(summary, provenance):
    if not isinstance(summary,dict) or not isinstance(provenance,dict):
        raise ValueError("보고서 생성 근거가 없습니다.")
    cad, fea = summary.get("cad") or {}, summary.get("fea") or {}
    run, cad_sha = provenance.get("verified_run_id"), cad.get("sha256")
    case_sha = provenance.get("solved_case_sha256")
    if (not isinstance(run,str) or not RUN.fullmatch(run) or
            not isinstance(cad_sha,str) or not SHA.fullmatch(cad_sha) or
            not isinstance(case_sha,str) or not SHA.fullmatch(case_sha) or
            provenance.get("source_verification")!="INP_STA_FRD_reverified" or
            provenance.get("summary_numbers_crosschecked") is not True or
            fea.get("state")!="complete" or
            fea.get("result_run_id") not in (None,run) or
            fea.get("result_case_sha256") not in (None,case_sha)):
        raise ValueError("보고서 응력·변위 원본의 실행 ID 및 SHA-256 검증이 완료되지 않았습니다.")
    return run,cad_sha,case_sha,fea


def compose_evidence_html(summary, provenance, case, *, local_agent=None,
                          external_agent=None):
    """Append measured evidence, never a fabricated 3D screenshot or AI text.

    The caller must have passed A07 full numeric and mesh source revalidation.
    DeepSeek (or any external explanation) is never inferred from configuration
    alone: a fully bound, explicit opt-in, executed response is required.
    """
    run,sha,case_sha,fea=_identified(summary,provenance)
    stress=_number(fea.get("maximum_von_mises_mpa"),"응력","MPa")
    disp=_number(fea.get("maximum_displacement_mm"),"변위","mm")
    n,t=fea.get("node_count"),fea.get("tetrahedron_count")
    if type(n) is not int or n<1 or type(t) is not int or t<1:
        raise ValueError("검증된 메시 노드/요소 개수가 없습니다.")
    case=case if isinstance(case,dict) and case.get("cad_sha256")==sha and case.get("case_sha256")==case_sha else {}
    material=case.get("material") or {}
    bc=case.get("boundary_conditions") or {}
    mesh=case.get("mesh_request") or {}
    force=bc.get("total_force_n")
    if type(force) not in (int,float) or not math.isfinite(force) or force<0:
        force=None
    direction=bc.get("force_direction_unit")
    if not (isinstance(direction,list) and len(direction)==3 and
            all(type(x) in (int,float) and math.isfinite(x) for x in direction)
            and math.isclose(math.sqrt(sum(x*x for x in direction)),1,rel_tol=1e-5,abs_tol=1e-5)):
        direction=None
    # The report cannot send a list to _text() (which accepts scalars only):
    # an otherwise correctly verified [-1,0,0] used to display "확인 불가".
    direction_text=("(" + ", ".join(format(x,".5g") for x in direction) + ")"
                    if direction is not None else "확인 불가")
    # Independent solver-result element evidence takes precedence over the
    # requested mesh. Never silently call a different requested type verified.
    verified_type=provenance.get("verified_element_type")
    if verified_type not in ("C3D4","C3D10"):
        verified_type=None
    requested_type=mesh.get("element_type")
    if requested_type not in ("C3D4","C3D10"):
        requested_type=None
    if verified_type and requested_type and verified_type!=requested_type:
        element_text="조건/실제 요소 형식 불일치 · 검증 필요"
    elif verified_type:
        element_text=verified_type+" (실제 솔버 메시)"
    elif requested_type:
        element_text=requested_type+" (저장된 조건 · 실제 요소 확인 불가)"
    else:
        element_text="확인 불가"
    fixed=bc.get("fixed_face_ids")
    loaded=bc.get("load_face_ids")
    def face_count(value):
        return len(value) if isinstance(value,list) and all(type(n) is int and n>0 for n in value) else None
    def row(name,value):
        return "<tr><th>"+escape(name)+"</th><td>"+value+"</td></tr>"
    rows=[
        row("CAD 원본 SHA-256",_text(sha,limit=64)),
        row("검증된 실행 ID",_text(run,limit=32)),
        row("FEA 조건 SHA-256",_text(case_sha,limit=64)),
        row("재료",_text(material.get("name"))),
        row("영률",_text(material.get("young_modulus_mpa"))+" MPa" if type(material.get("young_modulus_mpa")) in (int,float) and math.isfinite(material["young_modulus_mpa"]) else "확인 불가"),
        row("고정 면 수",_text(face_count(fixed))),
        row("하중 면 수",_text(face_count(loaded))),
        row("하중 합력",_number(force,"하중","N") if force is not None else "확인 불가"),
        row("하중 방향",direction_text),
        row("메시 요소",escape(element_text,quote=True)),
        row("전체 절점 최대 von Mises 응력",stress),
        row("전체 절점 최대 변위",disp),
        row("검증된 노드 / 사면체 요소",f"{n} / {t}"),
    ]
    ml=summary.get("ml")
    if isinstance(ml,dict):
        state=ml.get("state") or ml.get("status")
    else:
        state=None
    ml_note=("실험적 ML 상태: "+_text(state)+
             " · CAD/FEA 수치의 출처나 설계 안전성 승인에 사용하지 않았습니다.")
    local_ok=(isinstance(local_agent,dict) and
              local_agent.get("schema")=="geofield-evidence-agent-v1" and
              local_agent.get("mode")=="rules_only" and
              local_agent.get("cad_sha256")==sha and
              (local_agent.get("llm") or {}).get("executed") is False)
    local_note=("동일 CAD 기반 규칙 설명 포함 · 해석 승인 아님" if local_ok else
                "분석 불가 또는 실행하지 않음 · 검증된 FEA 수치는 유지")
    deepseek_ok=(isinstance(external_agent,dict) and
                 external_agent.get("provider")=="deepseek" and
                 external_agent.get("status")=="external_explanation_only" and
                 external_agent.get("executed") is True and
                 external_agent.get("opt_in") is True and
                 external_agent.get("cad_sha256")==sha and
                 external_agent.get("run_id")==run and
                 external_agent.get("case_sha256")==case_sha and
                 isinstance(external_agent.get("explanation"),str) and
                 0<len(external_agent["explanation"].strip())<=1600)
    ext=("사용자 동의·실제 연결·동일 실행 검증된 DeepSeek 설명: "+
         _text(external_agent["explanation"],limit=1600)) if deepseek_ok else (
         "DeepSeek 설명: 표시 불가 (사용자 동의·실제 호출 결과·동일 실행 검증 증거 없음)")
    return (
        '<section id="geofield-a08-evidence" style="max-width:900px;margin:2em auto">'
        '<h2>실제 CAD·FEA 검증 수치 및 설명 출처</h2>'
        '<h3>핵심 결과 · 검증된 동일 실행</h3>'
        '<p><strong>전체 절점 최대 von Mises 응력:</strong> '+stress+
        ' · <strong>전체 절점 최대 변위:</strong> '+disp+'</p>'
        '<p><strong>계산 조건:</strong> '+_text(material.get('name'))+
        ' · 합력 '+(_number(force,"하중","N") if force is not None else '확인 불가')+
        ' · CAD 하중 방향 '+direction_text+'</p>'
        '<p><strong>검증:</strong> CalculiX INP/STA/FRD 동일 실행의 수치와 요소 수 교차 검증.'
        ' <strong>미검증:</strong> 메시 수렴, 경계조건 적절성, 구조 안전성, 전체 최대 위치.'
        ' 이 보고서를 여는 행위는 새 FEA 계산이 아닙니다.</p>'
        '<details><summary>원본 추적 근거 · 재료·면 조건·실행 ID 펼치기</summary>'
        '<table><tbody>'+''.join(rows)+'</tbody></table></details>'
        '<p>'+ml_note+'</p><p>로컬 AI: '+local_note+'</p><p>'+ext+'</p>'
        '<p>3D 화면 이미지: 표시 불가 (별도로 검증된 캡처 파일이 없습니다). '
        '실제 FRD 수치와 이미지 표시 여부를 혼동하지 마세요.</p>'
        '</section>'
    )


def append_verified_evidence(html, summary, provenance, case, *,
                             local_agent=None, external_agent=None):
    if (not isinstance(html,str) or len(html.encode("utf-8"))>MAX_HTML or
            html.count("</body>")!=1):
        raise ValueError("검증된 HTML 보고서의 형식 또는 크기가 잘못됐습니다.")
    extra=compose_evidence_html(summary,provenance,case,
                                local_agent=local_agent,external_agent=external_agent)
    if 'id="geofield-a08-evidence"' in html:
        raise ValueError("A08 검증 섹션이 이미 삽입된 보고서입니다.")
    # Put the already verified key numbers and explicit limits BEFORE the
    # long legacy report. Preserve every pre-existing section and its content.
    body_open=re.search(r"<body(?:\\s[^>]*)?>",html,re.IGNORECASE)
    if body_open:
        out=html[:body_open.end()]+extra+html[body_open.end():]
    else:
        out=html.replace("</body>",extra+"</body>",1)
    if len(out.encode("utf-8"))>MAX_HTML:
        raise ValueError("검증된 보고서 용량 제한을 초과했습니다.")
    return out


def save_immutable_html(root, html, run_id, cad_sha, case_sha):
    """Atomic no-overwrite HTML export. Same bytes may be reopened unchanged.

    Temporary sibling is fsynced first; os.link atomically creates the final
    name only if absent. No os.replace or overwrite of an older report. On
    Windows this depends on NTFS hard-link support and must be tested there.
    """
    if (not isinstance(run_id,str) or not RUN.fullmatch(run_id) or
            not isinstance(cad_sha,str) or not SHA.fullmatch(cad_sha) or
            not isinstance(case_sha,str) or not SHA.fullmatch(case_sha)):
        raise ValueError("보고서 파일 식별값 형식 오류")
    if not isinstance(html,str):
        raise ValueError("보고서 HTML 형식 오류")
    wire=html.encode("utf-8")
    if not wire or len(wire)>MAX_HTML or 'id="geofield-a08-evidence"' not in html:
        raise ValueError("검증된 근거 섹션 또는 HTML 저장 범위 오류")
    root=Path(root)
    if root.is_symlink():
        raise ValueError("심볼릭 링크 보고서 폴더에는 저장하지 않습니다.")
    root.mkdir(parents=True,exist_ok=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("안전한 보고서 폴더가 없습니다.")
    filename="geofield-fea-"+run_id+"-"+cad_sha[:12]+"-"+case_sha[:12]+".html"
    final=root/filename
    def identical():
        if final.is_symlink() or not final.is_file():
            raise ValueError("기존 파일이 없거나 보호된 심볼릭 링크입니다.")
        if final.stat().st_size!=len(wire):
            return False
        return hashlib.sha256(final.read_bytes()).digest()==hashlib.sha256(wire).digest()
    if final.exists() or final.is_symlink():
        if identical():
            return {"saved":True,"reused":True,"path":str(final),"sha256":hashlib.sha256(wire).hexdigest()}
        raise FileExistsError("이 실행의 기존 보고서를 덮어쓸 수 없습니다.")
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode="wb",prefix=".geofield-a08-",suffix=".tmp",
                                         dir=root,delete=False) as stream:
            temporary=Path(stream.name)
            stream.write(wire)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link creation is exclusive on both POSIX and NTFS, unlike
        # os.rename which may replace an existing file on some systems.
        try:
            os.link(temporary,final)
        except FileExistsError:
            if identical():
                return {"saved":True,"reused":True,"path":str(final),"sha256":hashlib.sha256(wire).hexdigest()}
            raise
        return {"saved":True,"reused":False,"path":str(final),"sha256":hashlib.sha256(wire).hexdigest()}
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
