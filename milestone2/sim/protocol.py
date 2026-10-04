"""Design v3 application layer: prefunded trading accounts, local matching, withdrawals and
Mars-hosted capped futures, running on the brief's transport (transport.py).

Everything financial happens inside one `Ledger` per exchange.  Ledgers only change through
  * a local client instruction (1 s local access, lossless),
  * a direct-service client packet that actually arrived (see `Client`),
  * an authenticated backbone TRANSFER / RECEIVED record delivered by the Courier,
  * a host-local timer (order expiry, opening deadline, fixing) or a local price observation.
After every financial event `World.audit()` re-adds every unit of every asset and checks that
nothing was created, destroyed or used twice.
"""
import math, itertools
from collections import defaultdict
from geom import (SETTLEMENTS, HOUR, DAY, direct_flight, flight, EXCLUSION_AU, NODE_ID)
from transport import Net, Quota, Courier, Direct, Record, Incident

CASH = 'ND'
SHARES = ('ARES', 'BELT', 'TERRA')
REGISTRY = {'ARES': 'Mars', 'BELT': 'Ceres', 'TERRA': 'Earth'}   # market + registry location
SIZE = dict(TRANSFER=176, RECEIVED=120, ORDER=128, CANCEL=128, STATUS=128, CLOSE=128, WITHDRAW=128,
            REPORT=160, CINSTR=256, PRICE=200, MDS=152, MDREQ=120)
MD_COALESCE = 6 * HOUR      # an exchange sends at most one quote request per stock per 6 h; its clients share it
MAX_ORDER_LIFE = 30 * DAY
MAX_LIVE_ORDERS_CLIENT, MAX_LIVE_ORDERS_HOST = 32, 256     # resting (open or partial) orders
STATUS_MAX = 52            # entries per STATUS record: 128 + 51 x 16 = 944 bytes, the most one packet carries
XFER_WINDOW = 512          # transfers to a destination go out in number order; n is not sent while any number <= n - 512 is unresolved
UNRESOLVED_CAP = 4096      # unresolved exports + reserved export slots per host; admission stops at 80 %
ADMIT_LIMIT = UNRESOLVED_CAP * 4 // 5
DIRECT_SUBHEADER, FWD_HEADER, PAYLOAD = 16, 24, 960


def msg_size(msg):
    """Fixed-width size in bytes of one client instruction (or a batch / forwarded wrapper) in a direct packet."""
    k = msg['type']
    if k == 'BATCH':
        return sum(msg_size(m) for m in msg['items'])
    if k == 'FWD':
        return FWD_HEADER + msg_size(msg['inner'])
    return SIZE[k]

OPENING_BOOK = [  # account, home, NeoDollars, {share: qty}
    ('Alice', 'Earth', 150_000, {}),
    ('Bob', 'Mars', 50_000, {'ARES': 3000}),
    ('Cara', 'Ceres', 100_000, {'BELT': 1000}),
    ('Dax', 'Neptune', 100_000, {}),
    ('Eve', 'Uranus', 50_000, {}),
    ('Fin', 'Earth', 50_000, {'TERRA': 1000}),
]


class Rejected(Exception):
    pass


def hours(t):
    return t / HOUR


# ====================================================================== ledger
class Ledger:
    RESERVE = True        # count reserved export slots in admission (False = the earlier rule, for comparison)
    """One exchange's authoritative books: customer available balances, order holds, contract
    instruction holds and escrow, exports and imports.  The exchange itself owns nothing."""

    def __init__(self, world, name):
        self.w, self.name = world, name
        self.avail = defaultdict(int)          # (owner, asset) -> units
        self.orders = {}                       # oid -> order dict
        self.decisions = {}                    # (owner, oid) -> (terms, outcome)
        self.tomb = set()                      # (owner, oid) cancelled before admission
        self.book = defaultdict(list)          # asset -> live order ids
        self.exports = {}                      # eid -> transfer dict
        self.imports = {}                      # (src, eid) -> transfer dict
        self.withdrawals = {}                  # (owner, req) -> (terms, outcome)
        self.instr = {}                        # (cid, owner) -> instruction dict
        self.contracts = {}                    # cid -> contract dict
        self.closed = set()                    # owners whose account generation 1 is closed
        self.restricted = defaultdict(int)     # (owner, asset) late top-ups awaiting return
        self.ret_pending = {}                  # (owner, asset, src) -> amount credited but not yet exported back
        self.peak_ret_waiting = 0
        self.registry = defaultdict(int)       # for assets registered here: custodian -> qty
        self.n_exp = itertools.count(1)
        self.n_exec = itertools.count(1)
        self.n_seq = itertools.count(1)
        self.reports_sent = {}
        self.status_out = {}          # home exchange -> status entries waiting for this instant's STATUS record
        self.dseq = defaultdict(int)           # destination -> last transfer number
        self.unres = defaultdict(set)          # destination -> numbers of exports without RECEIVED
        self.held = defaultdict(list)          # destination -> exports waiting for the window (FIFO)
        self.n_res = 0                         # export slots reserved by accepted obligations (orders, contracts)
        self.peak_committed = 0
        self.dlv_of = {}                       # delivery export eid -> order id
        self.mdv = defaultdict(int)            # asset listed here -> book version (changes on admit, fill, release)
        self.last_trade = {}                   # asset -> (price, qty, time)
        self.board = {}                        # asset listed elsewhere -> latest snapshot received
        self.md_req = {}                       # asset -> time of the last quote request this exchange sent
        self.md_wait = defaultdict(list)       # asset -> (client, max_age) waiting for a fresher snapshot
        self.md_log = []                       # (t, 'mdreq' | 'reply', peer) market-data records sent

    # ------------------------------------------------------------------ helpers
    def ev(self, kind, **kw):
        self.w.event(self.name, kind, **kw)

    def home_of(self, owner):
        return self.w.home[owner]

    # ------------------------------------------------------------------ transfers
    def export(self, owner, asset, amount, dst, purpose, ref=None, restricted=False):
        """Debit available (or restricted) balance and create one immutable, irrevocable export."""
        if dst == self.name:
            raise Rejected('remote destination required')
        if asset != CASH and self.name != REGISTRY[asset] and dst != REGISTRY[asset]:
            raise Rejected('share transfers route through the registry')
        pool = self.restricted if restricted else self.avail
        if amount <= 0 or pool[owner, asset] < amount:
            raise Rejected(f'insufficient available {asset}: have {pool[owner, asset]}, need {amount}')
        pool[owner, asset] -= amount
        eid = f'{self.name[:2].upper()}-X{next(self.n_exp)}'
        t = dict(src=self.name, eid=eid, dst=dst, owner=owner, asset=asset, amount=amount, purpose=purpose,
                 ref=ref, t_export=self.w.now, state='EXPORTED', t_import=None, t_receipt=None)
        self.exports[eid] = t
        if asset != CASH and self.name == REGISTRY[asset]:
            self.registry[dst] += amount          # registry knows the delegated custody it created
            self.registry[self.name] -= amount
        self.w.transit[(self.name, eid)] = t
        self.dseq[dst] += 1
        t['seq'] = self.dseq[dst]
        self.unres[dst].add(t['seq'])
        self.peak_committed = max(self.peak_committed, self.committed())
        self.ev('EXPORT', owner=owner, asset=asset, amount=amount, dst=dst, eid=eid, purpose=purpose, ref=ref)
        rec = Record('TRANSFER', self.name, dst, dict(t), SIZE['TRANSFER'], critical=True)
        t['rid'] = rec.rid
        if self.held[dst] or min(self.unres[dst]) <= t['seq'] - XFER_WINDOW:
            self.held[dst].append(rec)          # debited and durable; sent when the window opens
            self.ev('EXPORT_HELD', eid=eid, dst=dst, seq=t['seq'])
        else:
            self.w.courier.send(rec)
        self.w.audit()
        return t

    def n_unresolved(self):
        return sum(len(v) for v in self.unres.values())

    def committed(self):
        """Export slots in use: unresolved exports plus the slots reserved by accepted orders and contracts for the
        transfers they may still create (one home delivery per order at a time, one payout per contract party)."""
        return self.n_unresolved() + self.n_res

    def _slots_needed(self, principal, msg):
        k = msg['type']
        remote = self.home_of(principal) != self.name
        if k in ('FUND', 'WITHDRAW'):
            return 1
        if k == 'CINSTR':
            return 1 if remote else 0
        if k == 'ORDER':
            return 1 if remote and msg.get('disp') == 'AUTO' else 0
        if k == 'CLOSE':
            return sum(1 for (o, a), v in self.avail.items() if o == principal and v > 0) if remote else 0
        return 0

    def _drain_returns(self):
        """Return late top-ups while a slot below the hard cap is free.  Returns are the only exports not admitted
        through reservation, so they take only free slots: slots in use never exceed UNRESOLVED_CAP.  A return that
        does not fit waits as a restricted balance owned by its client, one entry per (owner, asset, source), and
        later top-ups for the same entry merge into it."""
        while self.ret_pending and self.committed() < UNRESOLVED_CAP:
            k = next(iter(self.ret_pending))
            amt = self.ret_pending.pop(k)
            self.export(k[0], k[1], amt, k[2], 'RETURN_LATE_TOPUP', restricted=True)
        if self.ret_pending:
            self.ev('RETURN_WAITING', entries=len(self.ret_pending))

    def _release_held(self, dst):
        while self.held[dst] and min(self.unres[dst]) > self.held[dst][0].body['seq'] - XFER_WINDOW:
            rec = self.held[dst].pop(0)
            self.ev('EXPORT_RELEASED', eid=rec.body['eid'], dst=dst, seq=rec.body['seq'])
            self.w.courier.send(rec)

    def on_transfer(self, rec):
        t = rec
        key = (t['src'], t['eid'])
        if key in self.imports:
            self.ev('DUPLICATE_IMPORT_IGNORED', eid=t['eid'], src=t['src'])
        else:
            self.imports[key] = t
            src_t = self.w.ledgers[t['src']].exports[t['eid']]     # harness bookkeeping only
            src_t['t_import'] = self.w.now
            del self.w.transit[key]
            if t['asset'] != CASH and self.name == REGISTRY[t['asset']]:
                self.registry[t['src']] -= t['amount']
                self.registry[self.name] += t['amount']
            if t['owner'] in self.closed and self.home_of(t['owner']) != self.name:
                self.restricted[t['owner'], t['asset']] += t['amount']
                self.ev('IMPORT_RESTRICTED', owner=t['owner'], asset=t['asset'], amount=t['amount'], eid=t['eid'],
                        src=t['src'])
                self.w.audit()
                k = (t['owner'], t['asset'], t['src'])
                self.ret_pending[k] = self.ret_pending.get(k, 0) + t['amount']   # merges with a waiting return
                self.peak_ret_waiting = max(self.peak_ret_waiting, len(self.ret_pending))
                self._drain_returns()
            else:
                self.avail[t['owner'], t['asset']] += t['amount']
                self.ev('IMPORT', owner=t['owner'], asset=t['asset'], amount=t['amount'], eid=t['eid'], src=t['src'],
                        purpose=t['purpose'], ref=t['ref'])
                self.w.audit()
        # RECEIVED for every authentic copy (a duplicate means our earlier receipt may be lost)
        rr = Record('RECEIVED', self.name, t['src'], dict(eid=t['eid'], src=t['src']), SIZE['RECEIVED'])
        self.w.courier.send(rr)
        self.ev('RECEIVED_QUEUED', eid=t['eid'], dst=t['src'], rid=rr.rid)
        self.w.notify('import', self.name, t)

    def on_received(self, body):
        t = self.exports.get(body['eid'])
        if t is None:
            return
        if t['state'] != 'RECEIPT_KNOWN':
            t['state'] = 'RECEIPT_KNOWN'
            t['t_receipt'] = self.w.now
            self.unres[t['dst']].discard(t['seq'])
            self._release_held(t["dst"])
            self.ev('RECEIPT_KNOWN', eid=t['eid'], owner=t['owner'], asset=t['asset'], amount=t['amount'], dst=t['dst'])
            oid = self.dlv_of.pop(t['eid'], None)
            if oid is not None:
                r = self.orders[oid]
                r['dlv'] = None
                asset = r['asset'] if r['side'] == 'BUY' else CASH
                amt = min(r['pend'], self.avail[r['owner'], asset])     # the client may have used some meanwhile
                r['pend'] = 0
                if amt > 0:
                    self._deliver(r, amt, oid)
                elif r['state'] in ('OPEN', 'PARTIAL'):
                    r['res'] = True               # re-reserve the slot for later fills
                    self.n_res += 1
            if self.ret_pending:                  # after the order has taken back its own slot
                self._drain_returns()
            self.w.notify('received', self.name, t)

    # ------------------------------------------------------------------ client instructions
    def instruction(self, principal, msg, via):
        """Entry point for every client instruction (local or direct).  `principal` is the
        authenticated sender; every instruction only acts on that principal's own account."""
        k = msg['type']
        try:
            need = self._slots_needed(principal, msg)
            if need and (self.committed() if self.RESERVE else self.n_unresolved()) + need > ADMIT_LIMIT:
                raise Rejected('export capacity reserved for existing obligations; try later')
            if k == 'FUND':
                return self.fund(principal, msg)
            if k == 'ORDER':
                return self.order(principal, msg)
            if k == 'CANCEL':
                return self.cancel(principal, msg['oid'])
            if k == 'WITHDRAW':
                return self.withdraw(principal, msg)
            if k == 'CINSTR':
                return self.contract_instruction(principal, msg, via)
            if k == 'CLOSE':
                return self.close(principal)
            if k == 'PRICE':
                return self.price(principal, msg)
            if k == 'QUOTE':
                return self.md_request(principal, msg['asset'], msg.get('max_age', 6 * HOUR))
        except Rejected as e:
            self.ev('REJECTED', owner=principal, what=k, reason=str(e), ref=msg.get('oid') or msg.get('req') or msg.get('cid'))
            self.w.notify('rejected', self.name, dict(owner=principal, msg=msg, reason=str(e)))
            return None
        raise ValueError(k)

    def fund(self, owner, msg):
        """Local instruction at the client's home: transfer to own trading account elsewhere."""
        key = (owner, msg['req'])
        terms = (msg['asset'], msg['amount'], msg['dst'])
        if key in self.withdrawals:
            old, out = self.withdrawals[key]
            if old != terms:
                raise Rejected('request ID reused with different terms')
            return out
        try:
            t = self.export(owner, msg['asset'], msg['amount'], msg['dst'], 'FUND', ref=msg['req'])
        except Rejected as e:
            self.withdrawals[key] = (terms, 'REJECTED')
            raise
        self.withdrawals[key] = (terms, t)
        return t

    # ------------------------------------------------------------------ market data (R5)
    def snapshot(self, asset):
        """Best bid and ask with sizes, last trade, book version, time.  Informational only."""
        live = [self.orders[i] for i in self.book[asset] if self.orders[i]['state'] in ('OPEN', 'PARTIAL')]
        def best(side, pick):
            px = [o['limit'] for o in live if o['side'] == side]
            if not px:
                return None
            b = pick(px)
            return (b, sum(o['remaining'] for o in live if o['side'] == side and o['limit'] == b))
        return dict(asset=asset, market=self.name, bid=best('BUY', max), ask=best('SELL', min),
                    last=self.last_trade.get(asset), ver=self.mdv[asset], t=self.w.now)

    def quote(self, asset):
        """What a client at this exchange sees by local access: the live book for a stock listed here, otherwise the
        latest snapshot on the board (possibly stale, with its time), or None."""
        if REGISTRY.get(asset) == self.name:
            return self.snapshot(asset)
        return self.board.get(asset)

    def on_mds(self, snap):
        cur = self.board.get(snap['asset'])
        if cur is None or snap['ver'] > cur['ver'] or (snap['ver'] == cur['ver'] and snap['t'] > cur['t']):
            self.board[snap['asset']] = snap
        self.ev('MD_BOARD', asset=snap['asset'], ver=snap['ver'], age_h=(self.w.now - snap['t']) / HOUR)
        waiting, self.md_wait[snap['asset']] = self.md_wait[snap['asset']], []
        for client, max_age in waiting:
            self.w.notify('quote', self.name, dict(client=client, snap=self.board[snap['asset']]))

    def on_mdreq(self, src, asset):
        """A market answers every quote request with its current snapshot (routine backbone traffic)."""
        self.md_log.append((self.w.now, 'reply', src))
        self.ev('MD_REPLY', dst=src, asset=asset, ver=self.mdv[asset])
        self.w.courier.send(Record('MDS', self.name, src, self.snapshot(asset), SIZE['MDS']))

    def md_request(self, client, asset, max_age=6 * HOUR):
        """QUOTE instruction by local access.  Served at once from the board if fresh enough; otherwise the exchange
        asks the market over the backbone, at most once per stock per 6 h, and answers every waiting client from the
        reply.  The request leaves with whatever else is queued for that market (e.g. the client's funding)."""
        q = self.quote(asset)
        if q is not None and self.w.now - q['t'] <= max_age:
            self.w.notify('quote', self.name, dict(client=client, snap=q))
            return q
        self.md_wait[asset].append((client, max_age))
        last = self.md_req.get(asset)
        if last is None or self.w.now - last >= MD_COALESCE:
            self.md_req[asset] = self.w.now
            self.md_log.append((self.w.now, 'mdreq', REGISTRY[asset]))
            self.ev('MD_REQUEST', asset=asset, market=REGISTRY[asset])
            self.w.courier.send(Record('MDREQ', self.name, REGISTRY[asset], dict(asset=asset), SIZE['MDREQ']))
        return q

    # ------------------------------------------------------------------ orders and matching
    def order(self, owner, o):
        oid = o['oid']
        key = (owner, oid)
        terms = (o['asset'], o['side'], o['qty'], o['limit'], o['tif'], o['expiry'], o['disp'])
        if key in self.decisions:
            old, out = self.decisions[key]
            if old != terms:
                raise Rejected('order ID reused with different terms')
            self.ev('DUPLICATE_ORDER', owner=owner, oid=oid, outcome=out)
            return out

        def fail(reason):
            self.decisions[key] = (terms, 'REJECTED:' + reason)
            raise Rejected(reason)

        if key in self.tomb:
            fail('cancelled before admission (tombstone)')
        if owner in self.closed:
            fail('account closed')
        if REGISTRY.get(o['asset']) != self.name:
            fail('asset not listed here')
        if o['qty'] <= 0 or o['limit'] <= 0 or o['side'] not in ('BUY', 'SELL'):
            fail('invalid terms')
        if not (self.w.now < o['expiry'] <= self.w.now + MAX_ORDER_LIFE):
            fail('expiry outside (now, now+30 d]')
        live = [r for r in self.orders.values() if r['state'] in ('OPEN', 'PARTIAL')]
        if len(live) >= MAX_LIVE_ORDERS_HOST or sum(r['owner'] == owner for r in live) >= MAX_LIVE_ORDERS_CLIENT:
            fail('live-order limit reached')
        hold_asset = CASH if o['side'] == 'BUY' else o['asset']
        need = o['qty'] * o['limit'] if o['side'] == 'BUY' else o['qty']
        if self.avail[owner, hold_asset] < need:
            fail(f'insufficient available {hold_asset}: have {self.avail[owner, hold_asset]}, need {need}')
        self.avail[owner, hold_asset] -= need
        rec = dict(oid=oid, owner=owner, asset=o['asset'], side=o['side'], qty=o['qty'], limit=o['limit'], tif=o['tif'],
                   expiry=o['expiry'], disp=o['disp'], remaining=o['qty'], held=need, state='OPEN',
                   seq=next(self.n_seq), t_admit=self.w.now, fills=[], res=False, dlv=None, pend=0)
        if o['disp'] == 'AUTO' and self.home_of(owner) != self.name:
            rec['res'] = True                     # one delivery slot, held until the order is done and delivered
            self.n_res += 1
            self.peak_committed = max(self.peak_committed, self.committed())
        self.orders[oid] = rec
        self.decisions[key] = (terms, 'ACCEPTED')
        self.ev('ORDER_ADMITTED', owner=owner, oid=oid, side=o['side'], asset=o['asset'], qty=o['qty'],
                limit=o['limit'], tif=o['tif'], hold=need, hold_asset=hold_asset)
        self.w.audit()
        self.mdv[rec['asset']] += 1
        self._match(rec)
        if rec['state'] in ('OPEN', 'PARTIAL'):
            if rec['tif'] == 'IOC':
                self._release(rec, 'IOC_REMAINDER_RELEASED')
            else:
                self.book[rec['asset']].append(oid)
                self.w.net.at(rec['expiry'], lambda: self._expire(oid), rank=1)
        return 'ACCEPTED'

    def _match(self, inc):
        """Price-time priority against resting orders, at the resting price, skipping self-trades."""
        while inc['remaining'] > 0:
            opp = 'SELL' if inc['side'] == 'BUY' else 'BUY'
            cands = [self.orders[i] for i in self.book[inc['asset']]
                     if self.orders[i]['side'] == opp and self.orders[i]['state'] in ('OPEN', 'PARTIAL')
                     and self.orders[i]['owner'] != inc['owner']]
            if inc['side'] == 'BUY':
                cands = [c for c in cands if c['limit'] <= inc['limit']]
                cands.sort(key=lambda c: (c['limit'], c['seq']))
            else:
                cands = [c for c in cands if c['limit'] >= inc['limit']]
                cands.sort(key=lambda c: (-c['limit'], c['seq']))
            if not cands:
                return
            rest = cands[0]
            q = min(inc['remaining'], rest['remaining'])
            buy, sell = (inc, rest) if inc['side'] == 'BUY' else (rest, inc)
            self._fill(buy, sell, q, rest['limit'])

    def _fill(self, b, s, q, p):
        eid = f'{self.name[:2].upper()}-F{next(self.n_exec)}'
        asset = b['asset']
        b['held'] -= q * b['limit']
        s['held'] -= q
        self.avail[b['owner'], CASH] += q * (b['limit'] - p)          # price improvement released
        self.avail[s['owner'], CASH] += q * p
        self.avail[b['owner'], asset] += q
        for r in (b, s):
            r['remaining'] -= q
            r['state'] = 'FILLED' if r['remaining'] == 0 else 'PARTIAL'
            r['fills'].append((eid, q, p, self.w.now))
        for r in (b, s):
            if r['state'] == 'FILLED' and r['oid'] in self.book[asset]:
                self.book[asset].remove(r['oid'])
        self.ev('FILL', exec_id=eid, asset=asset, qty=q, price=p, buyer=b['owner'], seller=s['owner'],
                buy_oid=b['oid'], sell_oid=s['oid'], improvement=q * (b['limit'] - p))
        self.w.stats['matched_value'] += q * p
        self.mdv[asset] += 1
        self.last_trade[asset] = (p, q, self.w.now)
        self.w.audit()
        self.w.notify('fill', self.name, dict(exec_id=eid, asset=asset, qty=q, price=p, buyer=b['owner'],
                                              seller=s['owner'], buy=b, sell=s))
        # automatic home withdrawal of this fill's results, committed with the fill
        if b['disp'] == 'AUTO' and self.home_of(b['owner']) != self.name:
            self._deliver(b, q, eid)
        if s['disp'] == 'AUTO' and self.home_of(s['owner']) != self.name:
            self._deliver(s, q * p, eid)
        for r in (b, s):
            if r['state'] == 'FILLED':
                self._order_done(r)

    def _deliver(self, r, amount, ref):
        """Home delivery for an order: at most one delivery transfer per order is unresolved at a time, so the order
        never needs more than its one reserved slot.  Fills made while a delivery is in transit stay available at the
        host and are added to the next one, which leaves when the RECEIVED for the previous one arrives."""
        if r['dlv'] is not None:
            r['pend'] += amount
            self.ev('DELIVERY_PENDING', owner=r['owner'], oid=r['oid'], amount=amount, pending=r['pend'])
            return
        asset = r['asset'] if r['side'] == 'BUY' else CASH
        if r['res']:
            r['res'] = False                      # the reserved slot becomes this unresolved export
            self.n_res -= 1
        t = self.export(r['owner'], asset, amount, self.home_of(r['owner']), 'AUTO_FILL', ref=ref)
        r['dlv'] = t['eid']
        self.dlv_of[t['eid']] = r['oid']

    def _order_done(self, r):
        if r['res']:
            r['res'] = False
            self.n_res -= 1

    def _release(self, r, why):
        asset = CASH if r['side'] == 'BUY' else r['asset']
        amt = r['held']
        self.avail[r['owner'], asset] += amt
        r['held'] = 0
        r['state'] = {'IOC_REMAINDER_RELEASED': 'CANCELLED', 'EXPIRED': 'EXPIRED'}.get(why, 'CANCELLED')
        if r['oid'] in self.book[r['asset']]:
            self.book[r['asset']].remove(r['oid'])
        self.mdv[r['asset']] += 1
        self._order_done(r)
        self.ev(why, owner=r['owner'], oid=r['oid'], released=amt, asset=asset, filled=r['qty'] - r['remaining'])
        self.w.audit()

    def _expire(self, oid):
        r = self.orders[oid]
        if r['state'] in ('OPEN', 'PARTIAL'):
            self._release(r, 'EXPIRED')

    def cancel(self, owner, oid):
        r = self.orders.get(oid)
        if r is None or r['owner'] != owner:
            if (owner, oid) not in self.tomb:
                self.tomb.add((owner, oid))
                self.ev('CANCEL_TOMBSTONE', owner=owner, oid=oid)
            return 'TOMBSTONE'
        if r['state'] in ('OPEN', 'PARTIAL'):
            self._release(r, 'CANCELLED')
            return 'CANCELLED'
        self.ev('CANCEL_TOO_LATE', owner=owner, oid=oid, state=r['state'])
        return r['state']

    # ------------------------------------------------------------------ withdrawals and close
    def withdraw(self, owner, msg):
        key = (owner, msg['req'])
        terms = (msg['asset'], msg['amount'])
        if key in self.withdrawals:
            old, out = self.withdrawals[key]
            if old != terms:
                raise Rejected('request ID reused with different terms')
            self.ev('DUPLICATE_WITHDRAW', owner=owner, req=msg['req'])
            return out
        amt = self.avail[owner, msg['asset']] if msg['amount'] == 'ALL' else msg['amount']
        if amt <= 0:
            self.withdrawals[key] = (terms, 'NOTHING_AVAILABLE')
            self.ev('WITHDRAW_NOTHING', owner=owner, req=msg['req'], asset=msg['asset'])
            return 'NOTHING_AVAILABLE'
        try:
            t = self.export(owner, msg['asset'], amt, self.home_of(owner), 'WITHDRAW', ref=msg['req'])
        except Rejected:
            self.withdrawals[key] = (terms, 'REJECTED')
            raise
        self.withdrawals[key] = (terms, t)
        return t

    def close(self, owner):
        if owner in self.closed:
            return 'CLOSED'
        self.closed.add(owner)
        self.ev('ACCOUNT_CLOSING', owner=owner)
        for r in list(self.orders.values()):
            if r['owner'] == owner and r['state'] in ('OPEN', 'PARTIAL'):
                self._release(r, 'CANCELLED')
        for (o, a), v in list(self.avail.items()):
            if o == owner and v > 0 and self.home_of(owner) != self.name:
                self.export(owner, a, v, self.home_of(owner), 'CLOSE_SWEEP')
        return 'CLOSED'

    # ------------------------------------------------------------------ capped futures
    def contract_instruction(self, owner, m, via):
        cid = m['cid']
        key = (cid, owner)
        if key in self.instr:
            old = self.instr[key]
            if old['terms'] != m['terms']:
                raise Rejected('contract instruction conflicts with earlier terms')
            self.ev('DUPLICATE_CINSTR', owner=owner, cid=cid, state=old['state'])
            self._report(owner, cid, via)
            return old['state']
        T = m['terms']
        if owner not in (T['long'], T['short']):
            raise Rejected('not a party')
        c = self.contracts.get(cid)
        if c and c['state'] != 'PENDING':
            self.instr[key] = dict(terms=T, hold=0, state='REJECTED', reason='contract ' + c['state'])
            self._report(owner, cid, via)
            raise Rejected('contract ' + c['state'])
        if self.w.now >= T['deadline']:
            self.instr[key] = dict(terms=T, hold=0, state='REJECTED', reason='after opening deadline')
            self._report(owner, cid, via)
            raise Rejected('after opening deadline')
        margin = T['Q'] * (T['K'] - T['lo'])      # = Q * (hi - K): maximum loss per side
        if self.avail[owner, CASH] < margin:
            self.instr[key] = dict(terms=T, hold=0, state='REJECTED', reason='insufficient margin')
            self._report(owner, cid, via)
            raise Rejected(f'insufficient available cash for margin: have {self.avail[owner, CASH]}, need {margin}')
        self.avail[owner, CASH] -= margin
        self.instr[key] = dict(terms=T, hold=margin, state='HELD', t=self.w.now,
                               res=self.home_of(owner) != self.name and T.get('payout', 'AUTO') == 'AUTO')
        self.n_res += self.instr[key]['res']      # slot for this party's payout home
        self.peak_committed = max(self.peak_committed, self.committed())
        if c is None:
            c = self.contracts[cid] = dict(cid=cid, terms=T, state='PENDING', escrow=0, obs={}, t_open=None)
            self.w.net.at(T['deadline'], lambda: self._deadline(cid), rank=1)
        self.ev('MARGIN_HELD', owner=owner, cid=cid, amount=margin)
        self.w.audit()
        other = T['short'] if owner == T['long'] else T['long']
        if (cid, other) in self.instr and self.instr[(cid, other)]['state'] == 'HELD':
            self._open(c)
        self._report(owner, cid, via)
        return 'HELD'

    def _open(self, c):
        T = c['terms']
        for p in (T['long'], T['short']):
            i = self.instr[(c['cid'], p)]
            c['escrow'] += i['hold']
            i['hold'] = 0
            i['state'] = 'OPENED'
        c['state'] = 'OPEN'
        c['t_open'] = self.w.now
        c['t_maturity'] = self.w.now + T['duration']
        c['t_fix'] = c['t_maturity'] + T['grace']
        self.ev('CONTRACT_OPEN', cid=c['cid'], escrow=c['escrow'], long=T['long'], short=T['short'], Q=T['Q'],
                maturity=c['t_maturity'], fixing=c['t_fix'])
        self.w.audit()
        self.w.net.at(c['t_fix'], lambda: self._fix(c['cid']), rank=4)
        self.w.notify('contract_open', self.name, c)
        for p in (T['long'], T['short']):
            if self.home_of(p) != self.name:
                self._report(p, c['cid'], 'direct', force=True)

    def _deadline(self, cid):
        c = self.contracts[cid]
        if c['state'] != 'PENDING':
            return
        c['state'] = 'REJECTED_DEADLINE'
        for p in (c['terms']['long'], c['terms']['short']):
            i = self.instr.get((cid, p))
            if i and i['state'] == 'HELD':
                amt = i['hold']
                self.avail[p, CASH] += amt
                i['hold'] = 0                     # both sides of the move before the event is recorded
                i['state'] = 'RELEASED'
                if i.get('res'):
                    i['res'] = False
                    self.n_res -= 1
                self.ev('MARGIN_RELEASED', owner=p, cid=cid, amount=amt, why='opening deadline passed')
        self.ev('CONTRACT_REJECTED', cid=cid, why='both instructions not held by deadline')
        for p in (c['terms']['long'], c['terms']['short']):     # R6: every instructing party learns REJECTED
            if (cid, p) in self.instr:
                self._report(p, cid, 'direct', force=True)
        self.w.audit()
        self.w.notify('contract_rejected', self.name, c)

    def price(self, source, m):
        c = self.contracts.get(m['cid'])
        if c is None or source != c['terms']['oracle']:
            raise Rejected('unknown contract or unauthorised price source')
        if c['state'] != 'OPEN':
            self.ev('LATE_PRICE_IGNORED', cid=m['cid'], k=m['k'], price=m['price'])
            return
        k = m['k']
        prev = c['obs'].get(k)
        if prev is not None and prev != m['price']:
            c['obs'][k] = 'CONFLICT'
        elif prev is None:
            c['obs'][k] = m['price']
        self.ev('PRICE_OBSERVED', cid=m['cid'], k=k, price=m['price'], source=source)

    def _fix(self, cid):
        c = self.contracts[cid]
        T = c['terms']
        obs = c['obs']
        P, used = 100, 'default 100'
        for k in range(T['n_obs'], 0, -1):
            if isinstance(obs.get(k), int):
                P, used = obs[k], f'observation {k}'
                break
        Pc = min(max(P, T['lo']), T['hi'])
        net_long = T['Q'] * (Pc - T['K'])
        margin = c['escrow'] // 2
        gross = {T['long']: margin + net_long, T['short']: margin - net_long}
        c['state'] = 'FIXED'
        c['fixing'] = dict(P=P, used=used, net_long=net_long, gross=gross, t=self.w.now)
        c['escrow'] = 0
        for p, g in gross.items():
            self.avail[p, CASH] += g
        self.ev('CONTRACT_FIXED', cid=cid, P=P, used=used, net_long=net_long, gross_long=gross[T['long']],
                gross_short=gross[T['short']])
        self.w.audit()
        self.w.notify('contract_fixed', self.name, c)
        for p, g in gross.items():                # automatic home payout in the same transaction
            i = self.instr.get((cid, p))
            if i and i.get('res'):
                i['res'] = False                  # the reserved slot becomes the payout export (or is freed)
                self.n_res -= 1
            if g > 0 and self.home_of(p) != self.name and T.get('payout', 'AUTO') == 'AUTO':
                self.export(p, CASH, g, self.home_of(p), 'PAYOUT', ref=cid)

    def _report(self, owner, cid, via, force=False):
        """Contract status for a remote client.  The host does not use the direct service: it adds the entry to one
        batched STATUS record per home exchange (backbone, host's origination quota), and the home exchange tells
        its client by local access.  Rate-limited to one entry per client and contract per 6 h unless the state
        changed."""
        if via == 'local' or self.home_of(owner) == self.name:
            self.w.notify('report', self.name, dict(owner=owner, cid=cid, state=self._cstate(owner, cid), local=True))
            return
        last = self.reports_sent.get((owner, cid))
        st = self._cstate(owner, cid)
        if not force and last and last[1] == st and self.w.now - last[0] < 6 * HOUR:
            return
        self.reports_sent[(owner, cid)] = (self.w.now, st)
        home = self.home_of(owner)
        q = self.status_out.setdefault(home, {})
        if not q:
            self.w.net.at(self.w.now, lambda home=home: self._flush_status(home), rank=2)
        q[(owner, cid)] = st                     # the latest state wins within one instant

    def _flush_status(self, home):
        q = self.status_out.pop(home, {})
        if not q:
            return
        allent = [dict(owner=o, cid=c, state=st) for (o, c), st in q.items()]
        for i in range(0, len(allent), STATUS_MAX):          # one STATUS record never exceeds one packet
            entries = allent[i:i + STATUS_MAX]
            rec = Record('STATUS', self.name, home, dict(entries=entries, t=self.w.now),
                         SIZE['STATUS'] + 16 * max(0, len(entries) - 1))
            self.ev('STATUS_QUEUED', dst=home, entries=len(entries), rid=rec.rid)
            self.w.courier.send(rec)

    def _cstate(self, owner, cid):
        c = self.contracts.get(cid)
        i = self.instr.get((cid, owner))
        if c and c['state'] != 'PENDING':
            return c['state']
        return i['state'] if i else 'UNKNOWN'


# ====================================================================== world
class World:
    def __init__(self, seed=0, loss=False, maintenance=True, incidents=(), t0=0.0, policy=None, book=OPENING_BOOK,
                 log_launches=True, audit=True):
        self.t0 = t0
        self.net = Net(seed=seed, loss=loss, maintenance=maintenance, incidents=incidents, t_start=t0,
                       log=log_launches)
        self.policy = dict(direct_target=0.99, direct_cap=8, batch_window=0.0, auto_withdraw=True, fallback_slack_h=6,
                           agent_relay=True)      # rule R9 (option O2) is part of the design
        if policy:
            self.policy.update(policy)
        self.quota = Quota({s: 66 for s in SETTLEMENTS}, reserve=self.policy.get('quota_reserve', 22))
        self.ledgers = {s: Ledger(self, s) for s in SETTLEMENTS}
        self.courier = Courier(self.net, self.quota, {s: s for s in SETTLEMENTS}, self._deliver,
                               policy=dict(batch_window=self.policy['batch_window'],
                                           backoff=self.policy.get('backoff', True),
                                           fast_resubmit=self.policy.get('fast_resubmit'),
                                           restart_notice=self.policy.get('restart_notice', False)))
        self.direct = Direct(self.net)
        self.home = {}
        self.supply = defaultdict(int)
        self.events = []
        self.watchers = []
        self.transit = {}
        self.stats = defaultdict(int)
        self.do_audit = audit
        self.n_audits = 0
        self.snap = []                 # (t, capital snapshot)
        self.direct_log = []
        self.incidents = list(incidents)
        for acct, home, cash, shares in book:
            self.home[acct] = home
            L = self.ledgers[home]
            L.avail[acct, CASH] += cash
            self.supply[CASH] += cash
            for a, q in shares.items():
                L.avail[acct, a] += q
                self.supply[a] += q
                self.ledgers[REGISTRY[a]].registry[home] += q
        for inc in incidents:
            if inc.kind == 'reset':
                self.net.at(inc.start, lambda inc=inc: self._reset(inc.node), rank=0)
        self.audit()

    @property
    def now(self):
        return self.net.now

    # ------------------------------------------------------------------ plumbing
    def event(self, actor, kind, **kw):
        self.events.append(dict(t=self.now, actor=actor, kind=kind, **kw))

    def notify(self, what, where, obj):
        for w in list(self.watchers):
            w(what, where, obj)

    def _deliver(self, inst, rec):
        L = self.ledgers[inst]
        if rec.kind == 'TRANSFER':
            L.on_transfer(rec.body)
        elif rec.kind == 'RECEIVED':
            L.on_received(rec.body)
        elif rec.kind == 'MDS':
            L.on_mds(rec.body)
        elif rec.kind == 'MDREQ':
            L.on_mdreq(rec.src, rec.body['asset'])
        elif rec.kind == 'STATUS':              # the home exchange tells each client by local access (1 s)
            for e in rec.body['entries']:
                self.event(inst, 'STATUS_RECEIVED', owner=e['owner'], cid=e['cid'], state=e['state'], src=rec.src)
                self.net.at(self.now + 1.0, lambda e=e: self.notify('report', inst, dict(e, local=False)), rank=1)

    def _reset(self, inst):
        self.event(inst, 'ENDPOINT_RESET')
        self.courier.reset(inst)

    def run(self, until):
        self.net.run(self.t0 + until)

    # ------------------------------------------------------------------ client channels
    def local(self, principal, where, msg, delay=0.0):
        """Local access: 1 s, lossless, no quota."""
        def go():
            self.event(principal, 'LOCAL_INSTRUCTION', where=where, msg=_short(msg))
            self.ledgers[where].instruction(principal, msg, 'local')
        self.net.at(self.now + delay + 1.0, go, rank=1)

    def direct_copies(self, a, b, t):
        p = direct_flight(a, b, t)['p_loss']
        tgt = self.policy['direct_target']
        k = 1 if p <= 0 else math.ceil(math.log(1 - tgt) / math.log(p))
        return max(1, min(self.policy['direct_cap'], k))

    def direct_send(self, principal, a, b, msg, copies=None, label='', on_arrive=None, relay_ok=True):
        """Send `copies` direct packets 60 s apart, waiting for an open solar path and for the
        principal's 12/day quota.  Each copy is an independent loss trial at its own geometry.
        Rule R9 / option O2 (policy agent_relay): if the a->b path is closed now, the client hands the signed
        message to its own agent at a third settlement, which re-sends it direct (agent's quota)."""
        if relay_ok and self.policy.get('agent_relay') and not direct_flight(a, b, self.now)['open']:
            x = self.pick_agent(a, b, self.now)
            if x is not None:
                fwd = dict(type='FWD', inner=msg, to=b, origin=principal, label=label, done=False)
                self.event(principal, 'AGENT_RELAY', via=x, to=b, label=label or msg['type'])
                return self.direct_send(principal, a, x, fwd, copies=copies, label='FWD:' + (label or msg['type']),
                                        relay_ok=False)
        assert DIRECT_SUBHEADER + msg_size(msg) <= PAYLOAD, (msg['type'], msg_size(msg))   # one direct packet
        if copies is None:
            copies = self.direct_copies(a, b, self.now)
        t = self.now
        for c in range(copies):
            t = self._direct_slot(principal, a, b, t)
            self.net.at(t, lambda c=c: self._direct_launch(principal, a, b, msg, label, c, on_arrive), rank=1)
            self.direct.hist_planned[principal].append(t)
            t += 60.0

    def pick_agent(self, a, b, t):
        """Third settlement minimising the two-leg arrival with both legs open now."""
        best, bx = math.inf, None
        for x in SETTLEMENTS:
            if x in (a, b):
                continue
            f1 = direct_flight(a, x, t)
            if not f1['open']:
                continue
            f2 = direct_flight(x, b, f1['arrive'] + 1.0)
            if f2['open'] and f2['arrive'] < best:
                best, bx = f2['arrive'], x
        return bx

    def _direct_slot(self, principal, a, b, t):
        """Earliest t' >= t with an open direct path such that every rolling 24 h window that
        contains t' still holds at most 12 of this principal's launches and launches stay >= 60 s
        apart (planned future launches included)."""
        planned = sorted(self.direct.hist_planned[principal])
        for _ in range(20000):
            t = next_direct_open(a, b, t)
            if not math.isfinite(t):
                raise RuntimeError('direct path never opens')
            close = [x for x in planned if abs(x - t) < 60.0 - 1e-6]
            if close:
                t = max(close) + 60.0 + 1e-3
                continue
            back = [x for x in planned if t - DAY < x <= t]
            if len(back) >= 12:
                t = back[-12] + DAY + 1e-3
                continue
            bad = False
            for y in planned:
                if t < y < t + DAY:
                    if sum(1 for x in planned if y - DAY < x <= y) + 1 > 12:
                        bad = True
                        break
            if bad:
                t += 60.0
                continue
            return t
        raise RuntimeError('no direct slot')

    def _direct_launch(self, principal, a, b, msg, label, copy, on_arrive):
        f = direct_flight(a, b, self.now)
        killed = any(inc.kind == 'isolation' and inc.node in (a, b) and inc.start <= f['te'] < inc.end
                     for inc in self.incidents)
        lost = (not f['open']) or killed or (self.net.loss and self.net.rng.random() < f['p_loss'])
        row = dict(t=self.now, te=f['te'], ta=f['arrive'], principal=principal, a=a, b=b, label=label or msg['type'],
                   copy=copy, d=f['d'], p_loss=f['p_loss'], lost=lost, killed=killed)
        self.direct_log.append(row)
        self.event(principal, 'DIRECT_LAUNCH', a=a, b=b, label=row['label'], copy=copy, arrive=f['arrive'],
                   lost=lost, p_loss=round(f['p_loss'], 4))
        if not lost:
            def arrive():
                if msg['type'] == 'FWD':
                    if not msg['done']:            # the agent forwards the first authentic copy once
                        msg['done'] = True
                        self.direct_send(b + ' exchange (agent)', b, msg['to'], dict(msg['inner'], _signer=msg['origin']),
                                         label=msg['label'],
                                         on_arrive=on_arrive, relay_ok=False)
                    return
                signer = msg.get('_signer', principal)      # a forwarded message keeps its signer
                if msg['type'] == 'REPORT':
                    self.notify('report', b, dict(msg, local=False))
                elif msg['type'] == 'BATCH':
                    for m in msg['items']:
                        self.ledgers[b].instruction(signer, m, 'direct')
                else:
                    self.ledgers[b].instruction(signer, msg, 'direct')
                if on_arrive:
                    on_arrive()
            self.net.at(f['arrive'], arrive, rank=0, sender=NODE_ID[a])

    # ------------------------------------------------------------------ audit / capital
    def audit(self):
        if not self.do_audit:
            return
        self.n_audits += 1
        tot = defaultdict(int)
        for L in self.ledgers.values():
            for (o, a), v in L.avail.items():
                assert v >= 0, (L.name, o, a, v)
                tot[a] += v
            for (o, a), v in L.restricted.items():
                assert v >= 0
                tot[a] += v
            for r in L.orders.values():
                exp = (r['remaining'] * r['limit'] if r['side'] == 'BUY' else r['remaining']) \
                    if r['state'] in ('OPEN', 'PARTIAL') else 0
                assert r['held'] == exp, (r, exp)
                tot[CASH if r['side'] == 'BUY' else r['asset']] += r['held']
            for i in L.instr.values():
                assert i['hold'] >= 0
                tot[CASH] += i['hold']
            for c in L.contracts.values():
                tot[CASH] += c['escrow']
        for t in self.transit.values():
            tot[t['asset']] += t['amount']
        for a in set(tot) | set(self.supply):
            assert tot[a] == self.supply[a], ('conservation', a, tot[a], self.supply[a])
        # registry reconciliation: delegated custody = holdings there + in transit there
        for a, reg in REGISTRY.items():
            R = self.ledgers[reg].registry
            for s, L in self.ledgers.items():
                held = sum(v for (o, x), v in L.avail.items() if x == a) + \
                    sum(v for (o, x), v in L.restricted.items() if x == a) + \
                    sum(r['held'] for r in L.orders.values() if r['asset'] == a and r['side'] == 'SELL')
                inbound = sum(t['amount'] for t in self.transit.values() if t['asset'] == a and t['dst'] == s
                              and t['src'] == reg)
                outbound = sum(t['amount'] for t in self.transit.values() if t['asset'] == a and t['src'] == s
                               and t['dst'] == reg)
                # registry counts inbound-to-s as at s, and outbound-from-s (to registry) still at s
                assert R[s] == held + inbound + outbound * (s != reg), ('registry', a, s, R[s], held, inbound, outbound)
        self.snap.append((self.now, self.capital()))

    def capital(self):
        """Per asset: home available, remote available, order holds, contract instruction holds,
        contract escrow, in transit."""
        out = {}
        for a in (CASH,) + SHARES:
            d = dict(home=0, remote=0, order=0, instr=0, escrow=0, transit=0)
            for s, L in self.ledgers.items():
                for (o, x), v in L.avail.items():
                    if x == a:
                        d['home' if self.home[o] == s else 'remote'] += v
                for (o, x), v in L.restricted.items():
                    if x == a:
                        d['transit'] += v
                for r in L.orders.values():
                    if (CASH if r['side'] == 'BUY' else r['asset']) == a:
                        d['order'] += r['held']
                if a == CASH:
                    d['instr'] += sum(i['hold'] for i in L.instr.values())
                    d['escrow'] += sum(c['escrow'] for c in L.contracts.values())
            d['transit'] += sum(t['amount'] for t in self.transit.values() if t['asset'] == a)
            out[a] = d
        return out

    def balances(self):
        """Per account and location: available / held / escrow."""
        rows = []
        for s, L in self.ledgers.items():
            per = defaultdict(lambda: defaultdict(int))
            for (o, a), v in L.avail.items():
                if v:
                    per[o][a] += v
            for r in L.orders.values():
                if r['held']:
                    per[r['owner']][('held', CASH if r['side'] == 'BUY' else r['asset'])] += r['held']
            for (cid, o), i in L.instr.items():
                if i['hold']:
                    per[o][('instr', CASH)] += i['hold']
            for c in L.contracts.values():
                if c['escrow']:
                    per['(escrow ' + c['cid'] + ')'][('escrow', CASH)] += c['escrow']
            for o, d in per.items():
                rows.append((s, o, dict(d)))
        return rows


def _short(m):
    return {k: v for k, v in m.items() if k != 'terms'}


def next_direct_open(a, b, t, step=1800.0):
    """Earliest send time >= t whose direct photon path clears the 0.1 AU exclusion sphere."""
    if a == b:
        return t
    if flight(a, b, t + 2.0)[2] >= EXCLUSION_AU:
        return t
    lo, hi = t, t
    for _ in range(int(400 * DAY / step)):
        hi += step
        if flight(a, b, hi + 2.0)[2] >= EXCLUSION_AU:
            while hi - lo > 1e-3:
                mid = 0.5 * (lo + hi)
                if flight(a, b, mid + 2.0)[2] >= EXCLUSION_AU:
                    hi = mid
                else:
                    lo = mid
            return hi
        lo = hi
    return math.inf


def _relay_clear(a, b, x, guard):
    """R9 (option O2): some third settlement has both direct legs a->X and X->b clear at time x."""
    for s in SETTLEMENTS:
        if s in (a, b):
            continue
        ta, _, c1 = flight(a, s, x + 2.0)
        if c1 >= guard and flight(s, b, ta + 3.0)[2] >= guard:
            return True
    return False


def direct_clear_window(a, b, t, horizon, step=900.0, relay=False):
    """Known-geometry check a client can make: earliest t' >= t such that the direct path a->b
    is open at every 15-min sample of [t', t'+horizon] (Lipschitz guard 0.00146 AU/h makes the
    sampled check conservative: a sample above the guard implies openness until the next one).
    With relay=True (rule R9) a sample also passes if a two-leg forwarding path is clear."""
    if a == b:
        return t
    guard = EXCLUSION_AU + 0.00146 * step / HOUR
    cand, x, end = t, t, t + 400 * DAY
    while x < end:
        c = flight(a, b, x + 2.0)[2]
        if c < guard and not (relay and _relay_clear(a, b, x, guard)):
            x = next_direct_open(a, b, x) if (c < EXCLUSION_AU and not relay) else x
            x += step
            cand = x
            continue
        if x - cand >= horizon:
            return cand
        x += step
    return math.inf


def account_state(w, asset=CASH):
    """Per-account view of one asset: home available, remote available, order/instruction holds,
    contract margin (escrow attributed to the party that posted it) and in transit."""
    out = {a: dict(home=0, remote=0, held=0, escrow=0, transit=0) for a in w.home}
    for s, L in w.ledgers.items():
        for (o, x), v in L.avail.items():
            if x == asset:
                out[o]['home' if w.home[o] == s else 'remote'] += v
        for r in L.orders.values():
            if (CASH if r['side'] == 'BUY' else r['asset']) == asset:
                out[r['owner']]['held'] += r['held']
        if asset == CASH:
            for (cid, o), i in L.instr.items():
                out[o]['held'] += i['hold']
            for c in L.contracts.values():
                if c['escrow']:
                    for p in (c['terms']['long'], c['terms']['short']):
                        out[p]['escrow'] += c['escrow'] // 2
    for t in w.transit.values():
        if t['asset'] == asset:
            out[t['owner']]['transit'] += t['amount']
    return out
