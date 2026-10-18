"""Offline order lifecycle, accounting and crash-recovery harness. No broker I/O."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path


def amount(value, *, positive=False):
    if isinstance(value, bool):
        raise ValueError('boolean is not an amount')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('invalid decimal amount') from exc
    if not result.is_finite() or result < 0 or positive and result == 0:
        raise ValueError('finite nonnegative amount required')
    return result


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


@dataclass
class Ledger:
    orders: dict = field(default_factory=dict)
    cash: dict = field(default_factory=dict)
    positions: dict = field(default_factory=dict)
    fees: dict = field(default_factory=dict)
    messages: dict = field(default_factory=dict)
    executions: dict = field(default_factory=dict)
    reconciled: bool = True

    @staticmethod
    def status(order):
        if order['filled'] == order['quantity']:
            return 'filled'
        if order['rejected']:
            return 'rejected'
        if order['canceled_at'] is not None:
            return 'canceled'
        if order['cancel_pending']:
            return 'cancel_pending'
        if order['filled']:
            return 'partially_filled'
        return 'acknowledged' if order['venue_order_id'] else 'submitted'

    def apply(self, event):
        candidate = deepcopy(self)
        changed = candidate._apply(event)
        self.__dict__.update(candidate.__dict__)
        return changed

    def _apply(self, event):
        identifier = event['message_id']
        if not isinstance(identifier, str) or not identifier:
            raise ValueError('message ID required')
        signature = encoded({k:v for k,v in event.items() if k != 'received_ms'})
        if identifier in self.messages:
            if self.messages[identifier] != signature:
                raise ValueError('conflicting message ID')
            return False
        kind = event['kind']
        if kind != 'reconcile' and (not isinstance(event.get('client_order_id'),str) or not event['client_order_id']):
            raise ValueError('client order ID required')
        if kind == 'reconcile':
            def balances(items):
                result = {key:Decimal(str(value)) for key,value in items.items()}
                if any(not v.is_finite() for v in result.values()):
                    raise ValueError('nonfinite reconciliation balance')
                return {k:v for k,v in result.items() if v != 0}
            expected_open = {key:str(order['quantity']-order['filled']) for key,order in self.orders.items()
                             if self.status(order) not in ('filled','rejected','canceled')}
            observed_open = {k:str(amount(v)) for k,v in event['open_orders'].items()}
            self.reconciled = (balances(event['positions']) == balances(self.positions)
                               and balances(event['cash']) == balances(self.cash)
                               and {k:Decimal(v) for k,v in observed_open.items()} ==
                               {k:Decimal(v) for k,v in expected_open.items()})
        elif kind == 'submit':
            if not self.reconciled:
                raise ValueError('reconcile before new orders')
            key = event['client_order_id']
            terms = {'venue':event['venue'], 'side':event['side'],
                     'quantity':amount(event['quantity'], positive=True),
                     'order_type':event.get('order_type','market')}
            if terms['venue'] not in ('binance','okx','bybit') or terms['side'] not in ('buy','sell'):
                raise ValueError('unsupported venue or side')
            instrument = 'BTC-USDT-SWAP' if terms['venue']=='okx' else 'BTCUSDT'
            terms['instrument'] = event.get('instrument',instrument)
            if terms['instrument'] != instrument or terms['order_type'] not in ('market','limit'):
                raise ValueError('unsupported instrument or order type')
            terms['limit_price'] = amount(event.get('limit_price'),positive=True) if terms['order_type']=='limit' else None
            if terms['order_type']=='market' and event.get('limit_price') is not None:
                raise ValueError('market order cannot carry a limit price')
            if key in self.orders:
                if any(self.orders[key][k] != v for k,v in terms.items()):
                    raise ValueError('conflicting client order ID')
            else:
                self.orders[key] = {**terms, 'filled':Decimal(0), 'venue_order_id':None,
                                    'rejected':False, 'cancel_pending':False, 'canceled_at':None,
                                    'last_execution_ms':None}
        elif kind in ('ack','fill','reject','cancel_request','cancel_ack'):
            key = event['client_order_id']
            if key not in self.orders:
                raise ValueError('unknown client order ID')
            order = self.orders[key]
            if kind == 'ack':
                venue_id = event['venue_order_id']
                if not isinstance(venue_id,str) or not venue_id:
                    raise ValueError('venue order ID required')
                if order['venue_order_id'] not in (None,venue_id):
                    raise ValueError('conflicting venue order ID')
                order['venue_order_id'] = venue_id
            elif kind == 'reject':
                if order['filled']:
                    raise ValueError('full-order rejection conflicts with fills')
                order['rejected'] = True
            elif kind == 'cancel_request':
                order['cancel_pending'] = True
            elif kind == 'cancel_ack':
                stamp = event['venue_cancel_ms']
                if type(stamp) is not int or stamp < 0:
                    raise ValueError('valid venue cancellation timestamp required')
                if order['last_execution_ms'] is not None and stamp < order['last_execution_ms']:
                    raise ValueError('cancellation predates a known fill')
                if order['canceled_at'] not in (None,stamp):
                    raise ValueError('conflicting cancellation timestamp')
                order['canceled_at'] = stamp
                order['cancel_pending'] = False
            else:
                quantity, price, fee = [amount(event[k], positive=k != 'fee_usdt')
                                        for k in ('quantity','price','fee_usdt')]
                stamp = event['venue_execution_ms']
                if type(stamp) is not int or stamp < 0 or event.get('fee_currency','USDT') != 'USDT':
                    raise ValueError('valid venue execution time and USDT fee required')
                if not isinstance(event['execution_id'],str) or not event['execution_id']:
                    raise ValueError('execution ID required')
                execution = (order['venue'],event['execution_id'])
                economics = (key,quantity,price,fee,stamp)
                if execution in self.executions:
                    if self.executions[execution] != economics:
                        raise ValueError('conflicting execution ID')
                else:
                    if order['limit_price'] is not None and (
                            order['side']=='buy' and price>order['limit_price'] or
                            order['side']=='sell' and price<order['limit_price']):
                        raise ValueError('fill violates limit price')
                    if (order['rejected'] or order['filled']+quantity > order['quantity'] or
                            order['canceled_at'] is not None and stamp > order['canceled_at']):
                        raise ValueError('fill conflicts with order lifecycle')
                    order['filled'] += quantity
                    order['last_execution_ms'] = max(stamp,order['last_execution_ms'] or 0)
                    sign = Decimal(1) if order['side']=='buy' else Decimal(-1)
                    venue = order['venue']
                    self.positions[venue] = self.positions.get(venue,Decimal(0))+sign*quantity
                    self.cash[venue] = self.cash.get(venue,Decimal(0))-sign*quantity*price-fee
                    self.fees[venue] = self.fees.get(venue,Decimal(0))+fee
                    self.executions[execution] = economics
        else:
            raise ValueError('unknown lifecycle event')
        self.messages[identifier] = signature
        return True

    def snapshot(self):
        return {'orders':{key:{'status':self.status(order), 'venue':order['venue'], 'side':order['side'],
                               'quantity':str(order['quantity']), 'filled':str(order['filled']),
                               'instrument':order['instrument'],'order_type':order['order_type'],
                               'limit_price':str(order['limit_price']) if order['limit_price'] is not None else None,
                               'remaining':str(order['quantity']-order['filled']),
                               'venue_order_id':order['venue_order_id']} for key,order in sorted(self.orders.items())},
                'positions_btc':{k:str(v) for k,v in sorted(self.positions.items())},
                'cash_usdt':{k:str(v) for k,v in sorted(self.cash.items())},
                'fees_usdt':{k:str(v) for k,v in sorted(self.fees.items())},
                'net_btc':str(sum(self.positions.values(),Decimal(0))),
                'gross_btc':str(sum((abs(v) for v in self.positions.values()),Decimal(0))),
                'reconciled':self.reconciled, 'unique_executions':len(self.executions)}


class Journal:
    """Single-writer append/fsync journal. Truncated tails fail closed; never repair silently."""
    def __init__(self, path):
        self.path = path
        self.ledger = Ledger()
        self.sequence = 0
        self.previous = '0'*64
        if path.exists():
            raw = path.read_bytes()
            if raw and not raw.endswith(b'\n'):
                raise ValueError('truncated journal tail; retain evidence and reconcile')
            for line in raw.splitlines():
                record = json.loads(line)
                digest = record.pop('sha256')
                if (record['sequence'] != self.sequence+1 or record['previous_sha256'] != self.previous
                        or hashlib.sha256(encoded(record).encode()).hexdigest() != digest):
                    raise ValueError('journal sequence or digest mismatch')
                self.ledger.apply(record['event'])
                self.sequence, self.previous = record['sequence'], digest
            self.ledger.reconciled = False

    def append(self, event):
        candidate = deepcopy(self.ledger)
        candidate.apply(event)
        body = {'sequence':self.sequence+1, 'previous_sha256':self.previous, 'event':event}
        digest = hashlib.sha256(encoded(body).encode()).hexdigest()
        with self.path.open('a',encoding='utf-8') as target:
            target.write(encoded({**body,'sha256':digest})+'\n')
            target.flush()
            os.fsync(target.fileno())
        self.ledger, self.sequence, self.previous = candidate, body['sequence'], digest


def scenario_events():
    return [
        {'message_id':'s1','kind':'submit','client_order_id':'entry','venue':'okx','side':'buy','quantity':'.001'},
        {'message_id':'a1','kind':'ack','client_order_id':'entry','venue_order_id':'venue-1'},
        {'message_id':'f1','kind':'fill','client_order_id':'entry','execution_id':'exec-1',
         'quantity':'.0004','price':'60000','fee_usdt':'.012','venue_execution_ms':100},
        {'message_id':'c1','kind':'cancel_request','client_order_id':'entry'},
        {'message_id':'c2','kind':'cancel_ack','client_order_id':'entry','venue_cancel_ms':200},
        {'message_id':'f2','kind':'fill','client_order_id':'entry','execution_id':'exec-2',
         'quantity':'.0002','price':'60001','fee_usdt':'.0060001','venue_execution_ms':190},
        {'message_id':'retry-fill','kind':'fill','client_order_id':'entry','execution_id':'exec-2',
         'quantity':'.0002','price':'60001','fee_usdt':'.0060001','venue_execution_ms':190}]


def demo(out):
    out.mkdir(parents=True,exist_ok=False)
    journal = Journal(out/'events.jsonl')
    for event in scenario_events():
        journal.append(event)
    before = journal.ledger.snapshot()
    restarted = Journal(out/'events.jsonl')
    after = restarted.ledger.snapshot()
    restarted.append({'message_id':'reconcile','kind':'reconcile','positions':before['positions_btc'],
                      'cash':before['cash_usdt'],'open_orders':{}})
    result = {'synthetic':True,'before_restart':before,'after_restart_before_reconcile':after,
              'after_reconcile':restarted.ledger.snapshot(),
              'scope':'Offline lifecycle/accounting harness only. No transport, orders, accounts or fill probabilities.'}
    (out/'lifecycle.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo',action='store_true',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    demo(args.out)
    print('Offline partial-fill/cancel-race/restart scenario reconciled; no orders sent')


if __name__=='__main__':
    main()
