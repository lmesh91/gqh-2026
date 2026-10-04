"""E4: 200-Julian-year scan of every backbone link, every direct client path and the best
backbone route from each settlement to each market host, with exact boundary refinement.

Sampling argument (why no closure is missed): the solar clearance of a launch is the distance
from the Sun to the segment sender(t_e) -> receiver(t_a).  That distance moves no faster than
the fastest endpoint, <= 0.00142 AU/h (Mercury at perihelion, 58.98 km/s), and t_a moves at
1 + O(v/c) times t_e, so the clearance is Lipschitz with L <= 0.00146 AU/h.  A closure that
starts and ends between two hourly samples would therefore leave a sample below
0.10 + 0.00146 AU.  Every sample below that guard is refined on a 10 s grid and every
open/closed transition is bisected on the exact scalar light-time solver to 1 ms.
"""
import json, math, sys, time
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from geom import *

OUT = Path(__file__).resolve().parents[1] / 'results'
YEARS = 200
STEP = HOUR
GUARD = EXCLUSION_AU + 0.00146
VMAX_AU_H = 58.98 * 3600 / 149_597_870.7


def clearance_series(a, b, t):
    out = np.empty(len(t))
    for i in range(0, len(t), 400_000):
        out[i:i + 400_000] = vflight(a, b, t[i:i + 400_000])[2]
    return out


def bisect(a, b, lo, hi, lo_open):
    """lo and hi bracket a transition; return emission time of the first state change (1 ms)."""
    while hi - lo > 1e-3:
        mid = 0.5 * (lo + hi)
        if (flight(a, b, mid)[2] >= EXCLUSION_AU) == lo_open:
            lo = mid
        else:
            hi = mid
    return lo, hi


def closures(a, b, t, clr, offset=0.0):
    """Exact closure intervals [start, end) in emission time (s) for one directed path."""
    flag = clr < GUARD
    if not flag.any():
        return [], int(flag.sum())
    idx = np.flatnonzero(flag)
    groups = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    res = []
    for g in groups:
        lo = t[max(g[0] - 1, 0)]
        hi = t[min(g[-1] + 1, len(t) - 1)]
        fine = np.arange(lo, hi + 10.0, 10.0)
        fc = np.array([flight(a, b, x)[2] for x in fine]) if len(fine) < 2000 else vflight(a, b, fine)[2]
        op = fc >= EXCLUSION_AU
        ch = np.flatnonzero(op[1:] != op[:-1])
        start = None
        if not op[0]:
            start = fine[0]          # closed at the start of the scan
        for k in ch:
            l, h = bisect(a, b, fine[k], fine[k + 1], bool(op[k]))
            if op[k]:
                start = h
            else:
                res.append((start, h))
                start = None
        if start is not None:
            res.append((start, None))
    return res, len(groups)


def _backbone(ab):
    a, b = ab
    t = np.arange(0, YEARS * YEAR + 1, STEP)
    clr = clearance_series(a, b, t)
    cl, ng = closures(a, b, t, clr)
    durs = [(e - s) / HOUR for s, e in cl if e is not None and s is not None]
    return f'{a}->{b}', dict(min_clearance=float(clr.min()), t_min_clearance_h=float(t[int(np.argmin(clr))] / HOUR),
                             n_closures=len(cl), flagged_groups=ng,
                             closed_fraction=float(sum(durs) / (YEARS * YEAR / HOUR)),
                             max_closure_h=max(durs) if durs else 0.0, min_closure_h=min(durs) if durs else 0.0,
                             closures=[[s, e] for s, e in cl])


def _direct(ab):
    a, b = ab
    t = np.arange(0, YEARS * YEAR + 1, STEP)
    clr = clearance_series(a, b, t)
    cl, ng = closures(a, b, t, clr)
    durs = [(e - s) / HOUR for s, e in cl if e is not None and s is not None]
    return f'{a}->{b}', dict(min_clearance=float(clr.min()), n_closures=len(cl),
                             closed_fraction=float(sum(durs) / (YEARS * YEAR / HOUR)),
                             max_closure_h=max(durs) if durs else 0.0,
                             mean_closure_h=float(np.mean(durs)) if durs else 0.0,
                             closures=[[s, e] for s, e in cl])


def _route(job):
    a, b = job
    ts = np.arange(0, YEARS * YEAR + 1, 6 * HOUR)
    best = np.full(len(ts), np.inf)
    use = np.zeros(len(ts), int)
    per = {}
    for ri, p in enumerate(routes(a, b)):
        cur = ts.copy()
        ok = np.ones(len(ts), bool)
        for k, (u, v) in enumerate(zip(p, p[1:])):
            ta, d, c = vflight(u, v, cur + 1.0)
            ok &= c >= EXCLUSION_AU
            cur = ta + (1.0 if k < len(p) - 2 else 0.0)
        dl = np.where(ok, cur - ts, np.inf) / 60.0
        per['-'.join(SHORT[n] for n in p)] = float(ok.mean())
        better = dl < best
        best = np.where(better, dl, best)
        use = np.where(better, ri, use)
    fin = np.isfinite(best)
    imax = int(np.argmax(np.where(fin, best, -1)))
    yearly_max = [float(best[i:i + 1461][fin[i:i + 1461]].max()) for i in range(0, len(ts) - 1, 1461)]
    return f'{a}->{b}', dict(connected_fraction=float(fin.mean()), min_min=float(best[fin].min()),
                             p50_min=float(np.median(best[fin])), p95_min=float(np.percentile(best[fin], 95)),
                             max_min=float(best[fin].max()), t_max_h=float(ts[imax] / HOUR),
                             route_availability=per, three_link_fraction=float((use >= 2).mean()),
                             yearly_max_min=yearly_max)


def main():
    from multiprocessing import Pool
    t0 = time.time()
    out = dict(samples=int(YEARS * YEAR / STEP) + 1, step_h=1, years=YEARS, guard_AU=GUARD,
               lipschitz_AU_per_h=0.00146, vmax_mercury_AU_per_h=VMAX_AU_H)
    jobs_r = [(x, h) for h in ('Mars', 'Ceres', 'Earth') for x in SETTLEMENTS if x != h]
    jobs_r += [(h, x) for x, h in jobs_r]
    with Pool(20) as pool:
        out['backbone'] = dict(pool.map(_backbone, DIRECTED, chunksize=1))
        print('backbone', f'{time.time() - t0:.0f}s', flush=True)
        out['direct'] = dict(pool.map(_direct, [(a, b) for a in SETTLEMENTS for b in SETTLEMENTS if a != b],
                                      chunksize=1))
        print('direct', f'{time.time() - t0:.0f}s', flush=True)
        out['routes'] = dict(pool.map(_route, jobs_r, chunksize=1))
        print('routes', f'{time.time() - t0:.0f}s', flush=True)
    out['runtime_s'] = time.time() - t0
    OUT.mkdir(exist_ok=True)
    (OUT / 'e4_scan.json').write_text(json.dumps(out))


if __name__ == '__main__':
    main()
