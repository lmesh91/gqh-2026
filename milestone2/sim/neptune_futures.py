"""Service-table check: an outer-planet client in the Mars futures (Dax at Neptune long, Cara short),
and the same for Eve at Uranus.  300 lossy runs each; writes ../results/outer_futures.json."""
import json, sys
from pathlib import Path
from multiprocessing import Pool
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from scenarios import run, futures, metrics
from evidence import OUT


def one(args):
    long, seed, pol = args
    w, tr = run([(futures, dict(path='rising', long=long, Q=1250 if long == 'Eve' else 2000))], loss=seed > 0,
                seed=seed, until_h=900, log_launches=False, audit=seed == 0, policy=pol)
    t = tr.rel()
    pay = [v for k, v in t.items() if k.endswith('payout_spendable')]
    return dict(open=t.get('F1:open'), comp=max(pay) if len(pay) == 2 else None,
                returned=[k for k in t if k.endswith('returned_home')], packets=metrics(w, tr)['total_packets'])


if __name__ == '__main__':
    res = {}
    with Pool(20) as pool:
        for long in ('Dax', 'Eve'):
            for name, pol in (('baseline', None), ('without O2', dict(agent_relay=False))):
                det = one((long, 0, pol))
                rs = pool.map(one, [(long, s, pol) for s in range(1, 301)])
                op = np.array([r['open'] if r['open'] is not None else np.inf for r in rs])
                cp = np.array([r['comp'] if r['comp'] is not None else np.inf for r in rs])
                res[f'{long}|{name}'] = dict(noloss_open=det['open'], noloss_comp=det['comp'],
                                             p_open=float(np.isfinite(op).mean()),
                                             open_p50=float(np.median(op)), comp_p50=float(np.median(cp)),
                                             comp_p90=float(np.percentile(cp, 90)),
                                             mean_packets=float(np.mean([r['packets'] for r in rs])))
                print(long, name, res[f'{long}|{name}'], flush=True)
    (OUT / 'outer_futures.json').write_text(json.dumps(res, indent=1))
