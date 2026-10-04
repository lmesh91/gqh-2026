"""E2 for every S1 run: every direct message, every backbone launch with its per-launch loss and per-hop
abandonment probability, and Monte Carlo completion for the runs that run_e2 does not cover (S1f to S1i).
Writes results/e2_full.json.

    python e2_full.py
"""
import json, math, sys, time
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from geom import HOUR, flight
from evidence import SCEN, OUT, _mc_one, completion
from scenarios import run
from transport import Courier
from hop_bound import hop_abandon

H = HOUR
KINDS = {}


def _hook():
    orig = Courier.send

    def send(self, rec, delay=0.0):
        b = rec.body if isinstance(rec.body, dict) else {}
        KINDS[rec.rid] = (rec.kind, b.get('eid') or b.get('purpose') or '')
        return orig(self, rec, delay)
    Courier.send = send


def direct_messages(w):
    groups, n_msg = defaultdict(list), defaultdict(int)
    for r in w.direct_log:
        k0 = (r['principal'], r['a'], r['b'], r['label'])
        if r['copy'] == 0:
            n_msg[k0] += 1
        groups[k0 + (n_msg[k0],)].append(r)
    out = []
    for k, v in groups.items():
        miss = math.prod(x['p_loss'] for x in v)
        out.append(dict(principal=k[0], a=k[1], b=k[2], label=k[3], copies=len(v), t_first_h=v[0]['t'] / H,
                        t_arrive_h=v[0]['ta'] / H, t_last_arrive_h=v[-1]['ta'] / H, p_each=v[0]['p_loss'],
                        p_each_max=max(x['p_loss'] for x in v), p_first=1 - v[0]['p_loss'], p_success=1 - miss,
                        p_all_lost=miss))
    return sorted(out, key=lambda x: x['t_first_h'])


def hops(w):
    """Every backbone launch except hop receipts.  A hop is confirmed when the data crosses and its hop receipt
    (launched on arrival, back over the same link) crosses; the sender gives up the hop after four unconfirmed
    launches.  p_abandon is exact for retries at the hop-timer times and p_abandon_bound an upper bound for retries
    delayed by up to 24 h each (hop_bound.py); p_abandon_frozen is the earlier approximation p_unconf^4."""
    seqmap = defaultdict(list)
    for rid, lst in w.courier.rec_pkt.items():
        for sid, seq in lst:
            seqmap[(sid, seq)].append(KINDS.get(rid, ('?', ''))[0])
    rows = []
    for te, ta, a, b, kind, pid, sid, k, d, p, lost, killed, logical in w.net.launches:
        if kind == 'RCPT':
            continue
        _, dr, _ = flight(b, a, ta)
        pr = 1 - math.exp(-0.02 * dr)
        un = 1 - (1 - p) * (1 - pr)
        carries = ''
        if kind == 'DATA' and logical:
            ks = seqmap.get((logical[2], logical[3]), [])
            carries = '+'.join(f'{n}×{x}' if n > 1 else x for x, n in sorted(
                {x: ks.count(x) for x in ks}.items()))
        hb = hop_abandon(a, b, te)
        rows.append(dict(t_h=te / H, a=a, b=b, kind=kind, carries=carries, session=sid, attempt=k, d=d, p_data=p,
                         p_receipt=pr, p_unconf=un, p_abandon=hb['exact'], p_abandon_bound=hb['bound'],
                         p_abandon_frozen=un ** 4, open_certified=hb['open_certified'], p_never=p ** 4))
    return rows


def main():
    _hook()
    res = dict(runs={})
    for key, sc in SCEN.items():
        w, _ = run(sc['spec'], until_h=sc['until'])
        hs = hops(w)
        res['runs'][key] = dict(title=sc['title'], direct=direct_messages(w), hops=hs,
                                p_all_first=math.prod(1 - x['p_unconf'] for x in hs),
                                p_any_abandon=1 - math.prod(1 - x['p_abandon'] for x in hs),
                                p_any_abandon_bound=1 - math.prod(1 - x['p_abandon_bound'] for x in hs),
                                all_open_certified=all(x['open_certified'] for x in hs))
        print(key, len(res['runs'][key]['direct']), len(hs), round(res['runs'][key]['p_all_first'], 4),
              f"{res['runs'][key]['p_any_abandon']:.1e}")
    with Pool(20) as pool:
        for key, end in (('S1f', None), ('S1g', 'F1:Alice:returned_home'), ('S1i', None)):
            t = time.time()
            sc = SCEN[key]
            rs = pool.map(_mc_one, [(key, s, None) for s in range(1, 2001)], chunksize=20)
            cs = np.array([(r['times'].get(end) if end else completion(sc['kind'], sc['tag'], r['times'])) or np.inf
                           for r in rs])
            fin = cs[np.isfinite(cs)]
            res['runs'][key]['mc'] = dict(
                n=len(cs), completed=int(len(fin)), end=end or 'completion', p50=float(np.median(fin)),
                p90=float(np.percentile(cs, 90)), p99=float(np.percentile(cs, 99)), max=float(cs.max()),
                mean_total=float(np.mean([r['bb'] + r['direct'] for r in rs])),
                max_quota_inst=int(max(r['qpeak'] for r in rs)), max_direct_peak=int(max(r['dpeak'] for r in rs)),
                resubmit_runs=int(sum(r['resubmits'] > 0 for r in rs)),
                fallback_runs=int(sum(r['fallbacks'] > 0 for r in rs)),
                p_open=float(np.mean([r['times'].get('F1:open') is not None for r in rs])))
            print(key, res['runs'][key]['mc'], f'{time.time() - t:.0f}s', flush=True)
    (OUT / 'e2_full.json').write_text(json.dumps(res, indent=1, default=float))


if __name__ == '__main__':
    main()
