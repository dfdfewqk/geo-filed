"""Production FEA engine step 3: fixed reaction force/moment evidence.

Exercises real write_inp and parse_fixed_reactions_dat functions extracted
from existing solver; no fabricated CalculiX execution is claimed.
"""
import ast
import math
import tempfile
import unittest
import zipfile
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/'payload'/'fea_solver.py'
ARCHIVE=Path('/mnt/data/files/09ef27cabe074bfa84b413d786fe075e.zip')


def extract_functions():
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    names={'write_inp','parse_fixed_reactions_dat','validate_volume_mesh','parse_frd_results'}
    functions=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names]
    assert {x.name for x in functions} == names
    import re
    scope={'Path':Path,'math':math,'re':re,'EXP_RE':re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)[EeDd][-+]?\d+')}
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(SOURCE),'exec'),scope)
    return scope


class ReactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.funcs=extract_functions()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dat=Path(self.tmp.name)/'geofield_case.dat'
        self.nodes={1:(0.,0.,0.),2:(2.,0.,0.),3:(0.,2.,0.),4:(1.,1.,0.)}
        self.fixed={1,2,3}
        self.loads={4:[0.,0.,-10.]}

    def write(self, rows, time=1., header='forces (fx,fy,fz) for set GEOFIELD_FIXED and time'):
        text=f' S T E P 1\n INCREMENT 1\n\n {header} {time:.7E}\n\n'
        text+='\n'.join(f' {n} {v[0]:.6E} {v[1]:.6E} {v[2]:.6E}' for n,v in rows.items())+'\n\n'
        self.dat.write_text(text,encoding='ascii')

    def balanced(self):
        return {1:[0.,0.,0.],2:[0.,0.,5.],3:[0.,0.,5.]}

    def audit(self,**kw):
        return self.funcs['parse_fixed_reactions_dat'](self.dat,self.nodes,self.fixed,self.loads,**kw)

    def test_real_synthetic_equilibrium_force_and_moment(self):
        self.write(self.balanced())
        result=self.audit()
        self.assertTrue(result['checked'])
        self.assertEqual(result['fixed_nodes_verified'],3)
        self.assertLess(result['moment_residual_magnitude_n_mm'],1e-10)
        self.assertLess(result['force_residual_magnitude_n'],1e-10)

    def test_incorrect_force_is_rejected(self):
        self.write({1:[0.,0.,0.],2:[0.,0.,4.],3:[0.,0.,5.]})
        with self.assertRaisesRegex(ValueError,'평형'):
            self.audit()

    def test_incorrect_moment_is_rejected_even_if_force_balances(self):
        self.write({1:[0.,0.,0.],2:[0.,0.,7.],3:[0.,0.,3.]})
        with self.assertRaisesRegex(ValueError,'평형'):
            self.audit()

    def test_missing_fixed_reaction_rejected(self):
        self.write({1:[0.,0.,0.],2:[0.,0.,5.]})
        with self.assertRaisesRegex(ValueError,'누락'):
            self.audit()

    def test_extra_nonfixed_node_rejected(self):
        self.write({**self.balanced(),4:[0.,0.,0.]})
        with self.assertRaisesRegex(ValueError,'미등록'):
            self.audit()

    def test_duplicate_reaction_row_rejected(self):
        self.write(self.balanced())
        # A second occurrence inside the same RF block, before its terminator.
        self.dat.write_text(self.dat.read_text().rstrip()+'\n 2 0.00000E+00 0.00000E+00 5.00000E+00\n\n')
        with self.assertRaisesRegex(ValueError,'중복'):
            self.audit()

    def test_truncated_final_time_rejected(self):
        self.write(self.balanced(),time=.8)
        with self.assertRaisesRegex(ValueError,'최종'):
            self.audit()

    def test_double_increment_uses_latest(self):
        self.write(self.balanced(),time=1.)
        valid=self.dat.read_text()
        earlier=valid.replace('1.0000000E+00','5.0000000E-01').replace('5.000000E+00','9.000000E+00')
        self.dat.write_text(earlier+'\n'+valid,encoding='ascii')
        self.assertTrue(self.audit()['checked'])

    def test_fake_nset_cannot_substitute_fixed(self):
        self.write(self.balanced(),header='forces (fx,fy,fz) for set OTHER and time')
        with self.assertRaisesRegex(ValueError,'GEOFIELD_FIXED'):
            self.audit()

    def test_gravity_dload_does_not_claim_reactions(self):
        result=self.audit(gravity_present=True)
        self.assertFalse(result['checked'])
        self.assertIn('gravity',result['status'])

    def test_reaction_with_fixed_cload_rejected(self):
        self.write(self.balanced())
        self.loads[2]=[1.,0.,0.]
        with self.assertRaisesRegex(ValueError,'고정 노드'):
            self.audit()

    def test_new_inp_requests_fixed_nset_and_dat_reaction(self):
        # A single, valid C3D4 element; 3 DOF constrained at base.
        nodes={1:(0.,0.,0.),2:(1.,0.,0.),3:(0.,1.,0.),4:(0.,0.,1.)}
        self.funcs['write_inp'](self.dat.with_suffix('.inp'),nodes,[(1,[1,2,3,4])],{1,2,3},{4:[0.,0.,-3.]},69000.,.33)
        inp=self.dat.with_suffix('.inp').read_text(encoding='ascii')
        self.assertIn('*NSET, NSET=GEOFIELD_FIXED\n1, 2, 3\n',inp)
        self.assertIn('*NODE PRINT, NSET=GEOFIELD_FIXED, GLOBAL=YES, TOTALS=NO\nRF\n',inp)
        self.assertIn('*NODE FILE\nU\n*EL FILE\nS',inp)

    def test_actual_archived_frd_matches_old_verified_extrema_no_retroactive_rf(self):
        if not ARCHIVE.is_file():
            self.skipTest('Historical private INP/STA/FRD archive not available')
        with zipfile.ZipFile(ARCHIVE) as z:
            inp=z.read(next(x for x in z.namelist() if x.endswith('/geofield_case.inp'))).decode('ascii')
            frd=z.read(next(x for x in z.namelist() if x.endswith('/geofield_case.frd')))
            dat=z.read(next(x for x in z.namelist() if x.endswith('/geofield_case.dat')))
        self.assertEqual(dat,b'')  # historical run did NOT print support reactions
        nodes=set(); section=''
        for line in inp.splitlines():
            s=line.strip()
            if s.startswith('*'):section=s.split(',')[0].upper();continue
            if section=='*NODE' and s and not s.startswith('**'):nodes.add(int(s.split(',')[0]))
        p=Path(self.tmp.name)/'archive.frd';p.write_bytes(frd)
        data=self.funcs['parse_frd_results'](p,nodes)
        self.assertAlmostEqual(data['maximum_nodal_von_mises_mpa'],9.183541168,places=5)
        self.assertAlmostEqual(data['maximum_displacement_mm'],0.0131454359,places=6)


if __name__=='__main__':unittest.main()
