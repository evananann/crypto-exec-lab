"""Discover official historical quote archives; catalog access never qualifies a study."""
import argparse
from datetime import date, datetime, timezone
import hashlib
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request

from research.autolab.qualification import digest
from research.autolab.reversal_depth import save
from research.continuous_capture import strict_json

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_HOSTS = {'www.okx.com', 'static.okx.com', 'data.binance.vision'}
MAX_DOWNLOAD_BYTES = 1_200_000_000


def validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None, 443)
            or (parsed.query and (parsed.hostname != 'www.okx.com' or parsed.path != '/api/v5/public/market-data-history'))):
        raise ValueError('only unsigned official HTTPS archive/catalog URLs are permitted')
    return parsed


class OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request(url, method='GET', limit=65536):
    from urllib.request import build_opener
    validate_url(url)
    try:
        with build_opener(OfficialRedirects()).open(Request(url, method=method,
                headers={'User-Agent': 'crypto-exec-lab-historical-discovery/1.0'}), timeout=25) as reply:
            validate_url(reply.url)
            body = reply.read(limit+1) if method == 'GET' else b''
            if len(body) > limit:
                raise ValueError('catalog response exceeds byte limit')
            length = reply.headers.get('Content-Length')
            return {'status': 'HTTP_OK', 'http_status': reply.status,
                    'content_length': int(length) if length is not None else None,
                    'response_sha256': hashlib.sha256(body).hexdigest()}, body
    except HTTPError as error:
        # Never emit response bodies, headers, signed redirects or raw exceptions.
        return {'status': 'HTTP_ERROR', 'http_status': error.code}, None
    except (URLError, TimeoutError, OSError):
        return {'status': 'NETWORK_OR_TRANSPORT_UNAVAILABLE', 'http_status': None}, None


def okx_url(day, module):
    start = int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp()*1000)
    return 'https://www.okx.com/api/v5/public/market-data-history?'+urlencode({
        'module': module, 'instType': 'SWAP', 'instFamilyList': 'BTC-USDT',
        'dateAggrType': 'daily', 'begin': start, 'end': start+86_400_000-1})


def okx_archives(body, day, module):
    payload = strict_json(body)
    if payload.get('code') != '0' or module not in (4, 5):
        raise ValueError('successful official order-book catalog response required')
    stamp = str(int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp()*1000))
    level = 400 if module == 4 else 5000
    name = f'BTC-USDT-SWAP-L2orderbook-{level}lv-{day.isoformat()}.tar.gz'
    expected_url = f'https://static.okx.com/cdn/okx/match/orderbook/pro/L2/{level}lv/daily/{day:%Y%m%d}/'+name
    found = []
    for section in payload['data']:
        if section['dateAggrType'] != 'daily':
            raise ValueError('wrong catalog aggregation')
        for group in section['details']:
            if group['instType'] != 'SWAP' or group['instFamily'] != 'BTC-USDT':
                raise ValueError('instrument family mismatch')
            for item in group['groupDetails']:
                validate_url(item['url'])
                if item['dateTs'] != stamp or item['filename'] != name or item['url'] != expected_url:
                    raise ValueError('date, instrument or native archive identity mismatch')
                found.append({'venue': 'okx', 'instrument': 'BTC-USDT-SWAP', 'module': module,
                    'url': item['url'], 'filename': name, 'advertised_size_mb': item['sizeMB'],
                    'timestamp_domain': 'UNVERIFIED_NATIVE_ARCHIVE', 'depth_quantity_unit': 'UNVERIFIED',
                    'schema_verified': False, 'instrument_metadata_verified': False})
    if len(found) > 1:
        raise ValueError('ambiguous archive ownership; no favorable replacement')
    return found


def binance_archive(day):
    name = f'BTCUSDT-bookTicker-{day.isoformat()}.zip'
    return {'venue': 'binance', 'instrument': 'BTCUSDT', 'filename': name,
        'url': f'https://data.binance.vision/data/futures/um/daily/bookTicker/BTCUSDT/{name}',
        'timestamp_domain': 'UNVERIFIED_NATIVE_ARCHIVE', 'depth_quantity_unit': 'UNVERIFIED',
        'schema_verified': False, 'instrument_metadata_verified': False}


def checksum(body, filename):
    value = body.decode('ascii').strip()
    match = re.fullmatch(r'([0-9a-f]{64})\s+\*?'+re.escape(filename), value)
    if match is None:
        raise ValueError('publisher checksum must name the exact original archive')
    return match[1]


def download(archive, root):
    from urllib.request import build_opener
    url = archive['url']
    validate_url(url)
    name = archive['filename']
    if Path(name).name != name:
        raise ValueError('safe original archive filename required')
    target, partial = root/name, root/(name+'.partial')
    if target.exists() or partial.exists():
        raise FileExistsError('never overwrite an original or orphan download')
    started = time.monotonic()
    with build_opener(OfficialRedirects()).open(Request(url,
            headers={'User-Agent': 'crypto-exec-lab-historical-discovery/1.0'}), timeout=30) as reply:
        validate_url(reply.url)
        size = reply.headers.get('Content-Length')
        if reply.status != 200 or size is None or not 0 < int(size) <= MAX_DOWNLOAD_BYTES:
            raise ValueError('bounded complete HTTP archive response required')
        expected, count = int(size), 0
        with partial.open('xb') as stream:
            while True:
                chunk = reply.read(1024*1024)
                if not chunk:
                    break
                count += len(chunk)
                if count > expected or count > MAX_DOWNLOAD_BYTES or time.monotonic()-started > 600:
                    raise ValueError('download exceeded size or elapsed-time budget; preserve orphan')
                stream.write(chunk)
        if count != expected:
            raise ValueError('truncated original download; preserve orphan')
    actual = digest(partial)
    if archive.get('publisher_sha256') and actual != archive['publisher_sha256']:
        raise ValueError('publisher archive checksum mismatch; preserve orphan')
    partial.rename(target)
    return {'filename': name, 'bytes': count, 'sha256': actual,
            'publisher_checksum_verified': archive.get('publisher_sha256') is not None,
            'schema_verified': False, 'historical_sample_qualified': False}


def discover(day, out, fetch=False):
    if day >= datetime.now(timezone.utc).date():
        raise ValueError('completed historical UTC day required')
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    for module in (4, 5):
        url = okx_url(day, module)
        probe, body = request(url)
        row = {'source': f'okx-native-{module}', 'catalog_url': url, 'catalog_probe': probe, 'archives': []}
        if body is not None:
            row['archives'] = okx_archives(body, day, module)
            # Modules 4/5 are accepted only with unsigned exact official URLs.
            (out/f'okx-module-{module}.json').write_bytes(body)
            for archive in row['archives']:
                archive['access_probe'], _ = request(archive['url'], method='HEAD')
        rows.append(row)
    archive = binance_archive(day)
    archive['access_probe'], _ = request(archive['url'], method='HEAD')
    check_probe, body = request(archive['url']+'.CHECKSUM', limit=8192)
    archive['checksum_probe'] = check_probe
    if body is not None:
        archive['publisher_sha256'] = checksum(body, archive['filename'])
        (out/'binance.CHECKSUM').write_bytes(body)
    rows.append({'source': 'binance-native-bookticker', 'archives': [archive]})
    downloads = []
    if fetch:
        # Predeclared preference: 400-level OKX, with no automatic date/module substitution.
        chosen = [archive, *rows[0]['archives']]
        for item in chosen:
            if item['access_probe']['status'] != 'HTTP_OK':
                raise ValueError('source not accessible; preserve discovery receipts and fix access first')
        if not archive.get('publisher_sha256') or len(chosen) != 2:
            raise ValueError('exact two-source catalog and Binance checksum required before download')
        for item in chosen:
            downloads.append(download(item, out))
    result = {'schema_version': 1, 'status': 'SOURCE_CATALOG_ONLY_NOT_QUALIFIED',
        'observed_at_utc': datetime.now(timezone.utc).isoformat(), 'historical_day_utc': day.isoformat(),
        'purpose': 'Find original Binance/OKX BTC perpetual archives without reading strategy outcomes.',
        'sources': rows, 'downloads': downloads, 'strategy_outcomes_computed': 0,
        'historical_sample_qualified': False, 'registered_study_eligible': False,
        'confirmatory_inference_valid': False, 'deployment_authorized': False,
        'qualification_blockers': ['Need complete bounded originals and source hashes.',
            'Need native schema, snapshot/delta/sequence and completeness verification.',
            'Need dated instrument metadata and native-to-BTC quantity semantics.',
            'Need timestamp-unit and clock-domain evidence; exchange times cannot substitute for receiver times.',
            'Need a separate reviewed historical design; no retrospective enrollment into the receive-time study.'],
        'implementation_sha256': digest(Path(__file__))}
    save(out/'discovery.json', result)
    save(out/'checksums.json', {p.name:digest(p) for p in sorted(out.iterdir()) if p.is_file() and not p.name.endswith('.partial')})
    return result


def verify_discovery(folder):
    """Verify dated discovery evidence offline; never retry downloads inside CI."""
    expected = strict_json((folder/'checksums.json').read_bytes())
    if not expected:
        raise ValueError('empty discovery evidence inventory')
    for name, checksum_value in expected.items():
        if Path(name).name != name or digest(folder/name) != checksum_value:
            raise ValueError('historical-source discovery checksum mismatch')
    report = strict_json((folder/'discovery.json').read_bytes())
    if (report['schema_version'] != 1 or report['status'] != 'SOURCE_CATALOG_ONLY_NOT_QUALIFIED'
            or report['implementation_sha256'] != digest(Path(__file__))
            or report['historical_sample_qualified'] is not False
            or report['registered_study_eligible'] is not False
            or report['strategy_outcomes_computed'] != 0 or report['downloads']):
        raise ValueError('discovery cannot promote historical or registered eligibility')
    day = date.fromisoformat(report['historical_day_utc'])
    if [row['source'] for row in report['sources']] != ['okx-native-4', 'okx-native-5', 'binance-native-bookticker']:
        raise ValueError('fixed candidate inventory changed')
    for index, module in enumerate((4, 5)):
        row = report['sources'][index]
        if row['catalog_url'] != okx_url(day, module):
            raise ValueError('original catalog request differs')
        if row['catalog_probe']['status'] == 'HTTP_OK':
            raw = folder/f'okx-module-{module}.json'
            if digest(raw) != row['catalog_probe']['response_sha256']:
                raise ValueError('catalog response identity differs')
            actual = [{k:v for k,v in item.items() if k != 'access_probe'} for item in row['archives']]
            if actual != okx_archives(raw.read_bytes(), day, module):
                raise ValueError('archive identities do not reproduce from catalog')
    native = report['sources'][2]['archives']
    if len(native) != 1 or any(native[0][k] != v for k,v in binance_archive(day).items()):
        raise ValueError('proposed Binance identity changed')
    if native[0]['checksum_probe']['status'] == 'HTTP_OK':
        raw = folder/'binance.CHECKSUM'
        if (digest(raw) != native[0]['checksum_probe']['response_sha256']
                or checksum(raw.read_bytes(), native[0]['filename']) != native[0]['publisher_sha256']):
            raise ValueError('Binance publisher checksum evidence differs')
    elif 'publisher_sha256' in native[0]:
        raise ValueError('publisher checksum cannot be invented without a successful read')
    return {'status': report['status'], 'historical_day_utc': day.isoformat(),
        'official_okx_archive_descriptions': sum(len(row['archives']) for row in report['sources'][:2]),
        'native_pair_downloaded': False, 'historical_sample_qualified': False,
        'registered_study_eligible': False, 'network_requests_this_check': 0,
        'strategy_outcomes_computed': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day', type=date.fromisoformat, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    result = discover(args.day, args.out, args.download)
    print(result['status'], 'strategy_outcomes_computed='+str(result['strategy_outcomes_computed']))


if __name__ == '__main__':
    main()
