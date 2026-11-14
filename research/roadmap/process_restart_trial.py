"""Offline process-death trial for collector ownership and segment preservation."""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from research.continuous_capture import Spool, capture_owner, verify_spool

CHILD = '''
import json,sys
from pathlib import Path
from research.continuous_capture import Spool,capture_owner
with capture_owner(sys.argv[1]):
 s=Spool(sys.argv[1],reserve_bytes=0)
 s.write({'fixture':'completed before death'})
 s.seal()
 s.write({'fixture':'interrupted at death'})
 s.raw.flush()
 print('READY',flush=True)
 sys.stdin.read()
'''


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='capture-process-trial-') as directory:
        root = Path(directory)
        child = subprocess.Popen([sys.executable, '-c', CHILD, directory],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            # communicate through an explicit readiness signal, not a guessed startup delay.
            import selectors
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                if not selector.select(timeout=15) or child.stdout.readline().strip() != 'READY':
                    raise RuntimeError('child did not become ready')
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in root.iterdir() if p.is_file()}
            refused = False
            try:
                with capture_owner(root):
                    pass
            except RuntimeError:
                refused = True
            if not refused:
                raise AssertionError('concurrent spool owner was accepted')
            child.kill()
            exit_code = child.wait(timeout=10)
            if exit_code != -signal.SIGKILL:
                raise AssertionError('child was not killed as specified')
            after_death = verify_spool(root)
            with capture_owner(root):
                spool = Spool(root, reserve_bytes=0)
                interrupted = list(spool.interrupted)
                spool.write({'fixture': 'fresh session after process death'})
                spool.seal()
            unchanged = all((root/name).exists() and hashlib.sha256((root/name).read_bytes()).hexdigest() == sha
                            for name, sha in before.items())
            after_restart = verify_spool(root)
            if not (unchanged and interrupted and after_death['integrity_state'] == 'incomplete'
                    and after_restart['integrity_state'] == 'incomplete'
                    and len(after_restart['verified_segments']) == 2):
                raise AssertionError('restart repaired, lost or misclassified interrupted evidence')
            report = dict(schema_version=1, synthetic=True, process_killed=True,
                          child_exit_code=exit_code, concurrent_owner_refused=refused,
                          lock_reacquired_after_death=True, previous_files_unchanged=unchanged,
                          interrupted_files_retained=interrupted,
                          after_death=after_death, after_restart=after_restart,
                          passed=True, scope='Real local process death and restart; fixture records, no exchange transport or deployment qualification')
            (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
            return report
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
            child.stdin.close()
            child.stdout.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(args.out)
