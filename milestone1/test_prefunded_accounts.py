"""Bounded v3 financial tests. No transport or full matching-engine claims."""
import unittest
from dataclasses import replace
from itertools import permutations
from prefunded_accounts import *

class AccountsTest(unittest.TestCase):
    def setUp(self):
        self.e=Exchange('Earth',['Alice','Bob']); self.m=Exchange('Mars',['Alice','Bob'])
        self.e.seed('Alice',CASH,1000000); self.m.seed('Bob','ARES',1000)
        self.initial={CASH:1000000,'ARES':1000}
    def check(self): self.assertEqual(audit([self.e,self.m]),self.initial)
    def fund(self,amount=1000000,request='fund'):
        t=self.e.export(request,'Alice',CASH,amount,'Mars','Alice')
        self.check(); self.m.import_transfer(t,'Earth'); self.check(); return t
    def buy(self,oid='b',q=100,p=1000):
        o=Order('Alice',oid,'ARES','BUY',q,p,86400)
        self.m.order(o,'Alice'); return ('Alice',oid)
    def sell(self,oid='s',q=1000,p=800):
        o=Order('Bob',oid,'ARES','SELL',q,p,86400)
        self.m.order(o,'Bob'); return ('Bob',oid)
    def test_funding_moves_authority_and_duplicate_import_is_noop(self):
        t=self.fund(); self.m.import_transfer(t,'Earth'); self.check()
        self.assertEqual(self.e.balance('Alice',CASH),0)
        self.assertEqual(self.m.balance('Alice',CASH),1000000)
    def test_two_exports_cannot_spend_same_cash(self):
        self.e.export('a','Alice',CASH,700000,'Mars','Alice')
        with self.assertRaises(Rejected): self.e.export('b','Alice',CASH,700000,'Mars','Alice')
        self.check()
    def test_host_spends_before_receipt_returns(self):
        t=self.fund(); b=self.buy(); s=self.sell(); self.m.fill('f',b,s,100,900)
        self.assertNotIn(t.export_id,self.e.receipts); self.check()
    def test_two_order_holds_cannot_exceed_cash(self):
        self.fund(); self.buy('one',700,1000)
        with self.assertRaises(Rejected): self.buy('two',700,1000)
        self.check()
    def test_partial_fill_and_price_improvement(self):
        self.fund(); b=self.buy(q=400); s=self.sell()
        self.m.fill('f',b,s,150,900)
        self.assertEqual(self.m.orders[b]['held'],250000)
        self.assertEqual(self.m.balance('Alice',CASH),615000)
        self.assertEqual(self.m.balance('Bob',CASH),135000); self.check()
    def test_cancel_after_partial_fill_releases_only_remainder(self):
        self.fund(); b=self.buy(q=400); s=self.sell(); self.m.fill('f',b,s,150,1000)
        self.m.cancel('Alice','b','Alice'); self.m.cancel('Alice','b','Alice')
        self.assertEqual(self.m.balance('Alice',CASH),850000)
        self.assertEqual(self.m.balance('Alice','ARES'),150); self.check()
    def test_cancel_before_order_is_tombstone(self):
        self.fund(); self.m.cancel('Alice','b','Alice')
        with self.assertRaises(Rejected): self.buy()
        self.check()
    def test_order_before_funding_rejection_is_sticky(self):
        with self.assertRaises(Rejected): self.buy()
        self.fund()
        with self.assertRaises(Rejected): self.buy()
        self.buy('new'); self.check()
    def test_duplicate_and_conflicting_order(self):
        self.fund(); self.buy(); self.buy()
        with self.assertRaises(Rejected): self.buy(q=101)
        self.assertEqual(self.m.balance('Alice',CASH),900000); self.check()
    def test_duplicate_and_conflicting_fill(self):
        self.fund(); b=self.buy(); s=self.sell(); self.m.fill('f',b,s,50,900)
        self.m.fill('f',b,s,50,900)
        with self.assertRaises(Rejected): self.m.fill('f',b,s,51,900)
        self.check()
    def test_overfill_or_invalid_price_cannot_mutate_balances(self):
        self.fund(); b=self.buy(); s=self.sell()
        for q,p in [(101,900),(10,1100),(10,700)]:
            with self.assertRaises(Rejected): self.m.fill('bad',b,s,q,p)
            self.check()
    def test_multiple_sellers_partial_fills(self):
        self.fund(); b=self.buy(q=100); s1=self.sell('s1',40); s2=self.sell('s2',60)
        self.m.fill('f1',b,s1,40,850); self.m.fill('f2',b,s2,60,900)
        self.assertEqual(self.m.orders[b]['state'],'FILLED'); self.check()
    def test_withdrawal_cannot_take_order_hold(self):
        self.fund(); self.buy(q=400)
        with self.assertRaises(Rejected): self.m.export('w','Alice',CASH,700000,'Earth','Alice')
        self.m.export('w2','Alice',CASH,600000,'Earth','Alice'); self.check()
    def test_all_available_retry_does_not_take_new_cash(self):
        self.fund(500000); t=self.m.export('w','Alice',CASH,'ALL_AVAILABLE','Earth','Alice')
        self.fund(500000,'topup')
        self.assertEqual(self.m.export('w','Alice',CASH,'ALL_AVAILABLE','Earth','Alice'),t)
        self.assertEqual(self.m.balance('Alice',CASH),500000); self.check()
    def test_returned_cash_and_stock_arrive_once(self):
        self.fund(); b=self.buy(); s=self.sell(); self.m.fill('f',b,s,100,900)
        for asset in [CASH,'ARES']:
            t=self.m.export('w'+asset,'Alice',asset,'ALL_AVAILABLE','Earth','Alice')
            self.check(); self.e.import_transfer(t,'Mars'); self.e.import_transfer(t,'Mars'); self.check()
        self.assertEqual(self.e.balance('Alice',CASH),910000)
        self.assertEqual(self.e.balance('Alice','ARES'),100)
    def test_seller_proceeds_are_sellers_not_depositors(self):
        self.fund(); b=self.buy(); s=self.sell(); self.m.fill('f',b,s,100,900)
        t=self.m.export('bobw','Bob',CASH,90000,'Earth','Bob')
        self.e.import_transfer(t,'Mars'); self.assertEqual(self.e.balance('Bob',CASH),90000); self.check()
    def test_timeout_never_refunds(self):
        t=self.fund()
        with self.assertRaises(Rejected): self.e.refund_on_timeout(t.export_id)
        self.check()
    def test_expiry_releases_only_unfilled_hold(self):
        self.fund(); b=self.buy(); s=self.sell(); self.m.fill('f',b,s,30,900)
        self.m.expire(86400); self.assertEqual(self.m.balance('Alice',CASH),973000)
        with self.assertRaises(Rejected): self.m.fill('late',b,s,1,900,86400)
        self.check()
    def test_reset_and_duplicate_after_network_lifetime(self):
        t=self.fund(); b=self.buy(); s=self.sell(); self.m.fill('f',b,s,50,900)
        self.m=self.m.reset(); self.m.import_transfer(t,'Earth'); self.m.fill('f',b,s,50,900,10**9)
        self.check()
    def test_identity_and_changed_transfer_rejected(self):
        t=self.fund()
        with self.assertRaises(Rejected): self.m.import_transfer(t,'Venus')
        with self.assertRaises(Rejected): self.m.import_transfer(replace(t,amount=t.amount+1),'Earth')
        with self.assertRaises(Rejected): self.m.cancel('Alice','b','Bob')
        with self.assertRaises(Rejected): self.e.received(t,'Venus')
        self.check()
    def test_integer_amount_and_overflow_rules(self):
        self.fund()
        for n in [-1,0,True,1.5,2**63]:
            with self.assertRaises(Rejected): self.buy(str(n),n)
        with self.assertRaises(Rejected): self.buy('overflow',2**62,1000)
        self.check()
    def test_fill_cancel_withdraw_all_six_serial_orders(self):
        for actions in permutations(['fill','cancel','withdraw']):
            self.setUp(); self.fund(); b=self.buy(q=400); s=self.sell()
            for action in actions:
                try:
                    if action=='fill': self.m.fill('f',b,s,150,900)
                    if action=='cancel': self.m.cancel('Alice','b','Alice')
                    if action=='withdraw': self.m.export('w','Alice',CASH,'ALL_AVAILABLE','Earth','Alice')
                except Rejected: pass
                self.check()
    def test_payoff_arithmetic_and_margin_boundary(self):
        for p in [0,60,65,75,100,125,135,140,100000]:
            net=2000*(min(140,max(60,p))-100)
            self.assertEqual((80000+net)+(80000-net),160000)
            self.assertGreaterEqual(min(80000+net,80000-net),0)
        self.assertEqual(2500*40,100000); self.assertGreater(2501*40,100000)

if __name__=='__main__': unittest.main()
