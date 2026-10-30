"""Fail-closed Windows launcher regressions. No installed runtime or user data."""
from __future__ import annotations

from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "GeoField_Start.cmd"


class WindowsLauncherContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text(encoding="utf8").replace("\r\n", "\n")

    def test_goto_targets_exist_and_each_label_unique(self):
        labels = re.findall(r"(?im)^:([a-z_][a-z0-9_]*)\s*$", self.text)
        targets = re.findall(r"(?i)\bgoto\s+:([a-z_][a-z0-9_]*)", self.text)
        self.assertEqual(len(labels),len(set(labels)), "duplicate CMD labels route to wrong place")
        self.assertFalse(set(targets)-set(labels), "goto destination missing")
        self.assertIn("source_checkout",labels)
        self.assertIn("unpacked",labels)

    def test_extracted_package_and_source_checkout_are_different(self):
        snippet = self.text.split('if not exist "%GF_PACKAGE%bootstrap.py"',1)[1]
        snippet = snippet.split('if not exist "%GF_PACKAGE%installer.py"',1)[0]
        self.assertRegex(snippet, r'(?s)^ \(\n +set "GF_MISSING=bootstrap.py"\n +goto :unpacked\n\)\n')
        source = self.text.split(":source_checkout",2)[-1]
        self.assertIn("exit /b 21",source)
        self.assertIn("verify_package.py",self.text)
        self.assertLess(self.text.index("\n:source_checkout\n"),self.text.index("\n:unpacked\n"))
        self.assertLess(self.text.index("exit /b 0"),self.text.index("\n:source_checkout\n"))

    @unittest.skipUnless(sys.platform=="win32", "Requires Windows cmd.exe")
    def test_source_checkout_never_runs_installer(self):
        env=os.environ.copy()
        completed=subprocess.run(
            ["cmd.exe","/d","/c",str(SOURCE)],
            cwd=SOURCE.parent, env=env, input="\n",
            capture_output=True, text=True, encoding="utf8", errors="replace",timeout=20)
        self.assertEqual(completed.returncode,21,completed.stdout[-1500:]+completed.stderr[-1500:])
        self.assertIn("[SOURCE CHECKOUT]",completed.stdout)
        self.assertNotIn("[1/3] Verify",completed.stdout)

    @unittest.skipUnless(sys.platform=="win32", "Requires Windows cmd.exe")
    def test_missing_payload_fails_closed_before_running_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy=Path(tmp)/"GeoField_Start.cmd"
            copy.write_bytes(SOURCE.read_bytes())
            completed=subprocess.run(
                ["cmd.exe","/d","/c",str(copy)],
                cwd=tmp,input="\n",capture_output=True,text=True,
                encoding="utf8",errors="replace",timeout=20)
            self.assertEqual(completed.returncode,1,completed.stdout[-1500:])
            self.assertIn("bootstrap.py",completed.stdout)
            self.assertNotIn("[2/3] Validate",completed.stdout)


if __name__ == "__main__":
    unittest.main()
