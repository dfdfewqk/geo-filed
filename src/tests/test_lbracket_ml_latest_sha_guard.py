"""L-bracket integration: production latest-ML API cannot bypass SHA/face validation.

Only run actual extracted production validation functions. No private model,
OCP, STEP, FEA, SQLite, Windows install or paid external AI is required.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
from pathlib import Path
import re
import unittest

SERVER=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
TREE=ast.parse(SERVER.read_text(encoding="utf-8"),filename=str(SERVER))
FUNCS={n.name:n for n in TREE.body if isinstance(n,ast.FunctionDef)}
JOB="a"*32
RID="b"*32
CAD_SHA=hashlib.sha256(b"L-bracket checked model").hexdigest()


def sample():
    return {"schema":"legacy-brepml-research",
            "sha256":CAD_SHA,"decision_usage":"blocked_diagnostic_only",
            "viewer_face_mapping_verified":False,
            "trained_architecture_equivalence":"not_proven",
            "variants":{"topology_trimmed":{"faces":[
                {"face_ordinal":1,"model_score_uncalibrated":.37,
                 "model_class":"blind_hole","geometry_surface":"CYLINDER"}]}}}


class BrepMFRLatestSourceGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        code=compile(ast.Module(body=[
            FUNCS["qa_validate_brepmfr_diagnostic"],
            FUNCS["qa_latest_brepmfr_task"]],
            type_ignores=[]),str(SERVER),"exec")
        ns={"valid_uid":lambda s:bool(re.fullmatch(r"[0-9a-f]{32}",s))}
        exec(code,ns)
        cls.guard=staticmethod(ns["qa_latest_brepmfr_task"])

    @staticmethod
    def task(**values):
        return {"id":RID,"cad_job_id":JOB,"cad_sha256":CAD_SHA,
                "status":"complete","result":sample(),**values}

    def test_valid_original_is_unchanged_and_survives_read(self):
        task=self.task()
        old=deepcopy(task)
        checked=self.guard(task,JOB,CAD_SHA)
        self.assertEqual(checked,old)
        self.assertEqual(task,old)
        self.assertIsNot(checked,task)

    def test_wrong_sha_and_cross_cad_run_never_return_prediction(self):
        for change in ({"cad_sha256":"c"*64},{"cad_job_id":"c"*32},
                       {"id":"invalid"},{"id":None}):
            with self.subTest(change=change):
                task=self.task()
                task.update(change)
                with self.assertRaises(ValueError):
                    self.guard(task,JOB,CAD_SHA)
        with self.assertRaises(ValueError):
            self.guard(self.task(),JOB,"d"*64)

    def test_tampered_diagnostic_result_must_be_rejected_and_not_exposed(self):
        variations=[
            ("sha256","c"*64),("decision_usage","production"),
            ("viewer_face_mapping_verified",True),
            ("trained_architecture_equivalence","verified"),
        ]
        for field,value in variations:
            with self.subTest(field=field):
                task=self.task()
                task["result"][field]=value
                checked=self.guard(task,JOB,CAD_SHA)
                self.assertEqual(checked["status"],"evidence_rejected")
                self.assertNotIn("result",checked)
                self.assertEqual(task["result"][field],value,
                                 "Do not modify the archived worker output")
        for wrong in (float("nan"),-0.2,1.4):
            task=self.task()
            task["result"]["variants"]["topology_trimmed"]["faces"][0][
                "model_score_uncalibrated"]=wrong
            self.assertEqual(self.guard(task,JOB,CAD_SHA)["status"],
                             "evidence_rejected")
        for bad_faces in ([{"face_ordinal":1,"model_score_uncalibrated":.5,
                            "geometry_surface":"CYLINDER","model_class":"blind_hole"}]*2,
                          [],
                          "invalid"):
            task=self.task()
            task["result"]["variants"]["topology_trimmed"]["faces"]=bad_faces
            checked=self.guard(task,JOB,CAD_SHA)
            # Empty legitimate face list is an abstaining ML observation.
            self.assertEqual(checked["status"],
                "complete" if bad_faces==[] else "evidence_rejected")

    def test_failed_or_pending_task_never_leaks_stale_result(self):
        for status in ("failed","queued","running","r12_fallback"):
            task=self.task();task["status"]=status
            checked=self.guard(task,JOB,CAD_SHA)
            self.assertEqual(checked["status"],status)
            self.assertNotIn("result",checked)
            self.assertIn("result",task)

    def test_latest_http_route_cannot_return_raw_ml_task(self):
        handler=next(n for n in TREE.body if isinstance(n,ast.ClassDef)
                     and n.name=="Handler")
        do_get=next(n for n in handler.body if isinstance(n,ast.FunctionDef)
                    and n.name=="do_GET")
        source=ast.unparse(do_get)
        start=source.index("if path.startswith('/api/ml/latest/'):")
        end=source.index("if path.startswith('/api/ml/r12/latest/'):",start)
        route=source[start:end]
        self.assertIn("qa_latest_brepmfr_task(tasks[-1], uid, job['sha256'])",route)
        self.assertIn("v.get('cad_sha256') == job['sha256']",route)
        self.assertIn("job.get('status') != 'complete'",route)
        self.assertIn("CURRENT.get('job_id') != uid",route)
        self.assertIn("JOBS.get(uid, {}).get('sha256') != job['sha256']",route)
        self.assertNotIn("self.send_raw(tasks[-1])",route)


if __name__=="__main__":
    unittest.main(verbosity=2)
