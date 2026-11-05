# GeoField 전체 진단 (2026-11-05) — 테스트 결과 및 모든 미해결 항목

> **진단 전용**. 대상 `dfdfewqk/geo-filed`의 PR #111 뒤 소스. 실제 애플리케이션 코드를 바꾸거나 사용자 STEP/SQLite/ML/FRD를 읽거나 고치지 않았다. 이번 진단은 `.github/workflows/geofield-full-system-audit-20261105.yml` 추가 및 테스트 러너의 의존성/줄바꿈만 조정했다. **완벽한 실행이나 최종 배포 합격을 선언하는 문서가 아니다.**

실행 증거:
- [완성형 진단 재실행 (GitHub Actions #41976663185)](https://github.com/dfdfewqk/geo-filed/actions/runs/41976663185)
- [초기 탐색 실행 (GitHub Actions #41976340659)](https://github.com/dfdfewqk/geo-filed/actions/runs/41976340659)
- [PR #110 보고서 버튼 수정본](https://github.com/dfdfewqk/geo-filed/pull/110)
- [PR #111 보수적 파일 정리](https://github.com/dfdfewqk/geo-filed/pull/111)

## 실행 범위와 검증된 성공

| 검증 영역 | 실제 실행 | 결과 및 한계 |
|---|---|---|
| 전체 브라우저 JS | Node 22, Ubuntu 53개 검사 | 53/53 PASS |
| 원래 Windows 소스 줄바꿈 | Windows 53개 JS 검사 | 3 FAIL (아래 정확한 원인 확인) |
| Windows CRLF→LF **임시 실행기 사본만** 정규화 | Windows Node 22, 전체 53개 | **53/53 PASS**; 프로그램 소스 저장소 미수정 |
| Python 전체 자동검사 Ubuntu / Python 3.12 | `unittest` 발견 835개 | 1 FAIL, 25 ERROR, 36 SKIP. 전체 패스 아님 |
| Python 전체 자동검사 Windows / Python 3.13 | 동일 835개 | 1 FAIL, 25 ERROR, 22 SKIP. 전체 패스 아님 |
| 실제 물리 FEA | 원본 `fixtures/L_bracket.step` SHA `fe6584...`; Ubuntu Gmsh 4.12.1, CalculiX 2.21 | 기본 1회 + C3D4 메시 세 단계 3회 + C3D10 메시 세 단계 3회, **총 7개 실제 솔버 해석 PASS** |
| R12 실제 연구 모델 | CadQuery/OCP + 로컬 joblib/sklearn | STEP 기반 실제 추론 4개 및 fail-closed 15개 테스트 통과; 독립 모델 정확도 인증은 아님 |
| Windows 설치·업데이트 | 실제 Windows CMD, **임시 가짜 사용자 설치 경로** | 검증·설치·실패 롤백·구버전 15경로 백업·사용자 자료 보존 검사 통과 |
| GitHub Windows 테스트 후보 | 최신 PR #111 기존 워크플로 | 26개 파일 SHA/source lock 일치 검증 통과; **독립 EXE/새 설치 프로그램 아님** |

### 실제 계산 수치의 해석 제한

공개 원본 L-브래킷, 3kg, -Z 등의 **CI용 조건**에서 기본 FEA는 최대 4.84248049 MPa, 최대 변위 0.02605893 mm, 실제 반력 잔차 검증 PASS. 3회 C3D4 메시 해석 대상 요소 크기 4.2/3.0/2.25mm의 응력 최대값은 약 4.733/4.842/5.011 MPa. 인접 변위 변화율 중 **9.422998%**로 기존 5% 수치 안정성 선별 기준 **미충족**. 이것은 소프트웨어 동작 오류가 아니라 **수렴·구조 안전성 미확정이라는 실제 공학적 결과**다. 3회 계산 PASS와 '수렴 검증 PASS'를 혼동하지 않는다.

**사용자 Windows 영상은 `L_bracket_correct.step` 6kg +X(약 22.632 MPa / 0.03971mm) 조건이다.** CI 공개 STEP/3kg/-Z 수치를 사용자 결과의 정답이나 불량 근거로 직접 비교하지 않는다.

## 발견 항목 — 총 6가지 테스트 오류 유형

Python 재실행에서는 두 운영체제 모두 **25 ERROR + 1 FAIL**이 동일 범주로 나왔다. 25개 오류를 숨기지 않고 재현 원인별로 모두 분류했다.

| 구분 | 발생 수 | 해당 테스트 파일과 구체적 원인 | 분류 및 필요한 조치 |
|---|---:|---|---|
| A. 과거 QA/FRD 원본 ZIP 또는 작업 폴더 없음 | **15 ERROR** | `test_final_validation.py`, `test_qa5.py`, `test_qa7.py`, `test_qa8.py`, `test_qa10.py`, `test_qa11.py`. `/mnt/data/GeoField_R12_13_QA6_...zip`, QA7, QA10, QA11, 예전 FRD 및 `geofield_qa6_work` 절대 경로 참조 | **테스트 자산·이식성 문제**. 과거 자료 해시 확인 또는 격리된 재현 데이터로 교체. 없으면 '미실시'로 표기, 성공으로 둔갑시키지 않음 |
| B. 이전 manifest 목업에 `files` 필드 없음 | **6 ERROR** | `test_lbracket_p5_read_only_compat_audit.py`의 5건, `test_runtime_source_api_contract.py`의 1건. 실제 `bootstrap.main`은 현행 26파일 manifest를 기대하지만 목업은 `{runtime_id: ...}`만 반환하여 `KeyError: 'files'` | **구버전 테스트 계약 불일치**. 새 manifest 목업에 현재 필드를 공급하고 손상된 manifest 별도 실패-차단 테스트를 추가하는 것이 좋음. 실제 설치본 오류로 확정되지 않음 |
| C. 오래된 FEA UI 함수 정의 문자열 찾기 실패 | **2 ERROR** | `test_final_validation.py`, `test_qa10.py`. 실제 콜백은 `onclick=async(launchMode)=>`인데 옛 테스트는 `onclick=async()=>` 원문만 검색하여 `IndexError` | **테스트 소스 추출자 노후화**. 현재 실행 코드의 보호된 발췌/상태 모의로 수정. FEA 콜백 자체 작동 실패 증거는 아님 |
| D. 동일 데이터를 중복 생성한 연구용 ML 그래프 | **1 ERROR** | `test_brepmfr_v2_research_pipeline.py`. 테스트의 `np.savez_compressed`가 클래스별 동일 5면 그래프를 여러 개 만들어 정확히 같은 SHA가 생김. `train_research.validate_corpus`가 `Tampered or duplicate graph`로 거부 | **테스트 데이터 생성 문제**가 유력하며 독립 재현으로 동일 npz→동일 SHA 확인. 중복을 막는 검증을 제거해서는 안 됨. 서로 독립적인 유효 그래프 fixture로 재검증 필요 |
| E. 과거 QA11에서 별도 비공개 Windows 런타임 전체를 요구 | **1 ERROR** | `test_qa11.py`: `analysis_hub.py`, `engine_runtime.py`, `fea_previous_import.py`, `frontend/cad.css`, `legacy/geofield_v823_extension.py` 등 실제 설치 환경 모듈이 CI 체크아웃에 부재/부적합 | **CI 환경·설치본 전제 불충족**. 사용자 Windows 환경의 실제 파일은 이 진단에서 읽지 않았으며 삭제/자동 생성 금지 |
| F. 구버전 QA7 오류 메시지 기대가 현행 26파일 후보와 충돌 | **1 FAIL** | `test_qa7.py`: `Refusing to overwrite unknown source`를 기대했지만 실제는 `Unexpected payload files in manifest`로 먼저 차단됨 | **옛 테스트 메시지·패키지 형식 불일치**. 설치가 불안전한 입력을 차단했다는 점은 확인했지만 구 QA7 전용 세부 검사는 통과하지 못함 |

초기 Python 검사에서는 `pytest` 및 `numpy` 미설치에 따른 추가 import 실패가 있었다. **재실행에서 의존성을 설치한 뒤 이 계열은 제거**되었으므로, 그것을 남은 실제 프로그램 결함으로 세지 않는다.

## Windows에서만 처음 실패했던 JS 3건 — 원인 확정

- `test_b05_fea_delete_ui.js`
- `test_fea_stage3_auto_unified_report_ui.js`
- `test_fea_stage6_evidence_display_ui.js`

Windows Git checkout이 `src/payload/frontend/cad.js`에 CRLF 4,727개를 삽입한 반면 일부 테스트는 내부 문자열에 LF `\\n`을 하드코딩한 상태에서 원문 추출/비교했다. CI 임시 복사본에서 LF로 바꾼 뒤 **이 3개와 전체 53개가 모두 PASS**했다. **프런트엔드 기능 고장을 의미하지 않으며**, 테스트가 다른 표준 줄바꿈 양쪽을 받아들여야 한다. GitHub 실제 소스는 수정하지 않았다.

## 사용자 요구 대비 별도 확인/미해결

1. **[높음: 사용자 보고 실증] 최신 PR #110 보고서 버튼 수정의 실사용 재검증은 여전히 미실시.** 2026-11-05 원래 화면 녹화에서는 검증된 22.632MPa 응력 지도가 보이지만 HTML 보고서 버튼이 비활성화되었다. 수정된 코드의 브라우저 계약 테스트는 통과했으나 사용자 Windows의 실제 원본·오래된 기록·연속 메시 동작이 한 번에 완주했는지는 확인하지 못했다.
2. **[중간: 사용자 요구 의미와 차이] AI ON/OFF 토글의 현재 뜻이 '외부 유료 AI 포함 여부'만이다.** `index.html`은 OFF일 때도 '로컬 규칙 기반 AI 보고서 자동 생성'이라고 명시하고, 서버 `gf_current_verified_report(as_html=True)`는 스위치와 관계없이 `gf_render_live_agent_report`를 호출한다. 따라서 사용자가 요구한 'AI OFF이면 과거 AI 결과까지 보고서에서 제외'가 **외부 AI뿐 아니라 로컬 AI 전체를 뜻한다면 현재 구현과 맞지 않는다**. 외부 AI 캐시가 OFF에서 제거된다는 테스트는 별도로 통과했으나 로컬 AI 제외는 구현되지 않았다. 사용자 지시 범위를 넘는 UI 기능 추가가 아니라 기존 토글의 의미 불일치임.
3. **[중간: 실행환경 의존] 26파일 후보는 독립 실행형 전체 GeoField/EXE가 아니다.** 기존 설치의 엔진·기록·CSS·FreeCAD/FEA 등 필수 모듈에 의존하며, GitHub의 `payload/legacy/geofield_v823_extension.py`은 49바이트 테스트 스텁이므로 **실제 사용자의 사설 기록관리 코드 대체 금지**. 실제 Windows 설치 경로에서 호환성 검사로 검증해야 함.
4. **[미검증] 전체 앱 실제 3D GPU/WebGL, 원본 현재 STEP을 통한 버튼 1회→ML→새 FEA→세 번 추가 해석→HTML 보고서→SQLite 비교/재실행 복원**은 사용자 PC 실기동이 필요. 이번 CI 실제 물리 해석과 브라우저 계약 시험은 분리 실행했음. 브라우저와 CAD 엔진 간 전체 엔드투엔드 검증 PASS를 주장할 수 없음.
5. **[미검증] 개인 Windows BrepMFR epoch43 모델·실제 학습 데이터, 유료 DeepSeek/OpenAI 외부 연결**은 이번 CI에서 실호출하지 않았음. R12의 실제 모델 추론은 성공했지만 독립 라벨 정확도는 증명하지 않음. **무단 유료 API 사용 없음**.
6. **[공학적 경고] C3D4 3메시 수치 안정성 선별 5% 기준을 실제 데이터에서 통과하지 못함.** 응력/변위가 수치적으로 결과를 출력하는 것과 설계 안전성/응력 집중 수렴 인증은 별개다.

## 결론

- 최신 소스의 UI 시뮬레이션 및 실제 공개 STEP/솔버와 R12 추론, Windows 업데이트/롤백의 **검증 범위 내 결과는 긍정적**이다.
- **전체 Python 회귀검사는 아직 빨간색**이다: 25 오류 + 1 실패 (Linux/Windows 동일한 분류). 테스트 자산, 오래된 테스트, 실제 외부 런타임 가정 때문에 포괄적 안정성에 대한 단정 불가.
- **사용자에게 이미 발생했던 보고서 버튼 문제는 수정 후 실제 Windows에서 확인할 필요가 있음.** 새 기능/다른 STEP 형상 개발을 제안하지 않는다.
- 안전한 다음 순서: 오래된 실패 테스트의 오탐 제거·정확한 의존성 판별 → 현재 기능만 재회귀 → 필요할 때만 실제 Windows 한 번에 통합 검증 → 결과를 바탕으로 오류 수정/최종 배포. 이번 진단에서는 **기존 제품 코드 변경 없음, main 변경 없음, 배포 없음.**
