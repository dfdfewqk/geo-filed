"""Actual FEA engine: free-node, force+moment-preserving surface traction approximation.

The user-supplied 3kg archived mesh is optional. Tests never call CalculiX,
change user files, or mistake load-vector equality for solver accuracy.
"""
import ast
import math
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/'payload'/'fea_solver.py'
ARCHIVE=Path('/mnt/data/files/09ef27cabe074bfa84b413d786fe075e.zip')


def load_engine_functions():
    functions={'triangle_area','weighted_surface_force','audit_surface_load',
               'verify_written_inp_cload','write_inp','validate_volume_mesh'}
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    fn=[v for v in tree.body if isinstance(v,ast.FunctionDef) and v.name in functions]
    if {v.name for v in fn} != functions:
        raise AssertionError('Production FEA engine entry point missing')
    scope={'math':math,'Path':Path}
    exec(compile(ast.Module(body=fn,type_ignores=[]),str(SOURCE),'exec'),scope)
    return scope


class ActualEngineSurfaceLoadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine=load_engine_functions()

    def square(self):
        # A 4x4 cell mesh: constraining one *corner* keeps the global
        # moment within the nearby free-node hull with modest reweighting.
        nodes={1+y*5+x:(float(x),float(y),0.)
               for y in range(5) for x in range(5)}
        nodes[26]=(2.,2.,1.)
        triangles=[]
        for y in range(4):
            for x in range(4):
                a=1+y*5+x;b=a+1;c=a+5;d=c+1
                triangles.extend([(a,b,c),(b,d,c)])
        return nodes,triangles

    def test_unshared_surface_remains_original_area_over_three(self):
        nodes,triangles=self.square()
        loads,free_area=self.engine['weighted_surface_force'](nodes,triangles,60.,[0.,0.,-1.])
        self.assertEqual(len(loads),25)
        self.assertAlmostEqual(free_area,16.)
        self.assertAlmostEqual(loads[13][2],-60./16.)
        self.assertAlmostEqual(loads[1][2],-60./96.)
        audit=self.engine['audit_surface_load'](nodes,triangles,loads,set(),60.,[0,0,-1])
        self.assertLess(audit['moment_difference_n_mm'],1e-10)
        self.assertTrue(audit['nominal_surface_pressure_exactly_preserved'])
        self.assertFalse(audit['free_node_force_and_moment_equivalent'])

    def test_shared_fixed_corner_keeps_exact_force_and_moment(self):
        nodes,triangles=self.square()
        loads,free=self.engine['weighted_surface_force'](nodes,triangles,60.,[0,0,-1],{1})
        self.assertNotIn(1,loads)
        self.assertEqual(len(loads),24)
        self.assertLess(free,16.)
        audit=self.engine['audit_surface_load'](nodes,triangles,loads,{1},60.,[0,0,-1])
        self.assertAlmostEqual(sum(p[2] for p in loads.values()),-60.)
        self.assertLess(audit['moment_difference_n_mm'],1e-9)
        self.assertLess(audit['centroid_shift_mm'],1e-9)
        self.assertTrue(audit['free_node_force_and_moment_equivalent'])
        self.assertFalse(audit['nominal_surface_pressure_exactly_preserved'])
        self.assertEqual(audit['shared_fixed_load_nodes_excluded'],1)

    def test_fixed_nodes_never_receive_direct_cload(self):
        nodes,triangles=self.square()
        loads,_=self.engine['weighted_surface_force'](nodes,triangles,50.,(0,0,-1),{1,26})
        self.assertFalse(set(loads) & {1,26})
        self.assertTrue(all(f[2]<0 and f[:2]==[0,0] for f in loads.values()))

    def test_impossible_positive_moment_distribution_rejected(self):
        # Center (1,1,0) lies on remaining nodes' convex-hull boundary;
        # positive loads on all three free nodes cannot achieve exact moment.
        nodes={1:(0.,0.,0.),2:(2.,0.,0.),3:(0.,2.,0.),4:(2.,2.,0.)}
        with self.assertRaisesRegex(ValueError,'모멘트|하중 분배'):
            self.engine['weighted_surface_force'](nodes,[(1,2,3),(2,4,3)],20.,(0,0,-1),{1})

    def test_oblique_direction_preserves_resultant_and_bending_moment(self):
        nodes,triangles=self.square()
        d=(0.,-0.6,-0.8)
        loads,_=self.engine['weighted_surface_force'](nodes,triangles,150.,d,{1})
        a=self.engine['audit_surface_load'](nodes,triangles,loads,{1},150.,d)
        self.assertLess(math.dist(a['applied_resultant_n'],[0.,-90.,-120.]),1e-7)
        self.assertLess(a['moment_difference_n_mm'],1e-8)

    def test_non_surface_fixed_nodes_do_not_change_uniform_triangle_weights(self):
        nodes,triangles=self.square()
        regular,area=self.engine['weighted_surface_force'](nodes,triangles,50.,(0,0,-1))
        alternate,alternate_area=self.engine['weighted_surface_force'](nodes,triangles,50.,(0,0,-1),{26})
        self.assertEqual(regular,alternate)
        self.assertEqual(area,alternate_area)

    def test_fully_fixed_load_surface_rejected(self):
        nodes,triangles=self.square()
        with self.assertRaisesRegex(ValueError,'자유 노드'):
            self.engine['weighted_surface_force'](nodes,triangles,60.,(0,0,-1),set(range(1,26)))

    def test_invalid_direction_and_duplicate_triangles_rejected(self):
        nodes,triangles=self.square()
        with self.assertRaisesRegex(ValueError,'단위 하중 방향'):
            self.engine['weighted_surface_force'](nodes,triangles,60.,(0,0,-2),{1})
        with self.assertRaisesRegex(ValueError,'중복'):
            self.engine['weighted_surface_force'](nodes,triangles+[tuple(reversed(triangles[0]))],60.,(0,0,-1),{1})

    def test_actual_mesh_inp_write_verify_without_ccx(self):
        if not ARCHIVE.is_file():
            self.skipTest('private historical solver archive not available')
        with zipfile.ZipFile(ARCHIVE) as z:
            inp_member=next(v for v in z.namelist() if v.endswith('/geofield_case.inp'))
            before=z.read(inp_member)
        nodes,tets,fixed,old_loads={},[],set(),{}
        section=''
        for raw in before.decode('ascii').splitlines():
            line=raw.strip()
            if not line or line.startswith('**'):continue
            if line.startswith('*'):
                section=line.split(',')[0].upper();continue
            chunks=[c.strip() for c in line.split(',')]
            if section=='*NODE':nodes[int(chunks[0])]=tuple(map(float,chunks[1:4]))
            elif section=='*ELEMENT':tets.append((int(chunks[0]),tuple(map(int,chunks[1:5]))))
            elif section=='*BOUNDARY':fixed.add(int(chunks[0]))
            elif section=='*CLOAD':old_loads.setdefault(int(chunks[0]),[0.,0.,0.])[int(chunks[1])-1]=float(chunks[2])
        surface=Counter(tuple(sorted(t[:i]+t[i+1:])) for _,t in tets for i in range(4))
        load_tris=[tri for tri,count in surface.items() if count==1 and all(abs(nodes[n][2])<1e-8 for n in tri)]
        self.assertEqual(len(load_tris),1146)
        loads,_=self.engine['weighted_surface_force'](nodes,load_tris,29.41995,(0,0,-1),fixed)
        audit=self.engine['audit_surface_load'](nodes,load_tris,loads,fixed,29.41995,(0,0,-1))
        self.assertEqual(len(loads),609)
        self.assertLess(audit['moment_difference_n_mm'],1e-6)
        self.assertAlmostEqual(audit['applied_force_centroid_mm'][0],25.,places=6)
        self.assertLess(max(abs(loads[n][2]/old_loads[n][2]-1) for n in loads),.06)
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'geofield_case.inp'
            self.engine['write_inp'](out,nodes,tets,fixed,loads,69000.,.33)
            serialized=self.engine['verify_written_inp_cload'](out,nodes,loads,fixed,audit)
            self.assertTrue(serialized['written_inp_cload_verified'])
            self.assertLess(math.dist(serialized['inp_applied_moment_n_mm'],audit['nominal_moment_about_origin_n_mm']),1e-6)
            self.assertIn('*CLOAD',out.read_text())
        with zipfile.ZipFile(ARCHIVE) as z:
            self.assertEqual(z.read(inp_member),before)


if __name__=='__main__':unittest.main()
