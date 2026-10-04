"""Conditional packet traces for direct, on-demand settlement, design v2.
One cold session starts only after the remote order arrives. No random losses.
Original six-account opening book; relocated buyer cases are declared S3 resets.
"""
import math
from collections import defaultdict,Counter
from direct_settlement import Home,Venue,Order,audit
from transport_no_loss import MultiTrace
from model import photon,launchable,save,csvout

def run(buyer_home='Earth',market='Mars',asset='ARES',seller='Bob',label=None):
    label=label or buyer_home.lower()+'_'+market.lower()
    if buyer_home==market: raise ValueError('Local transaction is an atomic local case, not this remote trace')
    t=MultiTrace(); h=Home(buyer_home,{'Alice':15000000}); v=Venue(market,seller,asset,1000)
    o=Order('Alice',buyer_home,market,'A1','R1',asset,1000,10000)
    snapshots=[]
    def note(actor,event,state):
        t.note_event(actor,event,state)
        z=audit(h,v)
        # Other accounts' original cash remains 350000 NeoDollars; venue cash is proceeds.
        assert z['cash_cents']+35000000==50000000
        snapshots.append(dict(hour=t.now/3600,event=event,alice_available_cents=h.cash['Alice'],alice_reserved_cents=sum(r['locked'] for r in h.reservations.values()),other_opening_cash_cents=35000000,seller_new_proceeds_cents=v.cash,cash_in_transit_cents=z['cash_in_transit_cents'],seller_trade_shares_remaining=v.sell_available+sum(q.order.quantity for q in v.pending.values()),alice_trade_shares=h.shares['Alice',asset],shares_in_transit=z['shares_in_transit'],other_original_shares=4000,total_cash_cents=50000000,total_shares=5000))
    def received(q,d):
        h.receive(q,d,market)
        note(buyer_home,'SPENDABLE_BUYER','Matching cash debit and share export recorded; buyer receives local custody')
        t.send(buyer_home,market,'RECEIVED',lambda:note(market,'COMPLETE_KNOWN','Authoritative home receipt confirms buyer spendability; close recovery work'))
    def paid(q,p):
        d=v.resolve(q,p,buyer_home)
        assert d is not None
        note(market,'SPENDABLE_SELLER','Atomic payment import, seller credit and share debit/export; payment obligation discharged')
        t.send(market,buyer_home,'DELIVERY',lambda:received(q,d))
    def request(q):
        p=h.decide(q,market,t.now)
        note(buyer_home,'PAYMENT_RECORDED','Single-use reservation consumed; payment exported; buyer holds backed delivery claim')
        t.send(buyer_home,market,'PAYMENT',lambda:paid(q,p))
    def order_arrived():
        q=v.propose(o,10000,t.now,authenticated_client='Alice')
        note(market,'PROVISIONAL_MATCH','Seller shares promised for this request; backing not yet verified')
        t.connect(market,buyer_home)
        t.send(market,buyer_home,'PAY_REQUEST',lambda:request(q))
    def start():
        h.reserve(o)
        note(buyer_home,'RESERVED','Local buyer reservation; seller standing sell order already reserves 1000 shares')
    t.at(1,start)
    arrival,d,c=photon(buyer_home,market,2)
    assert c>=.1
    t.at(float(arrival)+1,order_arrived)
    t.run()
    assert h.cash['Alice']==5000000 and h.shares['Alice',asset]==1000 and v.cash==10000000
    last=defaultdict(lambda:-math.inf)
    for p in sorted(t.rows,key=lambda x:x['emission_s']):
        k=p['sender'],p['receiver']
        assert p['emission_s']-last[k]>=1-1e-8 and launchable(*k,p['emission_s'])
        last[k]=p['emission_s']
    times={r['event']:r['hour'] for r in t.events}
    summary=dict(design_version=2,scenario=label,buyer_home=buyer_home,market=market,reset='Original opening book; relocate Alice only for S3 non-Earth buyer cases',conditions='No random loss; cold on-demand session; no closure encountered; no batching',backbone_originations=sum(t.origins.values()),originations_by_institution=dict(t.origins),backbone_launches=len(t.rows),direct_launches=1,total_launches=len(t.rows)+1,direct_order_success_probability=math.exp(-.08*float(d)),backed_claim_hour=times['PAYMENT_RECORDED'],discharge_hour=times['SPENDABLE_SELLER'],seller_spendable_hour=times['SPENDABLE_SELLER'],buyer_spendable_hour=times['SPENDABLE_BUYER'],complete_hour=max(times['SPENDABLE_SELLER'],times['SPENDABLE_BUYER']),complete_known_hour=times['COMPLETE_KNOWN'],cash_asset_hours=100000*(times['SPENDABLE_SELLER']-1/3600),share_asset_hours=1000*(times['SPENDABLE_BUYER']-1/3600),peak_cash_encumbered=100000,peak_trade_shares_encumbered=1000,capital_utilization=.2,capital_efficiency=1,types=dict(Counter(x['kind'] for x in t.rows)))
    assert summary['backbone_originations']==5 and summary['total_launches']==45
    prefix='v2_'+label
    save(prefix+'_summary.json',summary)
    csvout(prefix+'_events.csv',t.events); csvout(prefix+'_balances.csv',snapshots)
    csvout(prefix+'_messages.csv',t.commands)
    csvout(prefix+'_packets.csv',sorted(t.rows,key=lambda x:(x['emission_s'],x['packet_id'])))
    return summary

if __name__=='__main__':
    specs=[('Earth','Mars','ARES','Bob'),('Earth','Ceres','BELT','Cara'),('Jupiter','Mars','ARES','Bob'),('Neptune','Mars','ARES','Bob')]
    summaries=[run(*x) for x in specs]
    for s in summaries: print(s['scenario'],s['complete_hour'],s['total_launches'],s['direct_order_success_probability'])
    save('v2_comparison.json',dict(cases=summaries,old_protocol_examples={'earth_mars':{'total_launches':69,'originations':8,'complete_hour':4.524639823906794},'earth_ceres_via_mars':{'total_launches':149,'originations':17,'complete_hour':4.99350402209501}},note='Same opening funding and local-spendability requirement; previous examples used early session setup, v2 starts its session only after direct order receipt. Both no-loss and unbatched.'))
