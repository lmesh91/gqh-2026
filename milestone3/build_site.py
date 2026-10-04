"""Build the data files the website needs.

    python build_site.py

* data/py_bundle.json  - the unmodified Milestone 2 simulator sources + webapi.py + the two data.zip
                         members the simulator reads; the page loads them into Pyodide for custom runs.
* data/replays.json    - every preset scenario pre-run with the same code (instant playback, works offline).
* data/evidence.json   - compact summaries of the Milestone 2 evidence runs for the Evidence tab.
"""
import json, sys, zipfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SIM = ROOT / 'milestone2' / 'sim'
RES = ROOT / 'milestone2' / 'results'
OUT = HERE / 'data'
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(HERE / 'py'))
import webapi  # noqa: E402

CONJ = 12470.027099609375          # E5 difficult epoch: 24 h after Earth->Mars direct closes (h since epoch)

PRESETS = [
    # id, group, title, blurb, cfg
    ('S1a', 'Required scenarios', 'Earth buys Mars shares',
     'Alice (Earth) buys 1,000 Ares from Bob (Mars) at $100: fund, order, local fill, automatic delivery home.',
     dict(trades=[dict(type='equity', buyer='Alice', asset='ARES', tag='EQ')], until_h=48)),
    ('S1b', 'Required scenarios', 'Earth buys Ceres shares',
     'The same trade against Cara at Ceres; Mars is not involved at all.',
     dict(trades=[dict(type='equity', buyer='Alice', asset='BELT', tag='EQB')], until_h=48)),
    ('S1c', 'Required scenarios', 'Uranus buys Earth shares',
     'Eve at Uranus buys 400 Terra from Fin at Earth: 2.6-hour light time, 78% loss per direct copy.',
     dict(trades=[dict(type='equity', buyer='Eve', asset='TERRA', qty=400, tag='EQT')], until_h=96)),
    ('S1d', 'Required scenarios', 'Futures, rising prices',
     'Alice long, Cara short, Q = 2,000 hosted at Mars. Prices 110 → 125: Alice receives $130k gross.',
     dict(trades=[dict(type='futures', path='rising', tag='F1')], until_h=700)),
    ('S1e', 'Required scenarios', 'Futures, falling prices',
     'Same contract, prices 90 → 75: identical until the first observation, then Cara wins.',
     dict(trades=[dict(type='futures', path='falling', tag='F1')], until_h=700)),
    ('S1f', 'Required scenarios', 'Futures at the boundary (Q = 2,500)',
     'Margin $100,000 each: the largest contract Cara can fund.',
     dict(trades=[dict(type='futures', path='rising', Q=2500, tag='F1')], until_h=700)),
    ('S1g', 'Required scenarios', 'Binding: Q = 2,501',
     'Cara cannot fund $100,040; Alice\'s margin waits at Mars until the 168 h deadline and comes home.',
     dict(trades=[dict(type='futures', path='rising', Q=2501, tag='F1')], until_h=400)),
    ('S1h', 'Required scenarios', 'Binding: Q = 4,000',
     'Both homes reject the funding before anything moves.',
     dict(trades=[dict(type='futures', path='rising', Q=4000, tag='F1')], until_h=100)),
    ('S1i', 'Required scenarios', 'Repeat trading on $10,000',
     'Two orders, a partial fill with price improvement, a cancel/fill race, a resale, a final sweep home.',
     dict(trades=[dict(type='repeat', tag='RT')], until_h=120)),
    ('S2', 'Stress', 'Worst incident: Mars reset at 0.75 h',
     'Worst of 56,280 stress runs. Mars forgets its sessions just after the handshakes; funding sits in transit for ~125 h.',
     dict(trades=[dict(type='futures', path='rising', tag='F1')], incidents=[dict(kind='reset', node='Mars', start_h=0.75)],
          until_h=700)),
    ('S2A1', 'Stress', 'Same incident with restart notice (A1)',
     'Mars tells its recent peers it restarted; they resend at once. Futures complete on schedule.',
     dict(trades=[dict(type='futures', path='rising', tag='F1')], incidents=[dict(kind='reset', node='Mars', start_h=0.75)],
          policy=dict(restart_notice=True), until_h=700)),
    ('S2iso', 'Stress', 'Mars isolated for 72 h at fixing',
     'The host goes dark from h 310: payouts wait, funded, in the outbox and leave when the links return.',
     dict(trades=[dict(type='futures', path='rising', tag='F1')], incidents=[dict(kind='isolation', node='Mars', start_h=310)],
          until_h=700)),
    ('S1c-loss', 'Stress', 'Lossy run: Uranus buys Terra',
     'Random loss on (seed 7): watch copies and hop retries die and the fallback order go out.',
     dict(trades=[dict(type='equity', buyer='Eve', asset='TERRA', qty=400, tag='EQT')], loss=True, seed=7, until_h=200)),
    ('S3Ne', 'Access (S3)', 'Alice moved to Neptune',
     'The worst-served settlement: 4-hour light time and 91% loss per direct copy.',
     dict(trades=[dict(type='equity', buyer='Alice', asset='ARES', tag='EQ')], homes=dict(Alice='Neptune'), until_h=200)),
    ('S3Me', 'Access (S3)', 'Alice moved to Mercury',
     'The Mercury–Mars direct path closes at h 22; the client checks the whole sequence fits first.',
     dict(trades=[dict(type='equity', buyer='Alice', asset='ARES', tag='EQ')], homes=dict(Alice='Mercury'), until_h=100)),
    ('S3Dax', 'Access (S3)', 'Dax (Neptune) goes long against Cara',
     'An outer-system futures position: margin funding across 30 AU.',
     dict(trades=[dict(type='futures', path='rising', long='Dax', short='Cara', tag='F1')], until_h=800)),
    ('E5conj', 'Far future (E5)', 'Mars behind the Sun (2028)',
     'Start 24 h into the 53-day Earth–Mars direct blackout. Rule R9 forwards the order Earth → Mercury → Mars under '
     'Mercury\'s quota. Trade done in under 5 h.',
     dict(trades=[dict(type='equity', buyer='Alice', asset='ARES', tag='EQ')], t0_h=CONJ, until_h=200)),
    ('E5conjNoR9', 'Far future (E5)', 'Blackout without forwarding',
     'The same start with rule R9 switched off for comparison. The client keeps its money home: no trade, no loss.',
     dict(trades=[dict(type='equity', buyer='Alice', asset='ARES', tag='EQ')], t0_h=CONJ, until_h=1600,
          policy=dict(agent_relay=False))),
    ('E5fut', 'Far future (E5)', 'Futures during the blackout',
     'Alice and Cara open the capped futures while Earth cannot see Mars directly; Alice\'s instructions are forwarded (R9).',
     dict(trades=[dict(type='futures', path='rising', tag='F1')], t0_h=CONJ, until_h=400)),
    ('E5y100', 'Far future (E5)', 'The same trade in 2126',
     'Orbits advanced 100 years; the rules need no changes.',
     dict(trades=[dict(type='equity', buyer='Alice', asset='ARES', tag='EQ')], epoch_years=100, until_h=48)),
]


def bundle():
    files = {}
    for f in ('geom.py', 'transport.py', 'protocol.py', 'scenarios.py', 'traces.py'):
        files[f] = (SIM / f).read_text()
    files['webapi.py'] = (HERE / 'py' / 'webapi.py').read_text()
    with zipfile.ZipFile(ROOT / 'info' / 'data.zip') as z:
        data = {n: z.read(n).decode() for n in ('orbital_elements.json', 'network_model.json')}
    (OUT / 'py_bundle.json').write_text(json.dumps(dict(py=files, data=data)))


def replays():
    out = {}
    for pid, group, title, blurb, cfg in PRESETS:
        t = time.time()
        r = webapi.simulate(cfg)
        assert r['ok'], (pid, r)
        out[pid] = dict(id=pid, group=group, title=title, blurb=blurb, cfg=cfg, result=r)
        print(f'{pid:9s} {time.time() - t:5.2f}s  done={r["completion"]}  packets={r["metrics"]["total"]}')
    (OUT / 'replays.json').write_text(json.dumps(clean(dict(elements=webapi.elements(), presets=out)), separators=(',', ':'), allow_nan=False))


def evidence():
    def load(n):
        p = RES / f'{n}.json'
        return json.loads(p.read_text()) if p.exists() else None
    e2, s3, s2d, e5 = load('e2'), load('s3'), load('s2_detail'), load('e5')
    ev = {}
    if e2:
        ev['mc'] = {k: dict(p50=v['p50'], p90=v['p90'], p99=v['p99'], n=v['n'], completed=v['completed'],
                            comps=sorted(round(c, 3) for c in v['comps'] if c is not None)[::4])
                    for k, v in e2.items() if k != 'direct'}
    if s3:
        ev['relocations'] = {k: dict(noloss=v['completion_h'], p50=v['mc_p50'], p90=v['mc_p90'], p99=v['mc_p99'],
                                     p72=v['p_by_72h'], packets=v['packets']) for k, v in s3['relocations'].items()}
    srch = {}
    for path in ('rising', 'falling'):
        d = load(f's2_search_{path}')
        if d:
            g = {}
            for r in d['runs']:
                g.setdefault(f"{r['kind']}|{r['node']}", []).append([r['start'], round(min(r['damage'], 1e3), 1)])
            for k, pts in g.items():          # keep only the points where the damage changes
                pts.sort()
                keep = [p for i, p in enumerate(pts) if i in (0, len(pts) - 1) or p[1] != pts[i - 1][1] or p[1] != pts[i + 1][1]]
                g[k] = keep
            srch[path] = dict(base=d['base'], n=d['n'], series=g)
    if srch:
        ev['s2_search'] = srch
    if s2d:
        ev['s2_mc'] = {k: v for k, v in s2d['runs'].items() if k.startswith('mc:')}
    if e5:
        ev['e5'] = {k: dict(comp=v['noloss']['comp'], p50=v['mc']['p50'], suspended=v['noloss']['suspended'],
                            deferred=v['noloss']['deferred'], relays=len(v['noloss']['relays']))
                    for k, v in e5['rows'].items()}
    e4 = load('e4_scan')
    if e4:
        ev['e4'] = dict(years=e4['years'], routes={k: {kk: v[kk] for kk in ('min_min', 'p50_min', 'p95_min', 'max_min',
                                                                            'connected_fraction')}
                                                   for k, v in e4['routes'].items()},
                        direct={k: dict(closed=v['closed_fraction'], n=v['n_closures'], max_h=v['max_closure_h'])
                                for k, v in e4['direct'].items()})
    (OUT / 'evidence.json').write_text(json.dumps(clean(ev), separators=(',', ':'), allow_nan=False))


def clean(x):
    """NaN / inf (e.g. a median over runs that never complete) -> null, so browsers can parse the file."""
    if isinstance(x, float):
        return x if x == x and abs(x) != float('inf') else None
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


def stdlib_text():
    """Pyodide's python_stdlib.zip as base64 text (the Artifact host serves no .zip files)."""
    import base64
    z = HERE / 'pyodide' / 'python_stdlib.zip'
    (HERE / 'pyodide' / 'python_stdlib.b64.txt').write_text(base64.b64encode(z.read_bytes()).decode())


def page():
    """index.html for local serving = the artifact page (app.html) inside a standard document skeleton."""
    body = (HERE / 'app.html').read_text()
    (HERE / 'index.html').write_text('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
                                     '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
                                     '</head><body>\n' + body + '\n</body></html>\n')


if __name__ == '__main__':
    page()
    stdlib_text()
    bundle()
    replays()
    evidence()
    for f in sorted(OUT.iterdir()):
        print(f.name, f'{f.stat().st_size / 1e3:.0f} kB')
