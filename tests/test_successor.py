from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from scripts.successor_claim import claim, slot_identity, verify_claim
from scripts.successor_recorder import normalize, InstrumentSampler
from scripts.successor_rehearsal import gate, pack, restore

PROTOCOL = json.loads(Path('configs/successor/protocol.json').read_text())


class FakeGitHub:
    def __init__(self):
        self.lock = threading.Lock()
        self.refs, self.commits = {}, {}
        self.counter = 0

    def __call__(self, endpoint, payload=None):
        with self.lock:
            if payload is not None and endpoint.endswith('/git/commits'):
                self.counter += 1
                sha = f'{self.counter:040x}'
                self.commits[sha] = payload
                return {'sha':sha}
            if payload is not None and endpoint.endswith('/git/refs'):
                if payload['ref'] in self.refs:
                    raise RuntimeError('already claimed')
                self.refs[payload['ref']] = payload['sha']
                return {'ref':payload['ref'], 'object':{'sha':payload['sha']}}
            if '/git/ref/' in endpoint:
                key = 'refs/' + endpoint.split('/git/ref/')[1]
                return {'object':{'sha':self.refs[key]}}
            sha = endpoint.rsplit('/',1)[-1]
            return self.commits.get(sha, {'tree':{'sha':'f'*40}})


class SuccessorTests(unittest.TestCase):
    def test_concurrent_contenders_have_one_durable_owner_without_takeover(self):
        api = FakeGitHub()
        def compete(owner):
            try:
                return claim('owner/repo', PROTOCOL, '2026-10-20T03:17:00Z', 'a'*40, owner, request=api)
            except RuntimeError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            records = list(pool.map(compete, ['100-1','101-1']))
        winners = [r for r in records if r]
        self.assertEqual(len(winners),1)
        self.assertTrue(verify_claim(winners[0],request=api))
        self.assertIsNone(compete('102-1'))
        self.assertEqual(len(api.refs),1)

    def test_claim_binding_rejects_changed_owner(self):
        api = FakeGitHub()
        record = claim('owner/repo',PROTOCOL,'2026-10-20T03:17:00Z','a'*40,'1-1',request=api)
        with self.assertRaisesRegex(ValueError,'metadata'):
            verify_claim(record | {'owner_run_attempt':'2-1'},request=api)

    def test_slot_timezone_normalization_and_invalid_identifiers(self):
        self.assertEqual(slot_identity('study','2026-10-20T11:17:00+08:00'),slot_identity('study','2026-10-20T03:17:00Z'))
        with self.assertRaises(ValueError):
            slot_identity('../bad','2026-10-20T03:17:00Z')
        with self.assertRaises(ValueError):
            slot_identity('study','2026-10-20T03:17:00')

    def test_gate_enforces_intended_date_and_does_not_relabel_late_run(self):
        intended = '2026-10-20T03:17:00Z'
        for now, expected in [('2026-10-20T03:16:59Z',False),('2026-10-20T03:17:00Z',True),
                              ('2026-10-20T03:22:00Z',True),('2026-10-20T03:22:01Z',False),
                              ('2026-10-21T03:17:00Z',False)]:
            self.assertIs(gate(PROTOCOL,intended,now,'prospective')['accepted'],expected)
        transport = gate(PROTOCOL,intended,'2026-10-21T03:17:00Z','transport_only')
        self.assertTrue(transport['accepted'])
        self.assertFalse(transport['timing_qualified'])

    def test_fallback_flag_uses_actual_field_not_clock_equality(self):
        payload = {'e':'bookTicker','s':'BTCUSDT','u':1,'b':'10','a':'11','B':'2','A':'2','E':100}
        event, source = normalize(payload,100,'binance',.01)[0]
        self.assertEqual(event.exchange_ts,event.local_ts)
        self.assertEqual(source,'E')
        del payload['E']
        self.assertEqual(normalize(payload,100,'binance',.01)[0][1],'local_receive')

    def test_okx_multirow_provenance_and_units_are_row_specific(self):
        row = {'bids':[['10','2']], 'asks':[['11','3']]}
        payload = {'arg':{'channel':'bbo-tbt','instId':'BTC-USDT-SWAP'},'data':[row | {'ts':'99'}, row]}
        events = normalize(payload,100,'okx',.01)
        self.assertEqual([source for _,source in events],['ts','local_receive'])
        self.assertEqual(events[0][0].bid_sz,.02)

    def test_sampler_retains_failed_and_changed_instrument_snapshots(self):
        with TemporaryDirectory() as tmp:
            row = {'instId':'BTC-USDT-SWAP','ctVal':'0.01'}
            responses = iter([({'data':[row]},.01),({'data':[row | {'ctVal':'0.02'}]},.02)])
            sampler = InstrumentSampler(Path(tmp),fetch=lambda:next(responses))
            sampler.sample()
            sampler.sample()
            sampler.sample()
            self.assertTrue(sampler.changed)
            self.assertTrue(sampler.failed)
            self.assertEqual(len(sampler.path.read_text().splitlines()),3)

    def test_tampered_archive_fails_before_interpreting_data(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root/'recording'
            original.mkdir()
            (original/'sample.json').write_text('{}')
            archive = root/'attempt.tar.gz'
            pack(original,archive)
            archive.write_bytes(archive.read_bytes()+b'tampered')
            with self.assertRaisesRegex(ValueError,'digest'):
                restore(archive,root/'restore')
