"""python -m cel — offline fixture demo. No sockets."""

from __future__ import annotations

from cel.ingest.fixture import DEFAULT_PATH, write_sample
from cel.summary import format_demo, measure


def main(argv: list[str] | None = None) -> int:
    if not DEFAULT_PATH.exists():
        write_sample(DEFAULT_PATH)
    print(format_demo(measure(DEFAULT_PATH)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
