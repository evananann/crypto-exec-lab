"""Append and read Event JSONL."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

from cel.ingest.schema import Event


class JsonlWriter:
    """Keep one handle open. Opening per line is too slow for a live tape."""

    def __init__(self, path: Path, *, append: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._handle: TextIO = path.open("a" if append else "w", encoding="utf-8")
        self._n = 0

    def write(self, event: Event) -> None:
        self._handle.write(json.dumps(event.to_dict(), separators=(",", ":")) + "\n")
        self._n += 1
        if self._n % 64 == 0:
            self._handle.flush()

    def close(self) -> None:
        try:
            self._handle.flush()
        finally:
            self._handle.close()

    def __enter__(self) -> JsonlWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def write_event(path: Path, event: Event) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), separators=(",", ":")) + "\n")


def iter_events(path: Path) -> Iterator[Event]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield Event.from_dict(json.loads(line))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{path}:{line_no}: bad event ({exc})") from exc
