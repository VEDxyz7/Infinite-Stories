"""SYNTHETIC data only: test code safeguards, never live cultural coverage."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


smoke = module('qloo_smoke_test')
solver = module('solvability_reference')
SYNTHETIC_ID = '00000000-0000-4000-8000-000000000001'


def synthetic_city():
    evidence = {'SYNTHETIC_EDGE': {'source': 'synthetic', 'kind': 'recommendation',
        'source_id': 'SYNTHETIC_ARTIST', 'target_id': 'SYNTHETIC_FILM',
        'source_type': 'artist', 'target_type': 'movie'}}
    city = {'locations': ['A', 'B', 'C', 'D'], 'residents': {'r1': 'A', 'r2': 'B', 'r3': 'C'},
        'gate_location': 'D', 'budget': 12, 'clues': {},
        'answers': [{'requires': ['c3'], 'evidence': 'SYNTHETIC_EDGE'}]}
    for i, loc in enumerate(['A', 'B', 'C', 'D']):
        city['clues']['c'+str(i)] = {'location': loc,
            'requires': [] if i == 0 else ['c'+str(i-1)], 'evidence': ['SYNTHETIC_EDGE']}
    return city, evidence


class AdapterTests(unittest.TestCase):
    def test_offline_default_has_no_network(self):
        with patch.object(smoke.Probe, 'get', side_effect=AssertionError('No network allowed')), patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(smoke.main([]), 0)
            self.assertEqual(json.loads(output.getvalue())['status'], 'NOT TESTED')

    def test_missing_key_blocks_before_network(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(smoke.os.environ, {}, clear=True), patch.object(smoke.Probe, 'get', side_effect=AssertionError('No network allowed')), patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(smoke.main(['--live', '--env-file', str(Path(folder)/'absent')]), 2)
            self.assertEqual(json.loads(output.getvalue())['api_requests'], 0)

    def test_usage_permissions_block_even_with_synthetic_key(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(smoke.os.environ, {'QLOO_API_KEY': 'SYNTHETIC_NOT_A_REAL_KEY'}, clear=True), patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(smoke.main(['--live', '--env-file', str(Path(folder)/'absent')]), 2)

    def test_secret_fields_and_exact_values_redacted(self):
        data = {'name': 'text SYNTHETIC_SECRET', 'authorization': 'SYNTHETIC_SECRET',
                'nested': [{'api_key': 'SYNTHETIC_SECRET'}]}
        result = json.dumps(smoke.redact(data, ['SYNTHETIC_SECRET']))
        self.assertNotIn('SYNTHETIC_SECRET', result)
        self.assertNotIn('authorization', result)

    def test_ambiguous_names_are_never_auto_selected(self):
        candidate = {'name': 'Synthetic', 'subtype': 'urn:entity:movie', 'entity_id': SYNTHETIC_ID}
        self.assertEqual(smoke.resolve([candidate, candidate], 'Synthetic', 'movie'), ('AMBIGUOUS', None))
        self.assertIsNone(smoke.resolve([candidate], 'Synthetic', 'artist')[1])

    def test_http_200_payload_does_not_imply_data(self):
        self.assertIsNone(smoke.extract_entities({'success': False, 'results': {'entities': []}}))
        self.assertIsNone(smoke.extract_entities({'unexpected': 'shape'}))
        self.assertEqual(smoke.extract_entities({'results': {'entities': []}}), [])

    def test_redirects_not_followed(self):
        self.assertIsNone(smoke.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com'))

    def test_endpoint_and_call_budget_restricted(self):
        p = smoke.Probe('SYNTHETIC_NOT_A_REAL_KEY')
        with self.assertRaises(ValueError):
            p.get('/write', {})
        p.records = [{}] * smoke.MAX_CALLS
        with self.assertRaises(ValueError):
            p.get('/search', {})

    def test_timeout_is_recorded_without_exception_text(self):
        p = smoke.Probe('SYNTHETIC_NOT_A_REAL_KEY')
        with patch.object(p.opener, 'open', side_effect=TimeoutError('SYNTHETIC_SECRET')):
            self.assertIsNone(p.get('/search', {}))
        self.assertEqual(p.records[0]['outcome'], 'TIMEOUT')
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(p.records))

    def test_rate_limit_is_recorded_without_body(self):
        p = smoke.Probe('SYNTHETIC_NOT_A_REAL_KEY')
        error = urllib.error.HTTPError('https://api.qloo.com/search', 429, 'SYNTHETIC_SECRET', {}, None)
        with patch.object(p.opener, 'open', side_effect=error):
            self.assertIsNone(p.get('/search', {}))
        self.assertEqual(p.records[0]['http_status'], 429)
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(p.records))


class AbstractSolvabilityTests(unittest.TestCase):
    def test_witness_route_is_deterministic(self):
        city, evidence = synthetic_city()
        result = solver.validate(city, evidence)
        self.assertEqual(result['status'], 'VALID_ABSTRACT')
        self.assertEqual(result['route'], ['A', 'B', 'C', 'D'])
        self.assertEqual(solver.validate(city, evidence), result)

    def test_budget_includes_gate_entry(self):
        city, evidence = synthetic_city()
        city['budget'] = 3
        self.assertEqual(solver.validate(city, evidence)['status'], 'REJECT')

    def test_twelve_visit_boundary(self):
        city, evidence = synthetic_city()
        city['clues'] = {}
        for i in range(12):
            city['clues'][str(i)] = {'location': ['A', 'B', 'C', 'D'][i % 4],
                'requires': [] if i == 0 else [str(i-1)], 'evidence': ['SYNTHETIC_EDGE']}
        city['answers'][0]['requires'] = ['11']
        self.assertEqual(solver.validate(city, evidence)['visits'], 12)
        city['budget'] = 11
        self.assertEqual(solver.validate(city, evidence)['status'], 'REJECT')

    def test_missing_evidence_rejected(self):
        city, evidence = synthetic_city()
        self.assertEqual(solver.validate(city, {})['status'], 'REJECT')

    def test_dependency_cycle_rejected(self):
        city, evidence = synthetic_city()
        city['clues']['c0']['requires'] = ['c3']
        self.assertEqual(solver.validate(city, evidence)['status'], 'REJECT')

    def test_unknown_dependency_rejected(self):
        city, evidence = synthetic_city()
        city['clues']['c0']['requires'] = ['missing']
        self.assertEqual(solver.validate(city, evidence)['status'], 'REJECT')

    def test_same_category_answer_rejected(self):
        city, evidence = synthetic_city()
        evidence['SYNTHETIC_EDGE']['target_type'] = 'artist'
        self.assertEqual(solver.validate(city, evidence)['status'], 'REJECT')

    def test_extra_unverifiable_answer_rejects_entire_candidate(self):
        city, evidence = synthetic_city()
        city['answers'].append({'requires': ['c3'], 'evidence': 'MISSING'})
        self.assertEqual(solver.validate(city, evidence)['status'], 'REJECT')

    def test_no_answers_rejected(self):
        city, evidence = synthetic_city()
        city['answers'] = []
        self.assertEqual(solver.validate(city, evidence)['status'], 'REJECT')

    def test_no_network_dependency(self):
        city, evidence = synthetic_city()
        with patch('urllib.request.urlopen', side_effect=AssertionError('No network allowed')):
            self.assertEqual(solver.validate(city, evidence)['status'], 'VALID_ABSTRACT')


if __name__ == '__main__':
    unittest.main()
