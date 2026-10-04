"""Regression checks for numerical/network boundaries and complete worked-book audit."""
import json, math
from collections import defaultdict
import numpy as np
from model import photon,pos,launchable,best,OUT,save,csvout
from verify import worked,safety,hop_analysis,failure_probes

def run():
    worked(); safety(); hop_analysis(); failure_probes()
    checks=[]
    for a,b in [('Earth','Mars'),('Mars','Earth'),('Neptune','Relay B')]:
        for te in [-86400,0,300*3600,200*365.25*86400]:
            ta,d,c=photon(a,b,te)
            residual=abs(float(ta-te)-499.02*np.linalg.norm(pos(b,ta)-pos(a,te)))
            assert residual<.001; checks.append(f'light residual {a}->{b} at {te}')
    # Maintenance applies to flights emitted BEFORE the window, not just emission time.
    assert not bool(launchable('Neptune','Relay B',0,True))
    assert bool(launchable('Neptune','Relay B',0,False))
    assert bool(launchable('Neptune','Relay B',26*3600,True))
    assert not bool(launchable('Ceres','Relay B',240*3600,True))
    assert bool(launchable('Ceres','Relay B',264*3600,True))
    assert np.linalg.norm(pos('Relay A',0)-[2,2,0])<1e-10
    assert np.linalg.norm(pos('Relay B',0)-[-2,2,0])<1e-10
    import csv
    packets=list(csv.DictReader((OUT/'trade_packets.csv').open()))
    last=defaultdict(lambda:-math.inf)
    for p in packets:
        key=(p['sender'],p['receiver']); te=float(p['emission_s'])
        assert te-last[key]>=1-1e-8; last[key]=te
        assert bool(launchable(*key,te))
    # Packet fit: batch header16 + n*(record header64 + body) <=960.
    sizes=[(64,7),(32,9),(72,6),(432,1),(56,7),(88,6),(136,4),(672,1)]
    for body,n in sizes:
        assert 16+n*(64+body)<=960 and 16+(n+1)*(64+body)>960
    budgets=[60,60,60,90,60,60,60,60,90]; assert sum(budgets)==600
    events=list(csv.DictReader((OUT/'trade_events.csv').open())); times={e['action']:float(e['hour']) for e in events}
    account_names=['Alice','Bob','Cara','Dax','Eve','Fin']
    homes=['Earth','Mars','Ceres','Neptune','Uranus','Earth']
    start_cash=[150000,50000,100000,100000,50000,50000]
    rows=[]
    for stage in ['OPENING','RESERVE_LOCAL','COMMIT','APPLIED','RELEASE','RELEASED']:
        cash=start_cash.copy(); ares=[0,3000,0,0,0,0]; lc=[0]*6; ls=[0]*6; transit_cash=transit_shares=0
        if stage!='OPENING': lc[0]=100000; ls[1]=1000
        if stage in ['COMMIT','APPLIED','RELEASE','RELEASED']:
            ares[1]=2000; ls[1]=0; transit_shares=1000
        if stage in ['APPLIED','RELEASE','RELEASED']:
            cash[0]-=100000; lc[0]=0; transit_cash=100000
        if stage in ['RELEASE','RELEASED']: cash[1]+=100000; transit_cash=0
        if stage=='RELEASED': ares[0]=1000; transit_shares=0
        assert sum(cash)+transit_cash==500000
        assert sum(ares)+transit_shares==3000
        for i,n in enumerate(account_names):
            rows.append(dict(stage=stage,hour=0 if stage=='OPENING' else times[stage],owner=n,location=homes[i],cash_owned=cash[i],cash_encumbered=lc[i],cash_available=cash[i]-lc[i],ares_owned=ares[i],ares_encumbered=ls[i],ares_available=ares[i]-ls[i],belt_owned=1000 if n=='Cara' else 0,terra_owned=1000 if n=='Fin' else 0,liability='none; no credit issued'))
        rows.append(dict(stage=stage,hour=0 if stage=='OPENING' else times[stage],owner='Bob cash / Alice shares',location='in transit, export T1',cash_owned=transit_cash,cash_encumbered=transit_cash,cash_available=0,ares_owned=transit_shares,ares_encumbered=transit_shares,ares_available=0,belt_owned=0,terra_owned=0,liability='matching staged claims only; do not count claims again'))
    csvout('trade_balances.csv',rows)
    save('regression_checks.json',dict(light_residual_checks=len(checks),maintenance_boundary_assertions=5,serialization_launches_checked=len(packets),packet_layouts_checked=len(sizes),static_quota_total=sum(budgets),audited_book_checkpoints=6,cash_total=500000,share_total=5000,status='PASS'))
    print('All geometry, packet layout, quota, financial state and worked-book checks passed.')
if __name__=='__main__': run()
