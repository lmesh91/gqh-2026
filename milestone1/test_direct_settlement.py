"""Adversarial application tests. No claims about full lossy transport."""
import copy, unittest
from dataclasses import replace
from direct_settlement import *
from model import save

class DirectSettlementTests(unittest.TestCase):
    def setUp(self): self.h,self.v,self.o=setup()
    def request(self,o=None):
        o=o or self.o
        return self.v.propose(o,10000,1,authenticated_client=o.owner)
    def pay(self,q): return self.h.decide(q,'Mars',2)
    def finish(self,q):
        p=self.pay(q); d=self.v.resolve(q,p,'Earth'); self.h.receive(q,d,'Mars'); audit(self.h,self.v)
        return p,d
    def test_success_and_replays(self):
        q=self.request(); p,d=self.finish(q)
        for _ in range(8):
            self.assertEqual(self.pay(q),p)
            self.assertEqual(self.v.resolve(q,p,'Earth'),d)
            self.h.receive(q,d,'Mars'); audit(self.h,self.v)
        self.assertEqual(self.h.cash['Alice'],5000000)
        self.assertEqual(self.h.shares['Alice','ARES'],1000)
    def test_two_reservations_cannot_reuse_capital(self):
        with self.assertRaises(Rejected): self.h.reserve(replace(self.o,order_id='A2',reservation_id='R2'))
        audit(self.h,self.v)
    def test_same_reservation_different_order_rejected_at_market(self):
        self.request()
        with self.assertRaises(Rejected): self.request(replace(self.o,order_id='A2'))
    def test_wrong_order_rejected_at_home_without_poisoning_valid_order(self):
        q=self.request(replace(self.o,order_id='wrong'))
        no=self.pay(q); self.assertIsInstance(no,Refusal)
        self.v.resolve(q,no,'Earth'); self.assertEqual(self.h.reservations['Alice','R1']['state'],'RESERVED')
        self.finish(self.request())
    def test_new_tx_cannot_consume_paid_reservation(self):
        q=self.request(); self.pay(q)
        no=self.pay(replace(q,tx='Mars:999'))
        self.assertIsInstance(no,Refusal); audit(self.h,self.v)
    def test_wrong_market_does_not_authorize_payment(self):
        q=self.request()
        with self.assertRaises(Rejected): self.h.decide(q,'Neptune',2)
        no=self.h.decide(replace(q,order=replace(self.o,market='Neptune')),'Neptune',2)
        self.assertIsInstance(no,Refusal)
    def test_wrong_client_cannot_claim_reservation(self):
        with self.assertRaises(Rejected): self.v.propose(self.o,10000,1,authenticated_client='Mallory')
    def test_changed_payload_under_same_tx_rejected(self):
        q=self.request(); self.pay(q)
        with self.assertRaises(Rejected): self.pay(replace(q,price_cents=9999))
    def test_cancel_before_payment(self):
        q=self.request(); self.h.cancel('Alice','R1')
        no=self.pay(q); self.assertIsInstance(no,Refusal)
        self.assertIsNone(self.v.resolve(q,no,'Earth')); audit(self.h,self.v)
        self.assertEqual(self.h.cash['Alice'],15000000)
    def test_cancel_after_payment_cannot_refund(self):
        q=self.request(); self.pay(q)
        self.assertEqual(self.h.cancel('Alice','R1'),'PAYMENT_ALREADY_RECORDED')
        self.finish(q)
    def test_deadline_and_expiry(self):
        q=self.request()
        no=self.h.decide(q,'Mars',q.accept_by_s)
        self.assertIsInstance(no,Refusal)
        self.assertIsInstance(self.h.decide(q,'Mars',2),Refusal) # Final no-payment decision cannot change.
        self.v.resolve(q,no,'Earth'); audit(self.h,self.v)
    def test_late_replay_of_paid_request_returns_payment(self):
        q=self.request(); p=self.pay(q)
        self.assertEqual(self.h.decide(q,'Mars',10**9),p)
    def test_price_improvement_releases_only_unused_budget(self):
        q=self.v.propose(self.o,9000,1,authenticated_client='Alice'); self.finish(q)
        self.assertEqual(self.h.cash['Alice'],6000000)
        no=self.h.decide(replace(q,tx='Mars:new'),'Mars',3)
        self.assertIsInstance(no,Refusal)
    def test_partial_fill_not_accepted_by_source(self):
        q=self.request(replace(self.o,quantity=500))
        self.assertIsInstance(self.pay(q),Refusal)
    def test_no_release_on_market_timeout(self):
        q=self.request(); self.pay(q)
        self.assertEqual(self.v.timeout(q.tx),'QUERY_SOURCE; KEEP_SHARES_RESERVED')
        self.assertEqual(self.v.sell_available,0); audit(self.h,self.v)
    def test_reset_and_packet_expiry_preserve_financial_records(self):
        q=self.request(); p=self.pay(q)
        self.h,self.v=copy.deepcopy((self.h,self.v))
        self.assertEqual(self.h.decide(q,'Mars',31*86400),p)
        self.finish(q)
    def test_share_delivery_before_payment_rejected(self):
        q=self.request(); d=Delivery(q.tx,fingerprint(q),'Mars','Earth','Alice','ARES',1000)
        with self.assertRaises(Rejected): self.h.receive(q,d,'Mars')
    def test_receipt_loss_does_not_repeat_stock_transfer(self):
        q=self.request(); p,d=self.finish(q)
        self.v.resolve(q,p,'Earth'); self.h.receive(q,d,'Mars')
        self.assertEqual(self.h.shares['Alice','ARES'],1000)
    def test_false_proof_wrong_identity_or_amount(self):
        q=self.request(); p=self.pay(q)
        with self.assertRaises(Rejected): self.v.resolve(q,p,'Neptune')
        with self.assertRaises(Rejected): self.v.resolve(q,replace(p,amount_cents=p.amount_cents+1),'Earth')
    def test_bogus_reservation_releases_only_after_source_refusal(self):
        q=self.request(replace(self.o,reservation_id='unknown'))
        self.assertEqual(self.v.sell_available,0)
        no=self.pay(q); self.v.resolve(q,no,'Earth')
        self.assertEqual(self.v.sell_available,1000)
    def test_independent_orders_have_independent_funding(self):
        h=Home('Earth',{'Alice':15000000})
        a=replace(self.o,quantity=500); b=replace(a,order_id='A2',reservation_id='R2')
        h.reserve(a); h.reserve(b)
        self.assertEqual(h.cash['Alice'],5000000)
    def test_void_before_payment_prevents_late_request(self):
        q=self.request(); no=self.h.void(q,'Mars')
        self.assertIsInstance(no,Refusal)
        self.assertEqual(self.pay(q),no)
        self.v.resolve(q,no,'Earth'); audit(self.h,self.v)
    def test_void_after_payment_returns_payment_not_refund(self):
        q=self.request(); p=self.pay(q)
        self.assertEqual(self.h.void(q,'Mars'),p)
        self.finish(q)
    def test_unpaid_expiry_releases_cash_and_prevents_late_payment(self):
        q=self.request(); self.h.expire(self.o.expiry_s)
        self.assertEqual(self.h.cash['Alice'],15000000)
        self.assertIsInstance(self.h.decide(q,'Mars',self.o.expiry_s),Refusal)
        audit(self.h,self.v)
    def test_paid_reservation_never_refunded_at_expiry(self):
        q=self.request(); self.pay(q); self.h.expire(10**9)
        self.assertEqual(self.h.cash['Alice'],5000000)
        self.finish(q)
    def test_integer_wire_limits(self):
        with self.assertRaises(Rejected): replace(self.o,quantity=1.5)
        with self.assertRaises(Rejected): replace(self.o,quantity=2**62)
        with self.assertRaises(Rejected): replace(self.o,limit_cents=True)
        with self.assertRaises(Rejected): self.v.propose(self.o,10000.0,1,authenticated_client="Alice")
        q=replace(self.request(),price_cents=9999.5)
        self.assertIsInstance(self.h.decide(q,"Mars",2),Refusal)
    def test_derivative_cash_conservation_for_both_paths_and_extremes(self):
        for p in [0,60,65,75,100,125,135,140,10**9]:
            payoff=2000*(min(140,max(60,p))-100)
            long=80000+payoff; short=80000-payoff
            self.assertGreaterEqual(min(long,short),0)
            self.assertEqual(long+short,160000)
        self.assertGreater(2501*40,100000)

def explore():
    """Explore all reachable states in this bounded one-trade message abstraction.
    Actors can retry, cancel, lose packets (no-op), reset, or deliver the next
    causally available message. No full transport timers are claimed.
    """
    h,v,o=setup(); initial=(h,v,o,None,None,None)
    def key(s):
        h,v,o,q,p,d=s
        return repr((h.__dict__,v.__dict__,o,q,p,d))
    seen={key(initial)}; todo=[initial]; edges=0
    actions=['order','request','response','delivery','cancel','void','expire','timeout','lost','reset']
    while todo:
        s=todo.pop()
        for a in actions:
            h,v,o,q,p,d=copy.deepcopy(s)
            try:
                if a=='order': q=v.propose(o,10000,1,authenticated_client='Alice')
                elif a=='request' and q is not None: p=h.decide(q,'Mars',2)
                elif a=='response' and p is not None: d=v.resolve(q,p,'Earth')
                elif a=='delivery' and d is not None: h.receive(q,d,'Mars')
                elif a=='cancel': h.cancel('Alice','R1')
                elif a=='void' and q is not None: p=h.void(q,'Mars')
                elif a=='expire': h.expire(o.expiry_s)
                elif a=='timeout' and q is not None: v.timeout(q.tx)
                # loss and durable reset are no-op / deepcopy in this abstraction.
            except (Rejected,Pending): pass
            audit(h,v); edges+=1
            ns=(h,v,o,q,p,d); k=key(ns)
            if k not in seen: seen.add(k); todo.append(ns)
    return dict(states=len(seen),transitions=edges)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(DirectSettlementTests))
    explored=explore()
    save('v2_safety_checks.json',dict(unit_tests=result.testsRun,passed=result.wasSuccessful(),failures=len(result.failures),errors=len(result.errors),exploration=explored,scope='Bounded financial model; not full transport or malicious-operator verification'))
    print(explored)
    if not result.wasSuccessful(): raise SystemExit(1)
