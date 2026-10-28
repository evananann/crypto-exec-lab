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
        self.assertEqual(sum(name.startswith('refs/tags/successor-claims/') for name in api.refs),1)
        self.assertEqual(len(api.refs),2)

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


class ReadinessAndStatusTests(unittest.TestCase):
    def trial(self, index, *, healthy=True, mode='workflow_dispatch', day=20):
        return {'slot_id':f'study/{index}', 'intended_start_utc':f'2026-10-{day:02}T03:17:00Z',
                'run_created_at_utc':f'2026-10-{day:02}T03:17:{index:02}Z', 'event':mode,
                'authenticated_remote_restore':True,
                'assessment':{'collection_healthy':healthy,'timing':{'timing_qualified':mode=='workflow_dispatch'}}}

    def test_transport_success_cannot_unlock_study(self):
        from scripts.successor_readiness import summarize
        records = [self.trial(i,mode='push',day=20+i) for i in range(3)]
        self.assertFalse(summarize(records,PROTOCOL)['activation_ready'])

    def test_three_trials_on_one_date_do_not_unlock_study(self):
        from scripts.successor_readiness import summarize
        self.assertFalse(summarize([self.trial(i) for i in range(3)],PROTOCOL)['activation_ready'])

    def test_only_latest_consecutive_attempts_qualify_and_failures_remain_visible(self):
        from scripts.successor_readiness import summarize
        records = [self.trial(i,day=20+i) for i in range(3)]
        self.assertTrue(summarize(records,PROTOCOL)['activation_ready'])
        records.append(self.trial(3,healthy=False,day=23))
        result = summarize(records,PROTOCOL)
        self.assertFalse(result['activation_ready'])
        self.assertEqual(result['attempts_examined'],4)
        self.assertEqual(result['qualifying_prospective_rehearsals'],3)

    def test_skipped_unarchived_trial_blocks_activation(self):
        from scripts.successor_readiness import summarize
        records = [self.trial(i,day=20+i) for i in range(3)]
        missing = self.trial(3,day=23)
        missing['authenticated_remote_restore'] = False
        missing['intended_start_utc'] = None
        records.append(missing)
        self.assertFalse(summarize(records,PROTOCOL)['activation_ready'])

    def test_duplicates_and_unready_registration_are_rejected(self):
        from scripts.successor_readiness import summarize, registration
        with self.assertRaisesRegex(ValueError,'duplicate'):
            summarize([self.trial(1),self.trial(1)],PROTOCOL)
        with self.assertRaisesRegex(ValueError,'blocked'):
            registration({'activation_ready':False},'2026-10-26','2026-10-19T00:00:00Z',PROTOCOL)

    def test_status_snapshot_is_dated_and_html_escapes_input(self):
        from scripts.project_status import from_observation, render
        state = from_observation(Path('reports/collection_followup_20261019/observation.json'))
        self.assertEqual(state['collection']['counts']['missing'],4)
        self.assertTrue(any('Static snapshot' in w for w in state['warnings']))
        state['software']['state'] = '<script>alert(1)</script>'
        with TemporaryDirectory() as tmp:
            out = Path(tmp)/'page'
            render(state,out)
            self.assertNotIn('<script>',(out/'index.html').read_text())
            self.assertIn('&lt;script&gt;',(out/'index.html').read_text())
            self.assertFalse(json.loads((out/'status.json').read_text())['successor']['study_activated'])


class RestoredProvenanceTests(unittest.TestCase):
    def recording(self, root):
        from scripts.successor_rehearsal import write
        from datetime import datetime, timedelta, timezone
        start = datetime(2026,10,20,3,17,tzinfo=timezone.utc)
        write(root/'protocol.json',PROTOCOL)
        write(root/'manifest.json',{'requested_seconds':900,'mode':'prospective',
              'intended_start_utc':start.isoformat(),'collector_started_at_utc':start.isoformat(),
              'collection_error_category':None})
        write(root/'connections.json',{'connections':[{'venue':v,'connection_id':v+'-one'} for v in ['binance','okx']],
                                      'parse_errors':{}})
        instrument = {'code':'0','data':[{'instId':'BTC-USDT-SWAP','instType':'SWAP','ctType':'linear',
            'ctValCcy':'BTC','settleCcy':'USDT','state':'live','ctVal':'.01','ctMult':'1'}]}
        with (root/'instruments.jsonl').open('w') as stream:
            for second in range(0,901,60):
                stream.write(json.dumps({'observed_at_utc':(start+timedelta(seconds=second)).isoformat(),
                                         'payload':instrument,'factor_btc':.01})+'\n')
        index = 0
        with (root/'wire.jsonl').open('w') as wire, (root/'events.jsonl').open('w') as events, (root/'provenance.jsonl').open('w') as provenance:
            for second in range(901):
                stamp = int(start.timestamp()*1000)+second*1000
                payloads = {'binance':{'e':'bookTicker','s':'BTCUSDT','u':second,'E':stamp,
                                     'b':'60000','a':'60001','B':'2','A':'2'},
                            'okx':{'arg':{'channel':'bbo-tbt','instId':'BTC-USDT-SWAP'},
                                   'data':[{'ts':str(stamp),'seqId':second,'bids':[['60000','200']],
                                            'asks':[['60001','200']]}]}}
                for venue,payload in payloads.items():
                    connection = venue+'-one'
                    wire.write(json.dumps({'venue':venue,'connection_id':connection,'local_ts':stamp,'payload':payload})+'\n')
                    for event,source in normalize(payload,stamp,venue,.01):
                        events.write(json.dumps(event.to_dict())+'\n')
                        provenance.write(json.dumps({'event_index':index,'venue':venue,'connection_id':connection,
                            'exchange_timestamp_source':source,'timestamp_fallback':False})+'\n')
                        index += 1
        write(root/'recorder.json',{'events':index,'duration_seconds':900,'workers_still_running':[]})

    def test_full_synthetic_rehearsal_restore_recomputes_health_and_provenance(self):
        from scripts.successor_rehearsal import assess
        with TemporaryDirectory() as tmp:
            root = Path(tmp)/'recording'
            root.mkdir()
            self.recording(root)
            assessment = assess(root)
            self.assertTrue(assessment['collection_healthy'],assessment['issues'])
            self.assertEqual(assessment['events'],1802)
            archive = Path(tmp)/'attempt.tar.gz'
            pack(root,archive)
            self.assertEqual(restore(archive,Path(tmp)/'restored'),assessment)

    def test_changed_event_or_timestamp_flag_is_detected_against_wire(self):
        from scripts.successor_rehearsal import assess
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.recording(root)
            path = root/'provenance.jsonl'
            lines = path.read_text().splitlines()
            row = json.loads(lines[0])
            row['timestamp_fallback'] = True
            lines[0] = json.dumps(row)
            path.write_text('\n'.join(lines)+'\n')
            assessment = assess(root)
            self.assertFalse(assessment['collection_healthy'])
            self.assertIn('wire/event/provenance reparse mismatch',assessment['issues'])

    def test_path_traversal_member_is_rejected_before_extraction(self):
        import hashlib
        import io
        import tarfile
        with TemporaryDirectory() as tmp:
            archive = Path(tmp)/'evil.tar.gz'
            with tarfile.open(archive,'w:gz') as tar:
                member = tarfile.TarInfo('../escape')
                member.size = 2
                tar.addfile(member,io.BytesIO(b'{}'))
            archive.with_name(archive.name+'.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest())
            with self.assertRaisesRegex(ValueError,'unsafe'):
                restore(archive,Path(tmp)/'restored')
            self.assertFalse((Path(tmp)/'escape').exists())


class PreservationRecoveryTests(unittest.TestCase):
    def test_partial_remote_publication_resumes_without_overwriting_originals(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from scripts.successor_rehearsal import preserve, write
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording = root/'recording'
            recording.mkdir()
            RestoredProvenanceTests().recording(recording)
            write(recording/'claim.json',{'repository':'owner/repo','source_commit':'a'*40,'slot_id':'study/slot'})
            write(recording/'source.json',{'commit':'a'*40,'dirty':False})
            archive = root/'rehearsal-1-1.tar.gz'
            pack(recording,archive)
            state = {'created':False,'assets':{},'interrupt':True}
            def api(endpoint,payload=None):
                self.assertIsNone(payload,'Preservation must not create a new Release')
                if '/git/ref/' in endpoint:
                    return {'object':{'sha':'a'*40}}
                if '/assets?' in endpoint:
                    return [{'name':n} for n in state['assets']]
                return {'id':1,'tag_name':'study-archive-btc-execution-v1','prerelease':True,'draft':False}
            def run(command,**kwargs):
                operation = command[2]
                if operation == 'create':
                    state['created'] = True
                elif operation == 'upload':
                    path = Path(command[4])
                    if path.name.endswith('.sha256') and state['interrupt']:
                        state['interrupt'] = False
                        raise RuntimeError('simulated interrupted checksum upload')
                    self.assertNotIn(path.name,state['assets'])
                    state['assets'][path.name] = path.read_bytes()
                elif operation == 'download':
                    destination = Path(command[command.index('--dir')+1])
                    pattern = command[command.index('--pattern')+1] if '--pattern' in command else None
                    for name,data in state['assets'].items():
                        if pattern is None or name == pattern:
                            (destination/name).write_bytes(data)
                else:
                    self.fail('unexpected remote mutation')
                return SimpleNamespace(returncode=0)
            args = SimpleNamespace(out=root,repository='owner/repo',source_commit='a'*40)
            with patch('scripts.successor_rehearsal.api',side_effect=api), patch('scripts.successor_rehearsal.subprocess.run',side_effect=run), patch('scripts.successor_rehearsal.verify_claim',return_value=True):
                with self.assertRaisesRegex(RuntimeError,'interrupted'):
                    preserve(args)
                original = state['assets'][archive.name]
                preserve(args)
                self.assertEqual(state['assets'][archive.name],original)
                self.assertIn('successor-readback-1-1.json',state['assets'])
                preserve(args)  # Same original/receipt is idempotent; no --clobber.
                state['assets'][archive.name] += b'corrupt'
                with self.assertRaisesRegex(ValueError,'conflicts'):
                    preserve(args)


class ConnectionProvenanceTests(unittest.TestCase):
    def test_reopen_same_socket_object_gets_new_connection_identity(self):
        from unittest.mock import Mock
        from scripts.successor_recorder import ProvenanceRecorder
        with TemporaryDirectory() as tmp:
            recorder = ProvenanceRecorder(Path(tmp),.01)
            recorder._writer = Mock()
            ws = Mock()
            handlers = recorder.handlers('binance')
            payload = json.dumps({'e':'bookTicker','s':'BTCUSDT','u':1,'E':100,
                                  'b':'10','a':'11','B':'2','A':'2'})
            try:
                handlers['on_open'](ws)
                handlers['on_message'](ws,payload)
                first = recorder.connections[id(ws)]
                handlers['on_close'](ws,None,None)
                handlers['on_open'](ws)
                handlers['on_message'](ws,payload)
                second = recorder.connections[id(ws)]
                self.assertNotEqual(first,second)
                recorder.provenance.flush()
                rows = [json.loads(s) for s in (Path(tmp)/'provenance.jsonl').read_text().splitlines()]
                self.assertEqual([r['connection_id'] for r in rows],[first,second])
                self.assertEqual([r['event_index'] for r in rows],[0,1])
                self.assertIn('closed_at_utc',recorder.connection_history[0])
            finally:
                recorder.provenance.close()
                recorder.wire.close()

    def test_fractional_intended_seconds_cannot_share_a_claim_reference(self):
        with self.assertRaisesRegex(ValueError,'whole'):
            slot_identity('study','2026-10-20T03:17:00.100Z')


class StatusFailureTests(unittest.TestCase):
    def test_unavailable_inventory_cannot_turn_into_success(self):
        from unittest.mock import patch
        from scripts.project_status import build
        inventory = {'healthy':False,'as_of_utc':'2026-10-19T00:00:00Z', 'inventory_available':False,
                     'counts':{'unverified':5},'sessions':[],'alerts':['inventory unavailable'],
                     'scope':'collection health only'}
        with patch('scripts.project_status.api_json',side_effect=RuntimeError('unavailable')), patch('scripts.project_status.collection_inventory',return_value=inventory), patch('scripts.project_status.rehearsal_readiness',side_effect=ValueError('no evidence')), patch('scripts.successor_study.load_registration',side_effect=ValueError('no verified registration')):
            state = build('owner/repo')
        self.assertEqual(state['software']['state'],'unverified')
        self.assertEqual(state['collection']['state'],'ALERT')
        self.assertEqual(state['collection']['counts'],{'unverified':5})
        self.assertEqual(state['successor']['state'],'unverified')
        self.assertFalse(state['successor']['study_activated'])

    def test_verified_registration_does_not_make_unavailable_inventory_healthy(self):
        from unittest.mock import patch
        from scripts.project_status import build
        plan = {'study_id': 'synthetic', 'start_date_utc': '2030-01-01',
                'end_date_utc': '2030-01-28', 'outcome_release_date_utc': '2030-01-29'}
        inventory = {'healthy': False, 'as_of_utc': '2030-01-01T00:00:00Z', 'inventory_available': False,
                     'counts': {'unverified': 5}, 'sessions': [], 'alerts': ['inventory unavailable'],
                     'scope': 'collection health only'}
        # Registration is now present on main; isolate both registration states explicitly.
        with patch('scripts.project_status.api_json', side_effect=RuntimeError('unavailable')), patch('scripts.project_status.collection_inventory', return_value=inventory), patch('scripts.project_status.rehearsal_readiness', side_effect=ValueError('no evidence')), patch('scripts.successor_study.load_registration', return_value=plan):
            state = build('owner/repo')
        self.assertTrue(state['successor']['study_activated'])
        self.assertEqual(state['collection']['state'], 'ALERT')
        self.assertFalse(state['collection']['inventory_available'])
        self.assertEqual(state['successor']['state'], 'unverified')
        self.assertEqual(state['software']['state'], 'unverified')


class ProtocolEvolutionTests(unittest.TestCase):
    def test_serialization_changes_do_not_change_protocol_identity(self):
        from scripts.successor_claim import canonical
        compact = json.dumps(PROTOCOL,separators=(',',':'))
        pretty = json.dumps(PROTOCOL,indent=2)
        self.assertNotEqual(compact,pretty)
        self.assertEqual(canonical(json.loads(compact)),canonical(json.loads(pretty)))

    def test_old_source_trials_remain_visible_but_new_matching_trials_can_qualify(self):
        from scripts.successor_readiness import summarize
        helper = ReadinessAndStatusTests()
        records = [helper.trial(i,day=20+i) | {'qualification_compatible':False} for i in range(3)]
        self.assertFalse(summarize(records,PROTOCOL)['activation_ready'])
        records += [helper.trial(i,day=20+i) | {'qualification_compatible':True} for i in range(3,6)]
        result = summarize(records,PROTOCOL)
        self.assertTrue(result['activation_ready'])
        self.assertEqual(result['attempts_examined'],6)


class RecoveryInventoryTests(unittest.TestCase):
    def test_recovered_failed_original_does_not_qualify_prospective_success(self):
        from scripts.successor_readiness import summarize
        helper = ReadinessAndStatusTests()
        records = [helper.trial(i,day=20+i) for i in range(3)]
        records[-1]['source_run_conclusion'] = 'failure'
        self.assertFalse(summarize(records,PROTOCOL)['activation_ready'])

    def test_recovery_zip_rejects_traversal_and_unexpected_members(self):
        import zipfile
        from scripts.successor_recovery import unpack
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            zipped = root/'artifact.zip'
            with zipfile.ZipFile(zipped,'w') as archive:
                archive.writestr('../outside.json','{}')
            with self.assertRaisesRegex(ValueError,'unsafe'):
                unpack(zipped,root/'out','rehearsal-1-1.tar.gz')
            self.assertFalse((root/'outside.json').exists())

    def test_original_recovery_restores_without_recording_or_promoting_failed_attempt(self):
        import zipfile
        from unittest.mock import patch
        from scripts.successor_recovery import recover
        from scripts.successor_rehearsal import write
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording = root/'recording'
            recording.mkdir()
            RestoredProvenanceTests().recording(recording)
            write(recording/'claim.json',{'owner_run_attempt':'1-1','repository':'owner/repo','source_commit':'a'*40,'slot_id':'study/slot'})
            write(recording/'source.json',{'commit':'a'*40,'dirty':False})
            archive = root/'rehearsal-1-1.tar.gz'
            pack(recording,archive)
            def api(endpoint):
                if endpoint.endswith('/artifacts?per_page=100'):
                    return {'artifacts':[{'id':2,'name':'successor-rehearsal-1-1','expired':False,
                        'workflow_run':{'id':1,'head_sha':'a'*40,'head_branch':'main'}}]}
                return {'id':1,'run_attempt':1,'path':'.github/workflows/successor-rehearsal.yml',
                        'head_branch':'main','status':'completed','event':'push','head_sha':'a'*40,
                        'head_repository':{'full_name':'owner/repo'},'conclusion':'failure'}
            def download(repository,identifier,out):
                with zipfile.ZipFile(out,'w') as zipped:
                    zipped.write(archive,'successor-attempt/'+archive.name)
                    zipped.write(archive.with_name(archive.name+'.sha256'),'successor-attempt/'+archive.name+'.sha256')
            with patch('scripts.successor_recovery.api',side_effect=api), patch('scripts.successor_recovery.download_zip',side_effect=download), patch('scripts.successor_recovery.verify_source'), patch('scripts.successor_recovery.verify_claim'), patch('scripts.successor_recovery.preserve') as preservation:
                recover('owner/repo',1,root/'recovery')
                preservation.assert_called_once()
            result = json.loads((root/'recovery'/'recovery.json').read_text())
            self.assertFalse(result['new_recording_performed'])
            self.assertFalse(result['qualifying_prospective_success'])
            self.assertEqual(result['original_conclusion'],'failure')


class DispatchEvidenceTests(unittest.TestCase):
    def test_single_dispatch_records_send_ack_and_receipt_id_without_retry(self):
        from datetime import datetime,timezone,timedelta
        from types import SimpleNamespace
        from unittest.mock import Mock
        from scripts.successor_dispatch import dispatch
        start=datetime(2026,10,20,3,17,tzinfo=timezone.utc)
        ticks=iter([start,start+timedelta(seconds=1)])
        runner=Mock(return_value=SimpleNamespace(returncode=0))
        with TemporaryDirectory() as tmp:
            out=Path(tmp)/'dispatch.jsonl'
            self.assertTrue(dispatch('owner/repo',start.isoformat(),out,clock=lambda:next(ticks),run=runner))
            rows=[json.loads(s) for s in out.read_text().splitlines()]
            self.assertEqual([r['phase'] for r in rows],['request_prepared','request_acknowledged'])
            payload=json.loads(runner.call_args.kwargs['input'])
            self.assertEqual(payload['inputs']['dispatch_id'],rows[0]['dispatch_id'])
            self.assertFalse(rows[1]['workflow_run_verified'])
            runner.assert_called_once()

    def test_uncertain_delivery_is_preserved_and_never_retried(self):
        from datetime import datetime,timezone
        from unittest.mock import Mock
        from scripts.successor_dispatch import dispatch
        start=datetime(2026,10,20,3,17,tzinfo=timezone.utc)
        runner=Mock(side_effect=OSError('connection lost'))
        with TemporaryDirectory() as tmp:
            out=Path(tmp)/'dispatch.jsonl'
            self.assertFalse(dispatch('owner/repo',start.isoformat(),out,clock=lambda:start,run=runner))
            rows=[json.loads(s) for s in out.read_text().splitlines()]
            self.assertEqual(rows[-1]['phase'],'delivery_unconfirmed')
            self.assertFalse(rows[-1]['automatic_retry'])
            runner.assert_called_once()
