"""Pure, offline tests of isolated C3D10 straight-Tri6 load deck experiment."""
import hashlib
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"payload"),str(ROOT/"tests"/"fea_ci_dependencies")]
import fea_solver
from verify_c3d10_shared_edge_traction_ci import (
    exact_tri6_surface_loads, reconstruct_separate_exact_deck,
    reaction_convention_screen,
)


class ResearchSharedEdgeTractionTests(unittest.TestCase):
    def setUp(self):
        coords={1:[0.,0.,0.],2:[2.,0.,0.],3:[0.,2.,0.],4:[0.,0.,2.]}
        self.nodes,self.tets,self.surfaces=fea_solver.promote_to_straight_c3d10(
            coords,[(1,[1,2,3,4])],{10:[[1,2,3]],20:[[1,2,4]]})
        self.loaded=self.surfaces[10]
        self.fixed={n for tri in self.surfaces[20] for n in tri}
        self.shared=set(self.loaded[0][3:6])&self.fixed
        self.assertEqual(len(self.shared),1)

    def test_full_consistent_quadratic_load_includes_shared_support(self):
        loads,audit=exact_tri6_surface_loads(self.nodes,self.loaded,24.,[0.,0.,-1.])
        self.assertEqual(len(loads),3)
        self.assertEqual(set(loads)&self.fixed,self.shared)
        self.assertEqual(audit["surface_area_mm2"],2.)
        self.assertLess(audit["moment_difference_n_mm"],1e-9)
        self.assertTrue(audit["uniform_traction_on_straight_tri6_integrated"])
        for n in loads:self.assertAlmostEqual(loads[n][2],-8.)

    def test_deck_replacement_changes_only_exact_cload(self):
        with tempfile.TemporaryDirectory() as dirname:
            root=Path(dirname)
            old=root/"old.inp";new=root/"new.inp"
            original_loads={n:[0.,0.,-12.] for n in set(self.loaded[0][3:6])-self.fixed}
            fea_solver.write_inp(old,self.nodes,self.tets,self.fixed,
                                 original_loads,68900.,.33)
            loads,_=exact_tri6_surface_loads(self.nodes,self.loaded,24.,[0.,0.,-1.])
            d=reconstruct_separate_exact_deck(old,new,self.nodes,self.tets,loads)
            self.assertTrue(d["only_cload_section_changed"])
            self.assertEqual(old.read_text().count("*CLOAD"),1)
            self.assertEqual(new.read_text().count("*CLOAD"),1)
            self.assertEqual(len([line for line in new.read_text().splitlines() if line.startswith(str(next(iter(self.shared)))+", ")]),3) # NODE, BOUNDARY and CLOAD
            self.assertNotEqual(old.read_bytes(),new.read_bytes())
            self.assertEqual(d["unchanged_original_sha256"],hashlib.sha256(old.read_bytes()).hexdigest())

    def test_mesh_change_is_refused_before_solver(self):
        with tempfile.TemporaryDirectory() as dirname:
            root=Path(dirname);old=root/"old.inp";new=root/"new.inp"
            original_loads={n:[0.,0.,-12.] for n in set(self.loaded[0][3:6])-self.fixed}
            fea_solver.write_inp(old,self.nodes,self.tets,self.fixed,
                                 original_loads,68900.,.33)
            loads,_=exact_tri6_surface_loads(self.nodes,self.loaded,24.,[0.,0.,-1.])
            shifted={n:list(p) for n,p in self.nodes.items()}
            shifted[1][0]=.5
            with self.assertRaisesRegex(ValueError,"Gmsh original and experimental"):
                reconstruct_separate_exact_deck(old,new,shifted,self.tets,loads)
            self.assertFalse(new.exists())

    def test_reaction_convention_cannot_claim_verified(self):
        loads,audit=exact_tri6_surface_loads(self.nodes,self.loaded,24.,[0.,0.,-1.])
        # Synthetic RF is not solver evidence; both convention residuals must
        # be shown, and no support-reaction safety pass can be inferred.
        rf={n:[0.,0.,0.] for n in self.fixed}
        diag=reaction_convention_screen(self.nodes,self.fixed,loads,rf)
        self.assertEqual(diag["fixed_surface_loaded_nodes"],1)
        self.assertAlmostEqual(diag["all_CLOAD_plus_printed_RF_force_residual_n"],24.)
        self.assertAlmostEqual(diag["free_CLOAD_plus_printed_RF_force_residual_n"],16.)
        self.assertFalse(diag["pure_support_reaction_verified"])


if __name__=="__main__":unittest.main()
