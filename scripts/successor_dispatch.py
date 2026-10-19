"""One authenticated dispatch, with durable client send/ack evidence and no automatic retry."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4

from scripts.successor_claim import instant


def append(stream, row):
    stream.write(json.dumps(row, separators=(',', ':')) + '\n')
    stream.flush()
    os.fsync(stream.fileno())


def dispatch(repository, intended_start, out, *, clock=lambda: datetime.now(timezone.utc), run=subprocess.run):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('invalid repository')
    intended, sent = instant(intended_start), clock().astimezone(timezone.utc)
    protocol = json.loads(Path('configs/successor/protocol.json').read_text())
    if intended.microsecond or not 0 <= (sent-intended).total_seconds() <= protocol['maximum_start_lateness_seconds']:
        raise ValueError('dispatch only during the explicit prospective start window')
    identifier = uuid4().hex
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x') as stream:
        append(stream, {'phase':'request_prepared','repository':repository,'dispatch_id':identifier,
                        'intended_start_utc':intended.isoformat(),'dispatch_sent_client_utc':sent.isoformat(),
                        'scope':'Caller clock; server dispatch receipt and run ID not yet known'})
        payload = {'ref':'main','inputs':{'intended_start_utc':intended.isoformat(),
                    'dispatch_sent_at_utc':sent.isoformat(),'dispatch_id':identifier}}
        try:
            response = run(['gh','api','--method','POST',
                            f'repos/{repository}/actions/workflows/successor-rehearsal.yml/dispatches','--input','-'],
                           input=json.dumps(payload),capture_output=True,text=True)
            accepted = response.returncode == 0
        except Exception:
            accepted = False
        append(stream, {'phase':'request_acknowledged' if accepted else 'delivery_unconfirmed',
                        'dispatch_id':identifier,'acknowledged_client_utc':clock().astimezone(timezone.utc).isoformat(),
                        'workflow_run_verified':False,'automatic_retry':False})
    return accepted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository',required=True)
    parser.add_argument('--intended-start',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    accepted = dispatch(args.repository,args.intended_start,args.out)
    print('Dispatch acknowledged; verify the run and retain the receipt' if accepted else
          'Dispatch delivery unconfirmed; reconcile before any further action. No automatic retry performed.')
    return 0 if accepted else 1


if __name__=='__main__':
    raise SystemExit(main())
