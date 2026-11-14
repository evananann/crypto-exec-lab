"""Kernel-enforced file-size failure in a disposable collector subprocess."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

CHILD = '''
import errno,json,os,resource,signal,sys
from pathlib import Path
from research.continuous_capture import Spool,verify_spool
root=Path(sys.argv[1])
s=Spool(root,reserve_bytes=0)
s.write({'fixture':'sealed before disk fault'})
s.seal()
before={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
signal.signal(signal.SIGXFSZ,signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE,(4096,4096))
error=None
try:
 s.write({'fixture':os.urandom(32768).hex()})
 s.seal()
except OSError as exc:
 error=exc.errno
 try:
  s.abandon()
 except OSError:
  pass
if error != errno.EFBIG:
 raise AssertionError('kernel did not enforce the file-size limit')
if not all((root/name).read_bytes()==value for name,value in before.items()):
 raise AssertionError('previous evidence changed')
inventory=verify_spool(root)
if inventory['integrity_state']!='incomplete' or len(inventory['verified_segments'])!=1:
 raise AssertionError('failed segment was promoted or prior segment lost')
print(json.dumps({'errno':error,'error_name':'EFBIG','previous_files_unchanged':True,
 'failed_segment_not_promoted':True,'inventory':inventory,'passed':True}))
'''


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='capture-disk-failure-') as directory:
        result = subprocess.run([sys.executable, '-c', CHILD, directory],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError('disk trial failed: ' + result.stderr)
        report = json.loads(result.stdout)
        report.update(schema_version=1, synthetic=True,
                      fault='kernel RLIMIT_FSIZE; real write failure, not a mocked OSError',
                      scope='Local file-size failure containment; does not reproduce full-volume ENOSPC, device failure or hosted storage behavior',
                      trial_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(args.out)
