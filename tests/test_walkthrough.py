import ast
import base64
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WalkthroughTests(unittest.TestCase):
    def test_five_minute_fixture_and_embedded_code_match_committed_sources(self):
        notebook = json.loads((ROOT/'notebooks/01_thesis_walkthrough.ipynb').read_text())
        self.assertTrue(notebook['metadata']['synthetic'])
        self.assertEqual(notebook['metadata']['market_tapes_read'], 0)
        constants = {}
        for cell in notebook['cells']:
            if cell['cell_type'] != 'code':
                continue
            self.assertIsNotNone(cell['execution_count'])
            self.assertFalse(any(o.get('output_type') == 'error' for o in cell['outputs']))
            tree = ast.parse(''.join(cell['source']))
            for node in tree.body:
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            constants[target.id] = node.value.value
        for encoded, path, checksum in (('DATA_GZIP_BASE64', 'notebooks/data/synthetic_5min.csv', 'DATA_SHA256'),
                                         ('TOOL_GZIP_BASE64', 'research/trading_decision.py', 'TOOL_SHA256')):
            raw = gzip.decompress(base64.b64decode(constants[encoded]))
            self.assertEqual(raw, (ROOT/path).read_bytes())
            self.assertEqual(hashlib.sha256(raw).hexdigest(), constants[checksum])
        rows = list(csv.DictReader(io.StringIO((ROOT/'notebooks/data/synthetic_5min.csv').read_text())))
        self.assertEqual(len(rows), 6002)
        self.assertEqual(int(rows[-1]['local_ts'])-int(rows[0]['local_ts']), 300000)
        self.assertEqual({r['venue'] for r in rows}, {'binance', 'okx'})
        self.assertTrue(all(float(r['bid']) <= float(r['ask']) and r['quantity_unit'] == 'BTC' for r in rows))


if __name__ == '__main__':
    unittest.main()
