# GeoField AI 에이전트 — 2단계 CAD 실측·3D 면 연결 계약 v1

이 문서는 AI 에이전트가 기존 CAD 분석에서 검증된 면 정보만 사용하도록 고정하는 기준입니다. CAD B-Rep 엔진, ML 모델, FEA 계산기를 새로 구현하지 않습니다.

## 실제 입력
- 활성 STEP: CURRENT.job_id, JOBS[job_id], analysis.sha256. 동일 CAD 작업 32자리 ID, STEP SHA-256 64자리 필요.
- 실제 CAD 3D 메시: JOBS_DIR 내 현재 작업의 JSON에 있는 sha256와 mesh.face_ids. 이는 삼각형마다 연결된 CAD 면 ID 배열이며 중복될 수 있습니다.
- 기존 review_decision 함수의 검토 항목: where, measured_evidence, face_ids, next_check.
- ML: BrepMFR의 face_ordinal 및 R12 내부 면 번호. 이 번호를 3D CAD 면 ID와 같다고 가정하지 않습니다.

## 에이전트 API
GET /api/agent/evidence/{현재 CAD 작업 ID}의 cad_features.schema = geofield-agent-cad-features-v1.

- verified_in_current_cad_mesh: 원본 SHA가 같고, 후보 face_ids가 모두 현재 CAD의 mesh.face_ids에 존재한 경우만 3D 면 강조 허용.
- not_verified: ID 누락, 타입 오류, 현재 3D 면 목록에서 빠진 경우. 일부만 일치해도 3D 강조 금지.
- mechanical_risk_confirmed, thin_wall_confirmed, hole_through_confirmed, fea_hotspot_correlated 는 모두 false. 별도 실측·공간적 교차검증 없이는 참이라고 말할 수 없습니다.
- ml_face_ordinals_are_cad_face_ids = false: ML 면 번호를 CAD 면 번호로 자동 변환하지 않습니다.
- CAD에서 실측 확인된 형상 검토 내용과 실제 FEA 응력 집중·홀 관통·최소 벽 두께 확정은 서로 별개의 증거입니다.

## 저장 및 자동검증
에이전트 설명은 기존 기록의 검증 데이터를 다시 읽어 생성하며 별도 SQLite 설명 테이블을 쓰지 않습니다. 새 STEP/FEA 복원 중 이전 요청은 UI에서 무효화합니다.

Python: cd src/tests && python -m unittest test_agent_cad_features test_agent_evidence test_agent_input_contract -v
Node: node src/tests/test_agent_ui.js

이 테스트는 생산 함수에 합성 근거를 입력한 회귀 테스트입니다. 실제 Windows FreeCAD/Gmsh/CalculiX, GPU 표시, 메시 수렴 및 구조 안전 인증의 근거가 아닙니다.
