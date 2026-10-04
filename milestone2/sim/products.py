"""Service by product and settlement: the client (Alice's account and funds) is moved to each settlement in turn
and buys each share at its own market (Ares from Bob at Mars, Belt from Cara at Ceres, Terra from Fin at Earth,
1,000 shares at $100 with home delivery), or enters the Mars futures long against Cara (Q = 2,000).
One run without loss and 300 lossy runs per cell.  Writes results/products.json.

    python products.py
"""
import json, sys, time
from multiprocessing import Pool
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from geom import SETTLEMENTS
from scenarios import run, metrics, equity, futures
from evidence import OUT, relocated_book, completion

PRODUCTS = {
    'Ares': ('equity', dict(tag='EQ', seller='Bob', asset='ARES')),
    'Belt': ('equity', dict(tag='EQ', seller='Cara', asset='BELT')),
    'Terra': ('equity', dict(tag='EQ', seller='Fin', asset='TERRA')),
    'Futures': ('futures', dict(path='rising')),
}


def one(args):
    home, prod, seed = args
    kind, kw = PRODUCTS[prod]
    fn = equity if kind == 'equity' else futures
    w, tr = run([(fn, kw)], loss=seed > 0, seed=seed, until_h=1500 if kind == 'futures' else 2000,
                book=relocated_book(home), audit=seed == 0, log_launches=seed == 0)
    m = metrics(w, tr)
    comp = completion(kind, kw.get('tag', 'F1'), m['times'])
    return dict(comp=comp, open=m['times'].get('F1:open'), packets=m['total_packets'], direct=m['direct'],
                relayed=any(e['kind'] == 'AGENT_RELAY' for e in w.events))


def main(n=300):
    res = {}
    with Pool(20) as pool:
        for home in SETTLEMENTS:
            for prod in PRODUCTS:
                t = time.time()
                det = one((home, prod, 0))
                rs = pool.map(one, [(home, prod, s) for s in range(1, n + 1)], chunksize=10)
                cs = np.array([r['comp'] if r['comp'] is not None else np.inf for r in rs])
                res[f'{home}|{prod}'] = dict(
                    noloss=det['comp'], noloss_open=det['open'], packets=det['packets'], direct=det['direct'],
                    relayed=det['relayed'], n=n, completed=int(np.isfinite(cs).sum()),
                    p50=float(np.median(cs)), p90=float(np.percentile(cs, 90)),
                    p_72=float((cs <= 72).mean()), p_168=float((cs <= 168).mean()),
                    p_open=float(np.mean([r['open'] is not None for r in rs])),
                    mean_packets=float(np.mean([r['packets'] for r in rs])))
                print(home, prod, {k: v for k, v in res[f'{home}|{prod}'].items()}, f'{time.time() - t:.0f}s', flush=True)
    (OUT / 'products.json').write_text(json.dumps(res, indent=1, default=float))


if __name__ == '__main__':
    main()
