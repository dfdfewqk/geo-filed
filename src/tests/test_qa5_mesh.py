"""Synthetic-only mesh comparator regression; NOT three actual CalculiX runs."""
import importlib.util,re,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
class MeshComparatorContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stub=types.ModuleType('fea_compare');stub._side=lambda *args:None
        with patch.dict(sys.modules,{'fea_compare':stub}):
            spec=importlib.util.spec_from_file_location('qa5_convergence',ROOT/'fea_convergence.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        cls.assess=staticmethod(module.assess)
        cls.module=module
    def rows(self):
        base={
            'cad_sha256':'a'*64,'material':'Al6061','young_modulus_mpa':69000.,
            'poisson_ratio':.33,'fixed_faces':[3], 'load_faces':[1],
            'force_n':98.0665,'direction':[0,0,-1.], 'external_mass_kg':10.,
            'analysis_type':'linear_static','load_interpretation':'mass_as_force',
            'self_weight_applied':True,'gravity_density_kg_m3':2700.,
            'gravity_direction':[0,0,-1.], 'gravity_mm_s2':9810.,
            'solver':'CalculiX ccx','mesher':'Gmsh Python API/OpenCASCADE',
            'max_stress_mpa':3.25,'max_displacement_mm':.0100,
            'mesh_node_count':2000,'mesh_tetrahedron_count':6500}
        rows=[]
        for i,(mm,count) in enumerate([(3.,6500),(2.,9000),(1.,15000)]):
            r=base|{'run_id':chr(97+i)*32,'snapshot_id':chr(100+i)*32,
               'mesh_target_mm':mm,'mesh_node_count':int(2000+1000*i),
               'mesh_tetrahedron_count':count,'max_stress_mpa':3.25+.04*i,
               'max_displacement_mm':.0100+.0001*i}
            rows.append(r)
        return rows
    def evaluate(self,rows):
        with patch.object(self.module,'_side',side_effect=lambda _db,_jobs,i:next(r for r in rows if r['snapshot_id']==i)):
            return self.assess('db','jobs',[r['snapshot_id'] for r in rows])
    def test_synthetic_valid_reports_diagnostic_not_proof(self):
        result=self.evaluate(self.rows());self.assertTrue(result['numeric_stability_diagnostic']['passes'])
        self.assertFalse(result['convergence_certified']);self.assertFalse(result['safety_certified'])
    def test_mismatched_gravity_density_rejected(self):
        r=self.rows();r[2]['gravity_density_kg_m3']=2900.
        with self.assertRaisesRegex(ValueError,'비교 불가'):self.evaluate(r)
    def test_mismatched_gravity_direction_rejected(self):
        r=self.rows();r[2]['gravity_direction']=[0,-1,0]
        with self.assertRaisesRegex(ValueError,'비교 불가'):self.evaluate(r)
    def test_mismatched_force_rejected(self):
        r=self.rows();r[2]['force_n']=120.
        with self.assertRaisesRegex(ValueError,'비교 불가'):self.evaluate(r)
    def test_missing_unique_mesh_target_rejected(self):
        r=self.rows();r[2]['mesh_target_mm']=2.
        with self.assertRaisesRegex(ValueError,'서로 다른 목표 메시'):self.evaluate(r)
    def test_no_count_growth_not_pass(self):
        r=self.rows();r[2]['mesh_node_count']=1000
        result=self.evaluate(r);self.assertFalse(result['numeric_stability_diagnostic']['passes'])
    def test_large_stress_shift_not_pass(self):
        r=self.rows();r[2]['max_stress_mpa']=9.
        result=self.evaluate(r);self.assertFalse(result['numeric_stability_diagnostic']['passes'])
if __name__=='__main__':unittest.main()
