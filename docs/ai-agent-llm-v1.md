# GeoField AI 에이전트 6단계 — 외부 LLM 연결 (선택 사항)

> 적용 범위: `work/ai-agent-evidence` · PR #5. **기본값은 언제나 `rules_only`이며 외부 호출하지 않습니다.**

## 연결 환경과 동의

GeoField 기존 소스에는 외부 LLM 설정·확인된 API 호출이 없어, 기존 규칙 기반 판단을 변경하지 않고 **OpenAI Chat Completions HTTPS** 선택적 설명 통로를 추가했습니다.

실행 환경(프로그램 기동 전)에 다음 값을 넣은 경우에만 호출을 허용합니다.

- `GEOFIELD_AGENT_LLM_ENABLED=1`
- `GEOFIELD_AGENT_LLM_MODEL`: 계정에서 사용할 수 있는 모델명
- `GEOFIELD_AGENT_LLM_API_KEY`: API 제공업체에서 발급한 비밀 키

설정값은 GitHub 소스, 저장된 SQLite, 화면, JSON 응답에 포함하지 않습니다. API 키는 HTTPS 인증 헤더에만 포함되어 OpenAI 서버에 전달되고, 모델 입력 메시지에는 포함하지 않습니다.

사용자는 웹 UI의 "이번 분석에 한해 외부 LLM 참고 설명 요청" 체크박스를 **직접 선택하고** 기존 근거 분석 버튼을 눌러야 합니다. 클라이언트는 `?llm=1`과 별도의 `X-GeoField-LLM-Opt-In: 1` 헤더를 같이 전송합니다. 서버는 이중 조건과 same-origin 출처 조건을 확인합니다. 동의는 매 요청 후 해제하며 다른 CAD를 불러와도 초기화됩니다.

외부 모델 비용은 계정과 모델에 따라 발생할 수 있습니다.

## 인증된 입력과 결과 격리

실제 원본 계산 교차검증에 성공한 최대 von Mises 응력(MPa), 최대 변위(mm), 검증 상태, 명시된 메시 요소 종류, 측정 후보 수, ML의 연구 전용 상태만 외부 서비스에 JSON으로 보냅니다.

**전송하지 않는 데이터:** STEP/FRD 원본, 원본 파일명, 원본 CAD 메쉬, CAD 작업 ID, 실행 ID, SHA, 저장된 사용자 기록 전체, 위치 좌표, 사용자 임의 문구.

- `gf_agent_evaluate` 및 FRD 원본 신뢰 게이트의 수치가 **항상 권위 있는 데이터**입니다.
- 외부 모델 설명은 `llm.explanation`에만 존재하며 `fea`, `cad`, `ml`, `findings`, 원본 보고서·SQLite를 덮어쓸 수 없습니다.
- 실제 API 응답이 성공하고 유효한 문장을 반환했을 때만 `rules_plus_llm`, `connected=true`로 표시합니다.
- 설정 없음, 동의 없음, 연결 오류, API 응답 이상, 타임아웃 시 기존 `rules_only`를 유지하고 규칙 분석 결과를 보존합니다.
- LLM이 만든 참고 설명은 정답·설계 개선율·안전 판정·메시 수렴 확인이 아니며, 화면에서 별도 표시합니다.
- API 호출은 기본적으로 비활성화됩니다. 외부 LLM 성공 연결은 실제 키와 네트워크에서 검증되기 전까지 주장하지 않습니다.

## 자동 검사와 검증 범위

- Python `test_agent_llm.py`: 동의 없는 전송 없음, 가짜 전송 테스트, 키·원본 식별값 미유출, FEA 수치 격리, 이상 응답·통신 오류 시 안전한 복귀
- Node `test_agent_ui.js`: 화면에서의 명시적 동의/해제, 연결 상태별 표시, 기존 규칙 분석, 오래된 CAD 응답 폐기
- Ubuntu/Windows 및 A+B+AI 임시 통합 CI에서 기존 CAD/ML/FEA 테스트와 함께 실행

이는 **모의 transport 기반 자동 테스트**이며 실제 OpenAI 계정 인증·요금·전송 성공, 실제 Windows/CalculiX 동작, 외부 모델 정확도를 인증하지 않습니다.
