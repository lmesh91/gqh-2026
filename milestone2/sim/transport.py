"""Discrete-event model of the brief's backbone and direct services (Sections 2, 4, 5).

Implements, per the brief:
  * 38 directed links, FIFO, 1 s serialization per launch, 10,000-packet cap (newest dropped);
  * launch only if the photon path clears the 0.10 AU sphere and the flight does not overlap
    maintenance; queues wait for known closures; incidents fail launches at emission;
  * independent loss 1-exp(-0.02 d) per backbone launch, 1-exp(-0.08 d) per direct launch;
  * hop receipts, hop retry R_h = 2*flight + 60 min, at most 4 launches, receipts one-shot,
    duplicate copies re-receipted but not re-forwarded, relay processing 1 s;
  * SYN / SYN-ACK / final ACK sessions on a pinned route; data after SYN-ACK; receiver releases
    data only after final ACK; 64-packet window; data ACKs; endpoint retry R_e = 2*T0 + 24 h with
    at most 4 attempts, retries get new packet IDs and discard unlaunched older copies;
  * 30-day packet lifetime, 7-day session idle expiry, endpoint reset;
  * origination quota: SYN and first copy of every application data packet are charged;
    retries, SYN-ACK, ACK, data ACKs and hop receipts are exempt but counted as transmissions.

The application layer (exchanges) lives in protocol.py and talks to this module through
`Courier`, which turns application records into session data and performs application-level
recovery (resubmission on a fresh session after 'delivery unknown').
"""
import heapq, math, random, itertools
from collections import deque, defaultdict
from geom import (flight, next_launch, route_T0, route_eval, routes, NODE_ID, SETTLEMENTS, RELAYS,
                  Maintenance, HOUR, DAY, EXCLUSION_AU, direct_flight)

LIFETIME = 30 * DAY
SESSION_IDLE = 7 * DAY
QUEUE_CAP = 10000
WINDOW = 64
HEADER = 64
PAYLOAD = 960


class Incident:
    """kind in {'isolation','forced_loss','reset'}; node = settlement / node / institution."""

    def __init__(self, kind, node, start, duration=None):
        self.kind, self.node, self.start = kind, node, start
        self.duration = duration if duration is not None else {'isolation': 72 * HOUR, 'forced_loss': 6 * HOUR, 'reset': 0}[kind]
        self.end = start + self.duration

    def kills_launch(self, a, b, te):
        if self.kind == 'isolation':
            return self.start <= te < self.end and self.node in (a, b)
        if self.kind == 'forced_loss':
            return self.start <= te < self.end and self.node in (a, b)
        return False

    def __repr__(self):
        return f'{self.kind}@{self.node}[{self.start/3600:.2f}h,+{self.duration/3600:.0f}h]'


class Packet:
    __slots__ = ('pid', 'kind', 'session', 'route', 'created', 'seq', 'records', 'size', 'ref', 'origin', 'dataseq',
                 'attempt', 'logical')

    def __init__(self, pid, kind, session, route, created, seq, records=None, ref=None, origin=None, dataseq=None,
                 attempt=1, logical=None):
        self.pid, self.kind, self.session, self.route = pid, kind, session, route
        self.created, self.seq, self.records, self.ref = created, seq, records, ref
        self.origin, self.dataseq, self.attempt, self.logical = origin, dataseq, attempt, logical
        self.size = HEADER + (16 + sum(r.size for r in records) if records else 0)


class Link:
    __slots__ = ('a', 'b', 'queue', 'last_emit', 'scheduled', 'max_q')

    def __init__(self, a, b):
        self.a, self.b = a, b
        self.queue = deque()
        self.last_emit = -math.inf
        self.scheduled = False
        self.max_q = 0


class Net:
    """The physical network plus hop-by-hop delivery."""

    def __init__(self, seed=None, loss=True, maintenance=True, incidents=(), t_start=0.0, log=True):
        self.rng = random.Random(seed)
        self.loss = loss
        self.maint = Maintenance(maintenance)
        self.incidents = list(incidents)
        self.now = t_start
        self.heap = []
        self.cnt = itertools.count()
        self.pid = itertools.count(1)
        self.seq = defaultdict(lambda: itertools.count(1))     # per sender node creation sequence
        self.links = {}
        self.seen = defaultdict(set)          # node -> packet ids stored
        self.hops = {}                        # (pid, node) -> hop sender state
        self.endpoints = {}                   # settlement -> callback(packet)
        self.launches = []                    # launch log rows
        self.log = log
        self.stats = defaultdict(int)
        self.queue_drops = 0

    # ------------------------------------------------------------------ scheduling
    def at(self, t, fn, rank=1, sender=0, seq=0):
        heapq.heappush(self.heap, (t, rank, sender, seq, next(self.cnt), fn))

    def run(self, until=math.inf):
        while self.heap and self.heap[0][0] <= until:
            t, _, _, _, _, fn = heapq.heappop(self.heap)
            self.now = t
            fn()
        self.now = max(self.now, until) if until != math.inf else self.now

    def link(self, a, b):
        L = self.links.get((a, b))
        if L is None:
            L = self.links[(a, b)] = Link(a, b)
        return L

    def new_packet(self, kind, session, route, created, records=None, ref=None, origin=None, dataseq=None,
                   attempt=1, logical=None):
        sender = route[0]
        return Packet(next(self.pid), kind, session, route, created, next(self.seq[sender]), records, ref,
                      origin, dataseq, attempt, logical)

    # ------------------------------------------------------------------ link service
    def enqueue(self, L, item, ready):
        """item = (packet, hop_index) or ('RCPT', receipt packet)."""
        def put():
            if len(L.queue) >= QUEUE_CAP:
                self.queue_drops += 1
                return
            L.queue.append(item)
            L.max_q = max(L.max_q, len(L.queue))
            if not L.scheduled:
                self._serve(L)
        if ready <= self.now:
            put()
        else:
            self.at(ready, put, rank=1)

    def _serve(self, L):
        while L.queue:
            pkt, k = L.queue[0]
            te = max(self.now, L.last_emit) + 1.0
            if pkt.created + LIFETIME < te:
                L.queue.popleft(); self.stats['expired'] += 1
                continue
            te2 = next_launch(L.a, L.b, te, self.maint)
            if te2 > pkt.created + LIFETIME:
                L.queue.popleft(); self.stats['expired'] += 1
                continue
            L.scheduled = True
            self.at(te2, lambda L=L, item=(pkt, k), te=te2: self._emit(L, item, te), rank=1)
            return
        L.scheduled = False

    def _emit(self, L, item, te):
        L.scheduled = False
        if not L.queue or L.queue[0][0] is not item[0]:
            self._serve(L)          # head changed (discarded); recompute
            return
        if L.last_emit + 1.0 > te + 1e-9:
            self._serve(L)
            return
        L.queue.popleft()
        L.last_emit = te
        pkt, k = item
        a, b = L.a, L.b
        ta, d, c = flight(a, b, te)
        p = 1 - math.exp(-0.02 * d)
        killed = any(inc.kills_launch(a, b, te) for inc in self.incidents)
        lost = killed or (self.loss and self.rng.random() < p)
        self.stats['launches'] += 1
        self.stats['launch_' + pkt.kind] += 1
        if self.log:
            self.launches.append((te, ta, a, b, pkt.kind, pkt.pid, pkt.session.sid if pkt.session else None,
                                  k, d, p, lost, killed, pkt.logical))
        if pkt.kind == 'RCPT':
            if not lost:
                self.at(ta, lambda: self._rcpt_arrive(pkt), rank=0, sender=NODE_ID[a], seq=pkt.seq)
        else:
            hs = self.hops[(pkt.pid, a)]
            hs['launches'] += 1
            hs['queued'] = False
            deadline = te + 2 * (ta - te) + HOUR
            self.at(deadline, lambda: self._hop_timer(pkt, k, a, hs, hs['launches']), rank=2)
            if not lost:
                self.at(ta, lambda: self._arrive(pkt, k), rank=0, sender=NODE_ID[a], seq=pkt.seq)
        self._serve(L)

    # ------------------------------------------------------------------ hop protocol
    def send_hop(self, pkt, k, ready):
        a, b = pkt.route[k], pkt.route[k + 1]
        key = (pkt.pid, a)
        if key not in self.hops:
            self.hops[key] = dict(launches=0, done=False, queued=False)
        hs = self.hops[key]
        hs['queued'] = True
        self.enqueue(self.link(a, b), (pkt, k), ready)

    def _hop_timer(self, pkt, k, a, hs, n):
        if hs['done'] or hs['launches'] != n or hs['queued']:
            return
        if pkt.created + LIFETIME <= self.now:
            return
        if hs['launches'] >= 4:
            self.stats['hop_abandoned'] += 1
            return
        self.stats['hop_retry'] += 1
        self.send_hop(pkt, k, self.now)

    def _arrive(self, pkt, k):
        a, b = pkt.route[k], pkt.route[k + 1]
        # hop receipt queued at once on the reverse link
        r = Packet(next(self.pid), 'RCPT', pkt.session, (b, a), self.now, next(self.seq[b]), ref=(pkt.pid, a))
        self.enqueue(self.link(b, a), (r, 0), self.now)
        if pkt.pid in self.seen[b]:
            self.stats['dup_copies'] += 1
            return
        self.seen[b].add(pkt.pid)
        if k + 1 < len(pkt.route) - 1:          # relay: forward after 1 s processing
            self.send_hop(pkt, k + 1, self.now + 1.0)
        else:
            cb = self.endpoints.get(b)
            if cb:
                cb(pkt)

    def _rcpt_arrive(self, r):
        pid, a = r.ref
        hs = self.hops.get((pid, a))
        if hs is None or hs['done']:
            return
        hs['done'] = True
        if hs['queued']:      # cancel an unlaunched retry
            L = self.link(r.route[1], r.route[0])
            for item in list(L.queue):
                if item[0].pid == pid:
                    L.queue.remove(item)
            hs['queued'] = False
            if not L.queue:
                pass

    def discard_unlaunched(self, pid, a, b):
        L = self.links.get((a, b))
        if not L:
            return
        for item in list(L.queue):
            if item[0].pid == pid:
                L.queue.remove(item)
                hs = self.hops.get((pid, a))
                if hs:
                    hs['queued'] = False
                    hs['done'] = True


class Quota:
    """Rolling-24 h origination accounting: per-institution budgets plus the global 600."""

    def __init__(self, budgets, global_cap=600, reserve=0):
        self.budgets = budgets
        self.global_cap = global_cap
        self.reserve = reserve            # originations per institution kept for SYN, receipts and resubmissions
        self.hist = defaultdict(deque)
        self.all = deque()
        self.log = []

    def _trim(self, q, t):
        while q and q[0] <= t - DAY:
            q.popleft()

    def available_at(self, inst, t, routine=False):
        """Earliest time >= t at which `inst` may originate.  Routine data (new records other than receipts)
        may use only budget - reserve originations in any 24 h; everything else may use the full budget."""
        q = self.hist[inst]
        self._trim(q, t); self._trim(self.all, t)
        t1 = t
        cap = self.budgets.get(inst, 0) - (self.reserve if routine else 0)
        if cap <= 0:
            return math.inf
        # +1 ms: the oldest origination must have left the window, not sit exactly on its edge
        if len(q) >= cap:
            t1 = max(t1, q[len(q) - cap] + DAY + 1e-3)
        if len(self.all) >= self.global_cap:
            t1 = max(t1, self.all[len(self.all) - self.global_cap] + DAY + 1e-3)
        return t1

    def charge(self, inst, t, what):
        self.hist[inst].append(t)
        self.all.append(t)
        self.log.append((t, inst, what))


class Session:
    _ids = itertools.count(1)

    def __init__(self, a_inst, b_inst, a_node, b_node, route, t):
        self.sid = next(Session._ids)
        self.ends = (a_inst, b_inst)
        self.nodes = {a_inst: a_node, b_inst: b_node}
        self.route = route                    # initiator -> responder
        self.created = t
        self.st = {a_inst: dict(role='init', estab=False, dead=False, last_rx=t, next_seq=0, unacked={}, pending=deque(),
                                rx_next=0, rx_buf={}, delivered=set(), synack_sent=0),
                   b_inst: dict(role='resp', estab=False, dead=False, last_rx=t, next_seq=0, unacked={}, pending=deque(),
                                rx_next=0, rx_buf={}, delivered=set(), synack_sent=0, seen=False)}

    def path_from(self, inst):
        return self.route if inst == self.ends[0] else tuple(reversed(self.route))

    def peer(self, inst):
        return self.ends[1] if inst == self.ends[0] else self.ends[0]


class Record:
    """Application record carried in session data (fixed-width size in bytes)."""
    _ids = itertools.count(1)

    def __init__(self, kind, src, dst, body, size, critical=False):
        self.rid = next(Record._ids)
        self.kind, self.src, self.dst, self.body, self.size = kind, src, dst, body, size
        self.critical = critical
        self.app_attempts = 0


class Courier:
    """Sessions + endpoint retries + application recovery for the institutions.
    institutions: name -> settlement node.  deliver(inst, record) is called once per record."""

    def __init__(self, net, quota, institutions, deliver, policy=None):
        self.net, self.quota, self.inst, self.deliver = net, quota, institutions, deliver
        self.policy = dict(batch_window=0.0, resubmit_after_unknown=True, fast_resubmit=None, max_app_resubmits=10**9,
                           route_lookahead=24 * HOUR)
        if policy:
            self.policy.update(policy)
        self.sessions = {}            # (inst, peer) -> Session (current)
        self.all_sessions = []
        self.outbox = defaultdict(list)    # (src,dst) -> records awaiting a data packet
        self.flush_pending = set()
        self.inflight = {}            # rid -> record (sent, not yet acked)
        self.delivered_rids = defaultdict(set)   # dst inst -> rids delivered to application
        self.reset_times = defaultdict(list)
        self.events = []
        self.originations = defaultdict(int)
        self.deferred = 0
        self.rec_pkt = defaultdict(list)      # record id -> [(session id, data seq)] (trace support)
        self.peers_seen = defaultdict(dict)   # durable: inst -> {peer: last session time} (restart notice)
        for node in set(institutions.values()):
            net.endpoints[node] = self._on_packet

    # ------------------------------------------------------------------ public
    def send(self, rec, delay=0.0):
        key = (rec.src, rec.dst)
        self.outbox[key].append(rec)
        if key not in self.flush_pending:
            self.flush_pending.add(key)
            self.net.at(self.net.now + delay + self.policy['batch_window'], lambda: self._flush(key), rank=3)

    def reset(self, inst):
        """Endpoint reset: lose all session state, keep durable records (handled by app)."""
        self.reset_times[inst].append(self.net.now)
        for s in self.all_sessions:
            if inst in s.ends:
                s.st[inst]['dead'] = s.st[inst]['swept'] = True      # the reset itself resends everything
                for seq, u in list(s.st[inst]['unacked'].items()):
                    u['dead'] = True
                s.st[inst]['pending'].clear()
        for k in [k for k in self.sessions if k[0] == inst]:
            del self.sessions[k]
        # durable outbox: anything not acknowledged is re-sent through a new session
        lost = [r for r in self.inflight.values() if r.src == inst]
        for r in lost:
            del self.inflight[r.rid]
            self.events.append((self.net.now, inst, 'RESET_RESEND', r.dst, r.rid, r.kind))
            self.send(r)
        if self.policy.get('restart_notice'):
            # Alternative A1: tell every peer seen in the last 7 days that our sessions are gone
            for peer, t in sorted(self.peers_seen[inst].items()):
                if self.net.now - t < SESSION_IDLE and peer != inst:
                    rec = Record('RESTART', inst, peer, dict(t_reset=self.net.now), 64, critical=True)
                    self.events.append((self.net.now, inst, 'RESTART_NOTICE', peer, rec.rid, 'RESTART'))
                    self.send(rec)

    # ------------------------------------------------------------------ sessions
    def _route_ok(self, path, t):
        r1 = route_eval(path, t, self.net.maint)
        if not r1['open']:
            return False
        la = self.policy['route_lookahead']
        if la:
            r2 = route_eval(path, t + la, self.net.maint)
            back = route_eval(tuple(reversed(path)), t + la, self.net.maint)
            return r2['open'] and back['open']
        return True

    def _choose_route(self, a_node, b_node, t, avoid=None):
        cands = []
        for p in routes(a_node, b_node):
            if avoid and set(p[1:-1]) == set(avoid):
                continue
            cands.append((route_T0(p, t), p))
        cands.sort()
        for T0, p in cands:
            if self._route_ok(p, t):
                return p
        for T0, p in cands:
            if route_eval(p, t, self.net.maint)['open']:
                return p
        return cands[0][1]

    def _session_usable(self, s, inst):
        st = s.st[inst]
        if st['dead']:
            return False
        if self.net.now - st['last_rx'] >= SESSION_IDLE:
            self._abandon(s, inst)
            return False
        path = s.path_from(inst)
        if not route_eval(path, self.net.now, self.net.maint)['open']:
            return False
        return True

    def _get_session(self, src, dst, avoid=None):
        s = self.sessions.get((src, dst))
        if s and self._session_usable(s, src) and not avoid:
            return s
        t_ok = self.quota.available_at(src, self.net.now)
        if t_ok > self.net.now:
            return t_ok
        a, b = self.inst[src], self.inst[dst]
        route = self._choose_route(a, b, self.net.now, avoid)
        s = Session(src, dst, a, b, route, self.net.now)
        self.all_sessions.append(s)
        self.sessions[(src, dst)] = s
        self.sessions[(dst, src)] = s
        self.peers_seen[src][dst] = self.net.now
        self.peers_seen[dst][src] = self.net.now
        self.quota.charge(src, self.net.now, 'SYN')
        self.originations[src] += 1
        self.events.append((self.net.now, src, 'SESSION_OPEN', dst, s.sid, '>'.join(route)))
        self._send_ctrl(s, src, 'SYN', attempt=1)
        return s

    def _send_ctrl(self, s, inst, kind, attempt=1, logical=None):
        path = s.path_from(inst)
        pkt = self.net.new_packet(kind, s, path, self.net.now if logical is None else logical[1], attempt=attempt,
                                  logical=logical or (kind, self.net.now, s.sid))
        if logical is None:
            pkt.created = self.net.now
        else:
            pkt.created = logical[1]
        self.net.send_hop(pkt, 0, self.net.now)
        if kind in ('SYN', 'SYNACK'):
            T0 = route_T0(path, self.net.now)
            Re = 2 * T0 + 24 * HOUR
            st = s.st[inst]
            st.setdefault('ctrl_pkts', {})[kind] = pkt.pid
            self.net.at(self.net.now + Re, lambda: self._ctrl_timer(s, inst, kind, attempt, pkt), rank=2)
        return pkt

    def _ctrl_timer(self, s, inst, kind, attempt, pkt):
        st = s.st[inst]
        if st['dead'] or st['estab']:
            return
        if kind == 'SYNACK':
            if st['synack_sent'] != attempt:
                return              # a duplicate SYN already triggered a newer SYN-ACK
            if attempt >= 4:
                return
            st['synack_sent'] += 1
        elif attempt >= 4:
            self._session_failed(s, inst)
            return
        self.net.discard_unlaunched(pkt.pid, pkt.route[0], pkt.route[1])
        self.net.stats['endpoint_retry_' + kind] += 1
        self._send_ctrl(s, inst, kind, attempt + 1, logical=pkt.logical)

    def _session_failed(self, s, inst):
        st = s.st[inst]
        st['dead'] = True
        peer = s.peer(inst)
        if self.sessions.get((inst, peer)) is s:
            del self.sessions[(inst, peer)]
            self.sessions.pop((peer, inst), None)
        self.events.append((self.net.now, inst, 'SESSION_FAILED', peer, s.sid, ''))
        groups = list(st['pending'])
        st['pending'].clear()
        for g in groups:
            for r in g:
                self._app_recover(r, s)

    # ------------------------------------------------------------------ data
    def _flush(self, key):
        self.flush_pending.discard(key)
        src, dst = key
        recs = self.outbox[key]
        if not recs:
            return
        s = self._get_session(src, dst)
        if not isinstance(s, Session):
            self.deferred += 1
            self.flush_pending.add(key)
            self.net.at(s, lambda: self._flush(key), rank=3)
            return
        st = s.st[src]
        # pack whole records into packets: 16-byte data sub-header + records <= 960-byte payload
        packets = self.pack(recs)
        # quota per data packet; a packet with any record other than RECEIVED is routine (44/day of 66)
        sent = 0
        for group in packets:
            routine = any(r.kind != 'RECEIVED' for r in group)
            t_ok = self.quota.available_at(src, self.net.now, routine=routine)
            if t_ok > self.net.now:
                break
            self._originate(st, src, group)
            sent += len(group)
        rest = recs[sent:]
        if rest and self.quota.available_at(src, self.net.now) <= self.net.now:
            # the routine share is spent but the reserve is not: receipts still go out
            rcpt = [r for r in rest if r.kind == 'RECEIVED']
            for group in self.pack(rcpt):
                if self.quota.available_at(src, self.net.now) > self.net.now:
                    break
                self._originate(st, src, group)
                for r in group:
                    rest.remove(r)
        self.outbox[key] = rest
        if self.outbox[key]:
            self.deferred += 1
            self.flush_pending.add(key)
            routine = any(r.kind != 'RECEIVED' for r in rest)
            self.net.at(self.quota.available_at(src, self.net.now, routine=routine), lambda: self._flush(key), rank=3)
        self._pump(s, src)

    @staticmethod
    def pack(recs):
        packets = []
        cur, size = [], HEADER + 16
        for r in recs:
            assert 0 < r.size <= PAYLOAD - 16, (r.kind, r.size)        # a record never spans packets
            if size + r.size > HEADER + PAYLOAD:
                packets.append(cur); cur, size = [], HEADER + 16
            cur.append(r); size += r.size
        if cur:
            packets.append(cur)
        return packets

    def _originate(self, st, src, group):
        self.quota.charge(src, self.net.now, 'DATA:' + '+'.join(r.kind for r in group))
        self.originations[src] += 1
        for r in group:
            self.inflight[r.rid] = r
        st['pending'].append(group)

    def _pump(self, s, inst):
        st = s.st[inst]
        can_send = st['estab'] if st['role'] == 'resp' else st.get('synack_rx', False)
        if not can_send or st['dead']:
            return
        while st['pending'] and len(st['unacked']) < WINDOW:
            group = st['pending'].popleft()
            seq = st['next_seq']; st['next_seq'] += 1
            u = dict(group=group, attempt=0, pids=[], created=self.net.now, dead=False)
            st['unacked'][seq] = u
            for r in group:
                self.rec_pkt[r.rid].append((s.sid, seq))
            self._send_data(s, inst, seq, u)

    def _send_data(self, s, inst, seq, u):
        u['attempt'] += 1
        path = s.path_from(inst)
        if u['pids']:
            self.net.discard_unlaunched(u['pids'][-1], path[0], path[1])
            self.net.stats['endpoint_retry_DATA'] += 1
        pkt = self.net.new_packet('DATA', s, path, u['created'], records=u['group'], dataseq=seq, attempt=u['attempt'],
                                  logical=('DATA', u['created'], s.sid, seq))
        u['pids'].append(pkt.pid)
        self.net.send_hop(pkt, 0, self.net.now)
        T0 = route_T0(path, self.net.now)
        Re = 2 * T0 + 24 * HOUR
        n = u['attempt']
        self.net.at(self.net.now + Re, lambda: self._data_timer(s, inst, seq, n), rank=2)
        fr = self.policy.get('fast_resubmit')
        if fr and n == 1 and any(r.critical for r in u['group']):
            self.net.at(self.net.now + 2 * T0 + fr, lambda: self._fast(s, inst, seq), rank=2)

    def _fast(self, s, inst, seq):
        """Optional application fast path: if a critical record is still unacknowledged
        after 2*T0+fr, resubmit it (charged) on a fresh session via the other relay."""
        st = s.st[inst]
        u = st['unacked'].get(seq)
        if not u or u['dead']:
            return
        for r in u['group']:
            if r.critical and r.app_attempts < self.policy['max_app_resubmits']:
                r.app_attempts += 1
                relay = [n for n in s.path_from(inst)[1:-1]]
                self.events.append((self.net.now, inst, 'FAST_RESUBMIT', r.dst, r.rid, r.kind))
                self._resubmit(r, avoid=relay)

    def _resubmit(self, r, avoid=None):
        src, dst = r.src, r.dst
        s = self._get_session(src, dst, avoid=avoid)
        if not isinstance(s, Session):
            self.net.at(s, lambda: self._resubmit(r, avoid), rank=3)
            return
        t_ok = self.quota.available_at(src, self.net.now)
        if t_ok > self.net.now:
            self.net.at(t_ok, lambda: self._resubmit(r, avoid), rank=3)
            return
        self.quota.charge(src, self.net.now, 'RESUBMIT:' + r.kind)
        self.originations[src] += 1
        s.st[src]['pending'].append([r])
        self._pump(s, src)

    def _data_timer(self, s, inst, seq, n):
        st = s.st[inst]
        u = st['unacked'].get(seq)
        if st['dead']:
            self._abandon(s, inst)         # e.g. reset; nothing may stay stranded on a dead session
            return
        if not u or u['attempt'] != n or u['dead']:
            return
        if n >= 4:
            del st['unacked'][seq]
            self.events.append((self.net.now, inst, 'DELIVERY_UNKNOWN', s.peer(inst), s.sid, seq))
            for r in u['group']:
                self._app_recover(r, s)
            self._pump(s, inst)
            return
        self._send_data(s, inst, seq, u)

    BACKOFF = (24 * HOUR, 48 * HOUR, 96 * HOUR, 168 * HOUR)

    def _app_recover(self, r, s=None):
        """Delivery unknown: abandon the session it travelled on and resubmit the same record
        (same financial identity) after the v3 application backoff 24/48/96/168 h."""
        if r.rid not in self.inflight:
            return
        if not self.policy['resubmit_after_unknown'] or r.app_attempts >= self.policy['max_app_resubmits']:
            self.events.append((self.net.now, r.src, 'GAVE_UP', r.dst, r.rid, r.kind))
            return
        r.app_attempts += 1
        if s is not None:
            self._abandon(s, r.src)
        delay = self.BACKOFF[min(r.app_attempts - 1, 3)] if self.policy.get('backoff', True) else 0.0
        self.events.append((self.net.now, r.src, 'APP_RESUBMIT_SCHEDULED', r.dst, r.rid, r.kind, self.net.now + delay))
        self.net.at(self.net.now + delay, lambda: self._resubmit_if_needed(r), rank=3)

    def _abandon(self, s, inst):
        """Stop using a session whose delivery is in doubt.  Every other record still unacknowledged or
        queued on it goes to application recovery too: the peer delivers in order, so nothing after the gap
        would ever be released or acknowledged on this session."""
        st = s.st[inst]
        if st.get('swept'):
            return
        st['dead'] = st['swept'] = True
        peer = s.peer(inst)
        if self.sessions.get((inst, peer)) is s:
            self.sessions.pop((inst, peer), None); self.sessions.pop((peer, inst), None)
        stranded = [r for u in st['unacked'].values() for r in u['group']] + [r for g in st['pending'] for r in g]
        for u in st['unacked'].values():
            u['dead'] = True
        st['unacked'].clear(); st['pending'].clear()
        for r in stranded:
            self._app_recover(r)

    def _resubmit_if_needed(self, r):
        if r.rid not in self.inflight:
            return
        self.events.append((self.net.now, r.src, 'APP_RESUBMIT', r.dst, r.rid, r.kind))
        self._resubmit(r)

    # ------------------------------------------------------------------ receive
    def _on_packet(self, pkt):
        s = pkt.session
        if s is None:
            return
        inst = s.ends[0] if s.nodes[s.ends[0]] == pkt.route[-1] else s.ends[1]
        st = s.st[inst]
        if st['dead']:
            self.net.stats['dead_session_drop'] += 1
            self.events.append((self.net.now, inst, 'IGNORED_UNKNOWN_SESSION', s.peer(inst), s.sid, pkt.kind))
            return
        if self.net.now - st['last_rx'] >= SESSION_IDLE:
            self._abandon(s, inst)
            self.net.stats['dead_session_drop'] += 1
            return
        st['last_rx'] = self.net.now
        k = pkt.kind
        if k == 'SYN':
            if not st['estab'] and st['synack_sent'] < 4:
                st['synack_sent'] += 1
                self._send_ctrl(s, inst, 'SYNACK', attempt=st['synack_sent'])
        elif k == 'SYNACK':
            self._send_ctrl(s, inst, 'ACK')
            if not st.get('synack_rx'):
                st['synack_rx'] = True
                st['estab'] = True
                self._pump(s, inst)
        elif k == 'ACK':
            if not st['estab']:
                st['estab'] = True
                self._release(s, inst)
                self._pump(s, inst)
        elif k == 'DATA':
            if pkt.dataseq in st['delivered'] or pkt.dataseq < st['rx_next']:
                self._send_dack(s, inst, pkt.dataseq)
                self.net.stats['dup_data'] += 1
                return
            st['rx_buf'][pkt.dataseq] = pkt
            if st['estab']:
                self._release(s, inst)
        elif k == 'DACK':
            peer_st = st
            u = peer_st['unacked'].pop(pkt.dataseq, None)
            if u:
                for r in u['group']:
                    self.inflight.pop(r.rid, None)
                self._pump(s, inst)

    def _release(self, s, inst):
        st = s.st[inst]
        while st['rx_next'] in st['rx_buf']:
            pkt = st['rx_buf'].pop(st['rx_next'])
            st['delivered'].add(st['rx_next'])
            st['rx_next'] += 1
            self._send_dack(s, inst, pkt.dataseq)
            for r in pkt.records:
                if r.rid in self.delivered_rids[inst]:
                    self.net.stats['dup_record'] += 1
                    continue
                self.delivered_rids[inst].add(r.rid)
                if r.kind == 'RESTART':
                    self._on_restart(inst, r.src, s)
                    continue
                self.deliver(inst, r)
        # out-of-order data waits (in-order delivery)

    def _on_restart(self, inst, peer, via):
        for x in self.all_sessions:
            if x is not via and inst in x.ends and peer in x.ends and not x.st[inst]['dead']:
                x.st[inst]['dead'] = x.st[inst]['swept'] = True
                for seq, u in list(x.st[inst]['unacked'].items()):
                    u['dead'] = True
                    for r in u['group']:
                        if r.rid in self.inflight:
                            self.events.append((self.net.now, inst, 'RESTART_RESUBMIT', peer, r.rid, r.kind))
                            self._resubmit(r)
                for g in list(x.st[inst]['pending']):
                    for r in g:
                        self.send(r)
                x.st[inst]['pending'].clear()
        for k in [k for k in self.sessions if inst in k and peer in k and self.sessions[k] is not via]:
            del self.sessions[k]

    def _send_dack(self, s, inst, seq):
        path = s.path_from(inst)
        pkt = self.net.new_packet('DACK', s, path, self.net.now, dataseq=seq)
        self.net.send_hop(pkt, 0, self.net.now)


class Direct:
    """Direct service: per-principal 12 per rolling 24 h, >=60 s spacing, no retries/receipts."""

    def __init__(self, net):
        self.net = net
        self.hist = defaultdict(deque)
        self.hist_planned = defaultdict(list)    # used by protocol.World for quota-aware scheduling
        self.log = []

    def send(self, principal, a, b, deliver, label=''):
        t = self.net.now
        q = self.hist[principal]
        while q and q[0] <= t - DAY:
            q.popleft()
        if len(q) >= 12 or (q and t - q[-1] < 60):
            raise RuntimeError('direct quota')
        q.append(t)
        f = direct_flight(a, b, t)
        killed = any(inc.kills_launch(a, b, f['te']) for inc in self.net.incidents if inc.kind == 'isolation')
        lost = (not f['open']) or killed or (self.net.loss and self.net.rng.random() < f['p_loss'])
        self.log.append((t, principal, a, b, label, f['te'], f['arrive'], f['d'], f['p_loss'], lost))
        if not lost:
            self.net.at(f['arrive'], deliver, rank=0, sender=NODE_ID[a])
        return f
