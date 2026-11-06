"""Stage 4: bind a real 3-mesh study only to its own verified base FEA run.

Execute the actual production read-only base-run gate with isolated fake
INP/STA/FRD verifier, without running Gmsh, CalculiX, SQLite or modifying data.
"""
import ast
import copy
import re
import threading
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SERVER=(ROOT/'payload/GeoField_CAD_Analysis.py').read_text(encoding='utf8')
MESH=(ROOT/'fea_mesh_series.py').read_text(encoding='utf8')
UID='a'*32
SHA='b'*64
CASE='c'*64
RUN='d'*32
OLD='e'*32

fn=next(x for x in ast.parse(SERVER).body if isinstance(x,ast.FunctionDef)
        and x.name=='gf_stage4_verified_base_run')
valid_uid=lambda x:isinstance(x,str) and re.fullmatch(r'[a-f0-9]{32}',x) is not None

def base_task(run=RUN,case_sha=CASE,status='complete'):
    return {'id':run,'status':status,'cad_job_id':UID,'cad_sha256':SHA,
            'case_sha256':case_sha}

def make_env():
    jobs={UID:{'id':UID,'status':'complete','sha256':SHA}}
    tasks={RUN:base_task()}
    session={'job_id':UID}
    calls=[]
    def verified(t,uid,sha,case,_dir):
        calls.append(('INP_STA_FRD',t['id']))
        return {'status':'complete','id':t['id'],'cad_job_id':uid,
                'cad_sha256':sha,'case_sha256':case['case_sha256'],
                'source_validation':'INP_STA_FRD_reverified'}
    def active(uid,sha,run,case):
        calls.append(('active',run))
        if session.get('job_id')!=uid:
            raise ValueError('CAD changed')
        if list(tasks)[-1]!=run and session.get('verified_restored_run_id')!=run:
            raise ValueError('newer FEA exists')
        return True
    env={'STATE_LOCK':threading.RLock(),'CURRENT':session,'JOBS':jobs,
         'FEA_JOBS':tasks,'JOBS_DIR':Path('/isolated_mock'),
         'valid_uid':valid_uid,
         'qa8_verified_completed_fea_status':verified,
         'qa_report_active_run_unchanged':active}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<production exact FEA gate>','exec'),env)
    return env,tasks,session,calls

class SameBaseSourceTests(unittest.TestCase):
    def test_selected_completed_inp_sta_frd_run_is_reused(self):
        env,tasks,session,calls=make_env()
        self.assertEqual(env['gf_stage4_verified_base_run'](UID,SHA,{'case_sha256':CASE}),RUN)
        self.assertEqual(calls,[('INP_STA_FRD',RUN),('active',RUN)])

    def test_wrong_case_sha_and_newer_active_run_rejected(self):
        env,tasks,session,calls=make_env()
        with self.assertRaises(ValueError):
            env['gf_stage4_verified_base_run'](UID,SHA,{'case_sha256':'f'*64})
        tasks[OLD]=base_task(run=OLD,case_sha='f'*64)
        with self.assertRaises(ValueError):
            env['gf_stage4_verified_base_run'](UID,SHA,{'case_sha256':CASE})
        session['verified_restored_run_id']=RUN
        self.assertEqual(env['gf_stage4_verified_base_run'](UID,SHA,{'case_sha256':CASE}),RUN)

    def test_pending_or_different_cad_never_accepted(self):
        env,tasks,session,_=make_env()
        tasks[RUN]['status']='running'
        with self.assertRaises(ValueError):
            env['gf_stage4_verified_base_run'](UID,SHA,{'case_sha256':CASE})
        tasks[RUN]['status']='complete'
        session['job_id']='f'*32
        with self.assertRaises(ValueError):
            env['gf_stage4_verified_base_run'](UID,SHA,{'case_sha256':CASE})

    def test_source_verifier_cannot_be_bypassed(self):
        env,tasks,session,calls=make_env()
        env['qa8_verified_completed_fea_status']=lambda *args:{
            'status':'complete','id':RUN,'cad_job_id':UID,'cad_sha256':SHA,
            'case_sha256':CASE,'source_validation':'not_verified'}
        with self.assertRaises(ValueError):
            env['gf_stage4_verified_base_run'](UID,SHA,{'case_sha256':CASE})
        self.assertEqual(calls,[])

    def test_explicit_study_run_and_case_persist_in_public_manifest(self):
        tree=ast.parse(MESH)
        fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef)
                and x.name=='start_series')
        self.assertIn('base_run_id',fn.args.kwonlyargs[0].arg)
        snippet=ast.get_source_segment(MESH,fn)
        self.assertIn("'base_run_id':base_run_id",snippet)
        self.assertIn("'base_case_sha256':case['case_sha256']",snippet)
        self.assertIn("atomic_json(folder/'manifest.json',public_state(study))",snippet)
        self.assertIn("'base_run_id','base_case_sha256'",MESH)

    def test_server_and_frontend_verify_exact_link_without_second_solver(self):
        js=(ROOT/'payload/frontend/cad.js').read_text(encoding='utf8')
        self.assertIn("'X-GeoField-Base-FEA-Run':meshSeriesBaseRun",js)
        self.assertIn('meshSeriesBaseRun=meshSeriesPlan.base_run_id',js)
        self.assertIn('state.base_fea_binding_verified===true',js)
        self.assertIn('state?.base_fea_binding_verified!==true',js)
        self.assertIn('verified.base_fea_binding_verified!==true',js)
        self.assertIn('plan.base_run_id!==run',js)
        self.assertIn("gf_stage4_verified_base_run(uid,job['sha256'],case)",SERVER)
        self.assertIn('base_run_id=base_run)',SERVER)
        self.assertIn("output['base_fea_binding_verified']=False",SERVER)
        self.assertIn("output['base_fea_binding_verified']=(",SERVER)
        self.assertIn("qa8_verified_completed_fea_status(task,uid,cad_sha,case,JOBS_DIR)",SERVER)

    def test_gate_does_not_modify_input_or_run_paid_or_solver_tools(self):
        env,tasks,session,_=make_env()
        before=copy.deepcopy((tasks,session))
        env['gf_stage4_verified_base_run'](UID,SHA,{'case_sha256':CASE})
        self.assertEqual((tasks,session),before)
        source=ast.get_source_segment(SERVER,fn)
        for forbidden in ('launch_automatic_ml','gf_agent_llm_optional',
                          'execute_fea(', 'run_real_fea(', 'subprocess.',
                          'sqlite3.', 'write_text(', 'unlink('):
            self.assertNotIn(forbidden,source)

if __name__=='__main__':unittest.main()
