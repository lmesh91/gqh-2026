"""Reproduce bounded v2 evidence; not the complete hackathon simulator."""
from pathlib import Path
import csv, hashlib, json, subprocess, sys
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results'
for script in ['model.py','test_direct_settlement.py','trace_v2.py']:
    subprocess.run([sys.executable,str(ROOT/script)],check=True,cwd=ROOT.parent)
checks={}
assert 9*66==594 and 594<=600 and 44+22==66
checks['allocated_backbone_originations_per_rolling_day']=594
# Validate the declared fixed-width layout, including the batch header.
bodies={'ORDER':80,'PAY_REQUEST':160,'PAYMENT':96,'DELIVERY':120,'RECEIVED':56,'CONTROL':64,'TRANSFER':80,'PRICE':136,'CONTRACT_INSTRUCTION':192,'OPENED':64}
checks['records_per_payload']={k:(960-16)//(64+n) for k,n in bodies.items()}
assert checks['records_per_payload']==dict(ORDER=6,PAY_REQUEST=4,PAYMENT=5,DELIVERY=5,RECEIVED=7,CONTROL=7,TRANSFER=6,PRICE=4,CONTRACT_INSTRUCTION=3,OPENED=7)
for case in ['earth_mars','earth_ceres','jupiter_mars','neptune_mars']:
    summary=json.loads((OUT/f'v2_{case}_summary.json').read_text())
    assert summary['total_launches']==45 and summary['backbone_launches']==44
    assert summary['direct_launches']==1 and summary['backbone_originations']==5
    assert sorted(summary['originations_by_institution'].values())==[2,3]
    assert summary['backed_claim_hour']<summary['seller_spendable_hour']<summary['complete_hour']<summary['complete_known_hour']
    with (OUT/f'v2_{case}_balances.csv').open() as f:
        rows=list(csv.DictReader(f))
    for r in rows:
        cash=sum(int(r[k]) for k in ['alice_available_cents','alice_reserved_cents','other_opening_cash_cents','seller_new_proceeds_cents','cash_in_transit_cents'])
        stock=sum(int(r[k]) for k in ['seller_trade_shares_remaining','alice_trade_shares','shares_in_transit','other_original_shares'])
        assert cash==int(r['total_cash_cents'])==50000000
        assert stock==int(r['total_shares'])==5000
    checks[case]={'conserved_event_rows':len(rows),'physical_launches':45,'backbone_originations':5}
checks['passed']=True
checks['scope']='Conditional no-loss traces and bounded financial model; no full stochastic transport or derivative packet execution'
(OUT/'v2_regression_checks.json').write_text(json.dumps(checks,indent=2)+'\n')
paths=list((ROOT.parent/'info').glob('*'))
paths+=list(ROOT.glob('*.md'))+[ROOT/n for n in ['model.py','direct_settlement.py','transport_no_loss.py','test_direct_settlement.py','trace_v2.py','checks_v2.py']]
paths+=list(OUT.glob('v2_*'))+[OUT/n for n in ['README.md','validation.json','access.csv','long_scan_links.csv','long_scan_routes_screen.csv','long_scan_boundary.json','difficult_epoch.json']]
manifest={}
for p in sorted(set(paths)):
    if not p.is_file() or p.name=='v2_provenance.json': continue
    digest=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): digest.update(block)
    manifest[str(p.relative_to(ROOT.parent))]=digest.hexdigest()
(OUT/'v2_provenance.json').write_text(json.dumps({'design_version':2,'source_precedence':'brief.pdf and data.zip govern; independent exported CSV is secondary','files':manifest,'scope':checks['scope'],'long_scan':'Retained hourly geometry screen; not rerun by checks_v2'},indent=2)+'\n')
print('Current v2 accounting, layout and evidence checks passed.')
