"""Milestone 1 geometry/research model. Seconds since the brief's TDB epoch.
Not a complete implementation of the brief's transport simulator.
"""
from pathlib import Path
import csv, hashlib, itertools, json, math, zipfile
import numpy as np
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'milestone1/results'
with zipfile.ZipFile(ROOT/'info/data.zip') as z:
    ORBITS=json.loads(z.read('orbital_elements.json'))['bodies']
    NET=json.loads(z.read('network_model.json'))
BODIES=ORBITS+NET['relays']; NAMES=[b['name'] for b in BODIES]
D={b['name']:b for b in BODIES}; LIGHT=8.317*60
EDGES=[(s,r) for s in NAMES[:9] for r in NAMES[9:]]+[(NAMES[9],NAMES[10])]
DIRECTED=EDGES+[(b,a) for a,b in EDGES]
CHECK=np.array([[-.213426,-.410281,-.013955],[.679067,-.257950,-.042725],[1.003581,-.023693,-.000003],[.247476,1.526869,.025929],[.375786,2.653941,.014791],[-3.438179,4.038309,.060149],[9.271221,1.717485,-.398962],[8.962475,17.253919,-.052129],[29.839098,1.351785,-.715470],[2,2,0],[-2,2,0]])
def pos(name,t):
    b=D[name]; t=np.asarray(t); M=np.deg2rad((b['mean_anomaly_deg']+b['mean_motion_deg_day']*t/86400)%360)
    E=M.copy(); e=b['e']
    for _ in range(12):
        step=(E-e*np.sin(E)-M)/(1-e*np.cos(E)); E=E-step
        if np.max(np.abs(step))<1e-14: break
    x=b['a_au']*(np.cos(E)-e); y=b['a_au']*math.sqrt(1-e*e)*np.sin(E)
    w,i,o=np.deg2rad([b['arg_peri_deg'],b['i_deg'],b['node_deg']])
    X=np.cos(w)*x-np.sin(w)*y; Y=np.sin(w)*x+np.cos(w)*y
    return np.stack([np.cos(o)*X-np.sin(o)*np.cos(i)*Y,np.sin(o)*X+np.cos(o)*np.cos(i)*Y,np.sin(i)*Y],axis=-1)
def photon(a,b,te):
    te=np.asarray(te); p=pos(a,te); ta=te+LIGHT*np.linalg.norm(pos(b,te)-p,axis=-1)
    for _ in range(12):
        nt=te+LIGHT*np.linalg.norm(pos(b,ta)-p,axis=-1)
        if np.max(np.abs(nt-ta))<1e-5: ta=nt; break
        ta=nt
    q=pos(b,ta); v=q-p; vv=np.sum(v*v,axis=-1)
    f=np.clip(-np.sum(p*v,axis=-1)/vv,0,1)
    clearance=np.linalg.norm(p+f[...,None]*v,axis=-1)
    return ta,(ta-te)/LIGHT,clearance

def launchable(a,b,te,maintenance=True):
    ta,d,c=photon(a,b,te); ok=c>=.1
    if maintenance:
        for m in NET['maintenance']:
            if {a,b}==set(m['edge']):
                lo=m['start_hours']*3600; hi=m['end_hours']*3600
                ok=ok & ~((np.asarray(te)<hi)&(ta>=lo))
    return ok

def paths(a,b):
    if a==b: return [(a,)]
    return [(a,'Relay A',b),(a,'Relay B',b),(a,'Relay A','Relay B',b),(a,'Relay B','Relay A',b)]
def route(path,ready,maintenance=True,check=True):
    t=float(ready); hops=[]
    for k,(a,b) in enumerate(zip(path,path[1:])):
        te=t+1; ta,d,c=photon(a,b,te)
        if check and not launchable(a,b,te,maintenance): return None
        hops.append(dict(sender=a,receiver=b,ready_s=t,emission_s=te,arrival_s=float(ta),distance_au=float(d),clearance_au=float(c),loss=1-math.exp(-.02*float(d))))
        t=float(ta)+(1 if k<len(path)-2 else 0)
    return dict(path=list(path),arrival_s=t,delay_s=t-ready,hops=hops)
def best(a,b,t,maintenance=True):
    rs=[route(p,t,maintenance) for p in paths(a,b)]; rs=[r for r in rs if r is not None]
    return min(rs,key=lambda r:(r['delay_s'],r['path'])) if rs else None

def save(name,obj):
    OUT.mkdir(parents=True,exist_ok=True); (OUT/name).write_text(json.dumps(obj,indent=2)+'\n')
def csvout(name,rows):
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]); w.writeheader(); w.writerows(rows)

def validation():
    err=np.abs(np.array([pos(n,0) for n in NAMES])-CHECK)
    assert err.max()<1e-5
    tests=[]
    for b in BODIES:
        n=b['name']; per=360/b['mean_motion_deg_day']*86400
        r=np.linalg.norm(pos(n,np.linspace(-per,per,1001)),axis=-1)
        re=float(np.linalg.norm(pos(n,per)-pos(n,0)))
        assert re<1e-10 and min(r)>=b['a_au']*(1-b['e'])-1e-10 and max(r)<=b['a_au']*(1+b['e'])+1e-10
        tests.append(dict(body=n,epoch_max_error_au=float(err[NAMES.index(n)].max()),period_error_au=re,min_radius_au=float(min(r)),max_radius_au=float(max(r)),position_hour300=pos(n,300*3600).tolist()))
    examples=[]
    for a,b in [('Earth','Mars'),('Mars','Earth'),('Earth','Neptune'),('Neptune','Earth')]:
        ta,d,c=photon(a,b,0); static=LIGHT*np.linalg.norm(pos(b,0)-pos(a,0))
        examples.append(dict(sender=a,receiver=b,moving_flight_s=float(ta),frozen_flight_s=float(static),difference_s=float(ta-static),direct_success=float(math.exp(-.08*d)),clearance_au=float(c)))
    csvcheck=[]
    with (ROOT/'info/Solar_System_positions_2026-09-22_to_2226-10-01_daily.csv').open() as f:
        for row in csv.DictReader(f):
            day=float(row['days_since_2026-09-22'])
            if day in (0,1,365,3652,36525,73050):
                errs={n:float(np.linalg.norm(pos(n,day*86400)-np.array([float(row[n.lower()+'_'+axis+'_au']) for axis in 'xyz']))) for n in NAMES[:9]}
                csvcheck.append(dict(day=day,max_error_au=max(errs.values()),body_errors_au=errs))
    save('validation.json',dict(tests=tests,light_examples=examples,csv_cross_check=csvcheck,archive_sha256=hashlib.sha256((ROOT/'info/data.zip').read_bytes()).hexdigest()))

def access():
    rows=[]
    for h in [0,300,365.25*24,10*365.25*24,100*365.25*24]:
        for dest in ['Earth','Mars','Neptune','Ceres']:
            for n in NAMES[:9]:
                r=best(n,dest,h*3600)
                if r:
                    ts=(h*3600)+np.arange(1440)*60
                    # brief's simultaneous launch-availability definition, not end-to-end delivery probability
                    ok=np.ones(len(ts),bool)
                    for a,b in zip(r['path'],r['path'][1:]): ok &= launchable(a,b,ts)
                    av=float(ok.mean())
                else: av=0
                rows.append(dict(hour=h,origin=n,authority=dest,route=' > '.join(r['path']) if r else 'NONE',delay_minutes=r['delay_s']/60 if r else None,launch_availability_24h_sample=av,sample_minutes=1))
    csvout('access.csv',rows)
    # Placement screen: geography only, uniformly weighted origin->clearer legs, four epochs.
    mats=[]
    for h in [0,300,365.25*24,100*365.25*24]:
        mats.append(np.array([[best(a,b,h*3600)['delay_s']/60 if best(a,b,h*3600) else 1e6 for b in NAMES[:9]] for a in NAMES[:9]]))
    rows=[]
    for k in (1,2,3):
        ranked=[]
        for combo in itertools.combinations(range(9),k):
            # One fixed assignment across sampled epochs; no per-transaction teleportation.
            avg=np.mean(mats,axis=0); assign=np.argmin(avg[:,combo],axis=1)
            costs=np.array([[m[i,combo[assign[i]]] for i in range(9)] for m in mats])
            ranked.append((float(costs.mean()),float(costs.max()),combo,assign))
        mean,mx,combo,assign=min(ranked,key=lambda z:(z[0],z[1]))
        rows.append(dict(clearers=k,sites=[NAMES[i] for i in combo],mean_one_way_minutes=mean,worst_sample_minutes=mx,assignment={NAMES[i]:NAMES[combo[assign[i]]] for i in range(9)}))
    save('placement_screen.json',rows)

def longscan():
    # Hourly directed moving-receiver link scan, chunked; no claim to catch sub-hour grazing closures.
    total=200*365.25*24; step=3600; counts={e:0 for e in DIRECTED}; mn={e:math.inf for e in DIRECTED}; mx={e:0 for e in DIRECTED}
    first=None; sample_count=0; route_stats={n:[0,math.inf,0,None] for n in NAMES[:9]}
    for start in range(0,int(total),24000):
        hours=np.arange(start,min(start+24000,int(total))+ (1 if start+24000>=total else 0)); ts=hours*3600.; sample_count+=len(ts)
        values={}
        for e in DIRECTED:
            ta,d,c=photon(*e,ts); ok=launchable(*e,ts,False); values[e]=(ok,(ta-ts+1)/60)
            counts[e]+=int(ok.sum()); mn[e]=min(mn[e],float(((ta-ts)/60).min())); mx[e]=max(mx[e],float(((ta-ts)/60).max()))
            if first is None and np.any(ok[:-1]!=ok[1:]):
                j=np.where(ok[:-1]!=ok[1:])[0][0]; first=(e,float(ts[j]),float(ts[j+1]))
        # Screening route ranges: all links evaluated at same emission epoch (explicit approximation).
        for n in NAMES[:9]:
            if n=='Mars': arr=np.zeros(len(ts))
            else:
                options=[]
                for p in paths(n,'Mars'):
                    ok=np.ones(len(ts),bool); dur=np.zeros(len(ts))
                    for e in zip(p,p[1:]):
                        ko,dd=values[e]; ok &=ko; dur+=dd
                    dur+=(len(p)-2)/60
                    options.append(np.where(ok,dur,np.inf))
                arr=np.min(options,axis=0)
            finite=np.isfinite(arr); st=route_stats[n]; st[0]+=int(finite.sum())
            if finite.any():
                st[1]=min(st[1],float(arr[finite].min()))
                if arr[finite].max()>st[2]:
                    j=int(np.argmax(np.where(finite,arr,-1))); st[2]=float(arr[j]); st[3]=float(hours[j])
    e,lo,hi=first; orig=[lo,hi]; val=bool(launchable(*e,lo,False))
    while hi-lo>.001:
        mid=(lo+hi)/2
        if bool(launchable(*e,mid,False))==val: lo=mid
        else: hi=mid
    csvout('long_scan_links.csv',[dict(sender=e[0],receiver=e[1],samples=sample_count,availability=counts[e]/sample_count,min_flight_minutes=mn[e],max_flight_minutes=mx[e]) for e in DIRECTED])
    csvout('long_scan_routes_screen.csv',[dict(origin=n,authority='Mars',sampled_availability=s[0]/sample_count,min_minutes=s[1],max_minutes=s[2],max_hour=s[3]) for n,s in route_stats.items()])
    save('long_scan_boundary.json',dict(edge=e,initial_bracket_s=orig,refined_bracket_s=[lo,hi],tolerance_s=.001,state_before=val,sample_hours=1,years=200,samples=sample_count,route_range_method='simultaneous link geometry screening; exact sequential re-evaluation required for E4 Tier 3'))
    poor=max(route_stats,key=lambda n:route_stats[n][2]); t=route_stats[poor][3]*3600
    save('difficult_epoch.json',dict(selection='maximum hourly screened best-route delay to Mars',origin=poor,hour=t/3600,exact_route=best(poor,'Mars',t,False),other_direction=best('Mars',poor,t,False)))

if __name__=='__main__':
    import sys
    validation(); access()
    if '--scan' in sys.argv: longscan()
    print('Geometry validation and requested outputs complete.')
