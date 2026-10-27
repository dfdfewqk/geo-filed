"""Contract of saved FEA element mode, historic case identity and UI opt-in.

No private installed CAD engine, user file, SQLite data or real solver needed.
"""
from __future__ import annotations

import ast
import copy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fea_mesh_series import mesh_cases


def hash_case(case):
    c = {k:v for k,v in case.items() if k!='case_sha256'}
    return hashlib.sha256(json.dumps(c,sort_keys=True,ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()


def load_case_mode_function():
    # Runtime server imports proprietary engines not available in GitHub CI.
    # Compile ONLY the audited, self-contained real source function.
    filename = ROOT/'payload'/'GeoField_CAD_Analysis.py'
    tree=ast.parse(filename.read_text(encoding='utf-8'))
    func=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='set_fea_element_mode']
    if len(func)!=1:raise AssertionError('Server save-time FEA mode function missing/duplicated')
    scope={'hashlib':hashlib,'json':json}
    module=ast.Module(body=func,type_ignores=[])
    exec(compile(ast.fix_missing_locations(module),str(filename),'exec'),scope)
    return scope['set_fea_element_mode']


class _ElementPicker(HTMLParser):
    def __init__(self):
        super().__init__();self.in_picker=False;self.pickers=0;self.options=[];self.defaults=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='select' and attrs.get('id')=='feaElementMode':
            self.pickers+=1;self.in_picker=True
        elif self.in_picker and tag=='option':
            self.options.append(attrs.get('value'))
            if 'selected' in attrs:self.defaults.append(attrs.get('value'))
    def handle_endtag(self,tag):
        if tag=='select' and self.in_picker:self.in_picker=False


class C3D10FEACaseAndHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepare=staticmethod(load_case_mode_function())
        cls.html=(ROOT/'payload'/'frontend'/'index.html').read_text(encoding='utf8')
        cls.js=(ROOT/'payload'/'frontend'/'cad.js').read_text(encoding='utf8')

    def old_case(self):
        c={'schema':'geofield-fea-case-v1','cad_sha256':'a'*64,
           'mesh_request':{'target_element_size_mm':3.,'volume_mesh_generated':False},
           'boundary_conditions':{'total_force_n':29.41995,'force_direction_unit':[0,0,-1]},
           'status':'configuration_prepared_solver_not_connected',
           'cautions':['Existing legacy warning.']}
        c['case_sha256']=hash_case(c)
        return c

    def test_legacy_default_unchanged_including_sha(self):
        prior=self.old_case(); snapshot=copy.deepcopy(prior)
        returned=self.prepare(prior,{'apply_self_weight':True})
        self.assertEqual(returned,snapshot)
        self.assertIs(returned,prior)
        self.assertNotIn('element_type',returned['mesh_request'])

    def test_three_modes_keep_distinct_record_and_restore_identity(self):
        base=self.old_case()
        regular=self.prepare(base,{'fea_element_mode':'c3d4','apply_self_weight':False})
        old_quad=self.prepare(base,{'fea_element_mode':'c3d10','apply_self_weight':False})
        new_quad=self.prepare(base,{'fea_element_mode':'c3d10_full','apply_self_weight':False})
        self.assertEqual(regular['case_sha256'],base['case_sha256'])
        self.assertEqual(old_quad['mesh_request']['element_type'],'C3D10')
        self.assertNotIn('traction_model',old_quad['mesh_request'])
        self.assertEqual(new_quad['mesh_request']['traction_model'],'straight_tri6_full_consistent')
        self.assertEqual(len({c['case_sha256'] for c in (regular,old_quad,new_quad)}),3)
        self.assertEqual(hash_case(old_quad),old_quad['case_sha256'])
        self.assertEqual(hash_case(new_quad),new_quad['case_sha256'])
        self.assertNotIn('element_type',base['mesh_request'])
        self.assertEqual(base['cautions'],['Existing legacy warning.'])

    def test_unsafe_mode_and_gravity_blocked_before_persistence(self):
        for x in ('C3D10','full','',None,True,{},['c3d10_full']):
            with self.subTest(mode=x):
                with self.assertRaises(ValueError):
                    self.prepare(self.old_case(),{'fea_element_mode':x,'apply_self_weight':False})
        for req in ({'fea_element_mode':'c3d10_full','apply_self_weight':True},
                    {'fea_element_mode':'c3d10_full'}):
            with self.assertRaisesRegex(ValueError,'자중'):
                self.prepare(self.old_case(),req)

    def test_mesh_sensitivity_keeps_signed_element_mode_without_mutating_saved_case(self):
        base=self.prepare(self.old_case(),{'fea_element_mode':'c3d10_full','apply_self_weight':False})
        old=copy.deepcopy(base)
        studies=mesh_cases(base)
        self.assertEqual(len(studies),3)
        self.assertEqual(base,old)
        self.assertEqual({s['mesh_request']['element_type'] for s in studies},{'C3D10'})
        self.assertEqual({s['mesh_request']['traction_model'] for s in studies},
                         {'straight_tri6_full_consistent'})
        self.assertEqual(len({s['case_sha256'] for s in studies}|{base['case_sha256']}),4)
        for case in studies:self.assertEqual(case['case_sha256'],hash_case(case))

    def test_ui_is_one_advanced_control_and_changes_invalidate_saved_case(self):
        p=_ElementPicker();p.feed(self.html)
        self.assertEqual(p.pickers,1)
        self.assertEqual(p.options,['c3d4','c3d10','c3d10_full'])
        self.assertEqual(p.defaults,['c3d10_full'], 'New browser FEA case must start with validated quadratic full Tri6, not legacy C3D4')
        # Read only the selector markup, never alter the old server default
        # and never overwrite the saved historical C3D4 SHA/mesh case.
        import re
        quality=re.search(r'<select id="feaMeshQuality">(.*?)</select>',self.html,re.S)
        self.assertIsNotNone(quality)
        self.assertRegex(quality.group(1),r'<option value="fine" selected>')
        self.assertIn('id="feaOwnWeight"',self.html)
        self.assertIn("if(mode!=='c3d4')request.fea_element_mode=mode",self.js)
        self.assertIn("'feaMeshQuality','feaElementMode'",self.js)
        self.assertIn("if(mode!=='c3d4')request.fea_element_mode=mode",self.js)
        self.assertIn("const expectedElement=mode==='c3d4'?'C3D4':'C3D10'",self.js)
        self.assertIn("'straight_tri6_full_consistent'",self.js)
        self.assertIn("gfFeaTableShow('현재 CAD · 실제 CalculiX 새 계산'",self.js)

    def test_backend_saves_the_mode_and_existing_run_restores_exact_case_sha(self):
        backend=(ROOT/'payload'/'GeoField_CAD_Analysis.py').read_text(encoding='utf-8')
        self.assertIn('case=set_fea_element_mode(',backend)
        self.assertIn("prepare_fea_case(job['analysis'],model['mesh'],arg),arg)",backend)
        self.assertIn("case['case_sha256']",backend)
        self.assertIn("result.get('case_sha256')",backend)
        self.assertIn("find_valid_previous(",backend)
        self.assertIn("'result_case_sha256'",backend)


if __name__=='__main__':
    unittest.main()
