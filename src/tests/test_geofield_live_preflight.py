"""Standard-library-only security tests for read-only live API preflight."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))
import geofield_live_preflight as live


class LivePreflightTests(unittest.TestCase):
    def test_refuses_non_readonly_route(self):
        for url in ('/api/agent/evidence/foo?llm=1',
                    '/api/ml/r12/run/foo', 'https://example.com/'):
            with self.assertRaises(ValueError):
                live.fetch_status(8600, url)

    def test_success_is_redacted(self):
        state = live.sanitize({
            'server': {'ok': True, 'server_instance': 'SECRET_RUN_ID'},
            'r12': {'available': True, 'python': 'C:/Users/PRIVATE_PERSON/python.exe',
                    'missing': [], 'private_file': 'SENSITIVE'},
            'ai': {'agent': {'llm_config': {'configured': True,
                        'configured_provider': 'deepseek',
                        'selected_model': 'deepseek-flash',
                        'key': 'PRIVATE_API_KEY'}}}})
        self.assertTrue(state['server']['ok'])
        self.assertTrue(state['r12']['available'])
        self.assertTrue(state['deepseek']['configured_in_running_server'])
        self.assertFalse(state['paid_api_called'])
        output = json.dumps(state)
        for secret in ('PRIVATE_PERSON', 'SENSITIVE', 'PRIVATE_API_KEY', 'SECRET_RUN_ID'):
            self.assertNotIn(secret, output)

    def test_offline_report_is_not_claimed_connected(self):
        state = live.sanitize({'server': ConnectionError('SECRET'),
                               'r12': TimeoutError('SECRET'), 'ai': ValueError('SECRET')})
        self.assertFalse(state['server']['reachable'])
        self.assertFalse(state['r12']['checked'])
        self.assertFalse(state['deepseek']['checked'])
        self.assertNotIn('SECRET', json.dumps(state))

    def test_ml_available_does_not_mean_current_step_executed(self):
        state = live.sanitize({
            'server': {'ok': True},
            'r12': {'available': True, 'python': 'python.exe'},
            'ai': {'agent': {'llm_config': {'configured': False}}}})
        self.assertFalse(state['r12']['inference_performed'])
        self.assertFalse(state['deepseek']['configured_in_running_server'])
        self.assertFalse(state['deepseek']['live_request_sent'])

    def test_one_click_only_checks_known_local_endpoint(self):
        script = (SRC / 'GeoField_Connection_Status.cmd').read_text(encoding='utf8')
        self.assertIn('geofield_live_preflight.py', script)
        self.assertIn('--port 8600', script)
        for unsafe in ('GeoField_Start.cmd', 'bootstrap.py', 'Stop-Process',
                       'GeoField_Repair.cmd', 'pip install'):
            self.assertNotIn(unsafe, script)

if __name__ == '__main__':
    unittest.main()
