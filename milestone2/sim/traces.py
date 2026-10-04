"""Human-readable conditional traces in the brief's seven-column format (Section 8):
time, actor, local knowledge, action, packet or transmission, arrival, financial state after.

Every row is generated from the simulator's authoritative event stream; the financial state
column is the ledger snapshot taken immediately after that event."""
import sys
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).parent))
import protocol
from protocol import account_state, CASH, World
from scenarios import run
from geom import HOUR, SHORT

H = HOUR
ARROW = '→'


def k(v):
    """$ amounts in compact form."""
    v = float(v)
    if abs(v) >= 1000:
        s = f'{v / 1000:,.3f}'.rstrip('0').rstrip('.')
        return f'${s}k'
    return f'${v:,.0f}'


def hh(t):
    return f'{t:.4f}'


def run_traced(spec, who, assets=(), **kw):
    """Run a scenario and capture the account state after every event."""
    snaps = []
    orig = World.event

    def hooked(self, actor, kind, **kk):
        orig(self, actor, kind, **kk)
        st = {CASH: account_state(self, CASH)}
        for a in assets:
            st[a] = account_state(self, a)
        snaps.append(st)
    World.event = hooked
    try:
        w, tr = run(spec, **kw)
    finally:
        World.event = orig
    return w, tr, snaps


def state_str(st, who, assets, homes):
    parts = []
    for p in who:
        c = st[CASH][p]
        bits = []
        if c['home']:
            bits.append(f"{k(c['home'])} at {homes[p]}")
        if c['remote']:
            bits.append(f"{k(c['remote'])} free at host")
        if c['held']:
            bits.append(f"{k(c['held'])} held")
        if c['escrow']:
            bits.append(f"{k(c['escrow'])} margin")
        if c['transit']:
            bits.append(f"{k(c['transit'])} in transit")
        for a in assets:
            s = st[a][p]
            for key, lab in (('home', 'home'), ('remote', 'at market'), ('held', 'held'), ('transit', 'in transit')):
                if s[key]:
                    bits.append(f"{s[key]:,} {a.title()} {lab}")
        parts.append(f"<b>{p}</b> " + ', '.join(bits) if bits else f"<b>{p}</b> —")
    return '<br>'.join(parts)


def launches_of(w, rid):
    out = []
    for sid, seq in w.courier.rec_pkt.get(rid, []):
        for r in w.net.launches:
            lg = r[12]
            if r[4] == 'DATA' and lg and lg[2] == sid and lg[3] == seq:
                out.append(r)
    return out


def rows_for(w, tr, snaps, who, assets=(), t_max=None, skip=()):
    """Build trace rows. Direct copies of one instruction are merged into one row."""
    t0 = w.t0
    homes = w.home
    exports = {}
    for L in w.ledgers.values():
        for t in L.exports.values():
            exports[(L.name, t['eid'])] = t
    rows = []
    i = 0
    ev = w.events
    while i < len(ev):
        e = ev[i]
        st = snaps[i]
        t = (e['t'] - t0) / H
        if t_max is not None and t > t_max:
            break
        kd = e['kind']
        if kd in skip:
            i += 1
            continue
        row = None
        a = e['actor']
        if kd == 'LOCAL_INSTRUCTION':
            m = e['msg']
            typ = m.get('type')
            if typ == 'FUND':
                act = f"Funds own {m['dst']} account: {k(m['amount'])}"
                knows = f"Own {e['where']} balance"
            elif typ == 'ORDER':
                act = f"{m['side'].title()} {m['qty']:,} {m['asset'].title()} limit ${m['limit']} {m['tif']}"
                knows = 'Own inventory at the market'
            elif typ == 'PRICE':
                act = f"Publishes observation {m['k']}: index {m['price']}"
                knows = 'Schedule (learned locally at opening)'
            elif typ == 'QUOTE':
                act = f"QUOTE for {m['asset'].title()}"
                knows = f"Listing table: {m['asset'].title()} trades at {protocol.REGISTRY[m['asset']]}"
            elif typ == 'CINSTR':
                act = 'Contract instruction (local)'
                knows = 'Own funded account at host'
            else:
                act = typ
                knows = '—'
            # the event fires on arrival; local access takes 1 s, so the client sent it 1 s earlier.  The row is shown at
            # the arrival so that its financial state (taken after this event) matches its time and order.
            row = [hh(t), a, knows, act, f"Local access at {e['where']}, sent h {hh(t - 1 / 3600)}", hh(t)]
        elif kd == 'EXPORT':
            x = exports[(a, e['eid'])]
            L = [r for r in launches_of(w, x.get('rid')) if r[2] != x['dst'] and r[3] != x['src']]
            syn = [r for r in w.net.launches if r[4] == 'SYN' and L and r[6] == L[0][6]]
            ses = ''
            if syn:
                ts = (syn[0][0] - t0) / H
                ses = (f'New session (SYN h {hh(ts)}); ' if ts >= t - 1e-6 else f'Session from h {hh(ts)}; ')
            pk = ses + 'DATA ' + (', '.join(f"{SHORT[r[2]]}{ARROW}{SHORT[r[3]]} h {hh((r[0] - t0) / H)}" +
                                          (' LOST' if r[10] else '') for r in L) if L else 'queued')
            arr = hh((x['t_import'] - t0) / H) if x['t_import'] else 'not imported'
            what = {'FUND': 'funding', 'AUTO_FILL': 'automatic home delivery', 'PAYOUT': 'payout',
                    'WITHDRAW': 'withdrawal', 'RETURN_LATE_TOPUP': 'return'}.get(e['purpose'], e['purpose'])
            amt = k(e['amount']) if e['asset'] == CASH else f"{e['amount']:,} {e['asset'].title()}"
            row = [hh(t), f'{a} exchange', 'Instruction or fill; its own ledger',
                   f"Debits {e['owner']} {amt}; TRANSFER {e['eid']} ({what}) to {e['dst']}", pk, arr]
        elif kd == 'IMPORT':
            x = exports[(e['src'], e['eid'])]
            arr = hh((x['t_receipt'] - t0) / H) if x['t_receipt'] else 'pending'
            amt = k(e['amount']) if e['asset'] == CASH else f"{e['amount']:,} {e['asset'].title()}"
            row = [hh(t), f'{a} exchange', f"Authentic new transfer {e['eid']}",
                   f"Imports once; credits {e['owner']} {amt} (spendable now)",
                   f"RECEIVED to {e['src']} (backbone)", arr]
        elif kd == 'RECEIPT_KNOWN':
            row = [hh(t), f'{a} exchange', f"{e['dst']} imported {e['eid']}", 'Marks transfer delivered; no balance change',
                   '—', '—']
        elif kd == 'DIRECT_LAUNCH':
            j = i
            copies = []
            while j < len(ev) and ev[j]['kind'] == 'DIRECT_LAUNCH' and ev[j]['actor'] == a and \
                    ev[j]['label'] == e['label'] and ev[j]['t'] - ev[i]['t'] < 3600:
                copies.append(ev[j])
                j += 1
            st = snaps[j - 1]
            times = ', '.join(hh((c['t'] - t0) / H) for c in copies)
            pl = e['p_loss']
            n = len(copies)
            row = [hh(t), a, 'Published geometry; own funding confirmed' if 'exchange' not in a else 'Contract state',
                   f"Sends {e['label']} ×{n} copies" if n > 1 else f"Sends {e['label']}",
                   f"Direct {SHORT.get(e['a'], e['a'])}{ARROW}{SHORT.get(e['b'], e['b'])}, launches {times}; "
                   f"p(loss) {pl:.3f} each, all lost {pl ** n:.1e}",
                   hh((copies[0]['arrive'] - t0) / H) + (' (first)' if n > 1 else '') +
                   (' LOST' if all(c['lost'] for c in copies) else '')]
            i = j - 1
        elif kd == 'ORDER_ADMITTED':
            amt = k(e['hold']) if e['hold_asset'] == CASH else f"{e['hold']:,} {e['hold_asset'].title()}"
            row = [hh(t), f'{a} exchange', 'Its own available balances', f"Admits {e['owner']} {e['oid']}; holds {amt}",
                   '—', '—']
        elif kd == 'FILL':
            imp = f"; improvement {k(e['improvement'])}" if e['improvement'] else ''
            row = [hh(t), f'{a} exchange', 'Both holds in its own ledger',
                   f"Fill {e['qty']:,} {e['asset'].title()} @ ${e['price']}: {e['buyer']} buys from {e['seller']}{imp}",
                   '—', 'local, atomic']
        elif kd in ('CANCELLED', 'EXPIRED', 'IOC_REMAINDER_RELEASED'):
            row = [hh(t), f'{a} exchange', 'Order state', f"{kd.replace('_', ' ').title()} {e['oid']}; releases "
                   f"{k(e['released']) if e['asset'] == CASH else e['released']}", '—', '—']
        elif kd == 'CANCEL_TOO_LATE':
            row = [hh(t), f'{a} exchange', f"{e['oid']} already {e['state']}", 'Cancel has no effect', '—', '—']
        elif kd == 'MARGIN_HELD':
            row = [hh(t), f'{a} exchange', 'Instruction + own funded balance', f"Holds {e['owner']} margin {k(e['amount'])}",
                   '—', '—']
        elif kd == 'CONTRACT_OPEN':
            row = [hh(t), f'{a} exchange', 'Both margins held', f"Opens {e['cid']}: escrow {k(e['escrow'])}; maturity h "
                   f"{hh((e['maturity'] - t0) / H)}, fixing h {hh((e['fixing'] - t0) / H)}", 'STATUS (OPEN) records to Earth and Ceres (backbone)',
                   '—']
        elif kd == 'PRICE_OBSERVED':
            row = [hh(t), f'{a} exchange', f"Signed observation from {e['source']}", f"Records observation {e['k']} = {e['price']}",
                   'Local access', '—']
        elif kd == 'CONTRACT_FIXED':
            row = [hh(t), f'{a} exchange', f"Fixing cutoff; uses {e['used']}",
                   f"Fixes at {e['P']}: long net {k(e['net_long'])}; gross long {k(e['gross_long'])}, short {k(e['gross_short'])}",
                   '—', 'settles; claims backed']
        elif kd in ('MARGIN_RELEASED', 'CONTRACT_REJECTED'):
            row = [hh(t), f'{a} exchange', e.get('why', ''),
                   f"Releases {e['owner']} margin {k(e['amount'])}" if kd == 'MARGIN_RELEASED' else f"Rejects {e['cid']}",
                   '—', '—']
        elif kd == 'REJECTED':
            row = [hh(t), f'{a} exchange', e['reason'], f"Rejects {e['owner']} {e['what']} {e.get('ref', '')}", '—', '—']
        elif kd in ('CLIENT_FALLBACK', 'CLIENT_DEFER_ACCESS', 'CLIENT_SUSPENDED_ACCESS',
                    'CLIENT_WITHDRAW_AFTER_DEADLINE'):
            row = [hh(t), a, e.get('knowledge', ''), kd.replace('CLIENT_', '').replace('_', ' ').lower(), '—', '—']
        elif kd == 'AGENT_RELAY':
            row = [hh(t), a, 'Direct path to host closed now', f"Hands {e['label']} to agent at {e['via']}", '—', '—']
        elif kd == 'STATUS_QUEUED':
            row = [hh(t), f'{a} exchange', 'Contract state changed for remote clients',
                   f"Queues STATUS record ({e['entries']} entr{'y' if e['entries'] == 1 else 'ies'}) for {e['dst']}",
                   f"Backbone DATA {SHORT[a]}{ARROW}{SHORT[e['dst']]}", '—']
        elif kd == 'STATUS_RECEIVED':
            row = [hh(t), f'{a} exchange', f"STATUS from {e['src']}: {e['cid']} {e['state'].replace('_DEADLINE', ' (deadline)')} for {e['owner']}",
                   f"Tells {e['owner']} (no balance change)", 'Local access (1 s)', hh(t + 1 / 3600)]
        elif kd.startswith('DUPLICATE_'):
            what = kd[10:].lower()
            res = e.get('outcome') or e.get('state') or ''
            row = [hh(t), f'{a} exchange', f'Same {what} already decided' + (f' ({res})' if res else ''),
                   'Ignores the copy; returns the original result', '—', '—']
        elif kd in ('EXPORT_HELD', 'EXPORT_RELEASED'):
            row = [hh(t), f'{a} exchange', 'Transfer window to ' + e['dst'],
                   ('Holds ' if kd == 'EXPORT_HELD' else 'Releases ') + f"{e['eid']} (number {e['seq']})", '—', '—']
        elif kd == 'MD_REQUEST':
            nxt = next((x for x in ev[i:] if x['kind'] == 'MD_REPLY' and x['actor'] == e['market']
                        and x['dst'] == a and x['asset'] == e['asset']), None)
            row = [hh(t), f'{a} exchange', f"No fresh {e['asset'].title()} snapshot on its board",
                   f"Quote request (MDREQ) for {e['asset'].title()} to {e['market']}",
                   f"Backbone {SHORT[a]}{ARROW}{SHORT[e['market']]}, batched with queued records",
                   hh((nxt['t'] - t0) / H) if nxt else 'pending']
        elif kd == 'MD_REPLY':
            nxt = next((x for x in ev[i:] if x['kind'] == 'MD_BOARD' and x['actor'] == e['dst']
                        and x['asset'] == e['asset']), None)
            row = [hh(t), f'{a} exchange', 'Its own live book', f"Replies with {e['asset'].title()} snapshot (MDS, version {e['ver']})",
                   f"Backbone {SHORT[a]}{ARROW}{SHORT[e['dst']]}, batched with queued records",
                   hh((nxt['t'] - t0) / H) if nxt else 'pending']
        elif kd == 'MD_BOARD':
            row = [hh(t), f'{a} exchange', f"MDS from {protocol.REGISTRY[e['asset']]}",
                   f"Posts {e['asset'].title()} snapshot to its board ({e['age_h']:.2f} h old); answers waiting QUOTEs",
                   'Local access (1 s)', hh(t + 1 / 3600)]
        elif kd == 'CLIENT_QUOTE':
            if e.get('ask') is None and e.get('bid') is None and 'age_h' not in e:
                act = f"Reads {e['asset'].title()} quote: none yet"
            else:
                side = lambda q: f"${q[0]} × {q[1]:,}" if q else 'none'
                act = (f"Reads {e['asset'].title()} quote: bid {side(e.get('bid'))}, ask {side(e.get('ask'))}, "
                       f"{e['age_h']:.2f} h old")
            row = [hh(t), a, 'Home board (local access)', act, '—', '—']
        elif kd not in ('RECEIVED_QUEUED',):
            extra = ', '.join(f'{x}={v}' for x, v in e.items() if x not in ('t', 'actor', 'kind'))
            row = [hh(t), a, '—', kd.replace('_', ' ').capitalize() + (f' ({extra})' if extra else ''), '—', '—']
        if row is not None:
            row.append(state_str(st, who, assets, homes))
            rows.append(row)
        i += 1
    # rows are already in event order; the stable sort only merges the multi-copy rows into time order
    rows.sort(key=lambda r: float(str(r[0]).split(' ')[0]))
    return rows


def html_table(rows, cls='trace'):
    head = ('<tr><th>h</th><th>Actor</th><th>Knows</th><th>Does</th><th>Packet / transmission</th>'
            '<th>Arrives</th><th>Financial state after</th></tr>')
    body = '\n'.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows)
    return f'<table class="{cls}"><thead>{head}</thead><tbody>{body}</tbody></table>'


if __name__ == '__main__':
    from scenarios import equity, futures
    w, tr, sn = run_traced([(equity, dict(tag='EQ'))], ['Alice', 'Bob'], ('ARES',), until_h=48)
    for r in rows_for(w, tr, sn, ['Alice', 'Bob'], ('ARES',)):
        print(r)
