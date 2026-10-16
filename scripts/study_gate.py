"""Dependency-free Actions gate: preserve intended UTC slots through queue delays."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path


def gate(plan, now, *, event, mode='preflight', slot='am', schedule='', report=False):
    now = now.astimezone(timezone.utc)
    result = {'run': 'false', 'mode': mode, 'slot': slot, 'session': '', 'reason': ''}
    if event not in ('schedule', 'workflow_dispatch', 'push'):
        result['reason'] = 'unsupported event'
        return result
    if report:
        end = date.fromisoformat(plan['end_date_utc'])
        released = now.date() > end
        if event == 'schedule':
            released = released and now.date() == end + timedelta(days=1)
        result.update(run=str(released).lower(), mode='report', reason='released' if released else 'holdout not released or stale schedule')
        return result
    if event == 'push':
        mode = 'preflight'
    elif event == 'schedule':
        # Separate cron entries identify the intended slot. Never infer it from
        # the current hour: a queued AM job must not become a PM observation.
        fields = schedule.split()
        clock = f'{int(fields[1]):02}:{int(fields[0]):02}' if len(fields) == 5 and all(x.isdecimal() for x in fields[:2]) else ''
        matches = [name for name, value in plan['slots_utc'].items() if value == clock]
        if len(matches) != 1:
            result['reason'] = 'unrecognized schedule'
            return result
        slot, mode = matches[0], 'collect'
    if mode not in ('preflight', 'collect') or slot not in plan['slots_utc']:
        result['reason'] = 'invalid mode or slot'
        return result
    result.update(mode=mode, slot=slot)
    if mode == 'preflight':
        result.update(run='true', session=f'preflight-{now:%Y%m%dT%H%M%SZ}', reason='bounded preflight')
        return result
    day = str(now.date())
    scheduled = datetime.fromisoformat(f"{day}T{plan['slots_utc'][slot]}:00+00:00")
    in_window = plan['start_date_utc'] <= day <= plan['end_date_utc']
    in_slot = 0 <= (now - scheduled).total_seconds() <= plan['slot_tolerance_minutes'] * 60
    result.update(run=str(in_window and in_slot).lower(), session=f'{day}-{slot}',
                  reason='scheduled slot' if in_window and in_slot else 'outside frozen dates or slot')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=Path('configs/study_v1.json'))
    parser.add_argument('--event', required=True)
    parser.add_argument('--mode', default='preflight')
    parser.add_argument('--slot', default='am')
    parser.add_argument('--schedule', default='')
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    result = gate(json.loads(args.plan.read_text()), datetime.now(timezone.utc),
                  event=args.event, mode=args.mode or 'preflight', slot=args.slot or 'am',
                  schedule=args.schedule, report=args.report)
    with args.output.open('a', encoding='utf-8') as stream:
        for key, value in result.items():
            # Outputs are parsed by the Actions runner; prevent multiline values.
            stream.write(f'{key}={value.replace(chr(10), " ").replace(chr(13), " ")}\n')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
