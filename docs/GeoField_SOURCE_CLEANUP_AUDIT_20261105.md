# GeoField — 2026-11-05 보수적 미사용 파일·코드 정리 보고

## 목적과 원칙

PR #110의 실제 사용자 Windows 화면에서 확인한 보고서 버튼 수정 기능을 유지하면서, 최신 Windows 업데이트에 포함되지 않는 **과거 QA3~QA11/최종 후보 배포 안내 파일**만 통합한다. 실행 코드·솔버·CAD·ML·SQLite·현재 설치된 Windows 환경에 닿지 않으며, 중요한 기록은 삭제하지 않는다.

분석 대상: `dfdfewqk/geo-filed` 최신 작업 브랜치, Git tree 338개 항목(디렉터리 포함). 정확한 실행 의존성 확인 없이 단지 파일 이름에 'legacy'나 'old'가 있다는 이유로 지우지 않는다.

## 실제 정리한 항목

| 대상 | 조치 | 확인 |
|---|---|---|
| `src/QA3_검증안내.txt` ~ `src/QA11_검증안내.txt` (9개) | 원문 전량 보관 후 소스 루트에서 제거 | Git blob SHA-1 무결성 자동검사 |
| `src/FINAL_검증안내.txt`, `src/FINAL_통합테스트_체크리스트.txt`, `src/PORT8600_수정사항.txt` (3개) | 같은 보관 문서로 합치고 루트에서 제거 | Git blob SHA-1 무결성 자동검사 |
| `src/geofield_live_preflight.py` | 사용되지 않는 `import urllib.error` 1줄 제거 | read-only preflight 테스트 |
| `src/tests/test_ui_cleanup.py` | 이전 UI 배치·옛 AI 동의식에 대한 낡은 테스트 조건을 현재 화면 구조와 1회 수동 동의 규칙으로 교정 | 실제 HTML/JS 구조 검사 |
| `src/tests/test_legacy_release_notes_cleanup.py` | 12개 기록의 바이트 복원 가능성, Windows 패키지 비의존성, 필수 기록 모듈 보존 검증 추가 | GitHub Actions |

보관된 원문: [GeoField_LEGACY_QA_NOTES_ARCHIVE_20261105.md](./GeoField_LEGACY_QA_NOTES_ARCHIVE_20261105.md). Git 기록에서 개별 원문도 그대로 복원할 수 있다. 새로운 기능은 없다.

## 조사했지만 보존해야 하는 것

- `src/payload/legacy/geofield_v823_extension.py`: 텍스트가 짧더라도 **삭제 금지**. 현재 백엔드는 `record_module()`으로 정확히 이 경로를 import한 뒤 `RECORDS.register_cad`, `list_records`, `get_record`, `generate_report` 등 기록/보고서 기능에서 사용한다. Git 저장소의 작은 테스트 스텁만으로 실제 설치된 비공개 기록 모듈을 대체할 수 없다.
- `src/fea_result_trust_gate.py`와 `src/payload/fea_result_trust_gate.py`: 단순한 중복 복사라고 단정하지 않는다. 원본 C3D4/C3D10 검증 분기와 테스트 참조가 존재하며 내용도 완전히 동일하지 않다.
- `src/payload/frontend/cad.js`, `index.html`, `src/payload/GeoField_CAD_Analysis.py`, `src/payload/fea_solver.py` 등 실제 실행 파일: 원클릭, 3D, 외부 AI 동의, 솔버/이력 의존성이 연결되어 있으므로 일괄 축약 금지.
- `src/tests/` 회귀검사 전체, `.github/workflows/`의 과거 개별 실솔버 CI, BrepMFR 학습·연구 스크립트: 즉시 Windows 실행 파일에 묶이지 않아도 검증·재현의 근거로 사용한다.
- `fixtures/L_bracket.step`, 연구 모델 가중치, 원본 실행 파일, 사용자 PC의 SQLite·INP·FRD·STA·MP4·설치 폴더: **변경·삭제 없음**.

## 테스트 범위

GitHub Actions는 Linux 전체 프런트엔드 JS 회귀, Windows+Linux 목표 UI 회귀, 에이전트·SQLite·보고서 출처/복원·과거 메모 정리 무결성, 소스 잠금 Windows 업데이트 **테스트 후보** 검증을 수행한다. 이는 사용자 Windows에서 실제 원본 L-브래킷을 클릭해 계산/보고서/복원을 완주했다는 증명이 아니므로 그런 결론을 내리지 않는다.

**추가 정리 정책**: 향후 실제 Windows 사용 중 새로 문제로 확인된 코드 이외에는, 근거 없이 오래된 모듈이나 테스트를 추가 삭제하지 않는다. `main`은 수정하지 않는다.
