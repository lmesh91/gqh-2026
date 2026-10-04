"""Earth buys Ceres shares; Mars clears. Conditional no-loss, three cold
sessions opened in parallel at t=1 s. Reuses the validated launch/receipt model.
Not a complete lossy transport implementation.
"""
from collections import Counter, defaultdict
import math
from model import best, photon, launchable, csvout, save
from verify import Trace

class MultiTrace(Trace):
    def __init__(self):
        super().__init__(); self.sessions={}; self.events=[]; self.origins=Counter(); self.commands=[]
    def note_event(self,actor,event,state):
        self.events.append(dict(hour=self.now/3600,actor=actor,event=event,financial_state=state))
    def connect(self,a,b):
        key=frozenset((a,b)); path=best(a,b,self.now)['path']
        s=dict(paths={(a,b):path,(b,a):path[::-1]},ready={a:False,b:False},pending={a:[],b:[]},buffers={a:[],b:[]})
        self.sessions[key]=s; self.origins[a]+=1
        def enable(node):
            s['ready'][node]=True
            for fn in s['buffers'][node]: fn()
            s['buffers'][node]=[]
            pending=s['pending'][node]; s['pending'][node]=[]
            for fn in pending: fn()
        def synack():
            self.packet(path,'ACK',lambda:enable(b)); enable(a)
        self.packet(path,'SYN',lambda:self.packet(path[::-1],'SYN_ACK',synack))
    def send(self,a,b,label,cb):
        s=self.sessions[frozenset((a,b))]
        def emit():
            self.origins[a]+=1
            self.commands.append(dict(hour=self.now/3600,sender=a,receiver=b,message=label))
            path=s['paths'][a,b]
            def delivered():
                self.packet(path[::-1],'DATA_ACK',lambda:None)
                if s['ready'][b]: cb()
                else: s['buffers'][b].append(cb)
            self.packet(path,label,delivered)
        if s['ready'][a]: emit()
        else: s['pending'][a].append(emit)

def main():
    t=MultiTrace(); received=set(); prepared=set(); applied=set(); released=set(); acknowledgments=set()
    funds={'Alice':150000,'Cara':100000}; shares={'Alice':0,'Cara':1000}; cash_transit=0; share_transit=0
    def audit():
        assert sum(funds.values())+cash_transit==250000
        assert sum(shares.values())+share_transit==1000
        assert not released or applied=={'Earth','Ceres'}
    def release_received(n):
        nonlocal cash_transit,share_transit
        if n=='Earth': shares['Alice']+=share_transit; share_transit=0
        else: funds['Cara']+=cash_transit; cash_transit=0
        released.add(n); audit()
        t.note_event(n,'SPENDABLE',str(dict(cash=funds,shares=shares,cash_transit=cash_transit,share_transit=share_transit)))
        def ack():
            acknowledgments.add(n)
            if len(acknowledgments)==2: t.note_event('Mars','COMPLETE_KNOWN','Both home releases acknowledged')
        t.send(n,'Mars','RELEASED',ack)
    def applied_received(n):
        applied.add(n)
        t.note_event('Mars','APPLIED_RECEIVED_'+n,'Debit certificate received; outputs remain blocked until release')
        if len(applied)==2:
            t.note_event('Mars','RELEASE_READY','Both source debits known; obligation discharged')
            for p in ['Earth','Ceres']: t.send('Mars',p,'RELEASE',lambda p=p:release_received(p))
    def commit_received(n):
        nonlocal cash_transit,share_transit
        if n=='Earth': funds['Alice']-=100000; cash_transit=100000
        else: shares['Cara']-=1000; share_transit=1000
        audit(); t.note_event(n,'APPLIED','Outgoing asset debited; incoming claim blocked')
        t.send(n,'Mars','APPLIED',lambda:applied_received(n))
    def vote(n):
        prepared.add(n)
        if len(prepared)==2:
            t.note_event('Mars','COMMIT','Both exact debits and destinations prepared; decision irreversible')
            for p in ['Earth','Ceres']: t.send('Mars',p,'COMMIT',lambda p=p:commit_received(p))
    def prepare_received(n):
        t.note_event(n,'PREPARED','Exact outgoing debit and incoming destination bound to manifest')
        t.send(n,'Mars','PREPARED',lambda:vote(n))
    def proposed():
        t.note_event('Mars','PROPOSE_RECEIVED','Ceres match known; request exact preparation from both authorities')
        for p in ['Earth','Ceres']: t.send('Mars',p,'PREPARE',lambda p=p:prepare_received(p))
    def market_input(kind):
        received.add(kind); t.note_event('Ceres',kind,'Client instruction or official reservation received')
        if received=={'ORDER','RESERVATION'}:
            t.note_event('Ceres','MATCH','Alice $100000 reserved on Earth; Cara 1000 Belt Works shares reserved on Ceres')
            t.send('Ceres','Mars','PROPOSE',proposed)
    def start():
        t.note_event('Earth/Ceres','RESERVE_LOCAL','Alice reserves $100000; Cara reserves 1000 shares; neither has clearing authority')
        for a,b in [('Earth','Ceres'),('Earth','Mars'),('Ceres','Mars')]: t.connect(a,b)
        t.send('Earth','Ceres','RESERVATION',lambda:market_input('RESERVATION'))
    t.at(1,start)
    ta,d,c=photon('Earth','Ceres',2); assert c>=.1
    t.at(float(ta)+1,lambda:market_input('ORDER'))
    t.run(); audit()
    assert funds=={'Alice':50000,'Cara':200000} and shares=={'Alice':1000,'Cara':0}
    last=defaultdict(lambda:-math.inf)
    for r in sorted(t.rows,key=lambda x:x['emission_s']):
        k=r['sender'],r['receiver']; assert r['emission_s']-last[k]>=1-1e-8
        assert launchable(*k,r['emission_s']); last[k]=r['emission_s']
    csvout('earth_ceres_events.csv',t.events)
    csvout('earth_ceres_packets.csv',sorted(t.rows,key=lambda x:(x['emission_s'],x['packet_id'])))
    csvout('earth_ceres_messages.csv',t.commands)
    summary=dict(scenario='Separate reset of original book; Alice buys all 1000 Cara Belt Works shares at $100 each; Mars clears',assumptions='No random loss; three cold sessions opened in parallel at 1 s; no closures encountered; no optional client reply',backbone_originations=sum(t.origins.values()),originations_by_institution=dict(t.origins),backbone_launches=len(t.rows),direct_launches=1,total_launches=len(t.rows)+1,direct_order_success_probability=math.exp(-.08*float(d)),spendable_hours={x['actor']:x['hour'] for x in t.events if x['event']=='SPENDABLE'},complete_hour=max(x['hour'] for x in t.events if x['event']=='SPENDABLE'),clearer_knows_complete_hour=t.events[-1]['hour'],types=dict(Counter(r['kind'] for r in t.rows)))
    assert summary['backbone_originations']==17 and summary['total_launches']==149
    save('earth_ceres_summary.json',summary)
    print(summary)
if __name__=='__main__': main()
