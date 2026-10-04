"""Shared conditional no-loss transport for v2 traces.
Serialization, moving receivers, pinned handshakes, hop receipts and data ACKs.
Raises on known closure; not a lossy/closure-wait simulator.
"""
import heapq, math
from collections import defaultdict, Counter
from model import best, photon, launchable

class Trace:
    def __init__(self,origin='Earth'):
        self.origin=origin
        self.q=[]; self.tick=0; self.now=0.; self.busy=defaultdict(float); self.rows=[]; self.fin=[]; self.seq=0
    def at(self,t,fn):
        self.tick+=1; heapq.heappush(self.q,(t,self.tick,fn))
    def launch(self,a,b,ready,label,pid,cb,receipt=False):
        def enqueue():
            start=max(self.now,self.busy[a,b]); te=start+1
            # Conditional traces must fail visibly if their no-closure assumption does not hold.
            if not launchable(a,b,te):
                raise RuntimeError('Closure encountered: exact waiting/retries require the full transport simulator')
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
    def run(self):
        while self.q:
            self.now,_,fn=heapq.heappop(self.q); fn()

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
