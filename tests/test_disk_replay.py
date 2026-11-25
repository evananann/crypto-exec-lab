"""The disk adapter must reproduce the independent in-memory replay exactly."""
import base64
from contextlib import closing
from copy import deepcopy
import gzip
import json
from pathlib import Path
import random
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.autolab import disk_replay as disk, raw_replay as raw, cohort, secondary
from research.autolab.qualification import digest
from research.autolab import controller as lab
from research.roadmap import empirical_pipeline as oracle
from tests.test_raw_replay import fixture
from tests.test_capture_qualification import fixture as broken_fixture
from tests.test_cohort_controls import fixture as cohort_fixture


def design():
    return json.loads(oracle.DESIGN.read_text())


def rewrite(spool, transform):
    segment = next(spool.glob('*.jsonl.gz'))
    with gzip.open(segment, 'rt') as stream:
        rows = [json.loads(line) for line in stream]
    rows = transform(rows)
    with gzip.open(segment, 'wt') as stream:
        for row in rows:
            stream.write(raw.canonical(row)+'\n')
    path = next(spool.glob('*.manifest.json'))
    manifest = json.loads(path.read_text())
    manifest.update(records=len(rows), sha256=digest(segment))
    path.write_text(json.dumps(manifest))


class DiskReplayTests(unittest.TestCase):
    def test_every_grid_row_and_trace_matches_the_memory_oracle(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool, metadata, _ = fixture(root)
            books, source = oracle.load_session(spool, metadata)
            reference = oracle.Replay(books, design())
            grid, _ = raw.calendar_grid(['2030-01-01'], 10**10)
            with disk.open_replay(spool, metadata, design(), storage='disk') as (view, actual_source):
                self.assertEqual(source['counts'], actual_source['counts'])
                expected = raw.reconstruct(reference, source, grid, 10**10)
                actual = raw.reconstruct(view, actual_source, grid, 10**10)
                count = 0
                for a, b in zip(expected, actual, strict=True):
                    self.assertEqual(a, b)
                    count += 1
                self.assertEqual(count, 8640)
                path = Path(view.temporary.name)
                self.assertEqual(view.metrics['raw_records'], source['counts']['raw_records'])
                self.assertEqual(view.connection.execute('PRAGMA cache_size').fetchone()[0], -8192)
                self.assertTrue(view.connection.execute('PRAGMA query_only').fetchone()[0])
            self.assertFalse(path.exists())
            self.assertIsNone(view.connection)

    def test_seeded_asof_boundaries_and_all_execution_cells_match(self):
        with TemporaryDirectory() as directory:
            spool, metadata, _ = fixture(Path(directory))
            books, _ = oracle.load_session(spool, metadata)
            rng = random.Random(19)
            stamps = [-10**18, 0, 10**9+2, 1803*10**9+1002, 1803*10**9+1003,
                      *[rng.randrange(1, 1805*10**9) for _ in range(200)]]
            with disk.open_replay(spool, metadata, design(), storage='disk') as (view, _):
                for delay in (0, 25, 50, 100, 250, 500):
                    for holding in (250, 1000, 5000):
                        variant = deepcopy(design())
                        variant['execution'].update(decision_delay_ms=delay, holding_after_entry_ms=holding)
                        memory, indexed = oracle.Replay(books, variant), view.for_design(variant)
                        for venue in ('binance', 'okx'):
                            for stamp in stamps:
                                self.assertEqual(memory.at(venue, stamp), indexed.at(venue, stamp))
                        for stamp in (10*10**9, 20*10**9, 30*10**9, 40*10**9, 1803*10**9):
                            self.assertEqual(memory.features(stamp), indexed.features(stamp))
                            for action in (-1, 0, 1):
                                session = books['okx'][0].session
                                self.assertEqual(memory.execute(action, stamp, session), indexed.execute(action, stamp, session))

    def test_same_timestamp_last_written_quote_and_exact_retransmissions_match(self):
        with TemporaryDirectory() as directory:
            spool, metadata, _ = fixture(Path(directory))
            def ties(rows):
                out, inserted = [], False
                for row in rows:
                    if row['feed'] == 'binance-bbo':
                        payload = json.loads(base64.b64decode(row['payload']))
                        if inserted:
                            payload['u'] += 1
                            row['payload'] = base64.b64encode(json.dumps(payload).encode()).decode()
                        out.append(row)
                        if not inserted:
                            out.append(deepcopy(row))
                            extra = deepcopy(row)
                            payload.update(u=payload['u']+1, b='10000', a='10002')
                            extra['payload'] = base64.b64encode(json.dumps(payload).encode()).decode()
                            out.append(extra)
                            inserted = True
                    else:
                        out.append(row)
                return out
            rewrite(spool, ties)
            books, source = oracle.load_session(spool, metadata)
            memory = oracle.Replay(books, design())
            with disk.open_replay(spool, metadata, design(), storage='disk') as (view, actual):
                self.assertEqual(actual['counts']['exact_retransmissions'], 1)
                self.assertEqual(actual['counts'], source['counts'])
                self.assertEqual(view.at('binance', 10**9+2), memory.at('binance', 10**9+2))
                self.assertEqual(str(view.at('binance', 10**9+2).bid), '10000')

    def test_raw_build_verify_and_missing_row_checks_work_with_disk_storage(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool, metadata, calendar = fixture(root)
            target = root/'ledger.gz'
            before = {p.name:digest(p) for p in spool.iterdir()}
            with patch.object(raw, 'MAX_RAW_RECORDS', 100):
                blocked = raw.assess(spool, metadata, calendar, build_to=root/'memory.gz')
                built = raw.assess(spool, metadata, calendar, build_to=target, storage='disk')
            self.assertEqual(blocked['status'], 'BLOCKED_REPLAY_RESOURCE_LIMIT')
            self.assertEqual(built['status'], 'RAW_DERIVED_LEDGER_BUILT', built)
            self.assertFalse(built['confirmatory_inference_valid'])
            verified = raw.assess(spool, metadata, calendar, ledger=target, storage='disk')
            self.assertTrue(verified['raw_replay_matched'], verified)
            omitted = root/'omitted.gz'
            with gzip.open(target, 'rb') as source, gzip.open(omitted, 'wb') as writer:
                next(source)
                for line in source:
                    writer.write(line)
            self.assertEqual(raw.assess(spool, metadata, calendar, ledger=omitted, storage='disk')['status'], 'LEDGER_RAW_MISMATCH')
            self.assertEqual(before, {p.name:digest(p) for p in spool.iterdir()})

    def test_index_quota_exhaustion_cleans_derived_files_and_preserves_originals(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool, metadata, _ = fixture(root)
            created = []
            factory = TemporaryDirectory
            def temporary(**kwargs):
                value = factory(dir=root, **kwargs)
                created.append(Path(value.name))
                return value
            before = {p.name:digest(p) for p in spool.iterdir()}
            with patch.object(disk, 'TemporaryDirectory', side_effect=temporary), self.assertRaises((sqlite3.Error, disk.IndexFailure)):
                disk.DiskReplay(spool, metadata, design(), max_database_bytes=16384)
            self.assertTrue(created)
            self.assertTrue(all(not p.exists() for p in created))
            self.assertEqual(before, {p.name:digest(p) for p in spool.iterdir()})

    def test_bad_order_sequence_and_capture_faults_are_not_repaired(self):
        for mode in ('writer_regression', 'sequence_regression', 'conflict', 'fault'):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                spool, metadata = broken_fixture(Path(directory), mode=mode)
                with self.assertRaises(ValueError), closing(disk.DiskReplay(spool, metadata, design())):
                    pass

    def test_insufficient_depth_and_unknown_exit_inventory_match_the_oracle(self):
        with TemporaryDirectory() as directory:
            spool, metadata, _ = fixture(Path(directory))
            def thin_asks(rows):
                for row in rows:
                    if row['feed'] == 'okx-bbo':
                        payload = json.loads(base64.b64decode(row['payload']))
                        payload['data'][0]['asks'][0][1] = '.05'
                        row['payload'] = base64.b64encode(json.dumps(payload).encode()).decode()
                return rows
            rewrite(spool, thin_asks)
            books, _ = oracle.load_session(spool, metadata)
            memory = oracle.Replay(books, design())
            session = books['okx'][0].session
            with disk.open_replay(spool, metadata, design(), storage='disk') as (view, _):
                for action in (-1, 1):
                    self.assertEqual(memory.execute(action, 10*10**9, session), view.execute(action, 10*10**9, session))
                self.assertEqual(view.execute(1, 10*10**9, session)['reason'], 'insufficient_entry_depth')
                unknown = view.execute(-1, 10*10**9, session)
                self.assertIsNone(unknown['net_usdt'])
                self.assertEqual(unknown['residual_btc'], '-0.001')

    def test_controller_can_explicitly_select_disk_storage_without_promotion(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root/'data/raw/trial'
            stage.mkdir(parents=True)
            manifest = cohort_fixture(stage, total_days=1, captured=(0,))
            ledger = stage/'ledger.gz'
            cohort.assess(manifest, build_to=ledger, storage='disk')
            (stage/'calendar.json').write_text('["2030-01-01"]')
            config = {'cohort_manifest': 'data/raw/trial/cohort.json', 'replay_storage': 'disk',
                      'paired_evidence': {'ledger': 'data/raw/trial/ledger.gz', 'calendar': 'data/raw/trial/calendar.json'}}
            with patch.object(lab, 'ROOT', root):
                result = lab.paired_evaluation(config)
            self.assertTrue(result['raw_grid_verification']['raw_replay_matched'])
            self.assertEqual(result['secondary_review']['storage'], 'disk')
            self.assertFalse(result['deployment_authorized'])

    def test_cohort_and_fixed_controls_match_across_storage_modes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = cohort_fixture(root, total_days=2, captured=(0,))
            memory, indexed = root/'memory.gz', root/'indexed.gz'
            a, b = cohort.assess(manifest, build_to=memory), cohort.assess(manifest, build_to=indexed, storage='disk')
            self.assertEqual(a['counts'], b['counts'])
            with gzip.open(memory, 'rb') as x, gzip.open(indexed, 'rb') as y:
                self.assertEqual(x.read(), y.read())
            a, b = secondary.run(manifest), secondary.run(manifest, storage='disk')
            for key in ('cells', 'controls', 'daily', 'activity_checks', 'leave_one_date_out_primary_incremental_usdt'):
                self.assertEqual(a[key], b[key], key)
            self.assertFalse(b['confirmatory_inference_valid'])
