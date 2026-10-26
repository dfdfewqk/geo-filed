"""Real released-artifact upgrade chain, not only a synthetic manifest test.

Windows CI authenticates the last SUCCESSFUL GitHub artifact first. This test
installs its exact 17 actual payload blobs into an isolated fake runtime, then
uses our production installer to upgrade, reject edits, and roll back.
No real user files or ports are modified.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

SRC=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SRC))
import installer
import build_integration_candidate as buildtool
from runtime_compatibility import assess_compatibility


class RealPriorArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("GF_PRIOR_CANDIDATE_ZIP"):
            raise unittest.SkipTest("Local workspace has no authenticated previous Actions artifact")
        cls.previous=buildtool.previous_distribution()
        if not cls.previous:
            raise AssertionError("Required previous GitHub artifact missing")
        cls.staging=tempfile.TemporaryDirectory(prefix="geofield-previous-candidate-")
        cls.bundle=Path(cls.staging.name)/"candidate"
        cls.manifest=buildtool.build(cls.bundle)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,"staging"):cls.staging.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="geofield-upgrade-chain-")
        self.addCleanup(self.temp.cleanup)
        self.local=Path(self.temp.name)
        self.runtime=self.local/"GeoFieldCAD"/"onefile_runtime"/self.manifest["runtime_id"]
        self.runtime.mkdir(parents=True)
        # The real installer checks for preexisting engine identity.
        (self.runtime/"engine_runtime.py").write_text("# dummy runtime for isolated test\n")
        with zipfile.ZipFile(os.environ["GF_PRIOR_CANDIDATE_ZIP"]) as z:
            old=json.loads(z.read("manifest.json"))
            self.old={}
            for name in old["files"]:
                blob=z.read("payload/"+name)
                assert hashlib.sha256(blob).hexdigest()==old["files"][name]["to"]
                self.old[name]=blob
                p=self.runtime/name
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes(blob)

    def test_direct_upgrade_of_actual_previous_artifact(self):
        before=assess_compatibility(self.runtime,self.manifest)
        self.assertTrue(before["safe_to_install"],before["blocking_files"])
        receipt={}
        rc=installer.apply(installer.DirectoryBundle(self.bundle),localappdata=self.local,receipt=receipt)
        self.assertEqual(rc,0)
        after=assess_compatibility(self.runtime,self.manifest)
        self.assertTrue(after["safe_to_install"],after["blocking_files"])
        self.assertEqual(after["blocking_files"],[])
        for name,meta in self.manifest["files"].items():
            self.assertEqual(installer.sha((self.runtime/name).read_bytes()),meta["to"])
        changed=[name for name,old in self.old.items()
                 if installer.sha(old)!=self.manifest["files"][name]["to"]]
        if changed:
            self.assertTrue(receipt.get("backup"))
            self.assertEqual(set(item["path"] for item in receipt["changed"]),set(changed))
            installer.rollback_install(receipt)
            for name,old in self.old.items():
                self.assertEqual((self.runtime/name).read_bytes(),old)
        else:
            # Already-current previous candidate is a legitimate no-op.
            self.assertIsNone(receipt.get("backup"))
            self.assertEqual(receipt.get("changed"),[])

    def test_unknown_user_modified_source_blocks_before_any_update(self):
        mod=self.runtime/"frontend"/"cad.js"
        mod.write_bytes(mod.read_bytes()+b"\n# edited privately\n")
        snapshot={name:installer.sha((self.runtime/name).read_bytes())
                  for name in self.old}
        before=assess_compatibility(self.runtime,self.manifest)
        self.assertFalse(before["safe_to_install"])
        self.assertIn("frontend/cad.js",before["blocking_files"])
        with self.assertRaisesRegex(RuntimeError,"Refusing to overwrite unknown source"):
            installer.apply(installer.DirectoryBundle(self.bundle),localappdata=self.local)
        self.assertEqual(snapshot,{name:installer.sha((self.runtime/name).read_bytes())
                                   for name in self.old})
        self.assertFalse((self.local/"GeoFieldCAD"/"backups").exists())

    def test_3_real_archived_frontend_releases_are_whitelisted_exactly(self):
        expected=buildtool.KNOWN_RELEASED_FRONTEND_HASHES
        self.assertEqual(len(expected["frontend/cad.js"]),3)
        self.assertEqual(len(expected["frontend/index.html"]),3)
        for name,old_shas in expected.items():
            approved=set(self.manifest["files"][name].get("compatible_from",[]))
            approved.add(self.manifest["files"][name]["to"])
            approved.add(self.manifest["files"][name].get("from"))
            self.assertTrue(set(old_shas).issubset(approved))
            self.assertNotIn("f"*64,approved)
        self.assertEqual(set(self.manifest["files"]),installer.ALLOWED_TARGETS)


if __name__=="__main__":
    unittest.main()
