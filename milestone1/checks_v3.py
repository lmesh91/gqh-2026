"""Run v3 bounded account checks and record provenance without touching v2/M2."""
from pathlib import Path
import csv, hashlib, json, unittest
from prefunded_accounts import *
from test_prefunded_accounts import AccountsTest
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'results'
r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(AccountsTest))
if not r.wasSuccessful(): raise SystemExit(1)
e=Exchange('Earth',['Alice','Bob']); m=Exchange('Mars',['Alice','Bob'])
e.seed('Alice',CASH,1000000); m.seed('Bob','ARES',1000)
rows=[]
def record(event):
    totals=audit([e,m]); assert totals=={CASH:1000000,'ARES':1000}
    cash_transit=sum(t.amount for x in (e,m) for t in x.outgoing.values() if t.asset==CASH and (x.name,t.export_id) not in ({'Earth':e,'Mars':m}[t.destination].incoming))
    rows.append(dict(event=event,cash_in_transit_cents=cash_transit,mars_bob_available_shares=m.balance('Bob','ARES'),mars_bob_held_shares=sum(z['held'] for z in m.orders.values() if z['terms'].owner=='Bob' and z['terms'].side=='SELL'),earth_alice_cash_cents=e.balance('Alice',CASH),mars_alice_available_cents=m.balance('Alice',CASH),mars_alice_order_holds_cents=sum(z['held'] for z in m.orders.values() if z['terms'].owner=='Alice' and z['terms'].side=='BUY'),mars_bob_cash_cents=m.balance('Bob',CASH),mars_alice_shares=m.balance('Alice','ARES'),earth_alice_shares=e.balance('Alice','ARES'),cash_total_cents=totals[CASH],shares_total=totals['ARES']))
record('OPENING')
t=e.export('fund','Alice',CASH,1000000,'Mars','Alice'); record('FUNDING_EXPORTED')
m.import_transfer(t,'Earth'); record('FUNDING_IMPORTED')
e.received(t,'Mars')
m.order(Order('Bob','sell','ARES','SELL',1000,1000,86400),'Bob')
for oid in ['one','two']: m.order(Order('Alice',oid,'ARES','BUY',400,1000,86400),'Alice')
record('TWO_4000_DOLLAR_ORDERS')
m.fill('f1',('Alice','one'),('Bob','sell'),150,1000); record('PARTIAL_FILL_1500_DOLLARS')
m.cancel('Alice','two','Alice'); record('CANCEL_SECOND_ORDER')
w=m.export('withdraw','Alice',CASH,600000,'Earth','Alice'); record('WITHDRAW_6000_DOLLARS')
e.import_transfer(w,'Mars'); record('RETURN_IMPORTED')
assert m.balance('Alice',CASH)==0 and e.balance('Alice',CASH)==600000
assert m.orders['Alice','one']['held']==250000 and m.balance('Bob',CASH)==150000
with (OUT/'v3_account_example.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=rows[0]); writer.writeheader();writer.writerows(rows)
bodies=dict(TRANSFER=112,RECEIVED=56,ORDER=64,CONTROL=64,REPORT=96,CONTRACT_INSTRUCTION=192,PRICE=136)
packing={k:(960-16)//(64+n) for k,n in bodies.items()}
assert packing==dict(TRANSFER=5,RECEIVED=7,ORDER=7,CONTROL=7,REPORT=5,CONTRACT_INSTRUCTION=3,PRICE=4)
result=dict(design_version=3,passed=True,tests=r.testsRun,serialized_race_permutations=6,example_event_rows=len(rows),backbone_allocated=9*66,records_per_payload=packing,scope='Bounded financial ledger and payoff arithmetic; no full matching, close/compaction, durable storage implementation, codec or transport simulation')
(OUT/'v3_safety_checks.json').write_text(json.dumps(result,indent=2)+'\n')
paths=[ROOT/n for n in ['DESIGN.md','IMPLEMENTATION.md','SIMPLIFICATION.md','README.md','prefunded_accounts.py','test_prefunded_accounts.py','checks_v3.py']]
paths+=list(OUT.glob('v3_*'))+[ROOT.parent/'info/brief.pdf',ROOT.parent/'info/data.zip']
manifest={}
for p in sorted(set(paths)):
    if p.name=='v3_provenance.json':continue
    manifest[str(p.relative_to(ROOT.parent))]=hashlib.sha256(p.read_bytes()).hexdigest()
(OUT/'v3_provenance.json').write_text(json.dumps(dict(design_version=3,files=manifest,scope=result['scope']),indent=2)+'\n')
print(json.dumps(result,indent=2))
