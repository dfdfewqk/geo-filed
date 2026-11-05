# GeoField — 전체 회귀검사 장애 정리 및 보고서 AI OFF 수정 (2026-11-05)

## 범위·보존 조건

기준은 기존 Draft PR #112 이후의 작업 브랜치다. 본 변경은 **기존 기능 오작동·구형 검사 코드의 오탐만 수정**했다. 새 형상 지원, UI 기능, AI 제공업체, 로컬 모델, 자동 설치 기능은 추가하지 않는다.

- `main`, 원본 `L_bracket.step`, 사용자 SQLite·ML 가중치·INP·STA·FRD, 실제 Windows 설치본은 건드리지 않았다.
- 외부 AI 자동 호출이나 무단 API 비용 없음.
- 검증 불가능한 2026-10 QA5~QA11 역사적 ZIP·독립 FRD 자료는 재구성/위조하지 않고 **명시적 skip**; 현재 26파일 후보 및 실솔버 검증은 계속 실행한다.

## 수정한 테스트·코드

### 오래된 Python 테스트와 25 ERROR + 1 FAIL

1. `test_lbracket_p5_read_only_compat_audit.py`, `test_runtime_source_api_contract.py`: 현재 26파일 manifest를 실제 런처에 공급하도록 모의 입력 갱신. 과거 누락된 API `restore_payload` 검증은 진단 구조체에서 검사하고, 차단 상태/사용자 자료 불변을 확인한다.
2. `test_brepmfr_v2_research_pipeline.py`: 모든 샘플에 똑같은 그래프 바이트를 만드는 잘못된 fixture 수정. 원본의 중복 그래프 차단 보호 기능은 유지한다.
3. `test_qa5.py`, `test_qa7.py`, `test_qa8.py`, `test_qa10.py`, `test_qa11.py`, `test_final_validation.py`: 과거 ZIP/실제 FEA 독립 아카이브가 없는 CI에서 파일 없음이 모든 최신 검사를 방해하지 않도록 정확한 사유로 skip. 사용 가능한 경우 원래 QA 유산 검증을 수행한다. 옛 `onclick=async()=>` 소스 문자열을 요구하는 두 테스트는 현재 실행기 경로에서의 브라우저/one-click 계약 검사로 대체되었음을 표시한다. 단, 원본 자료가 없는 채널에선 과거 버전 byte-for-byte 호환성을 확인했다고 주장할 수 없다.
4. `test_qa7.py`: 현행 26파일 manifest를 거절해도, 미확인 소스 덮어쓰기를 차단했다는 사실에 맞춰 오류 메시지 기대를 조정한다.
5. `test_b05_fea_delete_ui.js`, `test_fea_stage3_auto_unified_report_ui.js`, `test_fea_stage6_evidence_display_ui.js`: LF/CRLF를 모두 허용한다. 프로그램 계산 로직을 바꾸지 않는다.

### 기존 보고서 AI OFF 기능 정상화

- 사용자 요구: AI OFF 시 **현재/과거 로컬 AI 분석과 외부 유료 AI 설명을 보고서에서 제외**, 응력·변위·CAD·ML·원본 FEA·3회 메시 공학 수치는 그대로 유지.
- `GeoField_CAD_Analysis.py`: 서버 검증 보고서 생성에 `include_ai=False`가 기본값. ON으로 요청된 경우에만 현재 CAD/FEA 범위의 로컬 규칙 에이전트를 생성·삽입한다. 원래 고정된 'AI Agent: 미연결' 라벨은 OFF에서 제거한다.
- `fea_report_a08.py`: 보고서 AI OFF에서는 A08 근거 섹션에서 로컬 AI/옛 DeepSeek 상태 문구를 제외한다. 핵심 수치, 메쉬 및 보존 규칙은 변경하지 않는다.
- `frontend/cad.js`: ON일 때만 서버 GET `include_ai=1`; OFF에서는 예전 서버의 캐시 로컬/유료 섹션 및 상태 문구도 정리한다. 1회 외부 호출은 기존 `X-GeoField-LLM-Opt-In`을 가진 직접 버튼 조작에만 허용한다.
- 기존 자동 원클릭 보고서(별도 토글 없음)는 AI OFF로 생성하며, 로컬 규칙 분석은 원래 UI의 별도 결과 화면에서 볼 수 있다. 새로운 사용자 조작은 추가하지 않았다.
- `index.html`의 토글 설명도 실제 기능에 맞게 수정.
- 기존 서버 측 비공개 `integrated_results.html_report` 구현은 저장소에 없고 실제 사용자의 설치본에서만 확인 가능하므로, 실제 Windows 최종 보고서 화면/오래된 HTML 혼입 여부는 별도 실사용 검증 필요.

## 실행 근거

- [전체 자동검사 워크플로](https://github.com/dfdfewqk/geo-filed/actions/workflows/geofield-full-system-audit-20261105.yml).
- 최신 재실행: [#41980427613](https://github.com/dfdfewqk/geo-filed/actions/runs/41980427613).
- GitHub CI 검증 대상: Ubuntu Python 3.12 / Windows Python 3.13의 전체 `unittest` 835건, 53개 JS 브라우저 계약 스크립트(두 OS), 실제 1회 기본 + 3회 C3D4 + 3회 C3D10 Gmsh/CalculiX 해석, 실제 CadQuery/OCP·R12 연구 모델 추론, Windows 임시 설치/재설치/실패 롤백, 독립 `pytest` HTML/AI 보고서 테스트.
- **기록 기준**: Ubuntu Python 835건에서 0 실패·0 오류·51 skip (원본 QA ZIP 부재와 기존 환경 의존 포함). Linux/Windows JS 53개 각각 통과. 추가 A08 보고서 29건 및 AI 근거 4건 통과. 실솔버/R12 진단 통과.
- 51 skip은 '검증 완료'가 아님. 과거 QA 원본 파일/소유자 Windows 기록의 실제 복원 보증은 하지 않는다.
- 참고: 실제 3단계 메시의 5% 수치 안정성 선별에서는 과거 측정 조건 중 9.42% 변화 사례가 있어 '수렴 인증'이나 구조 안전성을 주장하지 않는다.

## 아직 미검증 — 이번 작업 범위를 넘어선 Windows 현실 테스트

1. 보고서 버튼 수정 PR #110을 실제 사용자의 기존 설치본에 적용한 후 원클릭→3D→추가 3메시→보고서 열기/저장 성공 여부.
2. 실제 설치본의 비공개 `engine_runtime`, `integrated_results`, 기존 SQLite/ML 자료와의 호환성 및 복원.
3. BrepMFR 기존 epoch43 체크포인트 실제 환경·GPU 상태 및 외부 AI의 실제 통신 결과(사용자 명시적 동의 없이 호출 불가).
4. *본 CI가 실행한 것은 물리 계산 및 UI를 분리 검증한 시험이다.* 실사용 Windows E2E 성공으로 오해하면 안 된다.

**후속 원칙:** 사용자 Windows에서 실제 오류가 재현될 경우 그 문제만 수정하고, 메인 브랜치 변경·완성품 배포는 모든 요구된 최종 검증 이후 별도 승인을 받아 수행한다.
