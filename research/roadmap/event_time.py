"""Bounded-memory receive-time contract and source-linked as-of trace."""

from dataclasses import asdict, dataclass, replace
from decimal import InvalidOperation
import hashlib
import json
import re

from research.decision_study.pipeline import decimal, integer

INSTRUMENTS = {"binance": "BTCUSDT", "okx": "BTC-USDT-SWAP"}


@dataclass(frozen=True)
class Observation:
    packet_id: str
    venue: str
    instrument: str
    exchange_ms: int
    receive_ms: int
    sequence: int
    session: str
    snapshot: bool
    bid: str
    ask: str
    bid_qty_btc: str
    ask_qty_btc: str
    quantity_unit: str
    quote_currency: str
    contract_kind: str
    segment_sha256: str
    raw_record_offset: int
    clock_qualified: bool

    def validate(self):
        for value in (self.exchange_ms, self.receive_ms, self.sequence, self.raw_record_offset):
            integer(value)
        if (
            not isinstance(self.packet_id, str)
            or not self.packet_id
            or not isinstance(self.session, str)
            or not self.session
        ):
            raise ValueError("packet and session identity required")
        if self.venue not in INSTRUMENTS or self.instrument != INSTRUMENTS[self.venue]:
            raise ValueError("unrecognized venue/instrument mapping")
        if (self.quantity_unit, self.quote_currency, self.contract_kind) != (
            "BTC",
            "USDT",
            "linear_perpetual",
        ):
            raise ValueError("explicit normalized BTC/USDT linear-contract units required")
        if type(self.snapshot) is not bool or self.clock_qualified is not True:
            raise ValueError("clock qualification and explicit snapshot flag required")
        if not isinstance(self.segment_sha256, str) or not re.fullmatch(
            "[0-9a-f]{64}", self.segment_sha256
        ):
            raise ValueError("source segment digest required")
        if (
            not 0 < decimal(self.bid) <= decimal(self.ask)
            or min(decimal(self.bid_qty_btc), decimal(self.ask_qty_btc)) <= 0
        ):
            raise ValueError("positive fillable BBO prices/depth required")


class ReceiveStream:
    """At most one book and last packet per venue; exact immediate retransmits dedup.

    Sequences must increase, but need not be contiguous (feed-dependent semantics).
    Non-immediate old duplicates fail as sequence regressions. Invalid input poisons
    the instance; start a newly qualified stream instead of silently repairing it.
    """

    def __init__(self, *, contiguous_sequences=False):
        if type(contiguous_sequences) is not bool:
            raise ValueError("explicit sequence policy required")
        self.contiguous_sequences = contiguous_sequences
        self.books = {}
        self.last_receive_ms = -1
        self.failed = False

    def consume(self, event):
        if self.failed:
            raise ValueError("stream invalidated; explicit requalification required")
        try:
            event.validate()
            if event.receive_ms < self.last_receive_ms:
                raise ValueError("receive clock regressed; no sorting repair")
            previous = self.books.get(event.venue)
            if previous is not None and event.packet_id == previous.packet_id:
                # Retransmits may have a later receipt/offset but cannot change economics.
                comparable = replace(
                    event,
                    receive_ms=previous.receive_ms,
                    raw_record_offset=previous.raw_record_offset,
                )
                if comparable != previous:
                    raise ValueError("conflicting duplicate packet")
                self.last_receive_ms = event.receive_ms
                return False
            if previous is None or previous.session != event.session:
                if not event.snapshot:
                    raise ValueError("new connection requires a qualified snapshot")
            elif event.sequence <= previous.sequence:
                raise ValueError("sequence regression")
            elif self.contiguous_sequences and event.sequence != previous.sequence + 1:
                raise ValueError("sequence gap under contiguous-feed contract")
            self.books[event.venue] = event
            self.last_receive_ms = event.receive_ms
            return True
        except (ValueError, TypeError, InvalidOperation):
            self.failed = True
            raise

    def asof(self, venue, decision_ms, max_age_ms=500):
        integer(decision_ms)
        integer(max_age_ms)
        if venue not in INSTRUMENTS:
            raise ValueError("unsupported venue")
        if self.failed:
            raise ValueError("stream invalidated")
        event = self.books.get(venue)
        if event is None or not 0 <= decision_ms - event.receive_ms <= max_age_ms:
            return None
        return event


def trace(event, decision_ms, max_age_ms=500):
    event.validate()
    integer(decision_ms)
    integer(max_age_ms)
    if not 0 <= decision_ms - event.receive_ms <= max_age_ms:
        raise ValueError("future or stale observation cannot support this decision")
    record = asdict(event) | {
        "decision_ms": decision_ms,
        "quote_age_ms": decision_ms - event.receive_ms,
        "source_identity_scope": "Digest and zero-based JSONL record offset; bytes require separate source verification",
    }
    record["trace_sha256"] = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return record
