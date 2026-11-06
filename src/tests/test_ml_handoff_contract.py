"""Stage 2: execute the production read-only ML handoff with the real
BrepMFR/R12 JSON validators, not a synthetic reimplementation.

No ML training, solver, paid request, STEP/FRD write, or user SQLite access.
"""
import ast
import copy
import math
import re
import types
import unittest
from pathlib import Path


PAYLOAD = Path(__file__).resolve().parents[1] / 'payload'
SERVER_TEXT = (PAYLOAD / 'GeoField_CAD_Analysis.py').read_text(encoding='utf-8')
R12_TEXT = (PAYLOAD / 'ml_r12_bridge.py').read_text(encoding='utf-8')
UID = 'a' * 32
SHA = 'b' * 64
BRUN = 'c' * 32
RRUN = 'd' * 32


def load_functions(source, names, env):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in nodes} != set(names):
        raise AssertionError('production ML validators or handoff function missing')
    namespace = dict(env)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<production ml contract>', 'exec'), namespace)
    return namespace


r12 = load_functions(R12_TEXT, {'validate_research_result'}, {'math': math})
production = load_functions(
    SERVER_TEXT,
    {'qa_validate_brepmfr_diagnostic', 'qa_latest_brepmfr_task', 'gf_ml_handoff_snapshot'},
    {'valid_uid': lambda x: isinstance(x, str) and re.fullmatch('[0-9a-f]{32}', x) is not None,
     'ml_r12_bridge': types.SimpleNamespace(validate_research_result=r12['validate_research_result'])})
snapshot = production['gf_ml_handoff_snapshot']


def job(enabled=True):
    return {'id': UID, 'sha256': SHA, 'status': 'complete', 'auto_ml_enabled': enabled,
            'auto_ml_status': 'not_run', 'auto_r12_status': 'not_run'}


def brep(faces=None):
    if faces is None:
        faces = [{'face_ordinal': 0, 'geometry_surface': 'Cylinder',
                  'model_class': 'hole_like', 'model_score_uncalibrated': .86}]
    return {'id': BRUN, 'cad_job_id': UID, 'cad_sha256': SHA,
            'status': 'complete', 'automatic': True,
            'result': {'sha256': SHA, 'decision_usage': 'blocked_diagnostic_only',
                       'trained_architecture_equivalence': 'not_proven',
                       'viewer_face_mapping_verified': False,
                       'variants': {'topology_trimmed': {'faces': faces}}}}


def r12_task(predictions=None):
    if predictions is None:
        predictions = [{'face_index': 1, 'raw_ml_top_class': 'through_hole',
                        'predicted_hole_type': 'through_hole', 'raw_ml_thresholded': 'through_hole',
                        'topology_evidence': 'through_hole',
                        'decision_basis': 'model_and_brep_topology_agree',
                        'uncalibrated_model_score': .9,
                        'status': 'research_unverified'}]
    return {'id': RRUN, 'cad_job_id': UID, 'cad_sha256': SHA,
            'status': 'complete', 'automatic': True,
            'result': {'cad_sha256': SHA, 'decision_usage': 'blocked_diagnostic_only',
                       'status': 'research_not_for_production', 'fea_calculated': False,
                       'geometry_certified': False, 'is_independent_r12_research': True,
                       'candidate_count': len(predictions), 'predictions': predictions}}


def r12_verified(run=RRUN, count=1):
    return {'state': 'complete', 'mode': 'research_only', 'cad_sha256': SHA,
            'run_id': run, 'candidate_count': count, 'fea_calculated': False}


class MlStage2HandoffTests(unittest.TestCase):
    def test_both_real_validators_keep_predictions_uncertain(self):
        output = snapshot(UID, SHA, job(), brep(), r12_task(), r12_verified())
        self.assertEqual(output['schema'], 'geofield-ml-handoff-v1')
        self.assertEqual(output['status'], 'research_available_with_limits')
        self.assertEqual({x['model'] for x in output['resolved']}, {'brepmfr', 'r12'})
        self.assertEqual({x['model'] for x in output['uncertain']}, {'brepmfr', 'r12'})
        self.assertEqual(output['failed'], [])
        self.assertEqual(output['unavailable'], [])
        self.assertEqual(output['models']['brepmfr']['run_id'], BRUN)
        self.assertEqual(output['models']['r12']['run_id'], RRUN)
        self.assertFalse(output['structural_authority'])
        self.assertFalse(output['face_mapping_verified'])
        self.assertFalse(output['fea_calculated'])
        self.assertEqual(output['uncertain'][1]['samples'][0]['decision_basis'],
                         'model_and_brep_topology_agree')

    def test_ml_failure_does_not_cancel_valid_independent_r12(self):
        bad = brep()
        bad.update(status='failed', message='worker environment failure')
        bad.pop('result')
        output = snapshot(UID, SHA, job(), bad, r12_task(), r12_verified())
        self.assertEqual([x['model'] for x in output['resolved']], ['r12'])
        self.assertEqual(output['models']['brepmfr']['status'], 'failed')

    def test_r12_failure_does_not_cancel_valid_brepmfr(self):
        bad = r12_task()
        bad.update(status='failed', message='sklearn unavailable')
        bad.pop('result')
        output = snapshot(UID, SHA, job(), brep(), bad, {'state': 'failed'})
        self.assertEqual([x['model'] for x in output['resolved']], ['brepmfr'])
        self.assertEqual(output['models']['r12']['status'], 'failed')

    def test_unavailable_or_opt_out_never_claims_inference(self):
        unavailable = job()
        unavailable.update(auto_ml_status='r12_fallback', auto_r12_status='unavailable')
        output = snapshot(UID, SHA, unavailable)
        self.assertFalse(output['resolved'])
        self.assertEqual(output['status'], 'research_unavailable')
        self.assertEqual(output['models']['brepmfr']['status'], 'r12_fallback')
        self.assertEqual(output['models']['r12']['status'], 'unavailable')
        off = snapshot(UID, SHA, job(False))
        self.assertEqual([x['status'] for x in off['unavailable']],
                         ['disabled_by_user', 'disabled_by_user'])
        self.assertFalse(off['resolved'])

    def test_pending_not_faked_as_success(self):
        queued = job()
        queued.update(auto_ml_status='queued', auto_r12_status='running')
        result = snapshot(UID, SHA, queued)
        self.assertEqual(result['status'], 'awaiting_research')
        self.assertEqual(len(result['pending']), 2)
        self.assertFalse(result['uncertain'])
        just_uploaded = job()
        just_uploaded['auto_ml_status'] = 'pending'
        initial = snapshot(UID, SHA, just_uploaded)
        self.assertEqual(initial['models']['brepmfr']['status'], 'pending')
        self.assertEqual(initial['status'], 'awaiting_research')

    def test_wrong_job_or_sha_rejects_entire_requested_handoff(self):
        for bad_job in ({**job(), 'id': 'f' * 32},
                        {**job(), 'sha256': 'f' * 64},
                        {**job(), 'status': 'running'}):
            with self.assertRaises(ValueError):
                snapshot(UID, SHA, bad_job)
        with self.assertRaises(ValueError):
            snapshot(UID, 'not-a-sha', job())

    def test_stale_brepmfr_id_or_result_sha_not_promoted(self):
        for change in (
            lambda t: t.update(cad_sha256='e' * 64),
            lambda t: t.update(id='invalid'),
            lambda t: t['result'].update(sha256='e' * 64),
            lambda t: t['result'].update(viewer_face_mapping_verified=True),
            lambda t: t['result']['variants']['topology_trimmed']['faces'].append(
                copy.deepcopy(t['result']['variants']['topology_trimmed']['faces'][0])),
        ):
            item = brep()
            change(item)
            output = snapshot(UID, SHA, job(), item)
            self.assertFalse(output['resolved'])
            self.assertEqual(output['models']['brepmfr']['status'], 'evidence_rejected')

    def test_r12_run_mismatch_or_corrupted_topology_rejected(self):
        for proof in (r12_verified('e' * 32), {**r12_verified(), 'cad_sha256': 'e' * 64},
                      {**r12_verified(), 'fea_calculated': True}):
            result = snapshot(UID, SHA, job(), None, r12_task(), proof)
            self.assertFalse(result['resolved'])
            self.assertEqual(result['models']['r12']['status'], 'evidence_rejected')
        task = r12_task()
        task['result']['predictions'][0]['decision_basis'] = 'model_topology_conflict'
        result = snapshot(UID, SHA, job(), None, task, r12_verified())
        self.assertEqual(result['models']['r12']['status'], 'evidence_rejected')

    def test_zero_model_candidates_do_not_prove_zero_real_holes(self):
        output = snapshot(UID, SHA, job(), brep([]), r12_task([]), r12_verified(count=0))
        self.assertEqual(len(output['uncertain']), 2)
        self.assertEqual([x['candidate_count'] for x in output['resolved']], [0, 0])
        self.assertFalse(output['face_mapping_verified'])

    def test_bounded_samples_while_count_is_preserved(self):
        faces = [{'face_ordinal': i, 'geometry_surface': 'Plane',
                  'model_class': 'other', 'model_score_uncalibrated': .5}
                 for i in range(30)]
        output = snapshot(UID, SHA, job(), brep(faces))
        self.assertEqual(output['models']['brepmfr']['candidate_count'], 30)
        self.assertEqual(len(output['uncertain'][0]['samples']), 12)

    def test_pure_read_only_and_no_paid_or_solver_dependency(self):
        inputs = [job(), brep(), r12_task(), r12_verified()]
        originals = copy.deepcopy(inputs)
        snapshot(UID, SHA, *inputs)
        self.assertEqual(inputs, originals)
        node = next(n for n in ast.parse(SERVER_TEXT).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'gf_ml_handoff_snapshot')
        source = ast.get_source_segment(SERVER_TEXT, node)
        for prohibited in ('requests.post(', 'subprocess.', 'gf_agent_llm_optional(',
                           'sqlite3.', 'launch_automatic_ml(', 'launch_automatic_r12(',
                           'gf_agent_evaluate(', 'fea_solver'):
            self.assertNotIn(prohibited, source)

    def test_existing_import_starts_both_models_without_extra_button(self):
        js = (PAYLOAD / 'frontend/cad.js').read_text(encoding='utf-8')
        self.assertIn('launch_automatic_r12(job,file_path)', SERVER_TEXT)
        self.assertIn('launch_automatic_ml(job,file_path)', SERVER_TEXT)
        self.assertIn('void watchAutoR12(jobId,current.sha256,autoMlGeneration)', js)
        self.assertIn('void watchAutoMl(jobId,current.sha256,autoMlGeneration,automaticMlForImport)', js)
        self.assertIn("if path.startswith('/api/ml/handoff/'):", SERVER_TEXT)
        self.assertIn('gf_ml_handoff_snapshot(', SERVER_TEXT)
        self.assertIn("CURRENT.get('job_id')!=uid", SERVER_TEXT)


if __name__ == '__main__':
    unittest.main()
