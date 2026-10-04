"""Produce every number used in the paper and the evidence appendix (design v3).

    python evidence.py s1 e2 s3 e1 s2 e5      (any subset; results go to ../results/*.json)
"""
import json, math, sys, time, itertools
from collections import defaultdict
from pathlib import Path
from multiprocessing import Pool
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from geom import *
import geom
from protocol import OPENING_BOOK, World, CASH, REGISTRY, direct_flight as _df
from transport import Incident
from hop_bound import hop_abandon
from scenarios import equity, futures, repeat_trading, run, metrics, PATHS

OUT = Path(__file__).resolve().parents[1] / 'results'
OUT.mkdir(exist_ok=True)
H = HOUR


def save(name, obj):
    (OUT / f'{name}.json').write_text(json.dumps(obj, indent=1, default=float))


# ====================================================================== scenario catalogue
SCEN = {
    'S1a': dict(title='Earth-Mars equity: Alice buys 1,000 Ares from Bob', spec=[(equity, dict(tag='EQ'))],
                until=48, kind='equity', tag='EQ', value=100_000),
    'S1b': dict(title='Earth-Ceres equity: Alice buys 1,000 Belt from Cara',
                spec=[(equity, dict(tag='EQB', seller='Cara', asset='BELT'))], until=48, kind='equity', tag='EQB',
                value=100_000),
    'S1c': dict(title='Uranus-Earth equity: Eve buys 400 Terra from Fin',
                spec=[(equity, dict(tag='EQT', buyer='Eve', seller='Fin', asset='TERRA', qty=400))], until=96,
                kind='equity', tag='EQT', value=40_000),
    'S1d': dict(title='Capped futures, rising path (Q = 2,000)', spec=[(futures, dict(path='rising'))], until=700,
                kind='futures', tag='F1', value=200_000),
    'S1e': dict(title='Capped futures, falling path (Q = 2,000)', spec=[(futures, dict(path='falling'))], until=700,
                kind='futures', tag='F1', value=200_000),
    'S1f': dict(title='Boundary variant Q = 2,500 (rising)', spec=[(futures, dict(path='rising', Q=2500))],
                until=700, kind='futures', tag='F1', value=250_000),
    'S1g': dict(title='Binding variant Q = 2,501 (rejected)', spec=[(futures, dict(path='rising', Q=2501))],
                until=400, kind='futures', tag='F1', value=0),
    'S1h': dict(title='Binding variant Q = 4,000 (rejected)', spec=[(futures, dict(path='rising', Q=4000))],
                until=400, kind='futures', tag='F1', value=0),
    'S1i': dict(title='Repeat trading on a $10,000 Mars account', spec=[(repeat_trading, dict())], until=120,
                kind='repeat', tag='RT', value=None),
}


def completion(kind, tag, times):
    if kind == 'equity':
        a, b = times.get(f'{tag}:buyer_spendable'), times.get(f'{tag}:seller_spendable')
        return max(a, b) if a is not None and b is not None else None
    if kind == 'futures':
        xs = [v for k, v in times.items() if k.endswith('payout_spendable')]
        return max(xs) if len(xs) == 2 else None
    if kind == 'repeat':
        return times.get(f'{tag}:all_home')


def n_transactions(w, kind):
    """Completed transactions: client-requested transfers (funding, withdrawals) + trades + contracts.
    Automatic home deliveries and payouts are part of their trade/contract."""
    n = 0
    for L in w.ledgers.values():
        for t in L.exports.values():
            if t['purpose'] in ('FUND', 'WITHDRAW') and t['t_import'] is not None:
                n += 1
        for r in L.orders.values():
            n += len(r['fills']) if r['side'] == 'BUY' else 0
        for c in L.contracts.values():
            n += c['state'] == 'FIXED'
    return n


def trace_rows(w, limit=None):
    """One row per financially relevant step (brief Section 8 trace format)."""
    rows = []
    launches_by = defaultdict(list)
    for r in w.net.launches:
        te, ta, a, b, kind, pid, sid, k, d, p, lost, killed, logical = r
        launches_by[sid].append(r)
    keep = {'LOCAL_INSTRUCTION', 'EXPORT', 'IMPORT', 'RECEIPT_KNOWN', 'DIRECT_LAUNCH', 'ORDER_ADMITTED', 'FILL',
            'MARGIN_HELD', 'CONTRACT_OPEN', 'PRICE_OBSERVED', 'CONTRACT_FIXED', 'CANCELLED', 'EXPIRED',
            'MARGIN_RELEASED', 'CONTRACT_REJECTED', 'REJECTED', 'CLIENT_FALLBACK', 'CANCEL_TOO_LATE',
            'IOC_REMAINDER_RELEASED', 'CANCEL_TOMBSTONE', 'ENDPOINT_RESET', 'CLIENT_DEFER_ACCESS',
            'CLIENT_SUSPENDED_ACCESS', 'CLIENT_WITHDRAW_AFTER_DEADLINE', 'WITHDRAW_NOTHING'}
    for e in w.events:
        if e['kind'] in keep:
            rows.append({k: v for k, v in e.items() if k != 'msg'} | ({'msg': e['msg']} if 'msg' in e else {}))
    return rows[:limit] if limit else rows


def record_launches(w, rid):
    """All physical launches (hops, receipts excluded) that carried a given record."""
    out = []
    for sid, seq in w.courier.rec_pkt.get(rid, []):
        for r in w.net.launches:
            lg = r[12]
            if r[4] == 'DATA' and lg and lg[2] == sid and lg[3] == seq:
                out.append(dict(te=r[0] / H, ta=r[1] / H, a=r[2], b=r[3], d=r[8], p=r[9], lost=r[10]))
    return out


def run_s1():
    res = {}
    for key, sc in SCEN.items():
        w, tr = run(sc['spec'], until_h=sc['until'])
        m = metrics(w, tr)
        comp = completion(sc['kind'], sc['tag'], m['times'])
        ntx = n_transactions(w, sc['kind'])
        cash = m['peak']['ND']
        # Brief Section 7 definitions: every completed transfer (shares at the stated $100), every trade fill and every
        # settled price-dependent contract (notional = Q x 1 x opening price 100) is one transaction.
        tx = []
        for L in w.ledgers.values():
            for t in L.exports.values():
                if t['t_import'] is not None:
                    tx.append(['transfer', t['purpose'], t['amount'] * (1 if t['asset'] == CASH else 100)])
            for r in L.orders.values():
                if r['side'] == 'BUY':
                    tx += [['fill', r['asset'], q * px] for _, q, px, _ in r['fills']]
            for c in L.contracts.values():
                if c['state'] == 'FIXED':
                    tx.append(['contract', c['cid'], c['terms']['Q'] * 100])
        vs = sum(x[2] for x in tx)
        caps = {a: dict(peak_encumbered=m['peak'][a]['encumbered'], peak_escrow=m['peak'][a]['escrow'],
                        peak_remote=m['peak'][a]['remote'], enc_hours=m['capital'][a]['encumbered_h'],
                        escrow_hours=m['capital'][a]['escrow_h'], remote_hours=m['capital'][a]['remote_h'])
                for a in m['peak']}
        exports = []
        for L in w.ledgers.values():
            for t in L.exports.values():
                exports.append(dict(src=t['src'], dst=t['dst'], eid=t['eid'], owner=t['owner'], asset=t['asset'],
                                    amount=t['amount'], purpose=t['purpose'], t_export=t['t_export'] / H,
                                    t_import=t['t_import'] / H if t['t_import'] else None,
                                    t_receipt=t['t_receipt'] / H if t['t_receipt'] else None,
                                    launches=record_launches(w, t.get('rid'))))
        contracts = {}
        for L in w.ledgers.values():
            for c in L.contracts.values():
                contracts[c['cid']] = dict(state=c['state'], t_open=(c['t_open'] or 0) / H if c['t_open'] else None,
                                           fixing=c.get('fixing'), obs=c['obs'])
        res[key] = dict(title=sc['title'], completion_h=comp, times=m['times'], transactions=ntx,
                        backbone=m['backbone'], backbone_total=m['backbone_total'], direct=m['direct'],
                        total_packets=m['total_packets'], originations=m['originations'],
                        originations_total=m['originations_total'], quota_peak_inst=m['quota_peak_inst'],
                        quota_peak_all=m['quota_peak_all'], direct_peak=m['direct_peak'], max_queue=m['max_queue'],
                        capital=caps, audits=m['audits'], matched_value=m['matched_value'],
                        utilisation=cash['encumbered'] / 500_000, position_utilisation=cash['escrow'] / 500_000,
                        value_settled=sc['value'],
                        capital_efficiency=(cash['encumbered'] / sc['value']) if sc['value'] else None,
                        comm_efficiency=m['total_packets'] / ntx if ntx else None,
                        tx_list=tx, n_tx=len(tx), value_settled_brief=vs,
                        cap_eff_brief=(cash['encumbered'] / vs) if vs else None,
                        comm_eff_brief=(m['total_packets'] / len(tx)) if tx else None,
                        balances=[(s, o, {str(k): v for k, v in d.items()}) for s, o, d in w.balances()],
                        exports=exports, contracts=contracts, trace=trace_rows(w),
                        direct_log=[{k: (v / H if k in ('t', 'te', 'ta') else v) for k, v in r.items()}
                                    for r in w.direct_log],
                        courier_events=[list(e) for e in w.courier.events])
        print(key, comp, m['total_packets'], ntx, w.n_audits, flush=True)
    save('s1', res)
    return res


# ====================================================================== E2 Monte Carlo
def _mc_one(args):
    key, seed, extra = args
    sc = SCEN[key]
    kw = dict(extra or {})
    w, tr = run(sc['spec'], loss=True, seed=seed, until_h=kw.pop('until', 1500), log_launches=True, audit=False, **kw)
    m = metrics(w, tr)
    comp = completion(sc['kind'], sc['tag'], m['times'])
    return dict(comp=comp, times=m['times'], bb=m['backbone_total'], direct=m['direct'], dlost=m['direct_lost'],
                orig=m['originations_total'], qpeak=max(m['quota_peak_inst'].values() or [0]),
                dpeak=max(m['direct_peak'].values() or [0]), hop_ab=m['hop_abandoned'],
                resubmits=sum(1 for e in w.courier.events if e[2] == 'APP_RESUBMIT'),
                fallbacks=sum(1 for e in w.events if e['kind'] == 'CLIENT_FALLBACK'))


def mc(key, n, extra=None, pool=None):
    jobs = [(key, s, extra) for s in range(1, n + 1)]
    rs = pool.map(_mc_one, jobs, chunksize=20)
    comps = np.array([r['comp'] if r['comp'] is not None else np.inf for r in rs])
    fin = comps[np.isfinite(comps)]
    out = dict(n=n, completed=int(np.isfinite(comps).sum()),
               p50=float(np.percentile(fin, 50)) if len(fin) else None,
               p90=float(np.percentile(comps, 90)), p99=float(np.percentile(comps, 99)),
               max=float(comps.max()), mean_bb=float(np.mean([r['bb'] for r in rs])),
               mean_direct=float(np.mean([r['direct'] for r in rs])),
               mean_total=float(np.mean([r['bb'] + r['direct'] for r in rs])),
               max_quota_inst=int(max(r['qpeak'] for r in rs)), max_direct_peak=int(max(r['dpeak'] for r in rs)),
               hop_abandon_runs=int(sum(r['hop_ab'] > 0 for r in rs)),
               resubmit_runs=int(sum(r['resubmits'] > 0 for r in rs)),
               fallback_runs=int(sum(r['fallbacks'] > 0 for r in rs)),
               cdf=[[float(x), float((comps <= x).mean())] for x in np.unique(np.round(np.sort(fin), 2))[::max(1, len(fin) // 300)]],
               comps=[float(c) if np.isfinite(c) else None for c in comps])
    if SCEN[key]['kind'] == 'futures':
        opens = [r['times'].get('F1:open') for r in rs]
        out['p_open'] = float(np.mean([o is not None for o in opens]))
        out['open_p50'] = float(np.median([o for o in opens if o is not None]))
        out['open_p99'] = float(np.percentile([o if o is not None else 1e9 for o in opens], 99))
    return out


def probabilities_for(w_key):
    """Analytic per-launch and hop-abandonment probabilities on the routes a no-loss run used."""
    s1 = json.loads((OUT / 's1.json').read_text())[w_key]
    rows = []
    seen = set()
    for x in s1['exports']:
        for L in x['launches']:
            key = (L['a'], L['b'], round(L['te'], 2))
            if key in seen:
                continue
            seen.add(key)
            te = L['te'] * H
            ta, d, c = flight(L['a'], L['b'], te)
            tr_, dr, cr = flight(L['b'], L['a'], ta)          # hop receipt launched on arrival
            pf, pr = 1 - math.exp(-0.02 * d), 1 - math.exp(-0.02 * dr)
            un = 1 - (1 - pf) * (1 - pr)
            hb = hop_abandon(L['a'], L['b'], te)
            rows.append(dict(record=f"{x['purpose']} {x['asset']} {x['src']}->{x['dst']}", a=L['a'], b=L['b'],
                             te_h=L['te'], d=d, p_launch=pf, p_receipt=pr, p_unconfirmed=un,
                             p_abandon=hb['exact'], p_abandon_bound=hb['bound'], p_abandon_frozen=un ** 4,
                             open_certified=hb['open_certified'], p_never_crosses=pf ** 4))
    return rows


def run_e2(n=2000):
    res = {}
    with Pool(20) as pool:
        for key in ('S1a', 'S1b', 'S1c', 'S1d', 'S1e'):
            t = time.time()
            res[key] = mc(key, n, pool=pool)
            res[key]['analytic'] = probabilities_for(key)
            print(key, res[key]['p50'], res[key]['p99'], res[key]['completed'], f'{time.time() - t:.0f}s', flush=True)
    # direct-service probabilities for the instructions used
    s1 = json.loads((OUT / 's1.json').read_text())
    dprob = {}
    for key in ('S1a', 'S1b', 'S1c', 'S1d', 'S1e', 'S1i'):
        rows = s1[key]['direct_log']
        groups = defaultdict(list)
        n_msg = defaultdict(int)
        for r in rows:                          # copy 0 starts a new message; later copies belong to it
            k0 = (r['principal'], r['a'], r['b'], r['label'])
            if r['copy'] == 0:
                n_msg[k0] += 1
            groups[k0 + (n_msg[k0],)].append(r)
        dprob[key] = [dict(principal=k[0], a=k[1], b=k[2], label=k[3], copies=len(v),
                           p_first=1 - v[0]['p_loss'], t_last_arrive=v[-1]['ta'],
                           p_loss_each=[x['p_loss'] for x in v], d=[x['d'] for x in v],
                           p_all_lost=float(np.prod([x['p_loss'] for x in v])),
                           p_success=1 - float(np.prod([x['p_loss'] for x in v])), t_first=v[0]['t'],
                           t_arrive=v[0]['ta'])
                      for k, v in groups.items()]
    res['direct'] = dprob
    save('e2', res)


# ====================================================================== S3 access table + relocations
def availability(path, h, maint, step=60.0):
    """Fraction of the 24 h starting at h in which every link on the route can launch (sequential)."""
    ok = 0
    n = 0
    for k in range(int(DAY / step)):
        t = h + k * step
        r = route_eval(path, t, maint)
        ok += r['open']
        n += 1
    return ok / n


def direct_availability(a, b, h, step=60.0):
    ok = n = 0
    for k in range(int(DAY / step)):
        t = h + k * step
        ok += flight(a, b, t + 2.0)[2] >= EXCLUSION_AU
        n += 1
    return ok / n


def s3_row(args):
    x, hh = args
    t = hh * H
    maint = Maintenance(True)
    row = dict(settlement=x, hour=hh)
    for host in ('Mars', 'Ceres', 'Earth'):
        if x == host:
            row[host] = dict(route='local', delay=0.0, back=0.0, avail=1.0, back_avail=1.0)
            continue
        br = best_route(x, host, t, maint, require_open=False)
        bk = best_route(host, x, t, maint, require_open=False)
        row[host] = dict(route='-'.join(SHORT[n] for n in br['path']), delay=br['delay'] / 60,
                         back_route='-'.join(SHORT[n] for n in bk['path']), back=bk['delay'] / 60,
                         avail=availability(br['path'], t, maint), back_avail=availability(bk['path'], t, maint))
    if x != 'Mars':
        f = direct_flight(x, 'Mars', t)
        g = direct_flight('Mars', x, t)
        w = World()
        k = w.direct_copies(x, 'Mars', t)
        row['direct'] = dict(delay=(f['arrive'] - t) / 60, p_loss=f['p_loss'], copies=k, burst=1 - f['p_loss'] ** k,
                             avail=direct_availability(x, 'Mars', t), back_delay=(g['arrive'] - t) / 60,
                             back_p_loss=g['p_loss'])
    else:
        row['direct'] = dict(delay=1 / 60, p_loss=0.0, copies=0, burst=1.0, avail=1.0, back_delay=1 / 60,
                             back_p_loss=0.0)
    return row


def relocated_book(home):
    return [(a, home if a == 'Alice' else h, c, s) for a, h, c, s in OPENING_BOOK]


def _reloc_mc(args):
    home, seed = args
    w, tr = run([(equity, dict(tag='EQ'))], loss=True, seed=seed, until_h=2000, book=relocated_book(home),
                audit=False)
    m = metrics(w, tr)
    return completion('equity', 'EQ', m['times']), m['total_packets']


def run_s3(n=1000):
    with Pool(20) as pool:
        rows = pool.map(s3_row, [(x, hh) for hh in (0, 300) for x in SETTLEMENTS])
        reloc = {}
        for home in SETTLEMENTS:
            w, tr = run([(equity, dict(tag='EQ'))], until_h=900, book=relocated_book(home))
            m = metrics(w, tr)
            comp = completion('equity', 'EQ', m['times'])
            mcr = pool.map(_reloc_mc, [(home, s) for s in range(1, n + 1)], chunksize=20)
            cs = np.array([c if c is not None else np.inf for c, _ in mcr])
            reloc[home] = dict(completion_h=comp, times=m['times'], packets=m['total_packets'],
                               backbone=m['backbone_total'], direct=m['direct'],
                               trace=trace_rows(w) if home in ('Mars', 'Jupiter', 'Neptune') else None,
                               mc_p50=float(np.percentile(cs, 50)), mc_p90=float(np.percentile(cs, 90)),
                               mc_p99=float(np.percentile(cs, 99)),
                               p_by_24h=float((cs <= 24).mean()), p_by_72h=float((cs <= 72).mean()),
                               p_by_168h=float((cs <= 168).mean()),
                               mc_packets=float(np.mean([p for _, p in mcr])),
                               direct_log=[{k: (v / H if k in ('t', 'te', 'ta') else v) for k, v in r.items()}
                                           for r in w.direct_log])
            print(home, comp, reloc[home]['mc_p50'], reloc[home]['p_by_72h'], flush=True)
    save('s3', dict(table=rows, relocations=reloc))


# ====================================================================== E1 orbital evidence
def run_e1():
    out = dict(epoch=[], later=[], examples=[])
    for n in NODES:
        p = pos(n, 0.0)
        ref = EPOCH_CHECK[n]
        out['epoch'].append(dict(body=n, x=p[0], y=p[1], z=p[2], ref=ref,
                                 err=math.dist(p, ref)))
    for n in ('Earth', 'Mars', 'Ceres', 'Relay A', 'Relay B', 'Neptune'):
        for hh in (300, 24 * 365.25):
            p = pos(n, hh * H)
            out['later'].append(dict(body=n, hour=hh, x=p[0], y=p[1], z=p[2], r=math.hypot(*p)))

    # the brief's sanity checks: back at the start after one period, and radius within [a(1 - e), a(1 + e)]
    out['orbit_checks'] = []
    for n in NODES:
        el = geom._EL[n]
        T = 2 * math.pi / el['n']
        ts = np.linspace(0.0, T, 200001)
        r = np.linalg.norm(vpos(n, ts), axis=-1)
        out['orbit_checks'].append(dict(body=n, period_d=T / DAY, ret=math.dist(pos(n, 0.0), pos(n, T)),
                                        below=float(el['a'] * (1 - el['e']) - r.min()),
                                        above=float(r.max() - el['a'] * (1 + el['e']))))

    def frozen(a, b, te):
        return LIGHT_S_PER_AU * math.dist(pos(a, te), pos(b, te))
    # the S1a funding and share delivery at their actual first launches in the no-loss S1a run
    w, _ = run([(equity, dict(tag='EQ'))], until_h=48)
    t_fill = next(e['t'] for e in w.events if e['kind'] == 'FILL')
    data = [r for r in w.net.launches if r[4] == 'DATA']
    te_fund = next(r[0] for r in data if r[2] == 'Earth' and r[3] == 'Relay A')
    te_deliv = next(r[0] for r in data if r[2] == 'Mars' and r[3] == 'Relay A' and r[0] >= t_fill)
    out['s1a_launch_h'] = dict(funding=te_fund / H, delivery=te_deliv / H)
    for a, b, te in (('Earth', 'Relay A', te_fund), ('Relay A', 'Mars', None), ('Mars', 'Relay A', te_deliv),
                     ('Relay A', 'Earth', None), ('Earth', 'Mars', 2.0), ('Mars', 'Earth', 2.0),
                     ('Neptune', 'Relay A', 1.0), ('Relay A', 'Neptune', 1.0)):
        if te is None:
            te = out['examples'][-1]['ta'] + 2.0      # relay: 1 s processing + 1 s serialization
        ta, d, c = flight(a, b, te)
        fz = frozen(a, b, te)
        out['examples'].append(dict(a=a, b=b, te=te, ta=ta, flight=ta - te, frozen=fz, diff_ms=(ta - te - fz) * 1e3,
                                    d=d, clearance=c))
    # convergence: iterations of the fixed-point light-time solve
    p = pos('Earth', 1.0)
    ta = 1.0 + LIGHT_S_PER_AU * math.dist(pos('Relay A', 1.0), p)
    it = []
    for k in range(6):
        nt = 1.0 + LIGHT_S_PER_AU * math.dist(pos('Relay A', ta), p)
        it.append(nt - ta)
        ta = nt
    out['iterations_Earth_A'] = it
    # route T0 / R_e and R_h for the S1a routes
    out['timers'] = []
    for path, t in ((('Earth', 'Relay A', 'Mars'), 0.0), (('Mars', 'Relay A', 'Earth'), 1.6966 * H),
                    (('Ceres', 'Relay A', 'Mars'), 0.0), (('Neptune', 'Relay A', 'Mars'), 0.0)):
        T0 = route_T0(path, t)
        out['timers'].append(dict(path='-'.join(SHORT[n] for n in path), t=t / H, T0_min=T0 / 60,
                                  Re_h=(2 * T0 + DAY) / H,
                                  Rh_min=[(2 * flight(u, v, t + 1)[1] * LIGHT_S_PER_AU + H) / 60 for u, v in
                                          zip(path, path[1:])]))
    # float64 time resolution limit (eons)
    out['float64_ms_limit_years'] = (1e-3 / np.finfo(float).eps) / YEAR
    save('e1', out)


# ====================================================================== S2 incident search
BASE = None


def _s2_one(args):
    kind, node, start, path, extra = args
    inc = Incident(kind, node, start * H)
    kw = dict(extra or {})
    maint = kw.pop('maintenance', True)
    w, tr = run([(futures, dict(path=path))], incidents=[inc], until_h=1400, log_launches=False, audit=False,
                maintenance=maint, **kw)
    m = metrics(w, tr)
    tm = m['times']
    comp = completion('futures', 'F1', tm)
    opened = tm.get('F1:open')
    returned = max([v for k, v in tm.items() if k.endswith('returned_home')] or [None]) \
        if not opened else None
    return dict(kind=kind, node=node, start=start, opened=opened, comp=comp, returned=returned,
                fallbacks=sum(1 for e in w.events if e['kind'] == 'CLIENT_FALLBACK'),
                resubmits=sum(1 for e in w.courier.events if e[2] == 'APP_RESUBMIT'),
                packets=m['total_packets'])


def run_s2_search(path='rising'):
    jobs = []
    for node in SETTLEMENTS:
        for s in np.arange(0, 420, 1.0):
            jobs.append(('isolation', node, float(s), path, None))
    for node in SETTLEMENTS + RELAYS:
        for s in np.arange(0, 420, 0.5):
            jobs.append(('forced_loss', node, float(s), path, None))
    for node in SETTLEMENTS:
        for s in np.arange(0, 420, 0.25):
            jobs.append(('reset', node, float(s), path, None))
    t = time.time()
    with Pool(22) as pool:
        rs = pool.map(_s2_one, jobs, chunksize=50)
    print('search', len(rs), f'{time.time() - t:.0f}s', flush=True)
    base_w, base_tr = run([(futures, dict(path=path))], until_h=1400)
    base = completion('futures', 'F1', metrics(base_w, base_tr)['times'])
    for r in rs:
        r['damage'] = (1e6 if r['opened'] is None else 0) + ((r['comp'] or 1e5) - base)
    rs.sort(key=lambda r: -r['damage'])
    save(f's2_search_{path}', dict(base=base, n=len(rs), runs=rs))
    return rs


def run_s2_detail(kind, node, start, path_list=('rising', 'falling'), n=1000):
    out = {}
    inc = Incident(kind, node, start * H)
    for path in path_list:
        variants = {
            'baseline_no_incident': dict(incidents=[]),
            'incident': dict(incidents=[inc]),
            'incident_no_maintenance': dict(incidents=[inc], maintenance=False),
            'no_incident_no_maintenance': dict(incidents=[], maintenance=False),
        }
        for alt_name, pol in ALTERNATIVES.items():
            variants['incident_' + alt_name] = dict(incidents=[inc], policy=pol)
        for name, kw in variants.items():
            w, tr = run([(futures, dict(path=path))], until_h=1400, **kw)
            m = metrics(w, tr)
            out[f'{path}:{name}'] = dict(times=m['times'], completion=completion('futures', 'F1', m['times']),
                                         packets=m['total_packets'], backbone=m['backbone_total'],
                                         direct=m['direct'], originations=m['originations_total'],
                                         trace=trace_rows(w), courier_events=[list(e) for e in w.courier.events],
                                         balances=[(s, o, {str(k): v for k, v in d.items()}) for s, o, d in
                                                   w.balances()],
                                         capital={a: dict(v) for a, v in m['capital'].items()},
                                         peak={a: dict(v) for a, v in m['peak'].items()}, audits=m['audits'],
                                         launch_count=len(w.net.launches),
                                         lost_launches=sum(1 for r in w.net.launches if r[10]))
            print(path, name, out[f'{path}:{name}']['completion'], flush=True)
    # Monte Carlo with loss on top of the incident
    with Pool(20) as pool:
        for name, extra in (('incident', None), ('incident_' + list(ALTERNATIVES)[0], dict(policy=list(ALTERNATIVES.values())[0]))):
            jobs = [('S1d', s, dict(incidents=[inc], **(extra or {}))) for s in range(1, n + 1)]
            rs = pool.map(_mc_one, jobs, chunksize=20)
            cs = np.array([r['comp'] if r['comp'] is not None else np.inf for r in rs])
            out[f'mc:{name}'] = dict(n=n, p50=float(np.percentile(cs, 50)), p90=float(np.percentile(cs, 90)),
                                     p99=float(np.percentile(cs, 99)), completed=int(np.isfinite(cs).sum()),
                                     p_open=float(np.mean([r['times'].get('F1:open') is not None for r in rs])),
                                     mean_total=float(np.mean([r['bb'] + r['direct'] for r in rs])))
            print('mc', name, out[f'mc:{name}'], flush=True)
    save('s2_detail', dict(incident=dict(kind=kind, node=node, start=start), runs=out,
                           alternatives=list(ALTERNATIVES)))


# ====================================================================== E5 shifted epochs
def find_difficult(years=4):
    """First Mars solar conjunction after the epoch: the Earth->Mars direct path closes and the
    Earth-Mars backbone routes are at their longest.  The scenario starts 24 h after closure."""
    t = np.arange(0, years * YEAR, HOUR)
    clr = vflight('Earth', 'Mars', t)[2]
    i = int(np.flatnonzero(clr < EXCLUSION_AU)[0])
    lo, hi = t[i - 1], t[i]
    while hi - lo > 1.0:
        mid = 0.5 * (lo + hi)
        if flight('Earth', 'Mars', mid)[2] >= EXCLUSION_AU:
            lo = mid
        else:
            hi = mid
    j = i
    while clr[j] < EXCLUSION_AU:
        j += 1
    return dict(close_h=hi / H, reopen_h=t[j] / H, start_h=hi / H + 24.0)


def _e5_one(args):
    key, t0_h, seed, pol, until = args
    sc = SCEN[key]
    w, tr = run(sc['spec'], loss=seed > 0, seed=seed, t0=t0_h * H, maintenance=False, policy=pol,
                until_h=until, audit=(seed == 0), log_launches=(seed == 0))
    m = metrics(w, tr)
    return dict(comp=completion(sc['kind'], sc['tag'], m['times']), times=m['times'],
                packets=m['total_packets'], bb=m['backbone_total'], direct=m['direct'], audits=m['audits'],
                relays=sorted(set(e['via'] for e in w.events if e['kind'] == 'AGENT_RELAY')),
                deferred=sum(1 for e in w.events if 'DEFER' in e['kind']),
                suspended=sum(1 for e in w.events if 'SUSPEND' in e['kind']))


def run_e5(n=300):
    diff = find_difficult()
    NO_O2 = dict(agent_relay=False)       # the design without rule R9, for comparison
    epochs = []
    for name, t0h in (('+1 year', YEAR / H), ('+10 years', 10 * YEAR / H), ('+100 years', 100 * YEAR / H),
                      ('Mars conjunction', diff['start_h'])):
        epochs += [(name, t0h, None), (name + ', without O2', t0h, NO_O2)]
    res = dict(difficult=diff, rows={})
    with Pool(20) as pool:
        for name, t0h, pol in epochs:
            for key in ('S1a', 'S1b', 'S1c', 'S1d', 'S1e'):
                until = 1600 if 'conjunction' in name else SCEN[key]['until'] + 400
                det = _e5_one((key, t0h, 0, pol, until))
                rs = pool.map(_e5_one, [(key, t0h, s, pol, until) for s in range(1, n + 1)], chunksize=10)
                cs = np.array([r['comp'] if r['comp'] is not None else np.inf for r in rs])
                row = dict(epoch=name, t0_h=t0h, scenario=key, policy=pol, noloss=det,
                           mc=dict(n=n, completed=int(np.isfinite(cs).sum()),
                                   p50=float(np.percentile(cs, 50)), p99=float(np.percentile(cs, 99)),
                                   mean_total=float(np.mean([r['bb'] + r['direct'] for r in rs]))))
                res['rows'][f'{name}|{key}'] = row
                print(name, key, det['comp'], det['packets'], row['mc'], flush=True)
    save('e5', res)


ALTERNATIVES = {
    'restart_notice': dict(restart_notice=True),
    'immediate_recovery': dict(backoff=False),
}


if __name__ == '__main__':
    for arg in sys.argv[1:]:
        t = time.time()
        if arg == 's1':
            run_s1()
        elif arg == 'e2':
            run_e2()
        elif arg == 's3':
            run_s3()
        elif arg == 'e1':
            run_e1()
        elif arg == 'e5':
            run_e5()
        elif arg == 's2search':
            run_s2_search('rising')
            run_s2_search('falling')
        print(arg, 'done', f'{time.time() - t:.0f}s', flush=True)
