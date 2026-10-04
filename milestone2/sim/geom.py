"""Frozen-element geometry for the MultiPlanetary Exchange System (brief Sections 2-3).

All times are seconds since the epoch 2026-09-22 00:00:00 TDB.  Positions are AU in the
Sun-centred J2000 ecliptic frame.  Two implementations are provided: a fast scalar one
(pure `math`, used by the event simulator) and a vectorised NumPy one (used by scans).
"""
from pathlib import Path
import json, math, zipfile
try:
    import numpy as np          # only the vectorised scan helpers need NumPy
except ImportError:            # (the browser build of the simulator runs without it)
    np = None

ROOT = Path(__file__).resolve().parents[2]
with zipfile.ZipFile(ROOT / 'info/data.zip') as z:
    _ORB = json.loads(z.read('orbital_elements.json'))['bodies']
    NET = json.loads(z.read('network_model.json'))

LIGHT_S_PER_AU = 8.317 * 60.0          # brief: 8.317 min per AU
EXCLUSION_AU = 0.10
DAY = 86400.0
HOUR = 3600.0
YEAR = 365.25 * DAY

SETTLEMENTS = ['Mercury', 'Venus', 'Earth', 'Mars', 'Ceres', 'Jupiter', 'Saturn', 'Uranus', 'Neptune']
RELAYS = ['Relay A', 'Relay B']
NODES = SETTLEMENTS + RELAYS
NODE_ID = {n: i + 1 for i, n in enumerate(NODES)}   # brief tie-break IDs 1..11
SHORT = {'Mercury': 'Me', 'Venus': 'Ve', 'Earth': 'Ea', 'Mars': 'Ma', 'Ceres': 'Ce', 'Jupiter': 'Ju',
         'Saturn': 'Sa', 'Uranus': 'Ur', 'Neptune': 'Ne', 'Relay A': 'A', 'Relay B': 'B'}

_EL = {}
for b in _ORB + NET['relays']:
    w, i, o = (math.radians(b[k]) for k in ('arg_peri_deg', 'i_deg', 'node_deg'))
    cw, sw, ci, si, co, so = math.cos(w), math.sin(w), math.cos(i), math.sin(i), math.cos(o), math.sin(o)
    # rotation matrix columns for (x', y') -> ecliptic, applying omega then i then Omega
    P = (co * cw - so * sw * ci, so * cw + co * sw * ci, sw * si)
    Q = (-co * sw - so * cw * ci, -so * sw + co * cw * ci, cw * si)
    _EL[b['name']] = dict(a=b['a_au'], e=b['e'], M0=math.radians(b['mean_anomaly_deg']),
                          n=math.radians(b['mean_motion_deg_day']) / DAY, P=P, Q=Q,
                          b=b['a_au'] * math.sqrt(1 - b['e'] ** 2), raw=b)
ELEMENTS = {k: v['raw'] for k, v in _EL.items()}

EPOCH_CHECK = {
    'Mercury': (-0.213426, -0.410281, -0.013955), 'Venus': (0.679067, -0.257950, -0.042725),
    'Earth': (1.003581, -0.023693, -0.000003), 'Mars': (0.247476, 1.526869, 0.025929),
    'Ceres': (0.375786, 2.653941, 0.014791), 'Jupiter': (-3.438179, 4.038309, 0.060149),
    'Saturn': (9.271221, 1.717485, -0.398962), 'Uranus': (8.962475, 17.253919, -0.052129),
    'Neptune': (29.839098, 1.351785, -0.715470), 'Relay A': (2.0, 2.0, 0.0), 'Relay B': (-2.0, 2.0, 0.0)}


def pos(name, t):
    """Scalar position (AU) of a body at time t (s)."""
    el = _EL[name]
    M = math.fmod(el['M0'] + el['n'] * t, 2 * math.pi)
    e = el['e']
    E = M if e < 0.8 else math.pi
    for _ in range(30):
        f = E - e * math.sin(E) - M
        E -= f / (1 - e * math.cos(E))
        if abs(f) < 1e-15:
            break
    x = el['a'] * (math.cos(E) - e)
    y = el['b'] * math.sin(E)
    P, Q = el['P'], el['Q']
    return (P[0] * x + Q[0] * y, P[1] * x + Q[1] * y, P[2] * x + Q[2] * y)


def vpos(name, t):
    """Vectorised position: t array (s) -> (..., 3) array."""
    el = _EL[name]
    t = np.asarray(t, dtype=float)
    M = np.mod(el['M0'] + el['n'] * t, 2 * np.pi)
    e = el['e']
    E = M.copy() if e < 0.8 else np.full_like(M, np.pi)
    for _ in range(30):
        f = E - e * np.sin(E) - M
        E = E - f / (1 - e * np.cos(E))
        if np.max(np.abs(f)) < 1e-15:
            break
    x = el['a'] * (np.cos(E) - e)
    y = el['b'] * np.sin(E)
    P, Q = np.array(el['P']), np.array(el['Q'])
    return x[..., None] * P + y[..., None] * Q


def _dist(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def seg_clearance(p, q):
    """Closest distance from the Sun (origin) to the segment p->q."""
    vx, vy, vz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
    vv = vx * vx + vy * vy + vz * vz
    f = -(p[0] * vx + p[1] * vy + p[2] * vz) / vv if vv > 0 else 0.0
    f = 0.0 if f < 0 else (1.0 if f > 1 else f)
    return math.sqrt((p[0] + f * vx) ** 2 + (p[1] + f * vy) ** 2 + (p[2] + f * vz) ** 2)


def flight(a, b, te, tol=1e-6):
    """Moving-receiver light time. Returns (t_arrival, path_length_AU, solar_clearance_AU)."""
    p = pos(a, te)
    ta = te + LIGHT_S_PER_AU * _dist(pos(b, te), p)
    for _ in range(50):
        q = pos(b, ta)
        nt = te + LIGHT_S_PER_AU * _dist(q, p)
        if abs(nt - ta) < tol:
            ta = nt
            break
        ta = nt
    q = pos(b, ta)
    return ta, (ta - te) / LIGHT_S_PER_AU, seg_clearance(p, q)


def vflight(a, b, te, iters=8):
    te = np.asarray(te, dtype=float)
    p = vpos(a, te)
    ta = te + LIGHT_S_PER_AU * np.linalg.norm(vpos(b, te) - p, axis=-1)
    for _ in range(iters):
        ta = te + LIGHT_S_PER_AU * np.linalg.norm(vpos(b, ta) - p, axis=-1)
    q = vpos(b, ta)
    v = q - p
    vv = np.sum(v * v, axis=-1)
    f = np.clip(-np.sum(p * v, axis=-1) / vv, 0, 1)
    clr = np.linalg.norm(p + f[..., None] * v, axis=-1)
    return ta, (ta - te) / LIGHT_S_PER_AU, clr


# --------------------------------------------------------------------------- network
LINKS = [(s, r) for s in SETTLEMENTS for r in RELAYS] + [('Relay A', 'Relay B')]
DIRECTED = LINKS + [(b, a) for a, b in LINKS]


def is_link(a, b):
    return (a, b) in DIRECTED


def routes(a, b):
    """All simple backbone routes of <=3 links between two settlements."""
    if a == b:
        return [(a,)]
    return [(a, 'Relay A', b), (a, 'Relay B', b), (a, 'Relay A', 'Relay B', b), (a, 'Relay B', 'Relay A', b)]


class Maintenance:
    """Scheduled one-time maintenance; `offset` shifts nothing: windows are absolute hours.
    For shifted-epoch runs pass enabled=False (brief: do not replay original windows)."""

    def __init__(self, enabled=True):
        self.windows = []
        if enabled:
            for m in NET['maintenance']:
                self.windows.append((frozenset(m['edge']), m['start_hours'] * HOUR, m['end_hours'] * HOUR))

    def blocks(self, a, b, te, ta):
        for edge, lo, hi in self.windows:
            if edge == frozenset((a, b)) and te < hi and ta >= lo:
                return True
        return False

    def next_clear(self, a, b, te, ta):
        """Earliest emission >= te not overlapping maintenance (flight intervals assumed short)."""
        for edge, lo, hi in self.windows:
            if edge == frozenset((a, b)) and te < hi and ta >= lo:
                return hi
        return te


def link_open(a, b, te, maint):
    ta, d, c = flight(a, b, te)
    if c < EXCLUSION_AU:
        return False, ta, d, c
    if maint is not None and maint.blocks(a, b, te, ta):
        return False, ta, d, c
    return True, ta, d, c


def next_geometric_open(a, b, te, step=600.0, horizon=120 * DAY):
    """Earliest emission time >= te whose photon path clears the Sun (bisection to 1 ms)."""
    ta, d, c = flight(a, b, te)
    if c >= EXCLUSION_AU:
        return te
    lo = te
    t = te
    while t - te < horizon:
        t += step
        if flight(a, b, t)[2] >= EXCLUSION_AU:
            hi = t
            while hi - lo > 1e-3:
                mid = 0.5 * (lo + hi)
                if flight(a, b, mid)[2] >= EXCLUSION_AU:
                    hi = mid
                else:
                    lo = mid
            return hi
        lo = t
    return math.inf


def next_launch(a, b, te, maint):
    """Earliest emission >= te at which a launch on a->b is valid (geometry and maintenance)."""
    for _ in range(20):
        t1 = next_geometric_open(a, b, te)
        if t1 == math.inf:
            return t1
        ta = flight(a, b, t1)[0]
        t2 = maint.next_clear(a, b, t1, ta) if maint is not None else t1
        if t2 == t1:
            return t1
        te = t2
    return te


def route_T0(path, t):
    """Brief T0: sequential empty-queue delay (serialization + flight + relay processing),
    pure light time even if blocked, moving receivers."""
    cur = t
    for k, (a, b) in enumerate(zip(path, path[1:])):
        te = cur + 1.0
        ta = flight(a, b, te)[0]
        cur = ta + (1.0 if k < len(path) - 2 else 0.0)
    return cur - t


def route_eval(path, t, maint=None, wait=False):
    """Sequential no-loss one-way evaluation of a route from ready time t.
    Returns dict(delay, hops=[...], open=bool). If wait, packets wait for known closures."""
    cur = t
    hops = []
    ok = True
    for k, (a, b) in enumerate(zip(path, path[1:])):
        te = cur + 1.0
        good, ta, d, c = link_open(a, b, te, maint)
        if not good:
            ok = False
            if wait:
                te = next_launch(a, b, te, maint)
                ta, d, c = flight(a, b, te)
        hops.append(dict(a=a, b=b, te=te, ta=ta, d=d, clr=c, p_loss=1 - math.exp(-0.02 * d)))
        cur = ta + (1.0 if k < len(path) - 2 else 0.0)
    return dict(path=path, delay=cur - t, arrival=cur, hops=hops, open=ok)


def best_route(a, b, t, maint=None, require_open=True):
    best = None
    for p in routes(a, b):
        r = route_eval(p, t, maint)
        if require_open and not r['open']:
            continue
        if best is None or r['delay'] < best['delay']:
            best = r
    return best


def direct_flight(a, b, t_ready):
    """Direct service: 1 s local access + 1 s serialization + flight + 1 s local access."""
    te = t_ready + 2.0
    ta, d, c = flight(a, b, te)
    return dict(te=te, ta=ta, arrive=ta + 1.0, d=d, clr=c, open=c >= EXCLUSION_AU,
                p_loss=1 - math.exp(-0.08 * d))
