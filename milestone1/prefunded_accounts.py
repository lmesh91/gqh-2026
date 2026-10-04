"""V3 bounded ledger reference: prefunding, local holds/fills, withdrawals.
Honest authenticated operators and atomic durable operations are assumptions.
No network, full matching loop, derivative lifecycle, close/compaction or codec.
Callers supply the already-authenticated principal/operator, never client proof.
"""
from dataclasses import dataclass
from collections import defaultdict
import copy

MAX=2**63-1
CASH='ND'
class Rejected(ValueError): pass

def positive(n):
    if type(n) is not int or not 0<n<=MAX: raise Rejected('positive bounded integer required')

@dataclass(frozen=True)
class Transfer:
    source: str
    export_id: str
    destination: str
    owner: str
    asset: str
    amount: int

@dataclass(frozen=True)
class Order:
    owner: str
    order_id: str
    asset: str
    side: str
    quantity: int
    limit: int
    expiry: int

class Exchange:
    def __init__(self,name,principals):
        self.name=name; self.principals=set(principals)
        self.available=defaultdict(int); self.orders={}; self.cancelled=set()
        self.outgoing={}; self.incoming={}; self.receipts=set(); self.executions={}
        self.withdrawals={}; self.decisions={}; self.counter=0
    def balance(self,owner,asset): return self.available[owner,asset]
    def auth(self,owner,authenticated):
        if owner not in self.principals or authenticated!=owner: raise Rejected('wrong principal')
    def seed(self,owner,asset,amount):
        """Scenario initialization only, never a runtime funding endpoint."""
        positive(amount)
        if owner not in self.principals: raise Rejected('unknown account')
        self.available[owner,asset]+=amount
    def export(self,request,owner,asset,amount,destination,authenticated):
        self.auth(owner,authenticated)
        terms=(owner,asset,amount,destination)
        key=(owner,request)
        if key in self.withdrawals:
            old,outcome=self.withdrawals[key]
            if old!=terms: raise Rejected('request ID conflict')
            if isinstance(outcome,str): raise Rejected(outcome)
            return outcome
        def fail(reason):
            self.withdrawals[key]=(terms,reason); raise Rejected(reason)
        if destination==self.name: fail('remote destination required')
        if amount=='ALL_AVAILABLE': actual=self.balance(owner,asset)
        else:
            try: positive(amount)
            except Rejected: fail('bad withdrawal amount')
            actual=amount
        if actual<=0 or actual>MAX or actual>self.balance(owner,asset): fail('insufficient available withdrawal balance')
        self.counter+=1
        t=Transfer(self.name,str(self.counter),destination,owner,asset,actual)
        self.available[owner,asset]-=actual
        self.outgoing[t.export_id]=t; self.withdrawals[key]=(terms,t)
        return t
    def import_transfer(self,t,authenticated_source):
        if authenticated_source!=t.source or t.destination!=self.name: raise Rejected('wrong transfer authority/destination')
        if t.owner not in self.principals or t.source==self.name: raise Rejected('unknown account/source')
        positive(t.amount)
        key=(t.source,t.export_id)
        if key in self.incoming:
            if self.incoming[key]!=t: raise Rejected('transfer ID conflict')
            return t
        self.available[t.owner,t.asset]+=t.amount
        self.incoming[key]=t
        return t # financial receipt payload in this bounded abstraction
    def received(self,t,authenticated_destination):
        if authenticated_destination!=t.destination or self.outgoing.get(t.export_id)!=t: raise Rejected('wrong receipt')
        self.receipts.add(t.export_id)
    def refund_on_timeout(self,export_id):
        if export_id not in self.outgoing: raise Rejected('unknown export')
        raise Rejected('export irrevocable; receipt loss cannot refund')
    def order(self,o,authenticated,now=0):
        self.auth(o.owner,authenticated)
        key=(o.owner,o.order_id)
        if key in self.decisions:
            old,result=self.decisions[key]
            if old!=o: raise Rejected('order ID conflict')
            if result!='ACCEPTED': raise Rejected(result)
            return self.orders[key]
        def fail(reason):
            self.decisions[key]=(o,reason); raise Rejected(reason)
        if key in self.cancelled: fail('cancelled before admission')
        try:
            positive(o.quantity); positive(o.limit); positive(o.expiry)
        except Rejected: fail('invalid integer terms')
        if o.asset==CASH or o.side not in ('BUY','SELL') or now>=o.expiry or o.expiry-now>30*86400: fail('invalid order terms')
        asset=CASH if o.side=='BUY' else o.asset
        amount=o.quantity*o.limit if o.side=='BUY' else o.quantity
        if amount>MAX: fail('hold overflow')
        if self.balance(o.owner,asset)<amount: fail('insufficient available order balance')
        self.available[o.owner,asset]-=amount
        self.orders[key]=dict(terms=o,remaining=o.quantity,held=amount,state='OPEN')
        self.decisions[key]=(o,'ACCEPTED')
        return self.orders[key]
    def cancel(self,owner,oid,authenticated):
        self.auth(owner,authenticated); key=(owner,oid); self.cancelled.add(key)
        r=self.orders.get(key)
        if r is None: return 'CANCELLED_BEFORE_ADMISSION'
        if r['state'] in ('OPEN','PARTIAL'):
            o=r['terms']; asset=CASH if o.side=='BUY' else o.asset
            self.available[owner,asset]+=r['held']; r['held']=0; r['state']='CANCELLED'
        return r['state']
    def expire(self,now):
        for (owner,oid),r in self.orders.items():
            if r['state'] in ('OPEN','PARTIAL') and now>=r['terms'].expiry:
                self.cancel(owner,oid,owner); r['state']='EXPIRED'
    def fill(self,eid,buyer_key,seller_key,qty,price,now=1):
        """Trusted local matcher invokes; no unauthenticated client fill API.
        Matcher must select price-time priority; this method checks ledger safety.
        """
        terms=(buyer_key,seller_key,qty,price)
        if eid in self.executions:
            if self.executions[eid]!=terms: raise Rejected('execution ID conflict')
            return
        positive(qty); positive(price)
        b=self.orders.get(buyer_key); s=self.orders.get(seller_key)
        if b is None or s is None: raise Rejected('unknown order')
        bo,so=b['terms'],s['terms']
        if bo.owner==so.owner: raise Rejected('self trade')
        if bo.side!='BUY' or so.side!='SELL' or bo.asset!=so.asset: raise Rejected('incompatible orders')
        if any(r['state'] not in ('OPEN','PARTIAL') or now>=r['terms'].expiry or qty>r['remaining'] for r in (b,s)): raise Rejected('unavailable quantity')
        if not so.limit<=price<=bo.limit: raise Rejected('price outside limits')
        # All validation precedes this atomic journal transaction.
        b['held']-=qty*bo.limit; s['held']-=qty
        self.available[bo.owner,CASH]+=qty*(bo.limit-price)
        self.available[so.owner,CASH]+=qty*price
        self.available[bo.owner,bo.asset]+=qty
        for r in (b,s):
            r['remaining']-=qty; r['state']='FILLED' if r['remaining']==0 else 'PARTIAL'
        self.executions[eid]=terms
    def reset(self): return copy.deepcopy(self) # durable state survives

def audit(exchanges):
    """Global evidence audit, not omniscient input to an operating exchange."""
    byname={x.name:x for x in exchanges}; totals=defaultdict(int)
    for x in exchanges:
        for (_,asset),amount in x.available.items():
            assert amount>=0; totals[asset]+=amount
        for r in x.orders.values():
            o=r['terms']; assert r['held']>=0 and r['remaining']>=0
            expected=(r['remaining']*o.limit if o.side=='BUY' else r['remaining']) if r['state'] in ('OPEN','PARTIAL') else 0
            assert r['held']==expected
            totals[CASH if o.side=='BUY' else o.asset]+=r['held']
        for t in x.outgoing.values():
            dest=byname[t.destination]
            imported=dest.incoming.get((x.name,t.export_id))
            assert imported is None or imported==t
            if imported is None: totals[t.asset]+=t.amount
        for (source,eid),t in x.incoming.items(): assert byname[source].outgoing.get(eid)==t
    return dict(totals)
