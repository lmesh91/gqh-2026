"""Where should the derivatives clearing host sit?  200-year, 2-day sampled study of
sequential best-route one-way delay and first-attempt delivery probability between
every pair of settlements (no maintenance; geometry only)."""
import itertools, json, sys
import numpy as np
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from geom import *

def route_arrays(path, t):
    cur = t.copy(); ok = np.ones_like(t, bool); surv = np.ones_like(t)
    for k, (a, b) in enumerate(zip(path, path[1:])):
        te = cur + 1.0
        ta, d, c = vflight(a, b, te)
        ok &= c >= EXCLUSION_AU
        surv *= np.exp(-0.02 * d)
        cur = ta + (1.0 if k < len(path) - 2 else 0.0)
    return cur - t, ok, surv

def pair_matrix(t):
    n = len(SETTLEMENTS)
    D = np.zeros((n, n, len(t))); S = np.ones((n, n, len(t)))
    for i, a in enumerate(SETTLEMENTS):
        for j, b in enumerate(SETTLEMENTS):
            if i == j: continue
            best = np.full(len(t), np.inf); bs = np.zeros(len(t))
            for p in routes(a, b):
                d, ok, s = route_arrays(p, t)
                d = np.where(ok, d, np.inf)
                better = d < best
                best = np.where(better, d, best); bs = np.where(better, s, bs)
            D[i, j] = best; S[i, j] = bs
    return D / 60.0, S

if __name__ == '__main__':
    t = np.arange(0, 200 * YEAR + 1, 2 * DAY)
    D, S = pair_matrix(t)
    assert np.isfinite(D[~np.eye(9, dtype=bool)]).all(), 'some pair disconnected'
    out = {'samples': len(t), 'step_days': 2, 'hosts': {}}
    n = 9
    RT = D + D.transpose(1, 0, 2)          # round trip X->H->X at the same sample (approx.)
    for h, H in enumerate(SETTLEMENTS):
        others = [i for i in range(n) if i != h]
        one = D[others, h]                  # X -> H
        rt = RT[others, h]
        pair = []                           # contract between two other settlements: slower leg
        for i, j in itertools.combinations(range(n), 2):
            pair.append(np.maximum(D[i, h] if i != h else 0, D[j, h] if j != h else 0))
        pair = np.array(pair)
        out['hosts'][H] = dict(mean_one_way_min=float(one.mean()), p95_one_way_min=float(np.percentile(one, 95)),
                               max_one_way_min=float(one.max()), mean_round_trip_min=float(rt.mean()),
                               mean_pair_slower_leg_min=float(pair.mean()),
                               mean_first_try_success=float((S[others, h] * S[h, others]).mean()),
                               inner_mean_one_way_min=float(D[[i for i in range(5) if i != h], h].mean()))
    # 1, 2, 3 host sets: each contract (pair i<j) uses the host in the set minimising its slower leg (fixed rule by mean)
    pairs = list(itertools.combinations(range(n), 2))
    def legs(i, j, h):
        a = D[i, h] if i != h else np.zeros(len(t)); b = D[j, h] if j != h else np.zeros(len(t))
        return np.maximum(a, b)
    L = {(i, j, h): legs(i, j, h).mean() for (i, j) in pairs for h in range(n)}
    sets = {}
    for k in (1, 2, 3):
        best = None
        for combo in itertools.combinations(range(n), k):
            cost = np.mean([min(L[i, j, h] for h in combo) for (i, j) in pairs])
            if best is None or cost < best[0]:
                best = (cost, combo)
        sets[k] = dict(hosts=[SETTLEMENTS[h] for h in best[1]], mean_pair_slower_leg_min=float(best[0]))
    out['host_sets'] = sets
    # per-settlement delay statistics to every other (for S3/E4 reference)
    out['pair_mean_min'] = {SETTLEMENTS[i]: {SETTLEMENTS[j]: float(D[i, j].mean()) for j in range(n) if j != i} for i in range(n)}
    json.dump(out, open(ROOT / 'milestone2/results/placement.json', 'w'), indent=1)
    for H, v in out['hosts'].items():
        print(f"{H:8s} mean1w {v['mean_one_way_min']:7.1f} p95 {v['p95_one_way_min']:7.1f} max {v['max_one_way_min']:7.1f} pair {v['mean_pair_slower_leg_min']:7.1f} inner {v['inner_mean_one_way_min']:6.1f} succ {v['mean_first_try_success']:.3f}")
    print(sets)
