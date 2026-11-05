"""Regression for 2026-11-05 real Windows recording of misleading legacy
section 5. No solver, user files, network or paid AI is called here.
"""
import ast
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'payload/GeoField_CAD_Analysis.py'
CAD='a'*64
RUN='1'*32
CASE='b'*64

def load_reconciler():
    tree=ast.parse(SOURCE.read_text(encoding='utf8'))
    wanted={'gf_reconcile_legacy_report_status','gf_verified_analysis_report_ready'}
    nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in wanted]
    assert {node.name for node in nodes}==wanted
    scope={}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),scope)
    return scope['gf_reconcile_legacy_report_status']

def verified_summary(ml='complete',r12='complete'):
    return {
        'cad':{'sha256':CAD},
        'fea':{'state':'complete','result_run_id':RUN,
               'result_case_sha256':CASE,
               'maximum_von_mises_mpa':30.277820017318223,
               'maximum_displacement_mm':.055235104783024284,
               'node_count':7303,'tetrahedron_count':26079},
        'fea_case_provenance':{
            'source_verification':'INP_STA_FRD_reverified',
            'summary_numbers_crosschecked':True,
            'verified_run_id':RUN,'solved_case_sha256':CASE,
            'verified_mesh':{'nodes':7303,'tetrahedra':26079}},
        'ml':{'state':ml},
        'r12_research_status':{'state':r12,'cad_sha256':CAD,
                               'mode':'research_only'}}

OLD_HTML=(
 '<!doctype html><html><body>'
 '<h2>5. 미연결 기능 및 제한</h2>'
 '<p>STEPFeatureNet 학습 ML: 미실행 · GeoField Stage B: 미연결 · '
 'AI Agent: 규칙 기반 분석 완료 (외부 AI 참고 설명은 별도 부록 확인)</p>'
 '<ul><li>홀 후보는 관통홀 여부 및 위험 판정이 아닙니다.</li>'
 '<li>BrepMFR 예측은 새 CAD에서 정확도 미검증이며 CAD 면과 모델 면 정합이 보장되지 않습니다.</li>'
 '<li>FEA가 실행되지 않았다면 응력과 변위 수치가 존재하지 않습니다.</li>'
 '<li>FEA가 완료되더라도 메시 수렴·응력 특이점·구조 안전성은 별도 검증해야 합니다.</li>'
 '</ul><p>생성 시각 2026-11-05</p>'
 '<section id="real-solver-evidence">30.277820017318223 MPa / '
 '0.055235104783024284 mm · INP STA FRD</section>'
 '</body></html>')

class LegacyReportStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.convert=staticmethod(load_reconciler())

    def test_actual_video_stale_status_replaced_but_engineering_uncertainty_kept(self):
        result=self.convert(OLD_HTML,verified_summary(),include_ai=False)
        self.assertIn('5. 이번 분석 상태와 확인 제한',result)
        self.assertNotIn('5. 미연결 기능 및 제한',result)
        self.assertNotIn('STEPFeatureNet 학습 ML: 미실행',result)
        self.assertNotIn('GeoField Stage B: 미연결',result)
        self.assertNotIn('AI Agent: 규칙 기반 분석 완료',result)
        self.assertNotIn('보고서 AI:',result)
        self.assertIn('기존 ML 연구 작업: 완료',result)
        self.assertIn('R12 연구 추론: 완료',result)
        self.assertIn('실제 CalculiX INP·STA·FRD 원본 교차검증 완료',result)
        self.assertIn('이번 기본 FEA는 실제 실행 및 수치 재검증 완료',result)
        self.assertIn('메시 수렴·응력 특이점·구조 안전성은 별도 검증해야 합니다',result)
        self.assertIn('30.277820017318223 MPa / 0.055235104783024284 mm',result)
        self.assertIn('생성 시각 2026-11-05',result)

    def test_no_stale_status_when_research_not_run_or_cad_does_not_match(self):
        state=verified_summary(ml='not_run',r12='complete')
        state['r12_research_status']['cad_sha256']='b'*64
        result=self.convert(OLD_HTML,state)
        self.assertIn('기존 ML 연구 작업: 이번 CAD 실행 기록 없음',result)
        self.assertIn('R12 연구 추론: 기록 없음',result)
        self.assertNotIn('R12 연구 추론: 완료',result)

    def test_ai_on_shows_only_requested_state_not_success_without_reply(self):
        result=self.convert(OLD_HTML,verified_summary(),include_ai=True)
        self.assertIn('보고서 AI: 이번 실행의 규칙 기반 분석 요청',result)
        self.assertNotIn('외부 AI 성공',result)

    def test_unverified_input_cannot_upgrade_old_status(self):
        state=verified_summary()
        state['fea_case_provenance']['summary_numbers_crosschecked']=False
        with self.assertRaisesRegex(ValueError,'FEA 원본 검증'):
            self.convert(OLD_HTML,state)

    def test_existing_modern_report_not_edited(self):
        modern='<html><body><h2>5. 현재 실행 결과</h2><p>임의 보고서 본문</p></body></html>'
        self.assertEqual(self.convert(modern,verified_summary()),modern)

    def test_untrusted_ml_state_cannot_be_injected_into_html(self):
        state=verified_summary(ml='<script>alert(1)</script>')
        result=self.convert(OLD_HTML,state)
        self.assertNotIn('<script>',result)
        self.assertIn('상태 확인 필요',result)

    def test_source_report_preview_and_immutable_save_both_use_same_reconciliation(self):
        src=SOURCE.read_text(encoding='utf8')
        self.assertIn('report=gf_reconcile_legacy_report_status(report,summary,include_ai=include_ai)',src)
        self.assertIn('value=gf_current_verified_report(uid,as_html=html_requested,include_ai=include_ai)',src)
        self.assertIn('data=gf_current_verified_report(uid,as_html=True)',src)

if __name__=='__main__':
    unittest.main()
