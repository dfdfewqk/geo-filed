"""Independent comparison of an *unapplied* moment-balanced load proposal.

Private historical archive is optional; no solver result is invented and no
input files are overwritten by any test.
"""
import math
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path

from fea_moment_balancing import propose_free_node_moment_balance


def cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def moment(nodes,loads):
    return [math.fsum(cross(nodes[n],f)[k] for n,f in loads.items()) for k in range(3)]


class CandidateNumericalAudit(unittest.TestCase):
    def setUp(self):
        self.points={1:[0.,0.,0.],2:[10.,0.,0.],3:[0.,10.,0.],4:[10.,10.,0.]}
        self.loads={n:[0.,0.,-25.] for n in self.points}

    def test_equal_weights_already_balanced(self):
        r=propose_free_node_moment_balance(self.points,self.loads,[],[5.,5.,0.],[0,0,-1])
        self.assertLess(r['candidate_moment_error_n_mm'],1e-8)
        self.assertLess(r['relative_nodal_force_changes']['max_absolute_percent'],1e-8)
        self.assertFalse(r['solver_executed'])

    def test_unequal_weights_preserves_resultant_and_moment(self):
        loads={1:[0,0,-10.],2:[0,0,-40.],3:[0,0,-20.],4:[0,0,-30.]}
        r=propose_free_node_moment_balance(self.points,loads,[],[5.,5.,0.],[0,0,-1])
        new=r['candidate_loads']
        self.assertEqual(set(new),set(loads))
        self.assertAlmostEqual(sum(v[2] for v in new.values()),-100.,places=7)
        self.assertLess(math.dist(moment(self.points,new),[ -500., 500., 0.]),1e-7)
        self.assertTrue(all(f[2]<0 for f in new.values()))

    def test_fixed_node_never_assigned(self):
        with self.assertRaisesRegex(ValueError,'fixed'):
            propose_free_node_moment_balance(self.points,self.loads,[1],[5.,5.,0.],[0,0,-1])

    def test_outside_free_node_convex_hull_fails(self):
        with self.assertRaisesRegex(ValueError,'cannot|converge|ill-conditioned'):
            propose_free_node_moment_balance(self.points,self.loads,[],[100.,100.,0.],[0,0,-1],max_iterations=18)

    def test_degenerate_support_fails_closed(self):
        points={1:[0.,0.,0.],2:[10.,0.,0.]}
        forces={1:[0,0,-50.],2:[0,0,-50.]}
        with self.assertRaisesRegex(ValueError,'ill-conditioned|span'):
            propose_free_node_moment_balance(points,forces,[],[4.,0.,0.],[0,0,-1])

    def test_3d_oblique_force_correct_moment(self):
        d=[0.,-math.sqrt(.5),-math.sqrt(.5)]
        weights=[10.,20.,30.,40.]
        oblique={n:[weights[n-1]*v for v in d] for n in self.points}
        target=[5.,5.,0.]
        r=propose_free_node_moment_balance(self.points,oblique,[],target,d)
        self.assertLess(r['candidate_moment_error_n_mm'],1e-6)
        self.assertAlmostEqual(math.fsum(f[1] for f in r['candidate_loads'].values()),-100*math.sqrt(.5))

    def test_bad_direction_rejected(self):
        with self.assertRaisesRegex(ValueError,'unit vector'):
            propose_free_node_moment_balance(self.points,self.loads,[],[5,5,0],[0,0,-2])

    def test_reverse_force_rejected(self):
        loads=dict(self.loads);loads[1]=[0,0,25]
        with self.assertRaisesRegex(ValueError,'reversed'):
            propose_free_node_moment_balance(self.points,loads,[],[5,5,0],[0,0,-1])

    def test_invalid_coordinates_rejected(self):
        points=dict(self.points);points[2]=[math.nan,0,0]
        with self.assertRaisesRegex(ValueError,'finite'):
            propose_free_node_moment_balance(points,self.loads,[],[5,5,0],[0,0,-1])

    def test_original_unchanged(self):
        points={n:p.copy() for n,p in self.points.items()}
        loads={n:f.copy() for n,f in self.loads.items()}
        propose_free_node_moment_balance(points,loads,[],[5,5,0],[0,0,-1])
        self.assertEqual(points,self.points)
        self.assertEqual(loads,self.loads)


class Archived3kgRealMeshAudit(unittest.TestCase):
    """Conservative reconstruction of Z=0 exterior face from archived tet mesh."""
    def test_inp_mesh_centroid_and_unapplied_candidate(self):
        archive=Path('/mnt/data/files/09ef27cabe074bfa84b413d786fe075e.zip')
        if not archive.is_file():
            self.skipTest('Private original 3kg evidence is not in the public repository')
        with zipfile.ZipFile(archive) as source:
            member=next(n for n in source.namelist() if n.endswith('/geofield_case.inp'))
            before=source.read(member)
        nodes,loads,fixed,tets={},{},set(),[]
        section=''
        for raw in before.decode('ascii').splitlines():
            line=raw.strip()
            if not line or line.startswith('**'):continue
            if line.startswith('*'):
                section=line.split(',',1)[0].strip().upper();continue
            fields=[x.strip() for x in line.split(',')]
            if section=='*NODE':nodes[int(fields[0])]=[float(x) for x in fields[1:]]
            if section=='*ELEMENT':tets.append(tuple(map(int,fields[1:])))
            if section=='*BOUNDARY':fixed.add(int(fields[0]))
            if section=='*CLOAD':loads.setdefault(int(fields[0]),[0.,0.,0.])[int(fields[1])-1]=float(fields[2])
        counts=Counter(tuple(sorted(t[:i]+t[i+1:])) for t in tets for i in range(4))
        surface=[tri for tri,num in counts.items() if num==1 and all(abs(nodes[n][2])<1e-8 for n in tri)]
        self.assertEqual(len(surface),1146)
        areas=[];cs=[]
        for tri in surface:
            a,b,c=(nodes[n] for n in tri)
            ab=[b[i]-a[i] for i in range(3)]
            ac=[c[i]-a[i] for i in range(3)]
            size=math.sqrt(math.fsum(x*x for x in cross(ab,ac)))/2
            areas.append(size)
            cs.append([math.fsum(nodes[n][k] for n in tri)/3 for k in range(3)])
        area=math.fsum(areas)
        center=[math.fsum(areas[i]*cs[i][k] for i in range(len(surface)))/area for k in range(3)]
        self.assertAlmostEqual(area,1455.54874033402,places=5)
        self.assertAlmostEqual(center[0],25.,places=7)
        self.assertAlmostEqual(center[1],0.,places=7)
        self.assertEqual(len(set(n for tri in surface for n in tri)&fixed),18)
        self.assertEqual(len(loads),609)
        old_moment=moment(nodes,loads)
        proposal=propose_free_node_moment_balance(nodes,loads,fixed,center,[0,0,-1])
        new_moment=moment(nodes,proposal['candidate_loads'])
        expected=cross(center,[0,0,-29.41995])
        self.assertLess(math.dist(new_moment,expected),1e-6)
        self.assertGreater(math.dist(old_moment,expected),11.4)
        self.assertLess(proposal['candidate_center_shift_perpendicular_mm'],1e-7)
        self.assertLess(proposal['relative_nodal_force_changes']['max_absolute_percent'],5.0)
        self.assertEqual(proposal['load_node_count'],609)
        self.assertFalse(proposal['solver_executed'])
        with zipfile.ZipFile(archive) as source:
            self.assertEqual(source.read(member),before)


if __name__=='__main__':unittest.main()
