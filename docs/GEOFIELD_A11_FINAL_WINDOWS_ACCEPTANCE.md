# GeoField A11 — Windows 1회 통합 실행 검증 인수인계 (2026-10-28)

## 목적과 현재 승인 범위

- **통합 소스:** `work/geofield-final-integrated-candidate-20261028` (PR #31), A11 ZIP 전달 브랜치: `work/geofield-windows-candidate-a11-20261028`.
- **현재 증거:** Linux/Windows의 임시 환경에서 Python·브라우저·22개 파일 설치 및 롤백 검증. 실사용 Windows Gmsh/CalculiX·3D WebGL 성공은 아직 검증하지 않았다.
- **배포 산출물:** 해당 A11 workflow Actions의 `GeoField-A11-22FILE-WINDOWS-ONE-EXTRACT-NOT-FINAL` **단일 ZIP 아티팩트**. 다운로드 뒤 Windows 파일 탐색기에서 **한 번만 압축 해제**한다.
- **중요:** *기존 설치된 GeoField Windows 런타임을 업데이트하는 후보*. 독립 실행 EXE가 아니며 FreeCAD/OpenCASCADE, Gmsh, CalculiX 등 미설치 의존성을 자동 설치하지 않는다.
- 원본 STEP, 기존 SQLite, INP/STA/FRD, 모델 가중치와 개인 프로젝트 파일 삭제/이동/재작성 금지. 소스 변경 전 해시 대조와 코드 백업/롤백이 필수이다. 로컬에서 승인하지 않은 소스는 덮어쓰지 않는다.

## ChatGPT/GitHub 담당 완료 기준

1. A11 workflow가 **Linux 선행 검증 → Windows 전체 검증 → 과거 GitHub Actions ZIP SHA-256 인증 → 실제 17/20→22 파일 업데이트·롤백 검증 → 새 ZIP 생성 → 압축 해제 후 SHA-256 검증 → 아티팩트 게시 → 재다운로드 검증** 순서를 모두 성공으로 표시해야 한다.
2. `src/manifest.json` 및 사용자의 엔지니어링 원본 파일은 수정하지 않는다. 새 모듈 `fea_field_a06.py`와 `fea_report_a08.py`를 22개 출처 잠금 패키지에 포함한다.
3. 현재 사용자 PC 실행 성공으로 표시하지 않는다. `NOT_FINAL` 표기를 유지한다.
4. A11 CI 실패 시 아티팩트를 완성본으로 소개하지 않고 실패한 검증 로그부터 수정한다.

## Antigravity 담당 — 사용자 실행 전 사전 검토

1. A11 Actions artifact 폴더에 `GeoField_Start.cmd`, `GeoField_Repair.cmd`, `GeoField_Acceptance_Check.cmd`, `START_HERE_ONE_EXTRACT.txt`, `bootstrap.py`, `installer.py`, `verify_package.py`, `manifest.json`, `payload/`가 정확히 한 단계에 존재하는지 확인.
2. 사용자 Windows 런타임의 **읽기 전용** 상태 점검: `python` 경로, FreeCAD/OCP/CadQuery, Gmsh, CalculiX, 엔진 API 호환성, 8600번 포트 소유자, 사용자 데이터 원본과 별도 디렉터리. 설치/실행 전에 코드 자동 수정이나 강제 종료 금지.
3. 키를 저장소/보고서/영상에 넣지 않는다. DeepSeek는 `DEEPSEEK_API_KEY`를 로컬 환경변수로만 주고 실제 API 호출은 사용자 명시적 일회성 동의가 있을 때만 한다.
4. 원본 파일을 변경하지 않는 하나의 실제 사용자 실행 경로를 준비한다. 실패 시 같은 날 반복적인 실행 시험을 요청하지 않고 해당 로그와 영상으로 일괄 수정한다.

## 7단계 보완 — 최종 시험 전 읽기 전용 사전 점검

A12 `GeoField_Preflight_ReadOnly.cmd`는 먼저 ZIP 내부 SHA-256과 **설치된** 런타임의 필수 파일·정적 API 계약·엔진 호환성을 확인한다. 이 단계는 **GeoField를 실행하거나 설치하지 않고 FEA를 계산하지 않는다.** 콘솔에는 사용자 계정/설치 경로가 표시될 수 있으니 외부 공유 전 반드시 가린다. 실패 시 `GeoField_Start.cmd`를 실행하지 않고 이 결과만 Antigravity에 전달한다.

`GeoField_Acceptance_Check.cmd`는 **실제 계산 후** 한 번 실행하며, 첫 서버 인스턴스와 마지막 서버 인스턴스가 같고 현재 CAD·복원 상태 및 실제 FEA 수치·조건이 검사 중 달라지지 않았는지 재검증한다. 검사 도중 서버가 바뀌거나 동일 CAD에 새 계산이 연결되면 그 결과의 응력·변위를 보고서에서 제거해 불확실한 결과를 통과시키지 않는다. 진단기가 실제 화면의 3D 렌더링을 검증한 것은 아니다.

## 사용자 Windows 1회 실제 검증 순서 (최종 단계에서만)

1. 기존 GeoField에서 편집 중인 내용을 저장하고 정상 종료한다. 다운로드한 **A12 통합 후보 ZIP**을 Windows 파일 탐색기로 딱 한 번 압축 해제한다. 반디집/7-Zip의 ZIP 미리보기에서 CMD를 실행하지 않는다. 먼저 `GeoField_Preflight_ReadOnly.cmd`로 사전 점검한다. 실패하면 실행 단계로 넘어가지 않는다.
2. 압축 해제한 폴더의 `GeoField_Start.cmd`를 1회 실행한다. 파일 무결성 검증, 기존 소스 해시 검사, 기존 엔진 호환성 결과를 확인한다. 설치 충돌·알 수 없는 프로세스·복구 불가 문구가 나오면 즉시 중단하고 로그를 전달한다. 기존 소스 승인 또는 변경은 내용을 이해한 경우에만 한다.
3. 프로그램이 `http://127.0.0.1:8600/`에 정상 표시되면 원본 L 브래킷 STEP을 선택한다. 모델 실측/홀/면 선택, FE 조건(재료·고정면·하중면·질량·방향)을 저장한다. 준비된 원본과 선택한 실제 물성을 기록하고 예시 수치를 결과로 표시하지 않는다.
4. **한 번의 실제 Gmsh→CalculiX 실행**으로 새 `INP/STA/FRD` 근거, 원본 CAD SHA, 해석 case SHA, 실행 ID 및 계산 단계/실패 상태를 확인한다. 응력 MPa·변위 mm가 계산 파일의 실측 값과 일치하는지 확인한다. 3D 색상·최대응력 위치·미검증 CAD 면 귀속 여부를 구분해 확인한다.
5. 해당 실행의 SQLite 저장 상태가 `저장 완료`로 표시되는지 확인한다. 보고서 HTML에는 실제 FEA 원본 추적, 수치/해석조건, 미검증 수렴·안전성 표시가 있어야 한다. 기록에서 **복원 가능한 이전 결과**를 선택해 실행 ID/조건이 바뀌지 않고 새 계산으로 오표시하지 않는지 확인한다. 실제 이전 FEA 2건이 이미 존재하는 경우에만 비교 기능을 확인한다. **실제 사용자 데이터에 영구 삭제 버튼을 누르지 않는다.**
6. AI 근거 분석은 `rules_only`로 확인한다. DeepSeek 실통신과 ML 새 학습은 이번 1회 시험의 필수 조건이 아니다. 다른 FEA 실행의 값이 섞이거나 추정 응력을 실측값처럼 표시하면 실패로 판정한다.
7. **GeoField_Start.cmd 백엔드 창을 닫지 않은 상태에서** 같은 폴더의 `GeoField_Acceptance_Check.cmd`를 한 번 실행한다. 이 도구는 실행기가 아니며 이미 실행 중인 로컬 API 증거만 읽는다.
8. 영상은 STEP→실제 계산→3D→저장/복원→AI→검증 명령 1회 흐름으로 촬영한다. 외부 공유 시 파일명·로컬 경로·API 키·프로젝트 비밀 정보는 가린다.

## 기록과 중단 기준

- 읽기 전용 진단: `%LOCALAPPDATA%\GeoFieldCAD\diagnostics\acceptance\geofield_acceptance_latest.json`.
- 부팅·엔진 로그: `%LOCALAPPDATA%\GeoFieldCAD\diagnostics\r12_launcher\bootstrap_latest.log`, `backend_latest.log`.
- 잠금 실패/모듈 미발견/포트 충돌/FEA 계산 실패/STA·FRD 불일치/3D 표시 불가/저장·복원 ID 불일치는 전부 **보류**이다. 녹화·로그를 바탕으로 GitHub/Antigravity에서 원인을 모아 수정하고 *같은 날 반복 실행을 요구하지 않는다*.
- CI 또는 실행기 검증 통과는 실제 구조 안전성, 메시 수렴, 실측 물성 신뢰성 인증을 의미하지 않는다.
