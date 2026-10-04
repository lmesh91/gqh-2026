"""Design paper (12 pages max). Every number comes from results/*.json."""
from build import *
import supp_text as SX


def T(s, env):
    return fill(s, {**globals(), **env})


def build():
    a = S1['S1a']
    d = S1['S1d']
    rel = S3['relocations']
    abstract = T(r'''
We present a design for trading shares and a capped futures contract among the nine settlements of the
MultiPlanetary Exchange System. Each settlement runs one exchange. A client who wants to trade at another settlement
first transfers money to an account at that settlement's exchange over the backbone network. Once the money has
arrived, the exchange executes the client's orders using only balances that it already holds. No exchange ever acts
on value that is still in transit, so lost, delayed or duplicated packets can slow trading down but cannot create
or destroy money or shares.

We evaluated the design with a discrete-event simulator of the network described in the brief. Without packet loss, an
Earth client buys 1,000 Ares shares from a Mars seller and has them at home after <<h(a['completion_h'])>> hours. With
random loss, the median time is <<h(E2['S1a']['p50'])>> hours, the 99th percentile is <<h(E2['S1a']['p99'])>> hours,
and all <<f"{E2['S1a']['n']:,}">> simulated runs complete. The 300-hour capped futures contract settles correctly for
both the rising and the falling price path, and both payouts are spendable at home after <<h(d['completion_h'])>> hours.
Clients at all nine settlements can use every product. Neptune is the slowest settlement: a share purchase from
Neptune completes within 72 hours with probability <<f"{rel['Neptune']['p_by_72h']:.2f}">> and within 168 hours with
probability <<f"{rel['Neptune']['p_by_168h']:.2f}">>.''', locals())
    o = [intro(), architecture(), rules(), guarantees(), risks_section(), longterm_section(), deployment_section()]
    return document('A Prefunded Design for the MultiPlanetary Exchange System',
                    r'Design paper \quad$\cdot$\quad Milestone 2 \quad$\cdot$\quad Design v3', '\n'.join(o), abstract, size='10pt')


# ---------------------------------------------------------------------- 1 introduction
def intro():
    return r'''
\section{Introduction}
The brief asks for a market system for clients on nine settlements, from Mercury to Neptune. Its scope covers
equities, futures, options, bonds, currencies, lending, short positions, clearing and settlement. We implement and test
equities, a capped futures contract, and the clearing and settlement of both; Section~\ref{sec:scope} explains how the
other products fit the same framework and marks them as extensions. All communication between settlements is by radio. Messages take minutes to
hours to arrive, some are lost, and some paths are blocked for weeks when they pass too close to the Sun. The main
difficulty is that no exchange can know the current state of another exchange.

Our design avoids the need for that knowledge. Every account balance is held by exactly one exchange, and only that
exchange can change it. An exchange only executes an instruction if the assets it needs are already in its own ledger.
Money moves between exchanges as explicit transfers that are credited exactly once. As a result, the correctness of
the ledgers never depends on whether a message arrives or when it arrives. Only the speed of service does. Unlike a
distributed commit protocol~\cite{gl}, no exchange ever waits for another exchange to agree before it acts.

Section~\ref{sec:arch} describes the institutions and accounts. Section~\ref{sec:rules} gives the operating rules.
Section~\ref{sec:guar} states the guarantees, the conditions they rely on and their cost. Section~\ref{sec:risk} lists
the weaknesses we found by testing the design. Section~\ref{sec:long} covers long-term operation, and
Section~\ref{sec:deploy} discusses what a real deployment would change. The evidence appendix contains the traces,
calculations and simulation results behind every number in this paper. All results use the epoch 2026-09-22 00:00 TDB
unless stated otherwise.
'''


# ---------------------------------------------------------------------- 2 architecture
def architecture():
    a = S1['S1a']
    t1 = table('lL', ['Shared state', 'Only institution allowed to change it'], [
        ['Available balances, order holds and contract escrow', 'The exchange that holds those balances'],
        ['Order book and fills', "The asset's market exchange"],
        ['Debit and terms of an outgoing transfer', 'The sending exchange'],
        ['Credit of an incoming transfer', 'The named receiving exchange, exactly once'],
        ['Share registry (how many shares each exchange holds)', "The asset's registry exchange, which is also its market"],
        ['Contract positions, fixing and payout allocation', 'The contract host (Mars)'],
    ], 'Ownership of shared state. Each item has exactly one writer.', 'tab:owners')
    t_scope = table('p{0.17\\linewidth}p{0.13\\linewidth}L', ['Product', 'Status', 'Treatment in this framework'], [
        ['Equities (Ares, Belt, Terra)', 'Implemented, tested (S1a–c, S1i, S3)',
         'Unit: one share, held at the registry or a custodian exchange. Limit orders at the market exchange (R2), fully '
         'prefunded. No end of life.'],
        ['Capped futures', 'Implemented, tested (S1d–g, S2, E5)',
         'Size Q per index point, strike 100, collar [60, 140], 300 h term, hosted at Mars, priced by Bob (R4, R5). Each '
         'side escrows its maximum loss, so the counterparty never bears a loss. Ends with the fixing and automatic payouts.'],
        ['Clearing and settlement', 'Implemented', 'No central counterparty. Delivery versus payment in one ledger write at '
         'the host (R2); transfers between exchanges by R1.'],
        ['Capped options', 'Extension', 'Writer escrows the maximum payout and the buyer prefunds the premium; settles like R4.'],
        ['Short positions', 'Extension', 'The bounded futures short is implemented. Borrowed-share shorts need borrow, return '
         'and buy-in rules and are not supported.'],
        ['Bonds and lending', 'Extension', 'A loan creates a claim and a liability, not cash. Guaranteed repayment needs '
         'escrowed backing; volatile collateral cannot guarantee it.'],
        ['Currencies', 'Extension', 'A unit issued by one exchange and fully backed by escrowed NeoDollars, redeemable only '
         'there.'],
    ], 'Products in the brief\'s scope. Extensions follow the same rules (prefunding, one writer per balance) but are '
       'not specified in full or tested.', 'tab:scope')
    return T(r'''
\section{Architecture}\label{sec:arch}
\subsection{Institutions}
The system has nine institutions: one exchange at each settlement. The brief allows up to twelve, but we found no
use for more. There is no clearinghouse. Each exchange keeps the accounts of its customers in its own ledger and is the
only institution that can change those balances.

The three stock markets are located where the share registries and the initial sellers are: Ares Habitat on Mars,
Belt Works on Ceres and Terra Fabrication on Earth. The capped futures contract is hosted by the Mars exchange. Mars is
the best-connected settlement in the inner system (Appendix S3), and the price source, Bob, lives there.

<<Raw(fig('map', 'The nine settlements and two relays at the epoch. Purple lines are the 19 backbone links; red '
          'markers are settlements that host a market. Actual flights do not follow straight lines between the '
          'positions shown: each one is computed with the receiver moving during the flight, and a link is closed '
          'whenever its path passes within 0.1~AU of the Sun.', 'fig:map'))>>

\subsection{Accounts}
Each client has one registered home settlement. A client may also hold a trading account at any of the other eight
exchanges. Remote accounts start empty and receive assets only through explicit transfers. Opening a remote account
does not create money, a new identity or any additional direct-service quota. Table~\ref{tab:owners} lists which
institution may change each part of the shared state.

<<Raw(t1)>>

Every run starts from the balances in Table~\ref{tab:open}. The institutions themselves hold nothing.

<<Raw(SX.opening_table('tab:open', compact=True))>>

\subsection{Products and scope}\label{sec:scope}
Table~\ref{tab:scope} lists every product in the brief's scope and marks each as implemented or as an extension. Every
product, implemented or not, must follow the same two rules: an exchange acts only on assets already in its own ledger,
and each balance has exactly one writer.

<<Raw(t_scope)>>

\subsection{Example: an Earth client buys Mars shares}
A cross-settlement trade proceeds in five steps. Figure~\ref{fig:swim} shows them for scenario S1a.
\begin{enumerate}\setlength{\itemsep}{1pt}
\item \emph{Funding.} Alice instructs the Earth exchange, by local access, to move \$100,000 to her Mars account.
Earth debits her balance immediately and sends a TRANSFER record over the backbone. While the record is in flight, the
money still belongs to Alice, but nobody can spend it.
\item \emph{Import.} Mars accepts the transfer exactly once, credits Alice's Mars account and sends a RECEIVED record
back to Earth.
\item \emph{Order.} When Earth has the receipt, Alice knows that her money is at Mars. She then sends a signed order
to Mars by the direct service. She sends several copies because direct packets are often lost.
\item \emph{Trade.} Mars holds \$100,000 of Alice's cash. It matches her order against Bob's resting sell order and
exchanges cash for shares in a single atomic step. Bob can spend the proceeds at Mars immediately.
\item \emph{Delivery.} Alice asked for home delivery, so the same atomic step also creates a transfer of her 1,000
shares to Earth. For Alice the trade is complete when Earth credits the shares.
\end{enumerate}

<<Raw(fig('swimlane_s1a', f"The S1a trade without packet loss. Bold arrows carry money or shares. Grey arrows are "
          f"handshake and acknowledgement packets required by the network. Dashed arrows are Alice's three direct "
          f"copies of her order. The trade is complete at {h(a['completion_h'], 3)} h.", 'fig:swim'))>>
''', locals())


# ---------------------------------------------------------------------- 3 rules
def rules():
    t_service = table('LLL', ['Message', 'Service', 'Quota charged'], [
        ['TRANSFER (funding, withdrawal, delivery, payout) and RECEIVED', 'Backbone, on a fixed route of at most 3 links',
         'Sending exchange, 66 per rolling 24 h'],
        ['Order, cancel, withdrawal, close, contract instruction', 'Local access at the host; otherwise direct',
         "The client's own 12 per 24 h, at least 60 s apart"],
        ['Price observation', 'Local access at Mars (Bob is local)', 'None'],
        ['Contract status for remote clients (HELD, OPEN, REJECTED)', 'Backbone STATUS record from Mars to the client\'s '
         'home exchange, which tells the client by local access', 'Mars exchange, 66 per 24 h; one record per home exchange'],
    ], 'Which communication service carries each message.', 'tab:service')
    t_fail = table('p{0.15\\linewidth}LLL', ['Event', 'Sender', 'Receiver', 'Financial effect'], [
        ['TRANSFER lost or late', 'Has no RECEIVED yet and keeps resending the same transfer',
         'Knows nothing; the money cannot be spent there', 'The value is in transit, still owned by the client'],
        ['RECEIVED lost', 'Resends the TRANSFER', 'Ignores the duplicate and resends RECEIVED',
         'None; the money is already spendable at the host'],
        ['Duplicate transfer, order or instruction', '—', 'Returns the original result; a copy with different terms is rejected',
         'None'],
        ['All order copies lost', 'Resends the same order ID when its fallback timer expires', 'No order exists; the cash stays available',
         "The client's cash is idle at the host"],
        ['Cancel lost or late', 'Assumes nothing until it sees the order state', 'The order may still fill',
         'A fill stands; the cancel releases only the unfilled part'],
        ['Conflicting price copies', '—', 'Treats the observation as invalid and uses an earlier one',
         'The fixing is final and never revised'],
        ['STATUS record lost', 'Courier resends it like any record', 'Client fallback resends the instruction; the '
         'duplicate only triggers a fresh status', 'None'],
        ['Host isolated for 72 h', 'Remote clients cannot send instructions', 'Local trading, matching and maturity continue',
         'Payout transfers wait, already funded, in the outbox'],
        ['Exchange reset', 'Loses its open sessions', 'Ledger is intact; the outbox is resent after a backoff',
         'None'],
        ['Forwarding exchange slow or silent (R9)', 'Resends the instruction when its fallback timer expires',
         'Host sees nothing, or a later duplicate it ignores', 'None; the client\'s funds stay available at the host'],
    ], 'What each party knows and does when a message goes wrong.', 'tab:fail')
    o2 = E5['rows']['Mars conjunction|S1a']['noloss']['comp']
    return T(r'''
\section{Operating rules}\label{sec:rules}
Each rule below states who acts, what information they may rely on and what happens when a message is lost or late.
A change is \emph{durable} if it survives a crash or reset. Every change of financial state described here is a single
atomic, durable write to one exchange's ledger.

\subsection{R1: Moving assets between exchanges}
A TRANSFER record carries a globally unique identifier (the source exchange and an export number), the owner, the
asset, the amount, the destination and the purpose. Its terms never change after it is created.
\begin{enumerate}\setlength{\itemsep}{1pt}
\item The source exchange checks that the owner's \emph{available} balance is large enough. In the same write that
creates the transfer, it debits that balance. From then on the value exists only as ``in transit''.
\item The destination exchange credits the transfer the first time it sees its identifier and keeps a durable record
of that identifier (compacted as described in Section~\ref{sec:long}). Any later copy only causes another RECEIVED.
\item The source marks the transfer as delivered when the RECEIVED record arrives.
\end{enumerate}
A missing receipt never causes a refund at the source. Instead, the courier keeps resending the same record: first
through the network's hop and endpoint retries, then by application resubmission after 24, 48, 96 and 168 hours,
until the receipt arrives. If the destination account has been closed, the transfer is credited to a restricted balance
and returned with a new transfer. Shares always move between the registry exchange and a custodian exchange, so the
registry can reconcile how many shares each exchange holds.

\subsection{R2: Orders, holds and matching}
An order specifies its owner, a unique identifier, the asset, the side, an integer quantity, a limit price, a
time-in-force (good-till-cancelled or immediate-or-cancel), an expiry no more than 30 days away, and a disposition.
The disposition says whether results stay at the market or are sent home automatically.

The market accepts an order only if the owner's available balance at that exchange covers it: quantity times limit
price for a buy, or the shares for a sell. The covered assets are moved into a hold that nothing else can use. An
order that is not covered is rejected permanently, and the client must fund the account and send a new order with a
new identifier.

Matching uses price-time priority at the resting order's price, and self-trades are skipped. Each fill is one atomic
write. It reduces the buyer's cash hold by the quantity times the limit price and the seller's share hold by the
quantity. It credits the buyer with the shares and with any price improvement, and credits the seller with the
quantity times the trade price. If the buyer chose home delivery, the same write creates the transfer home. Cash
and shares therefore change hands together, which is delivery versus payment within one ledger~\cite{pfmi}. A cancel
releases only the unfilled part of an order. If a cancel arrives before its order, the exchange records it so that the
order can never open later. Orders cannot be amended; the client cancels and sends a new order instead.

\subsection{R3: Withdrawals and account closure}
A WITHDRAW instruction names an amount or ALL. ALL is evaluated once, when the host first processes the instruction,
and repeated copies return the same transfer. A withdrawal can only take the available balance. It never cancels
orders and never touches margin. A CLOSE instruction stops new orders, cancels open ones and withdraws the free
balance. Escrowed margin stays at the host until the contract pays out, and the payouts are then sent home
automatically. The home exchange cannot release money held at another exchange; only the exchange that holds it can
send it back.

\subsection{R4: Capped futures and the margin rule}
The long and the short agree on a size $Q$ in NeoDollars per index point, a strike $K = 100$ and a collar of
$[60, 140]$. The long's payoff over the life of the contract is
\[ Q \times \bigl(\min(\max(P, 60), 140) - 100\bigr), \]
where $P$ is the fixing price, and the short receives the negative of this amount.

\emph{Margin rule.} From opening until fixing, each side must hold its maximum possible loss, $40Q$, in escrow at the
host. There is no variation margin, no margin call, no netting and no share collateral. The rule is fixed before any
price is observed. Because the escrow equals the largest amount either side can ever owe, no price path can produce an
unfunded obligation. The rule is the same for the rising and the falling price path.

To enter the contract, each party funds its Mars account (R1) and then sends a contract instruction with the full
terms. Mars moves that party's margin from its available cash into a hold. When both holds exist, the contract opens
atomically and its maturity is set to 300 hours after opening. If both margins are not held by the opening deadline,
168 hours after the scenario starts, the contract is rejected. Each hold then returns to the party's available balance
at Mars, and a client who has not received an OPEN report withdraws it. Payouts are transferred home in the same
write as the fixing.

\subsection{R5: Price source and fixing}
Bob is the named index source at Mars. He learns the observation schedule locally when the contract opens and
publishes one signed observation by local access at 60, 120, 180, 240 and 300 hours after opening. Mars fixes the
contract 24 hours after maturity using observation 5. If observation 5 is missing, or if two conflicting copies exist,
Mars uses the latest earlier valid observation, or 100 if there is none. Observations that arrive after the fixing are
ignored. The 24-hour grace period allows a remote price source's packet to arrive before the fixing. With a local
source it only costs one day of escrow (3.84 million dollar-hours) and could be removed (Section~\ref{sec:risk}).

\subsection{R6: Communication services}
Table~\ref{tab:service} shows which service carries each type of message. The nine exchanges divide the 600 backbone
originations allowed per day into 66 each (594 in total), so no shared counter is needed. SYN packets, first
transmissions, RECEIVED records and application resubmissions count against the quota. Automatic retries and ACKs do
not, although our packet totals include every launch. Client instructions never use the backbone, and exchanges never
use the direct service to coordinate with each other.

\emph{Quota classes.} A data packet that carries any record other than RECEIVED is \emph{routine} and may be sent only
while the exchange has made fewer than 44 originations in the last 24 hours. SYN packets, receipt-only packets and
resubmissions may use all 66, so at least 22 a day always remain for recovery, however much new work is queued.

\emph{Packet sizes.} Every record is a fixed-width binary layout with an 88-byte common header (type, length,
identifier, creation time and the issuer's Ed25519 signature). A TRANSFER is 176 bytes, a RECEIVED 120 bytes and a
client instruction 128 to 256 bytes. A packet has the brief's 64-byte header and at most 960 bytes of payload, of which
16 are our sub-header, so it carries at most 944 bytes of whole records: five transfers, seven receipts or three
contract instructions. Records are never split. The sender closes a packet when the next record would not fit, and a
client batch that does not fit is sent as several direct packets, each counted in the 12. Appendix F gives every field.

\emph{Status reports.} A remote client learns that its margin is held or that its contract is open from its own home
exchange. When a contract changes state, Mars adds one entry per affected remote client to a STATUS record for that
client's home exchange. All entries for the same home exchange created at the same moment travel in one record, so the
cost grows with the number of home exchanges, not with the number of clients. The home exchange tells the client by
local access. Status therefore uses Mars's backbone quota of 66 originations per day instead of its 12 direct packets,
gets the backbone's retries instead of a single direct copy, and still reaches a client whose own direct path is
behind the Sun. The price is packets: each STATUS record crosses two backbone hops with their receipts and
acknowledgements, which adds about 20 launches to a two-party contract (Appendix S1).

<<Raw(t_service)>>

\subsection{R7: Client policy}
Clients are programs that know the published ephemeris but not the hidden incidents. They follow four rules.
\begin{itemize}\setlength{\itemsep}{1pt}
\item \emph{Fund first, then instruct.} A client sends an order or contract instruction only after its home exchange
has recorded the RECEIVED for the funding transfer. The client learns this by local access, so the order cannot be
rejected for lack of funds.
\item \emph{Copies.} The client sends the smallest number of direct copies, 60 seconds apart, that gives at least a
99\% chance that one arrives, up to a maximum of 8. From Earth to Mars this is 3 copies, which are all lost with
probability 0.0021. From Neptune to Mars it is 8 copies, which are all lost with probability 0.46.
\item \emph{Fallback.} If an equity buyer's shares have not arrived home after twice the combined direct and
backbone delay plus 6 hours, the client resends the order with the same identifier until the order expires.
Duplicates are harmless. A futures party that has no HELD or OPEN status after twice the direct flight time, plus
three backbone route times from the host to its home, plus 6 hours (at most 12 hours, so that a distant client uses its whole daily quota), resends its instruction until the deadline.
\item \emph{Access check.} Before funding, the client checks that it will be able to reach the host for the whole
planned sequence, either directly or by forwarding (R9). If it will not, the client waits for the next window that is
long enough. If that window starts after the deadline, the client does not trade, and its money stays at home.
\end{itemize}

\subsection{R8: Recovery}
Ledgers, outboxes and identifier records are durable. After a reset, an expired session or a delivery that the
network gives up on, the courier opens a new session and resubmits the same records after 24, 48 and 96 hours and
then every 168 hours. It waits out known closures and quota limits, and it gives recovery traffic priority over new
traffic. Table~\ref{tab:fail} summarises how each party behaves when a message goes wrong.

<<Raw(t_fail)>>

\subsection{R9: Forwarding through a third exchange}
The Sun sometimes blocks a client's direct path to the host for weeks, while the backbone stays connected. Client
instructions cannot use the backbone, so R9 gives them a second direct route. If the client's direct path to the host
is closed when an instruction is due, the client sends it instead to the exchange of a third settlement. It picks the
settlement whose two direct legs are both open and which gives the earliest arrival at the host.
\begin{enumerate}\setlength{\itemsep}{1pt}
\item The client wraps its signed instruction in a FWD record with a forwarding attempt number $k = 1, 2, \ldots$
and sends it to the third exchange by direct service, with the number of copies set by R7 for that leg.
\item The third exchange forwards each new pair (instruction identifier, $k$) once, by direct service under its own
quota of 12 packets per day and with the number of copies set by R7 for the second leg. Further copies of the same
attempt are ignored. It keeps only the pair, until the instruction's expiry or opening deadline.
\item The host treats the forwarded instruction exactly like a direct one. It checks the client's signature, balance
and instruction identifier, so a forwarded copy and a direct copy of the same instruction are duplicates.
\end{enumerate}
The forwarding exchange gains no authority. It cannot change a signed instruction, no asset passes through it and it
owes nothing financially. The client learns the result from its home exchange over the backbone (R6), which works
during the closure. If no status arrives before the R7 fallback timer, the client sends attempt $k+1$, through the
third exchange that is best at that moment (possibly a different one) or directly once the path reopens. A forwarded instruction uses two direct legs, so it costs about
twice as many packets, and these are counted in every total. During the 2028 Mars conjunction, Earth clients cannot
reach Mars directly for 53 days. With R9, the S1a trade completes in <<h(o2)>> hours instead of not taking place
(Appendix E5).
''', locals())


# ---------------------------------------------------------------------- 4 guarantees
def guarantees():
    a = S1['S1a']
    d = S1['S1d']
    erows = []
    for k, lab, ex in (('S1a', 'Equity, Earth buys Ares', '$0'), ('S1c', 'Equity, Uranus buys Terra', '$0'),
                       ('S1d', 'Futures, either path', '$80,000'), ('S1f', 'Futures, Q = 2,500', '$100,000'),
                       ('S1i', 'Repeat trading', '$0')):
        x = S1[k]
        erows.append([k, lab, x['n_tx'], money(x['value_settled_brief']), x['total_packets'], h(x['comm_eff_brief'], 1),
                      money(x['capital']['ND']['peak_encumbered']), h(x['cap_eff_brief'], 2), ex])
    teff = table('llrrrrrrr', ['', 'Scenario', 'Tx', 'Value settled', 'Packets', 'Pkts/tx', 'Peak enc.', 'Cap. eff.',
                               'Exposure'], erows,
                 'Efficiency as defined in Section 7 of the brief (no loss). A transaction is a completed transfer, '
                 'trade fill or settled contract; exposure is each side\'s largest possible loss to its counterparty.',
                 'tab:eff', sep='2.4pt')
    rel = S3['relocations']
    ofut = load('outer_futures') or {}
    tg = table('lp{0.3\\linewidth}LL', ['', 'Guarantee', 'Reason', 'Condition'], [
        ['G1', 'The total of NeoDollars and of each share type never changes', 'Every write debits and credits equal amounts; '
         'value in transit is a ledger state', 'Rules only; checked after every event of every traced run'],
        ['G2', 'No asset is used for two purposes at once', 'Available, held, escrowed and in-transit balances are separate',
         'Rules only'],
        ['G3', 'Every futures payout is fully funded', 'Escrow equals the maximum loss and is posted before opening',
         'Rules only; holds for any price path'],
        ['G4', 'Each transfer is credited exactly once', 'The destination keeps a durable record of every credited identifier (tombstone or watermark)',
         'Rules and durable storage'],
        ['G5', 'A fill is final and immediately spendable at the host', 'Both holds exist before the atomic fill', 'Rules only'],
        ['G6', 'A funded transfer eventually arrives', 'Retries never stop and the backbone is always connected (E4)',
         'Model; under random loss there is no fixed deadline'],
        ['G7', 'Completion times', 'Measured in simulation', Raw('Model; see Table~\\ref{tab:access} and Appendix E2 and S3')],
    ], 'Guarantees of the design and the conditions they depend on.', 'tab:guar')
    rows = []
    notes = {
        'Mercury': 'Direct path to Mars closed from h 22 to h 357; instructions are forwarded (R9)',
        'Venus': 'Closed near Venus–Mars conjunctions; instructions are forwarded (R9)',
        'Earth': 'Terra local. Direct path to Mars closed about 53 days every 2.1 years; forwarded (R9)',
        'Mars': 'Ares and futures local; Belt (Ceres) and Terra (Earth) remote',
        'Ceres': 'Belt local; Ares and futures (Mars) and Terra (Earth) remote',
        'Jupiter': '4 copies per instruction',
        'Saturn': '7 copies per instruction',
        'Uranus': '8 copies; the fallback is often used',
        'Neptune': '8 copies still all fail 46% of the time',
    }
    for r0 in S3['table']:
        x = r0['settlement']
        if r0['hour'] != 0:
            continue
        rl = rel[x]
        bb = ' / '.join('local' if x == hst else f"{r0[hst]['delay']:.0f}" for hst in ('Mars', 'Ceres', 'Earth'))
        dm = r0['direct']
        dir_ = 'local' if x == 'Mars' else f"{dm['copies']}, {dm['burst']:.3f}"
        rows.append([x, bb, dir_, h(rl['completion_h'], 1), h(rl['mc_p50'], 1), f"{rl['p_by_72h']:.2f}", notes[x]])
    ta = table('lllrrrL', ['From', 'Backbone min', 'Copies, P', 'No loss', 'Median', 'P(72 h)', 'Notes'], rows,
               'Service at each settlement at hour 0. Backbone min: one-way delay in minutes to the Mars, Ceres and '
               'Earth hosts. Copies, P: direct copies per instruction to Mars and the probability that at least one '
               'arrives. The next three columns are for a \\$100,000 Ares purchase with home delivery: completion time '
               'in hours without loss, the median under random loss, and the probability of completing within 72 '
               'hours (1,000 runs each; Appendix S3).', 'tab:access')
    fut_note = ''
    if ofut:
        dx = ofut.get('Dax|baseline', {})
        fut_note = (f" For a Neptune party (Dax long against Cara), the contract opened before the deadline in "
                    f"{pct(dx.get('p_open', 0), 1)} of runs with random loss. In the other runs it was rejected at the "
                    f"deadline and all margin was returned (Appendix S3).")
    P = load('products')
    spread = max(max(v) - min(v) for v in ([P[f'{s}|{p}']['noloss'] for p in ('Ares', 'Belt', 'Terra')
                                              if P[f'{s}|{p}']['packets']] for s in S3['relocations']) if len(v) > 1)
    return T(r'''
\section{Guarantees and costs}\label{sec:guar}
We distinguish between properties that the \emph{rules} guarantee in every possible run and properties that the
\emph{model} (orbits, loss law and quotas) makes likely. The first kind holds for any pattern of packet loss, delay or
reordering. The second kind is supported by simulation evidence but is not proven. Table~\ref{tab:guar} lists both.

<<Raw(tg)>>

\subsection{Service at every settlement}
Every product is available at every settlement. Clients can fund and withdraw at all three markets, trade Ares, Belt
and Terra shares, and enter the capped futures at Mars. What differs between settlements is the speed of service and
the probability of completing within a given time. Table~\ref{tab:access} shows these figures for each settlement.

<<Raw(ta)>>

Table~\ref{tab:access} uses the Ares purchase. Appendix S3 repeats it for every product at every settlement. A purchase
is local, with no network traffic, only where the client's home hosts that market: Ares and the futures at Mars, Belt
at Ceres and Terra at Earth. Everywhere else the three share purchases complete within <<f"{spread:.1f}">> hours of
each other without loss, because the time is set by where the client is, not by the product.

Every futures party must reach Mars before the 168-hour opening deadline. Parties in the inner system almost always
do: in all <<f"{E2['S1d']['n']:,}">> simulated runs with random loss, the contract opened (Appendix E2).<<fut_note>>

\subsection{Costs}
A single cross-settlement trade with home delivery uses <<a['total_packets']>> packets: <<a['backbone_total']>>
backbone launches, including handshakes, receipts and ACKs, and <<a['direct']>> direct copies. It uses 5 backbone
originations from the quotas. Repeated trading is much cheaper per trade. In the \$10,000 example (S1i), one funding
transfer supports four fills, a cancellation, a race between a cancel and a fill, and a final transfer home, using
<<S1['S1i']['total_packets']>> packets in total. Table~\ref{tab:eff} gives both efficiency measures with one
definition of a transaction (Appendix S1).

<<Raw(teff)>>

The brief's measures count every leg, so one \$100,000 purchase settles \$300,000. For the client, S1a costs
<<a['total_packets']>> packets and commits exactly the price paid (ratio 1.0); the two futures sides post 80\% of the
notional (40\% each). Remote funding moves the client's money to its own account; the purchase completes only when the
shares are spendable at home, so the component ratio does not mean a third of the price is needed (Appendix S1).

The futures contract locks \$160,000 for 324 hours. This is <<f"{d['capital']['ND']['escrow_hours'] / 1e6:.2f}">>
million dollar-hours of escrow, and at its peak 80\% of the notional value is encumbered. An equity purchase ties up its
full value while it is in transit or on order, and nothing after the trade. No institution needs to hold capital.
Figure~\ref{fig:fut} shows where Alice's and Cara's cash is during the contract.

<<Raw(fig('futures_balances', "Location of Alice's and Cara's cash during the futures contract, without packet loss. "
          "The red band marks the period when the contract is open and the beige band the fixing grace period. Both "
          "price paths use the same margin and end with \\$500,000 in total.", 'fig:fut'))>>
''', locals())


# ---------------------------------------------------------------------- 5 risks
def risks_section():
    rel = S3['relocations']
    e5 = E5['rows']
    inc = S2D['incident']
    r = S2D['runs']
    base = r['rising:baseline_no_incident']['completion']
    hit = r['rising:incident']['completion']
    a1 = r['rising:incident_restart_notice']['completion']
    nsearch = S2R['n'] + S2F['n']
    o2 = e5['Mars conjunction|S1a']['noloss']['comp']
    rows = [
        ['1', 'A solar conjunction cuts a client off from its host',
         'During the 2028 Mars conjunction the Earth–Mars direct path is closed for 53 days. Earth clients cannot order, '
         "cancel or withdraw at Mars. Bob's 30-day sell order expires first, so the trade does not happen (E5).",
         f'Rule R9 forwards instructions through a third exchange (Mercury here): the trade completes in {h(o2)} h and '
         f'both futures runs complete. Without R9, the access check keeps money at home and nobody trades.'],
        ['2', 'Money left at a host can become unreachable',
         'Withdrawals are client instructions sent by direct service. Money left at Mars during a closure cannot be '
         'called home, even though the backbone still works.',
         'Clients fund just before they trade (R7). Home delivery and payouts need no instruction. A withdrawal can be '
         'forwarded through a third exchange (R9).'],
        ['3', 'Direct loss of 76–91% per copy at the outer settlements',
         f"From Neptune, P(complete within 72 h) = {rel['Neptune']['p_by_72h']:.2f}, because 8 copies only "
         f"succeed 54% of the time (S3).",
         f"Change I1 (applied): up to 8 copies instead of 6, fallback after 6 h instead of 24 h, and resending until "
         f"the order expires. This raised P(72 h) from 0.34 to {rel['Neptune']['p_by_72h']:.2f} for Neptune and "
         f"from 0.93 to {rel['Uranus']['p_by_72h']:.2f} for Uranus."],
        ['4', 'Concentration at the host',
         'All futures margin and the price source are at Mars. An isolation of Mars around the fixing delays both '
         'payouts by up to 75 h (S2 search).',
         'Fixing and payout are local and automatic. Payouts wait, already funded, in the outbox.'],
        ['5', 'The access check ignored closures later in the sequence',
         "With a 48 h check window, Mercury's funding was stuck for 335 h because the Mercury–Mars direct path closes "
         "from h 22 to h 357 (S3).",
         f"Change I2 (applied): the check covers the actual length of the sequence. Mercury now completes in "
         f"{h(rel['Mercury']['completion_h'])} h."],
        ['6', 'Sessions are silently lost after an exchange reset',
         f"The worst of {nsearch:,} simulated incidents (S2) is a Mars reset at h {inc['start']:g}, just after the "
         f"handshakes. Mars silently drops the funding transfers, and the senders wait about 100 h for endpoint retries "
         f"plus a 24 h backoff. The futures complete at {h(hit)} h instead of {h(base)} h. The contract still opens "
         f"before the deadline, and no money is at risk.",
         f"Alternative A1: after a reset, the exchange sends a restart notice to its recent peers. The futures then "
         f"complete at {h(a1)} h. A1 is not part of the evaluated design; it is the first change for the next revision."],
        ['7', 'Status reports at scale',
         "If Mars reported to each remote client by direct service, its 12 direct packets per day would cover at most "
         "12 status changes a day for all clients together.",
         'Status travels as batched STATUS records to home exchanges over the backbone (R6), at most one entry per '
         'client per 6 h unless the state changes. Clients still rely on fallbacks.'],
        ['8', 'Single price source', 'Bob may fail or publish conflicting copies.',
         'The fixing falls back to the latest valid earlier observation, or 100. This basis risk is disclosed.'],
        ['9', 'Trust in the custodian exchange', 'Prefunding concentrates exposure on the host exchange.',
         'The brief assumes operators follow the rules. Independent audit is future work.'],
    ]
    t = table('lp{0.17\\linewidth}LL', ['', 'Risk', 'Evidence', 'Treatment'], rows,
              'Risks found during testing, ranked by harm and likelihood.', 'tab:risk')
    return r'''
\section{Risks}\label{sec:risk}
Table~\ref{tab:risk} lists the weaknesses we found, ranked by their expected harm under our own evidence. The most
important ones are interactions between our rules and the orbital geometry. We did not find them by inspecting the
design. They came out of the incident search, the runs at shifted epochs and the runs from the outer settlements.
Changes I1 and I2 are already part of the design evaluated in this paper.

''' + t + '\n'


# ---------------------------------------------------------------------- 6 long term
def longterm_section():
    e4 = E4
    worst = max(e4['routes'].items(), key=lambda kv: kv[1]['max_min'])
    bnd = max(load('e4_bound')['routes'].items(), key=lambda kv: kv[1]['bound_min'])
    wname = worst[0].replace('->', ' to ')
    sat = load('saturation')
    bl = load('backlog')['cases']
    return T(r'''
\section{Long-term operation}\label{sec:long}
\paragraph{The backbone never disconnects.} The two relays are 90\textdegree{} apart on the same circular orbit, and
the link between them always passes at least 2~AU from the Sun. A link between a settlement and a relay is blocked
only when the settlement is almost directly behind the Sun as seen from that relay, at an angle of at least
159\textdegree. This cannot happen for both relays at the same time. Every settlement therefore always has a route of
at most three links to every other settlement, except during maintenance and incidents. Our 200-year scan confirms
this: every settlement had a route to every market host at all <<f"{e4['samples']:,}">> hourly samples. The slowest
one-way route observed was <<wname>> at <<f"{worst[1]['max_min']:.0f}">> minutes. Because a route has at most three links, its
length is at most $(r_a + R) + 4 + (r_b + R)$~AU at any time, where $r_a$ and $r_b$ are the aphelion distances of the two
settlements and $R = 2.83$~AU is the relay radius. With empty queues this bounds every one-way route delay for all time;
the largest bound is <<f"{bnd[1]['bound_min']:.0f}">> minutes (<<bnd[0].replace('->', ' to ')>>). Direct paths, in contrast,
do close for weeks at a time during conjunctions, so every promise that depends on the direct service is conditional.

\paragraph{Long outages and the backlog afterwards.} Only two things have a deadline: orders, which expire after at
most 30 days and release only their own hold, and contract opening deadlines, which return the margin. Transfers,
receipts and payouts wait in durable outboxes. Sessions that are idle for 7 days are reopened. A packet that reaches
the network's 30-day lifetime is replaced by an application resubmission with the same financial identifier. When a
route reopens, each exchange works through its outbox in packets of five transfers, within its 44 routine
originations per day. We say a backlog has \emph{cleared} when every transfer is credited at its destination and the
source holds every RECEIVED. In simulation (Appendix E6), with no competing traffic, 300 transfers from Earth to Mars
are credited within <<f"{bl['one_peer']['no_loss']['last_import_h']:.0f}">> hours and cleared within
<<f"{bl['one_peer']['no_loss']['last_receipt_h']:.0f}">> hours of the route reopening, and in at most
<<f"{bl['one_peer']['loss']['max_receipt_h']:.0f}">> hours in 20 runs with random loss. Other work from the same
exchange shares the 44 routine originations: 300 transfers to each of the eight peers clear in about
<<f"{bl['all_peers']['no_loss']['last_receipt_h'] / 24:.0f}">> days.

\paragraph{Obligations further in the future.} A contract stores its maturity and fixing times as absolute times.
The fixing is a local computation at the host, and the payout transfer is created in the same write. A maturity
several years away therefore needs no message in order to take place.

\paragraph{Capital.} There is no endowment. New capital can enter only through fees or contributions that are debited
from real accounts and moved by R1. Escrow is released only by a fixing or a rejection, so capital cannot leak out of
the system or be created.

\paragraph{Storage and identifiers.} An identifier is 12 bytes: a 32-bit principal prefix and a 64-bit counter. At a
million identifiers per second one principal's counter lasts about 585,000 years. Times are stored as signed 64-bit integer milliseconds,
which covers about 292 million years in each direction. Our simulator uses floating-point seconds, which can no longer
resolve 1~ms after <<f"{E1['float64_ms_limit_years']:,.0f}">> years, so a production system must use integer time and
extended-precision orbital phase. State is bounded: at most 32 live orders per client per host, 256 per host, and 4,096
export slots per host, each an unresolved transfer or a reservation. A remote client's contract instruction reserves
its payout's slot and a home-delivery order its delivery's (one delivery in transit per order). An instruction is
refused if the slots it needs would take the total past 3,276 (80\%), so every payout and delivery has its slot before
it exists. A late top-up to a closed account waits in a restricted balance, owned by the client, until a slot is
free, so slots in use never exceed 4,096. Synthetic capacity tests (Appendix E6; not compliant network scenarios)
confirm both rules.

\paragraph{Compaction without losing duplicate protection.} A source numbers its transfers to each destination
consecutively and sends them in that order. When a transfer is credited, the destination replaces the full record by a \emph{tombstone}: the
transfer identifier, the final state CREDITED and a 32-byte hash of the terms. A later copy that matches a tombstone
only causes another RECEIVED, and a copy whose terms do not match the hash is rejected. For each source the destination
also keeps a \emph{watermark} $W$, the highest number such that every transfer up to $W$ has been credited. Tombstones
at or below $W$ are dropped, because any identifier at or below $W$ is known to be a duplicate. A source does not send
transfer $n$ while any transfer numbered $n - 512$ or lower is unresolved, so every credited transfer above $W$ lies within
512 of it: at most 512 tombstones per source, however long a gap stays open. The source compacts its own export to a tombstone when the
RECEIVED arrives. Order and instruction identifiers are compacted the same way, and any copy that arrives after the
order's expiry or the contract's opening deadline is rejected on that ground alone. The result of a withdrawal,
funding, cancel or close request is kept for 60 days, twice the 30-day packet lifetime, and a copy older than 30 days is
rejected. A 52-byte closure record diverts late top-ups until the host's watermark passes the home's last
funding sent before it learned of the closure; a contract tombstone lasts until its instructions expire (Appendix E6;
design rules, not simulated). Full records can move to an
off-line audit archive; the live ledger needs only balances, open records, tombstones above the watermarks and one
watermark per peer. When a limit is reached the exchange refuses new work; an obligation it has accepted already
holds the capacity it needs.

\paragraph{Accepted demand.} Each exchange can make up to 44 routine backbone originations per day, which is enough
for about 10 new funding or withdrawal transfers between exchanges at 4 to 5 originations each, plus 22 originations
for recovery. Each client has 12 direct packets per day, which is enough for 1 to 4 remote instructions depending on
distance. A forwarding exchange (R9) also has 12 direct packets per day, so it can forward 1 to 4 instructions a day. Work beyond this is queued, and we make no promise about its timing.

\paragraph{Very long horizons.} The connectivity argument and the delay bound above depend only on the shapes of the
orbits, so they hold at every time in the model. The scanned statistics (availability, closure counts and typical
delays) describe only the 200 scanned years. The orbital periods are not commensurate, so the joint configuration of
the bodies never repeats exactly, and we do not extend those numbers beyond the scan. Our evidence for later epochs is
the runs at +1, +10 and +100 years (Appendix E5). With integer milliseconds and extended-precision phase, nothing in the rules depends on the date. The remaining limits are the identifier space described above and the physical infrastructure, which the brief
fixes.
''', locals())


# ---------------------------------------------------------------------- 7 deployment
def deployment_section():
    t = table('p{0.15\\linewidth}p{0.2\\linewidth}LL', ['Effect', 'Estimated size', 'Source and assumptions', 'Effect on the guarantees'], [
        ['Earth rotation', 'About 11.97 h without view per ground station per day',
         'Sidereal day of 23.93 h, one equatorial station, no elevation mask [1]',
         'Delays only, up to 12 h per hop with one station; G1–G5 unchanged.'],
        ['Doppler shift', 'About 3.20 MHz at 32 GHz', 'f·v/c with an assumed line-of-sight speed of 30 km/s [1, 2]',
         'Modems track it; otherwise more loss, which only slows service.'],
        ['Relativistic clock rates', 'Mercury vs Earth: 2.3 × 10⁻⁸, or 0.7 s per year',
         'GM/(rc²) + v²/(2c²) at 0.39 AU and 1 AU', 'Maturity and fixing use TDB; local clocks are corrected.'],
        ['Ephemeris drift', 'Not estimated', 'Kepler elements ignore perturbations between planets',
         'Timetables need a live ephemeris.'],
    ], 'Effects a real deployment would add.', 'tab:deploy')
    return r'''
\section{Deployment assessment}\label{sec:deploy}
The baseline model leaves out several real effects on purpose. None of them can break conservation or cause an asset
to be used twice, because they only delay or lose packets, which the rules already tolerate. They would change our
timings and probabilities. Table~\ref{tab:deploy} estimates their size.

''' + t + r'''

\begingroup\tablefont
\begin{thebibliography}{9}\setlength{\itemsep}{0pt}
\bibitem{fact} NASA, Earth Fact Sheet. \url{https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html}
\bibitem{esa} ESA, Cebreros DSA-2 ground station (Ka-band, 32 GHz).
\bibitem{pfmi} CPMI--IOSCO, \emph{Principles for Financial Market Infrastructures} (delivery versus payment), 2012.
\bibitem{gl} J.~Gray and L.~Lamport, Consensus on Transaction Commit, \emph{ACM TODS} 31(1), 2006.
\end{thebibliography}
\endgroup
'''
