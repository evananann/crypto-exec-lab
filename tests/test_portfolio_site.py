import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import tomllib
import unittest

from research.portfolio_site import ROOT, build, pages_gate


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('href', 'src'):
                self.links.append(value)


class PortfolioSiteTests(unittest.TestCase):
    def test_allowlisted_site_links_checksums_and_synthetic_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'site'
            build(output)
            self.assertEqual({p.name for p in output.iterdir()}, {'index.html', 'experiment.html',
                'cost-lab.html', 'hero.png', 'leadlag.png', 'site-checksums.json'})
            for name in ('index.html', 'experiment.html', 'cost-lab.html'):
                page = (output/name).read_text()
                self.assertIn('synthetic', page.lower())
                parser = Links()
                parser.feed(page)
                for link in parser.links:
                    if not link.startswith(('https://', '#')):
                        self.assertTrue((output/link).is_file(), link)
            for name, expected in json.loads((output/'site-checksums.json').read_text()).items():
                self.assertEqual(hashlib.sha256((output/name).read_bytes()).hexdigest(), expected)
            with self.assertRaises(FileExistsError):
                build(output)

    def test_incomplete_manifest_and_nonsynthetic_inputs_are_rejected(self):
        import shutil
        from unittest.mock import patch
        from research import portfolio_site
        for mode in ('missing_manifest_entry', 'nonsynthetic'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root/'reports/opportunity'
                shutil.copytree(ROOT/'reports/opportunity', source)
                manifest = json.loads((source/'checksums.json').read_text())
                if mode == 'missing_manifest_entry':
                    del manifest['hero.png']
                else:
                    report = json.loads((source/'opportunity.json').read_text())
                    report['synthetic'] = False
                    report['market_tapes_read'] = 1
                    (source/'opportunity.json').write_text(json.dumps(report))
                    manifest['opportunity.json'] = hashlib.sha256((source/'opportunity.json').read_bytes()).hexdigest()
                (source/'checksums.json').write_text(json.dumps(manifest))
                with patch.object(portfolio_site, 'ROOT', root), self.assertRaises(ValueError):
                    portfolio_site.build(root/'site')

    def test_pages_permission_failure_is_pending_not_published(self):
        calls = []
        def denied(method, *args):
            calls.append(method)
            return (404, {}) if method == 'GET' else (403, {})
        result = pages_gate('owner/repo', 'test-only', request=denied)
        self.assertFalse(result['ready'])
        self.assertEqual(result['status'], 403)
        self.assertEqual(calls, ['GET', 'POST'])
        self.assertNotIn('url', result)

    def test_existing_pages_and_authorized_creation(self):
        ready = pages_gate('owner/repo', 'test-only', request=lambda *args: (200, {'build_type': 'workflow'}))
        self.assertTrue(ready['ready'])
        calls = []
        def created(method, *args):
            calls.append(method)
            return (404, {}) if method == 'GET' else (201, {'build_type': 'workflow'})
        self.assertTrue(pages_gate('owner/repo', 'test-only', request=created)['ready'])
        self.assertEqual(calls, ['GET', 'POST'])
        with self.assertRaises(ValueError):
            pages_gate('../elsewhere', 'test-only', request=created)

    def test_container_dependency_matches_frozen_wheel(self):
        lock = tomllib.loads((ROOT/'uv.lock').read_text())
        package = next(p for p in lock['package'] if p['name'] == 'websocket-client')
        requirements = (ROOT/'deploy/continuous-capture/requirements.txt').read_text()
        self.assertIn('websocket-client=='+package['version'], requirements)
        self.assertTrue(any(w['hash'] in requirements for w in package['wheels']))


if __name__ == '__main__':
    unittest.main()
