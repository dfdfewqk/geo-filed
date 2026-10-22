# GeoField AI 에이전트 7단계 — 과거 CAD·FEA 복원 근거 연결

대상: `work/ai-agent-evidence` (PR #5, Draft). 다른 담당자의 CAD/FEA/ML 계산기 및 사용자의 SQLite·STEP·INP·STA·FRD 원본에는 기록·변경을 가하지 않습니다.

## 실제 연동

1. 기존 `restoreArchivedFea`는 저장된 FEA 기록의 원본 CAD SHA, 실행 ID, 조건 SHA를 사전 확인하고, 검증된 복원 번들을 받은 후에만 현재 화면을 변경합니다. 이 복원 과정을 중복 구현하지 않습니다.
2. `GET /api/agent/evidence/{CAD job id}`는 기존 `reverify_task_for_display`, `r125_reconcile_current_fea_summary`, `gf_agent_evaluate`를 유지합니다. 추가된 `gf_agent_restored_context`는 과거 복원 중일 때 CAD 작업 ID·SHA, 계산 실행 ID, 해석 조건 SHA, 복원 상태, 원본 재검증 및 메시/수치 교차검증 출처를 다시 맞춥니다.
3. 복원이 실제 확인된 경우에만 `restore_evidence.status=verified_restored_read_only`을 반환하고 **새로운 계산이 아니라 과거 검증된 CalculiX 실행**이라고 표시합니다. 불일치하거나 복원 선택 실행이 소실됐으면 에이전트 응답을 차단합니다.
4. 같은 CAD SHA와 같은 CAD 작업 ID라도 **복원된 FEA 실행 A/B가 다를 수 있으므로**, 지연된 디스크 조회 및 외부 LLM 응답 뒤 `gf_agent_assert_restore_session`에서 복원된 실행 ID와 복원 조건 SHA를 확인합니다.
5. 기존 화면의 복원 성공 후 규칙 기반 에이전트 분석을 **자동 갱신**합니다. 새 클릭 버튼을 추가하거나 LLM 호출 동의를 자동으로 하지 않습니다. 체크박스는 새 모델/복원 과정에서 초기화됩니다.
6. 브라우저는 요청 당시의 `gfRestoredRunId`와 실제 받은 `restore_evidence.run_id/case_sha256/cad_sha256`이 일치하고, `fea.status`가 실제 INP/STA/FRD 재검증됐을 때만 수치와 '과거 복원' 설명을 보여줍니다.
7. 사용자가 복원 뒤 다른 STEP을 고르거나 다른 FEA 기록을 복원하면 이전 에이전트 UI 응답을 폐기합니다. 이전 연구 ML 기록을 자동으로 복원했다고 주장하지 않습니다.

## 검증 범위

- `test_agent_restore_binding.py`: 복원 경로의 실제 프로덕션 Python 검증 함수로 실행 ID·조건·메시 출처 불일치, 복원 선택 소실, 같은 CAD에서 실행 교체 시 오래된 응답 차단
- `test_agent_ui.js`: 복원된 과거 FEA임을 표시, 응답 누락/불일치 차단, 같은 CAD에서 다른 실행으로 변경 시 지연 응답 무효화
- `test_agent_restore_ui.js`: 실제 UI 복원 완료 부분을 실행하여 자동 규칙 분석, 실행 ID 불일치나 새 선택 시 실행 차단 검증
- CI: Ubuntu / Windows / 임시 A+B+AI 통합 후보에서 계약 자동 검사

모든 위 테스트는 모의/합성 근거를 사용하며 **실제 사용자의 Windows 환경, 실제 STEP 복원 및 원본 CalculiX 재실행을 완료한 것으로 주장하지 않습니다.** 실제 사용자 FEA 원본과 재시작 검증은 마지막 9단계에서 다른 담당 개발 결과와 함께 진행합니다.
