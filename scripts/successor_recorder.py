"""Separate BBO-only successor recorder; frozen recorder and normalized schema stay unchanged."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from uuid import uuid4

from websocket import WebSocketApp

from cel.ingest.instruments import fetch_instrument
from cel.ingest.parse import parse_binance_message, parse_okx
from cel.ingest.record import Recorder, BINANCE_BBO_WS, OKX_WS


def utc():
    return datetime.now(timezone.utc).isoformat()


def specification(payload):
    row = payload['data'][0]
    return {key: row.get(key) for key in ('instId', 'instType', 'ctType', 'ctVal', 'ctMult',
            'ctValCcy', 'settleCcy', 'state', 'tickSz', 'lotSz', 'minSz')}


def normalize(payload, local_ts, venue, factor):
    """One provenance row per event; flag actual parser fallback, never timestamp equality."""
    if venue == 'binance':
        data = payload.get('data') if isinstance(payload.get('data'), dict) else payload
        event = parse_binance_message(payload, local_ts)
        if event is None or event.kind != 'bbo':
            return []
        source = 'E' if data.get('E') else 'T' if data.get('T') else 'local_receive'
        return [(event, source)]
    if payload.get('event') or (payload.get('arg') or {}).get('channel') != 'bbo-tbt':
        return []
    result = []
    for row in payload.get('data') or []:
        for event in parse_okx(payload | {'data': [row]}, local_ts, contract_value_btc=factor):
            result.append((event, 'ts' if row.get('ts') else 'local_receive'))
    return result


class ProvenanceRecorder(Recorder):
    def __init__(self, directory: Path, factor: float):
        super().__init__(directory / 'events.jsonl', okx_contract_value_btc=factor)
        self.directory = directory
        self.connections = {}
        self.connection_history = []
        self.provenance = (directory / 'provenance.jsonl').open('x')
        self.wire = (directory / 'wire.jsonl').open('x')
        self.parse_errors = Counter()

    def _bybit(self):
        pass

    def _binance_trade(self):
        pass

    def handlers(self, venue):
        def opened(ws):
            if not self._accept_open(ws):
                return
            identifier = uuid4().hex
            with self._lock:
                self.connections[id(ws)] = identifier
                self.connection_history.append({'venue': venue, 'connection_id': identifier,
                                                'opened_at_utc': utc()})
            self._mark_open(venue)
            if venue == 'okx':
                ws.send(json.dumps({'op': 'subscribe', 'args': [
                    {'channel': 'bbo-tbt', 'instId': 'BTC-USDT-SWAP'}]}))

        def message(ws, raw):
            if self._stop.is_set():
                return
            local_ts = self._now_ms()
            if raw in ('ping', 'pong'):
                if raw == 'ping':
                    ws.send('pong')
                return
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError('message is not an object')
                with self._lock:
                    if self._writer is None or self._stop.is_set():
                        return
                    connection = self.connections[id(ws)]
                    self.wire.write(json.dumps({'venue': venue, 'connection_id': connection,
                        'local_ts': local_ts, 'payload': payload}, separators=(',', ':')) + '\n')
                    for event, source in normalize(payload, local_ts, venue, self.okx_contract_value_btc):
                        row = {'event_index': self._written, 'venue': venue,
                               'connection_id': connection, 'exchange_timestamp_source': source,
                               'timestamp_fallback': source == 'local_receive'}
                        self._writer.write(event)
                        self.provenance.write(json.dumps(row, separators=(',', ':')) + '\n')
                        self._written += 1
                        self.written_by_venue[event.venue] += 1
                        self.written_by_kind[event.kind] += 1
            except Exception:
                with self._lock:
                    self.parse_errors[venue] += 1

        def closed(ws, _code, _reason):
            with self._lock:
                identifier = self.connections.pop(id(ws), None)
                for item in reversed(self.connection_history):
                    if item['connection_id'] == identifier:
                        item['closed_at_utc'] = utc()
                        break

        def error(_ws, _error):
            # Raw exception strings can include proxy/transport details; retain category only.
            self._note(venue + ': transport_error')

        return {'on_open': opened, 'on_message': message, 'on_close': closed, 'on_error': error}

    def _binance_bbo(self):
        self._run_ws('binance_bbo', WebSocketApp(BINANCE_BBO_WS, **self.handlers('binance')))

    def _okx(self):
        self._run_ws('okx', WebSocketApp(OKX_WS, **self.handlers('okx')))

    def run(self, seconds):
        try:
            return super().run(seconds)
        finally:
            # Base run has stopped writers first. Any surviving worker remains a failed gate.
            with self._lock:
                self.provenance.close()
                self.wire.close()
            (self.directory / 'connections.json').write_text(json.dumps({
                'connections': self.connection_history, 'parse_errors': dict(self.parse_errors),
                'scope': 'Connection opens/closes observed by client; no exchange-side delivery guarantee'
            }, indent=2) + '\n')


class InstrumentSampler:
    def __init__(self, directory, interval=60, fetch=fetch_instrument):
        self.path = directory / 'instruments.jsonl'
        self.interval, self.fetch = interval, fetch
        self.stop = threading.Event()
        self.failed = False
        self.first_specification = None
        self.changed = False
        self.count = 0
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.loop, name='instrument-sampler', daemon=True)

    def sample(self):
        try:
            payload, factor = self.fetch()
            spec = specification(payload)
            if self.first_specification is None:
                self.first_specification = spec
            elif spec != self.first_specification:
                self.changed = True
            row = {'observed_at_utc': utc(), 'payload': payload, 'factor_btc': factor}
        except Exception:
            self.failed = True
            row = {'observed_at_utc': utc(), 'error_category': 'instrument_fetch_or_validation_failed'}
            factor = None
        with self.lock, self.path.open('a') as stream:
            stream.write(json.dumps(row, separators=(',', ':')) + '\n')
            self.count += 1
        return factor

    def loop(self):
        while not self.stop.wait(self.interval):
            self.sample()

    def finish(self):
        self.stop.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=20)
        if self.thread.is_alive():
            self.failed = True
        else:
            self.sample()
