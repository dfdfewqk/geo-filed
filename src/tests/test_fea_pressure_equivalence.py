"""Read-only engineering review gates for candidate CLOAD moment balancing."""
import math
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from fea_pressure_equivalence import review_actual_surface_candidate


class BasicSurfaceReview(unittest.TestCase):
    def setUp(self):
        self.nodes = {1:[0.,0.,0.],2:[10.,0.,0.],3:[10.,10.,0.],4:[0.,10.,0.],5:[5.,5.,5.]}
        self.tris=[(1,2,3),(1,3,4)]
        self.original={n:[0.,0.,-w] for n,w in {1:100/3,2:100/6,3:100/3,4:100/6}.items()}
    def review(self, nodes=None, tris=None, loads=None, fixed=(), direction=(0,0,-1)):
        return review_actual_surface_candidate(nodes if nodes is not None else self.nodes,
            tris if tris is not None else self.tris,fixed,
            loads if loads is not None else self.original,direction)

    def test_original_area_weights_and_moment_stable(self):
        out=self.review()
        self.assertTrue(out['passes_research_screen'])
        self.assertLess(out['candidate_moment_error_n_mm'],1e-7)
        self.assertLess(out['maximum_nodal_force_change_percent'],1e-10)
        self.assertFalse(out['solver_executed'])
        self.assertFalse(out['uniform_pressure_equivalent'])

    def test_fixed_node_excluded_still_allows_small_correction(self):
        # Small square, 25% effective area/3 weight removed -> screen must fail
        nodes={1:[0.,0.,0.],2:[10.,0.,0.],3:[10.,10.,0.],4:[0.,10.,0.]}
        tris=[(1,2,3),(1,3,4)]
        w={1:1/3,2:1/6,3:1/3,4:1/6}
        free={n:ww for n,ww in w.items() if n!=2}
        norm=sum(free.values())
        loads={n:[0,0,-100*ww/norm] for n,ww in free.items()}
        r=self.review(nodes,tris,loads,fixed={2})
        self.assertFalse(r['passes_research_screen'])
        self.assertIn('5%',str(r['reasons']))
        self.assertFalse(r['production_loads_changed'])

    def test_different_force_law_rejected(self):
        loads={n:f.copy() for n,f in self.original.items()}
        loads[1][2]-=2.;loads[3][2]+=2.
        with self.assertRaisesRegex(ValueError,'surface-area'):
            self.review(loads=loads)

    def test_wrong_surface_nodes_rejected(self):
        with self.assertRaisesRegex(ValueError,'node set'):
            self.review(tris=[(1,2,3)])

    def test_duplicate_triangle_rejected(self):
        with self.assertRaisesRegex(ValueError,'Repeated'):
            self.review(tris=self.tris+[self.tris[0]])

    def test_zero_area_triangle_rejected(self):
        with self.assertRaisesRegex(ValueError,'Zero-area'):
            self.review(nodes={**self.nodes,6:[5.,0.,0.]},tris=[(1,2,6)])

    def test_reversed_force_rejected(self):
        loads={n:f.copy() for n,f in self.original.items()};loads[1][2]=1
        with self.assertRaisesRegex(ValueError,'off-axis or reversed'):
            self.review(loads=loads)

    def test_inputs_never_modified(self):
        nodes={n:v.copy() for n,v in self.nodes.items()}
        loads={n:v.copy() for n,v in self.original.items()}
        self.review(nodes=nodes,loads=loads)
        self.assertEqual(nodes,self.nodes); self.assertEqual(loads,self.original)

    def test_non_unit_force_direction_rejected(self):
        with self.assertRaisesRegex(ValueError,'unit vector'):
            self.review(direction=[0,0,-10])

    def test_reweight_over_10_percent_blocks_study(self):
        # Admissible free geometry but an edge's fixed-node share causes a large correction.
        nodes={1:[0,0,0],2:[10,0,0],3:[10,10,0],4:[0,10,0]}
        tris=[(1,2,3),(1,3,4)]
        free_weights={1:1/3,2:1/6,3:1/3}
        loads={n:[0,0,-100*w/sum(free_weights.values())] for n,w in free_weights.items()}
        result=self.review(nodes,tris,loads,fixed={4})
        self.assertFalse(result['passes_research_screen'])
        self.assertGreater(result['maximum_nodal_force_change_percent'],10)


class ActualArchivedThreeKgScreen(unittest.TestCase):
    def test_real_archived_inp_review_only(self):
        path=Path('/mnt/data/files/09ef27cabe074bfa84b413d786fe075e.zip')
        if not path.is_file():
            self.skipTest('The private original INP is not in this repository')
        with zipfile.ZipFile(path) as z:
            name=next(p for p in z.namelist() if p.endswith('geofield_case.inp'))
            raw=z.read(name)
        section='';nodes={};tets=[];fixed=set();forces={}
        for line in raw.decode('ascii').splitlines():
            line=line.strip()
            if not line or line.startswith('**'): continue
            if line.startswith('*'):section=line.split(',')[0].upper();continue
            v=[s.strip() for s in line.split(',')]
            if section=='*NODE': nodes[int(v[0])]=[float(q) for q in v[1:]]
            elif section=='*ELEMENT': tets.append(tuple(map(int,v[1:])))
            elif section=='*BOUNDARY': fixed.add(int(v[0]))
            elif section=='*CLOAD': forces.setdefault(int(v[0]),[0,0,0])[int(v[1])-1]=float(v[2])
        triangles=Counter(tuple(sorted(t[:i]+t[i+1:])) for t in tets for i in range(4))
        surface=[t for t,c in triangles.items() if c==1 and all(abs(nodes[n][2])<1e-8 for n in t)]
        result=review_actual_surface_candidate(nodes,surface,fixed,forces,(0,0,-1))
        self.assertTrue(result['passes_research_screen'])
        self.assertEqual(result['surface_triangle_count'],1146)
        self.assertEqual(result['free_load_node_count'],609)
        self.assertAlmostEqual(result['excluded_area_weight_percent'],1.535037345,places=6)
        self.assertLess(result['candidate_moment_error_n_mm'],1e-6)
        self.assertGreater(result['original_moment_error_n_mm'],11)
        self.assertLess(result['maximum_nodal_force_change_percent'],5)
        self.assertFalse(result['production_loads_changed'])
        with zipfile.ZipFile(path) as z:self.assertEqual(raw,z.read(name))


if __name__=='__main__':unittest.main()
