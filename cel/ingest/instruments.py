"""Verify public instrument metadata before converting OKX contracts to BTC."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from urllib.request import urlopen

OKX_INSTRUMENT_URL = 'https://www.okx.com/api/v5/public/instruments?instType=SWAP&instId=BTC-USDT-SWAP'


def contract_value_btc(payload: dict) -> float:
    if not isinstance(payload, dict) or str(payload.get('code')) != '0' or not isinstance(payload.get('data'), list) or len(payload['data']) != 1:
        raise ValueError('OKX instruments response must contain exactly one successful result')
    item = payload['data'][0]
    if not isinstance(item, dict):
        raise ValueError('invalid OKX instrument object')
    expected = {'instId': 'BTC-USDT-SWAP', 'instType': 'SWAP', 'ctType': 'linear',
                'ctValCcy': 'BTC', 'settleCcy': 'USDT', 'state': 'live'}
    if any(item.get(k) != v for k, v in expected.items()):
        raise ValueError('unsupported or non-live OKX instrument/currency specification')
    # Support standard linear contracts only. Do not guess how a nonstandard
    # additional multiplier interacts with ctVal, which is already per contract.
    try:
        multiplier = Decimal(str(item.get('ctMult') or '1'))
        value = Decimal(str(item['ctVal']))
    except (KeyError, InvalidOperation) as exc:
        raise ValueError('invalid OKX contract metadata') from exc
    if multiplier != 1 or not value.is_finite() or value <= 0:
        raise ValueError('nonstandard multiplier or invalid BTC contract value')
    result = float(value)
    if not 0 < result < float('inf'):
        raise ValueError('BTC contract value is not representable')
    return result


def fetch_instrument() -> tuple[dict, float]:
    # urllib uses the configured HTTPS proxy and default TLS verification.
    with urlopen(OKX_INSTRUMENT_URL, timeout=15) as response:
        payload = json.loads(response.read(1_000_001))
    return payload, contract_value_btc(payload)
