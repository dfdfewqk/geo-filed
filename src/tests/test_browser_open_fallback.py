"""Exercise real GeoField launch-to-browser code with a fake localhost backend.

No installed Windows runtime, CalculiX, real port, browser or user files used.
"""
from __future__ import annotations
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import sys

SRC=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SRC))
import bootstrap

URL="http://127.0.0.1:8600/"

class RelaunchBrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="geofield-open-check-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"onefile_runtime"
        self.root.mkdir()
        self.diag=Path(self.tmp.name)/"diagnostics"

    def simulate(self, browser_result, startfile_raises=False):
        events=[]
        process=Mock()
        process.poll.side_effect=[None,0]
        process.returncode=0
        # Preflight can be unavailable; opening CAD must not depend on ML.
        with patch.object(bootstrap,"DIAG",self.diag), \
             patch.object(bootstrap,"_ready",side_effect=[False,True]), \
             patch.object(bootstrap,"_port_occupied",return_value=False), \
             patch.object(bootstrap.subprocess,"Popen",return_value=process) as popen, \
             patch.object(bootstrap.time,"sleep"), \
             patch.object(bootstrap.webbrowser,"open",return_value=browser_result) as webopen, \
             patch.object(bootstrap.os,"startfile",create=True) as shell, \
             patch.object(bootstrap.urllib.request,"build_opener",side_effect=OSError("ML offline")), \
             patch.object(bootstrap,"emit",side_effect=lambda *parts:events.append(" ".join(map(str,parts)))):
            if startfile_raises:shell.side_effect=OSError("no URL handler")
            rc=bootstrap._start_backend(self.root,Path("C:/GeoField/python.exe"))
        self.assertEqual(rc,0)
        self.assertEqual(popen.call_count,1)
        webopen.assert_called_once_with(URL)
        self.assertTrue(any("[READY]" in event and URL in event for event in events))
        return shell,events

    def test_open_default_browser_on_verified_ready_server(self):
        shell,events=self.simulate(browser_result=True)
        shell.assert_not_called()
        self.assertTrue(any("[BROWSER] Opening" in event for event in events))

    @unittest.skipUnless(os.name=="nt","Windows Shell fallback specific")
    def test_browser_false_uses_windows_shell_url_handler(self):
        shell,events=self.simulate(browser_result=False)
        shell.assert_called_once_with(URL)
        self.assertTrue(any("Windows default URL handler" in event for event in events))

    @unittest.skipUnless(os.name=="nt","Windows Shell fallback specific")
    def test_browser_and_shell_failure_keep_manual_url_and_server(self):
        shell,events=self.simulate(browser_result=False,startfile_raises=True)
        shell.assert_called_once_with(URL)
        self.assertTrue(any("[BROWSER] Open manually: "+URL in event for event in events))
        self.assertTrue(any("[READY]" in event for event in events))

    def test_existing_service_never_start_second_backend_or_browser(self):
        with patch.object(bootstrap,"_ready",return_value=True), \
             patch.object(bootstrap.subprocess,"Popen") as popen, \
             patch.object(bootstrap.webbrowser,"open") as browser:
            with self.assertRaisesRegex(RuntimeError,"already runs"):
                bootstrap._start_backend(self.root,Path("python.exe"))
            popen.assert_not_called()
            browser.assert_not_called()

    def test_unverified_port_never_start_backend_or_browser(self):
        with patch.object(bootstrap,"_ready",return_value=False), \
             patch.object(bootstrap.socket,"socket") as sock, \
             patch.object(bootstrap.subprocess,"Popen") as popen, \
             patch.object(bootstrap.webbrowser,"open") as browser:
            sock.return_value.__enter__.return_value.connect_ex.return_value=0
            with self.assertRaisesRegex(RuntimeError,"unverified process"):
                bootstrap._start_backend(self.root,Path("python.exe"))
            popen.assert_not_called()
            browser.assert_not_called()


if __name__=="__main__":
    unittest.main()
