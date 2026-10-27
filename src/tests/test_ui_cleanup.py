"""UI cleanup regression: preserve the five-step CAD/FEA workflow and records.

Static structure tests, not a claim that Windows/GPU/CalculiX ran.
"""
import re
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'payload'/'frontend'
HTML=(ROOT/'index.html').read_text(encoding='utf-8')
SCRIPT=(ROOT/'cad.js').read_text(encoding='utf-8')

VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}

class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[]
        self.ids=[]
        self.details=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        parent_details=[(info[1] or '') for info in self.stack if info[0]=='details']
        if 'id' in attrs:self.ids.append((attrs['id'],parent_details[:]))
        if tag=='details':
            self.details.append((attrs.get('id'),attrs.get('open') is not None))
        if tag not in VOID:self.stack.append((tag,attrs.get('id')))
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                del self.stack[i:];return

class CleanupContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree=Tree();cls.tree.feed(HTML)
        cls.parents={name:ancestors for name,ancestors in cls.tree.ids}
    def test_no_duplicate_dom_ids(self):
        ids=[id for id,_ in self.tree.ids]
        self.assertEqual([x for x,n in Counter(ids).items() if n>1],[])
    def test_core_ui_remains_accessible(self):
        for name in ('stepFile','importBtn','feaSetFixed','feaSetLoad','feaMaterialPreset',
                     'feaLoadMode','feaLoadQuantity','feaDirectionMode','feaPrepareBtn',
                     'feaRunBtn','feaVerifiedResultTable','resultsOverview'):
            with self.subTest(id=name):
                self.assertIn(name,self.parents)
                self.assertEqual(self.parents[name],[])
    def test_cad_detail_actions_only_in_one_optional_cad_panel(self):
        self.assertIn(('cadDetailedMeasurements',False),self.tree.details)
        for name in ('geometryDimBtn','geometryDimResults',
                     'reviewBtn','integrationReview'):
            with self.subTest(name=name):
                self.assertIn(name,self.parents)
                self.assertEqual(self.parents[name],['cadDetailedMeasurements'])
        self.assertIn("get('/api/geometry/dimensions/'+expectedJob)",SCRIPT)
        self.assertIn("get('/api/integration/decision/'+expectedJob)",SCRIPT)

    def test_optional_ml_is_collapsed_not_deleted(self):
        for name in ('brepMlRunBtn','brepMlResults','r12RunBtn','r12Result',
                     'brepMlPreflight','r12Preflight'):
            with self.subTest(name=name):
                self.assertIn('optionalMlTools',self.parents[name])
        self.assertIn(('optionalMlTools',False),self.tree.details)
        self.assertIn(('optionalResearchAndExternal',False),self.tree.details)
        self.assertIn(('agentOptionalExternal',False),self.tree.details)
        for name in ('brepMlRunBtn','r12RunBtn','agentLLMOptIn'):
            self.assertIn('optionalResearchAndExternal',self.parents[name])
        self.assertIn('agentOptionalExternal',self.parents['agentLLMOptIn'])
        self.assertEqual(self.parents['agentRunBtn'],[])
        self.assertIn("const externalOptIn=$('optionalResearchAndExternal')?.open===true",SCRIPT)
        self.assertIn("$('agentOptionalExternal')?.open===true&&$('agentLLMOptIn')?.checked===true",SCRIPT)
    def test_one_default_verified_archive_search_and_optional_full_history(self):
        # HTMLParser represents bare boolean `open` as (open, None), so
        # verify the literal tag rather than inferring it from attrs.get().
        self.assertRegex(HTML,r'<details[^>]*id="feaOptionalHistory" open>')
        self.assertIn(('feaOptionalHistory',False),self.tree.details)
        self.assertIn(('recordAllAnalysisHistory',False),self.tree.details)
        self.assertIn(('feaArchiveRestoreOptions',False),self.tree.details)
        for id in ('feaArchivedResults','feaArchivedSearch','feaArchivedSelect',
                   'feaArchivedNumbers','feaArchive3DPreviewBtn'):
            with self.subTest(id=id):
                self.assertIn('feaOptionalHistory',self.parents[id])
                self.assertNotIn('recordAllAnalysisHistory',self.parents[id])
                self.assertNotIn('feaArchiveRestoreOptions',self.parents[id])
        self.assertIn('feaArchiveRestoreOptions',self.parents['feaArchivedRestoreBtn'])
        for id in ('historyStage','historySearch','historyMaterial','historyMass',
                   'historyCount','historyList','reloadHistory','historyLoadMore'):
            with self.subTest(id=id):
                self.assertIn('recordAllAnalysisHistory',self.parents[id])
        self.assertEqual(self.parents['feaImportPreviousBtn'],[])

    def test_legacy_records_preserved_but_not_in_main_flow(self):
        for name in ('activeRecords','trashRecords','emptyTrashRecords','recordsSearch','recordList'):
            with self.subTest(name=name):self.assertIn('legacyRecordTools',self.parents[name])
        self.assertIn(('legacyRecordTools',False),self.tree.details)
    def test_mesh_quality_advanced_not_an_extra_default_choice(self):
        self.assertIn('meshQualityDetails',self.parents['feaMeshQuality'])
        self.assertIn(('meshQualityDetails',False),self.tree.details)
    def test_research_tools_remain_accessible(self):
        for name in ('feaCompareRun','feaMeshStudyPanel'):
            with self.subTest(name=name):
                self.assertIn(name,self.parents)
                self.assertIn('recordResearchTools',self.parents[name])
        self.assertIn('previousResearchTools',self.parents['researchList'])
        self.assertIn(('previousResearchTools',False),self.tree.details)
    def test_verified_fea_stress_and_mesh_share_one_advanced_area(self):
        self.assertIn(('recordResearchTools',False),self.tree.details)
        self.assertIn(('feaEvidenceDetailTools',False),self.tree.details)
        groups={'feaStressHotspotPanel':'feaHotspotDetails',
                'feaStressMeshLinkPanel':'feaStressMeshDetails',
                'feaMeshQualityPanel':'feaSingleMeshDetails',
                'feaMeshStudyPanel':'feaMeshStudyDetails'}
        for output,disclosure in groups.items():
            with self.subTest(output=output):
                self.assertIn((disclosure,False),self.tree.details)
                self.assertIn('recordResearchTools',self.parents[output])
                self.assertIn('feaEvidenceDetailTools',self.parents[output])
                self.assertIn(disclosure,self.parents[output])
        for output in ('feaHotspotOpen3D','feaStressHotspotOutput',
                       'feaStressMeshLinkOutput','feaMeshQualityOutput',
                       'feaMeshStudyRun','feaMeshStudyClear','feaMeshStudyOutput'):
            self.assertIn('feaEvidenceDetailTools',self.parents[output])
        self.assertIn('feaEvidenceDetailTools',self.parents['feaCompareRun'])
        self.assertIn('feaEvidenceDetailTools',self.parents['feaMeshStudyRun'])
        stress_group=HTML.split('id="feaStressMeshGroup"',1)[1].split('id="feaCompareMeshGroup"',1)[0]
        compare_group=HTML.split('id="feaCompareMeshGroup"',1)[1].split('id="previousResearchTools"',1)[0]
        for panel in ('feaStressHotspotPanel','feaMeshQualityPanel','feaStressMeshLinkPanel'):
            self.assertIn('id="'+panel+'"',stress_group)
            self.assertNotIn('id="'+panel+'"',compare_group)
        for panel in ('feaComparePanel','feaMeshStudyPanel'):
            self.assertIn('id="'+panel+'"',compare_group)
            self.assertNotIn('id="'+panel+'"',stress_group)
        self.assertTrue(stress_group.index('id="feaStressHotspotPanel"') <
                        stress_group.index('id="feaMeshQualityPanel"') <
                        stress_group.index('id="feaStressMeshLinkPanel"'))
        self.assertIn("gfShowEvidenceDetails('feaComparePanel')",SCRIPT)
        # Real new CalculiX mesh-series jobs stay in FEA, not in historical read-only tools.
        self.assertNotIn('recordResearchTools',self.parents['feaMeshSeriesStartBtn'])

        self.assertIn("gfShowEvidenceDetails('feaHotspotDetails')",SCRIPT)
        self.assertIn("gfShowEvidenceDetails('feaStressMeshDetails')",SCRIPT)
        self.assertIn("gfShowEvidenceDetails('feaSingleMeshDetails')",SCRIPT)
        self.assertIn("gfShowEvidenceDetails('feaMeshStudyDetails')",SCRIPT)
        self.assertIn("summary.textContent='고급 분석·비교 (필요할 때 펼치기)'",SCRIPT)
        self.assertIn("if(item.stage==='fea_result')d.append(advanced)",SCRIPT)
        self.assertIn("restore.onclick=()=>restoreArchivedFea(item,restore);bar.append(restore)",SCRIPT)
        # Newly computed mesh series is not a read-only historical inspection.
        self.assertNotIn('recordResearchTools',self.parents['feaMeshSeriesStartBtn'])

    def test_brep_r12_preflight_only_when_ml_panel_open(self):
        self.assertIn("if($('optionalMlTools').open){loadBrepPreflight();loadR12Preflight();}",SCRIPT)
        tab=SCRIPT[SCRIPT.index('function tabTo('):SCRIPT.index('async function loadFeaPreflight(')]
        self.assertNotIn('loadBrepPreflight()',tab)
        self.assertNotIn('loadR12Preflight()',tab)
    def test_import_skips_expensive_hidden_ml_preflight(self):
        importer=SCRIPT[SCRIPT.index("$('importBtn').onclick"):SCRIPT.index('function renderFindings(')]
        self.assertIn("if($('optionalMlTools').open)loadBrepPreflight();",importer)
        self.assertNotIn('loadR12Preflight()',importer)
        # Import-scoped local ML is still polled, independent of the hidden UI.
        # Its opt-out value is frozen at upload time, not read after import.
        self.assertIn('const automaticMlForImport=autoMlToggle.checked;',importer)
        self.assertIn('void watchAutoMl(jobId,current.sha256,autoMlGeneration,automaticMlForImport)',importer)
    def test_auto_ml_status_poll_no_longer_reloads_full_summary(self):
        watcher=SCRIPT[SCRIPT.index('async function watchAutoMl('):SCRIPT.index("$('brepMlRunBtn').onclick")]
        self.assertNotIn('i%3===0',watcher)
        self.assertEqual(watcher.count('await loadCurrentResults()'),2)
    def test_manual_ml_has_single_final_summary_refresh(self):
        handler=SCRIPT[SCRIPT.index("$('brepMlRunBtn').onclick"):SCRIPT.index("$('reviewBtn').onclick")]
        self.assertEqual(handler.count('loadCurrentResults()'),1)
        self.assertIn('finally{if(generation===autoMlGeneration)',handler)
    def test_old_record_queries_only_when_opened(self):
        self.assertIn("if($('legacyRecordTools').open)loadRecords();",SCRIPT)
        self.assertIn("if($('previousResearchTools').open)loadResearch();",SCRIPT)
        tab=SCRIPT[SCRIPT.index('function tabTo('):SCRIPT.index('async function loadFeaPreflight(')]
        self.assertNotIn('loadRecords()',tab)
        self.assertNotIn('loadResearch()',tab)
    def test_dead_preview_and_redundant_status_requests_removed(self):
        self.assertNotIn('gfFocusAutoArchiveSurface',SCRIPT)
        self.assertNotIn('loadIntegrationPreflight',SCRIPT)
        self.assertNotIn("get('/api/integration/quality')",SCRIPT)
        self.assertNotIn("get('/api/integration/preflight')",SCRIPT)

if __name__=='__main__':
    unittest.main()
