"""Diagnostic only: correlate C0 held samples with labels over symbol lags. Package unchanged."""
import sys, json
from pathlib import Path
from functools import partial
sys.path.insert(0, sys.argv[1])
import c0_review as c
import olympus_common as common
run = Path(sys.argv[2])
status = common.read(run/'run_status.json')
live = common.raw_inventory(run)
raw = c.safe_raw(run, dict(status, raw_inventory=live), 'tranResponse.tran.tran',
                 parser=partial(c.parse_selected, required={'time', *c.save_names((c.R5/'quiet.scs').read_text('ascii'))}))
frozen = c.pinned_r5()
f = c.collect_r5.original_functions(c.R5/'source_dir')
records, audit = f.r5.extract_records(raw, frozen['training_run']['clock_specification'])
symbols = f.r5.validation_symbols()
import statistics as st
def corr(x,y):
    mx,my=st.fmean(x),st.fmean(y); sx=sum((a-mx)**2 for a in x)**.5; sy=sum((b-my)**2 for b in y)**.5
    return sum((a-mx)*(b-my) for a,b in zip(x,y))/(sx*sy) if sx and sy else float('nan')
for point in ('primary','secondary'):
    fl = frozen['selections'][point]['integer_symbol_lag']
    out=[]
    for lag in range(-6, 40):
        try:
            s,l,t = f.pi.aligned_window(records[point], symbols, lag, 1024, c.HOLDOUT)
        except Exception as e:
            continue
        xs=[float(v if not hasattr(v,'__len__') else sum(v)/len(v)) for v in s]
        ys=[float(v) for v in l]
        out.append((lag, corr(xs,ys)))
    if point=='primary':
        print('sample type', type(s[0]), 'label sample', list(l[:6]))
    best=sorted(out,key=lambda z:-abs(z[1]))[:5]
    print(point,'frozen lag',fl,'corr at frozen',[round(r,3) for L,r in out if L==fl],'best',[(L,round(r,3)) for L,r in best])
