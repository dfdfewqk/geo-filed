# GeoField A+B+AI — Windows 실사용 최종 확인 절차 (한 번의 테스트)

> 이 문서는 실제 CAD·FEA·AI 프로그램을 사용자가 자신의 Windows에서 테스트할 때의 단일 확인 절차다. **자동 CI나 후보 ZIP 생성만으로 실제 CalculiX 실행·ML 학습·3D 렌더링·설계 안전성이 입증되지 않는다.**

## 준비

- GitHub PR #5 Actions에서 최신 `GeoField-A-B-AI-Windows-ONE-EXTRACT-CANDIDATE-NOT-FINAL` 아티팩트를 받는다.
- Windows 파일 탐색기에서 ZIP을 **한 번만 압축 해제**한다. 내부에 두 번째 ZIP이 없는 것이 정상이다. 압축 프로그램(Bandizip·7-Zip 등)의 미리보기에서 CMD를 직접 실행하면 `Temp\\BNZ...` 임시 폴더로 CMD만 복사되므로 실행하지 않는다. 압축 해제한 폴더의 `START_HERE_ONE_EXTRACT.txt`를 먼저 확인한다. 기존 GeoField 프로젝트의 원본 STEP, SQLite, INP/STA/FRD는 이동·삭제하거나 덮어쓰지 않는다.
- 이 ZIP은 기존 `%LOCALAPPDATA%\GeoFieldCAD\onefile_runtime\8a9ac53a821a0eb5`가 설치된 PC를 위한 **업데이트 검증 후보**이며, 신규 PC에서 바로 실행되는 독립 앱이 아니다.
- 기존 GeoField CMD/백엔드가 실행 중이면 정상 종료한다. 설치 실행기는 변경 전 로컬 의존성 검사, 원본 보존, 백업/롤백을 수행하며 이상 시 수정 없이 중단하도록 설계됐다. 반드시 설치 상태가 정상인지 직접 확인한다.

## 집에서 필요한 한 차례의 전체 동작 시험

1. 압축 해제 폴더의 **`GeoField_Start.cmd`** 를 실행한다. 실행 성공 전까지 패키지 해시 검증 → 기존 런타임 의존성 확인 → 업데이트 → 서버 시동/브라우저 열기가 수행된다. 실패하면 추가 설치 시도를 반복하지 말고 로그를 먼저 확인한다.
2. 브라우저에서 원본 STEP을 가져오고 CAD 실측/형상 후보가 실제 원본과 맞는지 확인한다.
3. 기존 자동 ML이 수행됐는지 확인한다. `not_run` 또는 `failed`면 자동 ML 완료라고 표시하지 않는다. AI의 연구용 ML 후보를 CAD의 실제 3D 면 ID와 같은 것으로 취급하지 않는다.
4. 기존 FEA 입력 순서 **재료 → 고정면 → 하중면 → 질량(kg) → 방향 → 조건 저장 → 신규 계산/검증된 이전 실행 연결**을 한 번 수행한다. 실제 응력/변위 및 3D 색상·하중 분포가 화면에서 보이는지 확인한다. C3D4/C3D10 요소 형식, 수렴 여부, 반력 평형, 구조 안전성은 화면 표시만으로 인증하지 않는다.
5. 기존 AI 근거 분석에서 원본 STEP SHA, FEA 실행 ID/조건 SHA의 식별 계약이 일치하고, 실제 FEA 데이터가 없을 때 추정 응력/변위를 내지 않는지 확인한다. 외부 LLM은 테스트를 위해 필요하지 않으며, 별도 동의 전에는 호출하지 않는다.
6. **GeoField 브라우저/CMD가 실행 중인 상태에서**, 같은 압축 해제 폴더의 `GeoField_Acceptance_Check.cmd`를 실행한다. 이 CMD는 원본 CAD·SQLite에 접근하거나 변경하지 않으며 `127.0.0.1:8600`의 읽기 전용 현재 상태만 검사한다. 실행/해시 오류는 명시적으로 차단한다.
7. 필요한 경우 기존 기록에서 과거 FEA를 복원하여 과거 실행/조건 SHA 및 3D 필드 연결을 확인한다. 복원 시 새 FEA 계산이라고 표시하지 않아야 한다. 이후 기록 검색 및 앱 재시작 복원을 하나의 영상에 포함할 수 있다.

## 제출용 근거

- 진단 JSON: `%LOCALAPPDATA%\GeoFieldCAD\diagnostics\acceptance\geofield_acceptance_latest.json`
- 화면 녹화: STEP 불러오기 → CAD/ML → FEA 실제 계산 및 3D → AI 근거 → 저장 및 복원
- 프로그램이 켜지지 않거나 도중 종료됐다면: `%LOCALAPPDATA%\GeoFieldCAD\diagnostics\r12_launcher\bootstrap_latest.log` 및 `backend_latest.log`

진단 JSON에는 CAD 원본 파일명·SHA·작업 ID·실행 ID·API 키를 보존하지 않는다. 오류는 유형 이름만 남긴다. **보고서의 `same_run_backend_reverified_source`는 로컬 API가 재검증했다고 반환한 출처와 수치의 일치**를 뜻하며, 이 스크립트 자체가 FRD를 독립 파싱했거나 화면에서 3D가 보인다는 뜻은 아니다. 영상/원본 로그와 결합해 확인한다.

## 중단/보류 기준

- 기존 엔진 누락, 출처 SHA 불일치, 비정상 포트, 패키지 해시 실패, 실측 CAD 문제
- ML 자동 시작 실패·미완료, 실제 Gmsh/CalculiX 실행 실패, 원본 INP/STA/FRD 검증 실패
- 3D 응력 분포/하중 화살표 미표시 또는 입력 변경 후 잘못된 결과 재활용
- 과거 실행 복원 후 CAD와 FEA 실행/조건 불일치

문제가 하나라도 있으면 **완성/배포 승인으로 처리하지 않는다**. 증거를 모아 오류를 한 번에 수정하고, 필요한 재시험만 계획한다. 최종 PR 병합·배포는 별도 결정이다.
