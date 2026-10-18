import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.failure_attribution import classify, inspect


class FailureAttributionTests(unittest.TestCase):
    def test_explicit_connect_denial_identifies_proxy_path_not_exchange(self):
        result=classify({'errors':['binance: failed CONNECT via proxy status: 403']})
        self.assertEqual(result['observed_layers'],['network_proxy'])
        self.assertEqual(result['root_cause'],'unknown')
        self.assertNotIn('binance',json.dumps(result))

    def test_generic_403_and_timeout_do_not_prove_an_exchange_outage(self):
        result=classify({'errors':['instrument verification: HTTP Error 403: Forbidden',
                                   'okx: connection timed out']})
        self.assertEqual(result['observed_layers'],['access_path_unknown','unknown'])
        self.assertEqual(result['root_cause'],'unknown')

    def test_concurrent_network_quality_and_shutdown_symptoms_preserved(self):
        result=classify({'errors':['Tunnel connection failed: 403 Forbidden'],
                         'health':{'problems':['binance: quote silence']}},
                        {'errors':[],'workers_still_running':['binance_bbo']})
        self.assertEqual(result['observed_layers'],['collection_quality','network_proxy','recorder_shutdown'])
        self.assertEqual(len(result['observations']),3)

    def test_no_errors_is_not_eligibility_or_proof_of_complete_data(self):
        result=classify({'errors':[]},{'errors':[],'workers_still_running':[]})
        self.assertEqual(result['failure_evidence'],'none in supplied diagnostics')
        self.assertEqual(result['root_cause'],'unknown')
        self.assertNotIn('eligible',result)

    def test_raw_messages_and_embedded_sensitive_strings_are_not_emitted(self):
        result=classify({'errors':['unknown problem token=do-not-emit https://private.invalid']})
        self.assertNotIn('do-not-emit',json.dumps(result))
        self.assertNotIn('private.invalid',json.dumps(result))
        self.assertEqual(result['observations'][0]['evidence_ref'],'manifest.json#/errors/0')

    def test_malformed_error_structure_rejected(self):
        with self.assertRaises(ValueError):
            classify({'errors':'not an array'})
        with self.assertRaises(ValueError):
            classify({'errors':[None]})

    def test_real_failed_archives_verified_without_outcome_estimation(self):
        with patch('cel.study.evaluate') as evaluate:
            result=inspect(Path('reports/evidence'))
        evaluate.assert_not_called()
        self.assertEqual(result['archives_verified'],3)
        self.assertEqual(result['archives_by_observed_layer']['network_proxy'],3)
        self.assertTrue(all(r['recorded_event_count']==0 for r in result['records']))

    def test_corrupt_or_empty_sources_do_not_produce_attribution(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            with self.assertRaisesRegex(ValueError,'no archives'):
                inspect(root)
            (root/'bad.tar.gz').write_bytes(b'broken')
            (root/'bad.tar.gz.sha256').write_text('0'*64)
            with self.assertRaisesRegex(ValueError,'checksum'):
                inspect(root)
