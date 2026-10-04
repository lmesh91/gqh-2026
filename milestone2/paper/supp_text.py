"""Additional evidence sections written for the second review: message formats, backlog and storage, complete
traces for every scenario, per-launch probability tables, state histories and service by product.  Each function
returns one self-contained LaTeX section, so any of them can live in the 12-page appendix or in a supplement."""
from build import *
from geom import SHORT, HOUR
import math
import protocol
from protocol import SIZE, STATUS_MAX, XFER_WINDOW, UNRESOLVED_CAP, ADMIT_LIMIT, DIRECT_SUBHEADER, FWD_HEADER
from transport import HEADER, PAYLOAD, WINDOW


def T(s, env):
    return fill(s, {**globals(), **env})


# ====================================================================== F. formats
COMMON = [('Type', 1, 'Record type code'), ('Version', 1, 'Format version (1)'), ('Length', 2, 'Record length in bytes'),
          ('Record ID', 12, '32-bit principal prefix and 64-bit counter; never reused'),
          ('Created', 8, 'Signed 64-bit integer milliseconds of TDB since the epoch'),
          ('Signature', 64, 'Ed25519 by the issuing principal over every other byte of the record')]
BODIES = {
    'TRANSFER': [('Source exchange', 1), ('Destination exchange', 1), ('Purpose', 1), ('Asset', 1), ('Owner account', 8),
                 ('Amount (units or cents)', 8), ('Number n to this destination', 8), ('Reference ID (order, contract, request)', 12),
                 ('Beneficiary account', 8), ('Terms digest (SHA-256)', 32), ('Reserved', 8)],
    'RECEIVED': [('Transfer ID', 12), ('Source exchange', 1), ('Result (credited, restricted)', 1), ('Import time', 8),
                 ('Watermark W for this source', 8), ('Reserved', 2)],
    'ORDER': [('Account', 8), ('Host', 1), ('Asset', 1), ('Side', 1), ('Time in force', 1), ('Quantity', 8),
              ('Limit price (cents)', 8), ('Expiry', 8), ('Disposition (keep, home)', 1), ('Reserved', 3)],
    'CANCEL': [('Account', 8), ('Target order ID', 12), ('Reserved', 20)],
    'WITHDRAW': [('Account', 8), ('Asset', 1), ('Destination exchange', 1), ('Amount', 8), ('Reserved', 22)],
    'CLOSE': [('Account', 8), ('Reserved', 32)],
    'CINSTR': [('Account', 8), ('Contract ID', 12), ('Role (long, short)', 1), ('Quantity Q', 8), ('Multiplier', 4),
               ('Opening price K', 8), ('Floor', 8), ('Cap', 8), ('Five observation times', 40), ('Maturity', 8),
               ('Fixing time', 8), ('Opening deadline', 8), ('Counterparty account', 8), ('Price source', 8),
               ('Margin', 8), ('Reserved', 23)],
    'STATUS': [('Host exchange', 1), ('Home exchange', 1), ('Entry count m (1 to 52)', 2), ('As-of time', 8),
               ('Reserved', 12), ('Entry 1: account 8, contract counter 6, state 1, flags 1', 16)],
    'PRICE': [('Contract ID', 12), ('Observation number', 1), ('Index value (fixed point)', 8), ('Observation time', 8),
              ('Price source', 8), ('Source attestation (Ed25519)', 64), ('Reserved', 11)],
    'MDS': [('Market exchange', 1), ('Asset', 1), ('Book version', 8), ('Best bid (cents)', 8), ('Bid size', 4),
            ('Best ask (cents)', 8), ('Ask size', 4), ('Last trade price (cents)', 8), ('Last trade size', 4),
            ('Last trade time', 8), ('Reserved', 10)],
    'MDREQ': [('Requesting exchange', 1), ('Asset', 1), ('Reserved', 30)],
}
PACKETS = [
    ('Network header (brief)', '64', 'Every packet; defined by the network'),
    ('Data sub-header', '16', 'Session 8, data sequence 4, record count 2, flags 2'),
    ('Data packet', '64 + 16 + records', 'Whole records, at most 944 bytes of records'),
    ('SYN, SYN-ACK, ACK, DACK payload', '96', 'Session 8, route 4, data sequence 4, attempt 1, kind 1, reserved 6, '
                                              'time 8, signature 64'),
    ('Hop receipt payload', '16', 'Packet ID 12, launch number 1, reserved 3'),
    ('Direct sub-header', '16', 'Principal 8, packet sequence 4, instruction count 1, flags 1, reserved 2'),
    ('Direct packet', '64 + 16 + instructions', 'Whole signed instructions, at most 944 bytes'),
    ('FWD wrapper (R8)', '24 + inner', 'Forwarder 1, target host 1, attempt 1, flags 1, forward time 8, origin '
                                       'principal 8, inner length 2, reserved 2'),
]


def formats():
    common = sum(b for _, b, _ in COMMON)
    brow, crow = [], []
    for k, fields in BODIES.items():
        tot = common + sum(b for _, b in fields)
        assert tot == SIZE[k], (k, tot, SIZE[k])            # the paper's layout is the simulator's size
        brow.append([k, str(tot), '; '.join(f'{n} {b}' for n, b in fields)])
    room = PAYLOAD - 16
    for k in ('TRANSFER', 'RECEIVED', 'ORDER', 'CANCEL', 'WITHDRAW', 'CLOSE', 'CINSTR', 'PRICE', 'MDS', 'MDREQ'):
        n = room // SIZE[k]
        fw = (room - FWD_HEADER) // SIZE[k] if k in ('ORDER', 'CANCEL', 'WITHDRAW', 'CLOSE', 'CINSTR') else None
        crow.append([k, SIZE[k], n, HEADER + 16 + n * SIZE[k], '—' if fw is None else fw])
    smax = SIZE['STATUS'] + 16 * (STATUS_MAX - 1)
    crow.append([f'STATUS ({STATUS_MAX} entries)', smax, 1, HEADER + 16 + smax, '—'])
    tc = table('lL', ['Field', 'Bytes and meaning'], [[n, f'{b}: {m}'] for n, b, m in COMMON] + [['Total', f'{common}']],
               'Common header of every application record.', 'tab:fcommon')
    tb = table('lrL', ['Record', 'Bytes', 'Fields after the common header (bytes)'], brow,
               'Fixed-width body of each record type. The totals are the sizes the simulator charges '
               '(\\texttt{protocol.SIZE}); the build checks that the fields add up to them. A STATUS record grows by '
               '16 bytes for each entry after the first.', 'tab:fbody', sep='3pt')
    tp = table('llL', ['Unit', 'Bytes', 'Layout'], PACKETS, 'Packet layouts. Every packet is at most 1,024 bytes: the '
               "brief's 64-byte header and at most 960 bytes of payload.", 'tab:fpkt', sep='3pt')
    tcap = table('lrrrr', ['Record', 'Bytes', 'Per packet', 'Packet bytes', 'Per FWD packet'], crow,
                 'Capacity. A data or direct packet carries a 16-byte sub-header and up to 944 bytes of whole records. '
                 '``Packet bytes\'\' is the full packet at that count, header included; it never exceeds 1,024. The last '
                 'column is the number of client instructions that still fit when R8 wraps the batch in a 24-byte FWD '
                 'header.', 'tab:fcap', sep='4pt')
    return T(r'''
\section*{F. Message formats and sizes}
Every message has a fixed-width binary layout. The tables below give every field, and the record sizes are the
ones the simulator uses for packing. Integers are unsigned big-endian unless a field says otherwise. Times are signed
64-bit integer milliseconds of TDB since the epoch. Money is in integer cents, and share quantities are whole shares.
Each record carries the signature of the principal that issued it, so it can be checked at any exchange whatever
session or forwarder carried it.

<<Raw(tc)>>
<<Raw(tb)>>
<<Raw(tp)>>
<<Raw(tcap)>>

\paragraph{Packing and splitting rules.}
(1) A record is never split across packets. The sender takes records from the outbox for one peer in order and
adds whole records while the payload stays within 960 bytes (16-byte sub-header plus at most 944 bytes of records);
the next record starts a new packet. Every fixed record is at most 256 bytes, so up to 5 transfers, 7 receipts or
3 contract instructions fit in one packet (Table~\ref{tab:fcap}). The simulator's packer asserts that every record is
between 1 and 944 bytes.
(2) STATUS is the only variable-length record. It is closed at <<STATUS_MAX>> entries
(<<smax>> bytes). If more remote clients need an entry at the same moment, the host writes further STATUS records,
each a complete signed record of its own.
(3) A client may batch whole instructions in one direct packet, up to 944 bytes. A larger batch is split into
several direct packets, and each one counts against the client's 12 per day. A batch that may need forwarding (R8)
is limited to 920 bytes so that the 24-byte FWD header still fits; a forwarding exchange forwards each received
packet as one FWD packet and never merges or splits them. The simulator asserts this limit on every direct send.
(4) RECEIVED records are not sent alone if other records for the same peer are waiting: they share packets with
whatever is in the outbox. A packet that holds only receipts uses the reserve quota (Section E6).

\paragraph{Examples.} The S1a funding packet holds one TRANSFER: 64 + 16 + 176 = 256 bytes. A backlog packet with five
transfers is 64 + 16 + 880 = 960 bytes. A STATUS record with one entry is 128 bytes and one with 52 entries is 944 bytes. The
S1i batch of two orders is a direct packet of 64 + 16 + 256 = 336 bytes, and a forwarded order is 64 + 16 + 24 + 128 =
232 bytes.
''', locals())


# ====================================================================== E6. backlog and storage
def e6():
    B = load('backlog')
    C = B['cases']
    lab = {'one_peer': 'One peer', 'both_ways': 'Both ways', 'all_peers': 'All peers', 'over_window': 'Over window'}
    rows = []
    for k, name in lab.items():
        c = C[k]
        z, L = c['no_loss'], c['loss']
        src = 'Earth'
        rows.append([name, f"{z['n']:,}", z['originations'][src], z['peak24'][src], h(z['last_import_h'], 1),
                     h(z['last_receipt_h'], 1), f"{L['all_cleared']}/{L['runs']}", h(L['median_receipt_h'], 1),
                     h(L['max_receipt_h'], 1), max(L['peak24'].values()), z['held']])
    tb = table('lrrrrrrrrrr', ['Case', 'N', 'Orig.', 'Peak', 'Imported', 'Resolved',
                               'Cleared', 'Median', 'Max', 'Peak any', 'Held'], rows,
               'Backlog after an outage. All transfers are already in the outbox at hour 0. One peer: 300 transfers from '
               'Earth to Mars. Both ways: 300 each way between Earth and Mars. All peers: 300 from Earth to each of the '
               '8 other exchanges. Over window: 1,200 from Earth to Mars. ``All imported\'\' is when '
               'the last one is credited at its destination and ``All resolved\'\' when the source holds every RECEIVED '
               '(hours, no loss). N is the number of transfers. Orig.\\ and Peak are Earth\'s originations in total and in its busiest 24 hours '
               '(limit 66, of which 44 routine). The lossy columns use 20 runs (5 for the last row): runs fully resolved '
               'within 40 days, median and maximum time to resolve, and (Peak any) the highest 24-hour origination count of any '
               'exchange in any run. Held counts transfers that waited for the window of 512.', 'tab:e6backlog',
               sep='2pt')
    one = C['one_peer']['no_loss']
    allp = C['all_peers']['no_loss']
    srows = [
        ['Live orders', '32 per client per host; 256 per host', 'Order refused', 'Orders expire within 30 days'],
        ['Export slots (unresolved exports plus reserved payouts and deliveries)', f'{UNRESOLVED_CAP:,} per host',
         f'An instruction needing slots is refused if slots in use would exceed {ADMIT_LIMIT:,} (80\\%)',
         'Payouts and deliveries hold their slot from acceptance; returns of late top-ups use only free slots and '
         'otherwise wait'],
        ['Late top-ups awaiting return', 'One restricted balance per closed account, asset and source', 'Waits, owned by the '
         'client, until a slot is free', 'Later top-ups merge into it; never more slots than the cap'],
        ['Transfers in flight to one destination', f'Window of {XFER_WINDOW}', f'Transfer n waits (debited, durable) '
         f'while any transfer numbered n − {XFER_WINDOW} or lower is unresolved', 'Sent in number order; bounds the destination\'s tombstones'],
        ['Transfer tombstones above the watermark', f'At most {XFER_WINDOW} per source', 'Cannot be exceeded',
         '45 bytes each: ID 12, state 1, terms digest 32'],
        ['Request results (withdrawal, funding, cancel, close)', 'Kept 60 days after the request\'s creation time',
         'A copy older than 30 days is rejected as expired', 'At most 64 requests per account per host per day'],
        ['Account closure record', '52 bytes until the host\'s watermark for the home passes the home\'s last '
         'transfer sent before it learned of the closure, and every return is resolved', '—', 'Diverts late top-ups; the home sends none after (not simulated)'],
        ['Contract records', 'Full record until both payouts are resolved, then a tombstone until 30 days after the '
         'opening deadline', '—', 'Every instruction copy has expired by then (not simulated)'],
    ]
    SA = load('saturation')
    def sat_row(name, f):
        return [name, f(SA['new']), f(SA['old'])]
    srow = [
        sat_row('Contract instructions accepted / refused', lambda r: f"{r['accepted']['CINSTR']:,} / {r['refused']['CINSTR']:,}"),
        sat_row('Delivery orders accepted / refused', lambda r: f"{r['accepted']['ORDER']:,} / {r['refused']['ORDER']:,}"),
        sat_row('Withdrawals accepted / refused', lambda r: f"{r['accepted']['WITHDRAW']:,} / {r['refused']['WITHDRAW']:,}"),
        sat_row('Payouts resolved', lambda r: f"{r['payouts_resolved']:,} of {r['payouts']:,}"),
        sat_row('Shares delivered (transfers)', lambda r: f"{r['shares_delivered']:,.0f} of {r['shares_filled']:,.0f} ({r['deliveries']})"),
        sat_row('Peak unresolved exports', lambda r: f"{r['peak_unresolved']:,}"),
        sat_row('Peak slots in use (incl. reserved)', lambda r: f"{r['peak_committed']:,}"),
        sat_row(f'Hours above the {UNRESOLVED_CAP:,} cap', lambda r: f"{r['over_cap_h']:.1f}"),
        sat_row('Last RECEIVED (h)', lambda r: f"{r['last_receipt_h']:.0f}"),
        sat_row('Pending shares / reserved slots at end', lambda r: f"{r['pending_left']:.0f} / {r['reserved_left']}"),
    ]
    tsat = table('Lrr', ['Mars at its limits', 'Reservation', 'Unresolved only'], srow,
                 'Synthetic capacity test at Mars (not a compliant network scenario): the reservation rule against '
                 'the earlier admission rule.', 'tab:e6sat')
    RT = SA['returns']
    ts = table('p{0.2\\linewidth}p{0.2\\linewidth}LL', ['State', 'Limit', 'When the limit is reached', 'Note'], srows,
               'Bounded state at each exchange.', 'tab:e6state', sep='3pt')
    return T(r'''
\section*{E6. Quota, backlog and storage}
\paragraph{Two quota classes.} Each exchange may originate 66 backbone packets in any rolling 24 hours. A data
packet that carries any record other than RECEIVED is \emph{routine} and may be sent only while the exchange has made
fewer than 44 originations in the last 24 hours. SYN packets, packets that carry only RECEIVED records, and
application resubmissions may use all 66. So at least 22 originations a day always remain for recovery and receipts,
however much new work is queued. The simulator enforces both limits (\texttt{transport.Quota}, \texttt{reserve=22}).
When routine work is blocked, waiting receipts are taken out of the queue and sent in packets of their own.

\paragraph{Backlog experiment.} \texttt{backlog.py} puts a queue of \$100 transfers into the outboxes at hour 0, which
is the situation at the end of a long outage, and runs until everything is resolved (Table~\ref{tab:e6backlog}).
Three hundred transfers to one peer fill 60 data packets of five, plus one SYN. Earth sends 44 originations at once
and the remaining <<one['originations']['Earth'] - 44>> when the first ones leave the 24-hour window, so all
transfers are imported by hour <<h(one['last_import_h'], 1)>> and resolved by hour <<h(one['last_receipt_h'], 1)>>.
Mars uses <<one['originations']['Mars']>> originations for the receipts, which it may send from its reserve. With
random loss every run cleared, with a median of <<h(C['one_peer']['loss']['median_receipt_h'], 1)>> hours. Traffic
in both directions costs little extra, because receipts share packets with the reverse transfers. A backlog to all
eight peers at once is limited by Earth's own 44 routine originations a day: 2,400 transfers need about 490 packets,
or 11 days, and they resolve by hour <<h(allp['last_receipt_h'], 0)>>. The 1,200-transfer case shows the window: the
first 512 transfers go out and the rest wait until receipts come back.

\paragraph{What ``clears'' means.} A backlog has cleared when every transfer is credited at its destination and the
source has its RECEIVED, so no unresolved state remains. Credit comes earlier than resolution by at most one
route delay plus the receipt's queueing. The claim in the design paper is therefore: \emph{when no other traffic
competes, 300 transfers to one peer are credited within about 25 hours and resolved within about 26 hours of the route
reopening; competing traffic from the same exchange shares its 44 routine originations a day.}

<<Raw(tb)>>

\paragraph{Window and compaction.} A source numbers its transfers to each destination consecutively, sends them in
that order, and does not send transfer $n$ while any transfer numbered $n - <<XFER_WINDOW>>$ or lower is unresolved
(equivalently, $n < u + <<XFER_WINDOW>>$ for the lowest unresolved number $u$). Let $u$ be the lowest unresolved number at the source.
Every transfer below $u$ has a RECEIVED, so it was credited and the destination's watermark satisfies $W \ge u - 1$.
The source has sent nothing at or above $u + <<XFER_WINDOW>>$. The credited transfers above $W$ therefore all lie in
$[u, u + <<XFER_WINDOW - 1>>]$, so the destination never keeps more than <<XFER_WINDOW>> tombstones per source,
about 23~KB, however long a gap stays open. A transfer held by the window has already been debited and is durable at
the source; it is in transit and still owned by the client, exactly like a transfer waiting for an open link.
The simulator implements the window (\texttt{protocol.XFER\_WINDOW}); in the 1,200-transfer case
<<C['over_window']['no_loss']['held']>> transfers were held and released in order.

\paragraph{Admission and reservation.} An exchange has <<f"{UNRESOLVED_CAP:,}">> export slots. A slot is in use
while an export is unresolved or while it is \emph{reserved} for a transfer the exchange has promised. Accepting a
remote client's contract instruction reserves one slot for that party's payout home; the slot is freed if the contract
never opens, and used by the payout otherwise. Accepting a remote client's order with home delivery reserves one slot
for its delivery. An order has at most one delivery in transit: shares filled while it travels are added to a pending
amount, sent in one transfer when the RECEIVED returns, and the slot is kept while the order rests. Funding,
withdrawal and close each need slots for their own transfers. An instruction is refused (``try later'') if the slots
in use plus those it needs would exceed <<f"{ADMIT_LIMIT:,}">>; local trading continues. A payout or delivery
therefore always finds its slot already held. The live-order limits (32 per client, 256 per host) are enforced at
order entry.

\paragraph{Returns of late top-ups.} A transfer to a closed account is the one export the host cannot refuse in advance:
the home may have sent it before it learned of the closure, and each of the eight other exchanges may have up to
<<XFER_WINDOW>> transfers in flight, so their number is not bounded by the spare <<f"{UNRESOLVED_CAP - ADMIT_LIMIT:,}">>
slots. The host credits such a transfer to a \emph{restricted} balance, still owned by the client and usable for
nothing but its return, and records one return entry per closed account, asset and source; a later top-up for the
same entry adds to it. A return is exported only while slots in use are below the hard cap of
<<f"{UNRESOLVED_CAP:,}">>, oldest entry first; otherwise it waits. Because returns use only free slots and admission
counts them, slots in use never exceed the cap, and the reserved slots of payouts and deliveries are never taken. The
waiting entries are bounded by the number of closed accounts times assets times sources, each one balance row. Every
waiting return keeps a funded owner: the money stays in the client's restricted balance at the host until the return
is exported, and is then in transit, still the client's, until it is credited at home.

\paragraph{Synthetic capacity tests.} \texttt{saturation.py} tests the ledger's capacity rules, not the network
scenario: it is not a compliant workload under the brief. It uses about 5,250 synthetic client identities instead of
the six opening accounts, injects their instructions at the Mars ledger without the 12-packet direct quota or R6
retries (2,000 contract instructions alone would need at least 667 direct packets, against 72 a day for the six real
clients), and places their cash at Mars directly instead of funding it. Backbone transport, its quotas and the
transfer window are real. Within two hours Mars receives 2,000 contract instructions (1,000 contracts of 48 hours),
250 home-delivery buy orders filled three shares every 30 minutes, and 3,000 withdrawals. Table~\ref{tab:e6sat} compares the reservation rule with the earlier rule
that counted only unresolved exports. Under the earlier rule every request was accepted and unresolved exports reached
<<f"{SA['old']['peak_unresolved']:,}">>, above the cap for <<f"{SA['old']['over_cap_h']:.0f}">> hours: the payouts
were owed but had no capacity. Under the reservation rule the withdrawals that did not fit were refused at the door,
slots in use never exceeded <<f"{SA['new']['peak_committed']:,}">>, and every payout and delivery went out.

<<Raw(tsat)>>

A second test fills Mars to the admission limit with <<f"{RT['fill']:,}">> withdrawals in flight and then delivers
<<f"{RT['late']:,}">> top-ups from all <<RT['sources']>> other exchanges (<<RT['late'] // RT['sources']>> each) to
accounts already closed at Mars, three times the spare slots. Slots in use peaked at <<f"{RT['peak_committed']:,}">>
and never exceeded the cap; up to <<f"{RT['peak_waiting']:,}">> returns waited at once.
<<'All' if RT['returns_resolved'] == RT['late'] else 'Not all'>> <<f"{RT['returns_resolved']:,}">> returns were
resolved, the last at hour <<f"{RT['last_return_h']:.0f}">>; <<'every' if RT['all_home'] else 'not every'>>
client's \$1,000 was back at home, and no restricted balance remained.

Table~\ref{tab:e6state} lists every bounded part of an exchange's state.

\paragraph{Retention of request results.} Withdrawal, funding, cancel and close requests carry a per-account request
number and a creation time. The exchange keeps each result (request ID, outcome, terms digest and transfer ID, 57
bytes) for 60 days after the creation time, which covers the brief's 30-day packet lifetime and
its 30-day duplicate retention. A copy created more than 30 days ago is rejected on that ground alone, so a dropped result can never be
executed twice. A closed account keeps a 52-byte closure record so that a late top-up is returned, at least until
every return for it is resolved. Once the home
exchange learns of the closure it accepts no more funding for that account, so the record is dropped when the host's
watermark for the home passes the last transfer the home sent before learning of it. A contract record becomes a
tombstone once both payouts are resolved and is dropped 30 days after the opening deadline, when every copy of its
instructions has expired. These retention rules are design rules: the simulator keeps every result and record for the whole
run (at most 1,600 hours), so it does not exercise the 60-day expiry.

<<Raw(ts)>>
''', locals())


# ====================================================================== complete traces, S1 and S3
PARTIES = {'S1a': (['Alice', 'Bob'], ('ARES',)), 'S1b': (['Alice', 'Cara'], ('BELT',)), 'S1c': (['Eve', 'Fin'], ('TERRA',)),
           'S1d': (['Alice', 'Cara'], ()), 'S1e': (['Alice', 'Cara'], ()), 'S1f': (['Alice', 'Cara'], ()),
           'S1g': (['Alice', 'Cara'], ()), 'S1h': (['Alice', 'Cara'], ()), 'S1i': (['Alice', 'Bob'], ('ARES',))}
_RUNS = {}


def traced(key):
    """One traced run per scenario (S1 keys, or 'S3:<home>' for the relocated purchase), cached."""
    if key not in _RUNS:
        import traces
        from evidence import SCEN, relocated_book
        from scenarios import equity
        if key.startswith('S3:'):
            who, assets = ['Alice', 'Bob'], ('ARES',)
            w, tr, sn = traces.run_traced([(equity, dict(tag='EQ'))], who, assets, until_h=900,
                                          book=relocated_book(key[3:]))
        else:
            who, assets = PARTIES[key]
            sc = SCEN[key]
            w, tr, sn = traces.run_traced(sc['spec'], who, assets, until_h=sc['until'])
        _RUNS[key] = (w, tr, sn, who, assets)
    return _RUNS[key]


def trace_rows(rows):
    out = []
    for r in rows:
        st = esc(r[-1]).replace('<b>', r'\textbf{').replace('</b>', '}').replace('<br>', '; ')
        out.append([*r[:-1], Raw(st)])
    return out


TRACE_COLS = ''.join(r'>{\raggedright\arraybackslash}p{' + w + '}'
                     for w in ('0.55in', '0.6in', '0.72in', '1.05in', '1.05in', '0.55in', '1.45in'))
TRACE_HEAD = ['h', 'Actor', 'Knows', 'Does', 'Packet or transmission', 'Arrives', 'Financial state after']
TITLES = {'S1a': 'S1a: Alice (Earth) buys 1,000 Ares from Bob (Mars) at \\$100',
          'S1b': 'S1b: Alice (Earth) buys 1,000 Belt from Cara (Ceres) at \\$100',
          'S1c': 'S1c: Eve (Uranus) buys 400 Terra from Fin (Earth) at \\$100',
          'S1d': 'S1d: capped futures, rising path, $Q = 2{,}000$ (Alice long, Cara short)',
          'S1e': 'S1e: capped futures, falling path, $Q = 2{,}000$',
          'S1f': 'S1f: capped futures, boundary case $Q = 2{,}500$',
          'S1g': 'S1g: capped futures, $Q = 2{,}501$ (Cara cannot fund; Alice is refunded)',
          'S1h': 'S1h: capped futures, $Q = 4{,}000$ (both fundings refused at home)',
          'S1i': 'S1i: repeat trading on a \\$10,000 Mars account'}


def full_trace(key, label=None, title=None):
    import traces
    w, tr, sn, who, assets = traced(key)
    rows = traces.rows_for(w, tr, sn, who, assets)
    return longtab(TRACE_COLS, TRACE_HEAD, trace_rows(rows), 'Complete trace of ' + (title or TITLES[key]) +
                   '. Every ledger event, direct message and status message is shown.', label or f'tab:tr{key}')


def s1_traces():
    parts = [r'''
\clearpage
\section*{T. Complete traces}
These tables give every row of every S1 run and of the three S3 relocations discussed in the text, in the brief's
seven-column format. Rows come from the simulator's event stream. The financial state is the ledger snapshot
immediately after the event, for the parties named in the caption: ``free at host'' is available at the market,
``held'' is an order or instruction hold, and ``margin'' is contract escrow. A local instruction is shown when it
arrives at the exchange, 1~s after the client sends it (the send time is in the packet column), so that every row's
state is the state after that row. Packet columns list each backbone DATA launch of the record by hop; the
handshake, acknowledgements and hop receipts of every session are in \texttt{traces/<run>\_launches.csv}, whose
counts are Table~\ref{tab:s1sum}. The runs have no loss, so every first launch arrives.
''']
    for k in PARTIES:
        parts.append(full_trace(k))
    return '\n'.join(parts)


def s3_traces(homes):
    parts = [r'''
\paragraph{S3 relocations.} The same \$100,000 Ares purchase with Alice's account moved to the best, median and worst
homes of Table~\ref{tab:s3rel}.
''']
    for name, home in homes:
        parts.append(full_trace(f'S3:{home}', f'tab:trS3{home}',
                                f'the S3 relocation, {name} home: Alice at {home} buys 1,000 Ares from Bob (Mars)'))
    return '\n'.join(parts)


# ====================================================================== E2, complete
def _sh(n):
    return SHORT.get(n, n)


def e2_complete():
    F = load('e2_full')['runs']
    drows = []
    for k, r in F.items():
        for m in r['direct']:
            drows.append([k, m['principal'].replace(' exchange (agent)', ' (R8)'), f"{_sh(m['a'])}→{_sh(m['b'])}",
                          m['label'].replace('+', ' + ').replace('FWD:', 'FWD '), m['copies'], f"{m['p_each']:.4f}",
                          h(m['t_arrive_h'], 3), f"{m['p_first']:.4f}", h(m['t_last_arrive_h'], 3),
                          f"{m['p_success']:.6f}"])
    td = longtab('lllLrrrrrr', ['Run', 'Sender', 'Path', 'Message', 'Copies', 'p each', 'First h', 'P by then',
                                'Last h', 'P(arrives)'], drows,
                 'Every direct message in every S1 run (exact). ``First h\'\' is the arrival of the first copy, the time '
                 'used in the traces, and ``P by then\'\' the probability that the message has arrived by then. '
                 'P(arrives) is the probability that at least one copy arrives, reached at the last copy\'s arrival. '
                 'S1h sends no direct message: both fundings are refused at home.', 'tab:e2alldirect', lw='2.6cm')
    hrows, srows = [], []
    for k, r in F.items():
        for x in r['hops']:
            what = x['kind'] + (f" ({x['carries'].replace('TRANSFER', 'TR').replace('RECEIVED', 'RCV')})" if x['carries'] else '')
            hrows.append([k, h(x['t_h'], 3), f"{_sh(x['a'])}→{_sh(x['b'])}", what, f"{x['d']:.2f}",
                          f"{x['p_data']:.4f}", f"{x['p_receipt']:.4f}", f"{x['p_unconf']:.4f}", f"{x['p_abandon']:.1e}", f"{x['p_abandon_bound']:.1e}"])
        srows.append([k, len(r['direct']), len(r['hops']), f"{r['p_all_first']:.4f}", f"{r['p_any_abandon']:.1e}",
                      f"{r['p_any_abandon_bound']:.1e}"])
        assert r['all_open_certified']
    th = longtab('lrllrrrrrr', ['Run', 'Launch h', 'Hop', 'Packet', 'd (AU)', 'p data', 'p rcpt',
                               'p unconf.', 'P(aband.)', 'Bound'], hrows,
                 'Every backbone launch of every S1 run except hop receipts, with its per-launch probabilities. '
                 '``p unconf.\'\' is the chance that the launch is not confirmed: the data or its hop receipt is lost, '
                 '$1 - (1 - p_\\text{data})(1 - p_\\text{receipt})$. P(aband.) is the chance that the hop is abandoned '
                 'after four unconfirmed launches, $u_1 u_2 u_3 u_4$ with each retry at the hop timer and its own geometry; Bound '
                 'holds only if no retry is delayed by more than 24 hours (Section E2). '
                 'TR = TRANSFER, RCV = RECEIVED.', 'tab:e2alllaunch', sep='1.6pt')
    ts = table('lrrrrr', ['Run', 'Direct msgs', 'Backbone launches', 'P(no backbone retry)', 'P(some hop abandoned)', 'Bound'],
               srows, 'Per-run summary of Tables~\\ref{tab:e2alldirect} and~\\ref{tab:e2alllaunch}. The first '
               'probability is the chance that every backbone hop is confirmed at its first launch (direct copies not included); the second is '
               'the chance that at least one hop is abandoned and endpoint recovery takes over (exact, then the 24-hour-delay bound).', 'tab:e2sum')
    mrows = []
    for k in ('S1a', 'S1b', 'S1c', 'S1d', 'S1e'):
        m = E2[k]
        mrows.append([k, 'completion', f"{m['completed']}/{m['n']}", h(m['p50']), h(m['p90']), h(m['p99']), h(m['max']),
                      f"{3 / m['n']:.2%}" if m['completed'] == m['n'] else '—'])
    for k in ('S1f', 'S1g', 'S1i'):
        m = F[k]['mc']
        mrows.append([k, 'margin home' if k == 'S1g' else 'completion', f"{m['completed']}/{m['n']}", h(m['p50']),
                      h(m['p90']), h(m['p99']), h(m['max']), f"{3 / m['n']:.2%}" if m['completed'] == m['n'] else '—'])
    tm = table('llrrrrrr', ['Run', 'End point', 'Done', 'Median h', 'p90 h', 'p99 h', 'Max h', '95\\% bound'], mrows,
               'Monte Carlo under random loss for every S1 run with network traffic (2,000 runs each). The last column '
               'is the 95\\% upper confidence bound on the probability of not reaching the end point within the run '
               '(1,500 hours) when no run failed (rule of three, $3/n$). S1h has no network traffic.', 'tab:e2allmc',
               sep='3pt')
    return T(r'''
\clearpage
\section*{E2+. Every message and every launch}
Table~\ref{tab:e2alldirect} lists every direct message of every S1 run, including the S1b order to Ceres, the S1g
withdrawal after the deadline and the S1i batches. Table~\ref{tab:e2alllaunch} lists every backbone launch except
the hop receipts, which are the second factor of each row's probability. Table~\ref{tab:e2sum} summarises them per
run.

<<Raw(td)>>
<<Raw(ts)>>

\paragraph{What the Monte Carlo shows and does not show.} Every lossy run reached its end point within the run
(Table~\ref{tab:e2allmc}). With 2,000 runs and no failure, the probability of failing within 1,500 hours is below
0.15\% at 95\% confidence; the simulations alone cannot show more. Completion with probability one rests on the
rules, not on the sample. A transfer is resubmitted after every delivery-unknown, without limit. Each attempt crosses
a route of at most three links whose lengths are bounded for all time (E4), so it succeeds with probability at least
some $q > 0$, and after $k$ attempts it is still undelivered with probability at most $(1 - q)^k$, which goes to zero.
A client request is resent by R6 until it is 30 days old. A completion \emph{time} is never certain: every table
gives a distribution, and the no-loss trace time is its best case.

<<Raw(tm)>>
<<Raw(th)>>
''', locals())


# ====================================================================== E3, complete
def opening_table(label='tab:open', compact=False):
    """The opening balance sheet as an account table (from protocol.OPENING_BOOK)."""
    if compact:
        bk = protocol.OPENING_BOOK
        tot = lambda f: sum(f(x) for x in bk)
        rows = [['Home'] + [x[1] for x in bk] + ['5 settlements'],
                ['NeoDollars'] + [money(x[2]) for x in bk] + [money(tot(lambda x: x[2]))]]
        for a in ('ARES', 'BELT', 'TERRA'):
            rows.append([a.title()] + [f"{x[3][a]:,}" if x[3].get(a) else '—' for x in bk] +
                        [f"{tot(lambda x: x[3].get(a, 0)):,}"])
        return table('l' + 'r' * (len(bk) + 1), ['Account'] + [x[0] for x in bk] + ['Total'], rows,
                     'Opening balances at hour 0, all available at the home exchange. Remote accounts, holds, escrow, '
                     'transit and the exchanges\' own accounts are all zero.', label)
    rows = []
    tot = {'ND': 0, 'ARES': 0, 'BELT': 0, 'TERRA': 0}
    for acct, home, cash, shares in protocol.OPENING_BOOK:
        rows.append([acct, home, money(cash), *(f"{shares.get(a, 0):,}" if shares.get(a) else '—'
                                                for a in ('ARES', 'BELT', 'TERRA'))])
        tot['ND'] += cash
        for a, q in shares.items():
            tot[a] += q
    rows.append(['Total', '5 settlements', money(tot['ND']), f"{tot['ARES']:,}", f"{tot['BELT']:,}", f"{tot['TERRA']:,}"])
    rows.append(['Each exchange (own account)', 'all 9', '$0', '—', '—', '—'])
    return table('llrrrr', ['Account', 'Home exchange', 'NeoDollars', 'Ares', 'Belt', 'Terra'], rows,
                 'Opening balance sheet at hour 0. Every balance is available at the account\'s home exchange; remote '
                 'trading accounts, holds, escrow and transit are all zero. The share registries record the same '
                 'custody: Mars 3,000 Ares at Mars, Ceres 1,000 Belt at Ceres, Earth 1,000 Terra at Earth.', label)


def _label(e):
    k = e['kind']
    ref = e.get('eid') or e.get('oid') or e.get('cid') or e.get('req') or ''
    if k == 'FILL':
        return f"Fill {e['qty']:,} {e['asset'].title()} @ ${e['price']}"
    if k in ('EXPORT', 'IMPORT'):
        return f"{k.title()} {ref} ({e.get('purpose', '').lower().replace('_', ' ')})"
    return (k.replace('_', ' ').capitalize() + (f' {ref}' if ref else '')).strip()


def state_history(key):
    """Every change of the named parties' positions: one row per (event, account, asset) that changed."""
    from protocol import CASH
    w, tr, sn, who, assets = traced(key)
    t0 = w.t0
    keys = [(p, a) for p in who for a in (CASH,) + tuple(assets)]

    def pos(st, p, a):
        x = st[a][p]
        return (x['home'], x['remote'], x['held'] + x.get('escrow', 0), x['transit'])
    prev = None
    rows = []
    for e, st in zip(w.events, sn):
        cur = {k: pos(st, *k) for k in keys}
        if prev is not None:
            for (p, a) in keys:
                if cur[(p, a)] != prev[(p, a)]:
                    f = (lambda v: money(v)) if a == CASH else (lambda v: f'{v:,}')
                    rows.append([h((e['t'] - t0) / HOUR, 4), _label(e), p, 'ND' if a == CASH else a.title(),
                                 *(f(v) if v else '0' for v in cur[(p, a)])])
        prev = cur
    return rows


def settlement_moments(key):
    """Every obligation of the run: when it was created, discharged, backed by a funded transfer and spendable."""
    w, tr, sn, who, assets = traced(key)
    t0 = w.t0
    hh_ = lambda t: h((t - t0) / HOUR, 3) if t is not None else '—'
    rows = []
    for e in w.events:
        if e['kind'] == 'FILL':
            rows.append([key, f"Fill {e['qty']:,} {e['asset'].title()} @ ${e['price']}: {e['buyer']} from {e['seller']}",
                         hh_(e['t']), hh_(e['t']), 'local', hh_(e['t']) + ' at host'])
        elif e['kind'] == 'CONTRACT_OPEN':
            rows.append([key, f"Contract {e['cid']} (escrow {money(e['escrow'])})", hh_(e['t']),
                         'at fixing', 'escrow from ' + hh_(e['t']), '—'])
        elif e['kind'] == 'CONTRACT_FIXED':
            rows.append([key, f"Fixing of {e['cid']} at {e['P']}", hh_(e['t']), hh_(e['t']), hh_(e['t']) + ' (payouts)', '—'])
    for L in w.ledgers.values():
        for x in L.exports.values():
            amt = money(x['amount']) if x['asset'] == 'ND' else f"{x['amount']:,} {x['asset'].title()}"
            home = w.home[x['owner']] == x['dst']
            rows.append([key, f"{x['purpose'].replace('_', ' ').title()} {amt} for {x['owner']}, {_sh(x['src'])}→{_sh(x['dst'])}",
                         hh_(x['t_export']), hh_(x['t_import']), hh_(x['t_export']),
                         (hh_(x['t_import']) + (' at home' if home else ' at host')) if x['t_import'] else 'not imported'])
    rows.sort(key=lambda r: float(r[2].replace(',', '')) if r[2] != '—' else 1e9)
    return rows


def e3_complete():
    parts = [r'''
\clearpage
\section*{E3+. State histories and settlement moments}
Table~\ref{tab:e3open} is the opening balance sheet. For each scenario the next tables list every change in the
positions of its two parties, one row per account and asset that changed, so that the whole ledger history can be
read off without the trace files. ``Home'' is available at the home exchange, ``At host'' is available in the remote
trading account, ``Locked'' is order and instruction holds plus contract margin, and ``Transit'' is value debited at
one exchange and not yet credited at another. All other accounts are unchanged in every run.
''', opening_table('tab:e3open')]
    mom = []
    for k in PARTIES:
        rows = state_history(k)
        if rows:
            parts.append(longtab('rLllrrrr', ['h', 'Event', 'Account', 'Asset', 'Home', 'At host', 'Locked', 'Transit'],
                                 rows, f'State history of {TITLES[k]}.', f'tab:sh{k}', lw='4.6cm'))
        mom += settlement_moments(k)
    parts.append(r'''
\paragraph{Settlement moments.} Table~\ref{tab:e3moments} lists every obligation in every scenario. An obligation is
\emph{discharged} when the duty it records is met (a fill, a fixing, or a transfer credited at its destination); a
claim is \emph{backed} once the value has been debited into a transfer, so nobody can spend it twice; and it is
\emph{spendable} when the owner can use it, either at the host or at home.
''')
    parts.append(longtab('lLrrll', ['Run', 'Obligation', 'Created h', 'Discharged h', 'Backed', 'Spendable'], mom,
                         'Settlement moments of every obligation in every S1 scenario (hours, no loss).', 'tab:e3moments', lw='5.2cm'))
    return '\n'.join(parts)


# ====================================================================== service by product and settlement
def products_table(label='tab:prod'):
    P = load('products')
    order = ['Mercury', 'Venus', 'Earth', 'Mars', 'Ceres', 'Jupiter', 'Saturn', 'Uranus', 'Neptune']
    rows = []
    for s in order:
        cells = [s]
        for prod in ('Ares', 'Belt', 'Terra'):
            r = P[f'{s}|{prod}']
            if r['packets'] == 0:
                cells.append('local, 0.0')
            else:
                cells.append(f"{h(r['noloss'], 1)} / {h(r['p50'], 1)} / {r['p_72']:.2f}")
        f = P[f'{s}|Futures']
        cells.append(f"{h(f['noloss_open'], 1)} / {pct(f['p_open'], 1)}")
        rows.append(cells)
    return table('lllll', ['Home', 'Ares at Mars', 'Belt at Ceres', 'Terra at Earth', 'Futures at Mars'], rows,
                 'Service by product and settlement. The client\'s account is moved to each settlement and buys 1,000 '
                 'shares of each stock at \\$100 at its market with home delivery, or goes long $Q = 2{,}000$ in the '
                 'Mars futures against Cara. Share columns: completion hours without loss / median under random loss / '
                 'probability of completing within 72 hours. Futures column: opening hour without loss / probability '
                 'of opening before the 168-hour deadline. 300 lossy runs per cell (\\texttt{products.py}).', label,
                 sep='3pt')


def s3_products():
    P = load('products')
    nep = P['Neptune|Ares']
    miss = {k: v['n'] - v['completed'] for k, v in P.items() if v['completed'] < v['n']}
    n_all = sum(v['n'] for v in P.values())
    assert set(miss) <= {'Neptune|Ares', 'Neptune|Belt', 'Neptune|Futures'}, miss   # the cases explained below
    miss_txt = ', '.join(f"{n} {k.split('|')[1]}" for k, n in miss.items())
    return T(r'''
\paragraph{Every product at every settlement.} Table~\ref{tab:s3prod} repeats the relocation for each product. A
purchase is local, with no network traffic, only when the client's home is the market's host; every other cell uses
the same three steps (funding over the backbone, a direct order, delivery home over the backbone). The time is set by
the slower of the client's direct path to the host and the backbone route back, so the columns differ little. The
Neptune client completes within 72 hours with probability <<f"{nep['p_72']:.2f}">> and within 168 hours with
probability <<f"{nep['p_168']:.2f}">>.

Of the <<f"{n_all:,}">> lossy runs, <<sum(miss.values())>> did not trade, all with the client at Neptune
(<<miss_txt>>), and none lost anything. A direct copy from Neptune to Mars is lost with probability about 0.91.
In the share runs every copy of the order was lost during its 7-day life (64 copies in 8 sends in the Ares run); it expired and
the \$100,000 stayed available to the client at the host. In the futures run the client's instruction did not reach Mars
before the 168-hour opening deadline, so the contract was rejected and both margins went back home.

<<Raw(products_table('tab:s3prod'))>>
''', locals())


# ====================================================================== E5, forwarding legs per epoch
def e5_legs():
    r9 = load('r9_detail')
    rows = []
    for k, v in r9['epochs'].items():
        ep, sc = k.split('|')
        for l in v['legs']:
            via = l['label'].startswith('FWD:')
            agent = l['principal'].endswith('(agent)')
            leg = 'fwd 1' if via else ('fwd 2' if agent else 'direct')
            rows.append([ep, sc, l['principal'].replace(' exchange (agent)', ' (R8)'), f"{_sh(l['a'])}→{_sh(l['b'])}",
                         leg, l['label'].replace('FWD:', ''), l['n'], f"{l['p_loss_each'][0]:.3f}", h(l['t_first_arrive'], 2),
                         f"{l['p_all']:.4f}"])
    t = longtab('llllllrrrr', ['Epoch', 'Run', 'Sender', 'Path', 'Leg', 'Message', 'Copies', 'p each', 'First h',
                               'P(arrives)'], rows,
                'Every direct leg in the E5 runs of S1a and S1d (no loss). A forwarded instruction has two legs: the '
                'client to the forwarding exchange and that exchange to the host; it arrives with the product of the '
                'two P(arrives). Leg: fwd 1 is client to forwarder, fwd 2 is forwarder to host.', 'tab:e5legs', sep='2pt')
    fw = sorted({r[0] for r in rows if r[4] != 'direct'})
    dr = [e for e in ('+1 year', '+10 years', '+100 years', 'Mars conjunction') if e not in fw]
    fwd_txt = ('At ' + ' and '.join(dr) + ' every instruction goes direct. ' if dr else '') + \
        ('R8 forwards instructions at ' + ' and '.join(fw) + ', through the exchange named in the Sender column '
         'of the second leg.' if fw else 'No instruction is forwarded.')
    return T(r'''
\paragraph{Which path each instruction took.} Table~\ref{tab:e5legs} lists every direct leg in the shifted-epoch
runs of S1a and S1d. <<fwd_txt>>

<<Raw(t)>>
''', locals())


# ====================================================================== S2 incident trace
def s2_trace(until_after_open=1.0):
    """Event-by-event trace of the selected S2 incident, from traces/S2_reset_Mars_*.csv: every backbone launch
    except hop receipts (counted), every direct copy, every courier event and every ledger event, up to the opening."""
    import csv, json
    TR = Path(__file__).resolve().parents[1] / 'traces'
    rd = lambda n: list(csv.DictReader((TR / f'S2_reset_Mars_{n}.csv').open()))
    led, tra, lau = rd('ledger'), rd('transport'), rd('launches')
    t_open = next(float(e['t_h']) for e in led if e['event'] == 'CONTRACT_OPEN')
    end = t_open + until_after_open
    rows, n_rcpt = [], 0
    for x in lau:
        t = float(x['t_emit_h'])
        if t > end:
            continue
        if x['kind'] == 'RCPT':
            n_rcpt += 1
            continue
        lost = ' (lost)' if x['lost'] == 'True' else ''
        if x['layer'] == 'direct':
            what = f"direct {x['kind']} copy {int(x['copy']) + 1} from {x['carries']}"
        else:
            sess = f"s{x['session']}"
            what = f"{x['kind']} {sess}" + (' (carries ' + x['carries'].split('/')[0] + ')' if x['kind'] == 'DATA' else '')
        rows.append((t, 0, f"{_sh(x['src'])}→{_sh(x['dst'])}", 'launch', what + f", arrives {float(x['t_arrive_h']):.3f}{lost}"))
    for x in tra:
        t = float(x['t_h'])
        if t > end:
            continue
        det = {'SESSION_OPEN': lambda: f"session s{x['ref']} to {x['peer']} via {x['detail'].replace('>', ', ')}",
               'IGNORED_UNKNOWN_SESSION': lambda: f"{x['detail']} on s{x['ref']} from {x['peer']}: Mars lost this session in the reset",
               'DELIVERY_UNKNOWN': lambda: f"s{x['ref']} to {x['peer']}: four endpoint attempts unacknowledged",
               'APP_RESUBMIT_SCHEDULED': lambda: f"resubmission of the transfer scheduled for {float(x['detail'].split('|')[1]) / 3600:.3f}",
               'APP_RESUBMIT': lambda: f"transfer resubmitted to {x['peer']} on a new session"}.get(x['event'], lambda: x['detail'])()
        rows.append((t, 1, x['at'], {'IGNORED_UNKNOWN_SESSION': 'ignored'}.get(x['event'], x['event'].replace('_', ' ').lower()), det))
    keep = ('LOCAL_INSTRUCTION', 'EXPORT', 'ENDPOINT_RESET', 'IMPORT', 'RECEIVED_QUEUED', 'RECEIPT_KNOWN', 'MARGIN_HELD',
            'CONTRACT_OPEN', 'STATUS_QUEUED', 'STATUS_RECEIVED', 'DUPLICATE_CINSTR')
    for e in led:
        t = float(e['t_h'])
        if t > end or e['event'] not in keep:
            continue
        d = json.loads(e['detail'])
        det = {'LOCAL_INSTRUCTION': lambda: f"{d['msg']['type']} ${d['msg']['amount']:,} to {d['msg']['dst']}",
               'EXPORT': lambda: f"{d['eid']}: ${d['amount']:,} of {d['owner']} debited, in transit to {d['dst']}",
               'ENDPOINT_RESET': lambda: 'all session state lost; ledger and durable outbox kept',
               'IMPORT': lambda: f"{d['eid']}: ${d['amount']:,} credited to {d['owner']}",
               'RECEIVED_QUEUED': lambda: f"RECEIVED for {d['eid']} queued to {d['dst']}",
               'RECEIPT_KNOWN': lambda: f"{d['eid']} resolved",
               'MARGIN_HELD': lambda: f"{d['owner']}: ${d['amount']:,} margin held",
               'CONTRACT_OPEN': lambda: f"F1 opens, escrow ${d['escrow']:,}",
               'STATUS_QUEUED': lambda: f"STATUS record to {d['dst']}",
               'STATUS_RECEIVED': lambda: f"{d['owner']} told {d['state']}",
               'DUPLICATE_CINSTR': lambda: f"later copy from {d['owner']} ignored"}[e['event']]()
        rows.append((t, 2, e['actor'], e['event'].replace('_', ' ').lower(), det))
    rows.sort(key=lambda r: (r[0], r[1]))
    body = [[f"{t:.3f}", at, ev, det] for t, _, at, ev, det in rows]
    tt = longtab('rllL', ['h', 'At', 'Event', 'Detail'], body,
                 f'Event-by-event trace of the S2 incident (rising path, no loss) from hour 0 to the opening at '
                 f'{t_open:.3f}: every backbone launch except the {n_rcpt} hop receipts, every direct copy, every '
                 f'courier event and every ledger event. Ea = Earth, Ma = Mars, Ce = Ceres, A = Relay A.',
                 'tab:s2trace', lw='8.2cm', sep='3pt')
    return T(r'''
\paragraph{Complete trace of the incident.} Table~\ref{tab:s2trace} lists every event of the selected incident up to
the opening; the files \texttt{traces/S2\_reset\_Mars\_\{launches,transport,ledger\}.csv} hold the whole run, including
the 300-hour contract and the payouts, which then follow S1d shifted by the delay. The table shows the four steps of
the 125-hour penalty: the handshakes complete before the reset, so Earth and Ceres send their transfers into sessions
Mars has forgotten; Mars ignores every copy; each sender's four endpoint attempts expire (delivery unknown); and
after the 24-hour application backoff each resubmits on a new session, which succeeds within about two hours.

<<Raw(tt)>>
''', locals())


# ====================================================================== E7. market data
def e7():
    M = load('md_test')
    D, Q = M['daily'], M['six_hourly']
    order = ['Mercury', 'Venus', 'Earth', 'Mars', 'Ceres', 'Jupiter', 'Saturn', 'Uranus', 'Neptune']
    rows = []
    for hm in order:
        a, b = D['by_home'][hm], Q['by_home'][hm]
        rows.append([hm, h(a['wait_p95'], 1), h(a['age_p50'], 1), h(b['wait_p95'], 1), h(b['wait_max'], 1),
                     h(b['age_p50'], 1), h(b['age_p95'], 1)])
    tb = table('lrrrrrr', ['Exchange', 'Daily wait 95%', 'Daily age median', '6 h wait 95%', '6 h wait max',
                           '6 h age median', '6 h age 95%'],
               rows, 'Quote requests by clients at each exchange, pooled over the stocks listed elsewhere, in '
               f"{Q['runs']} lossy 30-day runs per demand level. Wait: hours from the QUOTE instruction to the quote "
               '(0 when the board was already fresh enough). Age: hours since the market took the snapshot, when the '
               'client received it. Daily: one request per stock per day, accepting quotes up to 24 hours old. '
               '6 h: one every 6 hours, accepting quotes up to 6 hours old.', 'tab:e7')
    rpd = lambda R: sum(R['replies_per_day'].values()) / len(R['replies_per_day'])
    pk = lambda R: max(R['peak_orig'].values())
    txt = T(r"""
\section*{E7. Market data}
\paragraph{Design.} Every exchange holds the listing table and a board with the newest snapshot of each stock (R5).
A client reads both by local access, at no quota cost; at the market itself the board is the live book. Snapshots
travel only as the reply to a quote request: a client's QUOTE instruction makes its exchange ask the market over the
backbone if the board is older than the client accepts, at most once per stock per 6 hours. In S1 the client sends
QUOTE together with its funding, so the request shares the funding transfer's packet and the reply shares the
RECEIVED's. Packet counts, originations and completion times are identical to runs without market data, in S1 and in
60 lossy S1a, S1c, S1d and S1i runs, and the client reads the quote just before it orders (mark
\texttt{quote\_seen}).

\paragraph{Load test.} \texttt{md\_test.py} has a client at every settlement ask for every stock listed elsewhere
(24 exchange--stock pairs) for 30 days, with random loss and maintenance, while a local trader at each market changes
the book every 2 hours. Table~\ref{tab:e7} gives the waits and ages. With a request every 6 hours, which is the most
an exchange sends, each market sent <<f"{rpd(Q):.1f}">> replies a day and its busiest 24 hours used <<pk(Q)>>
originations including session setup. With one request a day it sent <<f"{rpd(D):.1f}">> and used at most
<<pk(D)>>. <<f"{100*Q['immediate']:.0f}">>\% of the 6-hourly requests were answered from the board at once. Waits
are set by distance: a request and its reply each cross the backbone, and at Uranus and Neptune a new session's
handshake and losses of about a third per hop add a day or more. The quote never gates safety: an order's limit
price bounds what it pays.
""", locals())
    return txt + tb
