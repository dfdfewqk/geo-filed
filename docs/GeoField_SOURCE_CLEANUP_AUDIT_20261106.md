# GeoField 전체 미사용 소스 정리 감사 — 2026-11-06

## 범위와 보존 원칙

기준: `dfdfewqk/geo-filed`의 Draft PR #131 HEAD
`6e258f174560de6af5b59a268aff7302e36270cf`.
정리용 별도 브랜치 `work/geofield-unused-code-cleanup-20261106`에서만 수정했다.
`main`, 실제 Windows 설치 경로, 사용자 원본 STEP, ML 체크포인트,
SQLite, INP/STA/FRD, 저장된 HTML, 3D 결과는 변경하지 않았다.

GitHub 재귀 tree는 347개 항목(디렉터리 포함)이며, 그중
제품·지원·연구 Python 소스 46개를 조사했다(테스트 Python 제외).
핵심 JavaScript `src/payload/frontend/cad.js`는 전역 선언 함수
167개의 호출명 빈도와 같은 파일 및 HTML의 참조를 대조했다.
`src/payload/frontend/index.html` 이벤트 바인딩 및
`src/tests/` 회귀 테스트가 기능·사용자 데이터 보존을 입증할 때만 정리를 승인한다.

이 조사는 **정적 참조 검사**다. 문자열 기반 동적 접근,
기존 사용자 설치본의 비공개 모듈, 과거 Git ref의 재현용 스크립트,
외부에서 호출하는 CLI는 정적 검사만으로 미사용 판정하지 않는다.

## 실제 제거한 미사용 import (총 9개, 실제 로직·데이터 파일 삭제 0개)

| 파일 | 지운 import | 확인 |
|---|---|---|
| `src/payload/GeoField_CAD_Analysis.py` | `engine_python`, `REQUIRED_GMSH` | 해당 이름은 import 정의 이외의 서버 소스에서 참조되지 않음. `REQUIRED_ML`, `gmsh_python_status`, `prepare_python_environment` 유지 |
| `src/payload/fea_solver.py` | `sys` | 해당 이름은 import 이외의 솔버 소스에서 참조되지 않음 |
| `src/payload/ml/r12_research/train_eval.py` | `hashlib`, `sys`, `Counter`, `balanced_accuracy_score` | 연구 학습/평가 함수에서 참조 없음. `accuracy_score`와 `confusion_matrix` 및 원본 모델·라벨·분할 로직 유지 |
| `src/research/brepmfr_v2/train_pose_invariant.py` | `Counter` | 모델 학습·교차 검증 함수에서 참조 없음 |
| `src/research/brepmfr_v2/train_research.py` | `hashlib` | 학습 스크립트에서 참조 없음. 검증된 `sha256` 도우미는 유지 |

최초 정적 검사에서 Python 상위 import 9개가 정의문 이외의 이름 사용이
없음을 확인했고, 각 파일의 정확한 import 줄만 수정했다.
나머지 Python 내부 import도 재확인했으나 같은 수준의 명확한
미사용 후보는 없었다. JS 전역 함수는 선언만 있는 미호출 함수로
확정되는 항목이 없었으며 무리한 일괄 삭제를 하지 않았다.

## 점검 후 삭제하지 않은 항목

- `src/payload/legacy/geofield_v823_extension.py`:
  짧은 Git 스텁이지만 Windows 기록용 비공개 런타임 경로의 정확한 위치다.
  `RECORDS=record_module()` 및 기록/보고서 동작과 연결되므로 보존.
- `src/fea_result_trust_gate.py`와
  `src/payload/fea_result_trust_gate.py`:
  독립적인 검증/배포 경로가 존재해 파일명만 보고 중복 제거 불가.
- `src/manifest.json`, `verify_package.py`, `build_integration_candidate.py`,
  이전 릴리스 해시·보호 조건·Windows 설치 스크립트:
  **오래된 해시를 임의로 갱신하거나 지우면 기존 설치본 복원에 장애**.
- `src/payload/ml/r12_research/research_model.joblib` 및 `report.json`:
  연구 모델 가중치·실험 출처 근거.
- `fixtures/L_bracket.step`, BrepMFR 연구 도구와
  `src/tests/`, `.github/workflows/`, 과거 문서 기록:
  실행 재현·감사·회귀 테스트 증거. 서로 유사하다고 삭제하지 않음.
- GeoField 서버/브라우저의 하위 호환·이전 실행 복원·API 호출 오류 처리:
  런타임 사용 여부를 확인하기 전에는 변경 금지.

과거 보관 기록의 한 차례 정리는
`docs/GeoField_SOURCE_CLEANUP_AUDIT_20261105.md` 및
`docs/GeoField_LEGACY_QA_NOTES_ARCHIVE_20261105.md` 참조.
이미 제거된 안내문을 다시 삭제하거나 원본을 반복 복사하지 않는다.

## 정리의 검증 기준

정리 전 PR #131 전체 CI 9/9 성공. 정리 후에는 이 브랜치에 연결한
`geofield-full-system-audit-20261105.yml`에서 아래 항목을 모두 확인한다.

- 전체 Python 테스트, 실제 원본 SHA·FEA 보고서·유료 AI 입력 차단
- 전체 프런트엔드 JavaScript 보고서·뷰·재시작·다운로드 회귀
- 실제 Gmsh/CalculiX 원본 L-브래킷과 3회 메시
- 실제 R12 연구 추론 및 Windows 런처/롤백·원본 보존

전체 CI 실패 시 추가 삭제나 병합 금지.
자동검사 성공은 실제 사용자 Windows 3D/WebGL·외부 유료 AI 실서비스
최종검증을 대신하지 않는다. 해당 검증 전까지 Draft 유지.

## 이후 추가 정리 기준

외부 설치본의 `record_module()` 등 동적 의존성과 CLI,
개별 역사적 워크플로 경로가 **실제 실행 미사용**임을 입증하기
전에는 임의 삭제하지 않는다. 유료 AI 호출·ML 재학습·FEA 신규 계산은
이 정리 작업에 불필요하므로 수행하지 않는다.
