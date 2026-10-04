"""Executable financial safety checks and a conditional no-loss packet trace.
The trace implements serialization, hop receipts, data ACKs, handshake gating,
route pinning and known closures. It does NOT implement the full lossy endpoint
transport; failure tests below are explicitly application-level state exploration.
"""
import copy, csv, heapq, itertools, json, math
from collections import Counter, defaultdict
from model import OUT,NAMES,ROOT,best,photon,launchable,route,save,csvout,LIGHT

class Trace:
    def __init__(self,origin='Earth'):
        self.origin=origin
        self.q=[]; self.tick=0; self.now=0.; self.busy=defaultdict(float); self.rows=[]; self.fin=[]; self.seq=0
        self.originated=0; self.direct=0; self.session=None; self.receiver_ready=False; self.buffer=[]
    def at(self,t,fn):
        self.tick+=1; heapq.heappush(self.q,(t,self.tick,fn))
    def note(self,action,knowledge,state): self.fin.append(dict(hour=self.now/3600,actor='Mars clearer' if action not in ('RESERVE_LOCAL','PREPARED','APPLIED','RELEASED') else self.origin+' exchange',action=action,local_knowledge=knowledge,state=state))
    def launch(self,a,b,ready,label,pid,cb,receipt=False):
        def enqueue():
            start=max(self.now,self.busy[a,b]); te=start+1
            # No-loss baseline traces below do not encounter closure, but wait safely if they do.
            if not launchable(a,b,te):
                self.at(start+60,lambda:self.launch(a,b,self.now,label,pid,cb,receipt)); return
            self.busy[a,b]=te; ta,d,c=photon(a,b,te); ta=float(ta)
            self.rows.append(dict(packet_id=pid,kind=label,sender=a,receiver=b,ready_s=self.now,emission_s=te,arrival_s=ta,distance_au=float(d),loss_probability=1-math.exp(-.02*float(d))))
            def arrive():
                if not receipt:
                    self.seq+=1; rid=self.seq
                    self.launch(b,a,self.now,'HOP_RECEIPT',rid,lambda:None,True)
                cb()
            self.at(ta,arrive)
        self.at(ready,enqueue)
    def packet(self,path,label,cb):
        self.seq+=1; pid=self.seq
        def hop(k):
            a,b=path[k:k+2]
            def nextstep():
                if k==len(path)-2: cb()
                else: self.at(self.now+1,lambda:hop(k+1))
            self.launch(a,b,self.now,label,pid,nextstep)
        hop(0)
    def data(self,a,b,label,cb):
        self.originated+=1
        path=self.session if a==self.origin else self.session[::-1]
        def delivered():
            self.packet(path[::-1],'DATA_ACK',lambda:None)
            if b=='Mars' and not self.receiver_ready: self.buffer.append(cb)
            else: cb()
        self.packet(path,label,delivered)
    def run(self):
        while self.q:
            self.now,_,fn=heapq.heappop(self.q); fn()

def worked(origin='Earth',suffix=''):
    t=Trace(origin); flags={'order':False,'reserve':False}; amount=100000
    def match():
        if not all(flags.values()): return
        t.note('MATCH','Order and official cash reservation received; seller inventory reserved','Earth $100000 and Mars 1000 shares locked; no spendable proceeds')
        t.data('Mars',origin,'PREPARE',prepared)
    def prepared():
        t.note('PREPARED','Exact trade digest agrees with cash reservation','Earth reservation irreversibly prepared; cannot time out')
        t.data(origin,'Mars','PREPARED',commit)
    def commit():
        t.note('COMMIT','Both local Mars and Earth prepared records known','Immutable commit; Mars debits seller shares into staged Earth custody; both outputs blocked')
        t.data('Mars',origin,'COMMIT',applied)
    def applied():
        t.note('APPLIED','Authoritative commit received','Earth debits $100000; stages 1000 share entitlement; export cash is in transit, not new money')
        t.data(origin,'Mars','APPLIED',release)
    def release():
        t.note('RELEASE','All debit/apply certificates present','Mars seller cash spendable; Earth share release in flight; discharge and backed claims recorded')
        t.data('Mars',origin,'RELEASE',released)
    def released():
        t.note('RELEASED','All-participant applied certificate received','Earth 1000 shares spendable in exclusive local custody; trade complete')
        t.data(origin,'Mars','RELEASED',lambda:t.note('COMPLETE_KNOWN','Both release receipts known','Clearer knows both local balances are spendable'))
    def reserved():
        flags['reserve']=True; t.note('RESERVATION_RECEIVED','Earth official reservation present','Funded order eligible once client instruction arrives'); match()
    def start_data():
        t.packet(t.session,'ACK',ack_received)
        t.data(origin,'Mars','RESERVATION',reserved)
    def ack_received():
        t.receiver_ready=True
        for cb in t.buffer: cb()
        t.buffer=[]
    def syn_received(): t.packet(t.session[::-1],'SYN_ACK',start_data)
    def order_received(): flags['order']=True; match()
    # Both client submissions local at t=0, effective after 1 s. Seller order ready at Mars.
    t.at(1,lambda:t.note('RESERVE_LOCAL','Buyer requested funding locally','Buyer cash $100000 encumbered on Earth'))
    def start():
        t.session=best(origin,'Mars',t.now)['path']; t.originated+=1
        t.packet(t.session,'SYN',syn_received)
    t.at(1,start)
    # Remote buyer direct order: local access, serialization, flight, local access.
    te=2; ta,d,c=photon(origin,'Mars',te); assert c>=.1
    t.direct=1; t.at(float(ta)+1,order_received)
    t.run()
    for entry in t.fin:
        entry['state']=entry['state'].replace('Earth',origin)
        entry['local_knowledge']=entry['local_knowledge'].replace('Earth',origin)
    csvout('trade_packets'+suffix+'.csv',sorted(t.rows,key=lambda x:(x['emission_s'],x['packet_id'])))
    csvout('trade_events'+suffix+'.csv',t.fin)
    times={r['action']:r['hour'] for r in t.fin}
    summary=dict(label='conditional no-loss; cold session; no pre-epoch traffic',route=t.session,backbone_originations=t.originated,backbone_launches=len(t.rows),direct_launches=t.direct,total_launches=len(t.rows)+t.direct,direct_required_success_probability=math.exp(-.08*float(d)),complete_hour=times['RELEASED'],clearer_knows_complete_hour=times['COMPLETE_KNOWN'],backed_claim_hour=times['COMMIT'],discharge_hour=times['RELEASE'],peak_cash_encumbered=amount,peak_shares_encumbered=1000,cash_asset_hours=amount*(times['RELEASE']-1/3600),share_asset_hours=1000*(times['RELEASED']-1/3600),capital_utilization=.2,capital_efficiency=1,types=dict(Counter(r['kind'] for r in t.rows)))
    save('trade_summary'+suffix+'.json',summary)

class Ledger:
    """Two source assets, two destinations; in-transit units counted exactly once."""
    def __init__(self):
        self.stage=['FREE','FREE']; self.decision=None; self.ack=set(); self.released=[False,False]; self.seen=set()
    def op(self,op,i):
        if op=='prepare' and self.decision is None and self.stage[i]=='FREE': self.stage[i]='PREPARED'
        if op=='decide' and self.decision is None and self.stage==['PREPARED']*2: self.decision='COMMIT'
        if op=='abort' and self.decision is None: self.decision='ABORT'
        if op=='apply' and self.decision=='COMMIT' and self.stage[i]=='PREPARED': self.stage[i]='APPLIED'
        if op=='ack' and self.stage[i]=='APPLIED': self.ack.add(i)
        if op=='release' and self.decision=='COMMIT' and self.ack=={0,1}: self.released[i]=True
        if op=='unlock' and self.decision=='ABORT' and self.stage[i]=='PREPARED': self.stage[i]='FREE'
        # reset, expiry, loss, cancellation, duplicate stale payload: cannot override financial state.
        self.check()
    def check(self):
        for i in (0,1):
            source=1 if self.stage[i]!='APPLIED' else 0
            staged=1 if self.stage[i]=='APPLIED' and not self.released[i] else 0
            destination=int(self.released[i]); assert source+staged+destination==1
            if destination: assert self.stage==['APPLIED']*2 and self.decision=='COMMIT'
        if self.decision=='ABORT': assert not any(self.released) and 'APPLIED' not in self.stage
    def key(self): return (tuple(self.stage),self.decision,tuple(sorted(self.ack)),tuple(self.released))
def safety():
    actions=list(itertools.product(['prepare','decide','abort','apply','ack','release','unlock','reset','expiry','cancel','lost'],range(2)))
    init=Ledger(); reached={init.key():init}; todo=[init]; edges=0
    while todo:
        s=todo.pop()
        for a,i in actions:
            n=copy.deepcopy(s); n.op(a,i); edges+=1
            if n.key() not in reached: reached[n.key()]=n; todo.append(n)
    s=Ledger(); trail=[]
    schedule=[(0,'prepare',0),(0,'prepare',1),(1,'decide',0),(2,'apply',0),(2,'ack',0),(3,'release',0),(4,'reset',1),(720,'expiry',1),(721,'apply',1),(722,'ack',1),(723,'release',0),(724,'release',1)]
    for h,a,i in schedule:
        s.op(a,i); trail.append(dict(hour=h,event=a,participant=i,state=str(s.key())))
    assert all(s.released); csvout('failure_recovery_states.csv',trail)
    # Price product: Q=2000, K=100, bounds 60..140, each side posts Q*40.
    prices=[100,110,120,130,125,120,110,100,90,80,70,75]
    for p in prices+[0,1,1000,10**9]:
        payoff=2000*(min(140,max(60,p))-100)
        long=80000+payoff; short=80000-payoff
        assert min(long,short)>=0 and long+short==160000
    # Idempotency across sessions, payload mutation, out-of-order versions.
    records={}; rid=('Alice',1); payload=('buy',1000,100)
    def req(key,value):
        if key in records:
            if records[key]!=value: return 'CONFLICT'
            return 'DUPLICATE'
        records[key]=value; return 'ACCEPT'
    assert req(rid,payload)=='ACCEPT' and req(rid,payload)=='DUPLICATE' and req(rid,('buy',2000,100))=='CONFLICT'
    save('safety_checks.json',dict(reachable_abstract_states=len(reached),checked_transitions=edges,invariants=['unit conservation','no release before every debit applied','abort excludes commit','reset and packet expiry do not unlock','duplicate application request cannot execute twice','bounded payout funded for both directions'],limitations='Abstract financial model, not proof of implementation or full transport. Explicit application recovery trace spans packet expiry at 720 h.'))

def hop_analysis():
    rows=[]
    # Exact conservative abandonment bound: no timely receipt implies either forward loss or receipt loss.
    # Iterate own emission geometry for each of four attempts, flight-only R_h.
    for a,b in [('Earth','Relay A'),('Relay A','Mars'),('Neptune','Relay A'),('Relay A','Neptune')]:
        te=1.; qs=[]; ps=[]; launches=[]
        for k in range(4):
            ta,d,c=photon(a,b,te); tr,dr,cr=photon(b,a,float(ta)+1)
            pf=1-math.exp(-.02*float(d)); pr=1-math.exp(-.02*float(dr)); q=1-(1-pf)*(1-pr)
            qs.append(q); ps.append(pf); launches.append(dict(attempt=k+1,emission_s=te,p_forward=pf,p_receipt=pr,no_receipt_probability=q))
            te+=2*(float(ta)-te)+3600+1
        rows.append(dict(sender=a,receiver=b,no_closure_no_queue_assumption=True,attempts=launches,abandonment_upper_bound=math.prod(qs),data_never_arrives_probability=math.prod(ps),expected_forward_launches_upper=sum(math.prod(qs[:j]) for j in range(4))))
    save('hop_probability.json',rows)
def failure_probes():
    probes=[]
    for a,b,duration in [('Earth','Relay A',6),('Neptune','Relay A',72)]:
        te=1.; attempts=[]; delivered=False
        for k in range(4):
            ta,d,c=photon(a,b,te); failed=te<duration*3600
            attempts.append(dict(attempt=k+1,emission_hour=te/3600,nominal_arrival_hour=float(ta)/3600,forced_loss=failed))
            delivered |= not failed
            timeout=te+2*(float(ta)-te)+3600
            te=timeout+1
        assert not delivered
        probes.append(dict(sender=a,receiver=b,incident_hours=duration,attempts=attempts,abandoned_hour=timeout/3600,financial_consequence='delivery unknown; keep prepared assets locked; application/session recovery required'))
    save('forced_loss_hop_probes.json',probes)

if __name__=='__main__':
    worked(); safety(); hop_analysis(); failure_probes(); print('Conditional trace and financial checks passed.')
