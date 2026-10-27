"""Read-only upgrade version gate regression against disposable 17-file runtime."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from installer import ALLOWED_TARGETS
from runtime_compatibility import assess_compatibility,write_compatibility_report


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ReadOnlyCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="geofield-version-audit-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"old_runtime"
        self.root.mkdir()
        self.records={}
        self.manifest={"runtime_id":"8a9ac53a821a0eb5","files":{}}
        for name in sorted(ALLOWED_TARGETS):
            before=("original "+name).encode()
            after=("new "+name).encode()
            path=self.root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(before)
            self.records[name]=before
            self.manifest["files"][name]={
                "from":sha(before),"to":sha(after),
                "compatible_from":[],"bytes":len(after)}
        self.protected={
            "history/private.sqlite":b"database contents must be unchanged",
            "FEA/case.sta":b"STA remains identical",
            "original/L_bracket.step":b"STEP remains identical",
            "models/research.joblib":b"ML weights unchanged"}
        for name,data in self.protected.items():
            f=self.root/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data)

    def assert_protected(self):
        for name,data in self.protected.items():
            self.assertEqual((self.root/name).read_bytes(),data)

    def test_verified_legacy_versions_ready_without_changing_files(self):
        out=assess_compatibility(self.root,self.manifest)
        self.assertTrue(out["safe_to_install"])
        self.assertEqual(out["candidate_file_count"],17)
        self.assertEqual(out["blocking_files"],[])
        self.assertTrue(all(row["status"]=="verified_prior_version" for row in out["file_versions"].values()))
        self.assertFalse(out["user_data_inspected"])
        self.assertFalse(out["external_network_used"])
        for name,data in self.records.items():
            self.assertEqual((self.root/name).read_bytes(),data)
        self.assert_protected()

    def test_known_branch_exact_hash_allowed_unknown_customization_blocked(self):
        name="GeoField_CAD_Analysis.py"
        old=self.records[name]
        self.manifest["files"][name]["compatible_from"]=[sha(old)]
        self.manifest["files"][name]["from"]=sha(b"original unrelated")
        self.assertTrue(assess_compatibility(self.root,self.manifest)["safe_to_install"])
        (self.root/name).write_bytes(b"untracked user custom plugin")
        out=assess_compatibility(self.root,self.manifest)
        self.assertFalse(out["safe_to_install"])
        self.assertIn(name,out["blocking_files"])
        self.assertEqual(out["file_versions"][name]["status"],"unrecognized_local_source")
        self.assert_protected()

    def test_mixed_approved_and_unknown_blocks_entire_install(self):
        edited=["frontend/cad.js","fea_solver.py","ml_r12_bridge.py","fea_load_moment.py"]
        for name in edited:
            (self.root/name).write_bytes(b"unknown manual patch for "+name.encode())
        out=assess_compatibility(self.root,self.manifest)
        self.assertFalse(out["safe_to_install"])
        self.assertEqual(set(out["blocking_files"]),set(edited))
        self.assertTrue(all(
            out["file_versions"][k]["status"]=="unrecognized_local_source" for k in edited))
        self.assert_protected()

    def test_code_only_unknown_hashes_are_reviewable_but_not_auto_approved(self):
        for name in ("GeoField_CAD_Analysis.py","frontend/cad.js","frontend/index.html"):
            (self.root/name).write_bytes(b"local edited code")
        info=assess_compatibility(self.root,self.manifest)
        self.assertFalse(info["safe_to_install"])
        self.assertTrue(info["explicit_code_migration_possible"])
        self.assertEqual(set(info["explicit_code_migration_files"]),{
            "GeoField_CAD_Analysis.py","frontend/cad.js","frontend/index.html"})
        self.assert_protected()

    def test_unknown_model_bytes_never_migratable_as_local_source(self):
        name="ml/r12_research/research_model.joblib"
        (self.root/name).write_bytes(b"unverified model")
        info=assess_compatibility(self.root,self.manifest)
        self.assertFalse(info["safe_to_install"])
        self.assertFalse(info["explicit_code_migration_possible"])
        self.assertEqual(info["explicit_code_migration_files"],[])
        self.assert_protected()

    def test_missing_files_allowed_only_by_manifest_flag(self):
        target=self.root/"fea_load_moment.py"
        target.unlink()
        missing=assess_compatibility(self.root,self.manifest)
        self.assertFalse(missing["safe_to_install"])
        self.assertEqual(missing["file_versions"]["fea_load_moment.py"]["status"],"missing_blocked")
        self.manifest["files"]["fea_load_moment.py"]["allow_missing_from"]=True
        out=assess_compatibility(self.root,self.manifest)
        self.assertTrue(out["safe_to_install"])
        self.assertEqual(out["file_versions"]["fea_load_moment.py"]["status"],"missing_allowed")

    def test_absent_runtime_never_creates_install_location(self):
        dest=Path(self.tmp.name)/"nothing_here"
        out=assess_compatibility(dest,self.manifest)
        self.assertFalse(out["safe_to_install"])
        self.assertEqual(out["blocking_files"],["runtime_root"])
        self.assertFalse(dest.exists())

    def test_unknown_symlink_never_resolved_or_hashed(self):
        target=self.root/"frontend"/"cad.js"
        target.unlink()
        try:
            target.symlink_to(self.root/"history"/"private.sqlite")
        except (OSError,NotImplementedError):
            self.skipTest("Symlinks unavailable in this runner")
        out=assess_compatibility(self.root,self.manifest)
        self.assertFalse(out["safe_to_install"])
        self.assertEqual(out["file_versions"]["frontend/cad.js"]["status"],"unsafe_link")
        self.assert_protected()

    def test_json_inventory_contains_no_private_data_and_no_user_path(self):
        out=assess_compatibility(self.root,self.manifest)
        report=Path(self.tmp.name)/"reports"/"compatibility.json"
        write_compatibility_report(out,report)
        dump=report.read_text(encoding="utf8")
        self.assertTrue(report.is_file())
        self.assertEqual(json.loads(dump)["schema"],"geofield-local-version-compatibility-v1")
        self.assertNotIn(str(self.root),dump)
        for private in self.protected.values():
            self.assertNotIn(private.decode("utf8"),dump)
        self.assertEqual(len(out["file_versions"]),17)
        self.assert_protected()

    def test_invalid_manifest_targets_fail_without_moving_code(self):
        self.manifest["files"]["../../private.sqlite"]={"to":"0"*64}
        with self.assertRaises(ValueError):
            assess_compatibility(self.root,self.manifest)
        self.assert_protected()

if __name__=="__main__":
    unittest.main()
