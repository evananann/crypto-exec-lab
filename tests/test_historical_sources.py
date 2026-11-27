from datetime import date
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import URLError

from research.autolab import historical_sources as sources

DAY = date(2026, 9, 1)


def catalog(module=4):
    levels = 400 if module == 4 else 5000
    name = f'BTC-USDT-SWAP-L2orderbook-{levels}lv-2026-09-01.tar.gz'
    url = f'https://static.okx.com/cdn/okx/match/orderbook/pro/L2/{levels}lv/daily/20260901/'+name
    return {'code': '0', 'data': [{'dateAggrType': 'daily', 'details': [{
        'instType': 'SWAP', 'instFamily': 'BTC-USDT', 'groupDetails': [{
            'dateTs': '1788220800000', 'filename': name, 'url': url, 'sizeMB': '361.05'}]}]}]}


class Reply:
    status = 200
    def __init__(self, data, url, length=None):
        from io import BytesIO
        self.stream = BytesIO(data)
        self.url = url
        self.headers = {'Content-Length': str(len(data) if length is None else length)}
    def read(self, n):
        return self.stream.read(n)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.stream.close()


class HistoricalSourceTests(unittest.TestCase):
    def test_exact_day_instrument_module_mapping_and_no_qualification_promotion(self):
        for module in (4, 5):
            rows = sources.okx_archives(json.dumps(catalog(module)).encode(), DAY, module)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['instrument'], 'BTC-USDT-SWAP')
            self.assertFalse(rows[0]['schema_verified'])
            self.assertFalse(rows[0]['instrument_metadata_verified'])
            self.assertEqual(rows[0]['timestamp_domain'], 'UNVERIFIED_NATIVE_ARCHIVE')

    def test_changed_instrument_day_or_ambiguous_source_fails(self):
        for field, bad in (('dateTs', '0'), ('filename', 'ETH-USDT-SWAP.tar.gz')):
            value = catalog()
            value['data'][0]['details'][0]['groupDetails'][0][field] = bad
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                sources.okx_archives(json.dumps(value).encode(), DAY, 4)
        value = catalog()
        value['data'][0]['details'][0]['groupDetails'] *= 2
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            sources.okx_archives(json.dumps(value).encode(), DAY, 4)

    def test_signed_urls_credentials_http_and_unapproved_redirects_are_rejected(self):
        for url in ('http://static.okx.com/a', 'https://static.okx.com/a?Signature=secret',
                    'https://user:password@static.okx.com/a', 'https://untrusted.example/a',
                    'https://static.okx.com:444/a'):
            with self.assertRaises(ValueError):
                sources.validate_url(url)
        with self.assertRaises(ValueError):
            sources.OfficialRedirects().redirect_request(None, None, 302, '', {}, 'https://untrusted.example/file')

    def test_checksum_cannot_bind_a_different_archive(self):
        filename = sources.binance_archive(DAY)['filename']
        expected = 'a'*64
        self.assertEqual(sources.checksum((expected+'  '+filename+'\n').encode(), filename), expected)
        with self.assertRaises(ValueError):
            sources.checksum((expected+'  wrong.zip').encode(), filename)

    def test_transport_failure_is_unavailable_not_absent_data_and_hides_raw_errors(self):
        with patch('urllib.request.build_opener') as builder:
            builder.return_value.open.side_effect = URLError('private signed URL detail')
            result, body = sources.request(sources.binance_archive(DAY)['url'], method='HEAD')
        self.assertEqual(result['status'], 'NETWORK_OR_TRANSPORT_UNAVAILABLE')
        self.assertNotIn('private', json.dumps(result))
        self.assertIsNone(body)

    def test_truncation_preserves_partial_file_and_never_becomes_original(self):
        item = sources.binance_archive(DAY)
        with TemporaryDirectory() as directory, patch('urllib.request.build_opener') as builder:
            root = Path(directory)
            builder.return_value.open.return_value = Reply(b'short', item['url'], length=10)
            with self.assertRaisesRegex(ValueError, 'truncated'):
                sources.download(item, root)
            self.assertTrue((root/(item['filename']+'.partial')).exists())
            self.assertFalse((root/item['filename']).exists())
            with self.assertRaises(FileExistsError):
                sources.download(item, root)

    def test_wrong_checksum_preserves_orphan_and_never_commits_original(self):
        item = sources.binance_archive(DAY)
        item['publisher_sha256'] = 'a'*64
        with TemporaryDirectory() as directory, patch('urllib.request.build_opener') as builder:
            root = Path(directory)
            builder.return_value.open.return_value = Reply(b'corrupt', item['url'])
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                sources.download(item, root)
            self.assertTrue((root/(item['filename']+'.partial')).exists())
            self.assertFalse((root/item['filename']).exists())

    def test_download_verifies_publisher_hash_without_claiming_schema_or_clock(self):
        item = sources.binance_archive(DAY)
        body = b'synthetic-container-bytes'
        item['publisher_sha256'] = hashlib.sha256(body).hexdigest()
        with TemporaryDirectory() as directory, patch('urllib.request.build_opener') as builder:
            builder.return_value.open.return_value = Reply(body, item['url'])
            row = sources.download(item, Path(directory))
            self.assertTrue(row['publisher_checksum_verified'])
            self.assertFalse(row['schema_verified'])
            self.assertFalse(row['historical_sample_qualified'])

    def test_accessible_catalog_and_head_checks_still_do_not_qualify_a_study(self):
        filename = sources.binance_archive(DAY)['filename']
        def fake_request(url, method='GET', limit=65536):
            if 'market-data-history' in url:
                module = 4 if 'module=4&' in url else 5
                raw = json.dumps(catalog(module)).encode()
                return {'status': 'HTTP_OK', 'http_status': 200, 'response_sha256': hashlib.sha256(raw).hexdigest()}, raw
            if url.endswith('.CHECKSUM'):
                raw = ('a'*64+'  '+filename).encode()
                return {'status': 'HTTP_OK', 'http_status': 200, 'response_sha256': hashlib.sha256(raw).hexdigest()}, raw
            return {'status': 'HTTP_OK', 'http_status': 200}, b''
        with TemporaryDirectory() as directory, patch.object(sources, 'request', side_effect=fake_request) as mocked:
            row = sources.discover(DAY, Path(directory)/'out')
            self.assertEqual(row['status'], 'SOURCE_CATALOG_ONLY_NOT_QUALIFIED')
            self.assertFalse(row['registered_study_eligible'])
            self.assertFalse(row['historical_sample_qualified'])
            self.assertEqual(row['strategy_outcomes_computed'], 0)
            self.assertEqual(row['downloads'], [])
            before = mocked.call_count
            verified = sources.verify_discovery(Path(directory)/'out')
            self.assertEqual(verified['official_okx_archive_descriptions'], 2)
            self.assertEqual(mocked.call_count, before)
            row['historical_sample_qualified'] = True
            folder = Path(directory)/'out'
            (folder/'discovery.json').write_text(json.dumps(row))
            checksums = json.loads((folder/'checksums.json').read_bytes())
            checksums['discovery.json'] = sources.digest(folder/'discovery.json')
            (folder/'checksums.json').write_text(json.dumps(checksums))
            with self.assertRaisesRegex(ValueError, 'cannot promote'):
                sources.verify_discovery(folder)


if __name__ == '__main__':
    unittest.main()
