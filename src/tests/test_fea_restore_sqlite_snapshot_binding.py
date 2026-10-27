"""Bind selected SQLite history row to exact restored CAD+run+case.

Uses genuine on-disk SQLite, actual production AST functions, synthetic solver
file parser only. This does not assert the user's Windows FRD was reverified.
"""
from __future__ import annotations
import ast,copy,hashlib,json,sqlite3,tempfile,threading,unittest
from contextlib import closing
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/'payload'/'GeoField_CAD_Analysis.py'
TREE=ast.parse(SOURCE.read_text(encoding='utf8'))
NAMES={'r172_verify_snapshot_binding','r172_restore'}
SELECTED=[node for node in TREE.body if isinstance(node,ast.FunctionDef) and node.name in NAMES]
assert len(SELECTED)==len(NAMES)
SCOPE={'sqlite3':sqlite3,'json':json,'STATE_LOCK':threading.RLock(),
       'valid_uid':lambda s:isinstance(s,str) and len(s)==32 and all(x in '0123456789abcdef' for x in s)}
exec(compile(ast.fix_missing_locations(ast.Module(body=SELECTED,type_ignores=[])),str(SOURCE),'exec'),SCOPE)
verify=SCOPE['r172_verify_snapshot_binding']
restore=SCOPE['r172_restore']
UID='a'*32
SNAP_1='1'*32
SNAP_2='2'*32
RUN_1='3'*32
RUN_2='4'*32
CAD='c'*64
CASE_1='d'*64
CASE_2='e'*64

class SnapshotBoundRestartTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='geofield-fea-snapshot-same-cad-')
        self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name)
        self.db=self.base/'geofield_review_history.sqlite3'
        self.saved_evidence=self.base/'owned-old-results.frd'
        self.saved_evidence.write_bytes(b'FRD belongs to user - untouched')
        with closing(sqlite3.connect(self.db)) as con,con:
            con.execute('CREATE TABLE snapshots (id TEXT PRIMARY KEY,stage TEXT,job_id TEXT,cad_sha256 TEXT,summary_json TEXT)')
            for sid,rid,case in ((SNAP_1,RUN_1,CASE_1),(SNAP_2,RUN_2,CASE_2)):
                payload={'cad':{'sha256':CAD},'fea':{'state':'complete',
                         'result_run_id':rid,'result_case_sha256':case,
                         'maximum_von_mises_mpa':14.512,
                         'maximum_displacement_mm':0.05698}}
                con.execute('INSERT INTO snapshots VALUES(?,?,?,?,?)',
                            (sid,'fea_result',UID,CAD,json.dumps(payload)))
        SCOPE.update(HISTORY_DB=self.db,JOBS_DIR=self.base,
                     CURRENT={'job_id':None,'pending_job_id':None},
                     JOBS={},FEA_JOBS={},
                     rule_findings=lambda *_args:[])
        self.recover=RUN_1
        self.case=CASE_1
        def restore_files(_dir,uid,run_hint=None):
            self.assertEqual(uid,UID)
            self.assertEqual(run_hint,self.recover)
            # The parsed case is frozen independently from the SQLite row.
            cad={'sha':CAD,'analysis':{'sha256':CAD,'source':'saved.step'},
                 'model':{'sha256':CAD},'case':{'cad_sha256':CAD,'case_sha256':self.case}}
            return cad,self.recover,{'cad_sha256':CAD,'case_sha256':self.case,
                 'results':{'maximum_nodal_von_mises_mpa':14.512,
                            'maximum_displacement_mm':0.05698}},None
        SCOPE['restore_payload']=restore_files

    def assert_untouched(self):
        self.assertEqual(self.saved_evidence.read_bytes(),b'FRD belongs to user - untouched')

    def test_two_calculix_runs_same_cad_restore_the_selected_exact_snapshot(self):
        before=hashlib.sha256(self.db.read_bytes()).digest()
        for snap,run,case in ((SNAP_1,RUN_1,CASE_1),(SNAP_2,RUN_2,CASE_2)):
            self.recover,self.case=run,case
            # As if freshly restarted process had no prior in-memory job.
            SCOPE['CURRENT']={'job_id':None,'pending_job_id':None}
            SCOPE['FEA_JOBS'].clear();SCOPE['JOBS'].clear()
            preview=restore(UID,include_bundle=True,commit=False,
                            run_hint=run,snapshot_hint=snap)
            self.assertEqual(preview['run_id'],run)
            self.assertIsNone(SCOPE['CURRENT']['job_id'])
            self.assertEqual(SCOPE['JOBS'],{})
            result=restore(UID,include_bundle=True,run_hint=run,snapshot_hint=snap)
            self.assertEqual(result['run_id'],run)
            self.assertEqual(SCOPE['CURRENT']['verified_restored_run_id'],run)
            self.assertEqual(SCOPE['CURRENT']['verified_restored_case']['case_sha256'],case)
            self.assertNotIn('original_step',result)
            self.assertTrue(result['read_only_no_original_step'])
        self.assertEqual(before,hashlib.sha256(self.db.read_bytes()).digest())
        moved=self.base/'sqlite-safely-renamed.tmp'
        self.db.rename(moved);moved.rename(self.db) # validates closed SQLite on Windows
        self.assert_untouched()

    def test_same_cad_but_other_run_snapshot_rejected_without_live_state_change(self):
        self.recover,self.case=RUN_2,CASE_2
        initial=copy.deepcopy(SCOPE['CURRENT'])
        with self.assertRaisesRegex(ValueError,'실행·조건'):
            restore(UID,include_bundle=True,run_hint=RUN_2,snapshot_hint=SNAP_1)
        self.assertEqual(SCOPE['CURRENT'],initial)
        self.assertEqual(SCOPE['FEA_JOBS'],{})
        self.assertEqual(SCOPE['JOBS'],{})
        self.assert_untouched()

    def test_corrupt_sqlite_stress_is_rejected_before_live_state_change(self):
        with closing(sqlite3.connect(self.db)) as cn,cn:
            raw=cn.execute('SELECT summary_json FROM snapshots WHERE id=?',(SNAP_1,)).fetchone()[0]
            doc=json.loads(raw);doc['fea']['maximum_von_mises_mpa']=999.0
            cn.execute('UPDATE snapshots SET summary_json=? WHERE id=?',(json.dumps(doc),SNAP_1))
        old=copy.deepcopy(SCOPE['CURRENT'])
        with self.assertRaisesRegex(ValueError,'FRD 계산 수치'):
            restore(UID,include_bundle=True,run_hint=RUN_1,snapshot_hint=SNAP_1)
        self.assertEqual(SCOPE['CURRENT'],old)
        self.assertFalse(SCOPE['JOBS'])
        self.assertFalse(SCOPE['FEA_JOBS'])
        self.assert_untouched()

    def test_corrupt_sqlite_displacement_is_rejected_even_in_preview(self):
        with closing(sqlite3.connect(self.db)) as cn,cn:
            raw=cn.execute('SELECT summary_json FROM snapshots WHERE id=?',(SNAP_1,)).fetchone()[0]
            doc=json.loads(raw);doc['fea']['maximum_displacement_mm']=0.9
            cn.execute('UPDATE snapshots SET summary_json=? WHERE id=?',(json.dumps(doc),SNAP_1))
        with self.assertRaisesRegex(ValueError,'FRD 계산 수치'):
            restore(UID,include_bundle=True,commit=False,run_hint=RUN_1,snapshot_hint=SNAP_1)
        self.assertEqual(SCOPE['CURRENT']['job_id'],None)
        self.assert_untouched()

    def test_non_numeric_and_missing_solver_data_fail_closed(self):
        old=copy.deepcopy(SCOPE['CURRENT'])
        for record_key,bad in [('maximum_von_mises_mpa','NaN'),('maximum_displacement_mm',None)]:
            with self.subTest(key=record_key):
                with closing(sqlite3.connect(self.db)) as cn,cn:
                    raw=cn.execute('SELECT summary_json FROM snapshots WHERE id=?',(SNAP_1,)).fetchone()[0]
                    doc=json.loads(raw);doc['fea'][record_key]=bad
                    cn.execute('UPDATE snapshots SET summary_json=? WHERE id=?',(json.dumps(doc),SNAP_1))
                with self.assertRaisesRegex(ValueError,'FRD 계산 수치'):
                    restore(UID,run_hint=RUN_1,snapshot_hint=SNAP_1)
        self.assertEqual(SCOPE['CURRENT'],old)
        self.assert_untouched()

    def test_old_run_but_new_case_rejected(self):
        self.recover,self.case=RUN_1,CASE_2
        with self.assertRaisesRegex(ValueError,'실행·조건'):
            restore(UID,run_hint=RUN_1,snapshot_hint=SNAP_1)
        self.assertEqual(SCOPE['CURRENT']['job_id'],None)
        self.assert_untouched()

    def test_other_stage_or_cad_id_never_passes_as_solver_history(self):
        with closing(sqlite3.connect(self.db)) as con,con:
            con.execute("UPDATE snapshots SET stage='ml' WHERE id=?",(SNAP_1,))
        with self.assertRaisesRegex(ValueError,'SQLite 기록과 CAD'):
            verify(SNAP_1,UID,RUN_1,CAD,CASE_1)
        with self.assertRaisesRegex(ValueError,'SQLite 기록과 CAD'):
            verify(SNAP_2,'f'*32,RUN_2,CAD,CASE_2)
        self.assert_untouched()

    def test_no_database_is_created_and_existing_data_is_untouched(self):
        self.db.unlink()
        with self.assertRaisesRegex(ValueError,'SQLite FEA 기록'):
            verify(SNAP_1,UID,RUN_1,CAD,CASE_1)
        self.assertFalse(self.db.exists())
        self.assert_untouched()

    def test_invalid_and_unknown_snapshots_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'형식'):
            verify('../wrong',UID,RUN_1,CAD,CASE_1)
        with self.assertRaisesRegex(ValueError,'SQLite 기록과 CAD'):
            verify('9'*32,UID,RUN_1,CAD,CASE_1)
        self.assert_untouched()

if __name__=='__main__':unittest.main()
