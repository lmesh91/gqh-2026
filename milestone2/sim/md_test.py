"""E7. Market data (R5): how old is the quote a client gets, how long does it wait, and what does it cost?

Market data travels only as a reply to a quote request.  At every settlement a client asks its own exchange for every
stock listed elsewhere (24 exchange-stock pairs), for 30 days, with random loss and maintenance, accepting a quote no
older than its request interval.  Local traders at each market change the book every 2 h (GTC or IOC, 1-50 shares,
limit 95-105, 8 h expiry).  Two demand levels: a request per pair every 24 h, and every 6 h (the most the rules send,
since an exchange makes at most one request per stock per 6 h).  Originations are counted from the quota log, so they
include SYNs for new sessions."""
import json, random, sys
from collections import defaultdict
from pathlib import Path
from geom import HOUR, DAY, SETTLEMENTS
from protocol import World, REGISTRY, OPENING_BOOK

OUT = Path(__file__).resolve().parents[1] / 'results'


def one(seed, every_h, max_age_h, days=30):
    book = OPENING_BOOK + [(f'{m[:2]}loc', m, 10**7, {a: 10**6 for a, mm in REGISTRY.items() if mm == m})
                           for m in set(REGISTRY.values())]
    w = World(seed=seed, loss=True, maintenance=True, book=book, log_launches=False, audit=False)
    rng = random.Random(seed)
    asked, served = {}, []
    n = defaultdict(int)

    def trader(m, a):
        def go():
            n[m] += 1
            w.ledgers[m].instruction(f'{m[:2]}loc', dict(
                type='ORDER', oid=f'{m}-{n[m]}', asset=a, side=rng.choice(['BUY', 'SELL']), qty=rng.randint(1, 50),
                limit=rng.randint(95, 105), tif=rng.choice(['GTC', 'IOC']), expiry=w.now + 8 * HOUR, disp='RETAIN'),
                'local')
            w.net.at(w.now + 2 * HOUR, go, rank=1)
        w.net.at(w.t0 + rng.uniform(0, 2) * HOUR, go, rank=1)
    for a, m in REGISTRY.items():
        trader(m, a)

    def watch(what, where, obj):
        if what == 'quote':
            k = (obj['client'], obj['snap']['asset'])
            if k in asked:
                served.append(dict(home=where, wait_h=(w.now - asked.pop(k)) / HOUR,
                                   age_h=(w.now - obj['snap']['t']) / HOUR))
    w.watchers.append(watch)

    def client(home, a):
        c = f'Q@{home}:{a}'
        def go():
            if (c, a) not in asked:
                asked[c, a] = w.now
                w.ledgers[home].md_request(c, a, max_age_h * HOUR)
            w.net.at(w.now + every_h * HOUR, go, rank=1)
        w.net.at(w.t0 + rng.uniform(0, min(every_h, 6)) * HOUR, go, rank=1)

    for home in SETTLEMENTS:
        for a, m in REGISTRY.items():
            if m != home:
                client(home, a)
    w.run(days * DAY)
    per = defaultdict(list)
    for t, inst, what in w.quota.log:
        per[inst].append(t)

    def peak(ts):
        ts = sorted(ts); j = best = 0
        for i, t in enumerate(ts):
            while ts[j] <= t - DAY:
                j += 1
            best = max(best, i - j + 1)
        return best
    mk = sorted(set(REGISTRY.values()))
    return dict(served=served, days=days, pending=len(asked),
                records={m: sum(1 for x in w.ledgers[m].md_log if x[1] == 'reply') for m in mk},
                requests={h: sum(1 for x in w.ledgers[h].md_log if x[1] == 'mdreq') for h in SETTLEMENTS},
                peak={m: peak(per[m]) for m in SETTLEMENTS})


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p * len(v)))]


def summarise(runs):
    by = defaultdict(list)
    for r in runs:
        for x in r['served']:
            by[x['home']].append(x)
    sv = [x for v in by.values() for x in v]
    nd = len(runs) * runs[0]['days']
    return dict(
        by_home={h: dict(age_p50=pct([x['age_h'] for x in v], .5), age_p95=pct([x['age_h'] for x in v], .95),
                         wait_p95=pct([x['wait_h'] for x in v], .95), wait_max=max(x['wait_h'] for x in v), n=len(v))
                 for h, v in by.items()},
        replies_per_day={m: sum(r['records'][m] for r in runs) / nd for m in runs[0]['records']},
        requests_per_day=sum(sum(r['requests'].values()) for r in runs) / nd,
        peak_orig={m: max(r['peak'][m] for r in runs) for m in runs[0]['records']},
        served=len(sv), immediate=sum(x['wait_h'] < 1e-6 for x in sv) / len(sv),
        pending=sum(r['pending'] for r in runs), runs=len(runs))


if __name__ == '__main__':
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    res = {name: summarise([one(s, e, e) for s in range(seeds)]) for name, e in (('daily', 24), ('six_hourly', 6))}
    (OUT / 'md_test.json').write_text(json.dumps(res, indent=1, default=float))
    for name, r in res.items():
        print(name, {h: (round(v['age_p50'], 1), round(v['age_p95'], 1), round(v['wait_p95'], 1), round(v['wait_max'], 1))
                     for h, v in r['by_home'].items()})
        print('   replies/day', {m: round(x, 1) for m, x in r['replies_per_day'].items()}, 'peak', r['peak_orig'],
              'immediate %.2f' % r['immediate'], 'pending', r['pending'])
