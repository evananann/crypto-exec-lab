"""Pinned archive/member binding, clock diagnostics and a non-activating study draft."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import tarfile

from research.autolab.qualification import digest, source_files, qualify, load_hypothesis, HYPOTHESIS
from research.continuous_capture import strict_json, verify_spool

ROOT = Path(__file__).resolve().parents[2]
CATALOG = Path(__file__).with_name('retained_sources.json')
SOURCE_ID = 'public-rehearsal-20261123'
CLOCK_PROFILE = {'maximum_sample_gap_ns': 60_000_000_000, 'maximum_pair_uncertainty_ns': 1_000_000,
                 'maximum_sampled_wall_step_ns': 1_000_000, 'maximum_daemon_error_estimate_s': .001,
                 'maximum_reference_age_s': 300}


def pinned_source(source_id=SOURCE_ID):
    catalog = strict_json(CATALOG.read_bytes())
    if catalog['schema_version'] != 1 or source_id not in catalog['sources']:
        raise ValueError('unknown reviewed source inventory')
    source = catalog['sources'][source_id]
    receipt_path = ROOT/source['receipt_file']
    if digest(receipt_path) != source['receipt_sha256']:
        raise ValueError('approved preservation receipt changed')
    receipt = strict_json(receipt_path.read_bytes())
    if receipt['status'] != 'REMOTE_READBACK_VERIFIED' or receipt['release_url'] != source['release_url']:
        raise ValueError('preservation source differs from reviewed catalog')
    return source, receipt


def archive_inventory(archive, expected_sha256, members):
    if archive.is_symlink() or digest(archive) != expected_sha256:
        raise ValueError('archive differs from approved retained bytes')
    if not isinstance(members, dict) or not 1 <= len(members) <= 1024:
        raise ValueError('bounded approved member inventory required')
    found, total = {}, 0
    with tarfile.open(archive, 'r|gz') as stream:
        for item in stream:
            path = PurePosixPath(item.name)
            if (not item.isfile() or path.is_absolute() or '..' in path.parts
                    or item.name in found or item.name not in members
                    or item.size < 0 or item.size > 128_000_000):
                raise ValueError('unexpected or unsafe retained member')
            total += item.size
            if total > 1_000_000_000:
                raise ValueError('retained archive decompression budget exceeded')
            reader = stream.extractfile(item)
            checksum = hashlib.sha256()
            for chunk in iter(lambda: reader.read(1024*1024), b''):
                checksum.update(chunk)
            found[item.name] = checksum.hexdigest()
            if found[item.name] != members[item.name]:
                raise ValueError('retained member checksum mismatch')
    if found != members or digest(archive) != expected_sha256:
        raise ValueError('retained inventory incomplete or archive changed')
    return found


def member_map_digest(mapping):
    return hashlib.sha256(json.dumps(mapping, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def bind_recording(spool, metadata, members, metadata_prefix):
    source = source_files(spool, metadata)
    mapping, excluded = {}, []
    for local, checksum in source.items():
        if local == 'spool/.capture.lock' and checksum == hashlib.sha256(b'').hexdigest():
            excluded.append(local)
            continue
        target = metadata_prefix+local.split('/', 1)[1] if local.startswith('metadata/') else local
        if members.get(target) != checksum:
            raise ValueError('local recording differs from pinned retained inventory')
        mapping[local] = {'archive_member': target, 'sha256': checksum}
    required_metadata = {f'metadata/{venue}-{role}.json' for venue in ('binance', 'okx') for role in ('before', 'after')}
    if not required_metadata <= set(mapping) or not any(name.endswith('.jsonl.gz') for name in mapping):
        raise ValueError('complete recording and original metadata required')
    return {'matched_local_files': len(mapping), 'members': mapping, 'excluded_empty_operational_files': excluded}


def recording_bounds(spool):
    inventory = verify_spool(spool)
    if inventory['integrity_state'] != 'verified' or inventory['pending_session_status']:
        raise ValueError('sealed original source integrity required')
    sessions = {row['session_id'] for row in inventory['verified_segments']}
    if len(sessions) != 1 or inventory['records'] > 2_000_000:
        raise ValueError('one bounded capture session required')
    import gzip
    first = last = None
    for segment in sorted(inventory['verified_segments'], key=lambda row: row['file']):
        with gzip.open(spool/segment['file'], 'rb') as stream:
            for line in stream:
                stamp = strict_json(line)['writer_start_monotonic_ns']
                if type(stamp) is not int or stamp < 0 or last is not None and stamp < last:
                    raise ValueError('recorded availability ordering failed')
                first = stamp if first is None else first
                last = stamp
    if first is None or last <= first:
        raise ValueError('positive original recording span required')
    return first, last


def clock_review(path, start_ns, end_ns):
    with path.open('rb') as stream:
        original_bytes = stream.read(2_000_001)
    if len(original_bytes) > 2_000_000:
        raise ValueError('clock evidence byte budget exceeded')
    samples = [strict_json(line) for line in original_bytes.splitlines()]
    if not 2 <= len(samples) <= 10000 or not 0 <= start_ns < end_ns:
        raise ValueError('bounded bracketing clock samples required')
    checks = {'boundary_phases': samples[0]['phase'] == 'before_session' and samples[-1]['phase'] == 'after_session',
              'interior_phases': all(row.get('phase') == 'periodic' for row in samples[1:-1]),
              'brackets_recording': True, 'ordered_samples': True, 'sample_gaps': True,
              'pair_uncertainty': True, 'sampled_wall_consistency': True,
              'daemon_diagnostics_available': True, 'daemon_error_estimate': True, 'fresh_reference': True}
    prior = None
    unavailable = 0
    unavailable_reasons = set()
    for sample in samples:
        for field in ('monotonic_ns', 'wall_ns', 'pair_uncertainty_ns'):
            if type(sample[field]) is not int or sample[field] < 0:
                raise ValueError('invalid original clock pair')
        mono, wall, uncertainty = (sample[k] for k in ('monotonic_ns', 'wall_ns', 'pair_uncertainty_ns'))
        checks['pair_uncertainty'] &= uncertainty <= CLOCK_PROFILE['maximum_pair_uncertainty_ns']
        if prior is not None:
            gap = mono-prior['monotonic_ns']
            checks['ordered_samples'] &= gap > 0
            checks['sample_gaps'] &= 0 < gap <= CLOCK_PROFILE['maximum_sample_gap_ns']
            step = abs(wall-prior['wall_ns']-gap)+uncertainty+prior['pair_uncertainty_ns']
            checks['sampled_wall_consistency'] &= step <= CLOCK_PROFILE['maximum_sampled_wall_step_ns']
        prior = sample
        ntp = sample['ntp']
        if not (ntp.get('available') is True and ntp.get('provider') == 'chronyc tracking -c'
                and ntp.get('daemon_reports_synchronised') is True
                and ntp.get('leap_status') in ('Normal', 'Insert second', 'Delete second')):
            checks['daemon_diagnostics_available'] = False
            checks['daemon_error_estimate'] = checks['fresh_reference'] = False
            unavailable += 1
            reason = ntp.get('reason')
            unavailable_reasons.add(reason if reason in ('chronyc_not_installed', 'chrony_probe_unavailable_or_invalid')
                                    else 'daemon_diagnostics_unavailable_or_inconsistent')
            continue
        numbers = [ntp[k] for k in ('system_correction_s', 'root_delay_s', 'root_dispersion_s', 'reference_time_epoch_s')]
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in numbers):
            raise ValueError('finite numeric daemon diagnostics required')
        correction, delay, dispersion, reference = numbers
        if delay < 0 or dispersion < 0 or type(ntp['stratum']) is not int or not 1 <= ntp['stratum'] <= 15:
            raise ValueError('invalid daemon dispersion, delay or stratum')
        bound = abs(correction)+delay/2+dispersion
        checks['daemon_error_estimate'] &= bound <= CLOCK_PROFILE['maximum_daemon_error_estimate_s']
        checks['fresh_reference'] &= 0 <= wall/1e9-reference <= CLOCK_PROFILE['maximum_reference_age_s']
    checks['brackets_recording'] = samples[0]['monotonic_ns'] <= start_ns < end_ns <= samples[-1]['monotonic_ns']
    return {'status': 'DIAGNOSTIC_PROFILE_PASSED' if all(checks.values()) else 'CLOCK_EVIDENCE_INSUFFICIENT',
            'samples': len(samples), 'unavailable_daemon_samples': unavailable,
            'unavailable_reason_codes': sorted(unavailable_reasons), 'checks': checks,
            'profile': CLOCK_PROFILE, 'clock_file_sha256': hashlib.sha256(original_bytes).hexdigest(),
            'independent_utc_accuracy_verified': False,
            'scope': 'Archived software/daemon diagnostics only. Passing sampled checks is not independent UTC accuracy proof or continuous clock-error assurance.'}


def draft(archive_binding, clocks, capture):
    hypothesis = load_hypothesis()
    design = strict_json((ROOT/hypothesis['design_file']).read_bytes())
    checks = {'retained_archive_member_binding': archive_binding.get('local_member_binding_verified') is True,
              'capture_mechanics': capture.get('mechanical_capture_acceptable') is True,
              'daemon_clock_profile': clocks.get('status') == 'DIAGNOSTIC_PROFILE_PASSED',
              'independent_utc_accuracy': False, 'target_host_qualification': False,
              'independent_origin_attestation': False, 'complete_cohort_adapter': False,
              'prospective_publication_before_collection': False,
              'source_bound_sensitivity_and_placebo_checks': False, 'perpetual_execution_calibration': False}
    names = ('research/continuous_capture.py', 'research/clock_telemetry.py',
             'research/roadmap/empirical_pipeline.py', 'research/roadmap/feed_activity.py',
             'research/roadmap/public_instruments.py', 'research/roadmap/paired_inference.py',
             'research/roadmap/followon.py', 'research/decision_study/pipeline.py')
    sources = {name: digest(ROOT/name) for name in (*names, 'uv.lock', 'pyproject.toml')}
    sources.update({str(path.relative_to(ROOT)): digest(path) for path in Path(__file__).parent.glob('*.json')})
    sources.update({str(path.relative_to(ROOT)): digest(path) for path in Path(__file__).parent.glob('*.py')})
    return {'schema_version': 1, 'state': 'DRAFT_NOT_ENROLLED', 'hypothesis_sha256': digest(HYPOTHESIS),
            'design_sha256': hypothesis['design_sha256'], 'checks': checks,
            'blockers': [key for key, passed in checks.items() if not passed],
            'source_sha256': sources, 'calendar': {'fixed_dates': None,
                'discovery_days': design['calendar']['discovery_days'], 'validation_days': design['calendar']['validation_days'],
                'untouched_test_days': design['calendar']['untouched_test_days'],
                'embargo_days_after_discovery': design['calendar']['embargo_days_after_discovery'],
                'embargo_days_after_validation': design['calendar']['embargo_days_after_validation'],
                'minimum_complete_utc_days_after_qualification_and_publication': 2},
            'scientific_enrollment': False, 'deployment_authorized': False, 'strategy_outcomes_computed': 0,
            'scope': 'Evidence assessment and source-bound enrollment preparation only. No activation, retrospective enrollment, study dates or publication attestation are issued.'}


def assess(archive, spool, metadata, source_id=SOURCE_ID):
    source, receipt = pinned_source(source_id)
    members = archive_inventory(archive, receipt['archive_sha256'], receipt['member_sha256'])
    binding = bind_recording(spool, metadata, members, source['metadata_prefix'])
    if member_map_digest(binding['members']) != source['local_member_map_sha256']:
        raise ValueError('local recording subset differs from reviewed source identity')
    start, end = recording_bounds(spool)
    clock_name = Path(source['clock_member']).name
    if 'spool/'+clock_name not in binding['members']:
        raise ValueError('reviewed capture clock evidence missing')
    clocks = clock_review(spool/clock_name, start, end)
    if clocks['clock_file_sha256'] != receipt['member_sha256'][source['clock_member']]:
        raise ValueError('parsed clock bytes differ from reviewed archive')
    capture = qualify(spool=spool, metadata=metadata)
    if bind_recording(spool, metadata, members, source['metadata_prefix']) != binding:
        raise ValueError('original source files changed during review')
    archive_binding = {'source_id': source_id, 'approved_receipt_sha256': source['receipt_sha256'],
        'archive_sha256': receipt['archive_sha256'], 'archive_members_verified': len(members),
        'retained_archive_bytes_verified': True, 'local_member_binding_verified': True,
        'release_url': source['release_url'], **binding,
        'venue_origin_authenticated': False, 'worm_or_object_lock': False,
        'scope': 'Provided archive matches the reviewed independently read-back preservation inventory. Same-provider administrator mutability and upstream venue authenticity remain outside this proof.'}
    return {'assessed_at_utc': datetime.now(timezone.utc).isoformat(), 'archive_binding': archive_binding,
            'clock_review': clocks, 'capture_status': capture['status'], 'capture_checks': capture['checks'],
            'recording_bounds_ns': [start, end], 'draft': draft(archive_binding, clocks, capture)}


def published_readiness():
    """Recheck archived clock bytes; prior archive comparison is explicitly historical."""
    folder = ROOT/'reports/enrollment_evidence_20261125'
    source, receipt = pinned_source()
    clock = folder/'clock-original.jsonl'
    if digest(clock) != receipt['member_sha256'][source['clock_member']]:
        raise ValueError('published clock differs from approved retained member')
    saved = strict_json((folder/'assessment.json').read_bytes())
    archived = saved['archive_binding']
    if (archived['approved_receipt_sha256'] != source['receipt_sha256']
            or archived['archive_sha256'] != receipt['archive_sha256']):
        raise ValueError('published archive evidence binding differs')
    if member_map_digest(archived['members']) != source['local_member_map_sha256']:
        raise ValueError('published member mapping differs from reviewed recording')
    for item in archived['members'].values():
        if receipt['member_sha256'].get(item['archive_member']) != item['sha256']:
            raise ValueError('published local member is absent from reviewed archive')
    clocks = clock_review(clock, *saved['recording_bounds_ns'])
    if clocks['clock_file_sha256'] != receipt['member_sha256'][source['clock_member']]:
        raise ValueError('parsed clock evidence differs from reviewed archive')
    capture = {'mechanical_capture_acceptable': False}
    # Do not accept a report's qualification Boolean as evidence of a current host.
    historical = dict(archived, local_member_binding_verified=True)
    packet = draft(historical, clocks, capture)
    return {'status': 'BLOCKED_NOT_ENROLLED', 'archive_review': 'PREVIOUSLY_VERIFIED_NOT_REDOWLOADED',
            'previous_assessment_utc': saved['assessed_at_utc'], 'clock_review': clocks,
            'draft': packet, 'deployment_authorized': False,
            'scope': 'Historical rehearsal evidence only. Does not qualify a new recording, host or live account.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--spool', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.archive, args.spool, args.metadata)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'assessment.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(result['draft']['state'])
    return 0  # Successful assessment is distinct from scientific readiness.


if __name__ == '__main__':
    raise SystemExit(main())
