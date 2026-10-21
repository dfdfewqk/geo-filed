# GeoField — 두 채팅 병렬 개발 담당 범위 (2026-10-21)

## 공통 기준
- 저장소: https://github.com/dfdfewqk/geo-filed
- `main`은 공통 검증 기준. 시작 전에 `docs/HANDOFF.md`, `docs/PROVENANCE.md`, Issue #1/#2, 현재 PR을 읽을 것.
- R12.13 누적 최종 통합·메시 계획 변경 차단이 기준이며, 실제 Windows 최신 빌드 재검증과 3단계 독립 메시 CalculiX 계산은 **미완료**.
- Python 111건 통과는 이전 개발 환경에서 보고된 수치이며 GitHub CI 또는 실제 Windows E2E 성공을 뜻하지 않는다.

## 채팅 A — 현재 채팅 / FEA 수치 검증 (Issue #1)
- 브랜치 `work/fea-validation` (본인 브랜치에만 커밋).
- 전담: INP 실제 하중 합력/작용 중심/모멘트, 고정 노드 제외의 물리적 영향, STA/FRD 파싱과 실제 von Mises/변위 대조, 메시 품질, 3단계 coarse/medium/fine 조건 동등성·수렴 판정·최대 응력 위치 안정성.
- 우선 파일: `src/payload/fea_solver.py`, `src/fea_compare.py`, `src/fea_convergence.py`, `src/fea_mesh_series.py`, `src/fea_result_trust_gate.py`, `src/payload/fea_result_trust_gate.py`, 신규 `src/tests/test_fea_*.py`.
- 변경 범위 제외: WebGL UI, Windows 실행기/포트 복구, ML 가중치/훈련 파이프라인.
- 실제 솔버 실행 환경이 없으면 새로운 3개 메시의 실측 수렴값을 만들거나 통과로 표시하지 말고, 검증 경로를 준비한 뒤 Windows 최종 통합 시험으로 넘길 것.

## 채팅 B — 새 채팅 / CAD·ML·3D·Windows 통합 (Issue #2)
- 브랜치 `work/cad-ml-integration` (본인 브랜치에만 커밋).
- 전담: STEP/CAD B-Rep와 활성 CAD 식별, 독립 연구용 R12 ML, 3D WebGL 응력 색상/절점 최대 위치/하중 화살표, REST 상태 조회와 결과 저장·복원, Windows CMD 설치/업데이트/복구, 포트 8600 식별·안전 종료.
- 우선 파일: `src/payload/frontend/cad.js`, `src/payload/frontend/index.html`, `src/payload/ml/**`, `src/payload/ml_r12_bridge.py`, `src/payload/ml_env_resolver.py`, `src/geofield_port_recovery.py`, `src/bootstrap.py`, `src/installer.py`, `src/GeoField_Start.cmd`, 신규 `src/tests/test_cad_*.py`, `src/tests/test_integration_*.py`.
- 변경 범위 제외: CalculiX 물리 해석 공식, FEA 하중 분배 계산, FRD 기반 수치 자체, ML 학습 가중치 임의 변경.
- 양쪽 코드 PR이 검증·병합된 후 **최종 Windows 단일 패키지 조립 책임은 채팅 B**. 그 이전에는 반복 설치를 요구하지 말 것.

## 공유 파일·충돌 조정
- `src/payload/GeoField_CAD_Analysis.py`는 두 작업이 의존하는 공유 서버 진입점이다. 기본 수정 담당은 **채팅 B**이며, 채팅 A는 필요한 FEA API 변경 계약을 Issue #1에 명시하고 별도 모듈에서 구현한다. 불가피한 수정은 채팅 B가 해당 PR에서 연결한다.
- `src/manifest.json`과 `src/verify_package.py`는 **채팅 B**가 최종 조립 시 갱신한다. A는 검증 가능한 SHA 목록·변경 파일 목록만 전달한다.
- 기존 `src/tests/test_qa*.py`, `src/tests/test_final_validation.py`는 공통 회귀 기준. 소유권 충돌 시 기존 코드를 독단적으로 삭제하거나 시험 조건을 완화하지 않는다.
- 공통 데이터 계약: 실제 코드에서 필드명과 구조를 먼저 확인한 뒤 CAD SHA, 재료/하중/경계조건 해시, run_id, INP/STA/FRD 무결성, 메시/응력/변위를 연결한다. 필드를 추측해 만들지 말 것.
- 결과값을 조작하거나 색상만으로 응력값을 변경하지 않는다. ML 결과를 FEA 실측 결과로 섞지 않는다.
- 개인 SQLite, 비공개 STEP, 계산 기록, 사용자 경로, 로그, 토큰, 시험 비공개 자료를 공개 저장소에 올리지 않는다. 원본 STEP/INP/STA/FRD·모델 가중치를 임의 덮어쓰거나 삭제하지 않는다.

## 진행 및 완료 기준
1. `main` 최신과 PR을 확인하고 본인 브랜치를 동기화한다. 다른 브랜치나 main에 바로 개발 코드 푸시 금지.
2. 현상 재현 → 원인 분석 → 필요한 변경 → 자동 테스트 → 회귀 테스트 순으로 진행한다.
3. 변경 파일, 실행된 명령, 통과/실패 건수, 실제/모의/미실시 구분을 PR/Issue에 남긴다.
4. 서로 충돌하는 공유 파일의 수정은 Issue에 작업 계약을 먼저 남기고 상대 작업 결과를 기다린다.
5. A의 수치 검증 PR을 우선 검토·병합하고, B 브랜치를 최신 main으로 갱신해 최종 통합한다.
6. 두 영역 자동 검증을 통과한 후에만 Windows에서 STEP→조건→실제 CalculiX→FRD→3D→이력→3단계 메시의 묶음 최종 시험을 요청한다.
7. 최종 보고서는 `코드 구현`, `자동 시험 통과`, `실제 Windows 확인`, `독립 수렴 확인`을 서로 다른 상태로 기록한다.

## 바로 시작할 위치
- 채팅 A: https://github.com/dfdfewqk/geo-filed/issues/1
- 채팅 B: https://github.com/dfdfewqk/geo-filed/issues/2
