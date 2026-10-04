"""Full machine-readable communication traces for every S1 scenario, the S3 relocations and the S2 incident.

For each run three CSV files are written to ../traces/:
    <run>_launches.csv   every physical packet launch (backbone hops, receipts, direct packets)
    <run>_transport.csv  courier events (sessions opened/failed, resubmits, resets)
    <run>_ledger.csv     every ledger event (instructions, exports, imports, fills, margin, status, ...)
Times are hours from the start of the run (t = 0 is the client's first instruction).

    python export_traces.py
"""
import csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from geom import HOUR
from scenarios import run
from evidence import SCEN, SETTLEMENTS, relocated_book
from scenarios import equity, futures
from transport import Incident

OUT = Path(__file__).resolve().parents[1] / 'traces'
H = HOUR


def _num(x, d=6):
    return round(x, d) if isinstance(x, float) else x


def write(name, w):
    rows = []
    for r in w.net.launches:
        te, ta, a, b, kind, pid, sid, k, d, p, lost, killed, logical = r
        rows.append(dict(t_emit_h=te / H, t_arrive_h=ta / H, src=a, dst=b, layer='backbone', kind=kind, packet=pid,
                         session=sid, copy=k, distance_au=d, p_loss=p, lost=lost, killed=killed,
                         carries='' if not logical else '/'.join(str(x) for x in logical)))
    for r in w.direct_log:
        rows.append(dict(t_emit_h=r['te'] / H, t_arrive_h=r['ta'] / H, src=r['a'], dst=r['b'], layer='direct',
                         kind=r['label'], packet='', session='', copy=r['copy'], distance_au=r['d'],
                         p_loss=r['p_loss'], lost=r['lost'], killed=r['killed'], carries=r['principal']))
    rows.sort(key=lambda x: (x['t_emit_h'], x['src'], x['dst']))
    _csv(OUT / f'{name}_launches.csv', rows)
    tr = [dict(t_h=e[0] / H, at=e[1], event=e[2], peer=e[3], ref=e[4], detail='|'.join(str(x) for x in e[5:]))
          for e in w.courier.events]
    _csv(OUT / f'{name}_transport.csv', tr)
    led = []
    for e in w.events:
        extra = {k: v for k, v in e.items() if k not in ('t', 'actor', 'kind')}
        led.append(dict(t_h=e['t'] / H, actor=e['actor'], event=e['kind'],
                        detail=json.dumps(extra, default=str, separators=(',', ':'))))
    _csv(OUT / f'{name}_ledger.csv', led)
    return dict(launches=len(rows), backbone=len(w.net.launches), direct=len(w.direct_log), transport=len(tr),
                ledger=len(led))


def _csv(path, rows):
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        for r in rows:
            wr.writerow({k: _num(v) for k, v in r.items()})


def main():
    OUT.mkdir(exist_ok=True)
    index = {}
    for key, sc in SCEN.items():
        w, _ = run(sc['spec'], until_h=sc['until'])
        index[key] = dict(title=sc['title'], **write(key, w))
        print(key, index[key])
    for home in SETTLEMENTS:
        w, _ = run([(equity, dict(tag='EQ'))], until_h=900, book=relocated_book(home))
        k = f'S3_reloc_{home}'
        index[k] = dict(title=f'S1a with Alice relocated to {home}', **write(k, w))
        print(k, index[k])
    for k, kw in (('S2_reset_Mars', dict(incidents=[Incident('reset', 'Mars', 0.75 * H)])),):
        w, _ = run([(futures, dict(path='rising'))], until_h=1400, **kw)
        index[k] = dict(title='S1d (rising) with the S2 incident: endpoint reset of Mars at hour 0.75', **write(k, w))
        print(k, index[k])
    (OUT / 'index.json').write_text(json.dumps(index, indent=1))


if __name__ == '__main__':
    main()
