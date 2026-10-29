"""L-bracket P1: failed real-INP/STA/FRD recheck never leaks stale FEA flags.

Exercise actual source trust gate with disposable fixtures; NEVER assert that
dummy INP/STA/FRD or fake verifier is a real CalculiX solution.
"""
from __future__ import annotations
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"fea_result_trust_gate.py"
SPEC=importlib.util.spec_from_file_location("geofield_fea_result_trust_gate_test",SOURCE)
gate=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

JOB="a"*32
RUN="b"*32
CAD="c"*64
CASE="d"*64


def sample_task():
    return {
        "id":RUN,"cad_job_id":JOB,"cad_sha256":CAD,
        "case_sha256":CASE,"status":"complete",
        "source_validation":"INP_STA_FRD_reverified",
        "field_visualization":{"available":True},
        "surface_field":{"stress_units":"MPa"},
        "field":{"untrusted_3d":True},
        "result":{"results":{"maximum_nodal_von_mises_mpa":44.0,
                              "maximum_displacement_mm":0.1}},
        "history_archive_status":"saved"
    }


class P1SourceReadOnlyRegression(unittest.TestCase):
    def test_mismatched_lbracket_source_revokes_prior_markers(self):
        original=sample_task()
        prior=copy.deepcopy(original)
        with tempfile.TemporaryDirectory() as directory:
            checked=gate.reverify_task_for_display(
                original,{"cad_sha256":CAD,"case_sha256":"e"*64},
                CAD,directory)
        self.assertEqual(checked["status"],"failed")
        for name in ("result","field","surface_field","field_visualization",
                     "source_validation"):
            self.assertNotIn(name,checked,
                "No old FEA values/3D availability can survive failed read")
        self.assertEqual(original,prior,"Original run/SQLite evidence must not be changed")
        self.assertEqual(checked["id"],RUN)
        self.assertEqual(checked["history_archive_status"],"saved",
                         "Must not forge or delete independent archive status")

    def test_absent_real_frd_revokes_flags_even_when_task_says_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            checked=gate.reverify_task_for_display(
                sample_task(),{"cad_sha256":CAD,"case_sha256":CASE},
                CAD,directory)
        self.assertEqual(checked["status"],"failed")
        self.assertNotIn("source_validation",checked)
        self.assertNotIn("field_visualization",checked)
        self.assertNotIn("result",checked)

    def test_pending_or_failed_run_does_not_keep_old_fea_claims(self):
        for state in ("queued","running","failed"):
            with self.subTest(state=state):
                t=sample_task();t["status"]=state
                before=copy.deepcopy(t)
                with tempfile.TemporaryDirectory() as directory:
                    checked=gate.reverify_task_for_display(
                        t,{"cad_sha256":CAD,"case_sha256":CASE},CAD,directory)
                for name in ("result","field","surface_field","field_visualization",
                             "source_validation"):
                    self.assertNotIn(name,checked)
                self.assertEqual(t,before)
                self.assertEqual(checked["status"],state)

    def test_synthetic_positive_contract_only_with_explicit_verifier(self):
        # These fixture bytes are not an actual FEA run; this checks only
        # task identity/control flow after an external trusted verifier returns.
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/"fea_runs"/RUN
            folder.mkdir(parents=True)
            for name in ("case.json","result.json","geofield_case.inp",
                         "geofield_case.frd","geofield_case.sta"):
                (folder/name).write_text("SYNTHETIC PLACEHOLDER; NOT SOLVER OUTPUT")
            counted=[]
            def verifier(path,case,sha):
                counted.append((path,case,sha))
                return {
                    "schema":"geofield-fea-result-v1",
                    "status":"solver_executed_result_parsed",
                    "cad_sha256":CAD,"case_sha256":CASE,
                    "mesh":{"node_count":100,"tetrahedron_count":50},
                    "results":{"parsed_nodes":100,
                               "maximum_nodal_von_mises_mpa":12.0,
                               "maximum_displacement_mm":0.02}
                }, {"synthetic_only":True}
            task=sample_task()
            out=gate.reverify_task_for_display(
                task,{"cad_sha256":CAD,"case_sha256":CASE},
                CAD,root,verifier=verifier)
            self.assertEqual(out["status"],"complete")
            self.assertEqual(out["source_validation"],"INP_STA_FRD_reverified")
            self.assertEqual(out["result"]["results"]["maximum_nodal_von_mises_mpa"],12.0)
            self.assertEqual(len(counted),1)
            self.assertEqual(task["result"]["results"]["maximum_nodal_von_mises_mpa"],44.0)


if __name__=="__main__":
    unittest.main(verbosity=2)
