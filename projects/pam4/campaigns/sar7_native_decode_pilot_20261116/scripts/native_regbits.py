import json,os,sys
sys.path.insert(0,os.environ['PAM4_SAR7_FAST_PACKAGE'])
import sar7_fast
ps=sar7_fast.offset.base.review.parse_selected
from bisect import bisect_left
C=sys.argv[1]; case=json.load(open(C+'/case.json')); w=case['wave']
names={'time'}|{f'bit{b}' for b in range(7)}|{f'bit{b}b' for b in range(7)}|{f'q{b}p' for b in range(7)}|{f'q{b}n' for b in range(7)}|{'conv'}
names&= set(w['saved_signals'])|{'time'}
d=ps(C+'/raw/tranResponse.tran.tran',names); t=list(d.values['time']); V={k:list(v) for k,v in d.values.items()}
def at(n,x):
  i=bisect_left(t,x); 
  if t[i]==x: return V[n][i]
  a=(x-t[i-1])/(t[i]-t[i-1]); return V[n][i-1]+a*(V[n][i]-V[n][i-1])
P=w['period_s']; out=[]
for cv in w['conversions']:
  base=cv['sample_s']-67e-12
  row={'i':cv['index'],'exp':cv['expected_code'],'end_ps':round((cv['end_s']-base)*1e12,2)}
  for off in (548,550,554,557,560,565):
    x=base+off*1e-12
    row[off]=[(round(at(f'bit{b}',x),3),round(at(f'bit{b}b',x),3)) for b in range(6,-1,-1)]
  row['conv']=[round(at('conv',base+o*1e-12),3) for o in (548,554,557,560,565)]
  out.append(row)
print(json.dumps(out))
