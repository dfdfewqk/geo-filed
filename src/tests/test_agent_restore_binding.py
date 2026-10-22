"""Stage 7: restored historical FEA must bind exact CAD, case, run and provenance.

Exercises ACTUAL production agent functions with synthetic values; no solver,
historical SQLite, STEP, FRD, or user file is opened.
"""
import ast
import copy
from pathlib import Path
import unittest
from test_agent_evidence import record,agent,CAD,CASE,RUN,JOB

SOURCE=Path(__file__).resolve().parents[1]/'payload'/'GeoField_CAD_Analysis.py'
source=SOURCE.read_text(encoding='utf-8')
tree=ast.parse(source)
wanted={'gf_agent_restored_context','gf_agent_assert_restore_session'}
functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in wanted]
assert len(functions)==2,'Actual restored-session agent gates missing'
env={}
exec(compile(ast.Module(body=functions,type_ignores=[]),str(SOURCE),'exec'),env)
context=env['gf_agent_restored_context']
assert_current=env['gf_agent_assert_restore_session']

def sample():
    summary,decision,ml,r12,task=record()
    task['restored_after_restart']=True
    result=agent(summary,decision,ml,r12,task)
    job={'id':JOB,'sha256':CAD,'restored_without_original_step':True}
    case={'cad_sha256':CAD,'case_sha256':CASE}
    proof=copy.deepcopy(summary['fea_case_provenance'])
    proof.update(restored_record_active=True)
    session={'job_id':JOB,'pending_job_id':JOB,
             'verified_restored_run_id':RUN,'verified_restored_case':dict(case)}
    return session,job,task,case,proof,result

class RestoredAgentProvenance(unittest.TestCase):
    def test_real_run_restore_is_read_only_and_never_restores_ml_implicitly(self):
        args=sample();before=copy.deepcopy(args)
        res=context(*args)
        self.assertEqual(args,before)
        self.assertEqual(res['status'],'verified_restored_read_only')
        self.assertTrue(res['read_only'])
        self.assertFalse(res['ml_history_restored'])
        self.assertEqual(res['run_id'],RUN)
        self.assertEqual(res['case_sha256'],CASE)
        self.assertIn('신규 계산이 아니며',res['note'])
    def test_non_restored_session_is_not_claimed_historical(self):
        args=list(sample());args[0].pop('verified_restored_run_id')
        res=context(*args)
        self.assertEqual(res['status'],'not_restored')
        self.assertFalse(res['read_only'])
        self.assertIsNone(res['run_id'])
    def test_different_run_same_cad_rejected(self):
        args=list(sample());args[0]['verified_restored_run_id']='9'*32
        result=context(*args)
        self.assertEqual(result['status'],'restore_evidence_not_verified')
        self.assertIsNone(result['run_id'])
    def test_different_case_same_cad_rejected(self):
        args=list(sample());args[0]['verified_restored_case']['case_sha256']='f'*64
        self.assertEqual(context(*args)['status'],'restore_evidence_not_verified')
    def test_wrong_case_in_result_rejected(self):
        args=list(sample());args[5]['fea']['case_sha256']='d'*64
        self.assertEqual(context(*args)['status'],'restore_evidence_not_verified')
    def test_wrong_cad_job_rejected(self):
        args=list(sample());args[2]['cad_job_id']='9'*32
        self.assertEqual(context(*args)['status'],'restore_evidence_not_verified')
    def test_no_restored_task_evidence_rejected(self):
        args=list(sample());args[2].pop('restored_after_restart')
        self.assertEqual(context(*args)['status'],'restore_evidence_not_verified')
    def test_saved_editable_case_can_differ_without_relabeling_run(self):
        args=list(sample());args[4]['result_matches_saved']=False
        self.assertEqual(context(*args)['status'],'verified_restored_read_only')
    def test_provenance_failed_rejects_run(self):
        for attr,val in [('source_verification','unknown'),
                         ('summary_numbers_crosschecked',False),
                         ('verified_run_id','9'*32),
                         ('solved_case_sha256','d'*64),
                         ('restored_record_active',False),
                         ('result_matches_selected',False)]:
            with self.subTest(attr=attr):
                args=list(sample());args[4][attr]=val
                self.assertEqual(context(*args)['status'],'restore_evidence_not_verified')
    def test_other_historical_run_same_cad_rejected_before_output(self):
        old=sample()[0]
        new=copy.deepcopy(old);new['verified_restored_run_id']='8'*32
        with self.assertRaisesRegex(ValueError,'복원 실행'):
            assert_current(old,new)
    def test_case_change_same_run_rejected_before_output(self):
        old=sample()[0]
        new=copy.deepcopy(old);new['verified_restored_case']['case_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'계산 조건'):
            assert_current(old,new)
    def test_same_session_does_not_error(self):
        old=sample()[0]
        assert_current(old,copy.deepcopy(old))
    def test_cad_or_pending_import_change_is_blocked(self):
        old=sample()[0]
        for change in ({'job_id':'9'*32},{'pending_job_id':'9'*32}):
            updated=dict(old,**change)
            with self.assertRaisesRegex(ValueError,'변경'):
                assert_current(old,updated)
    def test_endpoint_uses_guard_both_before_and_after_optional_llm(self):
        self.assertIn("response['restore_evidence']=gf_agent_restored_context(",source)
        self.assertIn("if response['restore_evidence']['status']=='restore_evidence_not_verified':",source)
        self.assertGreaterEqual(source.count('gf_agent_assert_restore_session(session,current_session)'),2)

if __name__=='__main__':unittest.main()
