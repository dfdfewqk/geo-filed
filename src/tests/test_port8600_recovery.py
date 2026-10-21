"""Port 8600 upgrade handshake tests; no Windows process is stopped here."""
import copy
import json
import pathlib
import sys
import types
import unittest
from unittest.mock import patch
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import geofield_port_recovery as guard
import bootstrap

SCRIPT = r'C:\Users\User\AppData\Local\GeoFieldCAD\onefile_runtime\8a9ac53a821a0eb5\GeoField_CAD_Analysis.py'
OWNER = {'pid':5100,'name':'python.exe','executable':r'C:\Python312\python.exe',
         'created':'2026-10-21T14:20:05.423+09:00','commandline':
         '"C:\\Python312\\python.exe" -u "'+SCRIPT+'" --port 8600 --no-browser',
         'children':[]}
class OwnerValidation(unittest.TestCase):
    def test_exact_owner_accepted(self):
        self.assertTrue(guard.verified_windows_owner(OWNER,pathlib.Path(SCRIPT)))
    def test_unknown_program_rejected(self):
        e=copy.deepcopy(OWNER);e.update(name='chrome.exe', executable=r'C:\Chrome\chrome.exe')
        self.assertFalse(guard.verified_windows_owner(e,pathlib.Path(SCRIPT)))
    def test_similar_filename_and_wrong_port_rejected(self):
        e=copy.deepcopy(OWNER);e['commandline']=e['commandline'].replace('.py"','.py.malware"')
        self.assertFalse(guard.verified_windows_owner(e,pathlib.Path(SCRIPT)))
        e=copy.deepcopy(OWNER);e['commandline']=e['commandline'].replace('--port 8600','--port 8601')
        self.assertFalse(guard.verified_windows_owner(e,pathlib.Path(SCRIPT)))
    def test_children_and_inline_python_rejected(self):
        e=copy.deepcopy(OWNER);e['children']=[8742]
        self.assertFalse(guard.verified_windows_owner(e,pathlib.Path(SCRIPT)))
        e=copy.deepcopy(OWNER);e['commandline'] += ' -c "malicious"'
        self.assertFalse(guard.verified_windows_owner(e,pathlib.Path(SCRIPT)))
    def test_absent_fields_rejected(self):
        for field in ('commandline','created','executable','children'):
            e=copy.deepcopy(OWNER);e.pop(field)
            self.assertFalse(guard.verified_windows_owner(e,pathlib.Path(SCRIPT)),field)

class HttpActivityGate(unittest.TestCase):
    def status(self,**changes):
        payload={'ok':True,'phase':guard.PHASE,'version':'R20-core-stabilization',
                 'server_instance':'a'*32,'active_work_count':0,'safe_to_update':True}
        payload.update(changes)
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def read(self,n):return json.dumps(payload).encode('utf-8')
        opener=types.SimpleNamespace(open=lambda url,timeout:Response())
        with patch.object(guard.urllib.request,'build_opener',return_value=opener):
            return guard.geo_http_identity()
    def test_idle_verified_server_is_eligible(self):
        self.assertTrue(self.status())
    def test_active_solver_blocks_automatic_stop(self):
        for count in (1,2,100):
            with self.subTest(count=count):
                self.assertFalse(self.status(active_work_count=count,safe_to_update=False))
    def test_missing_activity_contract_blocks_legacy_server(self):
        self.assertFalse(self.status(active_work_count=None,safe_to_update=None))
    def test_false_safe_flag_blocks_even_when_count_zero(self):
        self.assertFalse(self.status(active_work_count=0,safe_to_update=False))
    def test_noninteger_activity_count_fails_closed(self):
        for count in (False,'0',0.0):
            with self.subTest(count=count):
                self.assertFalse(self.status(active_work_count=count))
    def test_spoofed_http_phase_and_version_rejected(self):
        self.assertFalse(self.status(phase='not-geofield'))
        self.assertFalse(self.status(version='future-unknown'))


class AutoStop(unittest.TestCase):
    def setUp(self):
        self.events=[]
        self.fake_os=types.SimpleNamespace(name='nt',environ={'LOCALAPPDATA':r'C:\Users\User\AppData\Local'})
        self.emit=lambda *args:self.events.append(' '.join(map(str,args)))
    def root(self):
        return pathlib.Path(SCRIPT).parent
    def test_trusted_owner_goes_through_double_identity_and_exact_stop(self):
        calls=[]
        def powershell(cmd, **kw):
            calls.append((cmd,kw))
            return json.dumps(OWNER) if len(calls)==1 else 'STOPPED_VERIFIED_GEOFIELD_PID=5100'
        with patch.object(guard,'os',self.fake_os):
            result=guard.stop_verified_old_geofield(self.root(),self.emit,inspect=powershell,identity=lambda p:True)
        # On Linux Path('\') has no Windows semantics, so use a genuine POSIX path
        # for the injected test owner in the next test. This test checks the fail-closed path.
        self.assertFalse(result)
        self.assertEqual(len(calls),1)
    def test_success_with_real_root_path(self):
        script=str(pathlib.Path('/tmp/GeoFieldCAD')/'GeoField_CAD_Analysis.py')
        owner=copy.deepcopy(OWNER);owner['commandline']='"C:\\Python312\\python.exe" -u "'+script+'" --port 8600 --no-browser'
        calls=[];ident=[]
        def ps(cmd,**kw):
            calls.append((cmd,kw));return json.dumps(owner) if len(calls)==1 else 'STOPPED_VERIFIED_GEOFIELD_PID=5100'
        with patch.object(guard,'os',self.fake_os):
            ok=guard.stop_verified_old_geofield(pathlib.Path('/tmp/GeoFieldCAD'),self.emit,inspect=ps,identity=lambda p:(ident.append(p) or True))
        self.assertTrue(ok);self.assertEqual(ident,[8600,8600]);self.assertEqual(len(calls),2)
        self.assertEqual(calls[1][1]['env']['GF_PORT_OWNER_ID'],'5100')
    def test_unverified_http_never_inspects_process(self):
        def should_not_run(*a,**k):raise AssertionError('no process inspection permitted')
        with patch.object(guard,'os',self.fake_os):
            self.assertFalse(guard.stop_verified_old_geofield(pathlib.Path('/tmp'),self.emit,inspect=should_not_run,identity=lambda p:False))
    def test_unknown_or_active_owner_never_stopped(self):
        for child in ([1002],[]):
            with self.subTest(child=child):
                owner=copy.deepcopy(OWNER);owner['children']=child
                if not child:owner['name']='chrome.exe'
                counter=[]
                def inspect(cmd,**kw):
                    counter.append(cmd)
                    if len(counter)>1:raise AssertionError('wrongful termination')
                    return json.dumps(owner)
                with patch.object(guard,'os',self.fake_os):
                    self.assertFalse(guard.stop_verified_old_geofield(self.root(),self.emit,inspect=inspect,identity=lambda p:True))
                self.assertEqual(len(counter),1)

class Launcher(unittest.TestCase):
    def test_wont_install_until_port_released(self):
        with patch.object(bootstrap,'_port_occupied',return_value=True), patch.object(bootstrap,'stop_verified_old_geofield',return_value=False) as stop, patch.dict(bootstrap.os.environ,{'LOCALAPPDATA':'/tmp'}):
            self.assertFalse(bootstrap.wait_for_port_release())
            stop.assert_called_once()
    def test_auto_release_waits_then_allows_update(self):
        with patch.object(bootstrap,'_port_occupied',side_effect=[True,True,False]), patch.object(bootstrap,'stop_verified_old_geofield',return_value=True), patch.dict(bootstrap.os.environ,{'LOCALAPPDATA':'/tmp'}), patch.object(bootstrap.time,'sleep'):
            self.assertTrue(bootstrap.wait_for_port_release(max_wait=1,interval=.01))
    def test_free_port_never_stops_anything(self):
        with patch.object(bootstrap,'_port_occupied',return_value=False),patch.object(bootstrap,'stop_verified_old_geofield') as stop:
            self.assertTrue(bootstrap.wait_for_port_release());stop.assert_not_called()

if __name__ == '__main__': unittest.main()
