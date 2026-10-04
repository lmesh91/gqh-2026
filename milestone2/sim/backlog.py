"""Backlog after an outage: how long a queue of transfers takes to clear once a route is usable again.

At t = 0 each case puts a number of 100-ND transfers into the outboxes at once, which is what an exchange
holds when a long outage ends.  "Cleared" means every transfer has been imported (credited) at its destination
and the source has the RECEIVED for it, i.e. nothing is left unresolved.  Writes results/backlog.json.

    python backlog.py
"""
import json, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from geom import HOUR, DAY, SETTLEMENTS
from protocol import World, CASH, XFER_WINDOW
from transport import Courier

OUT = Path(__file__).resolve().parents[1] / 'results'
H = HOUR
BOOK = [(f'Acct{s}', s, 10_000_000, {}) for s in SETTLEMENTS]


def peak24(ts):
    ts = sorted(ts)
    best, j = 0, 0
    for i, t in enumerate(ts):
        while ts[j] <= t - DAY:
            j += 1
        best = max(best, i - j + 1)
    return best


def case(flows, seed=0, loss=False, until_d=40):
    """flows: list of (src, dst, n).  Returns clearing times and quota use."""
    w = World(seed=seed, loss=loss, maintenance=False, book=BOOK, audit=False, log_launches=False)
    eids = []
    for src, dst, n in flows:
        L = w.ledgers[src]
        for _ in range(n):
            t = L.export(f'Acct{src}', CASH, 100, dst, 'BACKLOG')
            eids.append((src, t['eid']))
    w.run(until_d * DAY)
    xs = [w.ledgers[s].exports[e] for s, e in eids]
    done = [x for x in xs if x['t_receipt'] is not None]
    srcs = sorted({s for s, _, _ in flows} | {d for _, d, _ in flows})
    q = defaultdict(list)
    kinds = defaultdict(lambda: defaultdict(int))
    for t, inst, what in w.quota.log:
        q[inst].append(t)
        kinds[inst][what.split(':')[0] if not what.startswith('DATA') else
                    ('DATA_RCPT' if all(k == 'RECEIVED' for k in what[5:].split('+')) else 'DATA')] += 1
    held = sum(1 for e in w.events if e['kind'] == 'EXPORT_HELD')
    gave_up = sum(1 for e in w.courier.events if e[2] == 'GAVE_UP')
    return dict(flows=[list(f) for f in flows], seed=seed, loss=loss, n=len(xs), cleared=len(done),
                last_import_h=max((x['t_import'] for x in xs if x['t_import'] is not None), default=None) and
                max(x['t_import'] for x in xs if x['t_import'] is not None) / H,
                last_receipt_h=max((x['t_receipt'] for x in done), default=0) / H if len(done) == len(xs) else None,
                first_import_h=min(x['t_import'] for x in xs if x['t_import'] is not None) / H,
                originations={s: len(q[s]) for s in srcs},
                peak24={s: peak24(q[s]) for s in srcs},
                by_kind={s: dict(kinds[s]) for s in srcs},
                held=held, gave_up=gave_up)


def main():
    res = dict(window=XFER_WINDOW, cases={})
    specs = {
        'one_peer': [('Earth', 'Mars', 300)],
        'both_ways': [('Earth', 'Mars', 300), ('Mars', 'Earth', 300)],
        'all_peers': [('Earth', d, 300) for d in SETTLEMENTS if d != 'Earth'],
        'over_window': [('Earth', 'Mars', 1200)],
    }
    for name, fl in specs.items():
        r0 = case(fl)
        runs = [case(fl, seed=s, loss=True) for s in range(20 if name != 'over_window' else 5)]
        clr = [r['last_receipt_h'] for r in runs if r['last_receipt_h'] is not None]
        res['cases'][name] = dict(no_loss=r0, loss=dict(
            runs=len(runs), all_cleared=sum(r['cleared'] == r['n'] for r in runs),
            last_import_h=[r['last_import_h'] for r in runs], last_receipt_h=[r['last_receipt_h'] for r in runs],
            median_receipt_h=sorted(clr)[len(clr) // 2] if clr else None, max_receipt_h=max(clr) if clr else None,
            peak24={s: max(r['peak24'][s] for r in runs) for s in r0['peak24']},
            gave_up=sum(r['gave_up'] for r in runs)))
        L = res['cases'][name]
        print(name, 'no loss: import', round(r0['last_import_h'], 1), 'receipt', r0['last_receipt_h'] and
              round(r0['last_receipt_h'], 1), 'orig', r0['originations'], 'peak', r0['peak24'], 'held', r0['held'])
        print('   loss: cleared', L['loss']['all_cleared'], '/', L['loss']['runs'], 'median', L['loss']['median_receipt_h'],
              'max', L['loss']['max_receipt_h'], 'peak', L['loss']['peak24'])
    (OUT / 'backlog.json').write_text(json.dumps(res, indent=1, default=float))


if __name__ == '__main__':
    main()
