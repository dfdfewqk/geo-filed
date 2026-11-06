# GeoField 기존 ML→AI→FEA→결과보고서 연결 실사 (2026-11-06)

**기준**: `dfdfewqk/geo-filed`, 작업 브랜치 `work/geofield-verified-evidence-completion-20261106`, 조사 시작 HEAD `5238de6244ec444c5715f3361125cc912eab7676`. 이 문서는 현재 **소스 상의 실행 경로** 감사다. 사용자의 Windows GUI·실제 유료 API 연결 성공을 증명하지 않는다.

## 개발 목표 재고정
- 기존 L_bracket.step 한 형상. STEP 입력 → CAD 직접 측정 → 기존 BrepMFR/R12 연구 ML → **ML 결과/실패·불확실성 분류 → 로컬 AI로 자동 인계** → 실제 Gmsh/CalculiX FEA·3D·3메시 결과와 결합 → **검증된 최종 통합 보고서**.
- **AI는 기존 측정·해석 원본을 조작하지 않는다.** ML이 분류하지 못한 형상을 AI가 임의의 정답으로 만들어내지 않는다. 재검증 가능한 것만 검증, 불확실한 사실은 구체적인 사유·다음 행동과 함께 남긴다.
- 외부 유료 AI는 명시적 사용자 동의와 검증된 제한 입력이 있어야 한 번 호출한다. 자동 로컬 처리와 자동 유료 API 과금은 별개다.
- 기존 STEP·BrepMFR 가중치·R12 모델·FEA INP/STA/FRD·SQLite·기존 보고서·main은 수정/삭제하지 않는다. 부가적 신규 CAD/FEA 설계 기능 개발하지 않는다.

## 현재 실제 연결 (소스 검토)

| 순서 | 코드 진입점·원본 | 현황 | 핵심 관찰 |
| --- | --- | --- | --- |
| 1. CAD 입력 | `src/payload/frontend/cad.js` `importBtn.onclick` → `POST /api/cad/import?auto_ml=...`; 서버 `GeoField_CAD_Analysis.py` | **연결됨** | 등록된 STEP의 SHA와 현재 CAD 작업 ID를 대조하고 CAD 삼각형 표시. |
| 2. 로컬 자동 ML | 서버 `launch_automatic_ml`/`launch_automatic_r12`, 클라이언트 `watchAutoMl`/`watchAutoR12` | **연결됨 (실행 환경 의존)** | BrepMFR 실패 시 R12 대체 경로 있음. 모델 결과는 `blocked_diagnostic_only` 등 연구용 제한. 단순 fallback을 AI 호출로 착각하면 안 됨. |
| 3. ML 결과 확정/실패 | `GET /api/ml/latest/<cad>`, `/api/ml/r12/latest/<cad>`, `gfResearchEvidenceUpdated` | **읽기·표시 연동됨** | ML 완료/실패 후 현재 결과표 새로고침·연구 근거 리비전 증가. **분류 실패/불확실 항목별 AI 인계 자료 생성은 없음.** |
| 4. 로컬 AI | `gfMaybeAutoAnalyze` → `agentRunBtn.onclick` → `GET /api/agent/evidence/<cad>`, 서버 `gf_agent_evaluate` | **조건부 자동 동작** | `active==='integration'` 등 조건이 있어 단일 분석 보고서 전체 과정의 독립 후속 단계로 보장되지 않음. 기본 로컬 AI는 소스 근거를 설명하는 규칙 엔진이다. |
| 5. 실제 FEA | `feaRunBtn.onclick` → 기존 솔버 상태/원본 INP·STA·FRD 검증 | **연결됨** | CAD·재료·고정·하중 조건이 필요. ‘STEP을 불러오기만 하면 무조건 해석’은 현재 흐름 아님. |
| 6. 3회 메시 민감도 | `gfAutoStage2Verification` → 기존 3회 솔버 검증 | **연결됨 (실제 3개 완결 원본 필요)** | 같은 조건/형상의 굵음·기준·미세 결과, 실제 숫자·변화율. 수렴/안전 인증을 생성하는 단계가 아님. |
| 7. 자동 최종 HTML | `gfStage3CompleteReport` → `gfBuildVisibleReport(...,false,requireMesh)`; 서버 `gf_current_verified_report` | **FEA 근거 중심 보고서만 자동** | 기본 자동 HTML이 **AI OFF로 강제 호출**됨. `gfBuildVisibleReport`의 `!includeExternal` 분기는 로컬 규칙 AI 설명도 보고서에서 제외. **ML→AI→보고서 자동 해석 결합이 끊긴 핵심 지점.** |
| 8. 명시적 유료 AI | `gfBuildVisibleReport(...,true)` / `agentRunBtn.onclick` → `?llm=1` + `X-GeoField-LLM-Opt-In: 1` → `gf_paid_ai_preflight` → `gf_agent_llm_optional` | **수동 동의 전제** | 기존 브라우저·서버 양쪽 엄격한 사전 근거 검사. AI 부족분을 자동 결제·자동 호출하지 않도록 유지해야 함. |

## 확인된 구조적 갭 (다음 단계 수정 범위)

**G1 — 분류/인계 자료 모델 없음 (우선 2~3단계):** `BrepMFR`과 `R12` 개별 결과를 단순 나열하거나 상태 갱신할 뿐, 동일 CAD SHA의 `resolved / uncertain / failed / unavailable`로 묶어 *이유·원본 근거·다음 조치*를 AI에 자동 전달하는 단일 결과 계약이 없다. ML 내부 face_ordinal과 CAD face_id를 1:1로 이어붙이지 않는다.

**G2 — 로컬 AI 자동 실행이 별도 화면 중심 (3단계):** `gfMaybeAutoAnalyze`는 `active==='integration'`을 요구하고 `gfResearchEvidenceUpdated`도 분석 중에는 대기한다. 연구 결과가 늦게 도착하면 최종 보고서에 AI 설명 갱신이 자동으로 보장되지 않는다.

**G3 — 자동 보고서의 AI OFF 하드코딩 (5~6단계):** `gfStage3CompleteReport`의 `gfBuildVisibleReport(..., false,...)`는 보고서 원본·추가 근거를 안전하게 생성하지만 로컬 규칙 기반 분석도 생략한다. 현 단계에서 인위적으로 `true`로 바꾸면 **유료 호출**로 연결되므로 금지. **로컬 규칙 설명 포함 여부와 외부 유료 요청 여부를 별도 설정/계약으로 분리**할 것.

**G4 — 유료 모델 입력이 성공 자료 전부에 종속 (5단계):** `gfRequireCompletePaidReportEvidence`/`gf_paid_ai_preflight`는 BrepMFR+R12+3메시+3D 등 다중 원본을 기대한다. 일부 연구 ML 결과가 없을 때, 부족한 부분만 보완하는 AI 인계가 아니라 유료 요청 전체 차단으로 끝날 수 있다. 보안·요금/원본 검증 게이트는 보존하되, **실제 있는 자료만 전달하는 범위 제한된 참고 해석**과 **필수 물리 근거가 결여돼 어떤 계산도 할 수 없는 경우**를 구분할 것. 기준이 없으면 허위 수치 생성 금지.

**G5 — 자동 보고서 완료조건이 실제 3회 메시 원본에 종속 (6단계):** `verifiedMeshReady`가 거짓이면 기본 FEA 자체가 정상이어도 `gfStage3CompleteReport`를 자동 호출하지 않는다. 3회 실패/종료 미확인 시 원본을 보존해야 하지만 **기본 FEA 확정치 보고서와 추가 연구 부록의 미완성 상태**를 혼동하면 안 된다. 단, 완료하지 않은 3회 메시를 검증 완료로 표기해서는 안 됨.

**G6 — 한 번의 실행 전 준비 조건 (4단계):** 재료·고정면·하중면·실제 해석 조건의 사용자 선택이 현재 요구됨. 원클릭은 '입력 조건이 준비된 뒤 결과 분석 버튼 한 번'이지 'STEP 업로드만으로 물리 조건까지 정답 자동 추정'이 아님.

## 다음 수정에서 지킬 최소 계약

1. 모든 결과/인계는 **현재 CAD 작업 ID/SHA 및 ML·FEA 각 독립 실행/해석 조건 ID**에 묶는다.
2. 입력 정보의 출처 유형을 분리: 직접 CAD 측정, 연구용 ML 추론, 실제 솔버, 로컬 규칙 설명, 유료 외부 의견. **설명은 수치를 덮어쓰지 않는다.**
3. ML 실패·미실행을 FEA 실패로 전파하지 않되, AI에는 누락 항목과 실패 사유를 전달한다. AI가 **진행할 수 없는 계산이나 학습을 완료했다고 표시하지 않는다**.
4. AI 모드 3종을 분리: **OFF** (AI 설명 없음), **LOCAL** (오프라인 근거 해석 자동 포함), **EXTERNAL** (명시적으로 승인한 1회 요금 요청, 실패해도 LOCAL/FEA 보존). 기존 사용자 AI-OFF 의사 존중.
5. 3회 메시 실패 시 실제 기본 FEA만 포함한 보고서로 축소할 수 있지만, '완전 검증 3회 보고서'와는 명칭/검증 기준을 명확히 분리.
6. 실제 Windows 통합 GUI, 모델/솔버 환경, 선택적 유료 API 실응답은 별도 최종 검증. 테스트의 모의 응답을 실연동으로 보고하지 않는다.

## 1단계 결과
- 기존 구현과 끊긴 구간 식별: **완료 (정적 코드 조사)**.
- 해당 감사의 회귀 경계조건 `src/tests/test_pipeline_handoff_contract.py` 신규 추가.
- 기능 재연결 자체는 **2~6단계 작업으로 미완료**. 설계 확장/새로운 대응면 기능 개발 없이 이 경로부터 수정한다.
