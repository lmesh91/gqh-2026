"""Design paper (12 pages max).  Plain language first; every number comes from results/*.json."""
from build import *


def fin(x):
    return x is not None and math.isfinite(x)


def build():
    a = S1['S1a']
    d = S1['S1d']
    rel = S3['relocations']
    ofut = load('outer_futures') or {}
    T = d['times']
    o = []
    # ------------------------------------------------------------------ title + summary
    o.append(f'''
<div class="kicker">MultiPlanetary Exchange System · Design paper · Milestone 2 draft · design v3 (prefunded trading accounts)</div>
<h1>Nine exchanges, one rule: spend only what is already here</h1>
<p class="lede">Every settlement runs one exchange. A client who wants to trade on another world first moves money there
through the official backbone, and from then on that exchange trades for the client using only balances it already
holds. Nothing is ever spent on the strength of a message that might still be in flight, so lost, late or duplicated
packets can delay the market but cannot create or destroy a single NeoDollar or share.</p>
<p>This paper states the architecture and the operating rules (Sections 1–2), the guarantees we give and what they
cost (Section 3), the weaknesses we found by attacking the design (Section 4), how it keeps working indefinitely
(Section 5) and what a real deployment would change (Section 6). The evidence appendix holds the traces and
calculations behind every number; a full discrete-event simulator of the brief's network and our ledgers
reproduces all of them. Headline results at the 2026-09-22 epoch:</p>
<ul>
<li><b>Earth buyer, Mars shares:</b> funding, trade and delivery of 1,000 Ares shares home in {h(a['completion_h'])} h with no loss
({a['total_packets']} packets in total); median {h(E2['S1a']['p50'])} h and 99th percentile {h(E2['S1a']['p99'])} h over
{E2['S1a']['n']:,} random-loss runs, every run completed.</li>
<li><b>300-hour capped futures:</b> $160,000 of margin (32% of all cash) locked at Mars for the whole contract; both
price paths settle with both payouts spendable at home by {h(d['completion_h'])} h. The rejected oversize variant
(Q = 2,501) leaves everyone whole.</li>
<li><b>All nine settlements</b> can fund, trade and receive payouts. Neptune is the hardest: its direct packets are lost
91% of the time, so a trade there completes within 72 h with probability {rel['Neptune']['p_by_72h']:.2f} and within
168 h with probability {rel['Neptune']['p_by_168h']:.2f}.</li>
</ul>''')
    # ------------------------------------------------------------------ 1 architecture
    o.append(f'''
<h2>1. Architecture</h2>
<p><b>Institutions.</b> There are exactly nine institutions: one exchange per settlement (the brief allows twelve).
There is no clearinghouse. Each exchange keeps customer accounts in its own ledger and is the only writer of those
balances. The three stock markets sit with their share registries and their opening sellers: Ares Habitat on Mars,
Belt Works on Ceres, Terra Fabrication on Earth. The capped futures contract is hosted by the Mars exchange because Mars
is the best-connected settlement for the inner system (Appendix S3) and the price source, Bob, lives there.</p>
{fig('map', 'Figure 1. The nine settlements and two relays at the epoch. Purple lines are the 19 backbone links. Red '
             'settlements host a market. The geometry is never a straight line in practice: every flight is solved '
             'with the moving receiver, and links shut whenever a path passes within 0.1 AU of the Sun.')}
<p><b>Accounts.</b> A client has one registered home and may hold a trading account at any of the nine exchanges.
Remote accounts start empty and only ever receive assets by an explicit transfer. Opening a remote account creates no
wealth, no new identity and no extra direct-service quota.</p>
''')
    o.append(table(['Shared state', 'The only institution allowed to change it'], [
        ['Available balances, order holds, contract escrow', 'The exchange holding those balances'],
        ['Order book and every fill', "The asset's market exchange"],
        ['Debit and terms of an outgoing transfer', 'The sending exchange'],
        ['Credit of an incoming transfer', 'The named receiving exchange (exactly once)'],
        ['Share registry: which exchange holds how many shares', "The asset's registry exchange (= its market)"],
        ['Contract position, fixing and payout allocation', 'The contract host (Mars)'],
    ], cls='compact'))
    o.append(f'''
<p><b>Opening balance sheet</b> (hour 0, identical for every run): Alice (Earth) $150,000; Bob (Mars) $50,000 and
3,000 Ares; Cara (Ceres) $100,000 and 1,000 Belt; Dax (Neptune) $100,000; Eve (Uranus) $50,000; Fin (Earth) $50,000
and 1,000 Terra. Total $500,000 and 5,000 shares in six accounts at five settlements. Institutions start with zero.</p>
<h3>How a cross-planet trade works</h3>
<ol>
<li><b>Fund.</b> Alice tells Earth (local access, 1 s) to move $100,000 to her Mars account. Earth debits her at once
and sends a TRANSFER record over the backbone. While in flight, the money belongs to Alice but nobody can spend it.</li>
<li><b>Import.</b> Mars accepts that transfer exactly once, credits Alice's Mars account, and sends RECEIVED back.</li>
<li><b>Order.</b> When Earth has the receipt, Alice knows her money is at Mars and sends a signed order by the direct
service (several copies, because direct packets are often lost).</li>
<li><b>Trade.</b> Mars holds $100,000 of Alice's cash, matches Bob's resting sell order and swaps cash for shares
atomically. Bob's money is spendable on Mars at that instant.</li>
<li><b>Deliver.</b> Alice chose home delivery, so the same atomic step exports her 1,000 shares to Earth. The trade is
complete for Alice only when Earth credits them.</li>
</ol>
{fig('swimlane_s1a', f"Figure 2. The no-loss Earth–Mars trade (scenario S1a). Bold arrows carry money or shares; grey arrows are the brief's handshake and acknowledgement traffic; dashed arrows are Alice's three direct order copies. Complete at {h(a['completion_h'], 3)} h.")}
''')
    # ------------------------------------------------------------------ 2 rulebook
    o.append('''
<h2>2. Operating rulebook</h2>
<p>Each rule names who acts, what they may rely on, and what happens when a message goes wrong. "Durable" means the
change survives a crash or reset; every change below is one atomic durable write.</p>
<h3>R1. Moving assets between exchanges</h3>
<p>A TRANSFER carries a globally unique ID (source exchange + export number), the owner, asset, amount, destination
and purpose; its terms never change. (1) The source checks the owner's <i>available</i> balance and debits it in the same
write that creates the export, so the value now exists only as "in transit". (2) The destination credits it the first
time it sees that ID and records the ID forever; any later copy only triggers another RECEIVED. (3) The source marks
the export delivered when RECEIVED arrives. A missing receipt <b>never</b> refunds the source: the courier keeps
re-sending the same record (hop retries, endpoint retries, then application resubmission after 24, 48, 96 and 168 h)
until the receipt comes back. A transfer to an account that has been closed is credited to a restricted balance and
sent straight back with a new transfer. Shares always move between the registry exchange and a custodian, so the
registry can reconcile its custody totals.</p>
<h3>R2. Orders, holds and matching</h3>
<p>An order names its owner, a unique ID, asset, side, integer quantity and limit price, time-in-force (GTC or IOC),
an expiry no more than 30 days away and a disposition (keep results at the market, or send them home automatically).
The market admits it only if the owner's <i>available</i> balance at that exchange covers it: quantity × limit for a
buy, the shares for a sell. Those assets move into a hold that nothing else can touch. An order that is not covered is
rejected for good; the client must fund the account and send a new order ID. Matching is price-time priority at
the resting price; self-trades are skipped. Each fill is one atomic write: buyer hold −q·limit, seller hold −q
shares, buyer +q shares and +q·(limit − price) refund of price improvement, seller +q·price, plus the automatic home
export when chosen. Cancels release only the unfilled remainder; a cancel that arrives before its order leaves a
tombstone so the late order can never open. There is no amend: cancel and send a new order.</p>
<h3>R3. Withdrawals and account closure</h3>
<p>WITHDRAW names an amount or ALL. ALL is evaluated once, when the host first processes it, and repeated copies
return that same export. A withdrawal can only take available balance; it never cancels orders or touches margin.
CLOSE stops new orders, cancels open ones and withdraws what is free; escrow stays until the contract pays out, and
those payouts are then sent home automatically. The home exchange can never "unlock" money that sits at another
exchange: only the host that holds it can send it back.</p>
<h3>R4. Capped futures and the one margin rule</h3>
<div class="box"><p><b>Contract.</b> Long and short agree on Q NeoDollars per index point, strike K = 100, and a collar
[60, 140]. The long's lifetime payoff is Q × (clip(P, 60, 140) − 100); the short receives the negative.</p>
<p><b>Margin rule (stated before any price is seen).</b> Each side must hold its <i>maximum possible loss</i>,
Q × 40, in escrow at the host from opening until fixing. Nothing else: no variation margin, no calls, no offsets, no
share collateral. Because the escrow equals the largest loss either side can ever owe, no price path can produce an
unfunded obligation, and the rule is identical in the rising and falling runs.</p></div>
<p>Each party funds its Mars account (R1), then sends a contract instruction carrying the full terms. Mars moves that
party's margin from available cash into a hold; when both holds exist the contract opens atomically and maturity is set
to opening + 300 h. If both are not held by the opening deadline (168 h after the scenario starts) the contract is
rejected and each hold returns to that party's available Mars balance; clients who hear no OPEN report then withdraw.
Payouts are exported home automatically in the same write as the fixing.</p>
<h3>R5. Price source and fixing</h3>
<p>Bob, the named index source at Mars, learns the schedule locally at opening and publishes one signed observation
at opening + 60, 120, 180, 240 and 300 h by local access. Mars fixes at maturity + 24 h using observation 5; if it is
missing or two conflicting copies exist, it uses the latest earlier valid observation, else 100. Late observations
are ignored. The 24 h grace lets a remote source's packet arrive before fixing; with a local source it costs one day of
escrow (3.84 M dollar-hours) and could be cut (Section 4).</p>
<h3>R6. Which service carries what</h3>
''')
    o.append(table(['Message', 'Service', 'Quota charged'], [
        ['TRANSFER (funding, withdrawal, auto-delivery, payout), RECEIVED', 'Backbone, pinned route of ≤3 links',
         'Sending exchange, 66 per rolling 24 h'],
        ['Order, cancel, withdraw, close, contract instruction', 'Local access at the host, else direct',
         "Client's own 12 per 24 h, ≥60 s apart"],
        ['Price observation', 'Local access at Mars (Bob is local)', 'none'],
        ['Contract status REPORT to a remote client', 'Direct', 'Mars exchange principal, 12 per 24 h'],
    ], cls='compact'))
    o.append(f'''
<p>The nine exchanges split the 600 backbone originations as 66 each (594 total); there is no shared counter.
SYNs, first transmissions, RECEIVEDs and application resubmissions count; automatic retries and ACKs do not, but every
launch is counted in our packet totals. Client instructions never ride on the backbone, and exchange coordination
never rides on the direct service.</p>
<h3>R7. Declared client policy</h3>
<p>Clients are software with the published ephemeris but no knowledge of hidden incidents.</p>
<ul>
<li><b>Fund first, then instruct.</b> A client sends an order or contract instruction only after its home exchange has
recorded RECEIVED for the funding transfer. It learns this by local access, so the order cannot be rejected for
missing funds.</li>
<li><b>Copies.</b> Send the smallest number of direct copies, 60 s apart, that gives ≥99% chance at least one arrives,
capped at 8 (Earth→Mars: 3 copies, all lost with probability 0.0021; Neptune→Mars: 8 copies, 0.46).</li>
<li><b>Fallback.</b> An equity buyer whose shares have not arrived home by twice the direct + backbone delay
plus 6 h re-sends the same order ID (duplicates are harmless) until the order's own expiry. A futures party that has no
HELD/OPEN report after twice the direct flight plus 6 h re-sends its instruction, until the deadline.</li>
<li><b>Access check.</b> Before funding, the client checks that its direct path to the host stays open for the whole
planned sequence. If not, it waits for the next long-enough window, or, if that is after the deadline,
suspends; its money stays at home.</li>
</ul>
<h3>R8. Recovery</h3>
<p>Ledgers, outboxes and ID records are durable. After a reset, an expired session or a delivery the transport gives
up on, the courier opens a new session and resubmits the same records after 24, 48, 96 and then every 168 h, waiting
out known closures and quota. Recovery work is preferred over new work.</p>
<h3>What each actor knows when a message goes wrong</h3>
''')
    o.append(table(['Event', 'Sender knows / does', 'Receiver knows / does', 'Who owes what'], [
        ['TRANSFER lost or late', 'No RECEIVED yet; keeps retrying the same ID', 'Nothing; the money cannot be spent there',
         'Value is "in transit", owned by the client, backed by the source debit'],
        ['RECEIVED lost', 'Retries the TRANSFER', 'Duplicate import ignored, RECEIVED re-sent', 'Nothing changes; money already spendable at host'],
        ['Duplicate TRANSFER / order / instruction', '—', 'Same ID and terms: same result returned; changed terms: rejected', 'No double effect'],
        ['All order copies lost', 'No shares home by fallback time: re-sends same ID', 'No order exists; cash stays available', "Client's cash idle at host"],
        ['Cancel lost or late', 'Assumes nothing until state confirmed', 'Order may still fill', 'Fill stands; cancel releases only the remainder'],
        ['Contradicting price copies', '—', 'Observation invalid; fall back to earlier one', 'Fixed at cutoff; never revised'],
        ['Host isolated 72 h', 'Remote clients cannot instruct', 'Local trading, matching, maturity continue', 'Payout exports wait, funded, in the outbox'],
        ['Exchange reset', 'Volatile sessions lost', 'Ledger intact; outbox resubmitted after backoff', 'No balance changes'],
    ], cls='compact'))
    o.append(f'''
<h3><span class="tag opt">Option O2</span> Forwarding through a third exchange</h3>
<p>Not part of the v3 baseline; offered for adoption. When the client's direct path to the host is blocked by the Sun
but both legs through some third settlement are open, the client sends its signed instruction to that settlement's
exchange, which re-sends it by direct service under <i>its own</i> 12-per-day quota. The message stays client
communication; the forwarder gains no authority and the host still checks the client's signature and balances. At the
2028 Mars conjunction this turns "no Earth–Mars trading for 53 days" into a {h(E5['rows']['Mars conjunction, option O2|S1a']['noloss']['comp'])} h trade
(Appendix E5).</p>''')
    # ------------------------------------------------------------------ 3 guarantees
    o.append(f'''
<h2>3. Guarantees, conditions and costs</h2>
<p>We separate what the <b>rules</b> guarantee in every possible run from what the <b>model</b> (orbits, loss law,
quotas) makes likely. The first kind holds for any packet loss, delay or order; the second is evidence, not proof.</p>''')
    o.append(table(['#', 'Guarantee', 'Holds because', 'Condition'], [
        ['G1', 'Total NeoDollars and each share type never change', 'Every write debits and credits equal amounts; transit is a ledger state',
         'Rules only. Checked after every event in every traced run'],
        ['G2', 'No asset serves two uses at once', 'Available, held, escrowed and in-transit are disjoint states', 'Rules only'],
        ['G3', 'Every futures payout is fully funded', 'Escrow = maximum loss, posted before opening', 'Rules only; any price path'],
        ['G4', 'Each transfer is credited exactly once', 'Destination remembers every export ID forever', 'Rules + durable storage'],
        ['G5', 'A host fill is final and spendable at the host at once', 'Both holds exist before the atomic fill', 'Rules only'],
        ['G6', 'A funded transfer eventually arrives', 'Retries never stop and the backbone is always connected (E4)',
         'Model: no unconditional deadline exists under random loss'],
        ['G7', 'Completion times', 'Measured', 'Model: see probabilities below and in Appendix E2/S3'],
    ], cls='compact'))
    # service table
    rows = []
    for r0 in S3['table']:
        x = r0['settlement']
        if r0['hour'] != 0:
            continue
        rl = rel[x]
        bb = '/'.join('loc' if x == hst else f"{r0[hst]['delay']:.0f}" for hst in ('Mars', 'Ceres', 'Earth'))
        dm = r0['direct']
        dir_ = 'local' if x == 'Mars' else f"{dm['copies']} → {dm['burst']:.3f}"
        eq = f"{h(rl['completion_h'], 1)} / {h(rl['mc_p50'], 1)} / {rl['p_by_72h']:.2f}"
        notes = {
            'Mercury': 'Direct path to Mars closed h 22–357 at epoch: funding waits (R7) or O2',
            'Venus': 'Closed near Venus–Mars conjunctions; waits or O2',
            'Earth': 'Earth–Mars direct closed ~53 days per 2.1 y (Mars conjunction); O2',
            'Mars': 'All products local, 1 s',
            'Ceres': 'Belt market local',
            'Jupiter': '4 copies',
            'Saturn': '7 copies',
            'Uranus': '8 copies; fallback often used',
            'Neptune': '8 copies still lose 46% of bursts; slow',
        }[x]
        rows.append([x, bb, dir_, eq, notes])
    o.append('<p><b>Service table.</b> Every product is offered at every settlement: funding/withdrawal at all three '
             'markets, equity trading in Ares, Belt and Terra, and the capped futures at Mars. What differs is speed '
             'and probability. Columns: one-way backbone delay to the Mars/Ceres/Earth hosts (minutes, hour 0); direct '
             'copies per instruction to Mars and the chance at least one arrives; and for a $100k Ares purchase '
             'delivered home: no-loss time / median under loss / probability done within 72 h '
             '(1,000 runs each, Appendix S3).</p>')
    o.append(table(['Settlement', 'Backbone min', 'Direct copies → P', 'Ares trade h: no-loss / median / P(≤72 h)',
                    'Restrictions'], rows, cls='compact'))
    fut_note = ''
    if ofut:
        dx = ofut.get('Dax|baseline', {})
        fut_note = (f" For the futures, a Neptune party (Dax long against Cara) gets the contract opened in "
                    f"{pct(dx.get('p_open', 0), 0)} of lossy runs before the 168 h deadline; the rest are rejected at the "
                    f"deadline with all margin returned (Appendix S3).")
    o.append(f'''<p>All futures parties must reach Mars before the 168 h opening deadline. Inner-system parties
almost always do (Appendix E2: the contract opened in every one of {E2['S1d']['n']:,} lossy runs).{fut_note}</p>
<p><b>Costs.</b> A one-off cross-planet trade with home delivery costs {a['total_packets']} packets
({a['backbone_total']} backbone launches including handshakes, receipts and ACKs, plus {a['direct']} direct copies) and 5
backbone originations. Repeat trading is far cheaper: the $10k worked example (S1i) made four fills, one
cancellation, a cancel/fill race and a final sweep home on one funding transfer, {S1['S1i']['total_packets']} packets
in total. Capital: the futures lock $160,000 for 324 h (escrow {d['capital']['ND']['escrow_hours'] / 1e6:.2f} M dollar-hours,
peak encumbered / notional = 0.80); an equity purchase holds 100% of its value while in transit or on order and nothing
afterward. No institution holds capital, and none is needed.</p>
{fig('futures_balances', "Figure 3. Where Alice's and Cara's cash is during the futures (no loss). Shaded: contract open (red), fixing grace (beige). Both paths use the same margin and finish with $500,000 in total.")}''')
    # ------------------------------------------------------------------ 4 risks
    o.append(risks_section())
    o.append(longterm_section())
    o.append(deployment_section())
    return '\n'.join(o)


def s2_summary():
    if not S2D:
        return None
    inc = S2D['incident']
    r = S2D['runs']
    return inc, r


def risks_section():
    rel = S3['relocations']
    e5 = E5['rows']
    s2 = s2_summary()
    s2txt = ''
    s2row = None
    if s2:
        inc, r = s2
        base = r['rising:baseline_no_incident']['completion']
        hit = r['rising:incident']['completion']
        s2txt = (f"An isolation of Mars around fixing delays both payouts by up to 75 h (S2 search).")
        a1 = r['rising:incident_restart_notice']['completion']
        s2row = ['Silent session loss after an endpoint reset',
                 f"S2 (worst of {S2R['n'] + S2F['n']:,} incidents): a Mars reset at h {inc['start']:g}, just after the handshakes, makes Mars drop the "
                 f"funding transfers silently; senders wait ~100 h of endpoint retries + 24 h backoff. Futures done {h(hit)} h instead of {h(base)} h "
                 "(still opens inside the deadline; no money at risk)",
                 f"<span class=\"tag opt\">A1</span> restart notice to recent peers: done {h(a1)} h. Recommended"]
    rows = [
        ['1', 'Solar conjunction cuts a client off from its host', 'E5: at the 2028 Mars conjunction the Earth–Mars direct path is shut for 53 days. '
         'No Earth client can order, cancel or withdraw at Mars; Bob\'s 30-day sell order expires first, so the trade never happens',
         'Access check before funding (money stays home); futures suspend safely. <span class="tag opt">O2</span> forwarding restores service: '
         f"trade in {h(e5['Mars conjunction, option O2|S1a']['noloss']['comp'])} h, both futures runs complete"],
        ['2', 'Rule interaction: funds parked at a host become unreachable', 'Withdrawals are client instructions (direct), so money left at Mars during a '
         'closure cannot be called home even though the backbone works', 'Clients fund just in time (R7); automatic home delivery and payout need no instruction; O2'],
        ['3', 'Outer settlements: direct loss 76–91% per copy', f"S3: Neptune P(done ≤72 h) = {rel['Neptune']['p_by_72h']:.2f}; 8 copies give only a 54% burst",
         'Improvement I1 (applied): copies capped at 8 not 6, fallback after 6 h not 24 h, resend until order expiry: Neptune 0.34 → '
         f"{rel['Neptune']['p_by_72h']:.2f}, Uranus 0.93 → {rel['Uranus']['p_by_72h']:.2f}"],
        ['4', 'Host concentration', 'All futures margin and the price source are at Mars. ' + (s2txt or 'An isolation of Mars at fixing delays both payouts.'),
         'Fixing and payout are local and automatic; payouts wait funded in the outbox; nothing needs a remote instruction'],
        ['5', 'Rule interaction: access check vs. closures of the "wrong" path', 'S3 found Mercury\'s funding stuck for 335 h with a 48 h check '
         'window, because Mercury→Mars direct is shut h 22–357', 'Improvement I2 (applied): the check covers the real sequence length; Mercury now completes in '
         f"{h(rel['Mercury']['completion_h'])} h"],
        ['6', *s2row] if s2 else ['6', 'Recovery after a reset', 'pending', 'pending'],
        ['7', 'Shared host REPORT quota', 'Mars sends every remote client\'s status by direct service on one 12-per-day quota', 'Reports only on state change, ≤1 per 6 h per client; clients rely on fallbacks; demand cap in Section 5'],
        ['8', 'Single price source', 'Bob can fail or publish conflicting copies', 'Deterministic fallback to latest valid earlier observation, else 100; disclosed basis risk'],
        ['9', 'Custodian trust', 'Prefunding concentrates exposure on the host exchange', 'Brief assumes operators follow rules; independent audit is future work'],
    ]
    return ('<h2>4. Risks we found, ranked</h2><p>Ranked by harm × likelihood under our own evidence. The interesting '
            'ones are interactions between our own rules and the geometry; they were found by the stress search, the '
            'shifted epochs and the outer-settlement runs, not by inspection.</p>' +
            table(['#', 'Risk', 'Evidence', 'Treatment'], rows, cls='compact'))


def longterm_section():
    e4 = E4
    conn = ''
    if e4:
        worst = max(e4['routes'].items(), key=lambda kv: kv[1]['max_min'])
        conn = (f" The 200-year scan confirms it: every settlement had a route to every market host at all "
                f"{e4['samples']:,} hourly samples, and the slowest one-way route ever seen was {worst[0]} at "
                f"{worst[1]['max_min']:.0f} min.")
    return f'''
<h2>5. Long-term operation</h2>
<p><b>The backbone never disconnects (geometry, proven).</b> The relays are 90° apart on one circular orbit and the
A–B link always clears the Sun by 2 AU. A gateway–relay link is blocked only when the gateway sits nearly behind the
Sun as seen from that relay (an angle of at least 159°), which cannot happen for both relays at once. So every
settlement always has a route of at most three links to every other, outside maintenance and incidents.{conn}
Direct paths, by contrast, do close for weeks (conjunctions), so every direct-dependent promise is conditional.</p>
<p><b>Long periods with no usable route, and the backlog after.</b> Nothing has a wall-clock expiry except orders
(≤30 days, releasing only their own hold) and contract opening deadlines (returning margin). Transfers, receipts and
payouts wait in durable outboxes; sessions that idle for 7 days are simply re-opened; a packet that hits the 30-day
transport lifetime is replaced by an application resubmission of the same financial ID. After a route reopens, each
exchange drains its outbox within its 66-per-day origination budget, recovery first (22 of the 66 are reserved for it).
Up to 5 transfers share one 1,024-byte packet, so a backlog of 300 transfers to one peer drains in about a day.</p>
<p><b>Obligations past our longest example.</b> A contract stores absolute maturity and fixing times; fixing is a
local computation at the host and the payout export is created in the same write, so a maturity years away needs no
message to happen.</p>
<p><b>Capital.</b> There is no endowment. New capital can only enter through fees or contributions debited from real
accounts and moved by R1. Escrow is released only by fixing or rejection, so capital cannot leak or be invented.</p>
<p><b>Storage and identifiers.</b> IDs are 96-bit counters behind a 32-bit principal prefix: at a million IDs per
second they last 2.5 × 10¹⁵ years. Time is kept as signed 64-bit integer milliseconds (≈292 million years each way).
Our simulator uses float seconds, which stop resolving 1 ms after {E1['float64_ms_limit_years']:,.0f} years; a production
system must use integer time and extended-precision orbital phase. Bounded state: ≤32 live orders per client per
host, 256 per host, 4,096 unresolved transfers per host with 20% reserved for returns and maturities. Terminal
records are compacted behind per-principal floors; an unresolved one blocks compaction and, eventually, new work.
When a limit is reached we stop accepting new work; we never drop an obligation.</p>
<p><b>Demand we accept.</b> Per exchange per day: up to 44 routine backbone originations (≈10 new cross-exchange
funding or withdrawal workflows at 4–5 originations each) and 22 recovery originations; per client, 12 direct packets,
i.e. 1–4 remote instructions depending on distance. Above that, work queues; nothing is promised for it.</p>
<p><b>Eons.</b> The brief's orbits are fixed ellipses, so the geometry is quasi-periodic forever: the 200-year
statistics describe every later century of the model. What ages is arithmetic, not orbits. With integer
milliseconds and extended-precision phase, the rules above have no time-dependent part; the binding limits are
identifier space (above) and the physical infrastructure, which the brief fixes. The real Solar System would drift away
from these elements within centuries (Section 6), so we do not claim the model's geometry beyond its own terms.</p>
'''


def deployment_section():
    return table(['Effect', 'Size estimate', 'Source and assumptions', 'Effect on guarantees'], [
        ['Earth rotation hides the sky', '≈11.97 h below-horizon gaps per station', 'Sidereal day 23.93 h; one equatorial '
         'station, zero elevation mask [1]', 'Times only: +up to 12 h per hop without a 2nd station. G1–G5 unchanged'],
        ['Doppler shift', '≈3.20 MHz at 32 GHz', 'f·v/c with an assumed 30 km/s line-of-sight speed [1, 2]',
         'Modems must track it; if not, more loss. Loss only slows us'],
        ['Clock rates (relativity)', 'Mercury vs Earth clocks: ≈2.3 × 10⁻⁸, ≈0.7 s/yr', 'GM/(rc²) + v²/(2c²) at 0.39 and 1 AU',
         'Maturity and fixing use TDB; local clocks must be corrected, else ms-level schedule errors'],
        ['Real ephemeris drift', 'Not estimated', 'Kepler elements ignore planetary perturbations', 'All timetables need a live ephemeris; rules do not'],
    ], cls='compact').join(['''
<h2>6. Deployment assessment</h2>
<p>The baseline leaves real effects out on purpose. None of the following can break conservation or double use (they
only delay or lose packets, which the rules already tolerate); they would change our times and probabilities.</p>''',
                          '''<p class="refs" style="font-size:10pt">[1] NASA Earth Fact Sheet, nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html.
[2] ESA, Cebreros DSA-2 ground station (Ka-band, 32 GHz). [3] CPMI–IOSCO, Principles for Financial Market Infrastructures
(delivery versus payment). [4] Gray and Lamport, Consensus on Transaction Commit, 2004.</p>'''])
