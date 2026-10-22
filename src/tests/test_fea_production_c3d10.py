"""Regression for the optional production C3D10 path; no solver needed."""
import importlib.util
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
ENGINE=ROOT/'payload'/'fea_solver.py'

def load_solver():
    stub_gravity=types.ModuleType('gravity_evidence')
    stub_gravity.gravity_spec=lambda *_: None
    stub_gravity.gravity_input_validation=lambda *_: None
    stub_runtime=types.ModuleType('engine_runtime')
    stub_runtime.gmsh_python_status=lambda *_: {}
    with patch.dict(sys.modules,{'gravity_evidence':stub_gravity,'engine_runtime':stub_runtime}):
        spec=importlib.util.spec_from_file_location('fea_solver_quad_optional_unit',ENGINE)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module

class ProductionC3D10Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fea=load_solver()

    def simple(self):
        nodes={1:(0.,0.,0.),2:(2.,0.,0.),3:(0.,2.,0.),4:(0.,0.,2.)}
        return self.fea.promote_to_straight_c3d10(nodes,[(1,[1,2,3,4])],{7:[[1,2,3]]})

    def test_c3d10_shared_edge_has_exact_one_midside_node(self):
        nodes={1:(0.,0.,0.),2:(1.,0.,0.),3:(0.,1.,0.),4:(0.,0.,1.),5:(0.,0.,-1.)}
        nn,ee,_=self.fea.promote_to_straight_c3d10(nodes,[(1,[1,2,3,4]),(2,[1,3,2,5])],{7:[[1,2,3]]})
        self.assertEqual(len(ee),2)
        self.assertEqual(len(nn),14)
        self.assertEqual(len(ee[0][1]),10)
        self.assertEqual(self.fea.validate_volume_mesh(nn,ee)['element_type'],'C3D10')

    def test_planar_quad_tri_consistent_traction_has_only_midside_loads(self):
        nodes,tets,faces=self.simple()
        triangle=faces[7][0]
        loads,free_quarter=self.fea.weighted_surface_force(nodes,[triangle[3:6]],24.,(0.,0.,-1.))
        self.assertEqual(set(loads),set(triangle[3:6]))
        self.assertAlmostEqual(sum(v[2] for v in loads.values()),-24.)
        for mid in triangle[3:6]:self.assertAlmostEqual(loads[mid][2],-8.)
        self.assertAlmostEqual(4*free_quarter,2.)
        audit=self.fea.audit_surface_load(nodes,[triangle[:3]],loads,set(),24.,(0.,0.,-1.),surface_load_nodes=triangle)
        self.assertLess(audit['moment_difference_n_mm'],1e-9)
        self.assertTrue(audit['nominal_surface_pressure_exactly_preserved'])

    def test_inp_is_actual_c3d10_and_all_nodes_in_visualization(self):
        nodes,tets,faces=self.simple()
        tri=faces[7][0]
        loads,_=self.fea.weighted_surface_force(nodes,[tri[3:6]],24.,[0.,0.,-1.])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'case.inp'
            self.fea.write_inp(path,nodes,tets,{4},loads,68900.,.33)
            source=path.read_text()
            self.assertIn('TYPE=C3D10',source)
            self.assertIn('RF\n',source)
            self.assertEqual(next(x for x in source.splitlines() if x.startswith('1, ') and x.count(',')==10).count(','),10)
        field=self.fea.solver_surface_field(nodes,tets,{
            'nodal_displacements_mm':{n:[0.,0.,-0.01] for n in nodes},
            'nodal_von_mises_mpa':{n:1. for n in nodes}},
            {'cad_sha256':'0'*64,'case_sha256':'1'*64})
        self.assertEqual(len(field['triangles']),16)
        self.assertEqual(len(field['positions_mm']),10)
        self.assertEqual(len(field['von_mises_mpa']),10)

    def test_reject_bad_midpoint(self):
        nodes,tets,faces=self.simple()
        nodes[tets[0][1][4]][0]+=0.1
        with self.assertRaisesRegex(ValueError,'중간 절점'):
            self.fea.validate_volume_mesh(nodes,tets)

    def test_reject_linear_quadratic_mixed_mesh(self):
        nodes={1:(0.,0.,0.),2:(1.,0.,0.),3:(0.,1.,0.),4:(0.,0.,1.),5:(0.,0.,-1.)}
        nn,ee,_=self.fea.promote_to_straight_c3d10(nodes,[(1,[1,2,3,4]),(2,[1,3,2,5])],{7:[[1,2,3]]})
        ee[1]=(ee[1][0],ee[1][1][:4])
        with self.assertRaisesRegex(ValueError,'혼합'):
            self.fea.validate_volume_mesh(nn,ee)

if __name__=='__main__':unittest.main()
