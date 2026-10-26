"""Physics engine regression: face-connected C3D4 mesh is mandatory.

Uses the actual solver function via AST, avoiding the absent optional Gmsh/ccx
runtime dependencies. An archived real INP fixture is checked read-only.
"""
import ast
import math
import zipfile
import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / 'payload' / 'fea_solver.py'
ARCHIVE = Path('/mnt/data/files/09ef27cabe074bfa84b413d786fe075e.zip')


def load_mesh_validator():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    funcs = [x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == 'validate_volume_mesh']
    if len(funcs) != 1:
        raise AssertionError('Solver mesh validation entry point missing')
    scope = {'math': math}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(SOURCE), 'exec'), scope)
    return scope['validate_volume_mesh']


class FaceConnectivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.check = staticmethod(load_mesh_validator())

    def test_two_face_connected_tets_pass(self):
        n = {1:(0,0,0), 2:(1,0,0), 3:(0,1,0), 4:(0,0,1), 5:(0,0,-1)}
        t = [(1,[1,2,3,4]),(2,[1,3,2,5])]
        result = self.check(n,t)
        self.assertEqual(result['verified_tets'], 2)
        self.assertAlmostEqual(result['tetrahedral_volume_mm3'], 1/3)

    def test_two_disjoint_positive_volume_tets_rejected(self):
        n = {1:(0,0,0), 2:(1,0,0), 3:(0,1,0), 4:(0,0,1),
             5:(4,0,0), 6:(5,0,0), 7:(4,1,0), 8:(4,0,1)}
        with self.assertRaisesRegex(ValueError, '면으로 연결되지 않은'):
            self.check(n, [(1,[1,2,3,4]),(2,[5,6,7,8])])

    def test_vertex_touching_without_shared_face_rejected(self):
        n = {1:(0,0,0), 2:(1,0,0), 3:(0,1,0), 4:(0,0,1),
             5:(-1,0,0), 6:(0,-1,0), 7:(0,0,1.5)}
        with self.assertRaisesRegex(ValueError, '면으로 연결되지 않은'):
            self.check(n, [(1,[1,2,3,4]),(2,[1,5,6,7])])

    def test_three_tets_on_same_triangle_rejected(self):
        n = {1:(0,0,0), 2:(1,0,0), 3:(0,1,0), 4:(0,0,1),
             5:(0,0,-1), 6:(0,0,2)}
        with self.assertRaisesRegex(ValueError, '비다양체'):
            self.check(n, [(1,[1,2,3,4]),(2,[1,3,2,5]),(3,[1,2,3,6])])

    def test_duplicate_tet_connectivity_rejected(self):
        n = {1:(0,0,0), 2:(1,0,0), 3:(0,1,0), 4:(0,0,1)}
        with self.assertRaisesRegex(ValueError, '중복 연결'):
            self.check(n, [(1,[1,2,3,4]),(2,[2,3,1,4])])

    def test_inverted_tet_still_rejected(self):
        n = {1:(0,0,0), 2:(1,0,0), 3:(0,1,0), 4:(0,0,1)}
        with self.assertRaisesRegex(ValueError, '반전/퇴화'):
            self.check(n, [(1,[1,3,2,4])])

    def test_real_three_kg_archive_remains_valid(self):
        if not ARCHIVE.is_file():
            self.skipTest('Private archived INP not packaged in public GitHub')
        with zipfile.ZipFile(ARCHIVE) as z:
            name = next(x for x in z.namelist() if x.endswith('/geofield_case.inp'))
            source = z.read(name)
        nodes, tets, section = {}, [], ''
        for line in source.decode('ascii').splitlines():
            line=line.strip()
            if line.startswith('*'):
                section=line.split(',')[0].upper()
                continue
            if not line or line.startswith('**'):
                continue
            parts = [x.strip() for x in line.split(',')]
            if section == '*NODE':
                nodes[int(parts[0])] = tuple(map(float, parts[1:4]))
            elif section == '*ELEMENT':
                tets.append((int(parts[0]), list(map(int, parts[1:5]))))
        result = self.check(nodes, tets)
        self.assertEqual(result['verified_nodes'],2798)
        self.assertEqual(result['verified_tets'],8611)
        self.assertAlmostEqual(result['tetrahedral_volume_mm3'],8457.9450,places=2)


if __name__ == '__main__':
    unittest.main()
