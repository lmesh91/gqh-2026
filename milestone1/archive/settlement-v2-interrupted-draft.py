"""Version 2 funded order and debit-proof settlement model.
Integer quantities/amounts in tests; production amounts use integer cents.
Authenticated official messages and honest operators are assumed, not implemented
cryptographically. State here is durable financial state, independent of sessions.
"""
from dataclasses import dataclass, asdict
from collections import defaultdict
import copy, hashlib, json

class Rejected(ValueError): pass
class Pending(Exception): pass

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()

@dataclass(frozen=True)
class Terms:
    owner: str
    home: str
    venue: str
    order: str
    instrument: str
    side: str
    quantity: int
    limit: int
    expiry: int=86400
    epoch: int=2
    @property
    def hash(self): return digest(asdict(self))
    @property
    def asset(self): return 'CASH' if self.side=='BUY' else self.instrument
    @property
    def amount(self): return self.quantity*self.limit if self.side=='BUY' else self.quantity

@dataclass(frozen=True)
class Grant:
    id: str
    terms: Terms

@dataclass(frozen=True)
class Debit:
    grant: Grant
    sequence: int
    amount: int
    quantity: int
    destination_home: str
    destination_owner: str

@dataclass(frozen=True)
class Fill:
    id: str
    venue: str
    quantity: int
    price: int
    committed_at: int
    buy: Debit
    sell: Debit
    @property
    def hash(self): return digest(asdict(self))
    @property
    def debits(self): return (self.buy,self.sell)

@dataclass(frozen=True)
class Proof:
    fill_hash: str
    grant_id: str
    source: str
    asset: str
    amount: int
    destination_home: str
    destination_owner: str

class Home:
    def __init__(self,name,balances):
        self.name=name; self.free=defaultdict(int,balances); self.grants={}
        self.proofs={}; self.imported={}; self.order_grants={}
    def authorize(self,g):
        if g.id in self.grants:
            if self.grants[g.id]['grant']!=g: raise Rejected('grant ID conflict')
            return g
        t=g.terms
        if t.home!=self.name or t.side not in ('BUY','SELL') or min(t.quantity,t.limit)<=0: raise Rejected('invalid terms')
        key=(t.owner,t.venue,t.order)
        if key in self.order_grants: raise Rejected('one grant per order; no reattachment')
        if self.free[t.owner,t.asset]<t.amount: raise Rejected('insufficient unencumbered funds')
        self.free[t.owner,t.asset]-=t.amount
        self.grants[g.id]=dict(grant=g,remaining=t.amount,filled=0,last=0,close_at=None,closed=False)
        self.order_grants[key]=g.id
        return g
    def close(self,g,final_sequence):
        r=self.grants[g.id]
        if g!=r['grant'] or final_sequence<r['last']: raise Rejected('invalid closure')
        if r['close_at'] is not None and r['close_at']!=final_sequence: raise Rejected('conflicting closure')
        r['close_at']=final_sequence
        self._finish_close(r)
    def _finish_close(self,r):
        if not r['closed'] and r['close_at']==r['last']:
            t=r['grant'].terms
            self.free[t.owner,t.asset]+=r['remaining']; r['remaining']=0; r['closed']=True
    def apply(self,f):
        local=[d for d in f.debits if d.grant.terms.home==self.name]
        if not local: raise Rejected('not a source')
        # Validate ALL local legs before changing any. Essential when both traders share a home.
        for d in local:
            t=d.grant.terms; r=self.grants.get(d.grant.id); key=(d.grant.id,d.sequence)
            if r is None or r['grant']!=d.grant or f.venue!=t.venue: raise Rejected('grant/venue mismatch')
            if key in self.proofs:
                if self.proofs[key].fill_hash!=f.hash: raise Rejected('sequence reused for another fill')
                continue
            if r['closed'] or (r['close_at'] is not None and d.sequence>r['close_at']): raise Rejected('closed grant')
            if d.sequence!=r['last']+1: raise Pending('missing prior fill')
            if f.committed_at>=t.expiry: raise Rejected('expired at commit')
            if d.quantity!=f.quantity or f.quantity<=0 or f.price<=0: raise Rejected('invalid quantity/price')
            if t.side=='BUY':
                if d!=f.buy or f.price>t.limit or d.amount!=f.quantity*f.price: raise Rejected('buy bounds')
                counter=f.sell.grant.terms
            else:
                if d!=f.sell or f.price<t.limit or d.amount!=f.quantity: raise Rejected('sell bounds')
                counter=f.buy.grant.terms
            if (d.destination_home,d.destination_owner)!=(counter.home,counter.owner): raise Rejected('destination changed')
            if counter.instrument!=t.instrument or r['remaining']<d.amount or r['filled']+d.quantity>t.quantity: raise Rejected('budget exceeded')
        result=[]
        for d in local:
            key=(d.grant.id,d.sequence); r=self.grants[d.grant.id]; t=d.grant.terms
            if key not in self.proofs:
                r['remaining']-=d.amount; r['filled']+=d.quantity; r['last']=d.sequence
                self.proofs[key]=Proof(f.hash,d.grant.id,self.name,t.asset,d.amount,d.destination_home,d.destination_owner)
                self._finish_close(r)
            result.append(self.proofs[key])
        return result
    def credit(self,f,proofs):
        # Each destination requires the SAME fill's complete debit evidence.
        expected={d.grant.id:Proof(f.hash,d.grant.id,d.grant.terms.home,d.grant.terms.asset,d.amount,d.destination_home,d.destination_owner) for d in f.debits}
        supplied={p.grant_id:p for p in proofs}
        if supplied!=expected: raise Pending('complete matching debit evidence absent or wrong')
        for d in f.debits:
            if d.grant.terms.home==self.name:
                if self.proofs.get((d.grant.id,d.sequence))!=expected[d.grant.id]: raise Pending('own debit not durably applied')
        for p in proofs:
            if p.destination_home!=self.name: continue
            key=(f.hash,p.grant_id)
            if key not in self.imported:
                self.free[p.destination_owner,p.asset]+=p.amount; self.imported[key]=p

class Market:
    def __init__(self,name):
        self.name=name; self.grants={}; self.orders={}; self.order_grants={}; self.fills={}; self.counter=0
    def publish(self,g):
        if g.terms.venue!=self.name: raise Rejected('wrong market')
        if g.id in self.grants:
            if self.grants[g.id]['grant']!=g: raise Rejected('grant conflict')
            return
        key=(g.terms.owner,g.terms.order)
        if key in self.order_grants: raise Rejected('order already funded')
        self.order_grants[key]=g.id
        self.grants[g.id]=dict(grant=g,spent=0,filled=0,sequence=0,closed=False)
    def order(self,terms,grant_id):
        # This prototype requires the official grant before acceptance. A UI may buffer
        # an unfunded intent, but it has no executable priority and cannot reach fill().
        r=self.grants.get(grant_id)
        if r is None: raise Pending('no official backing')
        if r['grant'].terms!=terms: raise Rejected('backing belongs to different order/terms')
        if r['closed']: raise Rejected('closed order')
        key=(terms.owner,terms.order)
        if key in self.orders and self.orders[key]!=(terms,grant_id): raise Rejected('order ID conflict')
        self.orders[key]=(terms,grant_id)
    def fill(self,buy_id,sell_id,quantity,price,now=1):
        br=self.grants[buy_id]; sr=self.grants[sell_id]
        for r,side in [(br,'BUY'),(sr,'SELL')]:
            t=r['grant'].terms
            if r['closed'] or t.side!=side or (t.owner,t.order) not in self.orders: raise Rejected('order not executable')
            if now>=t.expiry or quantity<=0 or r['filled']+quantity>t.quantity: raise Rejected('expired/quantity')
            if side=='BUY' and (price>t.limit or price<=0): raise Rejected('buy limit')
            if side=='SELL' and price<t.limit: raise Rejected('sell limit')
        if br['grant'].terms.instrument!=sr['grant'].terms.instrument: raise Rejected('different instruments')
        # Check BEFORE mutating either order: one serialized, durable matching operation.
        if br['spent']+quantity*price>br['grant'].terms.amount or sr['spent']+quantity>sr['grant'].terms.amount: raise Rejected('budget')
        self.counter+=1; b=br['grant'].terms; s=sr['grant'].terms
        bd=Debit(br['grant'],br['sequence']+1,quantity*price,quantity,s.home,s.owner)
        sd=Debit(sr['grant'],sr['sequence']+1,quantity,quantity,b.home,b.owner)
        f=Fill(f'{self.name}:{self.counter}',self.name,quantity,price,now,bd,sd)
        for r,d in [(br,bd),(sr,sd)]: r['spent']+=d.amount; r['filled']+=quantity; r['sequence']+=1
        self.fills[f.id]=f
        return f
    def close(self,grant_id):
        r=self.grants[grant_id]; r['closed']=True
        return r['grant'],r['sequence']

def totals(homes):
    """Audit oracle only: application actors never consult this global view."""
    total=defaultdict(int); exports={}; imported=set()
    for h in homes:
        for (_,a),v in h.free.items(): assert v>=0; total[a]+=v
        for r in h.grants.values(): assert r['remaining']>=0; total[r['grant'].terms.asset]+=r['remaining']
        for p in h.proofs.values(): exports[p.fill_hash,p.grant_id]=p
        imported.update(h.imported)
    assert imported<=set(exports)
    for key,p in exports.items():
        if key not in imported: total[p.asset]+=p.amount
    return dict(total)

def example(venue='Mars',buyer_home='Earth',seller_home='Mars',instrument='ARES'):
    homes={n:Home(n,{}) for n in {buyer_home,seller_home,venue}}
    homes[buyer_home].free['Alice','CASH']=150000
    homes[seller_home].free['Seller','CASH']=100000
    homes[seller_home].free['Seller',instrument]=1000
    b=Grant('buyer-grant',Terms('Alice',buyer_home,venue,'buy-1',instrument,'BUY',1000,100))
    s=Grant('seller-grant',Terms('Seller',seller_home,venue,'sell-1',instrument,'SELL',1000,100))
    m=Market(venue)
    for g in (b,s): homes[g.terms.home].authorize(g)
    return homes,m,b,s
