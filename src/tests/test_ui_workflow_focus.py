"""GeoField focused STEP -> FEA -> verified results / AI UI regression.

Inspect actual HTML and JavaScript files. No browser/user CAD/solver data is
required; full runtime and asynchronous integration tests run separately.
"""
from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]/"payload"/"frontend"
HTML=(ROOT/"index.html").read_text(encoding="utf8")
JS=(ROOT/"cad.js").read_text(encoding="utf8")


class Tags(HTMLParser):
    void={"meta","input","link","br","hr","img","source","area","wbr"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[]
        self.ids={}
        self.errors=[]
        self.details=[]
    def handle_starttag(self,name,attrs):
        attributes=dict(attrs)
        if name=="details":
            self.details.append(attributes.get("id") or "(unnamed)")
        if attributes.get("id"):
            self.ids[attributes["id"]]=tuple(self.details)
        if name not in self.void:
            self.stack.append((name,self.getpos()[0]))
    def handle_startendtag(self,name,attrs):
        self.handle_starttag(name,attrs)
        if name not in self.void:
            self.handle_endtag(name)
    def handle_endtag(self,name):
        if name in self.void:
            return
        if not self.stack:
            self.errors.append("Closing without opening: "+name)
            return
        if self.stack[-1][0]!=name:
            self.errors.append("Mismatched close: "+name+
                               " after "+self.stack[-1][0]+":"+str(self.stack[-1][1]))
            # Keep checking later structures even if an existing HTML section
            # was already malformed; the test will fail anyway.
            for i in range(len(self.stack)-1,-1,-1):
                if self.stack[i][0]==name:
                    del self.stack[i:]
                    break
        else:
            self.stack.pop()
        if name=="details" and self.details:
            self.details.pop()


class FocusedWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dom=Tags()
        cls.dom.feed(HTML)
        cls.dom.close()

    def test_html_structure_balanced_and_all_ids_unique(self):
        self.assertEqual(self.dom.errors,[])
        self.assertEqual(self.dom.stack,[])
        ids=re.findall(r'\bid="([^"]+)"',HTML)
        self.assertTrue(len(ids)>=150)
        self.assertEqual([name for name,n in Counter(ids).items() if n!=1],[])

    def test_all_real_js_id_references_still_exist(self):
        refs=set(re.findall(r"\$\('([A-Za-z0-9_]+)'\)",JS))
        # Only optional FEA display/history containers are created at runtime.
        dynamic={"gfFocusArchiveDetails","gfFocusDisplayDetails"}
        self.assertEqual(refs-set(self.dom.ids),dynamic)
        self.assertIn("function gfFocusOrganizeUI()",JS)

    def test_essential_tabs_still_exist_and_results_remain_primary(self):
        tabs=re.findall(r'data-tab="([^"]+)"',HTML)
        self.assertEqual(tabs,["cad","fea","integration","records"])
        panes=re.findall(r'data-pane="([^"]+)"',HTML)
        self.assertEqual(panes,tabs)
        self.assertIn("const gfPrimaryMenus=['cad','fea','integration','records']",JS)
        self.assertNotIn("gfFocusMoreMenu",JS)
        self.assertIn("③ 결과·AI",HTML)
        self.assertIn("② FEA",HTML)
        self.assertIn("④ 기록",HTML)
        self.assertIn("① CAD",HTML)

    def test_legacy_geometry_clicks_now_open_integrated_cad_inspection(self):
        self.assertNotIn('data-pane="geometry"',HTML)
        self.assertNotIn('data-tab="geometry"',HTML)
        self.assertIn("const pane=t==='geometry'?'cad':t;",JS)
        self.assertEqual(JS.count("tabTo('geometry')"),2)
        self.assertEqual(self.dom.ids["findings"],())
        self.assertEqual(self.dom.ids["stats"],())
        self.assertTrue(HTML.index('id="stats"')<HTML.index('id="findings"'))
        self.assertLess(HTML.index('id="findings"'),HTML.index('data-pane="fea"'))
        self.assertIn("CAD 형상 검사·홀 후보",HTML)

    def test_main_3d_viewer_is_persistent_outside_all_sidebar_panes(self):
        self.assertEqual(HTML.count('id="scene"'),1)
        self.assertEqual(HTML.count('id="feaOverlay"'),1)
        self.assertEqual(HTML.count('id="sceneWrap"'),1)
        self.assertLess(HTML.index('</aside><main>') if '</aside><main>' in HTML else
                        HTML.index('</aside>'),HTML.index('<canvas id="scene"'))
        self.assertGreater(HTML.index('<canvas id="scene"'),HTML.index('<main>'))
        nav=JS[JS.index("function tabTo(t)"):JS.index("async function loadFeaPreflight")]
        self.assertIn("document.querySelectorAll('[data-pane]')",nav)
        self.assertIn("draw();",nav)
        self.assertNotIn("innerHTML",nav)
        self.assertNotIn("remove()",nav)
        self.assertNotIn("replaceChildren",nav)

    def test_fea_save_and_run_above_advanced_history(self):
        pane=HTML.split('data-pane="fea"',1)[1].split('data-pane="integration"',1)[0]
        # Material first, then 3D faces, loading, save, previous/new action,
        # verified numerical results. Advanced/historic inputs remain hidden.
        order=["id=\"feaMaterialPreset\"",
               "id=\"feaSetFixed\"","id=\"feaSetLoad\"",
               "id=\"feaLoadQuantity\"","id=\"feaDirectionMode\"",
               "id=\"feaOwnWeight\"","id=\"feaPrepareBtn\"",
               "id=\"feaImportPreviousBtn\"","id=\"feaRunBtn\"",
               "id=\"feaRunStatus\"","id=\"feaVerifiedResultTable\"",
               "id=\"feaArchivedResults\""]
        positions=[pane.index(item) for item in order]
        self.assertEqual(positions,sorted(positions))
        self.assertEqual(self.dom.ids["feaRunBtn"],())
        self.assertEqual(self.dom.ids["feaRunStatus"],())
        # The verified current FEA table must NOT disappear with historic
        # runs; it is the main numerical output after a live calculation.
        self.assertEqual(self.dom.ids["feaVerifiedResultTable"],())
        self.assertEqual(self.dom.ids["feaVerifiedTableBody"],())
        self.assertIn("feaOptionalHistory",self.dom.ids["feaArchivedResults"])
        self.assertEqual(self.dom.ids["feaImportPreviousBtn"],())
        self.assertEqual(self.dom.ids["feaPreviousHint"],())
        self.assertIn("feaOptionalHistory",self.dom.ids["feaArchivedSelect"])
        self.assertEqual(self.dom.ids["feaForceDistributionStatus"],())
        self.assertIn("feaOptionalColorRange",self.dom.ids["feaStressScaleMode"])
        self.assertNotIn("feaOptionalColorRange",self.dom.ids["feaContourMode"])

    def test_fea_stage2_unmodified_handler_contract_and_no_dom_reorder(self):
        pane=HTML.split('data-pane="fea"',1)[1].split('data-pane="integration"',1)[0]
        for wrapper in ('feaMaterialStep','feaFaceStep','feaLoadStep',
                        'feaCalculationActions','feaCurrentResults'):
            self.assertEqual(pane.count('id="'+wrapper+'"'),1)
        self.assertIn('class="gf-fea-choice"',pane)
        self.assertTrue(pane.index('id="feaImportPreviousBtn"')<pane.index('id="feaRunBtn"'))
        self.assertEqual(self.dom.ids["feaMaterialPreset"],())
        self.assertEqual(self.dom.ids["feaOwnWeight"],())
        self.assertIn("meshQualityDetails",self.dom.ids["feaMeshQuality"])
        self.assertEqual(self.dom.ids["feaContourMode"],())
        self.assertEqual(HTML.count('id="feaRunBtn"'),1)
        self.assertEqual(HTML.count('id="feaImportPreviousBtn"'),1)
        self.assertNotIn("prep.insertAdjacentElement('afterend',run)",JS)
        self.assertNotIn("run.insertAdjacentElement('afterend',result)",JS)
        self.assertIn("$('feaImportPreviousBtn').onclick",JS)
        self.assertIn("$('feaRunBtn').onclick",JS)
        self.assertIn("$('feaPrepareBtn').onclick",JS)
        self.assertIn("feaLoadMode",pane)
        self.assertIn('value="mass_kg"',pane)
        self.assertIn('value="force_n"',pane)
        self.assertIn('value="example_100n"',pane)

    def test_important_fea_values_not_hidden_by_legacy_reorganizer(self):
        self.assertIn('id="feaStressValue"',HTML)
        self.assertIn('id="feaDispValue"',HTML)
        self.assertNotIn("classList.add('gf-focus-duplicate-value')",JS)
        self.assertIn("archive.closest('#feaOptionalHistory')",JS)
        self.assertIn("const controls=[$('feaDeformToggle')?.closest('label'),",JS)

    def test_optional_ml_and_external_ai_cannot_be_mistaken_for_real_fea(self):
        self.assertTrue(self.dom.ids["autoMlToggle"])
        self.assertIn("optionalMlTools",self.dom.ids["brepMlRunBtn"])
        self.assertIn("optionalMlTools",self.dom.ids["r12RunBtn"])
        self.assertIn("agentOptionalExternal",self.dom.ids["agentLLMOptIn"])
        self.assertEqual(self.dom.ids["agentRunBtn"],())
        self.assertEqual(self.dom.ids["agentResult"],())
        self.assertEqual(self.dom.ids["geometryDimBtn"],())
        self.assertEqual(self.dom.ids["reviewBtn"],())
        self.assertTrue(HTML.index('id="resultsOverview"')<HTML.index('id="agentRunBtn"'))
        self.assertTrue(HTML.index('id="agentRunBtn"')<HTML.index('id="optionalMlTools"'))
        self.assertIn("외부 LLM이나 미연결 학습 모델의 답변이 아닙니다",HTML)
        self.assertIn("실제 계산",HTML)
        self.assertIn("구조 안전 인증",HTML)

    def test_results_auto_refresh_remains_after_removing_manual_button(self):
        # Basic UI simplification: remove only the redundant manual refresh.
        # The real current-CAD results must still update on import, tab visit,
        # FEA preparation, linking an existing run and completing a new run.
        self.assertNotIn('id="resultsRefreshBtn"',HTML)
        self.assertNotIn('resultsRefreshBtn',JS)
        self.assertIn('id="resultsOverview"',HTML)
        self.assertIn('id="resultsReportBtn"',HTML)
        self.assertIn("if(pane==='integration')loadCurrentResults();",JS)
        self.assertIn('renderInfo(current);renderFindings();',JS)
        self.assertRegex(JS,r'renderFindings\(\);[^\n]*loadCurrentResults\(\);')
        self.assertIn('await loadCurrentResults();',JS)
        self.assertIn('async function loadCurrentResults()',JS)
        for marker in (
            "$('feaPrepareBtn').onclick",
            "$('feaImportPreviousBtn').onclick",
            "$('feaRunBtn').onclick",
        ):
            start=JS.index(marker)
            end=JS.find("\n$('",start+len(marker))
            if end<0:end=len(JS)
            self.assertIn("loadCurrentResults()",JS[start:end],marker)

    def test_no_backend_or_request_contract_is_changed(self):
        for signature in (
          "$('feaSetFixed').onclick",
          "$('feaSetLoad').onclick",
          "$('feaPrepareBtn').onclick",
          "$('feaRunBtn').onclick",
          "$('agentRunBtn').onclick",
          "$('feaArchivedRestoreBtn').onclick",
          "$('resultsReportBtn').onclick",
          "gf_agent_evaluate",
        ):
            with self.subTest(signature=signature):
                self.assertIn(signature,JS if signature!="gf_agent_evaluate" else
                              (ROOT.parent/"GeoField_CAD_Analysis.py").read_text(encoding="utf8"))
        self.assertIn('/api/agent/evidence/',JS)
        self.assertIn('/api/results/summary/',JS)
        self.assertIn('/api/fea/preflight',JS)


if __name__=="__main__":
    unittest.main()
