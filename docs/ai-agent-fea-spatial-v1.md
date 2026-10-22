# GeoField AI 에이전트 3단계 — 실제 FEA 표면 피크 위치 검증

목표: CAD·ML·FEA 수치 중 **실제로 INP/STA/FRD에서 재검증된 FEA 필드의 표면 절점**만 이용해 최대 절점 응력과 최대 표면 변위 위치를 보여주고, 현재 CAD 메시와의 위치상 근접 후보를 안내합니다. *하중·구속·FEA 결과를 새로 계산하지 않습니다.*

## 출처 확인
1. 현재 CAD STEP SHA, CAD 작업 ID, FEA 실행 ID, 해석 조건 SHA, 노드/사면체 수가 일치해야 합니다. 기존 reverify_task_for_display과 r125_reconcile_current_fea_summary 결과를 먼저 통과해야 합니다.
2. 새 에이전트 GET 경로에서 해당 실행 폴더의 verify_directory를 **다시 호출**하고, 실제 검증된 field를 qa_bind_verified_fea_field로 같은 실행에 귀속시킵니다. 기존 캐시 surface_field.json에 담긴 식별자만 믿고 사용하지 않습니다.
3. 필드 schema geofield-fea-surface-field-v1 / source actual_calculix_ascii_frd와 CAD/해석 조건 SHA, 실행 ID, 작업 ID를 검증합니다. 표면 좌표·응력·변위·삼각형 연결은 유한 수치, 크기, 인덱스가 맞아야 합니다.
4. 표면 피크가 글로벌 FEA 최대 응력 또는 변위를 초과하면 위치를 무효화합니다. **표면 최대치는 내부 포함 전체 최대치와 다를 수 있습니다.**

## 결과 계약
응답 fea_spatial.schema = geofield-agent-fea-spatial-v1

- verified_frd_surface_peak_positions: 실제 재검증 필드의 표면 절점 중 응력 및 변위 피크 인덱스/좌표(mm)/수치를 표시할 수 있습니다.
- not_verified: 필드 없음, 원본 불일치, 손상, 비유한 수치, 크기 초과 시 좌표와 피크 수치는 null입니다.
- cad_face_attribution_verified=false: 좌표가 가까워도 **정확한 CAD 면 귀속·응력 집중 원인·홀 주변 응력 집중을 증명한 것은 아닙니다**.
- cad_face_proximity.status = geometric_proximity_candidate_only: 현재 CAD의 삼각형 **내부 수직 투영**이 0.0001~0.02mm 허용 오차 내에 존재하고 근접한 CAD 면 ID가 한 종류일 때만 알려줍니다. CAD 면과 FEM 외피 면이 서로 다른 분할이므로 이는 위치 후보만 의미합니다.
- ambiguous_faces 또는 no_close_cad_triangle이면 CAD 면 ID를 숨깁니다.
- ML 내부 face_ordinal이나 R12 내부 면 ID를 3D CAD 면 또는 FEA 노드 ID로 번역하지 않습니다.
- actual 3D 필드가 존재해도 요소 종류, 메시 수렴, 반력 평형, 구조 안전성은 여기서 새로 판정하지 않습니다.

## 검증
Python: cd src/tests && python -m unittest test_agent_fea_spatial test_agent_cad_features test_agent_evidence -v
Node: node src/tests/test_agent_ui.js
자동 CI: Ubuntu, Windows, A+B+에이전트 임시 Windows 통합 설치 후보.

테스트는 **실제 코드에 합성 FRD 형태의 입력**을 전달하며 실제 사용자 Windows CalculiX 계산이나 3D 사용성 검사와는 구분합니다. 근거 파일이 없으면 에이전트는 정확한 위치를 표시하지 않습니다.
