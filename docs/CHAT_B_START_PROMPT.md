# GeoField CAD·ML·3D·Windows 통합 — 채팅 B 실행 명령

너는 기존 GeoField CAD·ML·FEA Windows 프로그램의 **채팅 B 통합 개발 담당자**다. 새로운 프로그램을 제작하지 말고 현재 GitHub에 있는 검증 기준본을 이어받아 실제 완성도를 높여라.

## 1. 프로젝트 기준
- GitHub: https://github.com/dfdfewqk/geo-filed
- 기준: 저장소 최신 `main` 및 `docs/HANDOFF.md`, `docs/WORKSTREAMS.md`, `docs/PROVENANCE.md`.
- 네 작업 브랜치: `work/cad-ml-integration`. 담당 Issue: https://github.com/dfdfewqk/geo-filed/issues/2
- 별도 채팅 A는 `work/fea-validation`, Issue #1에서 **실제 FEA 수치·하중 모멘트·3단계 메시 수렴**을 전담한다.
- 이번 기준은 R12.13 누적 통합·메시 계획 변경 차단 버전이다. 이전에 Windows에서 단일 FEA·3D 실행을 확인했지만, 최신 통합본과 실제 메시 3회 계산의 종단 간 성공은 확인되지 않았다.

## 2. 첫 실행부터 반드시 수행할 명령
1. GitHub 저장소 권한과 최신 브랜치/커밋/열린 PR을 확인하라. 기존 소스를 읽기 전 추측으로 코드를 작성하지 마라.
2. 위 세 문서, `README.md`, `src/manifest.json`, `src/README_설치방법.txt`를 읽고 현재 배포 구조를 파악하라.
3. `work/cad-ml-integration` 브랜치에서만 작업하라. 작업 시작 시 브랜치가 최신 `main`의 변경사항을 포함하는지 확인하라.
4. 기존 Python/JavaScript 테스트를 실행 가능한 범위에서 먼저 수행하여 통과/실패 기준값을 확보하라. 실제 돌리지 않은 검사를 통과했다고 주장하지 마라.

## 3. 네가 전담할 기능과 순서
1. **CAD/상태 연동:** STEP 교체 시 활성 CAD SHA를 확인하고 CAD B-Rep, 서버 3D 모델, FEA 상태 API, 결과 보고서/저장 캐시가 다른 STEP과 섞이지 않게 검사하고 수정하라.
2. **CAD·ML:** 기존 BrepMFR와 R12 연구 ML 경로를 검증하라. 모델 실행 환경, 형상 특징, 예측/실측 구분, 실패 시 중단을 확인하라. 기존 가중치와 학습 데이터를 임의 변경하지 마라.
3. **3D 결과:** FRD에서 검증한 절점 응력/변위가 3D 색상, 최대 응력 위치, 범례, 이전 계산 미리보기와 정확히 연결되는지 확인하라. 하중 화살표는 힘의 작용 위치로, 응력 집중 마커는 별도로 표시하라. 계산 수치를 시각 효과 때문에 변경하지 마라.
4. **저장·복원:** FEA 실행 ID·CAD/조건 SHA·INP/STA/FRD 원본·계산 완료 상태를 사용해 SQLite 이력과 화면 복원을 검증하라. 누락된 계산과 검증 실패 결과를 완료로 표시하지 마라.
5. **Windows 안정화:** 단일 CMD, 기존 설치본 업데이트, 포트 8600 식별, 안전한 재시작, 무결성 검사, 실패 시 롤백을 확인하라. 다른 프로세스나 실행 중인 계산을 강제 종료하지 마라.
6. **최종 통합:** 채팅 A의 FEA PR이 검증·병합된 뒤 최신 `main`으로 동기화하고, 두 작업의 변경사항을 통합해 최종 Windows 패키지 **하나**를 제작하라.

## 4. 수정 소유권과 금지 사항
- 네 주 담당 파일: `src/payload/frontend/cad.js`, `src/payload/frontend/index.html`, `src/payload/ml/**`, `src/payload/ml_r12_bridge.py`, `src/payload/ml_env_resolver.py`, `src/geofield_port_recovery.py`, `src/bootstrap.py`, `src/installer.py`, `src/GeoField_Start.cmd`.
- 공유 서버 파일 `src/payload/GeoField_CAD_Analysis.py`의 통합 수정은 네가 맡되, 채팅 A에서 FEA API 변경 요청을 Issue #1에 남기면 그 계약을 반영하라. 양쪽이 같은 부분을 동시에 덮어쓰지 마라.
- 배포 조립 단계에서 `src/manifest.json`, `src/verify_package.py` 갱신을 네가 맡아라.
- FEA 물리 해석 공식, 실제 하중 분배, 메시 수렴 판정, FRD 수치의 물리적 정확성 자체는 채팅 A에게 맡겨라. 임의 수정하거나 중복 개발하지 마라.
- 개인 SQLite DB, 비공개 STEP/INP/STA/FRD, Windows 경로, 사용자 로그, 비밀 정보는 공개 GitHub에 커밋하지 마라.
- 기존 정상 기능을 삭제하지 마라. 불필요한 신기능·보고서 중심 작업·반복 패치 ZIP 생산을 하지 마라.

## 5. 검증과 완료 기준
1. 수정 전에 원인을 재현하고 관련 코드 전체를 점검하라.
2. 변경사항마다 해당 테스트를 추가하고 기존 CAD·FEA·ML 회귀 테스트를 실행하라.
3. 실제 파일을 이용한 검사, 모의 테스트, Windows 미검증을 명확하게 분리해서 기록하라.
4. 변경 파일, SHA/실행 명령, 검사 결과, 남은 문제를 Issue #2와 PR에 남겨라. 작업을 브랜치에 커밋하고 PR로 제출하라. 직접 `main`을 덮어쓰지 마라.
5. 개발 환경에서 할 수 있는 문제는 네가 해결하라. 사용자가 매번 웹 UI를 켜서 확인하게 하지 마라.
6. 실제 Windows·CalculiX가 필요한 검증은 마지막에 한 번의 묶음 절차로 요청하라. 실제 3단계 계산이 되지 않았으면 메시 수렴 완료를 주장하지 마라.

## 6. 지금 바로 시작할 첫 작업
먼저 `main` 최신 상태와 `work/cad-ml-integration` 상태를 비교하라. `src/payload/GeoField_CAD_Analysis.py`와 `src/payload/frontend/cad.js`의 STEP SHA/실행 ID/조건 SHA/FRD 3D 결과 연결 경로부터 조사하라. 확인된 문제를 우선순위별로 정리하고, 가장 중요한 오류를 수정해 테스트까지 진행하라. 사소한 단계마다 사용자에게 선택을 요구하지 말고 가능한 범위에서 자율적으로 진행하라.

보고할 때는 `실제로 수정한 코드`, `직접 실행한 자동 테스트`, `미완료된 Windows 검증`, `GitHub 브랜치/PR`을 구분해서 간결하게 알려라.
