"""Scenario scripts for design v3.  Every client acts only on what it can know locally:
its own home ledger (1 s local access), reports that physically arrived, and published
geometry.  The harness may audit global state but never feeds it to a client.

Declared client policy (the same in every run):
  * Funding is a local instruction at home.  A remote order/contract instruction is sent only
    after the home exchange has recorded the destination's RECEIVED for that funding export
    (confirmed-funding policy: no extra packets, no early-order rejection).
  * A direct instruction is sent as k copies 60 s apart, k = smallest number giving >= 99 %
    one-burst success at current geometry (cap 6), inside the 12/day quota.
  * Equity buyer fallback: if the bought shares have not been imported at home by
    send + 2*(direct + backbone) + 24 h, resend the same order ID (idempotent at the host).
  * Contract fallback: if no status (HELD/OPEN) arrived by send + 2*direct + 3*backbone + 6 h, resend the
    same instruction burst; stop at the opening deadline.  After the deadline without an OPEN
    report, withdraw ALL_AVAILABLE cash home.
"""
import math
from collections import defaultdict
from geom import HOUR, DAY, direct_flight, best_route, route_T0
from protocol import World, CASH, REGISTRY, Incident, Rejected, direct_clear_window

PATHS = {'rising': [110, 120, 130, 135, 125], 'falling': [90, 80, 70, 65, 75], 'flat': [100] * 5}


class Tracker:
    """Collects completion moments from notifications (harness side, not client knowledge)."""

    def __init__(self, w):
        self.w = w
        self.m = {}

    def mark(self, key, t=None):
        if key not in self.m:
            self.m[key] = self.w.now if t is None else t

    def rel(self):
        return {k: (v - self.w.t0) / HOUR for k, v in self.m.items()}


def access_horizon(home, host, t):
    """How long the client's direct path must stay open for the planned sequence: funding
    round trip on the backbone (cold session: 3 one-way trips + receipt) plus the direct order and a
    12 h margin for one fallback burst."""
    rt = _route_delay(home, host, t) + _route_delay(host, home, t)
    return 2 * rt + direct_flight(home, host, t)['arrive'] - t + 12 * HOUR


def _route_delay(a, b, t):
    if a == b:
        return 0.0
    return best_route(a, b, t, None, require_open=False)['delay']


def look(w, tr, client, asset, tag):
    """R6: before ordering, the client reads its home exchange's board by local access (1 s, no quota): the listing
    tells it the stock is valid and where it trades; the snapshot gives best bid/ask, last trade and their age."""
    home = w.home[client]
    assert asset in REGISTRY, 'not a listed stock'
    q = w.ledgers[home].quote(asset)
    if q is None:
        w.event(client, 'CLIENT_QUOTE', asset=asset, seen=None, knowledge='no snapshot on the home board yet')
    else:
        w.event(client, 'CLIENT_QUOTE', asset=asset, bid=q['bid'], ask=q['ask'], last=q['last'],
                age_h=(w.now - q['t']) / HOUR, knowledge='home board, local access')
    tr.mark(f'{tag}:quote_seen')
    return q


def fallback_send(w, principal, a, b, msg, label, done, what):
    """R7 for a remote request whose result the client sees at home (an import): send it direct, and if the
    result has not arrived by 2 x (direct + route back) + slack, resend the same request (same IDs, so a copy that
    did arrive only returns its original result).  Requests are valid for 30 days, so resending stops then."""
    t_created = w.now

    def go():
        if done():
            return
        w.direct_send(principal, a, b, msg, label=label)
        dd = direct_flight(a, b, w.now)['arrive'] - w.now
        slack = 2 * (dd + _route_delay(b, a, w.now)) + w.policy.get('fallback_slack_h', 24) * HOUR
        if w.now + slack < t_created + 30 * DAY:
            w.net.at(w.now + slack, lambda: (not done()) and resend(), rank=3)

    def resend():
        w.event(principal, 'CLIENT_FALLBACK', what='resend ' + label, knowledge=what)
        go()
    go()


# ====================================================================== equity value move
def equity(w, tr, buyer='Alice', seller='Bob', asset='ARES', qty=1000, price=100, tag='EQ', fund=None,
           disp='AUTO', start=0.0):
    host = REGISTRY[asset]
    bh, sh = w.home[buyer], w.home[seller]
    t0 = w.t0 + start
    fund = qty * price if fund is None else fund
    oid = f'{tag}-buy'
    sell_oid = f'{tag}-sell'
    order = dict(type='ORDER', oid=oid, asset=asset, side='BUY', qty=qty, limit=price, tif='GTC',
                 expiry=None, disp=disp)
    got = defaultdict(int)

    # seller: inventory is at its home market; local GTC sell at t=0 (or via funding if remote)
    def seller_go():
        w.local(seller, host, dict(type='ORDER', oid=sell_oid, asset=asset, side='SELL', qty=qty, limit=price,
                                   tif='GTC', expiry=w.now + 30 * DAY, disp=disp))
    assert sh == host, 'scenario expects seller inventory at the market'
    w.net.at(t0, seller_go, rank=1)

    state = dict(sent=0, done=False)

    def send_order():
        if state['done']:
            return
        o = dict(order)
        if not state['sent']:
            look(w, tr, buyer, asset, tag)
        if o['expiry'] is None:
            order['expiry'] = o['expiry'] = w.now + 7 * DAY
        state['sent'] += 1
        tr.mark(f'{tag}:order_sent')
        if bh == host:
            w.local(buyer, host, o)
        else:
            w.direct_send(buyer, bh, host, o, label='ORDER')
            dd = direct_flight(bh, host, w.now)['arrive'] - w.now
            slack = 2 * (dd + _route_delay(host, bh, w.now)) + w.policy.get('fallback_slack_h', 24) * HOUR
            if w.now + slack < order['expiry']:          # stop once the order itself would have expired
                w.net.at(w.now + slack, lambda: (not state['done']) and resend(), rank=3)

    def resend():
        w.event(buyer, 'CLIENT_FALLBACK', what='resend order ' + oid, knowledge='shares not yet imported at home')
        send_order()

    if bh == host:
        w.net.at(t0 + 0.5, send_order, rank=1)       # local buyer at the market
    else:
        req = f'{tag}-fund'

        def fund_go():
            if w.policy.get('access_check', True):
                t_ok = direct_clear_window(bh, host, w.now, access_horizon(bh, host, w.now),
                                           relay=w.policy.get('agent_relay', False))
                if t_ok > w.now + 1.0:
                    w.event(buyer, 'CLIENT_DEFER_ACCESS', until=t_ok,
                            knowledge='published geometry: direct path to host closes before the planned sequence ends')
                    tr.mark(f'{tag}:deferred_for_access')
                    w.net.at(t_ok, lambda: (w.local(buyer, bh, dict(type='QUOTE', asset=asset)),
                                            w.local(buyer, bh, dict(type='FUND', req=req, asset=CASH, amount=fund,
                                                                     dst=host))), rank=1)
                    return
            w.local(buyer, bh, dict(type='QUOTE', asset=asset))      # R6: ask for a quote with the funding
            w.local(buyer, bh, dict(type='FUND', req=req, asset=CASH, amount=fund, dst=host))
        w.net.at(t0, fund_go, rank=1)

    def watch(what, where, obj):
        if what == 'received' and where == bh and obj['ref'] == f'{tag}-fund' and obj['owner'] == buyer:
            tr.mark(f'{tag}:funding_receipt_at_home')
            if not state['sent']:
                w.net.at(w.now + 1.0, send_order, rank=1)       # local access to learn it
        if what == 'import' and where == host and obj['ref'] == f'{tag}-fund':
            tr.mark(f'{tag}:funding_imported_at_host')
        if what == 'fill' and where == host and obj['buy']['oid'] == oid:
            tr.mark(f'{tag}:first_fill')
            got['filled'] += obj['qty']
            if got['filled'] == qty:
                tr.mark(f'{tag}:host_final_fill')
                if sh == host:
                    tr.mark(f'{tag}:seller_spendable')
                if bh == host:
                    tr.mark(f'{tag}:buyer_spendable')
                    state['done'] = True
        if what == 'import' and where == bh and obj['asset'] == asset and obj['owner'] == buyer:
            got['home'] += obj['amount']
            if got['home'] >= qty:
                tr.mark(f'{tag}:buyer_spendable')
                state['done'] = True
        if what == 'import' and where == sh and obj['asset'] == CASH and obj['owner'] == seller \
                and obj['purpose'] == 'AUTO_FILL':
            got['proceeds'] += obj['amount']
            if got['proceeds'] >= qty * price:
                tr.mark(f'{tag}:seller_spendable')
    w.watchers.append(watch)


# ====================================================================== capped futures
def futures(w, tr, Q=2000, path='rising', long='Alice', short='Cara', host='Mars', oracle='Bob', tag='F1',
            start=0.0, deadline_h=168, duration_h=300, grace_h=24, fund_extra=0):
    t0 = w.t0 + start
    terms = dict(cid=tag, long=long, short=short, Q=Q, K=100, lo=60, hi=140, deadline=t0 + deadline_h * HOUR,
                 duration=duration_h * HOUR, grace=grace_h * HOUR, n_obs=5, obs_every=60 * HOUR, oracle=oracle,
                 host=host, payout='AUTO')
    margin = Q * 40
    prices = PATHS[path]
    st = {p: dict(sent=0, known=None, funded=False) for p in (long, short)}

    def instr(p):
        return dict(type='CINSTR', cid=tag, terms=terms)

    def send_instr(p):
        s = st[p]
        if s['known'] in ('HELD', 'OPEN', 'OPENED', 'FIXED') or w.now >= terms['deadline']:
            return
        s['sent'] += 1
        ph = w.home[p]
        tr.mark(f'{tag}:{p}:instr_sent')
        if ph == host:
            w.local(p, host, instr(p))
            return
        w.direct_send(p, ph, host, instr(p), label='CINSTR')
        dd = direct_flight(ph, host, w.now)['arrive'] - w.now
        # the status comes back over the backbone (host -> home, possibly a cold session: 3 one-way trips)
        # capped at 12 h so that a distant client uses its whole daily quota of 12 copies; duplicates are harmless
        w.net.at(w.now + min(2 * dd + 3 * _route_delay(host, ph, w.now) + 6 * HOUR, 12 * HOUR), lambda: fallback(p), rank=3)

    def fallback(p):
        if st[p]['known'] in ('HELD', 'OPEN', 'OPENED', 'FIXED') or w.now >= terms['deadline']:
            return
        w.event(p, 'CLIENT_FALLBACK', what='resend contract instruction', knowledge='no HELD/OPEN report yet')
        send_instr(p)

    for p in (long, short):
        ph = w.home[p]
        if ph == host:
            w.net.at(t0, lambda p=p: send_instr(p), rank=1)
        else:
            req = f'{tag}-{p}-fund'

            def fund_go(p=p, ph=ph, req=req):
                msg = dict(type='FUND', req=req, asset=CASH, amount=margin + fund_extra, dst=host)
                if w.policy.get('access_check', True):
                    t_ok = direct_clear_window(ph, host, w.now, access_horizon(ph, host, w.now),
                                           relay=w.policy.get('agent_relay', False))
                    if t_ok > w.now + 1.0:
                        if t_ok + 12 * HOUR >= terms['deadline']:
                            w.event(p, 'CLIENT_SUSPENDED_ACCESS', until=t_ok,
                                    knowledge='published geometry: no long-enough direct window to host before the deadline')
                            tr.mark(f'{tag}:{p}:suspended_no_access')
                            return
                        w.event(p, 'CLIENT_DEFER_ACCESS', until=t_ok,
                                knowledge='published geometry: direct path to host closes before the planned sequence ends')
                        tr.mark(f'{tag}:{p}:deferred_for_access')
                        w.net.at(t_ok, lambda: w.local(p, ph, msg), rank=1)
                        return
                w.local(p, ph, msg)
            w.net.at(t0, fund_go, rank=1)

    def after_deadline(p):
        if st[p]['known'] in ('OPEN', 'OPENED', 'FIXED'):
            return
        ph = w.home[p]
        if not st[p]['funded']:
            return
        w.event(p, 'CLIENT_WITHDRAW_AFTER_DEADLINE', knowledge='no OPEN report by the opening deadline')
        m = dict(type='WITHDRAW', req=f'{tag}-{p}-wd', asset=CASH, amount='ALL')
        if ph == host:
            return
        fallback_send(w, p, ph, host, m, 'WITHDRAW', lambda: st[p].get('returned', False),
                      'margin not yet back at home')

    for p in (long, short):
        w.net.at(terms['deadline'] + 1 * HOUR, lambda p=p: after_deadline(p), rank=3)

    def watch(what, where, obj):
        if what == 'received':
            for p in (long, short):
                if where == w.home[p] and obj['ref'] == f'{tag}-{p}-fund':
                    st[p]['funded'] = True
                    tr.mark(f'{tag}:{p}:funding_receipt_at_home')
                    if not st[p]['sent']:
                        w.net.at(w.now + 1.0, lambda p=p: send_instr(p), rank=1)
        elif what == 'rejected' and obj['msg'].get('type') == 'FUND' and obj['msg'].get('req', '').startswith(tag):
            tr.mark(f"{tag}:{obj['owner']}:funding_rejected_at_home")
        elif what == 'report' and obj.get('cid') == tag:
            p = obj['owner']
            st[p]['known'] = obj['state']
            tr.mark(f"{tag}:{p}:report_{obj['state']}")
        elif what == 'contract_open' and obj['cid'] == tag:
            tr.mark(f'{tag}:open')
            tr.mark(f'{tag}:maturity', obj['t_maturity'])
            # the oracle (Bob, at Mars) learns the schedule by local access and publishes locally
            for k, P in enumerate(prices, start=1):
                w.net.at(obj['t_open'] + k * terms['obs_every'] - 1.0,
                         lambda k=k, P=P: w.local(oracle, host, dict(type='PRICE', cid=tag, k=k, price=P)), rank=1)
        elif what == 'contract_rejected' and obj['cid'] == tag:
            tr.mark(f'{tag}:rejected_at_deadline')
        elif what == 'contract_fixed' and obj['cid'] == tag:
            tr.mark(f'{tag}:discharge')
            tr.mark(f'{tag}:backed_claim')
            for p in (long, short):
                if w.home[p] == host:
                    tr.mark(f'{tag}:{p}:payout_spendable')
        elif what == 'import' and obj.get('purpose') == 'PAYOUT' and obj.get('ref') == tag:
            tr.mark(f"{tag}:{obj['owner']}:payout_spendable")
        elif what == 'import' and obj.get('purpose') == 'WITHDRAW' and obj.get('ref', '').startswith(tag):
            tr.mark(f"{tag}:{obj['owner']}:returned_home")
            if obj['owner'] in st:
                st[obj['owner']]['returned'] = True
    w.watchers.append(watch)
    return terms


# ====================================================================== repeat trading ($10k example)
def repeat_trading(w, tr, tag='RT'):
    """The worked $10k account: two holds, partial fill with price improvement, cancel/fill race,
    spending proceeds at Mars, retained inventory and a final sweep home."""
    E, M = 'Earth', 'Mars'
    exp = w.t0 + 20 * DAY
    w.net.at(w.t0, lambda: (w.local('Alice', E, dict(type='QUOTE', asset='ARES')),
                            w.local('Alice', E, dict(type='FUND', req=f'{tag}-fund', asset=CASH, amount=10_000, dst=M))))
    w.net.at(w.t0, lambda: w.local('Bob', M, dict(type='ORDER', oid=f'{tag}-s1', asset='ARES', side='SELL', qty=10,
                                                  limit=97, tif='GTC', expiry=exp, disp='RETAIN')))
    w.net.at(w.t0 + 0.2, lambda: w.local('Bob', M, dict(type='ORDER', oid=f'{tag}-s2', asset='ARES', side='SELL', qty=5,
                                                        limit=100, tif='GTC', expiry=exp, disp='RETAIN')))
    st = dict(phase=0)

    def cancel(oid, label):
        # R7: resend until the client's report shows the order is no longer resting (cancelled, filled, or the
        # cancel left a tombstone because the order never arrived)
        L = w.ledgers[M]
        fallback_send(w, 'Alice', E, M, dict(type='CANCEL', oid=oid), label,
                      lambda: ('Alice', oid) in L.tomb or L.orders.get(oid, {}).get('state') not in (None, 'OPEN', 'PARTIAL'),
                      'cancel result not yet reported')

    def orders():
        look(w, tr, 'Alice', 'ARES', tag)
        tr.mark(f'{tag}:orders_sent')
        pkt = dict(type='ORDER', oid=f'{tag}-o1', asset='ARES', side='BUY', qty=40, limit=100, tif='GTC',
                   expiry=w.now + 10 * DAY, disp='RETAIN')
        pkt2 = dict(pkt, oid=f'{tag}-o2')
        w.direct_send('Alice', E, M, dict(type='BATCH', items=[pkt, pkt2]), label='ORDER o1+o2')
        # 6 h later: cancel o2 (frees $4,000) and later sell 10 of the retained shares at 101
        w.net.at(w.now + 6 * HOUR, lambda: cancel(f'{tag}-o2', 'CANCEL o2'))
        w.net.at(w.now + 12 * HOUR, lambda: w.direct_send('Alice', E, M, dict(
            type='ORDER', oid=f'{tag}-o3', asset='ARES', side='SELL', qty=10, limit=101, tif='GTC',
            expiry=w.now + 10 * DAY, disp='RETAIN'), label='ORDER o3'))
        # race: Alice cancels o1 at +24 h, but Bob's local sell at +24.1 h arrives first at Mars
        w.net.at(w.now + 24 * HOUR, lambda: cancel(f'{tag}-o1', 'CANCEL o1'))
        # final sweep at +48 h: all available cash and shares home
        w.net.at(w.now + 48 * HOUR, lambda: fallback_send(w, 'Alice', E, M, dict(type='BATCH', items=[
            dict(type='WITHDRAW', req=f'{tag}-sweep-cash', asset=CASH, amount='ALL'),
            dict(type='WITHDRAW', req=f'{tag}-sweep-ares', asset='ARES', amount='ALL')]), 'WITHDRAW cash+ARES',
            lambda: st.get('all_home', False), 'sweep not yet imported at home'))
        t_c = w.now
        # Bob: buys Alice's 10 @101 locally with his proceeds, then a sell that races Alice's cancel
        w.net.at(t_c + 13 * HOUR, lambda: w.local('Bob', M, dict(type='ORDER', oid=f'{tag}-b1', asset='ARES', side='BUY',
                                                                 qty=10, limit=101, tif='IOC', expiry=exp,
                                                                 disp='RETAIN')))
        w.net.at(t_c + 24 * HOUR + 0.1 * HOUR, lambda: w.local('Bob', M, dict(
            type='ORDER', oid=f'{tag}-s3', asset='ARES', side='SELL', qty=5, limit=99, tif='IOC', expiry=exp,
            disp='RETAIN')))

    def watch(what, where, obj):
        if what == 'received' and where == E and obj['ref'] == f'{tag}-fund' and not st['phase']:
            st['phase'] = 1
            w.net.at(w.now + 1.0, orders)
        if what == 'import' and where == E and obj['owner'] == 'Alice' and obj['purpose'] == 'WITHDRAW':
            tr.mark(f"{tag}:sweep_{obj['asset']}_home")
            L = w.ledgers[M]
            left = sum(v for (o, _), v in L.avail.items() if o == 'Alice') + \
                sum(r['held'] for r in L.orders.values() if r['owner'] == 'Alice')
            moving = any(t['owner'] == 'Alice' for t in w.transit.values())
            if left == 0 and not moving:            # everything Alice had at Mars is spendable at home
                st['all_home'] = True
                tr.mark(f'{tag}:all_home')
    w.watchers.append(watch)


# ====================================================================== runner and metrics
def run(spec, seed=0, loss=False, maintenance=True, incidents=(), t0=0.0, until_h=700, policy=None, book=None,
        log_launches=True, audit=True):
    kw = {}
    if book is not None:
        kw['book'] = book
    w = World(seed=seed, loss=loss, maintenance=maintenance, incidents=incidents, t0=t0, policy=policy,
              log_launches=log_launches, audit=audit, **kw)
    tr = Tracker(w)
    for fn, args in spec:
        fn(w, tr, **args)
    w.run(until_h * HOUR)
    return w, tr


def metrics(w, tr):
    """Communications, quota, capital and completion summary for one run."""
    net = w.net
    bb = {k[7:]: v for k, v in net.stats.items() if k.startswith('launch_')}   # counted even when not logged
    direct = len(w.direct_log)
    lost_direct = sum(r['lost'] for r in w.direct_log)
    # rolling quota peaks
    per = defaultdict(list)
    for t, inst, what in w.quota.log:
        per[inst].append(t)
    def peak(ts):
        ts = sorted(ts)
        best, j = 0, 0
        for i, t in enumerate(ts):
            while ts[j] <= t - DAY:
                j += 1
            best = max(best, i - j + 1)
        return best
    q_peak = {k: peak(v) for k, v in per.items()}
    q_all = peak([t for t, _, _ in w.quota.log])
    dper = defaultdict(list)
    for r in w.direct_log:
        dper[r['principal']].append(r['t'])
    d_peak = {k: peak(v) for k, v in dper.items()}
    # capital: integrate piecewise-constant snapshots
    cap = defaultdict(lambda: defaultdict(float))
    peak_c = defaultdict(lambda: defaultdict(int))
    snaps = w.snap
    for (t, s), (t2, _) in zip(snaps, snaps[1:] + [(w.now, None)]):
        dt = (t2 - t) / HOUR
        for a, d in s.items():
            enc = d['order'] + d['instr'] + d['escrow'] + d['transit']
            cap[a]['encumbered_h'] += enc * dt
            cap[a]['escrow_h'] += d['escrow'] * dt
            cap[a]['remote_h'] += d['remote'] * dt
            peak_c[a]['encumbered'] = max(peak_c[a]['encumbered'], enc)
            peak_c[a]['escrow'] = max(peak_c[a]['escrow'], d['escrow'])
            peak_c[a]['remote'] = max(peak_c[a]['remote'], d['remote'])
            peak_c[a]['away'] = max(peak_c[a]['away'], d['remote'] + enc)
    maxq = max((L.max_q for L in net.links.values()), default=0)
    return dict(
        times=tr.rel(),
        backbone=dict(bb), backbone_total=sum(bb.values()), direct=direct, direct_lost=lost_direct,
        total_packets=sum(bb.values()) + direct, originations=dict(w.courier.originations),
        originations_total=len(w.quota.log), quota_peak_inst=q_peak, quota_peak_all=q_all, direct_peak=d_peak,
        max_queue=maxq, capital={a: dict(v) for a, v in cap.items()}, peak={a: dict(v) for a, v in peak_c.items()},
        audits=w.n_audits, matched_value=w.stats['matched_value'], hop_abandoned=net.stats['hop_abandoned'],
        net_stats=dict(net.stats), courier_events=len(w.courier.events))
