"""Evidence appendix (12 pages max): E1, S1 + E2 + E3, S2, S3, E4, E5."""
from build import *
from collections import defaultdict
import math


def build():
    o = ['''<div class="kicker">MultiPlanetary Exchange System · Evidence appendix · Milestone 2 draft · design v3</div>
<h1>Evidence appendix</h1>
<p>All results come from one discrete-event simulator that implements the brief's network exactly (moving-receiver
light time, solar exclusion on every launch, 19 links, FIFO serialization, relay processing, hop and endpoint timers,
handshakes, quotas, maintenance, incidents, per-launch loss) and our v3 ledgers. Every traced run checks
conservation, non-negativity, hold arithmetic and registry custody after every ledger event. A trace is a
<b>conditional, no-loss</b> run unless labelled "lossy". Times are hours after the scenario start; the epoch is
2026-09-22 00:00 TDB. "Bound" and "exact" are stated wherever a probability appears.</p>''']
    o.append(e1())
    o.append(s1())
    o.append(e2())
    o.append(e3())
    o.append(s2())
    o.append(s3())
    o.append(e4())
    o.append(e5())
    return '\n'.join(o)


# ====================================================================== E1
def e1():
    ep = E1['epoch']
    rows = [[r['body'], f"{r['x']:+.6f}", f"{r['y']:+.6f}", f"{r['z']:+.6f}", f"{r['err']:.1e}"] for r in ep]
    later = {}
    for r in E1['later']:
        later.setdefault(r['body'], {})[r['hour']] = r
    lrows = [[b, *(f"({v['x']:+.4f}, {v['y']:+.4f}, {v['z']:+.4f})" for v in (later[b][300], later[b][8766.0]))]
             for b in later]
    ex = E1['examples']
    xr = [[f"{SH(r['a'])}→{SH(r['b'])}", f"{r['te']:.3f}", f"{r['flight']:.6f}", f"{r['frozen']:.6f}",
           f"{r['diff_ms']:+.3f}", f"{r['d']:.4f}", f"{r['clearance']:.3f}"] for r in ex]
    tm = [[t['path'], f"{t['t']:.4f}", f"{t['T0_min']:.2f}", f"{t['Re_h']:.3f}",
           ', '.join(f'{x:.1f}' for x in t['Rh_min'])] for t in E1['timers']]
    worst = max(r['err'] for r in ep)
    return f'''<h2>E1. Orbital calculations</h2>
<p><b>Method.</b> Each body follows the fixed Kepler ellipse in <code>data.zip</code>: mean anomaly
M = M₀ + n·t (n from the supplied mean motion), Kepler's equation solved by Newton iteration until the residual is
below 10⁻¹⁵ rad, then rotation by ω, i, Ω into the Sun-centred J2000 ecliptic frame. Units: AU and seconds of TDB
since the epoch (hours in tables). The relays use the same code with e = 0 and the supplied phases. <b>Light time:</b>
a packet emitted at t_e from P reaches Q at the t_a solving t_a = t_e + 499.02·|Q(t_a) − P(t_e)| (8.317 min/AU),
found by fixed-point iteration; for Earth→A the successive corrections are
{', '.join(f'{x:.1e}' for x in E1['iterations_Earth_A'][:3])} s (each step shrinks by v/c ≈ 10⁻⁴), so two
iterations reach 1 ms and we always iterate to 10⁻⁶ s. <b>Solar exclusion:</b> distance from the Sun to the segment P(t_e)→Q(t_a), blocked below 0.10 AU. Every
launch, ACK and receipt is evaluated at its own emission time. Maximum epoch error against the brief's table:
{worst:.1e} AU (table rounding).</p>
{table(['Body', 'x (AU)', 'y (AU)', 'z (AU)', '|error|'], rows, cls='compact', num=(1, 2, 3, 4))}
<p><b>Worked later positions</b> (same propagator): hour 300 and one Julian year.</p>
{table(['Body', 'hour 300 (x, y, z) AU', 'hour 8,766 (x, y, z) AU'], lrows, cls='compact')}
<p><b>Receiver motion changes arrival.</b> Rows 1–4 are the S1a funding path forward (Earth→A→Mars) and the return
path for the shares (Mars→A→Earth) at their actual emission times; each relay forward departs 2 s after arrival
(1 s processing + 1 s serialization). "Frozen" uses both positions at emission. The forward and return legs are not
mirror images: Earth→A gains {ex[0]['diff_ms']:+.1f} ms because Relay A moves away during flight, while the return
legs differ again.</p>
{table(['Path', 't_e (s)', 'flight (s)', 'frozen (s)', 'Δ ms', 'd (AU)', 'clear (AU)'], xr, cls='compact',
           num=(1, 2, 3, 4, 5, 6))}
<p><b>Timers used.</b> T0 is the empty-queue route time; R_e = 2·T0 + 24 h; R_h = 2·flight + 60 min per hop.</p>
{table(['Route', 'at h', 'T0 (min)', 'R_e (h)', 'R_h per hop (min)'], tm, cls='compact', num=(1, 2, 3))}'''


def SH(n):
    return {'Relay A': 'A', 'Relay B': 'B'}.get(n, n)


# ====================================================================== S1
def s1():
    import traces
    from scenarios import equity, futures
    names = [('S1a', 'Earth→Mars Ares purchase'), ('S1b', 'Earth→Ceres Belt purchase'), ('S1c', 'Uranus→Earth Terra purchase'),
             ('S1d', 'Futures, rising'), ('S1e', 'Futures, falling'), ('S1f', 'Futures Q = 2,500 (boundary)'),
             ('S1g', 'Futures Q = 2,501 (binds)'), ('S1h', 'Futures Q = 4,000 (binds)'), ('S1i', '$10k repeat trading')]
    rows = []
    for k, title in names:
        r = S1[k]
        c = r['capital']
        enc = '; '.join(f"{a.title() if a != 'ND' else '$'} {x['peak_encumbered']:,} / {x['enc_hours']:,.0f}"
                        for a, x in c.items() if x['peak_encumbered'])
        rows.append([k, title, h(r['completion_h']), f"{r['backbone_total']} + {r['direct']} = {r['total_packets']}",
                     r['transactions'], h(r['comm_efficiency'], 1), enc or '—', pct(r['utilisation'], 0),
                     h(r['capital_efficiency'], 2)])
    out = [f'''<h2>S1. Scenario traces (no loss, epoch, maintenance on)</h2>
<p>Traces omit only the "receipt known" bookkeeping rows (no balance changes) and Bob's publication of each
observation (the next row shows Mars recording it). Each scenario is a separate run from the opening book. Completion = every intended result spendable at its owner's
home. Packets count every backbone launch (data, handshake, hop receipts, ACKs, retries) plus every direct copy.
Encumbered = order holds + contract margin + value in transit, per asset as peak / asset-hours.
Utilisation = peak encumbered cash ÷ $500,000. Capital efficiency = peak encumbered $ ÷ value settled.</p>''',
           table(['', 'Scenario', 'Done (h)', 'Packets bb + dir', 'Tx', 'Pkts/tx', 'Peak enc. / asset-hours',
                  'Util.', 'Cap. eff.'], rows, cls='compact', num=(2, 4, 5, 7, 8)),
           f'''<p><b>Scale and binding constraint.</b> The futures hold $160,000 = 32% of all cash in escrow for 324 h
(S1d/S1e); the boundary Q = 2,500 holds $200,000 = 40%. Q = 2,501 needs $100,040 per side: Cara's Ceres exchange rejects
her funding transfer at once (she owns $100,000), Alice's $100,040 is held at Mars until the 168 h deadline, released,
and returned home by her withdrawal at {h(S1['S1g']['times'].get('F1:Alice:returned_home'))} h. Q = 4,000 ($160,000
each) is rejected at both homes before anything moves. Every audit passed: {sum(S1[k]['audits'] for k, _ in names):,}
checks across these runs.</p>''']
    # S1a full trace
    w, tr, sn = traces.run_traced([(equity, dict(tag='EQ'))], ['Alice', 'Bob'], ('ARES',), until_h=48)
    out.append('<h3>S1a full trace: Alice (Earth) buys 1,000 Ares from Bob (Mars) at $100</h3>')
    out.append(traces.html_table(traces.rows_for(w, tr, sn, ['Alice', 'Bob'], ('ARES',), skip=('RECEIPT_KNOWN',))))
    # futures trace (rising) - full ledger steps
    w, tr, sn = traces.run_traced([(futures, dict(path='rising'))], ['Alice', 'Cara'], (), until_h=340)
    rows_f = traces.rows_for(w, tr, sn, ['Alice', 'Cara'], (), skip=('RECEIPT_KNOWN',))
    # observations: keep the exchange's recording rows, drop Bob's matching publication rows
    rows_f = [r for r in rows_f if not str(r[3]).startswith('Publishes observation')]
    out.append('<h3>S1d full trace: capped futures, rising path (Alice long, Cara short, Q = 2,000)</h3>')
    out.append(traces.html_table(rows_f))
    t = S1['S1e']['times']
    fx = S1['S1e']['contracts']
    fxr = next(iter(fx.values()))['fixing']
    out.append(f'''<p><b>S1e (falling)</b> is step-for-step identical to S1d until the first observation, as the margin
rule requires: same opening ({h(t['F1:open'], 4)} h), same packets. Observations 90, 80, 70, 65, 75; fixing at
{fxr['P']} gives long net {money(fxr['net_long'])}, so the gross allocations swap: Alice $30,000, Cara $130,000.
Final home cash Alice $100,000 / Cara $150,000. Payout spendable: Cara {h(t['F1:Cara:payout_spendable'], 3)} h,
Alice {h(t['F1:Alice:payout_spendable'], 3)} h.</p>''')
    # compact traces for the others
    def kt(key, items):
        tt = S1[key]['times']
        return ', '.join(f"{lab} {h(tt[k], 3)}" for k, lab in items if k in tt)
    rows = [
        ['S1b', kt('S1b', [('EQB:funding_imported_at_host', 'funds at Ceres'), ('EQB:funding_receipt_at_home', 'receipt known'),
                           ('EQB:first_fill', 'fill'), ('EQB:seller_spendable', 'Cara spendable'), ('EQB:buyer_spendable', 'Belt home')])
         + '. Same structure as S1a, Earth–A–Ceres; no Mars involvement.'],
        ['S1c', kt('S1c', [('EQT:funding_imported_at_host', 'funds at Earth'), ('EQT:funding_receipt_at_home', 'receipt at Uranus'),
                           ('EQT:first_fill', 'fill'), ('EQT:seller_spendable', 'Fin spendable'), ('EQT:buyer_spendable', 'Terra at Uranus')])
         + '. Eve sends 8 copies Uranus→Earth (p(loss) 0.78 each).'],
        ['S1f', 'As S1d with $100k margin each: open 2.502, payouts spendable 328.03 / 328.17; Alice ends $212,500, Cara $37,500.'],
        ['S1i', 'Alice funds $10k at Mars; batched direct packet carries BUY 40 @ $100 (o1) and BUY 20 @ $100 (o2): o1 fills 10 @ $97 '
                '(price improvement $30 refunded at once) and 5 @ $100; o2 cancelled at +6 h releasing $2,000; she sells 10 @ $101 to Bob at +12 h; '
                'at +24 h her cancel of o1 races Bob\'s IOC sell: the earlier arrival fills 5 @ $100, the cancel then releases only the remainder. '
                f"Final sweep: cash and Ares home, done {h(S1['S1i']['completion_h'])} h, {S1['S1i']['total_packets']} packets for "
                f"{S1['S1i']['transactions']} transactions."],
    ]
    out.append('<h3>Key steps of the other scenarios (hours)</h3>')
    out.append(table(['', 'Steps'], rows, cls='compact'))
    return '\n'.join(out)


# ====================================================================== E2
def e2():
    dp = E2['direct']
    rows = []
    for key in ('S1a', 'S1c', 'S1d', 'S1i'):
        seen = set()
        for r in dp[key]:
            k = (r['principal'], r['a'], r['b'], r['label'])
            if k in seen:
                continue
            seen.add(k)
            rows.append([key, r['principal'], f"{SH(r['a'])}→{SH(r['b'])}", r['label'], r['copies'],
                         f"{r['p_loss_each'][0]:.4f}", f"{r['p_all_lost']:.2e}", f"{r['p_success']:.5f}"])
    fallback = {'ORDER': 'resend same ID at +2(direct+bb)+6 h', 'CINSTR': 'resend at +2·direct+6 h until deadline',
                'REPORT': 'none needed (status only)', 'BATCH': 'resend batch (same IDs)', 'WITHDRAW': 'resend same request ID'}
    for r in rows:
        r.append(fallback.get(r[3], 'resend same ID'))
    hop = []
    for key in ('S1a',):
        for r in E2[key]['analytic']:
            hop.append([r['record'].replace('ND', '$').replace('->', '→'), f"{SH(r['a'])}→{SH(r['b'])}", h(r['te_h'], 3),
                        f"{r['d']:.3f}", f"{r['p_launch']:.4f}", f"{r['p_unconfirmed']:.4f}", f"{r['p_abandon']:.1e}",
                        f"{r['p_never_crosses']:.1e}"])
    mc = []
    for key in ('S1a', 'S1b', 'S1c', 'S1d', 'S1e'):
        m = E2[key]
        mc.append([key, f"{m['completed']:,}/{m['n']:,}", h(S1[key]['completion_h']), h(m['p50']), h(m['p90']), h(m['p99']),
                   h(m['max']), f"{m['mean_bb']:.1f} + {m['mean_direct']:.1f}", m['max_quota_inst'], m['max_direct_peak'],
                   m['resubmit_runs'] + 0, m['fallback_runs']])
    return f'''<h2>E2. Probability and traffic</h2>
<p><b>Direct service (exact).</b> Each copy is lost independently with p = 1 − e^(−0.08 d) at its own geometry; copies
60 s apart do not share a closure (we check the path is open for every copy) and incidents are excluded from these
figures. P(all lost) = ∏ pᵢ. A lost order is <i>not</i> a financial failure: the client's cash simply stays
available at the host until the fallback copy arrives.</p>
{table(['Run', 'Sender', 'Path', 'What', 'Copies', 'p each', 'P(all lost)', 'P(≥1 arrives)', 'If none arrives'], rows,
           cls='compact', num=(4, 5, 6, 7))}
<p><b>Backbone (approximate, per launch geometry).</b> For each hop of the S1a records: p of the data launch,
p(unconfirmed) = 1 − (1 − p_data)(1 − p_receipt), hop abandonment after four launches ≈ p(unconfirmed)⁴ (geometry held
at the first launch; the true value differs in the 4th significant figure), and the chance the data never crosses,
p_data⁴. An abandoned hop triggers endpoint retries and then application resubmission of the same transfer ID; the
money stays in transit, owned by the client, until the import. No financial state changes.</p>
{table(['Record', 'Hop', 'launch h', 'd (AU)', 'p launch', 'p unconfirmed', 'P(abandon)', 'P(never crosses)'], hop,
           cls='compact', num=(2, 3, 4, 5, 6, 7))}
<p><b>Lossy Monte Carlo</b> (independent seeds, every launch drawn with the brief's law, our declared client policy).
Mean packets are backbone + direct. Quota columns are the worst rolling-24 h use seen in any run: backbone
originations by one exchange (limit 66) and direct packets by one principal (limit 12).</p>
{table(['Run', 'Done', 'no-loss', 'median', 'p90', 'p99', 'max', 'mean pkts', 'bb quota', 'direct quota', 'resubmit runs', 'fallback runs'],
           mc, cls='compact', num=(2, 3, 4, 5, 6, 7, 8, 9, 10, 11))}
{fig('cdf', 'Figure A1. Probability of completion by time t under random loss (2,000 runs each).')}
<p><b>Futures opening.</b> The contract opened in {pct(E2['S1d']['p_open'], 2)} of lossy runs (median {h(E2['S1d']['open_p50'])} h,
p99 {h(E2['S1d']['open_p99'])} h), far inside the 168 h deadline. <b>Link capacity.</b> The longest FIFO queue on any
directed link in any S1 run was {max(S1[k]['max_queue'] for k in S1)} packets (limit 10,000); serialization never
delayed a packet by more than a few seconds.</p>'''


# ====================================================================== E3
def e3():
    rows = []
    for k in ('S1a', 'S1b', 'S1c', 'S1d', 'S1e', 'S1g', 'S1i'):
        bal = S1[k]['balances']
        parts = []
        for s, owner, d in bal:
            txt = ', '.join((money(v) if a == 'ND' else f"{v:,} {a.title()}") for a, v in d.items() if v)
            parts.append(f"{owner}@{s}: {txt}")
        rows.append([k, '; '.join(parts)])
    d = S1['S1d']
    return f'''<h2>E3. Balances and capital</h2>
<p><b>Conservation check.</b> After every ledger event the simulator asserts, per asset: opening supply = Σ available
+ Σ order holds + Σ contract holds + Σ escrow + Σ unique exports not yet imported; every balance ≥ 0; every buy hold =
remaining × limit; and, per registry, custody[s] = shares held at s + inbound + outbound in transit. No run ever failed
a check. The futures figure in the design paper (Figure 3) plots balances over time; the table below gives every
account's final position.</p>
{table(['Run', 'Final balances (owner@location; anything not listed is zero)'], rows, cls='compact')}
<p><b>Ledger of the futures at its peak</b> (S1d, h 2.502 to 326.502). Every dollar has one owner, one location and
one use.</p>
{table(['Asset lot', 'Owner', 'Location', 'Liability it backs', 'Encumbrance'], [
        ['$80,000', 'Alice', 'Mars', 'Max loss of the long (Q × 40)', 'Contract escrow, released only by fixing'],
        ['$80,000', 'Cara', 'Mars', 'Max loss of the short', 'Contract escrow'],
        ['$70,000', 'Alice', 'Earth', '—', 'Free'], ['$20,000', 'Cara', 'Ceres', '—', 'Free'],
        ['$50,000; 3,000 Ares', 'Bob', 'Mars', '—', 'Free'], ['$100,000', 'Dax', 'Neptune', '—', 'Free'],
        ['$50,000', 'Eve', 'Uranus', '—', 'Free'], ['$50,000; 1,000 Terra', 'Fin', 'Earth', '—', 'Free'],
        ['1,000 Belt', 'Cara', 'Ceres', '—', 'Free'],
    ], cls='compact')}
<p>Spendable, backed-claim and discharge moments for every settled position (no loss):</p>
{table(['Position', 'Discharge (obligation ends)', 'Backed claim (funded export exists)', 'Spendable at home'], [
        ['S1a Alice shares', 'fill 2.502', 'fill 2.502', h(S1['S1a']['times']['EQ:buyer_spendable'], 3)],
        ['S1a Bob cash', 'fill 2.502', '— (local)', h(S1['S1a']['times']['EQ:seller_spendable'], 3)],
        ['S1d/e payouts', h(d['times']['F1:discharge'], 3), h(d['times']['F1:backed_claim'], 3),
         f"Cara {h(d['times']['F1:Cara:payout_spendable'], 3)}, Alice {h(d['times']['F1:Alice:payout_spendable'], 3)}"],
    ], cls='compact')}'''


# ====================================================================== S2
def s2():
    if not S2D:
        return '<h2>S2. Stress and recovery</h2><p>(pending)</p>'
    inc = S2D['incident']
    R = S2D['runs']
    # search summary: worst start per (kind,node), both paths
    best = {}
    for path, S in (('rising', S2R), ('falling', S2F)):
        for r in S['runs']:
            k = (r['kind'], r['node'])
            if k not in best or r['damage'] > best[k]['damage']:
                best[k] = dict(r, path=path)
    top = sorted(best.values(), key=lambda r: -r['damage'])[:8]
    trows = [[r['kind'].replace('_', ' '), r['node'], f"{r['start']:g}", h(r['opened']), h(r['comp']), f"+{r['damage']:.1f}"]
             for r in top]

    def rr(key):
        x = R[key]
        t = x['times']
        return [h(t.get('F1:open')), h(x['completion']), x['packets'], x['originations']]
    vrows = []
    for path in ('rising', 'falling'):
        for name, lab in (('baseline_no_incident', 'no incident'), ('incident', 'incident (baseline design)'),
                          ('incident_no_maintenance', 'incident, maintenance removed'),
                          ('no_incident_no_maintenance', 'no incident, maintenance removed'),
                          ('incident_restart_notice', 'incident + alternative A1: restart notice'),
                          ('incident_immediate_recovery', 'incident + sensitivity: no backoff')):
            if f'{path}:{name}' in R:
                vrows.append([path, lab, *rr(f'{path}:{name}')])
    mcrows = [[k.replace('mc:', ''), f"{v['completed']}/{v['n']}", h(v['p50']), h(v['p90']), h(v['p99']), pct(v['p_open'], 1),
               f"{v['mean_total']:.0f}"] for k, v in R.items() if k.startswith('mc:')]
    ev = [e for e in R['rising:incident']['courier_events'] if e[2] in ('SESSION_OPEN', 'DELIVERY_UNKNOWN', 'APP_RESUBMIT_SCHEDULED',
                                                                         'APP_RESUBMIT', 'SESSION_FAILED', 'RESET_RESEND')]
    evtxt = '; '.join(f"h {e[0] / 3600:.2f} {e[1]} {e[2].lower().replace('_', ' ')} → {e[3]}" for e in ev[:9])
    n_runs = S2R['n'] + S2F['n']
    return f'''<h2>S2. Stress and recovery</h2>
<p><b>How we chose the incident.</b> We ran the futures scenario (both price paths) under every allowed incident on
a grid: 72 h isolation of each settlement starting every hour, 6 h forced loss at each of the 11 nodes every 0.5 h,
and an endpoint reset of each exchange every 0.25 h, all starting between h 0 and 420: {n_runs:,} runs. Damage = extra
hours until both payouts are spendable (+10⁶ if the contract never opens). The worst start time for each kind and
node:</p>
{table(['Incident', 'Node', 'Start h', 'Opened h', 'Done h', 'Damage h'], trows, cls='compact', num=(2, 3, 4, 5))}
<p><b>Chosen: endpoint reset of the Mars exchange at h {inc['start']:g}</b>, the worst in both paths. It is not the
obvious "isolate the host at payout time" (which costs about 75 h) but a short, silent event. At h 0.75 Mars has
just answered Alice's and Cara's handshakes; the reset wipes its session state, but its SYN-ACKs are already in flight.
Earth and Ceres therefore believe the sessions are up and send their funding transfers into sessions Mars no longer
knows: Mars ignores them, as the brief requires. The senders learn nothing until four endpoint attempts of
R_e ≈ 25 h have expired, then wait the 24 h application backoff, then resubmit. Courier log (rising): {evtxt}.</p>
<p><b>State of every obligation during the incident.</b> Alice's and Cara's $80,000 are debited at home and
"in transit", owned by them, unspendable anywhere, for about 125 h: no contract exists, so nobody owes anyone
anything, and neither margin can be lost. Bob's shares and all other accounts are untouched. Local service at Mars never
stopped: the reset only lost transport state. <b>Recovery</b> (financial service resumed, not just a packet): the
transfers import at Mars, both margins are held, and the contract opens at h {h(R['rising:incident']['times'].get('F1:open'))},
inside the 168 h deadline, so the trade still happens with the full 300 h term and both payouts arrive home.</p>
{table(['Path', 'Variant', 'Opened h', 'Done h', 'Packets', 'Originations'], vrows, cls='compact', num=(2, 3, 4, 5))}
{fig('s2_search', 'Figure A2. Extra hours to completion (rising path; capped at 200) by incident start. Grey: other nodes. Isolation and forced loss matter only around opening (h 0–3) and the payout window (h 255–330); a reset matters only when it lands between a handshake and the first data.')}
<p><b>Maintenance comparison.</b> Removing the two scheduled maintenance windows changes nothing for this incident:
neither B–Neptune [2, 26) nor B–Ceres [240, 264) lies on the Earth–A–Mars or Ceres–A–Mars routes the runs use. Natural
geometry alone sets the timing. <b>Alternative A1 (one design change, same funding and guarantees):</b> after a
reset an exchange sends a RESTART notice (one 64-byte backbone record, counted against its quota) to every peer it has
had a session with in the last 7 days; a peer receiving it abandons its old sessions with that exchange and resubmits
unacknowledged records immediately. The contract now opens at h {h(R['rising:incident_restart_notice']['times'].get('F1:open'))}
instead of {h(R['rising:incident']['times'].get('F1:open'))}, with fewer packets. Removing the backoff alone (sensitivity)
saves only the 24 h. We recommend adopting A1. Lossy Monte Carlo with the incident (1,000 runs each):</p>
{table(['Variant', 'Done', 'median h', 'p90 h', 'p99 h', 'P(open)', 'mean pkts'], mcrows, cls='compact', num=(2, 3, 4, 5, 6))}'''


# ====================================================================== S3
def s3():
    rel = S3['relocations']
    rows = []
    t0 = {r['settlement']: r for r in S3['table'] if r['hour'] == 0}
    t3 = {r['settlement']: r for r in S3['table'] if r['hour'] == 300}
    xd = X['s3_direct']
    for s in t0:
        def cell(T, host):
            c = T[s][host]
            if c['route'] == 'local':
                return 'local'
            return f"{c['route']} {c['delay']:.1f}/{c['back']:.1f} {pct(min(c['avail'], c['back_avail']), 0)}"

        def dcell(hh, host):
            if s == host:
                return 'local'
            d = xd[f'{s}|{host}|{hh}']
            return f"{d['delay']:.0f}m {pct(d['avail'], 0)} ×{d['copies']}"
        rows.append([s, cell(t0, 'Mars'), cell(t3, 'Mars'), cell(t0, 'Ceres'), cell(t0, 'Earth'),
                     dcell(0, 'Mars'), dcell(300, 'Mars'), dcell(0, 'Ceres'), dcell(0, 'Earth')])
    rk = sorted(((v['completion_h'], k) for k, v in rel.items()))
    rel_rows = [[k, h(v['completion_h']), v['packets'], h(v['mc_p50']), h(v['mc_p90']), h(v['mc_p99']),
                 f"{v['p_by_24h']:.2f}", f"{v['p_by_72h']:.2f}", f"{v['p_by_168h']:.2f}", f"{v['mc_packets']:.0f}"]
                for _, k in rk for v in [rel[k]]]
    best, med, worst = rk[0][1], rk[4][1], rk[-1][1]

    def steps(k):
        t = rel[k]['times']
        lab = [('EQ:funding_imported_at_host', 'funds at Mars'), ('EQ:funding_receipt_at_home', 'receipt home'),
               ('EQ:order_sent', 'order sent'), ('EQ:first_fill', 'fill'), ('EQ:seller_spendable', 'Bob paid'),
               ('EQ:buyer_spendable', 'shares home')]
        return ', '.join(f"{l} {h(t[x], 3)}" for x, l in lab if x in t)
    of = load('outer_futures') or {}
    ofr = [[k.replace('|', ' / '), h(v['noloss_open']), h(v['noloss_comp']), pct(v['p_open'], 1), h(v['open_p50']), h(v['comp_p50'])]
           for k, v in of.items() if 'baseline' in k]
    return f'''<h2>S3. Access at every settlement</h2>
<p>Transaction types: <b>funding / withdrawal / payout</b> (backbone, to the host exchange and back) and <b>orders /
contract instructions</b> (direct from the client to the host). Backbone cells: best route, one-way delay
there/back in minutes, and availability = fraction of the 24 h from that hour in which every link can launch (1-min
samples, maintenance applied). Direct cells: delay, 24 h availability and the copies our policy sends. Hosts: Mars
(Ares + futures), Ceres (Belt), Earth (Terra).</p>
{table(['From', 'Mars bb h0', 'Mars bb h300', 'Ceres bb h0', 'Earth bb h0', 'dir→Mars h0', 'dir→Mars h300', 'dir→Ceres', 'dir→Earth'],
           rows, cls='compact')}
<p>Ceres and Earth backbone cells at h 300 differ from h 0 by under 2 min (all routes 100% available); the only
availability change in the whole table is Mercury's direct path to Mars, open 95% of the first day and shut for the
whole of day 300 (closed h 22.5–357). <b>Relocation timelines.</b> Same client (a $100k Ares purchase with home delivery
from a comparable funded account) re-run from reset with its home moved to each settlement, ranked by no-loss
completion. Best <b>{best}</b>: {steps(best)}. Median <b>{med}</b>: {steps(med)}. Worst <b>{worst}</b>: {steps(worst)}.</p>
{table(['Home', 'no-loss h', 'pkts', 'median', 'p90', 'p99', 'P≤24h', 'P≤72h', 'P≤168h', 'mean pkts'], rel_rows,
           cls='compact', num=(1, 2, 3, 4, 5, 6, 7, 8, 9))}
<p><b>Outer settlements in the futures</b> (300 lossy runs each; Dax at Neptune or Eve at Uranus is long against Cara;
Eve's position is Q = 1,250 to fit her $50k):</p>
{table(['Long party', 'no-loss open h', 'no-loss done h', 'P(open by 168 h)', 'median open h', 'median done h'], ofr,
           cls='compact', num=(1, 2, 3, 4, 5))}'''


# ====================================================================== E4
def e4():
    if not E4:
        return '<h2>E4. Long-horizon scan</h2><p>(pending)</p>'
    bb = E4['backbone']
    dr = E4['direct']
    ro = E4['routes']
    closed_links = sorted(((v['n_closures'], k) for k, v in bb.items()), reverse=True)
    bbrows = []
    for s in ('Mercury', 'Venus', 'Earth', 'Mars', 'Ceres', 'Jupiter', 'Saturn', 'Uranus', 'Neptune'):
        cells = [s]
        for r in ('Relay A', 'Relay B'):
            v = bb[f'{s}->{r}']
            cells.append(f"{pct(1 - v['closed_fraction'], 2)} · {v['n_closures']} · {v['max_closure_h']:.0f} h")
        for host in ('Mars', 'Ceres', 'Earth'):
            if s == host:
                cells.append('local')
                continue
            v = ro[f'{s}->{host}']
            cells.append(f"{v['min_min']:.0f}–{v['p50_min']:.0f}–{v['max_min']:.0f}")
        dm = dr.get(f'{s}->Mars')
        cells.append('local' if s == 'Mars' else f"{pct(1 - dm['closed_fraction'], 1)} · {dm['max_closure_h'] / 24:.0f} d")
        bbrows.append(cells)
    worst_route = max(ro.items(), key=lambda kv: kv[1]['max_min'])
    worst_direct = max(dr.items(), key=lambda kv: kv[1]['max_closure_h'])
    ab = bb.get('Relay A->Relay B', {})
    ex = E4.get('refined_example')
    if not ex:
        import e4_scan
        s0, e0 = bb['Earth->Relay A']['closures'][0]
        lo = math.floor(s0 / 3600) * 3600.0
        a_, b_ = e4_scan.bisect('Earth', 'Relay A', lo, lo + 3600.0, True)
        ex = dict(path='Earth → Relay A, first closure', lo=lo, hi=lo + 3600.0, a=a_, b=b_)
    exs = ''
    if ex:
        exs = (f"<p><b>Refined boundary (Tier 2).</b> {ex['path']}: hourly bracket [{ex['lo']:.0f}, {ex['hi']:.0f}] s, bisected on "
               f"the exact light-time solver to [{ex['a']:.6f}, {ex['b']:.6f}] s (width {1e3 * (ex['b'] - ex['a']):.3f} ms, tolerance 1 ms). "
               f"A packet emitted before the boundary flies on its own path and is unaffected; one emitted after it is "
               f"never launched by our queue (the link waits), so no packet in flight is lost by a closure: the closure only "
               f"delays the next launch, and the hop timer R_h is restarted at the actual emission.</p>")
    return f'''<h2>E4. Long-horizon scan — claiming Tier 3</h2>
<p><b>Scan.</b> {E4['years']} Julian years from the epoch at a 1 h step ({E4['samples']:,} epochs) for all 38 directed
backbone links and all 72 directed direct paths, moving-receiver clearance at each sample, maintenance not repeated.
Runtime {E4['runtime_s'] / 60:.0f} min on 20 cores. <b>Shortest closure we could miss:</b> clearance is the Sun's distance to the segment sender(t_e)→receiver(t_a), which
changes no faster than the fastest endpoint plus the arrival shift: L ≤ {E4['lipschitz_AU_per_h']} AU/h (Mercury at
perihelion, 58.98 km/s). A closure entirely between two samples would leave a sample below 0.10 + L = {E4['guard_AU']:.5f}
AU. Every sample below that guard is re-examined on a 10 s grid and every open/closed change is bisected to 1 ms, so no
closure of any length is missed. <b>Routes:</b> best-route delay from every settlement to each market host and back, at
6 h steps, sequential flights.</p>
{exs}
<p>Backbone: Relay A–B never closes (min clearance {ab.get('min_clearance', 2):.2f} AU). Gateway links: availability · number of
closures in 200 y · longest closure. Routes: one-way minutes min–median–max over 200 y. Direct to Mars: availability ·
longest closure.</p>
{table(['From', 'to A', 'to B', '→Mars min', '→Ceres min', '→Earth min', 'Direct→Mars'], bbrows, cls='compact')}
<p><b>Every settlement had a route to every host at every sample</b> (connected fraction 1.000 for all
{len(ro)} directed settlement–host pairs), as the geometric argument in the design paper predicts. <b>Poorest service:</b>
the longest one-way route is {worst_route[0].replace('->', ' → ')} at {worst_route[1]['max_min']:.0f} min (h {worst_route[1]['t_max_h']:,.0f});
the longest direct closure is {worst_direct[0].replace('->', ' → ')} at {worst_direct[1]['max_closure_h'] / 24:.1f} days. Direct paths are the
weak link: their closures are what our access check, deferral and option O2 exist for.</p>'''


# ====================================================================== E5
def e5():
    R = E5['rows']
    rt = X['e5_routes']
    rows = []
    for ep in ('+1 year', '+10 years', '+100 years', 'Mars conjunction'):
        r = {x['a'] + x['b']: x for x in rt[ep]['rows']}
        em = r['EarthMars']
        cm = r['CeresMars']
        rinfo = (f"Ea–Ma {em['route']} {em['delay']:.0f}′ {pct(em['avail'], 0)}, direct {em['direct_delay']:.0f}′ "
                 f"{pct(em['direct_avail'], 0)}; Ce–Ma {cm['route']} {cm['delay']:.0f}′, direct {pct(cm['direct_avail'], 0)}")
        cells = [ep, f"{rt[ep]['t0_h']:,.0f}", rinfo]
        for sc in ('S1a', 'S1d'):
            b = R[f'{ep}|{sc}']
            o2 = R[f'{ep}, option O2|{sc}']
            nb = b['noloss']['comp']
            cells.append((h(nb) if nb else ('suspended' if b['noloss']['suspended'] else 'deferred')) +
                         f" ({h(b['mc']['p50'])})" + (f" · O2 {h(o2['noloss']['comp'])}" if o2['noloss']['comp'] != nb else ''))
        rows.append(cells)
    d = E5['difficult']
    return f'''<h2>E5. Shifted epochs — claiming Tier 3</h2>
<p>Each run starts at t = k × 365.25 d with every orbit advanced from the epoch, balances reset to the opening book,
maintenance and the S2 incident not replayed, and observation/maturity times shifted with the start. Cells:
no-loss completion h (median of 300 lossy runs); "· O2" shows the result with option O2 where it differs. S1d and S1e
give identical times at every epoch (the margin rule is symmetric; only the payout split differs), so S1e is listed
in the JSON results only.</p>
{table(['Epoch', 't₀ (h)', 'Routes used (one-way min, 24 h availability)', 'S1a equity', 'S1d/S1e futures'], rows, cls='compact')}
<p><b>Difficult epoch (Tier 2–3).</b> We chose the first Mars solar conjunction after the epoch: the Earth→Mars direct
path closes at h {d['close_h']:,.1f} and reopens at h {d['reopen_h']:,.0f} (53 days); we start 24 h after closure. This is
harder than any backbone event because client instructions cannot use the backbone. <b>Baseline:</b> Alice's client
sees from the published geometry that no long-enough direct window exists, so it never funds Mars (equity deferred;
Bob's 30-day sell order expires first, so no trade happens); in the futures Alice suspends at h 0 and Cara, who did fund,
gets her margin back at the 168 h deadline and withdraws it home. <b>Funded consequences:</b> nobody loses anything;
Cara's $80,000 is locked for 168 h and returned by h {h(R['Mars conjunction|S1d']['noloss']['times'].get('F1:Cara:returned_home'))}.
Both price directions behave identically because suspension happens before any observation. <b>With option O2</b> the
instructions travel Earth→Mercury→Mars and both price runs complete normally.</p>'''
