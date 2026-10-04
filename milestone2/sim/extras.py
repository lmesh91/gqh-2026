"""Small geometric tables used by the paper: direct access to every market host (S3) and the
route delays / availabilities at each shifted epoch (E5 Tier 1).  Writes ../results/extras.json."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from geom import *
from evidence import availability, direct_availability, find_difficult, OUT
from protocol import World

H = HOUR
HOSTS = ('Mars', 'Ceres', 'Earth')


def direct_row(x, host, t):
    if x == host:
        return dict(delay=1 / 60, p_loss=0.0, copies=0, burst=1.0, avail=1.0, open=True)
    f = direct_flight(x, host, t)
    k = World().direct_copies(x, host, t)
    return dict(delay=(f['arrive'] - t) / 60, p_loss=f['p_loss'], copies=k, burst=1 - f['p_loss'] ** k,
                avail=direct_availability(x, host, t), open=bool(f['open']))


def s3_direct():
    out = {}
    for hh in (0, 300):
        for x in SETTLEMENTS:
            for host in HOSTS:
                out[f'{x}|{host}|{hh}'] = direct_row(x, host, hh * H)
    return out


def e5_routes():
    diff = find_difficult()
    epochs = {'+1 year': YEAR, '+10 years': 10 * YEAR, '+100 years': 100 * YEAR,
              'Mars conjunction': diff['start_h'] * H}
    pairs = [('Earth', 'Mars'), ('Mars', 'Earth'), ('Earth', 'Ceres'), ('Ceres', 'Earth'), ('Ceres', 'Mars'),
             ('Mars', 'Ceres'), ('Uranus', 'Earth'), ('Earth', 'Uranus')]
    out = {}
    for name, t in epochs.items():
        rows = []
        for a, b in pairs:
            br = best_route(a, b, t, None, require_open=False)
            d = direct_row(a, b, t)
            rows.append(dict(a=a, b=b, route='-'.join(SHORT[n] for n in br['path']), delay=br['delay'] / 60,
                             avail=availability(br['path'], t, None), direct_delay=d['delay'],
                             direct_avail=d['avail'], direct_open=d['open'], direct_p_loss=d['p_loss']))
        out[name] = dict(t0_h=t / H, rows=rows)
    return out


if __name__ == '__main__':
    res = dict(s3_direct=s3_direct(), e5_routes=e5_routes(), difficult=find_difficult())
    (OUT / 'extras.json').write_text(json.dumps(res, indent=1, default=float))
    for k, v in res['e5_routes'].items():
        for r in v['rows']:
            print(k, r['a'], r['b'], r['route'], round(r['delay'], 1), round(r['avail'], 3),
                  round(r['direct_delay'], 1), round(r['direct_avail'], 3))
