"""Bridge between the website and the Milestone 2 simulator.

simulate(cfg) runs one scenario with the unmodified simulator and returns everything the page needs to
replay it: packets (backbone hops and direct copies), ledger events, the seven-column trace, account
states after every event, completion times and the communication / capital metrics.  The same file runs
in CPython (to pre-build the canonical replays) and in Pyodide (for custom scenarios in the browser)."""
import json, math
from collections import defaultdict

from geom import _EL, HOUR, DAY, YEAR, SETTLEMENTS, NODES, SHORT, direct_flight, best_route
from protocol import OPENING_BOOK, REGISTRY, CASH, account_state, World
from transport import Incident
from scenarios import run, equity, futures, repeat_trading, metrics, PATHS
import traces

ACCOUNTS = [a for a, *_ in OPENING_BOOK]
SELLER = {'ARES': 'Bob', 'BELT': 'Cara', 'TERRA': 'Fin'}


def clean(x):
    """NaN / inf -> None so the browser's JSON.parse accepts the result."""
    if isinstance(x, float):
        return x if x == x and abs(x) != float('inf') else None
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


def elements():
    """Orbital elements for the browser-side propagator (same equations as geom.pos)."""
    return {k: dict(a=v['a'], b=v['b'], e=v['e'], M0=v['M0'], n=v['n'], P=list(v['P']), Q=list(v['Q']))
            for k, v in _EL.items()}


def book_for(cfg):
    homes = cfg.get('homes') or {}
    cash = cfg.get('cash') or {}
    return [(a, homes.get(a, h), int(cash.get(a, c)), dict(s)) for a, h, c, s in OPENING_BOOK]


def build_spec(cfg, book):
    home = {a: h for a, h, *_ in book}
    spec, kinds, errs = [], [], []
    for i, t in enumerate(cfg.get('trades', [])):
        tag = t.get('tag') or f'T{i + 1}'
        if t['type'] == 'equity':
            asset = t.get('asset', 'ARES')
            seller = SELLER[asset]
            buyer = t.get('buyer', 'Alice')
            if home[seller] != REGISTRY[asset]:
                errs.append(f'{seller} holds the {asset.title()} inventory and must stay at {REGISTRY[asset]}')
                continue
            if buyer == seller:
                errs.append('buyer and seller must differ')
                continue
            spec.append((equity, dict(tag=tag, buyer=buyer, seller=seller, asset=asset, qty=int(t.get('qty', 1000)),
                                      price=int(t.get('price', 100)), start=float(t.get('start_h', 0)) * HOUR)))
            kinds.append(('equity', tag, dict(buyer=buyer, seller=seller, asset=asset)))
        elif t['type'] == 'futures':
            if t.get('long', 'Alice') == t.get('short', 'Cara'):
                errs.append('long and short must differ')
                continue
            spec.append((futures, dict(tag=tag, Q=int(t.get('Q', 2000)), path=t.get('path', 'rising'),
                                       long=t.get('long', 'Alice'), short=t.get('short', 'Cara'),
                                       start=float(t.get('start_h', 0)) * HOUR)))
            kinds.append(('futures', tag, dict(long=t.get('long', 'Alice'), short=t.get('short', 'Cara'))))
        elif t['type'] == 'repeat':
            spec.append((repeat_trading, dict(tag=tag)))
            kinds.append(('repeat', tag, {}))
    return spec, kinds, errs


def completion(kind, tag, times):
    if kind == 'equity':
        a, b = times.get(f'{tag}:buyer_spendable'), times.get(f'{tag}:seller_spendable')
        return max(a, b) if a is not None and b is not None else None
    if kind == 'futures':
        xs = [v for k, v in times.items() if k.startswith(tag + ':') and k.endswith('payout_spendable')]
        return max(xs) if len(xs) == 2 else None
    if kind == 'repeat':
        xs = [v for k, v in times.items() if k.startswith(tag + ':') and 'sweep' in k]
        return max(xs) if len(xs) == 2 else None


def _world_kw(cfg):
    t0 = float(cfg.get('t0_h', 0.0)) * HOUR + float(cfg.get('epoch_years', 0.0)) * YEAR
    inc = [Incident(x['kind'], x['node'], t0 + float(x['start_h']) * HOUR,
                    float(x['duration_h']) * HOUR if x.get('duration_h') not in (None, '') else None)
           for x in cfg.get('incidents', [])]
    pol = dict(cfg.get('policy') or {})
    return t0, inc, pol


def _fmt_state(st, who, assets):
    out = {}
    for p in who:
        d = {}
        for a in (CASH,) + tuple(assets):
            s = st[a][p]
            d[a] = [s['home'], s['remote'], s['held'], s.get('escrow', 0), s['transit']]
        out[p] = d
    return out


def simulate(cfg):
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    book = book_for(cfg)
    spec, kinds, errs = build_spec(cfg, book)
    if errs or not spec:
        return dict(ok=False, error='; '.join(errs) or 'add at least one trade')
    t0, inc, pol = _world_kw(cfg)
    until = float(cfg.get('until_h', 700))
    assets = sorted({x[2]['asset'] for x in kinds if 'asset' in x[2]} |
                    ({'ARES'} if any(k == 'repeat' for k, *_ in kinds) else set()))
    who = ACCOUNTS
    w, tr, snaps = traces.run_traced(spec, who, tuple(assets), seed=int(cfg.get('seed', 0)),
                                     loss=bool(cfg.get('loss', False)), maintenance=bool(cfg.get('maintenance', True)),
                                     incidents=inc, t0=t0, until_h=until, policy=pol, book=book)
    m = metrics(w, tr)
    times = m['times']
    comps = {tag: completion(k, tag, times) for k, tag, _ in kinds}
    done = None if any(v is None for v in comps.values()) else max(comps.values())

    H = HOUR
    # ---- packets: backbone launches, labelled by the record they carry
    rid_label = {}
    for L in w.ledgers.values():
        for x in L.exports.values():
            amt = f"${x['amount']:,}" if x['asset'] == CASH else f"{x['amount']:,} {x['asset'].title()}"
            rid_label[x.get('rid')] = f"TRANSFER {x['eid']} {amt} ({x['purpose'].lower().replace('_', ' ')})"
    for e in w.events:
        if e['kind'] == 'RECEIVED_QUEUED':
            rid_label[e['rid']] = f"RECEIVED for {e['eid']}"
        elif e['kind'] == 'STATUS_QUEUED':
            rid_label[e['rid']] = f"STATUS ({e['entries']} client {'entry' if e['entries'] == 1 else 'entries'})"
    seq_rid = {}
    for rid, lst in w.courier.rec_pkt.items():
        for sid, seq in lst:
            seq_rid[(sid, seq)] = rid
    pk = []
    for r in w.net.launches:
        te, ta, a, b, kind = r[0], r[1], r[2], r[3], r[4]
        lg = r[12]
        lab = kind
        if kind == 'DATA' and lg:
            lab = rid_label.get(seq_rid.get((lg[2], lg[3])), 'DATA')
        pk.append([round((te - t0) / H, 5), round((ta - t0) / H, 5), a, b, kind, 1 if r[10] else (2 if r[11] else 0), lab])
    dl = [[round((r['te'] - t0) / H, 5), round((r['te'] - t0) / H + (direct_flight(r['a'], r['b'], r['te'])['arrive'] - r['te']) / H, 5),
           r['a'], r['b'], r['label'], 1 if r['lost'] else (2 if r['killed'] else 0), r['principal']]
          for r in w.direct_log]
    # ---- ledger events and account states
    ev = []
    for e, st in zip(w.events, snaps):
        d = {k: v for k, v in e.items() if k not in ('t', 'actor', 'kind', 'msg') and isinstance(v, (int, float, str, bool, type(None)))}
        if 'msg' in e:
            d['msg'] = {k: v for k, v in e['msg'].items() if isinstance(v, (int, float, str, bool))}
        ev.append([round((e['t'] - t0) / H, 5), e['actor'], e['kind'], d, _fmt_state(st, who, assets)])
    rows = traces.rows_for(w, tr, snaps, who, assets, skip=('RECEIPT_KNOWN',))
    courier = [[round((e[0] - t0) / H, 4), e[1], e[2], str(e[3])] for e in w.courier.events]
    quota = sorted([round((t - t0) / H, 4), inst] for t, inst, _ in w.quota.log)
    last = max([p[1] for p in pk] + [p[1] for p in dl] + [e[0] for e in ev] + [done or 0])
    return dict(
        ok=True, t0_h=t0 / H, until_h=until, horizon_h=min(until, last + 2.0), completion=done, per_trade=comps,
        times=times, kinds=[[k, t, d] for k, t, d in kinds], assets=assets, accounts=who,
        homes={a: h for a, h, *_ in book},
        packets=pk, direct=dl, events=ev, trace=rows, courier=courier, quota=quota,
        metrics=dict(backbone=m['backbone_total'], direct=m['direct'], direct_lost=m['direct_lost'],
                     total=m['total_packets'], originations=m['originations_total'], quota_peak=m['quota_peak_all'],
                     quota_by_exchange=m['quota_peak_inst'], direct_peak=m['direct_peak'], max_queue=m['max_queue'],
                     audits=m['audits'], matched_value=m['matched_value'], hop_abandoned=m['hop_abandoned'],
                     peak=m['peak'], capital=m['capital'],
                     lost_backbone=sum(1 for p in pk if p[5] == 1), killed=sum(1 for p in pk if p[5] == 2)))


def monte_carlo(cfg, n=50, first_seed=1):
    """Lossy repeats of one configuration (no logs): completion distribution and packet counts."""
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    book = book_for(cfg)
    spec, kinds, errs = build_spec(cfg, book)
    if errs or not spec:
        return dict(ok=False, error='; '.join(errs))
    t0, inc, pol = _world_kw(cfg)
    out = []
    for s in range(first_seed, first_seed + n):
        w, tr = run(spec, seed=s, loss=True, maintenance=bool(cfg.get('maintenance', True)), incidents=inc, t0=t0,
                    until_h=float(cfg.get('until_h', 700)) + 400, policy=pol, book=book, log_launches=False, audit=False)
        m = metrics(w, tr)
        cs = [completion(k, tag, m['times']) for k, tag, _ in kinds]
        out.append([None if any(c is None for c in cs) else max(cs), m['total_packets']])
    return dict(ok=True, runs=out)


def access(t_h=0.0, epoch_years=0.0):
    """S3-style access table at one moment: backbone best route and direct path from every settlement to
    every market host."""
    t = epoch_years * YEAR + t_h * HOUR
    rows = []
    for s in SETTLEMENTS:
        for host in ('Mars', 'Ceres', 'Earth'):
            if s == host:
                continue
            br = best_route(s, host, t, None, require_open=True)
            d = direct_flight(s, host, t)
            rows.append(dict(a=s, b=host, route='-'.join(SHORT[n] for n in br['path']) if br else None,
                             delay=br['delay'] / 60 if br else None, direct=(d['arrive'] - t) / 60,
                             p_loss=d['p_loss'], open=bool(d['open'])))
    return rows


if __name__ == '__main__':
    import time
    t = time.time()
    r = simulate(dict(trades=[dict(type='futures')]))
    print(time.time() - t, r['completion'], len(r['packets']), len(r['events']), len(json.dumps(r)) / 1e3, 'kB')
