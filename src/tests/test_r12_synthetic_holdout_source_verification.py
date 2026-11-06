# -*- coding: utf-8 -*-
"""Recompute the shipped R12 synthetic family holdout from its real signed
research records; mutations must be rejected. Never train, FEA or call AI."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PAYLOAD = Path(__file__).resolve().parents[1] / 'payload'
sys.path.insert(0, str(PAYLOAD))
import ml_r12_bridge as bridge


class TestR12SyntheticHoldout(unittest.TestCase):
    def test_real_signed_model_and_all_raw_split_rows(self):
        result = bridge.verified_synthetic_holdout(PAYLOAD)
        self.assertEqual(result['status'], 'source_recomputed_synthetic_family_holdout_only')
        self.assertEqual(result['model_sha256'], bridge.EXPECTED_MODEL_SHA256)
        self.assertEqual(result['training']['parts'], 54)
        self.assertEqual(result['validation']['parts'], 18)
        self.assertEqual(result['test']['parts'], 36)
        self.assertEqual(result['test']['correct'], 35)
        self.assertEqual(result['test']['topology_assisted_correct'], 36)
        self.assertAlmostEqual(result['test']['accuracy'], 35/36)
        self.assertEqual(result['test']['families'], ['l_support', 'chamfer_plate'])
        self.assertFalse(result['independent_real_cad_accuracy_verified'])
        self.assertFalse(result['production_eligible'])

    def test_model_or_research_records_cannot_silently_claim_accuracy(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            dest=root/'ml'/'r12_research'
            dest.mkdir(parents=True)
            src=PAYLOAD/'ml'/'r12_research'
            shutil.copyfile(src/'research_model.joblib',dest/'research_model.joblib')
            shutil.copyfile(src/'report.json',dest/'report.json')
            original=json.loads((dest/'report.json').read_text(encoding='utf8'))
            cases=[
                ('invented count', lambda d: d['metrics']['test'].__setitem__('correct_count',36)),
                ('invented matrix', lambda d: d['metrics']['test']['confusion_matrix'][1].__setitem__(2,1)),
                ('changed raw prediction', lambda d: d['metrics']['test']['prediction_records'][0].__setitem__('predicted','blind_hole')),
                ('false per-item accuracy', lambda d: d['metrics']['test']['prediction_records'][0].__setitem__('correct',False)),
                ('false average', lambda d: d['metrics']['test'].__setitem__('accuracy_including_abstentions',1.0)),
                ('family overlap', lambda d: d['families']['test'].__setitem__(0,'plate')),
                ('duplicate record', lambda d: d['metrics']['test']['prediction_records'][1].__setitem__('id',d['metrics']['test']['prediction_records'][0]['id'])),
                ('same split duplicate family', lambda d: d['families']['test'].__setitem__(1,'l_support')),
                ('self-consistent forged holdout labels', lambda d: (
                    d['metrics']['test']['prediction_records'][0].update(
                        predicted='blind_hole', correct=False),
                    d['metrics']['test']['confusion_matrix'][0].__setitem__(0,11),
                    d['metrics']['test']['confusion_matrix'][0].__setitem__(2,1),
                    d['metrics']['test'].__setitem__('correct_count',34),
                    d['metrics']['test'].__setitem__('accuracy_including_abstentions',34/36))),
            ]
            for name, change in cases:
                with self.subTest(case=name):
                    trial=json.loads(json.dumps(original))
                    change(trial)
                    (dest/'report.json').write_text(json.dumps(trial),encoding='utf8')
                    with self.assertRaises(ValueError):
                        bridge.verified_synthetic_holdout(root)
            # A Windows CRLF-only checkout must preserve exactly the same
            # archived research records without weakening source authenticity.
            original_lf=(src/'report.json').read_bytes().replace(b'\r\n',b'\n')
            (dest/'report.json').write_bytes(original_lf.replace(b'\n',b'\r\n'))
            self.assertEqual(bridge.verified_synthetic_holdout(root)['test']['correct'],35)
            # Reformatting or editing source labels/metrics is not the
            # original pinned research report, even if internally consistent.
            (dest/'report.json').write_text(json.dumps(original),encoding='utf8')
            with self.assertRaisesRegex(ValueError,'블롭 해시'):
                bridge.verified_synthetic_holdout(root)
            (dest/'report.json').write_bytes(original_lf)
            with open(dest/'research_model.joblib','ab') as f:
                f.write(b'tampered')
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                bridge.verified_synthetic_holdout(root)


if __name__=='__main__':
    unittest.main()
