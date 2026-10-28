# GeoField B02 — 실제 FEA 실행 흐름·파일 보호 작업 (2026-10-28)

## 담당 범위 및 상태

**GitHub 백엔드의 계산 시작/실패 방지 로직**까지 검증한다. 실제 사용자의 Windows 설치본, Gmsh/CalculiX 바이너리, 원본 STEP 파일과 실제 엔진 Python 모듈은 ChatGPT에서 접근하지 않는다. 최종 실제 실행 검증은 **B07 한 번**에 모은다.

A05에서 이미 적용된 계약은 보존한다.

- 실제 메시 도달 시 `mesh`, CCX 프로세스 실행 시 `solver`, 계산 후 실제 원본 검사 시 `verification`; 서로 다른 Python 작업자는 `external_worker`로만 표시한다. 내부 작업 단계는 추정하지 않는다.
- `complete` 상태는 동일 실행/조건의 INP·STA·FRD를 독립 재검증한 경우만 반환한다. `result.json`에 성공이라고 적힌 것만으로 성공으로 취급하지 않는다.
- 이력 자동 저장이 실패해도 실제 검증 완료된 계산 자체를 실패 상태로 바꾸지 않으며 `history_archive_status='failed'`로 따로 표시한다.

## 이번 B02에서 적용한 안전 장치

1. `src/payload/fea_b02_workspace.py`: 32자리 영문 소문자 hex run ID를 확인하고 **이미 내용이 있는 실행 폴더를 재사용하지 않는다**. 기존 INP/STA/FRD·결과 JSON·CCX 로그가 발견되면 파일을 지우지 않고 계산 시작을 거부한다. 빈 작업 디렉터리만 허용한다.
2. `src/payload/fea_solver.py`: Gmsh가 호출되기 전에 기존 CCX 출력이 남아 있는지 재검사한다. 별도 worker가 자신의 `worker_case.json`과 `worker_model.json`을 미리 작성한 것은 허용하되, 예전 계산의 FRD·STA·INP·result.json을 그대로 이용하지 않는다.
3. `src/payload/GeoField_CAD_Analysis.py`: HTTP 업로드 시 `JOBS_DIR/<run_id>.fea_input.step` 파일을 **`xb` 배타적 생성**으로 열어 기존 파일 덮어쓰기를 방지한다. 업로드 생성 성공 여부를 기록해 실제 요청이 생성한 파일만 오류 시 삭제한다. 실행 콜백도 해당 run ID로 등록된 임시 STEP 복사본이 아니면 계산을 거부한다. `finally`에서는 **자기 소유 임시 STEP**만 삭제하고 다른 경로/원본 STEP/심볼릭 링크 대상은 삭제하지 않는다.
4. 외부 `GEOFIELD_GMSH_PYTHON` 환경에서는 기존 설치본의 `fea_engine_worker.py`가 실제 안전한 정규 Python 파일인지 AST로 **읽기 전용** 확인하고 없거나 손상됐으면 실행을 거부한다. 모듈을 임의 생성하거나 다른 엔진을 자동 설치하지 않는다.
5. 기존 A05 해석 결과 재검증, A03 기록 저장, A06 3D 필드 검사, 보고서 조건, CAD·메시·ML 데이터는 변경하지 않는다.

## Antigravity B01 → B02 → B06 → B07

- **B01 실제 설치본 JSON 점검 먼저:** `docs/B01_WINDOWS_RUNTIME_INVENTORY.md`. GitHub에 `fea_engine_worker.py` 원본과 `fea_previous_import.py` 소스가 없으므로 실제 Windows 설치본을 확인해 경로·버전·필수 함수 인터페이스를 결정해야 한다.
- **B02 실제 계산 연동:** 확인된 기존 Windows `fea_engine_worker.py`와 독립 `fea_previous_import.verify_directory`가 새 작업 폴더에 정확히 파일을 생성·재검증하는지 B07에서 최종 실행 증거 확인. 실행 도중 CAD/조건 변경 시 결과 활성화 금지. GUI 단계·상태 표시는 실제 도달 시점만 표현.
- **B06 패키징:** `src/payload/fea_b02_workspace.py`는 B02에서 새로 작성한 모듈이므로 기존 설치본에 있다고 가정하지 말고 패키지/런처의 Python import 경로에 반영해야 한다. 기존 사용자 모듈·STEP·SQLite·FRD·ML 가중치 덮어쓰기 금지.
- **B07 실제 Windows 한 번의 통합 테스트:** STEP → 실제 Gmsh → 실제 CCX → INP/STA/FRD 독립 검증 → 3D·이력·보고서·재실행/실패 검증. 실제 CCX 계산에 성공했다는 주장은 이 단계의 로그·영상이 있어야 한다.

## 자동 테스트 범위

`src/tests/test_fea_workspace_b02.py` 및 기존 `test_fea_execution_a05.py`, `test_fea_progress_stages.py`는 임시 폴더와 가짜 solver 반환값으로 **파일 보존·실행 상태·실패 격리만 테스트**한다. GitHub Linux/Windows 회귀 통과는 실제 Gmsh/CCX 계산 성공을 뜻하지 않는다.
