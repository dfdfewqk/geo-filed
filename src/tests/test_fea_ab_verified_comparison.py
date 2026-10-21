"""Synthetic protocol-gate tests, NOT two newly solved CalculiX runs."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from fea_ab_verified_comparison import compare_actual_ab, _deck_except_loads

SHA='a'*64
CASE='b'*64
RUN_A='1'*32
RUN_B='2'*32


def make_deck(a,b,*,stiffness='193000.,0.29',constraints='1,1,3',elements='1,1,2,3,4',variant=''):
    return (f'*HEADING\n** A/B protocol test only\n*NODE\n1,0,0,0\n2,10,0,0\n3,10,10,0\n4,0,10,10\n'
        f'*ELEMENT,TYPE=C3D4,ELSET=VOLUME\n{elements}\n'
        f'*MATERIAL,NAME=TEST\n*ELASTIC\n{stiffness}\n*STEP\n*STATIC\n1,1\n'
        f'*BOUNDARY\n{constraints}\n*CLOAD\n2,3,-{a}\n3,3,-{b}\n'
        f'*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n{variant}')


class ABVerifierTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.force=100.
        self.base_a=[40,60]
        self.base_b=[55,45]
        self._create(RUN_A, self.base_a, stress=15.,disp=.025,frd=b'frd A test fixture')
        self._create(RUN_B, self.base_b, stress=14.,disp=.022,frd=b'frd B test fixture')

    def _create(self,rid,weights,*,stress,disp,frd):
        d=self.root/'fea_runs'/rid;d.mkdir(parents=True,exist_ok=True)
        case={'schema':'geofield-fea-case-v1','cad_sha256':SHA,'case_sha256':CASE,
              'boundary_conditions':{'total_force_n':self.force,'force_direction_unit':[0,0,-1]}}
        result={'schema':'geofield-fea-result-v1','status':'solver_executed_result_parsed',
                'cad_sha256':SHA,'case_sha256':CASE,
                'solver':'CalculiX ccx','mesher':'Gmsh Python API/OpenCASCADE',
                'mesh':{'node_count':4,'tetrahedron_count':1},
                'results':{'maximum_nodal_von_mises_mpa':stress,'maximum_displacement_mm':disp,'parsed_nodes':4}}
        (d/'case.json').write_text(json.dumps(case),encoding='utf8')
        (d/'result.json').write_text(json.dumps(result),encoding='utf8')
        (d/'geofield_case.inp').write_text(make_deck(*weights),encoding='ascii')
        (d/'geofield_case.sta').write_text('STEP 1 COMPLETE\n',encoding='ascii')
        (d/'geofield_case.frd').write_bytes(frd)
        return d

    @staticmethod
    def verifier(folder,case,cad_sha):
        assert case['cad_sha256']==cad_sha
        data=json.loads((folder/'result.json').read_text())
        result=copy.deepcopy(data)
        result['results']['parsed_nodes']=4
        # Independent injection represents Windows verifier *contract*, not solver execution.
        field={'schema':'geofield-fea-surface-field-v1','source':'actual_calculix_ascii_frd',
               'cad_sha256':SHA,'case_sha256':CASE,
               'positions_mm':[[0,0,0],[10,0,0],[10,10,0],[0,10,10]],
               'von_mises_mpa':[0,4,7,9] if folder.name==RUN_A else [0,3,8,7]}
        return result,field

    def compare(self):
        return compare_actual_ab(self.root,RUN_A,RUN_B,verifier=self.verifier)

    def test_valid_protocol_mock_does_not_certify_actual_safety(self):
        out=self.compare()
        self.assertEqual(out['status'],'two_real_calculix_ab_runs_independently_reverified')
        self.assertFalse(out['stress_improvement_certified'])
        self.assertFalse(out['mesh_convergence_certified'])
        self.assertFalse(out['solver_executed_by_this_comparator'])
        self.assertNotIn('cload_lines',out['original'])
        self.assertEqual(out['maximum_nodal_von_mises_comparison']['absolute_change'],-1)
        self.assertEqual(out['maximum_displacement_comparison']['absolute_change'],-.0030000000000000027)
        self.assertAlmostEqual(out['moment_equivalent_lever_arm_change_mm'],1.5)
        self.assertAlmostEqual(out['verified_surface_peak_position_movement_mm'],14.142135623730951)

    def test_same_run_disallowed(self):
        with self.assertRaisesRegex(ValueError,'different solver runs'):
            compare_actual_ab(self.root,RUN_A,RUN_A,verifier=self.verifier)

    def test_unverified_responses_disallowed(self):
        def fake(folder,case,cad):
            result,field=self.verifier(folder,case,cad)
            result['status']='mock_not_verified'
            return result,field
        with self.assertRaisesRegex(ValueError,'verifier rejected'):
            compare_actual_ab(self.root,RUN_A,RUN_B,verifier=fake)

    def test_changed_material_disallowed(self):
        path=self.root/'fea_runs'/RUN_B/'geofield_case.inp'
        path.write_text(path.read_text().replace('193000.,0.29','188000.,0.29'))
        with self.assertRaisesRegex(ValueError,'outside CLOAD'):
            self.compare()

    def test_changed_fixed_node_disallowed(self):
        path=self.root/'fea_runs'/RUN_B/'geofield_case.inp'
        path.write_text(path.read_text().replace('1,1,3','4,1,3'))
        with self.assertRaisesRegex(ValueError,'outside CLOAD'):
            self.compare()

    def test_changed_mesh_element_disallowed(self):
        path=self.root/'fea_runs'/RUN_B/'geofield_case.inp'
        path.write_text(path.read_text().replace('1,1,2,3,4','1,1,2,4,3'))
        with self.assertRaisesRegex(ValueError,'outside CLOAD'):
            self.compare()

    def test_changed_case_sha_disallowed(self):
        path=self.root/'fea_runs'/RUN_B/'case.json'
        obj=json.loads(path.read_text());obj['case_sha256']='c'*64
        path.write_text(json.dumps(obj))
        # Verify result must also use a new valid case; else blocked even earlier.
        with self.assertRaisesRegex(ValueError,'signed CAD case'):
            self.compare()

    def test_candidate_changed_force_disallowed(self):
        path=self.root/'fea_runs'/RUN_B/'geofield_case.inp'
        path.write_text(path.read_text().replace('3,3,-45','3,3,-44'))
        with self.assertRaisesRegex(ValueError,'resultant'):
            self.compare()

    def test_candidate_changed_applied_nodes_disallowed(self):
        path=self.root/'fea_runs'/RUN_B/'geofield_case.inp'
        path.write_text(path.read_text().replace('3,3,-45','4,3,-45'))
        with self.assertRaisesRegex(ValueError,'nodes/components'):
            self.compare()

    def test_same_cload_rejected(self):
        path=self.root/'fea_runs'/RUN_B/'geofield_case.inp'
        path.write_text(make_deck(*self.base_a))
        with self.assertRaisesRegex(ValueError,'No physical CLOAD change'):
            self.compare()

    def test_reused_frd_is_rejected(self):
        a=self.root/'fea_runs'/RUN_A/'geofield_case.frd'
        b=self.root/'fea_runs'/RUN_B/'geofield_case.frd'
        b.write_bytes(a.read_bytes())
        with self.assertRaisesRegex(ValueError,'Identical FRD'):
            self.compare()

    def test_corrupt_old_summary_is_rejected(self):
        path=self.root/'fea_runs'/RUN_B/'result.json'
        obj=json.loads(path.read_text());obj['results']['maximum_nodal_von_mises_mpa']+=2
        path.write_text(json.dumps(obj))
        def verifier(folder,case,cad):
            actual,field=self.verifier(folder,case,cad)
            if folder.name==RUN_B:
                actual['results']['maximum_nodal_von_mises_mpa']-=2
            return actual,field
        with self.assertRaisesRegex(ValueError,'differ from reverified FRD'):
            compare_actual_ab(self.root,RUN_A,RUN_B,verifier=verifier)

    def test_missing_frd_rejected(self):
        (self.root/'fea_runs'/RUN_B/'geofield_case.frd').unlink()
        with self.assertRaisesRegex(ValueError,'Missing actual'):
            self.compare()

    def test_repeated_cload_section_rejected(self):
        path=self.root/'fea_runs'/RUN_B/'geofield_case.inp'
        path.write_text(path.read_text()+"*CLOAD\n2,3,-1\n")
        with self.assertRaisesRegex(ValueError,'multiple CLOAD|Multiple CLOAD'):
            self.compare()

    def test_unsupported_cload_keyword_options_rejected(self):
        path=self.root/'fea_runs'/RUN_B/'geofield_case.inp'
        path.write_text(path.read_text().replace('*CLOAD\n','*CLOAD, OP=MOD\n'))
        with self.assertRaisesRegex(ValueError,'Unsupported CLOAD'):
            self.compare()

    def test_unverified_surface_field_position_suppressed(self):
        def verifier(folder,case,cad):
            x,field=self.verifier(folder,case,cad)
            field['source']='browser_view_cache'
            return x,field
        result=compare_actual_ab(self.root,RUN_A,RUN_B,verifier=verifier)
        self.assertIsNone(result['verified_surface_peak_position_movement_mm'])

    def test_external_include_is_rejected(self):
        path=self.root/'fea_runs'/RUN_B/'geofield_case.inp'
        path.write_text(path.read_text()+'*INCLUDE, INPUT=outside.inp\n')
        with self.assertRaisesRegex(ValueError,'External INCLUDE'):
            self.compare()

    def test_solver_identity_change_rejected(self):
        path=self.root/'fea_runs'/RUN_B/'result.json'
        obj=json.loads(path.read_text());obj['solver']='Different solver'
        path.write_text(json.dumps(obj))
        def real_verifier_identity(folder,case,cad):
            result,field=self.verifier(folder,case,cad)
            result['solver']='CalculiX ccx'
            return result,field
        with self.assertRaisesRegex(ValueError,'Solver/mesher provenance'):
            compare_actual_ab(self.root,RUN_A,RUN_B,verifier=real_verifier_identity)

    def test_no_surface_field_returns_unknown_location(self):
        def verifier(folder,case,cad):
            x,_=self.verifier(folder,case,cad)
            return x, None
        result=compare_actual_ab(self.root,RUN_A,RUN_B,verifier=verifier)
        self.assertIsNone(result['verified_surface_peak_position_movement_mm'])

    def test_read_only_bytes(self):
        files=[x for x in self.root.rglob('*') if x.is_file()]
        before={str(x):x.read_bytes() for x in files}
        self.compare()
        self.assertEqual(before,{str(x):x.read_bytes() for x in files})

if __name__=='__main__':unittest.main()
