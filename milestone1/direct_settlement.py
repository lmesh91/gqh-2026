"""Version 2 authoritative application model: single-use order-bound reservation,
PAY_REQUEST -> PAYMENT -> DELIVERY -> RECEIVED. Honest operators, authenticated
messages, atomic durable transitions. Money is integer cents throughout.
This is a financial model, not a cryptographic or lossy network implementation.
"""
from dataclasses import dataclass, asdict, replace
from collections import defaultdict
import hashlib, json, copy

class Rejected(ValueError): pass
class Pending(Exception): pass

def fingerprint(obj):
    return hashlib.sha256(json.dumps(asdict(obj),sort_keys=True).encode()).hexdigest()

@dataclass(frozen=True)
class Order:
    owner: str
    home: str
    market: str
    order_id: str
    reservation_id: str
    asset: str
    quantity: int
    limit_cents: int
    expiry_s: int=259200
    version: int=2
    def __post_init__(self):
        vals=(self.quantity,self.limit_cents,self.expiry_s)
        if any(type(x) is not int or x<0 or x>2**63-1 for x in vals) or self.quantity*self.limit_cents>2**63-1:
            raise Rejected('non-integer or overflowing wire amount')

@dataclass(frozen=True)
class Request:
    tx: str
    order: Order
    seller: str
    price_cents: int
    accept_by_s: float

@dataclass(frozen=True)
class Payment:
    tx: str
    request_hash: str
    owner: str
    source: str
    destination: str
    beneficiary: str
    amount_cents: int

@dataclass(frozen=True)
class Refusal:
    tx: str
    request_hash: str
    source: str
    reason: str

@dataclass(frozen=True)
class Delivery:
    tx: str
    request_hash: str
    source: str
    destination: str
    beneficiary: str
    asset: str
    quantity: int

class Home:
    def __init__(self,name,balances):
        self.name=name; self.cash=dict(balances); self.reservations={}
        self.order_ids={}; self.decisions={}; self.received={}; self.shares=defaultdict(int)
    def reserve(self,o):
        if o.home!=self.name or o.version!=2 or o.quantity<=0 or o.limit_cents<=0: raise Rejected('invalid terms')
        key=(o.owner,o.reservation_id)
        if key in self.reservations:
            if self.reservations[key]['order']!=o: raise Rejected('reservation ID conflict')
            return
        if (o.owner,o.market,o.order_id) in self.order_ids: raise Rejected('order already has a reservation')
        amount=o.quantity*o.limit_cents
        if self.cash.get(o.owner,0)<amount: raise Rejected('insufficient available cash')
        self.cash[o.owner]-=amount
        self.reservations[key]=dict(order=o,locked=amount,state='RESERVED',paid_tx=None)
        self.order_ids[o.owner,o.market,o.order_id]=o.reservation_id
    def cancel(self,owner,rid):
        r=self.reservations[owner,rid]
        if r['state']=='PAID': return 'PAYMENT_ALREADY_RECORDED'
        if r['state']=='RESERVED':
            self.cash[owner]+=r['locked']; r['locked']=0; r['state']='CANCELLED'
        return r['state']
    def expire(self,now):
        for (owner,rid),r in self.reservations.items():
            if r['state']=='RESERVED' and now>=r['order'].expiry_s:
                self.cancel(owner,rid); r['state']='EXPIRED'
    def void(self,q,authenticated_market):
        if authenticated_market!=q.order.market: raise Rejected('wrong authenticated requester')
        key=(authenticated_market,q.tx); h=fingerprint(q)
        if key in self.decisions:
            oldh,result=self.decisions[key]
            if oldh!=h: raise Rejected('transaction ID conflict')
            return result
        result=Refusal(q.tx,h,self.name,'REQUEST_VOIDED')
        self.decisions[key]=(h,result)
        return result
    def decide(self,q,authenticated_market,now):
        if authenticated_market!=q.order.market: raise Rejected('wrong authenticated requester')
        key=(authenticated_market,q.tx); h=fingerprint(q)
        if key in self.decisions:
            oldh,result=self.decisions[key]
            if oldh!=h: raise Rejected('transaction ID conflict')
            return result
        o=q.order; r=self.reservations.get((o.owner,o.reservation_id))
        reason=None
        if o.home!=self.name or r is None: reason='UNKNOWN_RESERVATION'
        elif r['order']!=o: reason='ORDER_OR_TERMS_MISMATCH'
        elif r['state']!='RESERVED': reason='RESERVATION_'+r['state']
        elif now>=o.expiry_s:
            self.cancel(o.owner,o.reservation_id); reason='EXPIRED'
        elif now>=q.accept_by_s: reason='REQUEST_DEADLINE'
        elif type(q.price_cents) is not int or q.price_cents<=0 or q.price_cents>o.limit_cents: reason='PRICE_OUTSIDE_LIMIT'
        if reason:
            result=Refusal(q.tx,h,self.name,reason)
        else:
            amount=o.quantity*q.price_cents
            result=Payment(q.tx,h,o.owner,self.name,o.market,q.seller,amount)
            # One atomic source debit/export + dedup result; no second use of price improvement.
            self.cash[o.owner]+=r['locked']-amount
            r['locked']=0; r['state']='PAID'; r['paid_tx']=q.tx
        self.decisions[key]=(h,result)
        return result
    def receive(self,q,d,authenticated_market):
        expected=Delivery(q.tx,fingerprint(q),q.order.market,self.name,q.order.owner,q.order.asset,q.order.quantity)
        if authenticated_market!=q.order.market or d!=expected: raise Rejected('wrong delivery')
        decision=self.decisions.get((authenticated_market,q.tx))
        if decision is None or not isinstance(decision[1],Payment) or decision[0]!=d.request_hash: raise Rejected('no matching local payment debit')
        key=(authenticated_market,d.tx)
        if key not in self.received:
            self.shares[d.beneficiary,d.asset]+=d.quantity; self.received[key]=d
        elif self.received[key]!=d: raise Rejected('delivery conflict')
        return key

class Venue:
    def __init__(self,name,seller,asset,quantity):
        self.name=name; self.seller=seller; self.asset=asset; self.sell_available=quantity
        self.cash=0; self.pending={}; self.by_order={}; self.active_reservations={}; self.records={}; self.counter=0
    def propose(self,o,price_cents,now,authenticated_client=None):
        if authenticated_client!=o.owner: raise Rejected('wrong client identity')
        if type(price_cents) is not int: raise Rejected('price must be integer cents')
        if o.market!=self.name or o.asset!=self.asset or o.version!=2 or o.quantity<=0 or not 0<price_cents<=o.limit_cents or now>=o.expiry_s: raise Rejected('invalid order')
        oid=(o.owner,o.order_id)
        if oid in self.by_order:
            q=self.by_order[oid]
            if q.order!=o: raise Rejected('order ID conflict')
            return q
        rkey=(o.home,o.owner,o.reservation_id)
        if rkey in self.active_reservations: raise Rejected('reservation already attached to pending trade')
        if any(q.order.owner==o.owner for q in self.pending.values()): raise Rejected('one provisional match per principal')
        if len(self.pending)>=8: raise Rejected('provisional-match cap')
        if self.sell_available<o.quantity: raise Rejected('all-or-none inventory unavailable')
        self.counter+=1
        q=Request(f'{self.name}:{self.counter}',o,self.seller,price_cents,min(o.expiry_s,now+86400))
        self.sell_available-=o.quantity; self.pending[q.tx]=q
        self.active_reservations[rkey]=q.tx; self.by_order[oid]=q
        return q
    def resolve(self,q,result,authenticated_home):
        if authenticated_home!=q.order.home: raise Rejected('wrong source authority')
        if result.tx!=q.tx or result.request_hash!=fingerprint(q) or result.source!=q.order.home: raise Rejected('response does not match request')
        if q.tx in self.records:
            prior,delivery=self.records[q.tx]
            if prior!=result: raise Rejected('contradictory terminal response')
            return delivery
        if self.pending.get(q.tx)!=q: raise Rejected('no matching committed delivery promise')
        if isinstance(result,Payment):
            expected=Payment(q.tx,fingerprint(q),q.order.owner,q.order.home,self.name,q.seller,q.order.quantity*q.price_cents)
            if result!=expected: raise Rejected('payment terms differ')
            d=Delivery(q.tx,fingerprint(q),self.name,q.order.home,q.order.owner,q.order.asset,q.order.quantity)
            # Atomic import cash + seller credit + seller share debit/export + durable outbox record.
            self.cash+=result.amount_cents
        elif isinstance(result,Refusal):
            self.sell_available+=q.order.quantity; d=None
        else: raise Rejected('unknown source result')
        del self.pending[q.tx]
        del self.active_reservations[q.order.home,q.order.owner,q.order.reservation_id]
        self.records[q.tx]=(result,d)
        return d
    def timeout(self,tx):
        if tx in self.pending: return 'QUERY_SOURCE; KEEP_SHARES_RESERVED'
        return 'TERMINAL'

def setup(market='Mars',asset='ARES'):
    o=Order('Alice','Earth',market,'A1','R1',asset,1000,10000)
    h=Home('Earth',{'Alice':15000000})
    v=Venue(market,'Seller',asset,1000)
    h.reserve(o)
    return h,v,o

def audit(h,v,opening_cash=15000000,opening_shares=1000):
    cash=sum(h.cash.values())+sum(r['locked'] for r in h.reservations.values())+v.cash
    transit_cash=0; transit_shares=0
    for (_,tx),(_,p) in h.decisions.items():
        if isinstance(p,Payment) and tx not in v.records: transit_cash+=p.amount_cents
    for tx,(_,d) in v.records.items():
        if d is not None and (v.name,tx) not in h.received: transit_shares+=d.quantity
    shares=v.sell_available+sum(q.order.quantity for q in v.pending.values())+sum(h.shares.values())+transit_shares
    assert cash+transit_cash==opening_cash
    assert shares==opening_shares
    assert all(x>=0 for x in h.cash.values()) and v.sell_available>=0
    assert all(r['locked']>=0 for r in h.reservations.values())
    return dict(cash_cents=cash+transit_cash,shares=shares,cash_in_transit_cents=transit_cash,shares_in_transit=transit_shares)
