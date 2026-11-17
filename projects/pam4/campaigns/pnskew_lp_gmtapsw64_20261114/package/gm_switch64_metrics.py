"""Collect native code-switch PSF and compare it to an unchanged destination run."""
from bisect import bisect_left
import hashlib
import math
from pathlib import Path
import re

from comp_measure import safe_raw
from diag_metrics import _region, _values, _vector, XT2_PATHS
from lp_diagnostics import UI
import olympus_common as common
from pvt.reference.psf_ascii import parse_text


FORMAT = 'pam4_split64_switch_transient_v1'
SWEEP_BYTES_MAX = 320*1024**2
SWEEP_RE = re.compile(r'raw/codeSwitch\.tran(?:\.tran)?')
TAIL_NODES = {
    leg:[f'GMSK{tap:02d}{leg}VT:p' for tap in (6,11,16)] for leg in ('P','M')
}
PERIOD_S = 16*UI
EDGE_MATCH_S = .10e-12
HOLD_WINDOW_S = 1e-9
MIN_LANE_SAMPLES = 8
THRESHOLDS = {'vb1_V':.001,'vb2_V':.001,'leg_current_fraction':.02,
              'held_difference_V':.001,'xt2_margin_deficit_V':.002}
BIAS_AND_TAILS = ('vb1_V','vb2_V','total_P_A','total_M_A')
PAIR_FIELDS = ('process','temperature_C','vdd_V','vb1_V','resolution','bias_kind','tail_variant',
               'anchors','final_code','switch_time_s','stop_s','slew_s','skew_ps','amplitude_Vppd',
               'max_step_s')
PUBLIC_CASE_FIELDS = (*PAIR_FIELDS,'case_id','group','initial_code','reference_case_id','offset_s')


def parse_transient(path):
    """Keep the native parser/attestation contract with a larger bounded tran input."""
    path = Path(path)
    with path.open('rb') as stream:
        blob = stream.read(SWEEP_BYTES_MAX+1)
    common.need(0<len(blob)<=SWEEP_BYTES_MAX and b'\x00' not in blob,
                'Missing, oversized, or binary code-switch PSF')
    data = parse_text(blob.decode('utf-8-sig'),source=str(path))
    data.sha256 = hashlib.sha256(blob).hexdigest()
    return data


def native_transient(root,status):
    names = [item['path'] for item in status['raw_inventory'] if SWEEP_RE.fullmatch(item['path'])]
    common.need(len(names)==1,'Expected exactly one completed native codeSwitch tran file')
    return safe_raw(root,status,names[0].removeprefix('raw/'),parser=parse_transient)


def axes(data,case):
    times = _vector(data,'time')
    time_unit = (data.unit('time') or '').strip().lower()
    stop = case['stop_s']
    switch = case['switch_time_s']
    end = switch+case.get('offset_s',0.)+case['slew_s']
    common.need(data.sweep_names==['time'] and time_unit in ('s','sec','second','seconds') and
                len(times)>=3 and abs(times[0])<=1e-15 and abs(times[-1]-stop)<=1e-15 and
                all(a<b for a,b in zip(times,times[1:])) and
                HOLD_WINDOW_S+PERIOD_S<switch<end<stop-HOLD_WINDOW_S,
                'Invalid or incomplete native switch time axis')
    return times,switch,end,stop


def held_edges(data,times,vdd):
    threshold = vdd/2
    lanes = []
    for lane in range(8):
        clk,p,m = (_vector(data,tag,len(times)) for tag in
                   (f'X_ck{lane}',f'X_h{lane}p',f'X_h{lane}m'))
        edges = []
        for i in range(1,len(times)):
            if clk[i-1]>threshold>=clk[i]:
                f = (clk[i-1]-threshold)/(clk[i-1]-clk[i])
                t = times[i-1]+f*(times[i]-times[i-1])
                left,right = p[i-1]-m[i-1],p[i]-m[i]
                edges.append([t,left+f*(right-left)])
        common.need(len(edges)>=MIN_LANE_SAMPLES and times[-1]-edges[-1][0]<=8.1*UI and all(
                    7.9*UI<=b[0]-a[0]<=8.1*UI for a,b in zip(edges,edges[1:])),
                    f'Missing held events on lane {lane}')
        lanes.append(edges)
    return lanes


def window_grid(times,start,stop):
    """Use both exact endpoints, even if the native solver took a shorter path."""
    lo,hi = bisect_left(times,start),bisect_left(times,stop)
    return lo,hi,sorted({start,stop,*times[lo:hi]})


def xt2_waveforms(data,times,windows):
    """Summarize every native tail and retain the min-margin trajectory."""
    report = {label:{} for label in windows}
    minima = [math.inf]*len(times)
    non_sat = [0]*len(times)
    for tail in XT2_PATHS:
        vds = _vector(data,tail+':vds',len(times))
        vdsat = _vector(data,tail+':vdsat',len(times))
        regions = [_region(v) for v in _values(data,tail+':region',len(times))]
        margins = [a-abs(b) for a,b in zip(vds,vdsat)]
        minima = [min(a,b) for a,b in zip(minima,margins)]
        non_sat = [n+(region.strip() not in ('2','2.0')) for n,region in zip(non_sat,regions)]
        timeline = {'time_s':times,'margin_V':margins,'region':regions}
        for label,(start,stop) in windows.items():
            lo,hi,window = window_grid(times,start,stop)
            worst_margin,worst_t = min((at(timeline,'margin_V',t),t) for t in window)
            occupancy = {}
            for i in range(max(lo-1,0),min(hi,len(times)-1)):
                overlap = max(0.,min(stop,times[i+1])-max(start,times[i]))
                region = regions[i]
                if overlap:
                    occupancy[region] = occupancy.get(region,0.)+overlap/(stop-start)
            report[label][tail] = {'minimum_margin_V':worst_margin,'time_at_minimum_s':worst_t,
                                   'native_region_at_minimum':at(timeline,'region',worst_t,hold=True),
                                   'native_region_time_fraction_left_hold':occupancy}
    return report,minima,non_sat


def measurement(data,case):
    times,switch,end,stop = axes(data,case)
    windows = {'before':(switch-HOLD_WINDOW_S,switch), 'transition':(switch,end),
               'recovery':(end,stop-HOLD_WINDOW_S), 'final':(stop-HOLD_WINDOW_S,stop)}
    signals = {'time_s':times,'vb1_V':_vector(data,'GMSKVBIAS',len(times)),
               'vb2_V':_vector(data,'X_vb',len(times))}
    for leg,names in TAIL_NODES.items():
        values = [_vector(data,name,len(times)) for name in names]
        signals.update({name:series for name,series in zip(names,values)})
        signals[f'total_{leg}_A'] = [sum(current) for current in zip(*values)]
    xt2,minima,non_sat = xt2_waveforms(data,times,windows)
    signals.update(xt2_worst_margin_V=minima,xt2_nonsaturation_count=non_sat)
    window_stats = {}
    for label,(start,finish) in windows.items():
        _,_,window = window_grid(times,start,finish)
        per_signal = {name:[at(signals,name,t) for t in window] for name in signals if name!='time_s'}
        window_stats[label] = {name:{'min':min(v),'max':max(v),'last':v[-1]} for name,v in per_signal.items()}
    return {'format':FORMAT,'case_id':case['case_id'],'case':{k:case[k] for k in PUBLIC_CASE_FIELDS if k in case},
            'switch_time_s':switch,'switch_end_s':end,'stop_s':stop,
            'tran_sha256':data.sha256,'signals':signals,'held_by_lane':held_edges(data,times,case['vdd_V']),
            'windows_s':windows,'signal_window_statistics':window_stats,'XT2_by_window':xt2}


def collect(root,case,status):
    log = (root/'spectre.log').read_text(encoding='utf-8',errors='replace')
    common.need(not re.search(r'SPECTRE-(8059|8061|8282|8287)\b',log),
                'Spectre skipped a required switch transient save')
    report = measurement(native_transient(root,status),case)
    common.need(all(common.sha(root/name)==digest for name,digest in case['staged_source_sha256'].items())
                and common.sha(root/'spectre.log')==status['spectre_log_sha256'],
                'Staged input or solver log changed during collection')
    common.write_new(root/'measurements.json',dict(report,measurement_complete=True,
        bench_sha256=common.sha(root/'bench.scs'),run_status_sha256=common.sha(root/'run_status.json')))
    common.write_new(root/'completion.json',{'measurement_complete':True,
        'measurement_sha256':common.sha(root/'measurements.json'),'completed_utc':common.utc()})


def at(table,name,t,*,hold=False):
    times = table['time_s']
    values = table[name]
    j = bisect_left(times,t)
    if j==0:
        common.need(abs(t-times[0])<=1e-15,'Requested time precedes captured transient')
        return values[0]
    if j==len(times):
        common.need(abs(t-times[-1])<=1e-15,'Requested time exceeds captured transient')
        return values[-1]
    same = t==times[j]
    if same or hold or name=='xt2_nonsaturation_count':
        return values[j] if same else values[j-1]
    f = (t-times[j-1])/(times[j]-times[j-1])
    return values[j-1]+f*(values[j]-values[j-1])


def relative_current_error(value,baseline):
    return abs(value-baseline)/max(abs(baseline),1e-12)


def errors(s,r,t,reference_t):
    return {**{name:abs(at(s,name,t)-at(r,name,reference_t)) for name in BIAS_AND_TAILS[:2]},
            **{name:relative_current_error(at(s,name,t),at(r,name,reference_t))
               for name in BIAS_AND_TAILS[2:]},
            'xt2_margin_deficit_V':max(0.,at(r,'xt2_worst_margin_V',reference_t)-
                                      at(s,'xt2_worst_margin_V',t))}


def pair_held(switched,reference,shift=0.):
    """Use actual phase-identical clock events, rejecting any interior missing edge."""
    common.need(len(switched)==len(reference)==8,'Need eight clock-event lanes in both captures')
    by_lane = []
    for source,target in zip(switched,reference):
        target_times = [sample[0] for sample in target]
        paired = []
        for t,v in source:
            match = t-shift
            if match<target_times[0]-EDGE_MATCH_S or match>target_times[-1]+EDGE_MATCH_S:
                continue
            j = bisect_left(target_times,match)
            possible = [i for i in (j-1,j) if 0<=i<len(target)]
            closest = min(possible,key=lambda i:abs(target_times[i]-match))
            common.need(abs(target_times[closest]-match)<=EDGE_MATCH_S,
                        'Held events do not match the same clock phase')
            paired.append((t,abs(v-target[closest][1])))
        by_lane.append(paired)
    return by_lane


def reference_screen(ref,stop):
    # Roundoff at the horizon is clipped by at().  Check one 16-UI history
    # against its own preceding period with tighter tolerances than the DUT.
    table = ref['signals']
    before = stop-HOLD_WINDOW_S
    grid = [t for t in table['time_s'] if before<=t<=stop]
    common.need(len(grid)>=2,'Destination reference lacks a complete final window')
    limits = {'vb1_V':THRESHOLDS['vb1_V']/4,'vb2_V':THRESHOLDS['vb2_V']/4,
              'total_P_A':THRESHOLDS['leg_current_fraction']/4,
              'total_M_A':THRESHOLDS['leg_current_fraction']/4}
    observed = {k:0. for k in limits}
    for t in grid:
        d = errors(table,table,t,t-PERIOD_S)
        observed = {k:max(m,d[k]) for k,m in observed.items()}
    pairs = pair_held(ref['held_by_lane'],ref['held_by_lane'],PERIOD_S)
    last = [[difference for t,difference in lane if before<=t<=stop] for lane in pairs]
    maxima = [max(lane,default=None) for lane in last]
    lane_ok = all(len(lane)>=MIN_LANE_SAMPLES and max(lane)<=THRESHOLDS['held_difference_V']/4
                  for lane in last)
    return {'stationary':all(observed[k]<=v for k,v in limits.items()) and lane_ok,
            'phase_period_s':PERIOD_S,'window_start_s':before,'periodic_rail_current_error':observed,
            'held_max_error_V_by_lane':maxima,'held_sample_count_by_lane':[len(lane) for lane in last]}


def final_xt2_region_comparison(switched,reference):
    """Inspect native-region dwell against the identical destination stimulus."""
    final = 'final'
    left,right = switched['XT2_by_window'][final],reference['XT2_by_window'][final]
    def fraction(row):
        return sum(v for region,v in row['native_region_time_fraction_left_hold'].items()
                   if region.strip() not in ('2','2.0'))
    evidence = {}
    for tail in XT2_PATHS:
        actual,target = left[tail],right[tail]
        a,b = fraction(actual),fraction(target)
        evidence[tail] = {'switch_nonsaturation_fraction':a,'reference_nonsaturation_fraction':b,
                          'difference_fraction':a-b,'switch_minimum_margin_V':actual['minimum_margin_V'],
                          'reference_minimum_margin_V':target['minimum_margin_V']}
    return evidence


def compare(switched,reference):
    """Produce an observed recovery or an explicit censored status from completed captures."""
    result = {'status':'unresolved','settled':None,'recovery_s_after_event':None,
              'thresholds':THRESHOLDS,'sustained_window_s':HOLD_WINDOW_S,
              'minimum_post_settle_samples_each_lane':MIN_LANE_SAMPLES}
    if reference is None:
        return dict(result,reason='Missing completed destination reference')
    try:
        case,ref = switched['case'],reference['case']
        common.need(switched['format']==reference['format']==FORMAT and
                    case['initial_code']!=case['final_code'] and ref['initial_code']==ref['final_code'] and
                    case.get('reference_case_id')==ref['case_id'] and
                    all(case.get(k)==ref.get(k) for k in PAIR_FIELDS),
                    'Destination reference identity, code, stimulus or environment differs')
        end,stop = switched['switch_end_s'],switched['stop_s']
        result['reference_case_id'] = ref['case_id']
        result['reference_screen'] = reference_screen(reference,stop)
        result['final_XT2_native_region_comparison'] = final_xt2_region_comparison(switched,reference)
        if not result['reference_screen']['stationary']:
            return dict(result,reason='Destination reference did not independently become periodic')
        s,r = switched['signals'],reference['signals']
        grid = sorted({end,stop}|{t for table in (s,r) for t in table['time_s'] if end<=t<=stop})
        limits = {'vb1_V':THRESHOLDS['vb1_V'],'vb2_V':THRESHOLDS['vb2_V'],
                  'total_P_A':THRESHOLDS['leg_current_fraction'],
                  'total_M_A':THRESHOLDS['leg_current_fraction'],
                  'xt2_margin_deficit_V':THRESHOLDS['xt2_margin_deficit_V']}
        biggest = {k:0. for k in limits}
        last_rail_bad = None
        xt2_count_error_max = 0
        for i,t in enumerate(grid):
            delta = errors(s,r,t,t)
            biggest = {k:max(v,delta[k]) for k,v in biggest.items()}
            if any(delta[k]>limits[k] for k in limits):
                last_rail_bad = i
            xt2_count_error_max = max(xt2_count_error_max,int(abs(
                at(s,'xt2_nonsaturation_count',t)-at(r,'xt2_nonsaturation_count',t))))
        by_lane = [[event for event in lane if end<=event[0]<=stop] for lane in
                   pair_held(switched['held_by_lane'],reference['held_by_lane'])]
        held_violations = [t for lane in by_lane for t,v in lane if v>THRESHOLDS['held_difference_V']]
        last_bad_held = max(held_violations,default=None)
        result.update(max_error_after_event=biggest,native_XT2_nonsaturation_count_error_max=xt2_count_error_max,
                      max_held_error_V_by_lane=[max((v for _,v in lane),default=None) for lane in by_lane],
                      last_bad_continuous_sample_s=grid[last_rail_bad] if last_rail_bad is not None else None,
                      last_bad_held_sample_s=last_bad_held,observation_end_s=stop)
        next_rail = (end if last_rail_bad is None else grid[last_rail_bad+1]
                     if last_rail_bad+1<len(grid) else None)
        next_held = end if last_bad_held is None else min(
            (t for lane in by_lane for t,_ in lane if t>last_bad_held),default=None)
        if next_rail is None or next_held is None:
            return dict(result,status='right_censored',settled=False,reason='A violation reaches the stop')
        start = max(next_rail,next_held)
        samples = [sum(t>=start for t,_ in lane) for lane in by_lane]
        result.update(first_sample_after_all_violations_s=start,post_settle_samples_by_lane=samples)
        if stop-start<HOLD_WINDOW_S or any(n<MIN_LANE_SAMPLES for n in samples):
            return dict(result,status='right_censored',settled=False,
                        reason='Insufficient uninterrupted final window or too few lane events')
        return dict(result,status='observed_recovery',settled=True,recovery_s_after_event=start-end)
    except (AttributeError,IndexError,KeyError,TypeError,ValueError) as exc:
        return dict(result,reason=str(exc))
