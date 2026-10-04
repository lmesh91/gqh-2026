"""Evidence appendix: E1, F, S1, T, E2, E2+, E3, E3+, S2, S3, E4, E5, E6.  The sections added for the second review
live in supp_text.py; build() decides which of them go in."""
from build import *
import supp_text as SX
from geom import SHORT
import math


def T(s, env):
    return fill(s, {**globals(), **env})


def SH(n):
    return {'Relay A': 'A', 'Relay B': 'B'}.get(n, n)


def build():
    o = [r'''
\linespread{0.95}\selectfont
\renewcommand{\thetable}{A\arabic{table}}\renewcommand{\thefigure}{A\arabic{figure}}
\section*{Introduction}
All results come from one discrete-event simulator that implements the brief's network in full (moving-receiver
light time, solar exclusion, links, queues, timers, sessions, quotas, maintenance, incidents and random loss) and the
ledgers of design v3. In every traced run it checks conservation, non-negative balances, hold arithmetic and registry
custody after every ledger event.

A trace is a single run \emph{without packet loss} unless it is labelled ``lossy''. Times are in hours after the
start of the scenario, and the epoch is 2026-09-22 00:00 TDB. For every probability we state whether it is exact or
an approximation.
''', e1(), SX.formats(), s1(), SX.s1_traces(), e2(), SX.e2_complete(), e3(), SX.e3_complete(), s2(), SX.s2_trace(),
         s3(), SX.s3_products(), SX.s3_traces(s3_picks()), e4(), e5(), SX.e5_legs(), SX.e6(), SX.e7()]
    return document('Evidence Appendix', r'MultiPlanetary Exchange System \quad$\cdot$\quad Milestone 2 \quad$\cdot$\quad Design v3',
                    '\n'.join(o), size='10pt')


# ====================================================================== E1
def e1():
    ep = E1['epoch']
    rows = [[r['body'], f"{r['x']:+.6f}", f"{r['y']:+.6f}", f"{r['z']:+.6f}", f"{r['err']:.1e}"] for r in ep]
    later = {}
    for r in E1['later']:
        later.setdefault(r['body'], {})[r['hour']] = r
    lrows = [[b, *(f"({v['x']:+.4f}, {v['y']:+.4f}, {v['z']:+.4f})" for v in (later[b][300], later[b][8766.0]))]
             for b in later if b in ('Earth', 'Mars', 'Ceres', 'Neptune', 'Relay A', 'Relay B')]
    ex = E1['examples']
    xr = [[f"{SH(r['a'])}→{SH(r['b'])}", f"{r['te']:.3f}", f"{r['flight']:.6f}", f"{r['frozen']:.6f}",
           f"{r['diff_ms']:+.3f}", f"{r['d']:.4f}", f"{r['clearance']:.3f}"] for r in ex]
    worst = max(r['err'] for r in ep)
    tsent = 'On the S1 routes: ' + '; '.join(
        f"{t['path']} at hour {t['t']:.4f}: $T_0$ = {t['T0_min']:.2f} min, $R_e$ = {t['Re_h']:.2f} h, $R_h$ = "
        + ' and '.join(f'{x:.1f}' for x in t['Rh_min']) + ' min' for t in E1['timers']) + '.'
    tsent = Raw(tsent)
    iters = ', '.join(f'{x:.1e}' for x in E1['iterations_Earth_A'][:3])
    t1 = table('lRRRR', ['Body', 'x (AU)', 'y (AU)', 'z (AU)', 'Error (AU)'], rows,
               'Positions at the epoch and their difference from the table in the brief.', 'tab:e1pos')
    t2 = table('lLL', ['Body', 'Hour 300 (x, y, z) in AU', 'Hour 8,766 (x, y, z) in AU'], lrows,
               'Positions computed by the same code at hour 300 and after one Julian year, for the bodies used in S1.', 'tab:e1later')
    t3 = table('lRRRRRR', ['Path', 'Emitted (s)', 'Flight (s)', 'Frozen (s)', 'Difference (ms)', 'Distance (AU)',
                           'Clearance (AU)'], xr,
               "Flight times on the S1a routes with a moving receiver, compared with the ``frozen'' time that uses both "
               'positions at emission. The first four rows are the S1a funding and share delivery at their actual launch '
               'times; the last four are illustrative emissions at the epoch.', 'tab:e1flight')
    return T(r'''
\section*{E1. Orbital calculations}
\paragraph{Method.} Each body follows the fixed Kepler ellipse given in \texttt{data.zip}. The mean anomaly is
$M = M_0 + nt$, where $n$ is the supplied mean motion. We solve Kepler's equation by Newton iteration until the residual
is below $10^{-15}$ rad, and then rotate by $\omega$, $i$ and $\Omega$ into the heliocentric J2000 ecliptic frame. Units
are AU and seconds of TDB since the epoch; tables give times in hours. The relays use the same code with $e = 0$ and
the supplied phases. The largest difference from the brief's table of epoch positions is <<f"{worst:.1e}">>~AU, which
is the rounding of the table (Table~\ref{tab:e1pos}). Table~\ref{tab:e1later} gives later positions. As the brief
asks, every body and relay returns to its starting point after one orbital period to within
<<f"{max(c['ret'] for c in E1['orbit_checks']):.0e}">>~AU, and over 200,001 samples per orbit its distance from the Sun
stays within $[a(1 - e), a(1 + e)]$ to within <<f"{max(max(c['below'], c['above']) for c in E1['orbit_checks']):.0e}">>~AU,
the floating-point rounding.

\paragraph{Light time.} A packet emitted at time $t_e$ from body $P$ reaches body $Q$ at the time $t_a$ that solves
$t_a = t_e + 499.02\,|Q(t_a) - P(t_e)|$, where 499.02 is the light time in seconds per AU. We solve this by fixed-point
iteration. For the Earth to Relay A link the successive corrections are <<iters>> seconds. Each step is smaller than
the previous one by a factor of about $v/c \approx 10^{-4}$, so two iterations reach 1~ms. We always iterate to
$10^{-6}$~s.

\paragraph{Solar exclusion.} A launch is blocked if the line segment from $P(t_e)$ to $Q(t_a)$ passes within 0.10~AU of
the Sun. Every launch, ACK and receipt is checked at its own emission time.

<<Raw(t1)>>
<<Raw(t2)>>

\paragraph{Effect of receiver motion.} Table~\ref{tab:e1flight} shows the S1a funding route (Earth to Relay A to
Mars) and the return route for the shares (Mars to Relay A to Earth) at their actual emission times in the S1a run:
hour <<h(E1['s1a_launch_h']['funding'], 4)>> for the funding, after the session handshake, and hour
<<h(E1['s1a_launch_h']['delivery'], 4)>> for the shares, just after the fill. Each relay sends
the packet on 2~s after it arrives (1~s of processing and 1~s of serialization). The ``frozen'' column uses the
positions of both ends at the emission time. The forward and return legs are not mirror images. On the Earth to Relay~A
leg the flight is <<f"{ex[0]['diff_ms']:+.1f}">>~ms longer than the frozen value because Relay~A moves away during the
flight.

<<Raw(t3)>>

\paragraph{Timers.} $T_0$ is the route time with empty queues. The endpoint timer is $R_e = 2T_0 + 24$~h and the hop
timer is $R_h = 2 \times \text{flight} + 60$~min. <<tsent>>
''', locals())


# ====================================================================== S1
TRACE_COLS = ''.join(r'>{\raggedright\arraybackslash}p{' + w + '}'
                     for w in ('0.55in', '0.6in', '0.72in', '1.05in', '1.05in', '0.55in', '1.45in'))


def trace_rows(rows):
    """traces.rows_for writes the state column as HTML (<b>, <br>); convert it to LaTeX."""
    out = []
    for r in rows:
        st = esc(r[-1]).replace('<b>', r'\textbf{').replace('</b>', '}').replace('<br>', '; ')
        out.append([*r[:-1], Raw(st)])
    return out
TRACE_HEAD = ['h', 'Actor', 'Knows', 'Does', 'Packet or transmission', 'Arrives', 'Financial state after']


def s1():
    import traces
    from scenarios import equity, futures
    names = [('S1a', 'Earth buys Ares'), ('S1b', 'Earth buys Belt'), ('S1c', 'Uranus buys Terra'),
             ('S1d', 'Futures, rising'), ('S1e', 'Futures, falling'), ('S1f', 'Futures, Q = 2,500'),
             ('S1g', 'Futures, Q = 2,501'), ('S1h', 'Futures, Q = 4,000'), ('S1i', 'Repeat trading')]
    import csv
    TR = HERE.parent / 'traces'
    kinds = ['SYN', 'SYNACK', 'ACK', 'DATA', 'DACK', 'RCPT']
    expo = {'S1a': '$0', 'S1b': '$0', 'S1c': '$0', 'S1d': '$80k', 'S1e': '$80k', 'S1f': '$100k',
            'S1g': '$0', 'S1h': '$0', 'S1i': '$0'}

    def kk(v):
        return f"{v / 1000:,.1f}k".replace('.0k', 'k') if v >= 1000 else f"{v:,.0f}"
    rows, crows = [], []
    for k, title in names:
        r = S1[k]
        c = r['capital']
        cnt = {x: 0 for x in kinds + ['direct']}
        with (TR / f'{k}_launches.csv').open() as f:
            for x in csv.DictReader(f):
                cnt['direct' if x['layer'] == 'direct' else x['kind']] += 1
        assert sum(cnt.values()) == r['total_packets'], k
        rows.append([k, h(r['completion_h']), *(cnt[x] for x in kinds), r['backbone_total'], r['direct'],
                     r['total_packets'], r['n_tx'], h(r['comm_eff_brief'], 1)])
        enc = '; '.join((f"${kk(x['peak_encumbered'])}" if a == 'ND' else f"{x['peak_encumbered']:,} {a.title()}")
                        + f" / {kk(x['enc_hours'])}" for a, x in c.items() if x['peak_encumbered'])
        crows.append([f'{k} ' + title.replace('Futures, ', ''), money(r['value_settled_brief']), enc or '—', pct(r['utilisation'], 0),
                      h(r['cap_eff_brief'], 2), expo[k]])
    tsum = table('lrrrrrrrrrrrr', ['', 'Done (h)', 'SYN', 'S-ACK', 'ACK', 'DATA', 'DACK', 'RCPT', 'Backbone', 'Direct',
                                   'Total', 'Tx', 'Pkts/tx'], rows,
                 'Completion and every packet of the S1 runs without loss, by type: session handshakes (SYN, SYN-ACK, '
                 'ACK), record launches (DATA), endpoint acknowledgements (DACK), hop receipts (RCPT) and direct copies. '
                 'Tx counts completed transactions as defined in the text.', 'tab:s1sum', sep='2.4pt')
    tcap = table('Lrlrrl', ['Scenario', 'Value settled', 'Peak enc. / asset-h', 'Util.', 'Cap. eff.',
                             'Exp./side'], crows,
                 'Capital measures (Section 7 of the brief). Asset-hours are in thousands (k). Capital efficiency is '
                 'peak encumbered cash divided by value settled. Exp./side is each side\'s largest possible loss; S1g and S1h never open.', 'tab:s1cap', sep='3pt')
    from evidence import SCEN
    cust = []
    for k in ('S1a', 'S1b', 'S1c'):
        kw = SCEN[k]['spec'][0][1]
        qty, price, asset = kw.get('qty', 1000), kw.get('price', 100), kw.get('asset', 'ARES')
        buyer = kw.get('buyer', 'Alice')
        where = {'S1a': 'Earth at Mars', 'S1b': 'Earth at Ceres', 'S1c': 'Uranus at Earth'}[k]
        cust.append((k, f"{buyer} buys {qty:,} {asset.title()} ({where})", qty * price))
    cust += [('S1d', 'Futures, Q = 2,000, both sides', SCEN['S1d']['value']), ('S1i', 'Repeat trading, $10,000 funded', 10_000)]
    rows_c = []
    for k, what, bought in cust:
        r = S1[k]
        c = r['capital']['ND']
        rows_c.append([what, money(bought), r['total_packets'], f"{c['peak_encumbered'] / bought:.2f}",
                     h(c['enc_hours'] / c['peak_encumbered'], 1), h(r['completion_h'], 1)])
    tcust = table('Lrrrrr', ['Customer action', 'Value', 'Packets', 'Committed / value', 'Hours committed', 'Done (h)'], rows_c,
                  'Efficiency per customer action (no loss). Value is the purchase price, or the notional for futures '
                  '(both sides). Committed / value is the peak encumbered cash over that value; hours committed are '
                  'dollar-hours over the peak.',
                  'tab:s1cust', sep='3pt')
    audits = sum(S1[k]['audits'] for k, _ in names)
    returned = h(S1['S1g']['times'].get('F1:Alice:returned_home'))

    w, tr, sn = traces.run_traced([(equity, dict(tag='EQ'))], ['Alice', 'Bob'], ('ARES',), until_h=48)
    ta = longtab(TRACE_COLS, TRACE_HEAD, trace_rows(traces.rows_for(w, tr, sn, ['Alice', 'Bob'], ('ARES',), skip=('RECEIPT_KNOWN',))),
                 'Full trace of S1a: Alice (Earth) buys 1,000 Ares from Bob (Mars) at \\$100.', 'tab:s1a')
    w, tr, sn = traces.run_traced([(futures, dict(path='rising'))], ['Alice', 'Cara'], (), until_h=340)
    rows_f = traces.rows_for(w, tr, sn, ['Alice', 'Cara'], (), skip=('RECEIPT_KNOWN',))
    rows_f = [r for r in rows_f if not str(r[3]).startswith('Publishes observation')]
    obs = [r for r in rows_f if str(r[3]).startswith('Records observation')]
    if obs:                     # the five observations change no balance: one row
        i = rows_f.index(obs[0])
        merged = list(obs[0])
        merged[0] = f"{float(obs[0][0]):.1f} to {float(obs[-1][0]):.1f}"
        merged[3] = 'Records observations ' + ', '.join(str(r[3]).split(' = ')[1] for r in obs) + ' (every 60 h)'
        rows_f = rows_f[:i] + [merged] + [r for r in rows_f[i:] if r not in obs]
    td = longtab(TRACE_COLS, TRACE_HEAD, trace_rows(rows_f),
                 'Full trace of S1d: capped futures on the rising path (Alice long, Cara short, $Q = 2{,}000$).', 'tab:s1d')
    t = S1['S1e']['times']
    fxr = next(iter(S1['S1e']['contracts'].values()))['fixing']

    def kt(key, items):
        tt = S1[key]['times']
        return ', '.join(f"{lab} at {h(tt[k], 3)}" for k, lab in items if k in tt)
    td_ = S1['S1d']['times']
    other = [
        ['S1d', f"Alice and Cara each fund $80,000 at Mars (receipts known at {h(td_['F1:Alice:funding_receipt_at_home'], 3)} "
                f"and {h(td_['F1:Cara:funding_receipt_at_home'], 3)}) and send their contract instructions. Both margins are held "
                f"and the contract opens at {h(td_['F1:open'], 3)} with $160,000 in escrow; Cara learns OPEN at "
                f"{h(td_['F1:Cara:report_OPEN'], 3)} and Alice at {h(td_['F1:Alice:report_OPEN'], 3)}. Bob publishes 110, 120, 130, "
                f"135 and 125 every 60 h; maturity at {h(td_['F1:maturity'], 3)}, fixing at {h(td_['F1:discharge'], 3)} at 125 "
                f"(long net +$50,000). Payouts: $30,000 spendable by Cara at {h(td_['F1:Cara:payout_spendable'], 3)} and "
                f"$130,000 by Alice at {h(td_['F1:Alice:payout_spendable'], 3)}."],
        ['S1b', kt('S1b', [('EQB:funding_imported_at_host', 'funds at Ceres'), ('EQB:funding_receipt_at_home', 'receipt known'),
                           ('EQB:first_fill', 'fill'), ('EQB:seller_spendable', 'Cara can spend'), ('EQB:buyer_spendable', 'Belt shares home')])
         + '. Same structure as S1a on the route Earth, Relay A, Ceres. Mars is not involved.'],
        ['S1c', kt('S1c', [('EQT:funding_imported_at_host', 'funds at Earth'), ('EQT:funding_receipt_at_home', 'receipt at Uranus'),
                           ('EQT:first_fill', 'fill'), ('EQT:seller_spendable', 'Fin can spend'), ('EQT:buyer_spendable', 'Terra shares at Uranus')])
         + '. Eve sends 8 copies from Uranus to Earth, each lost with probability 0.78.'],
        ['S1f', 'As S1d with $100,000 margin each. The contract opens at 2.502 and the payouts are spendable at 328.03 and '
                '328.17. Alice ends with $212,500 and Cara with $37,500.'],
        ['S1i', 'Alice funds $10,000 at Mars. One batched direct packet carries two buy orders, each 40 at $100 (o1 and '
                'o2). o1 fills 10 at $97, and the $30 price improvement is refunded immediately, then 5 at $100. o2 is cancelled '
                'unfilled at +6 h, which releases its $4,000 hold. At +12 h she sells 10 at $101 to Bob. At +24 h her cancel of o1 races an '
                "immediate-or-cancel sell from Bob. Bob's order arrives first and fills 5 at $100, and the cancel then releases "
                f"only the remainder, $2,000 for 20 shares. Finally, her cash and shares are sent home. Done at {h(S1['S1i']['completion_h'])} h, "
                f"with {S1['S1i']['total_packets']} packets for {S1['S1i']['n_tx']} transactions."],
    ]
    tother = table('lL', ['', 'Key steps (hours)'], other, 'Key steps of the scenarios without a trace table here (complete traces of every run: Section T).', 'tab:s1other')
    return T(r'''
\section*{S1. Scenario traces}
These runs have no packet loss, start at the epoch and include the scheduled maintenance. Each scenario is a separate
run from the opening balances. A scenario is complete when every intended result is spendable at its owner's home.
Packet counts include every backbone launch (data, handshakes, hop receipts, ACKs and retries) and every direct copy.

\paragraph{Transactions and value settled.} Both efficiency measures use one definition. A \emph{transaction} is a
completed transfer (funding, home delivery, payout or withdrawal), a trade fill, or a settled futures contract.
\emph{Value settled} adds their values as the brief defines them: a fill counts price $\times$ quantity, a transfer
counts the cash moved or the shares at the stated \$100, and a contract counts its notional $Q \times 1 \times 100$.
S1a has three transactions (funding \$100,000, the fill \$100,000 and the delivery of the shares \$100,000), so it
settles \$300,000; S1d has five (two fundings, the \$200,000 notional and two payouts).
\emph{Encumbered} value is the sum of order holds, contract
margin and value in transit, given per asset as the peak value and the asset-hours. \emph{Utilisation} is the peak
encumbered cash divided by the total cash of \$500,000. \emph{Exposure} is a side's largest possible loss to its
counterparty. It is \$0 for equities, because cash and shares change owner in one ledger event at the host (the buyer
carries only the market risk of the shares it chose to own). For futures it is the cap $40Q$, fully escrowed before the
contract opens. Tables~\ref{tab:s1sum} and~\ref{tab:s1cap} give the results.

<<Raw(tsum)>>
<<Raw(tcap)>>

\paragraph{Per customer.} The brief's measures count every leg, so a \$100,000 purchase settles \$300,000 and
costs <<h(S1['S1a']['comm_eff_brief'], 1)>> packets per transaction. Table~\ref{tab:s1cust} gives the same runs from
the client's side: one purchase with home delivery costs <<S1['S1a']['total_packets']>> packets and commits exactly its
own price, and the two futures sides together post 80\% of the notional (40\% each). Funding a remote market moves
the client's own money to its own account there; the purchase is complete only when the shares are spendable at home,
as the brief defines completion, and nothing remains encumbered afterwards. The funding leg is counted as a
transaction because the brief counts completed transfers, but it is not a completed purchase. The component capital
efficiency of <<h(S1['S1a']['cap_eff_brief'], 2)>> in Table~\ref{tab:s1cap} therefore reflects how the workflow is
divided into legs; it does not mean that a client needs only a third of the price. Every purchase is fully prefunded.

<<Raw(tcust)>>

\paragraph{Scale and the binding constraint.} The futures in S1d and S1e hold \$160,000, or 32\% of all cash, in escrow
for 324 hours. The boundary case $Q = 2{,}500$ holds \$200,000, or 40\%. With $Q = 2{,}501$ each side needs \$100,040.
Cara has only \$100,000, so her Ceres exchange rejects her funding transfer immediately. Alice's \$100,040 is held at
Mars until the 168-hour deadline, then released. Mars reports REJECTED to Earth in a STATUS record (R5), which
reaches Alice at hour <<h(S1['S1g']['times'].get('F1:Alice:report_REJECTED_DEADLINE'), 2)>>, and she withdraws the cash
home by hour <<returned>>. With $Q = 4{,}000$
(\$160,000 each) both home exchanges reject the funding before anything moves. All <<f"{audits:,}">> ledger checks in
these runs passed.

\paragraph{Traces.} Tables~\ref{tab:s1a} and~\ref{tab:s1d} give the financial traces of S1a and S1d. They omit rows
that change no balance: an exchange learning that its transfer arrived, and Bob publishing each observation. Section T
gives the complete trace of every S1 run, S1a to S1i, including those rows. The packet-level
communication traces are machine-readable files in \texttt{milestone2/traces/}, one set per S1 run and per S3
relocation. \texttt{*\_launches.csv} lists every packet in Table~\ref{tab:s1sum}, one row each, with its type, session,
copy number, emission and arrival time, distance, loss probability and outcome. \texttt{*\_transport.csv} lists every
session and recovery event, and \texttt{*\_ledger.csv} every ledger event. The packet counts in Table~\ref{tab:s1sum} are
computed from these files.

<<Raw(ta)>>
<<Raw(td)>>

\paragraph{S1e (falling prices).} This run is identical to S1d, step by step, until the first observation, as the
margin rule requires. The contract opens at the same time (<<h(t['F1:open'], 4)>> h) with the same packets. The
observations are 90, 80, 70, 65 and 75. The fixing at <<fxr['P']>> gives the long a net result of
<<money(fxr['net_long'])>>, so the gross payouts are reversed: \$30,000 to Alice and \$130,000 to Cara. Alice ends with
\$100,000 and Cara with \$150,000 at home. Cara's payout is spendable at <<h(t['F1:Cara:payout_spendable'], 3)>> h and
Alice's at <<h(t['F1:Alice:payout_spendable'], 3)>> h. Table~\ref{tab:s1other} gives the key steps of the remaining
scenarios.

<<Raw(tother)>>
''', locals())


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
            rows.append([key, r['principal'], f"{SHORT[r['a']]}→{SHORT[r['b']]}", r['label'].replace('+', ' + '), r['copies'],
                         f"{r['p_loss_each'][0]:.4f}", h(r['t_arrive'], 3), f"{r['p_first']:.4f}",
                         h(r['t_last_arrive'], 3), f"{r['p_success']:.5f}"])
    hop, relf, cert = [], [], []
    for key in ('S1a', 'S1b', 'S1c', 'S1d'):
        recs = {}
        for r in E2[key]['analytic']:
            recs.setdefault(r['record'], []).append(r)
        for rec, hs in recs.items():
            name = {'FUND': 'Funding', 'AUTO_FILL': 'Delivery', 'PAYOUT': 'Payout'}[rec.split()[0]]
            path = '→'.join(SHORT[x] for x in rec.split()[-1].split('->'))
            first = math.prod(1 - x['p_unconfirmed'] for x in hs)
            aband = 1 - math.prod(1 - x['p_abandon'] for x in hs)
            abnd = 1 - math.prod(1 - x['p_abandon_bound'] for x in hs)
            relf.extend(abs(x['p_abandon_frozen'] / x['p_abandon'] - 1) for x in hs)
            cert.extend(x['open_certified'] for x in hs)
            never = 1 - math.prod(1 - x['p_never_crosses'] for x in hs)
            hop.append([key + ('/e' if key == 'S1d' else ''), f"{name} {path}",
                        len(hs), f"{max(x['d'] for x in hs):.2f}", h(hs[0]['te_h'], 2),
                        f"{max(x['p_unconfirmed'] for x in hs):.4f}", f"{first:.4f}", f"{aband:.1e}", f"{abnd:.1e}", f"{never:.1e}"])
    mc = []
    for key in ('S1a', 'S1b', 'S1c', 'S1d', 'S1e'):
        m = E2[key]
        t0 = S1[key]['completion_h']
        cs = [x if x is not None else math.inf for x in m['comps']]
        p_at = sum(x <= t0 + 0.01 for x in cs) / len(cs)
        p_1h = sum(x <= t0 + 1 for x in cs) / len(cs)
        assert m['completed'] == m['n']
        mc.append([key, h(t0), f"{p_at:.2f}", f"{p_1h:.2f}", h(m['p50']), h(m['p90']),
                   h(m['p99']), h(m['max']), f"{m['mean_bb'] + m['mean_direct']:.1f}", m['max_quota_inst'],
                   m['max_direct_peak'], m['resubmit_runs'] + 0, m['fallback_runs']])
    t1 = table('lllLrrrrrr', ['Run', 'Sender', 'Path', 'Message', 'Copies', 'p each', 'First h', 'P by then',
                              'Last h', 'P(arrives)'], rows,
               'Direct-service messages in the S1 runs (exact). ``First h'' is the arrival time of the first copy, '
               'which is the time used in the traces; ``P by then'' is the probability that the message has arrived by '
               'that time. P(arrives) is the probability that at least one copy arrives, by the last copy\'s arrival.',
               'tab:e2direct', sep='3pt')
    assert all(cert)
    t2 = table('llrrrrrrrr', ['Run', 'Record', 'Hops', 'Max d', 'Launch', 'Max p unc.', 'P(no retry)',
                            'P(ab.)', 'Bound', 'P(never)'], hop,
               'Backbone loss for every record of S1a to S1e, over all of its hops. P(ab.), the chance that some hop is abandoned, is exact for retries '
               'at the hop timer; Bound holds only if no retry is delayed by more than 24 hours. S1d/e: S1e uses the '
               'same records and times as S1d. Ea = Earth, Ma = Mars, Ce = Ceres, Ur = Uranus.', 'tab:e2hop', sep='1.8pt')
    t3 = table('lrrrrrrrrrrrr', ['Run', 'Trace h', 'P(≤tr.)', 'P(+1h)', 'Median', 'p90', 'p99', 'Max',
                                  'Pkts', 'BB q.', 'Dir. q.', 'Res.', 'Fb.'], mc,
               'Monte Carlo results under random loss (2,000 runs each; every run completed). Times in hours. P(≤tr.) and P(+1h) are the '
               'probabilities of completing by the no-loss trace time and within one hour of it. Quota columns give '
               'the highest rolling 24-hour use in any run: backbone originations by one exchange (limit 66) and direct '
               'packets by one client (limit 12). The last two columns count the runs that needed an application '
               'resubmission or a client fallback.', 'tab:e2mc', sep='2.4pt')
    maxq = max(S1[k]['max_queue'] for k in S1)
    oa = next(r for r in dp['S1a'] if r['label'] == 'ORDER')
    gap = round((oa['t_last_arrive'] - oa['t_arrive']) * 60)
    return T(r'''
\section*{E2. Probability and traffic}
\paragraph{Direct service (exact).} Each copy is lost independently with probability $p = 1 - e^{-0.08d}$, where $d$
is the distance in AU at that copy's own launch. Copies are sent 60~s apart, and we check that the path is open for
every copy, so they are never blocked by the same closure. Incidents are excluded from these figures. The probability
that all copies are lost is the product of the $p_i$. A lost order is not a financial failure: the cash stays
available at the host until a fallback copy arrives. Table~\ref{tab:e2direct}
lists every direct message in S1a to S1e; Table~\ref{tab:e2alldirect} in Section E2+ extends it to all nine runs. The traces use the first copy's arrival. Each later copy adds 60~s and
raises the probability, so Alice's order in S1a has arrived with probability <<f"{oa['p_first']:.3f}">> at the traced time and
<<f"{oa['p_success']:.4f}">> <<gap>> minutes later. If no copy arrives, the client resends with the same identifier (R6). HELD and OPEN status reports are
not direct messages: they travel to the client's home exchange as STATUS records over the backbone, and are counted
with the backbone packets.

<<Raw(t1)>>

\paragraph{Backbone.} Table~\ref{tab:e2hop} covers every hop of every record in S1a to S1e;
Table~\ref{tab:e2alllaunch} in Section E2+ lists every launch of every S1 run individually. For each hop
a launch is unconfirmed with probability $1 - (1 - p_\text{data})(1 - p_\text{receipt})$. P(no retry) is the
probability that every hop of the record is confirmed at its first launch, which is the case shown in the traces. A hop
is abandoned after four unconfirmed launches. Launch $k$ is unconfirmed with probability
$u_k = 1 - e^{-0.02 d_k} e^{-0.02 r_k}$, where $d_k$ and $r_k$ are the path lengths of its data and of the hop receipt,
so the hop is abandoned with probability $u_1 u_2 u_3 u_4$. P(ab.) is the chance that this happens on some hop,
with each retry launched when the hop timer sets it ($t_{k+1} = t_k + $ twice the flight time $+ 1$~h) and each $u_k$
computed from its own geometry (\texttt{hop\_bound.py}). Queues or quota may delay a retry. If each retry may be
delayed by up to 24~hours, launch $k$ lies in a window of $(k-1) \cdot 24$~h, no path length grows faster than
0.0029~AU/h (twice Mercury's top speed, with margin), and $u$ grows with both lengths, so evaluating $u_k$ at
$d_k + 0.0029 \cdot (k-1) \cdot 24$ (and the same for $r_k$) gives the column Bound. Every window is also certified open:
the clearance at its start exceeds $0.10~\text{AU} + 0.00146$~AU/h times its length (the clearance Lipschitz bound
of E4). \emph{The bound is conditional on that 24-hour limit.} It does not cover a retry held longer, for example by a
closure of the hop that opens after the first launch or by congestion that fills the link for more than a day; for
such cases we give no per-hop bound, and the Monte Carlo results below are the evidence. Holding the first launch's geometry for all four launches, our earlier approximation, is within
<<f"{100 * max(relf):.2f}">>\% of the exact value on every hop. P(never) is the chance that the data never crosses some hop ($p_\text{data}^4$ per hop).
An abandoned hop leads to endpoint retries and resubmission; the money stays in transit, owned by the client.

<<Raw(t2)>>

\paragraph{Monte Carlo under random loss.} Each run uses an independent seed, draws every launch from the brief's loss
law and follows our client policy. Table~\ref{tab:e2mc} ties each traced time to its probability: the no-loss time is
a best case, met only when every launch succeeds first time. Figure~\ref{fig:cdf} shows the full distributions.

<<Raw(t3)>>
<<Raw(fig('cdf', 'Completion-time distributions under random loss (empirical CDF of the Monte Carlo runs in '
          'Table~\\ref{tab:e2mc}). Left: the three equity trades, log scale. Right: the futures, both payouts home.', 'fig:cdf'))>>

\paragraph{Futures opening and link capacity.} The contract opened in <<pct(E2['S1d']['p_open'], 2)>> of the lossy runs.
The median opening time was <<h(E2['S1d']['open_p50'])>> h and the 99th percentile <<h(E2['S1d']['open_p99'])>> h,
well before the 168-hour deadline. The longest queue on any directed link in any S1 run was <<maxq>> packets, against a
limit of 10,000, and serialization never delayed a packet by more than a few seconds.
''', locals())


# ====================================================================== E3
def e3():
    opening = {('Earth', 'Alice'): {'ND': 150000}, ('Mars', 'Bob'): {'ND': 50000, 'ARES': 3000},
               ('Ceres', 'Cara'): {'ND': 100000, 'BELT': 1000}, ('Neptune', 'Dax'): {'ND': 100000},
               ('Uranus', 'Eve'): {'ND': 50000}, ('Earth', 'Fin'): {'ND': 50000, 'TERRA': 1000}}
    rows = []
    for k in ('S1a', 'S1b', 'S1c', 'S1d', 'S1e', 'S1g', 'S1i'):
        parts = []
        for s, owner, d in S1[k]['balances']:
            if {a: v for a, v in d.items() if v} == opening.get((s, owner)):
                continue
            txt = ', '.join((money(v) if a == 'ND' else f"{v:,} {a.title()}") for a, v in d.items() if v)
            parts.append(f"{owner} at {s}: {txt}")
        rows.append([k, '; '.join(parts) or 'No change'])
    d = S1['S1d']
    t1 = table('lL', ['Run', 'Final balances of the accounts that changed'], rows,
               'Final balances. Accounts not listed end with their opening balances, and all other balances are zero.',
               'tab:e3final')
    t3 = table('lLLL', ['Position', 'Obligation discharged', 'Backed claim exists', 'Spendable at home'], [
        ['S1a, Alice\'s shares', 'Fill at 2.502', 'Fill at 2.502', h(S1['S1a']['times']['EQ:buyer_spendable'], 3)],
        ['S1a, Bob\'s cash', 'Fill at 2.502', '— (local)', h(S1['S1a']['times']['EQ:seller_spendable'], 3)],
        ['S1d and S1e payouts', h(d['times']['F1:discharge'], 3), h(d['times']['F1:backed_claim'], 3),
         f"Cara {h(d['times']['F1:Cara:payout_spendable'], 3)}, Alice {h(d['times']['F1:Alice:payout_spendable'], 3)}"],
    ], 'When each settled position is discharged, backed by a funded transfer, and spendable at home (hours, no loss).',
        'tab:e3times')
    return T(r'''
\section*{E3. Balances and capital}
\paragraph{Conservation check.} After every ledger event the simulator checks, for each asset, that the opening supply
equals the sum of available balances, order holds, contract holds, escrow, and transfers that have been sent but not
yet imported. It also checks that every balance is non-negative and that every buy hold equals the remaining quantity
times the limit price. For each share registry, it checks that the custody recorded for each exchange equals the
shares held there plus the shares in transit to and from it. No run ever failed a check. Table~\ref{tab:e3final} gives the final position of every account that changed.

<<Raw(t1)>>

\paragraph{Ledger at the peak of the futures.} Between hour 2.502 and hour 326.502 of S1d, Alice's \$80,000 and Cara's
\$80,000 sit in contract escrow at Mars. Each amount backs the maximum loss of that side ($40Q$) and is released only by
the fixing. All other assets are free: Alice has \$70,000 at Earth, Cara has \$20,000 and 1,000 Belt at Ceres, Bob has
\$50,000 and 3,000 Ares at Mars, Dax has \$100,000 at Neptune, Eve has \$50,000 at Uranus, and Fin has \$50,000 and
1,000 Terra at Earth. Every dollar therefore has one owner, one location and one use.

Table~\ref{tab:e3times} shows when each settled position stops being an obligation, when it is backed by
a funded transfer, and when it is spendable at home.

<<Raw(t3)>>
''', locals())


# ====================================================================== S2
def s2():
    inc = S2D['incident']
    R = S2D['runs']
    best = {}
    for path, S in (('rising', S2R), ('falling', S2F)):
        for r in S['runs']:
            k = (r['kind'], r['node'])
            if k not in best or r['damage'] > best[k]['damage']:
                best[k] = dict(r, path=path)
    top = sorted(best.values(), key=lambda r: -r['damage'])[:6]
    trows = [[r['kind'].replace('_', ' '), r['node'], f"{r['start']:g}", h(r['opened']), h(r['comp']), f"+{r['damage']:.1f}"]
             for r in top]

    def rr(key):
        x = R[key]
        return [h(x['times'].get('F1:open')), h(x['completion']), x['packets'], x['originations']]
    vrows = []
    same = all(rr(k) == rr(k.replace('rising', 'falling')) for k in R if k.startswith('rising:'))
    for path in (('rising',) if same else ('rising', 'falling')):
        for name, lab in (('baseline_no_incident', 'No incident'), ('incident', 'Incident, baseline design'),
                          ('incident_no_maintenance', 'Incident, no maintenance'),
                          ('no_incident_no_maintenance', 'No incident, no maintenance'),
                          ('incident_restart_notice', 'Incident with restart notice (A1)'),
                          ('incident_immediate_recovery', 'Incident with no backoff')):
            if f'{path}:{name}' in R:
                vrows.append(([] if same else [path]) + [lab, *rr(f'{path}:{name}')])
    mcrows = [[k.replace('mc:', '').replace('_', ' '), f"{v['completed']}/{v['n']}", h(v['p50']), h(v['p90']), h(v['p99']),
               pct(v['p_open'], 1), f"{v['mean_total']:.0f}"] for k, v in R.items() if k.startswith('mc:')]
    ev = [e for e in R['rising:incident']['courier_events'] if e[2] in ('SESSION_OPEN', 'DELIVERY_UNKNOWN', 'APP_RESUBMIT_SCHEDULED',
                                                                         'APP_RESUBMIT', 'SESSION_FAILED', 'RESET_RESEND')]
    def first(kind, node, after=0):
        return next(e[0] / 3600 for e in ev if e[2] == kind and e[1] == node and e[0] / 3600 >= after)
    t_open = first('SESSION_OPEN', 'Earth')
    lost = {n: first('DELIVERY_UNKNOWN', n) for n in ('Ceres', 'Earth')}
    resub = {n: first('APP_RESUBMIT', n) for n in ('Ceres', 'Earth')}
    n_runs = S2R['n'] + S2F['n']
    open_inc = h(R['rising:incident']['times'].get('F1:open'))
    open_a1 = h(R['rising:incident_restart_notice']['times'].get('F1:open'))
    t1 = table('llrrrr', ['Incident', 'Node', 'Start h', 'Opened h', 'Done h', 'Extra h'], trows,
               'Worst start time for each kind of incident and node, over both price paths.', 'tab:s2search')
    t3 = table('Lrrrr' if same else 'lLrrrr', ([] if same else ['Path']) + ['Variant', 'Opened h', 'Done h', 'Packets',
                                                                            'Originations'], vrows,
               'The chosen incident under each variant, without random loss.' +
               (' The falling price path gives identical results.' if same else ''), 'tab:s2var')
    t4 = table('lrrrrrr', ['Variant', 'Done', 'Median h', 'p90 h', 'p99 h', 'P(open)', 'Mean pkts'], mcrows,
               'The chosen incident with random loss (1,000 runs each).', 'tab:s2mc')
    return T(r'''
\section*{S2. Stress and recovery}
\paragraph{Choice of incident.} We ran the futures scenario on both price paths under every allowed incident on a
grid of start times between hour 0 and hour 420. The grid covered a 72-hour isolation of each settlement starting
every hour, a 6-hour forced loss at each of the 11 nodes starting every 0.5 hours, and an endpoint reset of each
exchange every 0.25 hours, <<f"{n_runs:,}">> runs in total. We measured damage as the extra hours until both payouts
are spendable, with a penalty of $10^6$ if the contract never opens. Table~\ref{tab:s2search} gives the worst start time
for each kind of incident and node, and Figure~\ref{fig:s2} shows the damage against start time.

<<Raw(t1)>>
<<Raw(fig('s2_search', 'Damage (extra hours until both payouts are home, capped at 200) against incident start time on '
          'the rising path. Coloured lines are the three exchanges in the scenario; grey lines are the other nodes.', 'fig:s2'))>>

We chose the endpoint reset of the Mars exchange at hour <<f"{inc['start']:g}">>, which is the worst incident on both
price paths. It does more damage than the obvious choice, isolating the host at payout time (about 75 hours), even
though no party can observe it. At hour 0.75, Mars has just answered Alice's and Cara's handshakes. The reset
erases its session state, but its SYN-ACK replies are already in flight. Earth and Ceres therefore believe that the
sessions are open and send their funding transfers into sessions that Mars no longer knows. As the brief requires,
Mars ignores them. The senders learn nothing until four endpoint attempts of $R_e \approx 25$ hours have expired. They
then wait for the 24-hour application backoff and resubmit. The courier log of the rising path shows this sequence.
Earth and Ceres open their sessions with Mars at hour <<f"{t_open:.4f}">>. Ceres declares its delivery unknown at
hour <<f"{lost['Ceres']:.2f}">> and Earth at hour <<f"{lost['Earth']:.2f}">>. Each schedules an application
resubmission 24 hours later, and they resubmit in new sessions at hours <<f"{resub['Ceres']:.2f}">> and
<<f"{resub['Earth']:.2f}">>.

\paragraph{State of every obligation during the incident.} Alice's and Cara's \$80,000 have been debited at home and are
in transit. They still belong to Alice and Cara but cannot be spent anywhere, for about 125 hours. No contract exists
yet, so nobody owes anything and neither margin can be lost. Bob's shares and all other accounts are not affected.
Local service at Mars never stops, because the reset only erased transport state.

\paragraph{Recovery.} Recovery here means that financial service resumes, not only that a packet gets through. The
transfers are imported at Mars, both margins are held and the contract opens at hour <<open_inc>>. This is before the
168-hour deadline, so the trade still takes place with the full 300-hour term, and both payouts arrive home.
Table~\ref{tab:s2var} compares the variants. Across the search, isolation and forced loss matter only around the
opening (hours 0 to 3) and in the payout window (hours 255 to 330), and a reset matters only if it falls between a
handshake and the first data packet.

<<Raw(t3)>>


\paragraph{Maintenance.} Removing the two scheduled maintenance windows makes no difference to this incident. Neither
window (Relay B to Neptune from hour 2 to 26, and Relay B to Ceres from hour 240 to 264) lies on the routes that the
runs use, which are Earth, Relay A, Mars and Ceres, Relay A, Mars. The timing is set by the geometry alone.

\paragraph{Alternative A1.} This alternative changes one rule and keeps the same funding and guarantees. After a reset,
an exchange sends a RESTART notice to every peer it has had a session with in the last 7 days. The notice is one
64-byte backbone record and counts against the sender's quota. A peer that receives it abandons its old sessions with
that exchange and immediately resubmits all unacknowledged records. With A1 the contract opens at hour <<open_a1>>
instead of hour <<open_inc>>, and fewer packets are needed. Removing the backoff alone, as a sensitivity test, saves
only 24 hours. A1 is not part of the evaluated design v3; it is the first change for the next revision.
Table~\ref{tab:s2mc} gives the results with random loss.

<<Raw(t4)>>
''', locals())


# ====================================================================== S3
def s3_picks():
    rel = S3['relocations']
    rk2 = sorted((v['completion_h'], k) for k, v in rel.items() if k != 'Mars')
    return [('best', rk2[0][1]), ('median', rk2[(len(rk2) - 1) // 2][1]), ('worst', rk2[-1][1])]


def s3():
    rel = S3['relocations']
    t0 = {r['settlement']: r for r in S3['table'] if r['hour'] == 0}
    t3 = {r['settlement']: r for r in S3['table'] if r['hour'] == 300}
    xd = X['s3_direct']
    rows, drows = [], []
    for s in t0:
        def cell(T_, host):
            c = T_[s][host]
            if c['route'] == 'local':
                return 'local'
            av = min(c['avail'], c['back_avail'])
            return f"{c['route'].split('-', 1)[1].rsplit('-', 1)[0]} {c['delay']:.0f}/{c['back']:.0f}" + (f", {pct(av, 0)}" if av < 1 else '')

        def dcell(hh, host):
            if s == host:
                return 'local'
            d = xd[f'{s}|{host}|{hh}']
            return f"{d['delay']:.0f}, {pct(d['avail'], 0)}, {d['copies']}"
        rows.append([s] + [cell(T_, host) for host in ('Mars', 'Ceres', 'Earth') for T_ in (t0, t3)])
        drows.append([s] + [dcell(hh, host) for host in ('Mars', 'Ceres', 'Earth') for hh in (0, 300)])
    rk = sorted(((v['completion_h'], k) for k, v in rel.items()))
    rel_rows = [[k, h(v['completion_h']), v['packets'], h(v['mc_p50']), h(v['mc_p90']), h(v['mc_p99']),
                 f"{v['p_by_24h']:.2f}", f"{v['p_by_72h']:.2f}", f"{v['p_by_168h']:.2f}", f"{v['mc_packets']:.0f}"]
                for _, k in rk for v in [rel[k]]]
    rk2 = [x for x in rk if x[1] != 'Mars']        # at Mars the purchase is local
    best, med, worst = rk2[0][1], rk2[(len(rk2) - 1) // 2][1], rk2[-1][1]

    lab = [('EQ:funding_imported_at_host', 'Funding imported at Mars'), ('EQ:funding_receipt_at_home', 'RECEIVED known at home'),
           ('EQ:order_sent', 'Order sent (direct)'), ('EQ:first_fill', 'Order arrives and fills'),
           ('EQ:seller_spendable', "Bob's cash spendable"), ('EQ:buyer_spendable', 'Shares spendable at home')]
    picks = [best, med, worst]

    def dl(k):
        d = [r for r in rel[k].get('direct_log') or []]
        if not d:
            return '—'
        return f"{len(d)} × p {d[0]['p_loss']:.3f}"
    srows = [[l] + [h(rel[k]['times'].get(x), 3) for k in picks] for x, l in lab]
    srows.append(['Order copies × loss each'] + [dl(k) for k in picks])
    srows.append(['Packets (backbone + direct)'] + [f"{rel[k]['backbone']} + {rel[k]['direct']}" for k in picks])
    tsteps = table('lrrr', ['Step (hours, no loss)', f'Best: {best}', f'Median: {med}', f'Worst: {worst}'], srows,
                   'Step-by-step timeline of the relocated purchase for the best, median and worst homes. The full '
                   'packet-level traces are in \\texttt{traces/S3\\_reloc\\_<home>\\_*.csv}.', 'tab:s3steps')
    of = load('outer_futures') or {}
    ofr = [[k.split('|')[0], h(v['noloss_open']), h(v['noloss_comp']), pct(v['p_open'], 1), h(v['open_p50']), h(v['comp_p50'])]
           for k, v in of.items() if 'baseline' in k]
    HD = ['From', 'Mars, h 0', 'Mars, h 300', 'Ceres, h 0', 'Ceres, h 300', 'Earth, h 0', 'Earth, h 300']
    t1 = table('lllllll', HD, rows,
               'Backbone access from each settlement to the three hosts at hours 0 and 300: relay or relays used (A, B) and '
               'one-way delay there and back in minutes. Availability over the next 24 hours is 100\\% unless shown.',
               'tab:s3access', sep='3pt')
    t1d = table('lllllll', HD, drows,
                'Direct access from each settlement to the three hosts at hours 0 and 300: one-way delay in minutes, '
                'availability over the next 24 hours, and the number of copies the client sends.', 'tab:s3direct', sep='3pt')
    t2 = table('lrrrrrrrrr', ['Home', 'No loss', 'Pkts', 'Median', 'p90', 'p99', 'P(24)', 'P(72)', 'P(168)',
                              'Mean pkts'], rel_rows,
               'The same \\$100,000 Ares purchase with the client moved to each settlement, ranked by completion time '
               'without loss. Times in hours; P(t) is the probability of completing within t hours (1,000 lossy runs each).', 'tab:s3rel')
    t3 = table('lrrrrr', ['Long party', 'Open, no loss', 'Done, no loss', 'P(open)', 'Median open',
                          'Median done'], ofr, 'Futures with an outer-system long party against Cara. Times in hours; P(open) is the probability that the '
               'contract opens before the 168-hour deadline (300 lossy runs each).',
               'tab:s3fut')
    return T(r'''
\section*{S3. Access at every settlement}
Funding, withdrawals and payouts travel over the backbone between the client's home exchange and the host; orders and
contract instructions travel by direct service from the client to the host. The hosts are Mars (Ares and the futures),
Ceres (Belt) and Earth (Terra). Tables~\ref{tab:s3access} and~\ref{tab:s3direct} show access by each service.
Availability is sampled every minute with maintenance applied. The only availability changes between hour 0 and hour
300 are on Mercury's direct paths: to Mars it is open for 95\% of the first day and closed all of day 300 (hours 22.5
to 357), and to Ceres it is open for <<pct(xd['Mercury|Ceres|300']['avail'], 0)>> of day 300. R8 forwards around both.

<<Raw(t1)>>
<<Raw(t1d)>>

\paragraph{Relocation.} We re-ran the same client, a \$100,000 Ares purchase with home delivery from a comparable
funded account, with its home moved to each settlement in turn (Table~\ref{tab:s3rel}). A Mars home is best overall
(the purchase is local, with no packets) and is left out of the ranking. Table~\ref{tab:s3steps} gives the step-by-step timeline for the best
(<<best>>), median (<<med>>) and worst (<<worst>>) homes. The sequence is the same everywhere; only the backbone and
direct delays and the number of direct copies change.

<<Raw(t2)>>
<<Raw(tsteps)>>

\paragraph{Outer settlements in the futures.} Table~\ref{tab:s3fut} shows the futures with Dax (Neptune) or Eve
(Uranus) as the long party against Cara. Eve's position is $Q = 1{,}250$ so that it fits her \$50,000.

<<Raw(t3)>>
''', locals())


# ====================================================================== E4
def e4():
    bb = E4['backbone']
    dr = E4['direct']
    ro = E4['routes']
    rows = []
    for s in ('Mercury', 'Venus', 'Earth', 'Mars', 'Ceres', 'Jupiter', 'Saturn', 'Uranus', 'Neptune'):
        cells = [s]
        for r in ('Relay A', 'Relay B'):
            v = bb[f'{s}->{r}']
            cells.append(f"{pct(1 - v['closed_fraction'], 1)}, {v['n_closures']}, {v['max_closure_h']:.0f} h")
        for host in ('Mars', 'Ceres', 'Earth'):
            if s == host:
                cells.append('local')
                continue
            v = ro[f'{s}->{host}']
            cells.append(f"{v['min_min']:.0f}/{v['p50_min']:.0f}/{v['max_min']:.0f}")
        dm = dr.get(f'{s}->Mars')
        cells.append('local' if s == 'Mars' else f"{pct(1 - dm['closed_fraction'], 1)}, {dm['max_closure_h'] / 24:.0f} d")
        rows.append(cells)
    worst_route = max(ro.items(), key=lambda kv: kv[1]['max_min'])
    worst_direct = max(dr.items(), key=lambda kv: kv[1]['max_closure_h'])
    ab = bb.get('Relay A->Relay B', {})
    ex = E4.get('refined_example')
    if not ex:
        import e4_scan
        s0, e0 = bb['Earth->Relay A']['closures'][0]
        lo = math.floor(s0 / 3600) * 3600.0
        a_, b_ = e4_scan.bisect('Earth', 'Relay A', lo, lo + 3600.0, True)
        ex = dict(path='Earth to Relay A, first closure', lo=lo, hi=lo + 3600.0, a=a_, b=b_)
    t1 = table('lllllll', ['From', 'To Relay A', 'To Relay B', 'To Mars', 'To Ceres', 'To Earth', 'Direct to Mars'], rows,
               'Results of the 200-year scan. Relay columns: availability, number of closures and longest closure. Host '
               'columns: one-way route time in minutes (minimum / median / maximum). Last column: availability and '
               'longest closure of the direct path to Mars.', 'tab:e4', sep='3pt')
    C, B = load('e4_certify'), load('e4_bound')
    bmax = max(B['routes'].items(), key=lambda kv: kv[1]['bound_min'])
    slack = min(v['bound_min'] - v['observed_max'] for v in B['routes'].values())
    wr = worst_route[0].replace('->', ' to ')
    wd = worst_direct[0].replace('->', ' to ')
    return T(r'''
\section*{E4. Long-horizon scan (Tier 3)}
\paragraph{Scan.} We scanned <<E4['years']>> Julian years from the epoch at a 1-hour step (<<f"{E4['samples']:,}">>
samples). At each sample we computed the clearance from the Sun, with a moving receiver, for all 38 directed backbone
links and all 72 directed direct paths, without maintenance. For routes, we computed the best-route delay from every settlement to each market host and back
at 6-hour steps, with flights in sequence.

\paragraph{Certification of the scan.} The clearance is the Sun's distance from the segment between the sender at
$t_e$ and the receiver at $t_a$. It changes no faster than the fastest endpoint moves plus the shift in arrival time,
which gives a Lipschitz bound of $L \le <<E4['lipschitz_AU_per_h']>>$~AU per hour (Mercury at perihelion, 58.98~km/s).
On any interval $[a, b]$ with end values $c(a)$ and $c(b)$, every interior value lies within
$\tfrac12(c(a) + c(b)) \pm \tfrac12 L(b - a)$. A second program (\texttt{e4\_certify.py}) uses this as an interval
test on all <<C['n_paths']>> paths. An hour is certified open if the lower bound is at least 0.10~AU and certified
closed if the upper bound is below it. Otherwise it is split in half and both halves are tested again, down to 1~ms.
Of the <<f"{C['total_hours']:,}">> path-hours, all but <<f"{C['refined_hours']:,}">> were certified directly, and
the refined hours contain <<f"{C['transitions']:,}">> changes between open and closed, each located to within 1~ms.
The closure counts agree exactly with the scan. Leaves that the test cannot classify can sit next to each other,
so we merged adjacent uncertified leaves into connected intervals. There are <<f"{C['components']:,}">> such intervals,
exactly one per located transition. The longest is <<f"{C['max_component_s']:.2f}">>~s
(<<C['max_leaves_in_component']>> leaves, at a grazing pass where the clearance stays very close to 0.10~AU), and
every one has different states at its two ends, so each contains the change it is counted for. Any further changes
inside an interval would come in pairs and bound a period shorter than the interval. Within the model, therefore, every
change between open and closed in the 200 years is located to within <<f"{C['max_component_s']:.2f}">>~s, and no open
or closed period longer than <<f"{C['max_component_s']:.2f}">>~s is missed. The run took <<f"{C['runtime_s'] / 60:.1f}">> minutes.

\paragraph{Refined boundary (Tier 2).} For the <<ex['path']>>, the hourly samples bracket the boundary in
[<<f"{ex['lo']:.0f}">>, <<f"{ex['hi']:.0f}">>]~s. Bisection with the exact light-time solver narrows this to
[<<f"{ex['a']:.6f}">>, <<f"{ex['b']:.6f}">>]~s, a width of <<f"{1e3 * (ex['b'] - ex['a']):.3f}">>~ms, within the
1~ms tolerance. A packet emitted before the boundary follows its own path and is not affected. Our queue does not launch
a packet after the boundary; the link waits instead. A closure therefore never destroys a packet in flight. It only
delays the next launch, and the hop timer $R_h$ restarts at the actual emission.

\paragraph{Results.} The link between Relay A and Relay B never closes; its minimum clearance is
<<f"{ab.get('min_clearance', 2):.2f}">>~AU. Table~\ref{tab:e4} gives the results for the other links. Every settlement
had a route to every host at every sample: the connected fraction is 1.000 for all <<len(ro)>> directed
settlement--host pairs, as the geometric argument in the design paper predicts. The longest one-way route is
<<wr>> at <<f"{worst_route[1]['max_min']:.0f}">> minutes (hour <<f"{worst_route[1]['t_max_h']:,.0f}">>). The longest
direct closure is <<wd>> at <<f"{worst_direct[1]['max_closure_h'] / 24:.1f}">> days. Direct paths are the weak point,
and their closures are the reason for our access check, deferral and forwarding rule R8.

<<Raw(t1)>>

\paragraph{What holds beyond 200 years.} Two results do not depend on the scan. The relay geometry argument shows that
every settlement always has a route to every host. Since a route has at most three links, its length is at most
$(r_a + R) + R\sqrt{2} + (r_b + R)$~AU, with aphelion distances $r_a, r_b$ and relay radius $R = <<f"{B['relay_radius']:.3f}">>$~AU,
so every one-way route delay with empty queues is bounded for all time (\texttt{e4\_bound.py}). The largest bound is
<<f"{bmax[1]['bound_min']:.0f}">> minutes (<<bmax[0].replace('->', ' to ')>>, against <<f"{bmax[1]['observed_max']:.0f}">> observed), and every
observed maximum is at least <<f"{slack:.0f}">> minutes below its bound. The availability figures, closure counts and
typical delays in Table~\ref{tab:e4} are statistics of the scanned 200 years only. The orbital periods are not
commensurate, so the configuration never repeats exactly, and we do not extrapolate them. Section E5 tests three
later epochs directly.
''', locals())


# ====================================================================== E5
def e5():
    R = E5['rows']
    rt = X['e5_routes']
    rows = []
    for ep in ('+1 year', '+10 years', '+100 years', 'Mars conjunction'):
        r = {x['a'] + x['b']: x for x in rt[ep]['rows']}
        em = r['EarthMars']
        cm = r['CeresMars']
        cells = [ep, f"{rt[ep]['t0_h']:,.0f}",
                 f"{em['route']} {em['delay']:.0f}" + (f", {pct(em['avail'], 0)}" if em['avail'] < 1 else '')
                 + f"; direct {em['direct_delay']:.0f}, {pct(em['direct_avail'], 0)}",
                 f"{cm['route']} {cm['delay']:.0f}" + (f", {pct(cm['avail'], 0)}" if cm['avail'] < 1 else '')
                 + f"; direct {cm['direct_delay']:.0f}, {pct(cm['direct_avail'], 0)}"]
        for sc in ('S1a', 'S1d'):
            b = R[f'{ep}|{sc}']
            w = R[f'{ep}, without O2|{sc}']
            nb, nw = b['noloss']['comp'], w['noloss']['comp']
            show = lambda r, c: h(c) if c else ('suspended' if r['noloss']['suspended'] else 'deferred')
            cells.append(show(b, nb) + f" ({h(b['mc']['p50'])})" + (f"; no R8: {show(w, nw)}" if nw != nb else ''))
        rows.append(cells)
    d = E5['difficult']
    t1 = table('lrLLLL', ['Epoch', 'Start (h)', 'Earth–Mars', 'Ceres–Mars', 'S1a equity', 'S1d/S1e futures'], rows,
               'Results at shifted epochs. Route columns: backbone route used and one-way time in minutes, then the direct path time '
               'and 24-hour availability (backbone availability is 100\\% unless shown). '
               'Scenario columns: completion time without loss, with the median of 300 lossy runs in brackets. '
               "Where the result without rule R8 (forwarding) differs, it is shown after ``no R8''.", 'tab:e5')
    cara_back = h(R['Mars conjunction, without O2|S1d']['noloss']['times'].get('F1:Cara:returned_home'))
    r9 = load('r9_detail')
    ra, rd = r9['runs']['S1a'], r9['runs']['S1d']
    ch = ra['chains'][0]
    l1, l2 = ch['leg1'], ch['leg2']
    st = r9['difficult']['start_h']
    fw = rd['agent_quota_peak']
    mca, mcd = R['Mars conjunction|S1a']['mc'], R['Mars conjunction|S1d']['mc']
    return T(r'''
\section*{E5. Shifted epochs (Tier 3)}
Each run starts at $t = k \times 365.25$ days with every orbit advanced from the epoch. Balances are reset to the
opening values, maintenance and the S2 incident are not repeated, and the observation and maturity times move with the
start. S1d and S1e give identical times at every epoch (only the payout split differs), so Table~\ref{tab:e5} lists
them together.

<<Raw(t1)>>

\paragraph{Difficult epoch.} We chose the first Mars solar conjunction after the epoch. The Earth to Mars direct path
closes at hour <<f"{d['close_h']:,.1f}">> and reopens at hour <<f"{d['reopen_h']:,.0f}">>, 53 days later, and we start
24 hours after the closure. With rule R8, Alice's client forwards her instructions through <<ch['via']>>, whose direct legs to Earth and to Mars
are both open. Her order goes Earth to <<ch['via']>> as <<l1['n']>> copies (each lost with probability
<<f"{l1['p_loss_each'][0]:.3f}">>), and <<ch['via']>> forwards it once as <<l2['n']>> copies (each lost with
probability <<f"{l2['p_loss_each'][0]:.3f}">>). The first copy reaches Mars at hour
<<h(l2['t_first_arrive'] - st, 3)>>, with probability <<f"{l1['p_first'] * l2['p_first']:.3f}">> that both first copies
arrive. The probability that some copy crosses each leg, so that the order arrives within minutes (by about hour
<<h(l2['t_last_arrive'] + (l1['n'] - 1) / 60 - st, 2)>>, if only the last first-leg copy gets through), is <<f"{ch['p_both']:.4f}">>. <<ch['via']>> uses at most
<<max(fw.values())>> of its 12 daily direct packets. Alice learns that her contract is OPEN at hour
<<h(rd['times']['F1:Alice:report_OPEN'], 2)>> from a STATUS record over the backbone. The equity trade completes in
<<h(R['Mars conjunction|S1a']['noloss']['comp'])>> hours, and both futures price paths complete in
<<h(R['Mars conjunction|S1d']['noloss']['comp'])>> hours. With random loss, <<mca['completed']>>/<<mca['n']>> equity
runs (median <<h(mca['p50'])>> h, p99 <<h(mca['p99'])>> h) and <<mcd['completed']>>/<<mcd['n']>> futures runs (median
<<h(mcd['p50'])>> h) complete. A lost forwarded copy is recovered by the R6 fallback as attempt $k + 1$.

Without R8, Alice's client finds no long enough direct window and never funds Mars: no trade takes place, and Cara's
futures margin is back home by hour <<cara_back>>. Nobody loses anything, but nobody trades. At +10 years the equity
trade waits <<h(R['+10 years, without O2|S1a']['noloss']['comp'], 0)>> hours and the futures are suspended.
''', locals())
