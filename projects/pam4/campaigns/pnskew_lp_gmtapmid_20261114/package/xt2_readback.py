"""Measure lane-resolved held-sample compression from existing DIAG NEXT raw."""
import argparse
import math
from pathlib import Path
from statistics import fmean

from diag_metrics import _vector
import diag_next
import gm_summary
import lp_diagnostics as diag
import olympus_common as common


def falling_samples(data, case):
    time = _vector(data,'time')
    common.need(all(a<b for a,b in zip(time,time[1:])) and
                abs(time[-1]-case['stop_s'])<.25e-12,'Incomplete XT2 time grid')
    threshold = case['vdd_V']/2
    samples = []
    for lane in range(8):
        clock,p,m = [_vector(data,node,len(time)) for node in
                     (f'X_ck{lane}',f'X_h{lane}p',f'X_h{lane}m')]
        edges = []
        for i in range(1,len(time)):
            if clock[i-1]>threshold>=clock[i]:
                f = (clock[i-1]-threshold)/(clock[i-1]-clock[i])
                t = time[i-1]+f*(time[i]-time[i-1])
                if t>=case['settle_after_s']:
                    a,b = p[i-1]-m[i-1],p[i]-m[i]
                    edges.append((t,a+f*(b-a)))
        common.need(len(edges)>=8 and all(7.9*diag.UI<=b[0]-a[0]<=8.1*diag.UI
                    for a,b in zip(edges,edges[1:])),f'Missing held edges in lane {lane}')
        samples.append(edges)
    return samples


def metrics(full,half,amplitude_ratio):
    common.need(len(full)==len(half) and len(full)>=8 and
                all(abs(x[0]-y[0])<=.1e-12 for x,y in zip(full,half)),
                'Full and half clock-fall records are not paired')
    x = [v for _,v in half]
    y = [v/amplitude_ratio for _,v in full]
    xc = [v-fmean(x) for v in x]
    yc = [v-fmean(y) for v in y]
    energy = sum(v*v for v in xc)
    common.need(energy>0,'Half-swing held samples have no variance')
    gain = sum(a*b for a,b in zip(xc,yc))/energy
    residual = [1000*(b-gain*a) for a,b in zip(xc,yc)]
    delta = [1000*(b-a) for a,b in zip(x,y)]
    ordered = sorted(map(abs,residual))
    return {'n':len(x),'normalized_full_vs_half_slope':gain,
            'gain_change_dB':20*math.log10(gain) if gain>0 else None,
            'normalized_delta_mean_mV':fmean(delta),
            'normalized_delta_rms_mV':math.sqrt(fmean(v*v for v in delta)),
            'affine_residual_rms_mV':math.sqrt(fmean(v*v for v in residual)),
            'affine_residual_p95_abs_mV':ordered[math.ceil(.95*len(ordered))-1],
            'affine_residual_max_abs_mV':ordered[-1]}


def readback(root):
    plan = diag_next.PLAN
    cases = common.read(plan)['cases'][17:19]
    common.need([c['amplitude_Vppd'] for c in cases]==[.4,.2],'Wrong XT2 source cases')
    waves,source = [],[]
    for case in cases:
        path = root/case['case_id']
        common.need(path.resolve(strict=True)==path,'Existing case root is redirected')
        measured = gm_summary.read_case(root,case,plan)
        common.need(measured['status']=='measured','XT2 source did not measure successfully')
        status = common.read(path/'run_status.json')
        live = common.raw_inventory(path)
        common.need(common.matches_historical_inventory(status['raw_inventory'],live),
                    'Existing XT2 raw differs from the run inventory')
        data = diag.raw_psf(path,dict(status,raw_inventory=live),r'raw/xt2Swing\.tran(?:\.tran)?')
        waves.append(falling_samples(data,case))
        source.append({'case_id':case['case_id'],'status_sha256':common.sha(path/'run_status.json'),
                       'measurement_sha256':common.sha(path/'measurements.json')})
    return {'format':'pam4_xt2_held_readback_v1','source':source,
            'sampling':'Primary held differential voltage at each lane clock falling through VDD/2',
            'normalization':'Full swing divided by the commanded 2:1 differential source ratio',
            'residual':'Full/2 versus half after independent affine fit per lane',
            'lanes':[dict(lane=i,**metrics(a,b,2.0)) for i,(a,b) in enumerate(zip(*waves))],
            'FFE_SER':None}


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--diag-next-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    root,out = a.diag_next_root.resolve(),a.output.resolve()
    common.need(not out.is_relative_to(root),'Write the report outside the existing run root')
    common.write_new(out,readback(root))
