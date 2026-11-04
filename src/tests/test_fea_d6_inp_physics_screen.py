"""Cross-geometry INP location screening using synthetic physical decks.

Production comparison re-verifies separate actual solver INP/STA/FRD archives
before calling this screen. These fixtures are NOT real FEA results.
"""
from pathlib import Path
import tempfile
import unittest
import sys

# CI runs this file from the repository root, not with PYTHONPATH=src.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fea_load_moment import (
    _audit_cross_geometry_regions, screen_two_geometry_verified_inp,
    D6_SUPPORT_BBOX_MAX_DRIFT_MM,D6_MOMENT_LEVER_ARM_MAX_DRIFT_MM
)

A="1"*32
B="2"*32

def build_deck(folder,*,load_shift=0.,fixed_shift=0.,missing_dof=False,
               grav=False,include=False,load_shift_along_axis=0.):
    p=Path(folder)/"geofield_case.inp"
    p.parent.mkdir(parents=True,exist_ok=True)
    x=5.+fixed_shift
    z=10.+load_shift_along_axis
    lines=[
        "*HEADING","Synthetic not a real solver","*NODE",
        "1,0,0,0",f"2,{x},0,0","3,0,5,0",f"4,{x},5,0",
        f"5,{20+load_shift},10,{z}",
        f"6,{22+load_shift},10,{z}",
        "*ELEMENT, TYPE=C3D4","1,1,2,3,5",
        "*BOUNDARY",
        "1, 1, 3, 0.","2,1,3,0","3,1,3,0",
        "4,1,2,0" if missing_dof else "4,1,3,0",
        "*CLOAD","5,3,-50","6,3,-50",
    ]
    if grav:
        lines.extend(["*DLOAD","VOLUME,GRAV,9806.65,0,0,-1"])
    if include:
        lines.extend(["*INCLUDE, INPUT=outside.inp"])
    lines.extend(["*NODE FILE","U","*END STEP"])
    p.write_text("\n".join(lines)+"\n",encoding="ascii")
    return p

class TwoGeometryRealINPScreens(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="gf-physical-d6-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.a=self.root/"fea_runs"/A
        self.b=self.root/"fea_runs"/B
        build_deck(self.a);build_deck(self.b)
        self.old={"run_id":A,"evidence":"real_solver_files_revalidated",
                  "self_weight_applied":False,"force_n":100.,
                  "direction":[0.,0.,-1.]}
        self.new={**self.old,"run_id":B}

    def verify(self):
        return screen_two_geometry_verified_inp(self.root,self.old,self.new)

    def test_equal_planar_support_bbox_and_load_moment_screen_passes(self):
        result=self.verify()
        self.assertEqual(result["status"],"real_two_inp_load_support_screen_passed")
        self.assertEqual(result["fixed_plane_axis"],2)
        for key in ("support_bbox_max_drift_mm","load_bbox_max_drift_mm",
                    "load_center_distance_mm","resultant_drift_n",
                    "load_moment_change_n_mm",
                    "load_moment_equivalent_lever_arm_change_mm"):
            self.assertEqual(result[key],0.)
        self.assertTrue(result["support_bounding_screen_passed"])
        self.assertTrue(result["applied_load_and_moment_screen_passed"])
        self.assertFalse(result["physical_cad_surface_correspondence_verified"])
        self.assertFalse(result["reaction_equilibrium_correspondence_verified"])
        self.assertFalse(result["geometry_improvement_verified"])
        self.assertFalse(result["structural_safety_certified"])
        self.assertGreater(D6_SUPPORT_BBOX_MAX_DRIFT_MM,0)
        self.assertGreater(D6_MOMENT_LEVER_ARM_MAX_DRIFT_MM,0)

    def test_load_center_or_moment_drift_blocks(self):
        for shift in (.3,-.3):
            with self.subTest(shift=shift):
                build_deck(self.b,load_shift=shift)
                with self.assertRaisesRegex(ValueError,"moment arm|center|region"):
                    self.verify()
        build_deck(self.b,load_shift_along_axis=.4)
        with self.assertRaisesRegex(ValueError,"center|region"):
            self.verify()

    def test_support_location_shift_blocks_even_same_resultant(self):
        build_deck(self.b,fixed_shift=.3)
        with self.assertRaisesRegex(ValueError,"support"):
            self.verify()

    def test_partial_support_dofs_rejected(self):
        build_deck(self.b,missing_dof=True)
        with self.assertRaisesRegex(ValueError,"Partial"):
            self.verify()

    def test_gravity_body_load_and_include_block(self):
        build_deck(self.b,grav=True)
        with self.assertRaisesRegex(ValueError,"gravity"):
            self.verify()
        build_deck(self.b,grav=False,include=True)
        with self.assertRaisesRegex(ValueError,"External"):
            self.verify()
        build_deck(self.b)
        self.new["self_weight_applied"]=True
        with self.assertRaisesRegex(ValueError,"self-weight"):
            self.verify()

    def test_saved_numbers_without_actual_solver_proof_rejected(self):
        self.new["evidence"]="saved_snapshot_only"
        with self.assertRaisesRegex(ValueError,"verification"):
            self.verify()

    def test_actual_fixed_coords_not_cad_face_numbers(self):
        a=_audit_cross_geometry_regions(self.a/"geofield_case.inp")
        self.assertEqual(a["fixed_bbox_mm"],[0.,5.,0.,5.,0.,0.])
        self.assertEqual(a["loaded_bbox_mm"],[20.,22.,10.,10.,10.,10.])
        self.assertEqual(a["fixed_node_count"],4)
        self.assertEqual(a["loaded_node_count"],2)

if __name__=="__main__":
    unittest.main()
