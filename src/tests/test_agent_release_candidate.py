"""AI stage 9: inspect the REAL A+B+AI candidate assembled in a scratch merge.

No actual Gmsh, CalculiX, native desktop CAD, external LLM or user's private
runtime data is accessed. The staged ZIP remains an UPDATE CANDIDATE only.
Requires the checkout's work/fea-validation ref and origin/main for provenance.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import build_integration_candidate as assembler
import installer
import runtime_preflight

class AgentIntegrationPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="gf-agent-abc-package-")
        cls.directory=Path(cls.temp.name)
        cls.stage=cls.directory/"candidate"
        cls.manifest=assembler.build(cls.stage)
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def test_agent_cad_ml_fea_ui_are_exact_source_bytes(self):
        for name in ("GeoField_CAD_Analysis.py","frontend/cad.js","frontend/index.html",
                     "fea_solver.py","fea_result_trust_gate.py"):
            with self.subTest(name=name):
                expected=(ROOT/"payload"/name).read_bytes()
                actual=(self.stage/"payload"/name).read_bytes()
                self.assertEqual(expected,actual)
                self.assertEqual(self.manifest["files"][name]["to"],
                                 hashlib.sha256(actual).hexdigest())
    def test_A_provenance_is_merged_into_verified_package(self):
        for name in assembler.NEW_RUNTIME:
            with self.subTest(name=name):
                data=(self.stage/"payload"/name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),
                                 self.manifest["files"][name]["to"])
        lock=json.loads((self.stage/"CANDIDATE_SOURCE_LOCK.json").read_text(encoding="utf8"))
        self.assertEqual(lock["source_revisions"]["a_fea_branch"],
                         assembler._revision("refs/remotes/origin/work/fea-validation"))
        self.assertEqual(lock["source_revisions"]["b_branch_checkout"],
                         assembler._revision("HEAD"))
        self.assertEqual(lock["status"],"TEST_CANDIDATE_NOT_FINAL")
        self.assertFalse(lock["production_release_approved"])
        self.assertEqual(lock["required_payload_count"],17)
        self.assertEqual(lock["real_calculix_study"],"NOT_VERIFIED_BY_PACKAGE_BUILD")
        self.assertEqual(lock["actual_user_windows_test"],"NOT_VERIFIED_BY_PACKAGE_BUILD")
        self.assertEqual(len(self.manifest["files"]),17)
    def test_included_real_agent_logic_and_explicit_opt_in_screen(self):
        server=(self.stage/"payload/GeoField_CAD_Analysis.py").read_text(encoding="utf8")
        browser=(self.stage/"payload/frontend/cad.js").read_text(encoding="utf8")
        html=(self.stage/"payload/frontend/index.html").read_text(encoding="utf8")
        for name in ("def gf_agent_evaluate(", "def gf_agent_compare_verified_runs(",
                     "def gf_agent_restored_context(", "def gf_agent_llm_optional(",
                     "response['restore_evidence']=gf_agent_restored_context(",
                     "gf_agent_assert_restore_session(session,current_session)"):
            with self.subTest(name=name):
                self.assertIn(name,server)
        for name in ("gfRestoredRunId", "agentLLMOptIn", "restore_evidence",
                     "FEA 복원 출처", "외부 LLM 참고 설명"):
            with self.subTest(name=name):
                self.assertIn(name,browser)
        self.assertIn('id="agentLLMOptIn"',html)
        self.assertIn('id="agentRunBtn"',html)
        self.assertIn("data['agent_review']=gf_agent_compare_verified_runs(data)",server)
    def test_candidate_is_an_update_not_new_full_engine_or_user_data(self):
        targets=set(installer.ALLOWED_TARGETS)
        self.assertEqual(targets,set(self.manifest["files"]))
        missing_existing=set(runtime_preflight.EXISTING_REQUIRED)-targets
        self.assertIn("cad_common.py",missing_existing)
        self.assertIn("engine_runtime.py",missing_existing)
        self.assertIn("fea_previous_import.py",missing_existing)
        for name in ("cad_common.py","engine_runtime.py","history_store.py",
                     "fea_previous_import.py","ml/brepmfr_worker.py"):
            self.assertFalse((self.stage/"payload"/name).exists())
        self.assertFalse(any(x in targets for x in ("geofield_review_history.sqlite3",
            "L_bracket.step","geofield_case.frd","geofield_case.inp",
            "geofield_case.sta","GEOFIELD_AGENT_LLM_API_KEY")))
        self.assertFalse(any(str(x).endswith((".step",".frd",".sta",".inp",".sqlite3"))
                for x in (self.stage/"payload").rglob("*") if x.is_file()))
        self.assertFalse((self.stage/"payload"/"src").exists())
    def test_approved_ancestor_source_hashes_are_in_candidate_compatibility(self):
        # The user may run an earlier commit of A, CAD, or AI; an exact tracked
        # old file is safe to upgrade, but arbitrary edited code is never
        # authorized. Hashes are anchored to immutable reviewed Git tips.
        known = assembler.trusted_prior_hashes("frontend/cad.js")
        self.assertGreaterEqual(len(known), 3)
        known_shas=set(known.values())
        meta=self.manifest["files"]["frontend/cad.js"]
        self.assertTrue(known_shas.issubset(
            set(meta.get("compatible_from", [])) | {meta["to"]}))
        # The five user's failing files all use exactly the same policy.
        for name in ("GeoField_CAD_Analysis.py","frontend/cad.js",
                     "frontend/index.html","ml_env_resolver.py","ml_r12_bridge.py"):
            with self.subTest(name=name):
                expected=set(assembler.trusted_prior_hashes(name).values())
                row=self.manifest["files"][name]
                accepted=set(row.get("compatible_from",[])) | {row["to"]}
                self.assertTrue(expected.issubset(accepted))
        self.assertFalse(any(
            "force" in str(meta.get(key,"")).lower()
            for key in ("from","compatible_from","allow_missing_from")))
        lock=json.loads((self.stage/"CANDIDATE_SOURCE_LOCK.json").read_text(encoding="utf8"))
        self.assertEqual(lock["approved_exact_previous_commits"],assembler.TRUSTED_PRIOR_COMMITS)
        self.assertFalse(lock["production_release_approved"])

    def test_exact_prior_windows_release_five_files_are_approved(self):
        # Reconstructed from verified previously delivered Windows update ZIP.
        # The installed file must equal these SHA-256s byte-for-byte, or the
        # guard must continue blocking. No force, wildcard or local SHA trust.
        exact = {
            "GeoField_CAD_Analysis.py": "c3c19306ec4e4f308cd39a0ac05b24faa9c157748ee78dde18e5abd4ab34dd8d",
            "frontend/cad.js": "936641e01a67b21a9c2a2dee3729afc4c891dcbc2fd2534ac1021621928f5f59",
            "frontend/index.html": "012b066ef84eb3568a79dd096e1f8160aa2cb042f55711b3ffdc912ea9b4da84",
            "ml_env_resolver.py": "c6aad7f2a7bf4e8e25b6017e88b152a3f0984318e9a8702f567730cae348237a",
            "ml_r12_bridge.py": "16e90c83972f13925c10c6e6c9b3588402f1b43264daecd4b87f3d873908e8aa",
        }
        self.assertEqual(assembler.VERIFIED_PREVIOUS_WINDOWS_SOURCE_SHA256,exact)
        self.assertEqual(assembler.VERIFIED_PREVIOUS_WINDOWS_PACKAGE_SHA256,
                         "18f413ad72b29078e38d5565b2f53783643de73a9e8d429b7da41b8bba06bf04")
        self.assertEqual(set(exact),{
            "GeoField_CAD_Analysis.py","frontend/cad.js","frontend/index.html",
            "ml_env_resolver.py","ml_r12_bridge.py"})
        for name,old_sha in exact.items():
            with self.subTest(name=name):
                row=self.manifest["files"][name]
                approved=set(row.get("compatible_from",[])) | {row.get("to"),row.get("from")}
                self.assertIn(old_sha,approved)
                self.assertNotIn("0"*64,approved)
        lock=json.loads((self.stage/"CANDIDATE_SOURCE_LOCK.json").read_text(encoding="utf8"))
        self.assertEqual(lock["approved_previous_windows_package_sha256"],
                         assembler.VERIFIED_PREVIOUS_WINDOWS_PACKAGE_SHA256)
        self.assertEqual(lock["approved_previous_windows_file_sha256"],exact)
        self.assertFalse(lock["production_release_approved"])

    def test_read_only_acceptance_tool_is_bundled_from_real_source(self):
        for name in ("acceptance_probe.py","GeoField_Acceptance_Check.cmd"):
            with self.subTest(name=name):
                self.assertEqual((self.stage/name).read_bytes(),
                                 (ROOT/name).read_bytes())
        source=(self.stage/"acceptance_probe.py").read_text(encoding="utf8")
        self.assertIn('SERVER="http://127.0.0.1:8600"',source)
        self.assertIn("production_release_approved",source)
        cmd=(self.stage/"GeoField_Acceptance_Check.cmd").read_text(encoding="utf8")
        self.assertIn("acceptance_probe.py",cmd)
        self.assertIn("verify_package.py",cmd)
        self.assertNotIn("bootstrap.py",cmd)
        launcher=(self.stage/"GeoField_Start.cmd").read_text(encoding="utf8")
        self.assertIn("[BUILD] GEOFIELD-20261026-RESEARCH-OPTIONAL-4",launcher)
        self.assertIn("[PACKAGE LOCATION]",launcher)
        self.assertIn("Check source compatibility BEFORE installation",launcher)
        bootstrap=(self.stage/"bootstrap.py").read_text(encoding="utf8")
        self.assertIn("from runtime_compatibility import assess_compatibility",bootstrap)
        self.assertIn("geofield_version_compatibility.json",bootstrap)
        self.assertIn("if not compatibility['safe_to_install']:",bootstrap)
        self.assertIn("return 25",bootstrap)
        self.assertEqual((self.stage/"runtime_compatibility.py").read_bytes(),
                         (ROOT/"runtime_compatibility.py").read_bytes())

    @unittest.skipUnless(os.name=="nt","Actual acceptance helper CMD requires Windows")
    def test_windows_read_only_probe_reports_missing_server_without_install(self):
        root=self.directory/"test_acceptance_localappdata"
        root.mkdir(parents=True,exist_ok=True)
        env=os.environ.copy()
        env["LOCALAPPDATA"]=str(root)
        command=[os.environ.get("COMSPEC","cmd.exe"),"/c",
                 str(self.stage/"GeoField_Acceptance_Check.cmd")]
        completed=subprocess.run(command,cwd=self.stage,env=env,
                                 capture_output=True,text=True,encoding="utf8",
                                 errors="replace",input="\n",timeout=60)
        self.assertNotEqual(completed.returncode,0)
        self.assertIn("NOT VERIFIED",completed.stdout)
        output=root/"GeoFieldCAD"/"diagnostics"/"acceptance"/"geofield_acceptance_latest.json"
        self.assertTrue(output.is_file(),"Read-only diagnostic JSON must be collected")
        data=json.loads(output.read_text(encoding="utf8"))
        self.assertEqual(data["server"],"not_verified")
        self.assertFalse(data["production_release_approved"])
        self.assertFalse((root/"GeoFieldCAD"/"onefile_runtime").exists())
        self.assertFalse((root/"GeoFieldCAD"/"backups").exists())
    @unittest.skipUnless(os.name == "nt", "Actual CMD invocation requires Windows")
    def test_extracted_cmd_without_companion_files_names_missing_bootstrap(self):
        launch_folder=self.directory/"missing_companions"
        launch_folder.mkdir()
        shutil.copy2(self.stage/"GeoField_Start.cmd",launch_folder/"GeoField_Start.cmd")
        env=os.environ.copy()
        env["LOCALAPPDATA"]=str(self.directory/"isolated_local")
        command=[os.environ.get("COMSPEC","cmd.exe"),"/c",
                 str(launch_folder/"GeoField_Start.cmd")]
        reply=subprocess.run(command,cwd=launch_folder,env=env, input="\n",
                             capture_output=True,text=True,encoding="utf8",
                             errors="replace",timeout=35)
        self.assertNotEqual(reply.returncode,0)
        self.assertIn("[EXECUTED FROM]",reply.stdout)
        self.assertIn("[MISSING] bootstrap.py",reply.stdout)
        self.assertIn("BNZ temporary folder",reply.stdout)
        self.assertFalse((self.directory/"isolated_local"/"GeoFieldCAD").exists())

    @unittest.skipUnless(os.name == "nt", "Actual CMD invocation requires Windows")
    def test_missing_payload_file_names_exact_failure_without_install(self):
        broken=self.directory/"missing_payload"
        shutil.copytree(self.stage,broken)
        (broken/"payload"/"GeoField_CAD_Analysis.py").unlink()
        env=os.environ.copy()
        env["LOCALAPPDATA"]=str(self.directory/"isolated_local_2")
        reply=subprocess.run([os.environ.get("COMSPEC","cmd.exe"),"/c",
                              str(broken/"GeoField_Start.cmd")],
                             cwd=broken,env=env,input="\n",capture_output=True,
                             text=True,encoding="utf8",errors="replace",timeout=35)
        self.assertNotEqual(reply.returncode,0)
        self.assertIn("[MISSING] payload\\GeoField_CAD_Analysis.py",reply.stdout)
        self.assertIn("[SAFE] No GeoField installation",reply.stdout)
        self.assertFalse((self.directory/"isolated_local_2"/"GeoFieldCAD").exists())

    def test_one_extract_stage_has_flat_launcher_readme_and_no_nested_archives(self):
        self.assertTrue((self.stage/"GeoField_Start.cmd").is_file())
        self.assertTrue((self.stage/"START_HERE_ONE_EXTRACT.txt").is_file())
        self.assertTrue((self.stage/"manifest.json").is_file())
        self.assertTrue((self.stage/"verify_package.py").is_file())
        self.assertTrue((self.stage/"payload"/"GeoField_CAD_Analysis.py").is_file())
        self.assertFalse(list(self.stage.rglob("*.zip")))
        text=(self.stage/"START_HERE_ONE_EXTRACT.txt").read_text(encoding="utf8")
        self.assertIn("Extract All ONCE",text)
        self.assertIn("DO NOT double-click it from Bandizip",text)
        self.assertIn("EXISTING compatible GeoField",text)
        self.assertIn("NOT FINAL",text)
        # Root candidate must retain strict source manifest verification.
        installer.verify_bundle(installer.DirectoryBundle(self.stage))
    def test_hash_verified_candidate_zip_and_tamper_rejection(self):
        zip_name=self.directory/"GeoField_AB_AI_CANDIDATE_NOT_FINAL.zip"
        assembler.zip_candidate(self.stage,zip_name)
        extracted=self.directory/"extracted"
        with zipfile.ZipFile(zip_name) as archive:
            files=archive.namelist()
            self.assertFalse(any(x.startswith("/") or ".." in Path(x).parts for x in files))
            archive.extractall(extracted)
        installer.verify_bundle(installer.DirectoryBundle(extracted))
        self.assertEqual((extracted/"payload"/"GeoField_CAD_Analysis.py").read_bytes(),
                         (ROOT/"payload/GeoField_CAD_Analysis.py").read_bytes())
        self.assertEqual((extracted/"payload/frontend/cad.js").read_bytes(),
                         (ROOT/"payload/frontend/cad.js").read_bytes())
        self.assertEqual((extracted/"CANDIDATE_SOURCE_LOCK.json").read_bytes(),
                         (self.stage/"CANDIDATE_SOURCE_LOCK.json").read_bytes())
        payload=extracted/"payload"/"GeoField_CAD_Analysis.py"
        original=payload.read_bytes()
        try:
            payload.write_bytes(original+b"tamper")
            with self.assertRaises(Exception):
                installer.verify_bundle(installer.DirectoryBundle(extracted))
        finally:
            payload.write_bytes(original)
        installer.verify_bundle(installer.DirectoryBundle(extracted))

if __name__=="__main__":
    unittest.main()
