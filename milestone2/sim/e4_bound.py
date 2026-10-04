"""Analytic upper bound on every one-way backbone route delay, valid at all times (empty queues).

A route has at most three links: settlement a -> relay -> (other relay) -> settlement b. A settlement is never farther
than its aphelion r from the Sun, the relays are on a circle of radius R, and the two relays are 90 degrees apart
(distance R*sqrt(2) = 4 AU). So the path length is at most (r_a + R) + 4 + (r_b + R) AU, plus 2 s of processing and
serialization at each relay and 1 s at the end. Compared with the 200-year maximum from e4_scan.json.

    python e4_bound.py            # writes results/e4_bound.json
"""
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from geom import ELEMENTS, SETTLEMENTS, LIGHT_S_PER_AU

OUT = Path(__file__).resolve().parents[1] / 'results'
HOSTS = ('Mars', 'Ceres', 'Earth')


def main():
    R = ELEMENTS['Relay A']['a_au']
    rr = R * math.sqrt(2)
    aph = {s: ELEMENTS[s]['a_au'] * (1 + ELEMENTS[s]['e']) for s in SETTLEMENTS}
    scan = json.loads((OUT / 'e4_scan.json').read_text())['routes']
    routes = {}
    for a in SETTLEMENTS:
        for b in HOSTS:
            if a == b:
                continue
            d = (aph[a] + R) + rr + (aph[b] + R)
            routes[f'{a}->{b}'] = dict(bound_min=(d * LIGHT_S_PER_AU + 5.0) / 60,
                                       observed_max=scan[f'{a}->{b}']['max_min'])
    assert all(v['observed_max'] <= v['bound_min'] for v in routes.values())
    out = dict(relay_radius=R, relay_separation=rr, aphelion=aph, routes=routes)
    (OUT / 'e4_bound.json').write_text(json.dumps(out, indent=1))
    print(max(routes.items(), key=lambda kv: kv[1]['bound_min']))


if __name__ == '__main__':
    main()
