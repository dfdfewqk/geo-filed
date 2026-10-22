# GeoField AI 에이전트 입력 계약 v1

적용 브랜치: `work/ai-agent-evidence` (AI 에이전트 전담). 이 문서는 계산법이나 ML 학습기를 변경하지 않습니다.

## 사용 중인 실제 데이터 경로

| 입력 | 소스 및 호출 | 필요한 일치 조건 | 불일치 시 동작 |
|---|---|---|---|
| CAD | 현재 활성 `JOBS[job_id]`, `qa_current_cad_evidence`, `build_summary(...).cad` | 32자리 CAD 작업 ID, 64자리 STEP SHA, `review_decision`과 CAD 요약 동일 SHA 및 작업 ID | 전체 에이전트 요청 거부(HTTP 409) |
| BrepMFR ML | `ML_JOBS` 최신 해당 CAD 작업 기록. 실행 시 `qa_validate_brepmfr_diagnostic` | 작업 ID·STEP SHA·실행 ID 및 `blocked_diagnostic_only`. 면 목록 형식이 유효할 것 | ML만 `identity_rejected` 또는 `evidence_rejected`; CAD·FEA 보존 |
| R12 ML | `r128_r12_status(job_id, SHA)` (내부적으로 원본 검증) | 동일 CAD SHA, `research_only`, `fea_calculated=false`, 32자리 실행 ID, 정수 후보 수 | R12만 거절. CAD·FEA에 영향 없음 |
| FEA | `reverify_task_for_display` → `build_summary` → `r124_case_provenance` → `r125_reconcile_current_fea_summary` | 동일 CAD 작업 ID 및 SHA, 32자리 CalculiX 실행 ID, 64자리 해석 조건 SHA, 원본 `INP_STA_FRD_reverified`, 응력·변위·노드·사면체 수 및 검증 근거 일치 | 실제 응력·변위·실행 ID 전부 숨김, `not_verified` |
| LLM | 현재 설정 없음 | 호출이나 응답이 실제 확인되지 않음 | 언제나 `rules_only`, `llm.connected=false` |

## 읽기 전용 결과 계약

`GET /api/agent/evidence/{현재 CAD 작업 ID}`의 `schema`는 `geofield-evidence-agent-v1`입니다. `input_contract.schema`는 `geofield-agent-input-contract-v1`입니다.

- `input_contract.cad`: `identity_verified` + 원본 SHA/작업 ID.
- `input_contract.ml`: `not_run | queued | running | failed | research_unverified | identity_rejected | evidence_rejected`. `structural_authority=false`.
- `input_contract.r12`: `not_run | queued | running | failed | research_complete | identity_rejected | evidence_rejected`. `structural_authority=false`.
- `input_contract.fea`: `not_run | queued | running | failed | identity_rejected | candidate_needs_frd_verification | INP_STA_FRD_reverified`. 이 표시 자체는 파일을 새로 계산하거나 원본 검증을 우회할 권한을 주지 않습니다.
- 최종 `fea.status`는 확인된 원본과 일치할 때만 `INP_STA_FRD_reverified`; 그 외 `not_verified`, 수치는 `null`. 물리적 수렴은 항상 별도 미검증입니다.
- `findings[]`: `kind`, `title`, `evidence`, `next_check`, `level`로 구성된 **설명 전용** 자료. 원본 해석 수치나 CAD 파일을 변경하지 않습니다.
- `llm`: `connected=false`, `executed=false`, `provider=null`. 외부 모델 연결 없이 생성 설명 실행을 주장하지 않습니다.

**C3D4/C3D10 구분:** 실제 재검증된 FEA 메시의 `element_type`이 명시된 경우에만 그대로 표시합니다. 추정해 채우거나 서로 다른 요소 형식의 데이터를 비교하지 않습니다.

**원본 기록:** 에이전트 결과는 생성 후 SQLite에 자동 보관되는 독립 결과가 아닙니다. CAD·ML·FEA 기존 기록을 검증한 뒤 현재 판단을 다시 만들어 보여줍니다.

## 회귀 검증

`python -m unittest test_agent_input_contract test_agent_evidence -v` (작업 디렉터리 `src/tests`), `node src/tests/test_agent_ui.js` (저장소 루트).

모두 기존 실제 함수를 호출하지만 **합성 근거 입력**을 사용합니다. 해당 검증이 통과하더라도 실제 Windows의 STEP → CalculiX → 3D → SQLite 재시작 또는 안전성을 인증한 것으로 해석하지 않습니다.
