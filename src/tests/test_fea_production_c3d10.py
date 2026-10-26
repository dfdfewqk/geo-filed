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

    def test_full_tri6_opt_in_preserves_force_moment_and_requires_explicit_permission(self):
        nodes,tets,faces=self.fea.promote_to_straight_c3d10(
            {1:[0.,0.,0.],2:[2.,0.,0.],3:[0.,2.,0.],4:[0.,0.,2.]},
            [(1,[1,2,3,4])],{7:[[1,2,3]],8:[[1,2,4]]})
        fixed={n for tri in faces[8] for n in tri}
        face=faces[7][0]
        loads,area=self.fea.weighted_surface_force(nodes,[face[3:6]],24.,[0.,0.,-1.])
        self.assertTrue(set(loads)&fixed)
        audit=self.fea.audit_surface_load(
            nodes,[face[:3]],loads,fixed,24.,[0.,0.,-1.],
            surface_load_nodes=set(face),include_fixed_loads=True)
        self.assertTrue(audit['nominal_surface_pressure_exactly_preserved'])
        self.assertEqual(audit['direct_fixed_load_node_count'],1)
        self.assertLess(audit['moment_difference_n_mm'],1e-8)
        with tempfile.TemporaryDirectory() as folder:
            inp=Path(folder)/'case.inp'
            with self.assertRaisesRegex(ValueError,'겹치거나'):
                self.fea.write_inp(inp,nodes,tets,fixed,loads,68900.,.33)
            self.fea.write_inp(inp,nodes,tets,fixed,loads,68900.,.33,
                               allow_constrained_cload=True)
            with self.assertRaisesRegex(ValueError,'CLOAD'):
                self.fea.verify_written_inp_cload(inp,nodes,loads,fixed,audit)
            verified=self.fea.verify_written_inp_cload(
                inp,nodes,loads,fixed,audit,allow_constrained_cload=True)
            self.assertTrue(verified['written_inp_cload_verified'])
            self.assertLess(math.dist(verified['inp_applied_resultant_n'],[0.,0.,-24.]),1e-7)

    def test_support_reaction_subtracts_direct_fixed_cload_from_raw_rf(self):
        # Synthetic RF convention chosen from actual 2026-10-26 CalculiX A/B:
        # ccx printed fixed RF cancels free CLOAD only. Fixed external CLOAD
        # must be subtracted from raw RF to reconstruct physical reactions.
        nodes={1:[0.,0.,0.],2:[2.,0.,0.],3:[0.,1.,0.],4:[0.,0.,1.]}
        fixed={1,2,4}
        loads={1:[0.,0.,-2.],3:[0.,0.,-8.]}
        # Real response to free point load at x=0,y=1 in this synthetic set:
        # total fixed RF 8 upward plus moments represented at fixed x nodes.
        # Use manually balanced (all+CLOAD) forces at y=0 would be impossible,
        # so select a fully collinear x arrangement for a valid moment example.
        nodes={1:[0.,0.,0.],2:[1.,0.,0.],3:[2.,0.,0.],4:[0.,1.,0.]}
        fixed={1,2}
        loads={1:[0.,0.,-2.],3:[0.,0.,-8.]}
        # RF in original ccx convention: +8 at node2, no fixed external included.
        dat=(
            'forces (fx,fy,fz) for set GEOFIELD_FIXED and time  1.000000E+00\n'
            '\n'
            '1 0. 0. 0.\n'
            '2 0. 0. 8.\n'
            '\n'
        )
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'case.dat';path.write_text(dat)
            # In realistic structures the RF distribution balances moments.
            # This deliberately unbalanced toy should be REJECTED, not guessed.
            with self.assertRaisesRegex(ValueError,'평형'):
                self.fea.parse_fixed_reactions_dat(
                    path,nodes,fixed,loads,allow_constrained_cload=True)
        # Geometry for moment-balanced synthetic: external -8 at x=2 needs
        # two fixed RFs summing +8 and moment +16 (RF x2=+16, x1=-8).
        rf={1:[0.,0.,-8.],2:[0.,0.,16.]}
        dat=('forces (fx,fy,fz) for set GEOFIELD_FIXED and time  1.000000E+00\n'
             '\n1 0. 0. -8.\n2 0. 0. 16.\n\n')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'case.dat';path.write_text(dat)
            verified=self.fea.parse_fixed_reactions_dat(
                path,nodes,fixed,loads,allow_constrained_cload=True)
            self.assertTrue(verified['checked'])
            self.assertEqual(verified['constrained_cload_nodes'],1)
            self.assertEqual(verified['raw_printed_rf_resultant_n'],[0.,0.,8.])
            self.assertEqual(verified['support_reaction_n'],[0.,0.,10.])
            self.assertLess(verified['moment_residual_magnitude_n_mm'],1e-8)
            with self.assertRaisesRegex(ValueError,'고정 노드'):
                self.fea.parse_fixed_reactions_dat(path,nodes,fixed,loads)

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
