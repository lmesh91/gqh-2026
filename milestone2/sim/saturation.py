"""Synthetic ledger-capacity tests (not compliant network scenarios): does every accepted obligation still get its
transfer out when one host's export slots are full?

These tests bypass the network's client limits on purpose.  They use thousands of synthetic client identities instead
of the six opening accounts, inject instructions at the ledger without direct-packet quotas (12 per client per day)
or R7 retries, and place clients' cash at Mars directly instead of funding it.  Backbone transport, quotas and the
transfer window are real.  They test the admission and reservation rules only.

The Mars ledger is driven at the real limits (4,096 export slots, admission stops at 3,276).  Within the first two
hours remote clients (homes at the other eight settlements) send it, in this order:
  * 1,000 capped-futures contracts between two remote clients (2,000 instructions; maturity 48 h, no observations,
    so each side gets its margin back as a payout home),
  * 250 home-delivery buy orders, 32 at most per client and 256 resting at the host, filled 3 shares at a time by a
    local seller every 30 minutes (so deliveries of partial fills chain behind each other),
  * 3,000 withdrawal requests of $10.
It then runs until every transfer is resolved.  With the reservation rule (design v3) the contracts and orders reserve
their slots at acceptance; with the earlier rule (admission counts unresolved exports only) they do not.  Clients'
cash at Mars is placed directly, so ledger audits are off; the run checks capacity, not conservation.
Writes results/saturation.json.

    python saturation.py
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from geom import HOUR, DAY, SETTLEMENTS
import protocol
from protocol import World, Ledger, CASH, UNRESOLVED_CAP, ADMIT_LIMIT

OUT = Path(__file__).resolve().parents[1] / 'results'
H = HOUR
HOMES = [s for s in SETTLEMENTS if s != 'Mars']


def case(reserve, n_contracts=1000, n_orders=250, n_withdraw=3000, until_d=60):
    Ledger.RESERVE = reserve
    clients = [f'C{i}' for i in range(2 * n_contracts + n_orders + n_withdraw)]
    book = [(c, HOMES[i % len(HOMES)], 1_000, {}) for i, c in enumerate(clients)] + [('Seller', 'Mars', 0, {'ARES': 3000})]
    w = World(seed=0, loss=False, maintenance=False, book=book, audit=False, log_launches=False)
    M = w.ledgers['Mars']
    for c in clients:
        M.avail[c, CASH] += 10_000                 # funded earlier (placed directly; audits off)
    out = dict(refused=dict(CINSTR=0, ORDER=0, WITHDRAW=0), accepted=dict(CINSTR=0, ORDER=0, WITHDRAW=0))
    trace = []

    def send(p, msg, t):
        def go():
            r = M.instruction(p, msg, 'direct')
            k = msg['type']
            out['refused' if r is None else 'accepted'][k] += 1
            trace.append((w.now / H, M.n_unresolved(), M.n_res))
        w.net.at(t, go, rank=1)

    k = 0
    for i in range(n_contracts):
        lo_, sh = clients[k], clients[k + 1]
        k += 2
        T = dict(cid=f'K{i}', long=lo_, short=sh, Q=10, K=100, lo=60, hi=140, deadline=24 * H, duration=48 * H,
                 grace=0.0, n_obs=5, obs_every=9.6 * H, oracle='Seller', host='Mars', payout='AUTO')
        for p in (lo_, sh):
            send(p, dict(type='CINSTR', cid=T['cid'], terms=T), 1 + 0.5 * k)
    buyers = clients[k:k + n_orders]
    k += n_orders
    for i, b in enumerate(buyers):
        send(b, dict(type='ORDER', oid=f'B{i}', asset='ARES', side='BUY', qty=10, limit=100, tif='GTC',
                     expiry=20 * DAY, disp='AUTO'), 0.6 * H + i)
    for j in range(n_orders * 10 // 3 + 1):                  # local seller: 3 shares every 30 minutes
        w.net.at(H + j * 1800.0, lambda j=j: M.instruction('Seller', dict(
            type='ORDER', oid=f'S{j}', asset='ARES', side='SELL', qty=3, limit=100, tif='IOC', expiry=20 * DAY,
            disp='RETAIN'), 'local'), rank=1)
    for i, c in enumerate(clients[k:k + n_withdraw]):
        send(c, dict(type='WITHDRAW', req=f'W{i}', asset=CASH, amount=10), 1.2 * H + i * 0.5)

    peak = dict(unres=0, committed=0, over_h=0.0)

    def probe():
        peak['unres'] = max(peak['unres'], M.n_unresolved())
        peak['committed'] = max(peak['committed'], M.committed())
        peak['over_h'] += (M.n_unresolved() > UNRESOLVED_CAP) * 600.0 / H
        trace.append((w.now / H, M.n_unresolved(), M.n_res))
        if w.now < until_d * DAY:
            w.net.at(w.now + 600.0, probe, rank=5)
    w.net.at(0.0, probe, rank=5)
    w.run(until_d * DAY)

    ex = list(M.exports.values())
    pay = [x for x in ex if x['purpose'] == 'PAYOUT']
    dlv = [x for x in ex if x['purpose'] == 'AUTO_FILL']
    filled = sum(r['qty'] - r['remaining'] for r in M.orders.values() if r['side'] == 'BUY')
    fixed = sum(c['state'] == 'FIXED' for c in M.contracts.values())
    opened = sum(c['t_open'] is not None for c in M.contracts.values())
    res = dict(reserve=reserve, cap=UNRESOLVED_CAP, admit=ADMIT_LIMIT, **out,
               contracts_opened=opened, contracts_fixed=fixed, payouts=len(pay),
               payouts_resolved=sum(x['t_receipt'] is not None for x in pay),
               shares_filled=filled, shares_delivered=sum(x['amount'] for x in dlv),
               deliveries=len(dlv), pending_left=sum(r['pend'] for r in M.orders.values()),
               reserved_left=M.n_res, all_resolved=M.n_unresolved() == 0,
               last_receipt_h=max(x['t_receipt'] for x in ex if x['t_receipt']) / H,
               peak_unresolved=peak['unres'], peak_committed=max(peak['committed'], M.peak_committed),
               over_cap_h=peak['over_h'],
               series=[(round(t, 2), u, r) for t, u, r in trace[::max(1, len(trace) // 400)]])
    Ledger.RESERVE = True
    return res


def returns_case(n_fill=3276, per_home=300, until_d=120):
    """Late top-ups at the cap: Mars has 3,276 withdrawals in flight (the admission limit) when 2,400 funding
    transfers (300 from each of the other eight exchanges, so several sources, each within its window of 512) arrive
    for accounts already closed at Mars.  Every one must be returned, but only 820 slots are free."""
    Ledger.RESERVE = True
    fill = [f'W{i}' for i in range(n_fill)]
    late = [(f'L{h[:2]}{i}', h) for h in HOMES for i in range(per_home)]
    book = [(c, HOMES[i % len(HOMES)], 0, {}) for i, c in enumerate(fill)] + [(c, h, 1_000, {}) for c, h in late]
    w = World(seed=0, loss=False, maintenance=False, book=book, audit=False, log_launches=False)
    M = w.ledgers['Mars']
    for c in fill:
        M.avail[c, CASH] += 100
    for c, _ in late:
        M.closed.add(c)                            # closed at Mars before the top-up arrives
    peak = dict(committed=0, waiting=0, over=0)
    for i, c in enumerate(fill):
        w.net.at(0.5 * i, lambda c=c, i=i: M.instruction(c, dict(type='WITHDRAW', req=f'w{i}', asset=CASH, amount=100),
                                                          'direct'), rank=1)
    for i, (c, h) in enumerate(late):
        w.net.at(1800.0 + i, lambda c=c, h=h, i=i: w.ledgers[h].instruction(
            c, dict(type='FUND', req=f'f{i}', asset=CASH, amount=1_000, dst='Mars'), 'local'), rank=1)

    def probe():
        peak['committed'] = max(peak['committed'], M.committed())
        peak['waiting'] = max(peak['waiting'], len(M.ret_pending))
        peak['over'] += M.committed() > UNRESOLVED_CAP
        if w.now < until_d * DAY:
            w.net.at(w.now + 60.0, probe, rank=5)
    w.net.at(0.0, probe, rank=5)
    w.run(until_d * DAY)
    rets = [x for x in M.exports.values() if x['purpose'] == 'RETURN_LATE_TOPUP']
    back = {c: w.ledgers[h].avail[c, CASH] for c, h in late}
    res = dict(fill=n_fill, late=len(late), sources=len(HOMES),
               withdrawals_resolved=sum(x['purpose'] == 'WITHDRAW' and x['t_receipt'] is not None for x in M.exports.values()),
               returns=len(rets), returns_resolved=sum(x['t_receipt'] is not None for x in rets),
               returned_amount=sum(x['amount'] for x in rets), restricted_left=sum(M.restricted.values()),
               all_home=all(v == 1_000 for v in back.values()),
               peak_committed=max(peak['committed'], M.peak_committed), peak_waiting=max(peak['waiting'], M.peak_ret_waiting),
               samples_over_cap=peak['over'],
               last_return_h=max((x['t_receipt'] or 0) for x in rets) / H if rets else None)
    return res


def main():
    res = dict(new=case(True), old=case(False), returns=returns_case())
    print('returns', res['returns'])
    for k, v in res.items():
        print(k, {x: y for x, y in v.items() if x != 'series'})
    (OUT / 'saturation.json').write_text(json.dumps(res, indent=1, default=float))


if __name__ == '__main__':
    main()
