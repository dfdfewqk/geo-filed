"""FEA A: read-only INP force/moment screen, never simulated CalculiX evidence."""
import copy
import importlib.util
import sys
import types
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fea_load_moment import audit_verified_deck, compare_verified_runs
# Production fea_convergence imports fea_compare -> Windows-only fea_restore.
# Inject an isolated _side for synthetic routing; read-only INP audit remains real.
mock_compare = types.ModuleType('fea_compare')
mock_compare._side = lambda *args: None
with patch.dict(sys.modules, {'fea_compare':mock_compare}):
    spec = importlib.util.spec_from_file_location('fea_convergence_under_test',
        Path(__file__).resolve().parents[1] / 'fea_convergence.py')
    fea_convergence = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fea_convergence)


class RealInpFixture(unittest.TestCase):
    def test_archived_three_kg_deck_preserves_original_and_expected_force(self):
        archive = Path('/mnt/data/files/09ef27cabe074bfa84b413d786fe075e.zip')
        if not archive.is_file():
            self.skipTest('Private historical INP archive is not distributed')
        with zipfile.ZipFile(archive) as z:
            filename = next(n for n in z.namelist() if n.endswith('/geofield_case.inp'))
            raw = z.read(filename)
        with tempfile.TemporaryDirectory() as folder:
            deck = Path(folder)/'actual.inp'; deck.write_bytes(raw)
            r = audit_verified_deck(deck,29.41995,[0,0,-1])
            self.assertEqual(deck.read_bytes(),raw)
            self.assertEqual(r['applied_node_count'],609)
            self.assertAlmostEqual(r['total_force_n'][2],-29.41995,places=5)
            self.assertAlmostEqual(r['force_application_center_mm'][0],25.389742,places=5)
            self.assertAlmostEqual(r['moment_about_global_origin_n_mm'][1],746.96494,places=4)


class SyntheticDecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.ids=[ch*32 for ch in 'abc']
        self.runs=[]
        for i,code in enumerate(self.ids):
            p=self.root/'fea_runs'/code/'geofield_case.inp'
            p.parent.mkdir(parents=True)
            self.write_deck(p,25.0)
            self.runs.append({'run_id':code,'force_n':100.,'direction':[0.,0.,-1.],
                'snapshot_id':str(i+1)*32,'cad_sha256':'d'*64,'material':'Al6061',
                'young_modulus_mpa':70000.,'poisson_ratio':.33,'fixed_faces':[1],
                'load_faces':[3],'external_mass_kg':10.,'analysis_type':'linear_static',
                'load_interpretation':'total_force_not_pressure',
                'self_weight_applied':False,'gravity_density_kg_m3':None,
                'gravity_direction':None,'gravity_mm_s2':None,'solver':'CalculiX ccx',
                'mesher':'Gmsh Python API/OpenCASCADE','mesh_target_mm':3.0-i,
                'mesh_node_count':2000+1000*i,'mesh_tetrahedron_count':6500+2500*i,
                'max_stress_mpa':3.25+i*.04,'max_displacement_mm':.01+i*.0001,
                'evidence':'real_solver_files_revalidated'})

    @staticmethod
    def write_deck(p, center=25., force=-100., extra=''):
        p.write_text(f'*NODE\n1,{center-1},0,0\n2,{center+1},0,0\n3,{center+1},3,0\n4,0,0,0\n'
                     '*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n*BOUNDARY\n4,1,3,0\n'
                     f'*CLOAD\n1,3,{force/2}\n2,3,{force/2}\n{extra}*NODE FILE\nU\n*END STEP\n')

    def test_same_real_deck_loads_moment_is_comparable(self):
        r=compare_verified_runs(self.root,self.runs)
        self.assertTrue(r['moment_comparable_for_mesh_only_review'])
        self.assertEqual(r['moment_step_changes_n_mm'],[0.,0.])
        self.assertFalse(r['convergence_certified'])

    def test_equal_resultant_different_moment_is_flagged(self):
        p=self.root/'fea_runs'/self.ids[1]/'geofield_case.inp'
        self.write_deck(p,25.35)
        r=compare_verified_runs(self.root,self.runs)
        self.assertFalse(r['moment_comparable_for_mesh_only_review'])
        self.assertAlmostEqual(r['moment_equivalent_lever_arm_step_mm'][0],.35)

    def test_corrupted_load_changes_denied(self):
        p=self.root/'fea_runs'/self.ids[1]/'geofield_case.inp'
        self.write_deck(p,25.,force=-90.)
        with self.assertRaisesRegex(ValueError,'resultant'):
            compare_verified_runs(self.root,self.runs)

    def test_duplicate_load_axis_denied(self):
        p=self.root/'fea_runs'/self.ids[1]/'geofield_case.inp'
        self.write_deck(p,25.,extra='1,3,-3\n')
        with self.assertRaisesRegex(ValueError,'duplicate'):
            compare_verified_runs(self.root,self.runs)

    def test_fixed_node_load_denied(self):
        p=self.root/'fea_runs'/self.ids[1]/'geofield_case.inp'
        p.write_text(p.read_text().replace('*CLOAD\n1,3,-50.0\n2,3,-50.0',
            '*CLOAD\n4,3,-50\n2,3,-50'))
        with self.assertRaisesRegex(ValueError,'fixed'):
            compare_verified_runs(self.root,self.runs)

    def test_missing_deck_is_not_a_zero_moment(self):
        (self.root/'fea_runs'/self.ids[0]/'geofield_case.inp').unlink()
        with self.assertRaisesRegex(ValueError,'missing'):
            compare_verified_runs(self.root,self.runs)

    def test_reject_duplicate_run_id(self):
        rows=copy.deepcopy(self.runs);rows[1]['run_id']=rows[0]['run_id']
        with self.assertRaisesRegex(ValueError,'Unique'):
            compare_verified_runs(self.root,rows)

    def test_read_only_no_inp_mutation(self):
        p=self.root/'fea_runs'/self.ids[0]/'geofield_case.inp'
        source=p.read_bytes()
        compare_verified_runs(self.root,self.runs)
        self.assertEqual(p.read_bytes(),source)

    def assess(self):
        rows=self.runs
        with patch.object(fea_convergence,'_side',side_effect=lambda _db,_jobs,id:next(r for r in rows if r['snapshot_id']==id)):
            return fea_convergence.assess('db',self.root,[r['snapshot_id'] for r in rows])

    def test_actual_inp_moment_drifts_block_stability_pass(self):
        p=self.root/'fea_runs'/self.ids[1]/'geofield_case.inp'
        self.write_deck(p,25.35)
        d=self.assess()
        self.assertFalse(d['numeric_stability_diagnostic']['passes'])
        self.assertFalse(d['actual_load_moment_comparability']['moment_comparable_for_mesh_only_review'])
        self.assertIn('moment',d['warning'].lower())
        self.assertFalse(d['convergence_certified'])

    def test_matched_inp_diagnostic_still_not_convergence_proof(self):
        d=self.assess()
        self.assertTrue(d['numeric_stability_diagnostic']['passes'])
        self.assertTrue(d['actual_load_moment_comparability']['moment_comparable_for_mesh_only_review'])
        self.assertFalse(d['convergence_certified'])

    def test_missing_inp_fails_closed_in_real_path(self):
        (self.root/'fea_runs'/self.ids[1]/'geofield_case.inp').unlink()
        with self.assertRaises(ValueError):self.assess()

if __name__=='__main__':unittest.main()
