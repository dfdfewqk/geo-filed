"""A4: actual INP tetrahedral refinement screens (not CalculiX numerical runs)."""
import importlib, math, shutil, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
import types, importlib.util
stub=types.ModuleType('fea_compare')
stub._side=lambda *_: None
with patch.dict(sys.modules,{'fea_compare':stub}):
    spec=importlib.util.spec_from_file_location('fea_convergence_stage4',ROOT/'fea_convergence.py')
    fc=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fc)


def make_inp(path, factor=1.0, repeat=1, *, malformed=False, element_type='C3D4'):
    """Two separated tetrahedra are intentional: pure evidence parser exercise."""
    # Four nodes per tetra; all coordinates scale by factor.
    coords=[(0,0,0),(1,0,0),(0,1,0),(0,0,1)]
    lines=['*HEADING','test','*NODE']
    for i in range(repeat):
        for j,pos in enumerate(coords):
            lines.append(f'{i*4+j+1}, '+', '.join(str((v+i*3)*factor) for v in pos))
    lines.append(f'*ELEMENT, TYPE={element_type}, ELSET=VOLUME')
    for i in range(repeat):
        refs=[i*4+j+1 for j in range(4)]
        if malformed and i == repeat-1: refs[-1] = 99999
        lines.append(str(i+1)+', '+', '.join(str(j) for j in refs))
    lines.extend(['*MATERIAL, NAME=ISOTROPIC','*ELASTIC','69000, 0.33'])
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('\n'.join(lines)+'\n',encoding='ascii')


class ActualInpTetraMesh(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_expected_edge_length_and_count(self):
        p=self.root/'m.inp';make_inp(p,2.0,repeat=2)
        r=fc.actual_tetra_edge_resolution(p,8,2)
        self.assertEqual(r['actual_tetrahedra'],2)
        self.assertAlmostEqual(r['mean_longest_tetra_edge_mm'],math.sqrt(2)*2)
    def test_decreasing_real_edges_detected(self):
        sizes=[]
        for i,factor in enumerate((2.,1.,.5)):
            p=self.root/f'{i}.inp';make_inp(p,factor)
            sizes.append(fc.actual_tetra_edge_resolution(p,4,1)['mean_longest_tetra_edge_mm'])
        self.assertTrue(sizes[0]>sizes[1]>sizes[2])
    def test_missing_node_rejected(self):
        p=self.root/'bad.inp';make_inp(p,malformed=True)
        with self.assertRaisesRegex(ValueError,'존재하지 않는 절점'):fc.actual_tetra_edge_resolution(p,4,1)
    def test_reject_non_c3d4(self):
        p=self.root/'bad.inp';make_inp(p,element_type='C3D10')
        with self.assertRaisesRegex(ValueError,'C3D4'):fc.actual_tetra_edge_resolution(p,4,1)
    def test_count_mismatch_rejected(self):
        p=self.root/'bad.inp';make_inp(p)
        with self.assertRaisesRegex(ValueError,'노드·요소'):fc.actual_tetra_edge_resolution(p,5,1)
    def test_duplicate_nodes_rejected(self):
        p=self.root/'bad.inp';make_inp(p)
        s=p.read_text();s=s.replace('4, 0.0, 0.0, 1.0','3, 0.0, 0.0, 1.0');p.write_text(s)
        with self.assertRaisesRegex(ValueError,'중복'):fc.actual_tetra_edge_resolution(p,4,1)
    def test_symlink_rejected(self):
        p=self.root/'a.inp';make_inp(p)
        link=self.root/'link.inp'
        try: link.symlink_to(p)
        except OSError:self.skipTest('symlink unavailable')
        with self.assertRaisesRegex(ValueError,'INP 원본'):fc.actual_tetra_edge_resolution(link,4,1)
    def test_original_private_3kg_mesh_when_available(self):
        archive=Path('/mnt/data/files/09ef27cabe074bfa84b413d786fe075e.zip')
        if not archive.is_file():self.skipTest('Prior 3kg evidence not present; CI without private file')
        with zipfile.ZipFile(archive) as z:
            source=next(n for n in z.namelist() if n.endswith('geofield_case.inp'))
            (self.root/'real.inp').write_bytes(z.read(source))
        diag=fc.actual_tetra_edge_resolution(self.root/'real.inp',2798,8611)
        self.assertGreater(diag['mean_longest_tetra_edge_mm'],0)
        self.assertEqual(diag['actual_tetrahedra'],8611)


class ThreeMeshScreen(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.ids=['a'*32,'b'*32,'c'*32];self.shots=['1'*32,'2'*32,'3'*32]
        self.rows=[]
        for i,sz in enumerate((4.,3.,2.)):
            rid=self.ids[i]
            make_inp(self.root/'fea_runs'/rid/'geofield_case.inp',factor=(3.,2.,1.)[i],repeat=i+1)
            self.rows.append(dict(snapshot_id=self.shots[i],run_id=rid,cad_sha256='0'*64,
                material='metal',young_modulus_mpa=200000.,poisson_ratio=.3,
                fixed_faces=[1],load_faces=[2],force_n=29.41995,direction=[0,0,-1],external_mass_kg=3,
                analysis_type='linear_static',load_interpretation='mass_as_force',self_weight_applied=False,
                gravity_density_kg_m3=None,gravity_direction=None,gravity_mm_s2=None,
                solver='CalculiX ccx',mesher='Gmsh Python API/OpenCASCADE',
                mesh_target_mm=sz,mesh_node_count=4*(i+1),mesh_tetrahedron_count=i+1,
                max_stress_mpa=8.0+.05*i,max_displacement_mm=.01+.00005*i,
                evidence='real_solver_files_revalidated'))
    def tearDown(self):self.tmp.cleanup()
    def assess(self):
        from types import ModuleType
        lm=ModuleType('fea_load_moment')
        lm.compare_verified_runs=lambda *_: {'moment_comparable_for_mesh_only_review':True,'warning':''}
        with patch.object(fc,'_side',side_effect=lambda _db,_jobs,sid:next(x for x in self.rows if x['snapshot_id']==sid)),patch.dict(sys.modules,{'fea_load_moment':lm}):
            return fc.assess('ignored',self.root,self.shots)
    def test_real_mesh_refinement_passes_screen_only(self):
        r=self.assess(); self.assertTrue(r['actual_mesh_resolution_diagnostic']['effective_mean_edge_refinement'])
        self.assertTrue(r['numeric_stability_diagnostic']['passes']);self.assertFalse(r['convergence_certified'])
    def test_target_gets_smaller_but_actual_mesh_does_not(self):
        make_inp(self.root/'fea_runs'/self.ids[2]/'geofield_case.inp',factor=3.,repeat=3)
        r=self.assess();self.assertFalse(r['actual_mesh_resolution_diagnostic']['effective_mean_edge_refinement'])
        self.assertFalse(r['numeric_stability_diagnostic']['passes']);self.assertIn('실제 사면체',r['warning'])
    def test_corrupted_inp_rejected_before_claiming_three_runs(self):
        p=self.root/'fea_runs'/self.ids[1]/'geofield_case.inp'
        make_inp(p,repeat=2,malformed=True)
        with self.assertRaisesRegex(ValueError,'절점'):self.assess()
    def test_mesh_series_summary_exposes_measured_edge_status(self):
        s=(ROOT/'fea_mesh_series.py').read_text(encoding='utf-8')
        self.assertIn("'actual_mesh_resolution_diagnostic':verified.get('actual_mesh_resolution_diagnostic')",s)

if __name__=='__main__':unittest.main()
