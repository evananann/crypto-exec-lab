"""Temporary, bounded SQLite quote index; economic rules come from the existing oracle."""
from collections import Counter
from contextlib import contextmanager
from decimal import Decimal
import gzip
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory

from research.autolab.qualification import source_files, load_hypothesis
from research.continuous_capture import strict_json, verify_spool
from research.roadmap import empirical_pipeline as engine
from research.roadmap.feed_activity import normalize

MAX_DATABASE_BYTES = 4_000_000_000
RESERVE_BYTES = 1_000_000_000
CACHE_KIB = 8192


class IndexFailure(ValueError):
    pass


class IndexedReplay(engine.Replay):
    def __init__(self, connection, ends, design):
        self.connection, self.ends, self.design = connection, ends, design
        self.age = design['observations']['maximum_quote_age_ms']*engine.NS

    def at(self, venue, when):
        if venue not in self.ends or when > self.ends[venue]:
            return None
        # SQLite INTEGER has a signed 64-bit range. Far-out calendar requests are unavailable.
        if not -(2**63) <= when < 2**63:
            return None
        row = self.connection.execute('''SELECT available_ns, receive_ns, session,
            bid, ask, bid_qty, ask_qty, segment_sha256, line_number, byte_offset
            FROM quotes WHERE venue=? AND available_ns<=?
            ORDER BY available_ns DESC, ordinal DESC LIMIT 1''', (venue, when)).fetchone()
        if row is None or when-row[0] > self.age:
            return None
        return engine.Book(*row[:3], *(Decimal(value) for value in row[3:7]), *row[7:])

    def for_design(self, design):
        return IndexedReplay(self.connection, self.ends, design)


class DiskReplay(IndexedReplay):
    """Owns a fresh derived index. Original spools are never modified or subsampled."""
    def __init__(self, spool, metadata_directory, design, *, max_database_bytes=MAX_DATABASE_BYTES):
        self.temporary = TemporaryDirectory(prefix='crypto-replay-')
        self.connection = None
        try:
            path = Path(self.temporary.name)/'quotes.sqlite'
            if type(max_database_bytes) is not int or not 16384 <= max_database_bytes <= MAX_DATABASE_BYTES:
                raise ValueError('bounded derived-index byte allowance required')
            if shutil.disk_usage(path.parent).free < max_database_bytes+RESERVE_BYTES:
                raise IndexFailure('insufficient free space for derived index and reserve')
            connection = sqlite3.connect(path)
            self.connection = connection
            connection.execute('PRAGMA page_size=4096')
            connection.execute(f'PRAGMA max_page_count={max_database_bytes//4096}')
            connection.execute(f'PRAGMA cache_size=-{CACHE_KIB}')
            connection.execute('PRAGMA temp_store=FILE')
            connection.execute('PRAGMA mmap_size=0')
            connection.execute('''CREATE TABLE quotes(ordinal INTEGER PRIMARY KEY,
                venue TEXT NOT NULL, available_ns INTEGER NOT NULL, receive_ns INTEGER NOT NULL,
                session TEXT NOT NULL, bid TEXT NOT NULL, ask TEXT NOT NULL, bid_qty TEXT NOT NULL,
                ask_qty TEXT NOT NULL, segment_sha256 TEXT NOT NULL, line_number INTEGER NOT NULL,
                byte_offset INTEGER NOT NULL)''')
            # Maintain this index while ingesting: no all-record in-memory sort after loading.
            connection.execute('CREATE INDEX quote_asof ON quotes(venue, available_ns, ordinal)')
            source, ends = self._populate(Path(spool), Path(metadata_directory))
            connection.commit()
            connection.execute('PRAGMA query_only=ON')
            self.source = source
            self.metrics = {'storage': 'disk', 'database_bytes': path.stat().st_size,
                            'maximum_database_bytes': max_database_bytes, 'sqlite_cache_kib': CACHE_KIB,
                            'raw_records': source['counts']['raw_records'],
                            'indexed_quotes': sum(source['counts'].get(venue+'_bbo', 0) for venue in ends)}
            super().__init__(connection, ends, design)
        except BaseException:
            self.close()
            raise

    def _populate(self, spool, metadata_directory):
        before = source_files(spool, metadata_directory)
        inventory = verify_spool(spool)
        if (inventory['integrity_state'] != 'verified' or inventory['pending_session_status']
                or inventory['reported_capture_faults']):
            raise ValueError('sealed fault-free original spool required')
        selected = sorted(inventory['verified_segments'], key=lambda row: row['file'])
        sessions = {row['session_id'] for row in selected}
        if len(sessions) != 1:
            raise ValueError('one capture session required')
        maximum = load_hypothesis()['capture_requirements']['maximum_records']
        if inventory['records'] > maximum:
            raise IndexFailure('explicit qualification record budget exceeded')
        session = next(iter(sessions))
        first = last = None
        # Establish metadata bracketing on original writer coordinates before normalization.
        for segment in selected:
            with gzip.open(spool/segment['file'], 'rb') as stream:
                for line in stream:
                    stamp = strict_json(line)['writer_start_monotonic_ns']
                    first = stamp if first is None else first
                    last = stamp
        if first is None or not 0 < last-first <= 86400*10**9:
            raise ValueError('one positive bounded recording interval required')
        metadata = {venue: engine.metadata_pair(metadata_directory, venue, first, last) for venue in ('binance', 'okx')}
        previous, counts, ends = {}, Counter(), {}
        anchor, last_writer = None, -1
        for segment in selected:
            checksum = before['spool/'+segment['file']]
            with gzip.open(spool/segment['file'], 'rb') as stream:
                offset = 0
                for line_number, line in enumerate(stream, 1):
                    start, offset = offset, offset+len(line)
                    counts['raw_records'] += 1
                    if counts['raw_records'] > maximum:
                        raise IndexFailure('explicit qualification record budget exceeded')
                    row = strict_json(line)
                    received, writer, enqueued, wall = (row[k] for k in (
                        'receive_monotonic_ns', 'writer_start_monotonic_ns', 'enqueue_monotonic_ns', 'local_utc_ns'))
                    if (any(type(value) is not int or not 0 <= value < 2**63 for value in (received, writer, enqueued, wall))
                            or not received <= enqueued <= writer or writer < last_writer):
                        raise ValueError('invalid recorded availability order; no repair allowed')
                    last_writer = writer
                    if row['capture_session_id'] != session:
                        raise ValueError('segment/session mismatch')
                    mapping = wall-received
                    if anchor is not None and anchor != mapping:
                        raise ValueError('inconsistent session wall/monotonic anchor')
                    anchor = mapping
                    quotes, control = normalize(row, okx_metadata=metadata['okx'], binance_metadata=metadata['binance'])
                    counts['control_notices'] += control is not None
                    for quote in quotes:
                        venue = quote['venue']
                        old = previous.get(venue)
                        if old is not None and quote['session'] == old['session']:
                            if quote['receive_monotonic_ns'] < old['receive_monotonic_ns']:
                                raise ValueError('per-connection receive regression')
                            if quote['sequence'] < old['sequence']:
                                raise ValueError('per-connection sequence regression')
                            if quote['sequence'] == old['sequence']:
                                if any(quote[k] != old[k] for k in ('bid', 'ask', 'bid_native', 'ask_native')):
                                    raise ValueError('conflicting duplicate quote')
                                counts['exact_retransmissions'] += 1
                                continue
                        previous[venue] = quote
                        self.connection.execute('INSERT INTO quotes VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?)', (
                            venue, writer, received, quote['session'], quote['bid'], quote['ask'],
                            quote['bid_qty_btc'], quote['ask_qty_btc'], checksum, line_number, start))
                        counts[venue+'_bbo'] += 1
                        ends[venue] = writer
        if set(ends) != {'binance', 'okx'} or before != source_files(spool, metadata_directory):
            raise ValueError('missing instrument or original files changed during normalization')
        return {'selected_capture_session': session,
                'segment_sha256': {row['file']: before['spool/'+row['file']] for row in selected},
                'metadata_file_sha256': {key.split('/', 1)[1]: value for key, value in before.items() if key.startswith('metadata/')},
                'utc_minus_monotonic_ns': anchor, 'start_ns': first, 'end_ns': last, 'counts': dict(counts),
                'capture_faults': [], 'activity_only': False, 'independent_utc_accuracy_verified': False}, ends

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        self.temporary.cleanup()


@contextmanager
def open_replay(spool, metadata, design, *, storage):
    if storage == 'disk':
        try:
            view = DiskReplay(spool, metadata, design)
        except sqlite3.Error as error:
            raise IndexFailure('SQLite index unavailable or capacity exhausted') from error
        try:
            yield view, view.source
        finally:
            view.close()
    elif storage == 'memory':
        books, source = engine.load_session(spool, metadata)
        yield engine.Replay(books, design), source
    else:
        raise ValueError('unsupported replay storage')
