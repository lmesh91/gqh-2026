"""R9 forwarding during the 2028 Mars conjunction: per-leg copies, delivery probabilities, the forwarding
exchange's quota use and when the client learns the outcome.  Writes results/r9_detail.json.

    python r9_detail.py
"""
import json, math, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from geom import HOUR, DAY
from evidence import SCEN, find_difficult, completion, OUT
from scenarios import run, metrics

H = HOUR


def legs(w):
    """Group the direct launches into messages (a new message starts at copy 0) and give each its delivery
    probability by the first copy's arrival and by the last copy's arrival."""
    msgs = []
    for r in w.direct_log:
        if r['copy'] == 0:
            msgs.append(dict(principal=r['principal'], a=r['a'], b=r['b'], label=r['label'], copies=[]))
        msgs[-1]['copies'].append(r)
    out = []
    for m in msgs:
        cs = m['copies']
        miss = math.prod(c['p_loss'] for c in cs)
        out.append(dict(principal=m['principal'], a=m['a'], b=m['b'], label=m['label'], n=len(cs),
                        t_first_emit=cs[0]['t'] / H, t_first_arrive=cs[0]['ta'] / H, t_last_arrive=cs[-1]['ta'] / H,
                        p_loss_each=[round(c['p_loss'], 4) for c in cs], p_first=1 - cs[0]['p_loss'],
                        p_all=1 - miss))
    return out


def quota_peak(w, who):
    ts = sorted(r['t'] for r in w.direct_log if r['principal'] == who)
    return max((sum(1 for y in ts if x - DAY < y <= x) for x in ts), default=0)


def main():
    diff = find_difficult()
    res = dict(difficult=diff, runs={})
    for key in ('S1a', 'S1d'):
        sc = SCEN[key]
        w, tr = run(sc['spec'], seed=0, loss=False, t0=diff['start_h'] * H, maintenance=False, until_h=1600)
        m = metrics(w, tr)
        ls = legs(w)
        # a forwarded instruction is delivered if both legs are: P = P(leg 1) x P(leg 2)
        chains = []
        for i, l in enumerate(ls):
            if l['label'].startswith('FWD:'):
                nxt = next((x for x in ls[i + 1:] if x['principal'].endswith('(agent)') and x['a'] == l['b']
                            and x['label'] == l['label'][4:]), None)
                if nxt:
                    chains.append(dict(client=l['principal'], via=l['b'], host=nxt['b'], label=nxt['label'],
                                       leg1=l, leg2=nxt, p_both=l['p_all'] * nxt['p_all'],
                                       arrive_h=nxt['t_last_arrive']))
        agents = sorted({l['principal'] for l in ls if l['principal'].endswith('(agent)')})
        status = [dict(t=e['t'] / H, actor=e['actor'], **{k: v for k, v in e.items() if k in ('state', 'what')})
                  for e in w.events if e['kind'] in ('STATUS_QUEUED', 'CLIENT_REPORT', 'REPORT_RECEIVED')]
        res['runs'][key] = dict(completion_h=completion(sc['kind'], sc['tag'], m['times']), times=m['times'],
                                packets=m['total_packets'], backbone=m['backbone_total'], direct=m['direct'],
                                legs=ls, chains=chains,
                                agent_quota_peak={a: quota_peak(w, a) for a in agents},
                                status=status)
        print(key, res['runs'][key]['completion_h'], len(chains), res['runs'][key]['agent_quota_peak'])
        for c in chains:
            print('  ', c['client'], c['via'], c['host'], c['label'], c['leg1']['n'], c['leg2']['n'],
                  round(c['p_both'], 4), round(c['arrive_h'], 2))
    # every epoch of E5: which direct legs each instruction used (direct, or forwarded through which exchange)
    e5 = json.loads((OUT / 'e5.json').read_text())['rows']
    res['epochs'] = {}
    for ep in ('+1 year', '+10 years', '+100 years', 'Mars conjunction'):
        for key in ('S1a', 'S1d'):
            row = e5[f'{ep}|{key}']
            w, tr = run(SCEN[key]['spec'], seed=0, loss=False, t0=row['t0_h'] * H, maintenance=False, until_h=1600)
            ls = legs(w)
            for l in ls:
                for x in ('t_first_emit', 't_first_arrive', 't_last_arrive'):
                    l[x] -= row['t0_h']
            res['epochs'][f'{ep}|{key}'] = dict(t0_h=row['t0_h'], legs=ls,
                                                 agent_quota_peak={a: quota_peak(w, a) for a in
                                                                   {l['principal'] for l in ls if l['principal'].endswith('(agent)')}})
            print(ep, key, [(l['principal'], l['a'][:2], l['b'][:2], l['label'], l['n']) for l in ls])
    (OUT / 'r9_detail.json').write_text(json.dumps(res, indent=1, default=float))


if __name__ == '__main__':
    main()
