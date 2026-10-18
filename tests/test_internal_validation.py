from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.order_lifecycle import Journal, Ledger, scenario_events
from scripts.collection_timeline import demo as timeline_demo, run_evidence, inspect as inspect_timeline
from scripts.numeric_reproducibility import compare
from scripts.audit_recordings import inspect as audit_recordings
from scripts.audit_artifact_storage import inspect as audit_storage
from cel.ingest.parse import parse_bybit
from cel.ingest.top_book import TopBook


def submit(key='entry',side='buy',venue='okx',quantity='.001'):
    return {'message_id':'submit-'+key,'kind':'submit','client_order_id':key,'side':side,'venue':venue,'quantity':quantity}


def fill(key='entry',quantity='.001',price='60000',fee='.03',identifier='f',stamp=100):
    return {'message_id':'message-'+identifier,'kind':'fill','client_order_id':key,'execution_id':identifier,
            'quantity':quantity,'price':price,'fee_usdt':fee,'venue_execution_ms':stamp}


class LifecycleTests(unittest.TestCase):
    def test_complete_roundtrip_conserves_cash_inventory_and_both_fees(self):
        ledger=Ledger()
        ledger.apply(submit())
        ledger.apply(fill(price='60001',fee='.0300005'))
        ledger.apply(submit('exit','sell'))
        ledger.apply(fill('exit',price='60000',fee='.03',identifier='x'))
        self.assertEqual(ledger.positions['okx'],Decimal(0))
        self.assertEqual(ledger.cash['okx'],Decimal('-.0610005'))
        self.assertEqual(ledger.fees['okx'],Decimal('.0600005'))

    def test_limit_price_and_order_terms_cannot_change_silently_on_retry(self):
        ledger=Ledger()
        order=submit() | {'order_type':'limit','limit_price':'60000'}
        ledger.apply(order)
        with self.assertRaisesRegex(ValueError,'conflicting client'):
            ledger.apply(order | {'message_id':'retry','limit_price':'61000'})
        with self.assertRaisesRegex(ValueError,'limit price'):
            ledger.apply(fill(price='60001'))
        ledger.apply(fill(price='59999'))
        self.assertEqual(ledger.snapshot()['orders']['entry']['status'],'filled')

    def test_duplicate_reports_and_retries_never_double_fill(self):
        ledger=Ledger()
        ledger.apply(submit())
        ledger.apply({**submit(),'message_id':'retry-submit'})
        event=fill()
        ledger.apply(event)
        ledger.apply({**event,'message_id':'different-notification','received_ms':200})
        ledger.apply({**event,'received_ms':300})
        self.assertEqual(len(ledger.orders),1)
        self.assertEqual(len(ledger.executions),1)
        self.assertEqual(ledger.positions['okx'],Decimal('.001'))

    def test_partial_cancel_race_retains_late_fill_and_canceled_remainder(self):
        ledger=Ledger()
        for event in scenario_events():
            ledger.apply(event)
        order=ledger.snapshot()['orders']['entry']
        self.assertEqual(order['status'],'canceled')
        self.assertEqual(Decimal(order['filled']),Decimal('.0006'))
        self.assertEqual(Decimal(order['remaining']),Decimal('.0004'))
        self.assertEqual(len(ledger.executions),2)

    def test_invalid_fills_and_conflicting_ids_leave_state_unchanged(self):
        ledger=Ledger()
        ledger.apply(submit())
        ledger.apply(fill(quantity='.0006'))
        before=deepcopy(ledger)
        for event in (fill(quantity='.001',identifier='overfill'),
                      {**fill(quantity='.0006'),'price':'1'},
                      {**submit(),'message_id':'retry','quantity':'.002'},
                      fill(identifier='fee-currency') | {'fee_currency':'BTC'}):
            with self.assertRaises(ValueError):
                ledger.apply(event)
            self.assertEqual(ledger,before)

    def test_fill_before_ack_does_not_get_resurrected_by_late_ack(self):
        ledger=Ledger()
        ledger.apply(submit())
        ledger.apply(fill())
        ledger.apply({'message_id':'ack','kind':'ack','client_order_id':'entry','venue_order_id':'v1'})
        self.assertEqual(ledger.snapshot()['orders']['entry']['status'],'filled')

    def test_fill_after_effective_cancel_is_invalid_but_earlier_execution_can_arrive_late(self):
        ledger=Ledger()
        ledger.apply(submit())
        ledger.apply({'message_id':'cancel','kind':'cancel_ack','client_order_id':'entry','venue_cancel_ms':200})
        with self.assertRaises(ValueError):
            ledger.apply(fill(stamp=201))
        ledger.apply(fill(stamp=199))
        self.assertEqual(ledger.snapshot()['orders']['entry']['status'],'filled')

    def test_restart_requires_complete_reconciliation_and_preserves_outstanding_orders(self):
        with TemporaryDirectory() as temp:
            path=Path(temp)/'journal.jsonl'
            journal=Journal(path)
            journal.append(submit())
            journal.append(fill(quantity='.0004'))
            recovered=Journal(path)
            self.assertFalse(recovered.ledger.reconciled)
            with self.assertRaisesRegex(ValueError,'reconcile'):
                recovered.append(submit('new'))
            recovered.append({'message_id':'bad-reconcile','kind':'reconcile','positions':{},'cash':{},'open_orders':{}})
            self.assertFalse(recovered.ledger.reconciled)
            current=recovered.ledger.snapshot()
            recovered.append({'message_id':'good-reconcile','kind':'reconcile',
                              'positions':current['positions_btc'],'cash':current['cash_usdt'],
                              'open_orders':{'entry':'.0006'}})
            self.assertTrue(recovered.ledger.reconciled)
            recovered.append(submit('new'))

    def test_truncated_or_tampered_journal_fails_without_silent_repair(self):
        with TemporaryDirectory() as temp:
            path=Path(temp)/'journal.jsonl'
            Journal(path).append(submit())
            original=path.read_bytes()
            path.write_bytes(original[:-1])
            with self.assertRaisesRegex(ValueError,'truncated'):
                Journal(path)
            self.assertEqual(path.read_bytes(),original[:-1])
            path.write_bytes(original.replace(b'".001"',b'".002"'))
            with self.assertRaisesRegex(ValueError,'digest'):
                Journal(path)

    def test_failed_append_does_not_commit_memory_state(self):
        with TemporaryDirectory() as temp:
            journal=Journal(Path(temp)/'journal.jsonl')
            with patch('scripts.order_lifecycle.os.fsync',side_effect=OSError('injected disk failure')):
                with self.assertRaises(OSError):
                    journal.append(submit())
            self.assertEqual(journal.ledger.orders,{})
            self.assertFalse(Journal(journal.path).ledger.reconciled)


class OperationalAuditTests(unittest.TestCase):
    def test_gate_success_and_skipped_recording_do_not_establish_intended_slot_or_collection(self):
        result=timeline_demo()['runs'][0]
        self.assertEqual(result['creation_to_run_start_seconds'],5)
        self.assertEqual(result['jobs'][0]['collection_observation'],'not executed: collection step skipped')
        self.assertIn('unknown',result['intended_cron_or_dispatch_slot'])
        with self.assertRaisesRegex(ValueError,'untrusted'):
            run_evidence({'head_branch':'feature'},[],'owner/repo')

    def test_workflow_activation_and_default_branch_are_evidence_not_assumed(self):
        def api(endpoint,**kwargs):
            if endpoint=='repos/owner/repo':
                return {'default_branch':'other'}
            if endpoint.endswith('.yml'):
                return {'state':'disabled_manually'}
            return {'workflow_runs':[],'total_count':0}
        with patch('scripts.collection_timeline.api_json',side_effect=api):
            result=inspect_timeline('owner/repo')
        self.assertEqual(len(result['workflows']),2)
        self.assertTrue(all(w['state']=='disabled_manually' for w in result['workflows']))
        self.assertFalse(result['workflows'][0]['default_branch_is_main'])
        self.assertEqual(result['runs'],[])

    def test_reconnect_deltas_cannot_reuse_old_sides_without_snapshot(self):
        book=TopBook()
        def message(update,kind,bids,asks):
            return {'topic':'orderbook.1.BTCUSDT','type':kind,'ts':100,
                    'data':{'u':update,'b':bids,'a':asks}}
        self.assertEqual(len(parse_bybit(message(10,'snapshot',[['100','1']],[['101','1']]),100,book)),1)
        book.reset()
        self.assertEqual(parse_bybit(message(11,'delta',[['99','1']],[]),101,book),[])
        self.assertIsNone(book.ask)
        self.assertEqual(parse_bybit(message(1,'snapshot',[['98','1']],[]),102,book),[])
        self.assertEqual(len(parse_bybit(message(2,'delta',[],[['99','1']]),103,book)),1)
        self.assertEqual(book.bid,98)
        self.assertEqual(book.ask,99)

    def test_archived_zero_event_counts_are_reconciled_without_outcomes(self):
        with patch('cel.study.evaluate') as evaluate:
            result=audit_recordings(Path('reports/evidence'))
        evaluate.assert_not_called()
        self.assertEqual(len(result['recordings']),3)
        self.assertTrue(all(r['raw_normalized_events']==0 for r in result['recordings']))
        self.assertTrue(all(r['replay_count_matches'] for r in result['recordings']))

    def test_storage_inventory_is_read_only_and_retains_duplicate_provenance(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('one.json','two.json'):
                (root/name).write_text('same bytes')
            result=audit_storage(root)
            self.assertEqual(result['files'],2)
            self.assertEqual(len(result['identical_byte_groups']),1)
            self.assertEqual(len(list(root.iterdir())),2)

    def test_cross_version_comparison_rejects_missing_versions_changed_values_and_sources(self):
        with TemporaryDirectory() as temp:
            paths=[]
            for version in ('3.11.1','3.12.1','3.13.1'):
                p=Path(temp)/(version+'.json')
                p.write_text(json.dumps({'schema_version':1,'python':version,'source_commit':'a'*40,
                                         'values':{'price':60000.,'passed':True}}))
                paths.append(p)
            self.assertTrue(compare(paths,expected_commit='a'*40)['passed'])
            with self.assertRaises(ValueError):
                compare(paths[:2],expected_commit='a'*40)
            data=json.loads(paths[0].read_text())
            data['values']['price']+=1
            paths[0].write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'disagreement'):
                compare(paths,expected_commit='a'*40)
            with self.assertRaisesRegex(ValueError,'revision'):
                compare(paths,expected_commit='b'*40)
