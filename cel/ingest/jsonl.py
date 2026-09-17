"""Append and read Event JSONL."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from cel.ingest.schema import Event


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
