"""E4 certification: prove, interval by interval, that the 200-year scan found every change between open and
closed on every backbone link and direct path.  Adjacent uncertified 1 ms leaves are merged into connected
intervals; each starts and ends in different states, so no open or closed period longer than the longest interval
(0.29 s over 200 years) is missed.

The solar clearance c(t) of a launch emitted at t is Lipschitz with L <= 0.00146 AU/h (see e4_scan.py).
On an interval [a, b] with end values c(a), c(b), every interior value satisfies
    c(t) >= (c(a) + c(b))/2 - L (b - a)/2      and      c(t) <= (c(a) + c(b))/2 + L (b - a)/2.
So the interval is certainly open if the lower bound is >= 0.10 AU and certainly closed if the upper bound
is < 0.10 AU. Otherwise it is split in two and both halves are tested, down to a width of 1 ms. Every
transition is then known to within 1 ms.  Adjacent uncertified 1 ms leaves are merged into connected intervals;
an open or closed period can only be missed if it lies inside one of them, so it is shorter than the widest
connected interval (max_component_s).

    python e4_certify.py          # writes results/e4_certify.json
"""
import json, sys, time
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from geom import *
from e4_scan import YEARS, STEP, clearance_series

OUT = Path(__file__).resolve().parents[1] / 'results'
L = 0.00146 / HOUR            # AU per second
TOL = 1e-3                    # s


def certify(a, b):
    t = np.arange(0, YEARS * YEAR + 1, STEP)
    c = clearance_series(a, b, t)
    mid, half = 0.5 * (c[:-1] + c[1:]), 0.5 * L * STEP
    open_ok = mid - half >= EXCLUSION_AU
    closed_ok = mid + half < EXCLUSION_AU
    todo = np.flatnonzero(~(open_ok | closed_ok))
    leaves, evals, depth = [], 0, 0
    for i in todo:
        stack = [(t[i], t[i + 1], c[i], c[i + 1], 0)]
        while stack:
            lo, hi, cl, ch, dp = stack.pop()
            m, hw = 0.5 * (cl + ch), 0.5 * L * (hi - lo)
            if m - hw >= EXCLUSION_AU or m + hw < EXCLUSION_AU:
                continue
            if hi - lo <= TOL:
                leaves.append((lo, hi, cl >= EXCLUSION_AU, ch >= EXCLUSION_AU))
                continue
            x = 0.5 * (lo + hi)
            cx = flight(a, b, x)[2]
            evals += 1
            depth = max(depth, dp + 1)
            stack += [(x, hi, cx, ch, dp + 1), (lo, x, cl, cx, dp + 1)]
    leaves.sort()
    # a leaf is a <= 1 ms interval whose state could not be certified: it holds every transition
    trans = [lo for lo, hi, so, eo in leaves if so != eo]
    graze = [lo for lo, hi, so, eo in leaves if so == eo]
    grazing = len(graze)
    tr = np.array(trans) if trans else np.array([np.inf])
    far = max((float(np.min(np.abs(tr - g))) for g in graze), default=0.0)   # s from the nearest transition
    # adjacent leaves form one connected uncertified interval; only inside such an interval can a change of state
    # hide, so its width bounds the length of any open or closed period the scan could have missed
    comps = []
    for lo, hi, so, eo in leaves:
        if comps and lo <= comps[-1][1] + 1e-9:
            comps[-1][1] = max(comps[-1][1], hi); comps[-1][3] = eo; comps[-1][4] += 1
        else:
            comps.append([lo, hi, so, eo, 1])
    widths = [hi - lo for lo, hi, *_ in comps]
    same = [hi - lo for lo, hi, so, eo, n in comps if so == eo]
    return f'{a}->{b}', dict(hours=len(t) - 1, certified_open=int(open_ok.sum()), certified_closed=int(closed_ok.sum()),
                             refined_hours=int(len(todo)), evaluations=evals, max_depth=depth,
                             transitions=len(trans), grazing_leaves=grazing, components=len(comps),
                             max_component_s=max(widths, default=0.0), max_leaves_in_component=max((c[4] for c in comps), default=0),
                             components_same_ends=len(same), max_same_ends_s=max(same, default=0.0), grazing_max_from_transition_s=far, closures=len(trans) // 2 + (len(trans) % 2))


def main(paths=None):
    from multiprocessing import Pool
    t0 = time.time()
    if paths is None:
        paths = [(u, v) for u, v in LINKS] + [(v, u) for u, v in LINKS]
        paths += [(x, y) for x in SETTLEMENTS for y in SETTLEMENTS if x != y]
    with Pool(20) as pool:
        res = dict(pool.map(_one, paths, chunksize=1))
    scan = json.loads((OUT / 'e4_scan.json').read_text())
    agree = {}
    for k, v in res.items():
        ref = scan['backbone'].get(k) or scan['direct'].get(k)
        if ref is not None:
            agree[k] = ref['n_closures'] == v['closures']
    out = dict(years=YEARS, step_h=STEP / HOUR, L_AU_per_h=0.00146, tol_s=TOL, paths=res,
               n_paths=len(res), total_hours=sum(v['hours'] for v in res.values()),
               refined_hours=sum(v['refined_hours'] for v in res.values()),
               transitions=sum(v['transitions'] for v in res.values()),
               grazing_leaves=sum(v['grazing_leaves'] for v in res.values()),
               grazing_max_from_transition_s=max(v['grazing_max_from_transition_s'] for v in res.values()),
               components=sum(v['components'] for v in res.values()),
               max_component_s=max(v['max_component_s'] for v in res.values()),
               max_leaves_in_component=max(v['max_leaves_in_component'] for v in res.values()),
               components_same_ends=sum(v['components_same_ends'] for v in res.values()),
               max_same_ends_s=max(v['max_same_ends_s'] for v in res.values()),
               closure_counts_agree=all(agree.values()), disagree=[k for k, ok in agree.items() if not ok],
               runtime_s=time.time() - t0)
    (OUT / 'e4_certify.json').write_text(json.dumps(out, indent=1))
    print({k: v for k, v in out.items() if k != 'paths'})


def _one(ab):
    return certify(*ab)


if __name__ == '__main__':
    main()
