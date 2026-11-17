"""Measure native transient and STB diagnostics from parsed Spectre PSF ASCII."""
import math


STARTUP_NODES = ('GF_VDD', 'GMSR_REF', 'GMSR_D', 'GMSR_BIAS',
                 'GMSQBP', 'GMSQK', 'GMSQBN', 'GMSQST')
TARGET_IREF_UA = {'ss': 338.3, 'tt': 324.8, 'ff': 307.1}
XT2_PATHS = tuple('XT2%s%d' % (leg, i) for leg in 'pm' for i in range(8))
PM_MIN_DEG = 60.0
GM_MIN_DB = 10.0


def _number(value):
    if isinstance(value, complex) and value.imag == 0:
        value = value.real
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError('Expected a finite real value')
    return float(value)


def _values(data, name, count=None):
    values = data.values.get(name, [])
    if not values or count is not None and len(values) != count:
        raise ValueError('Missing or incomplete PSF trace: '+name)
    return values


def _vector(data, name, count=None):
    try:
        return [_number(value) for value in _values(data, name, count)]
    except ValueError as error:
        raise ValueError('Invalid real PSF trace '+name+': '+str(error)) from error


def _review(reason):
    return {'status': 'review', 'passed': None, 'reason': str(reason)}


def _time(data, case):
    times = _vector(data, 'time')
    stop = _number(case['stop_s'])
    settle = _number(case['settle_after_s'])
    tolerance = max(1e-15, stop * 1e-8)
    if not (0 <= settle < stop and len(times) >= 2 and -tolerance <= times[0] <= tolerance and
            abs(times[-1] - stop) <= tolerance and all(a < b for a, b in zip(times, times[1:]))):
        raise ValueError('Transient time grid does not cover the requested start, final ramp and stop')
    return times, settle, stop


def _window(times, start, stop):
    selected = [i for i, time in enumerate(times) if start <= time <= stop]
    if len(selected) < 2:
        raise ValueError('Insufficient settled transient samples')
    return selected


def _stats(values):
    return {'min': min(values), 'max': max(values), 'final': values[-1]}


def _startup_window(signals, times, start, stop, vdd, target):
    selected = _window(times,start,stop)
    windows = {name: [values[i] for i in selected] for name, values in signals.items()}
    supply = windows['GF_VDD']
    iref = [(v-r)/462*1e6 for v, r in zip(supply, windows['GMSR_REF'])]
    replica = [(v-d)/462*1e6 for v, d in zip(supply, windows['GMSR_D'])]
    kick = [(bp-k)/50e3*1e6 for bp, k in zip(windows['GMSQBP'], windows['GMSQK'])]
    positive_ref = all(i > 0 for i in iref)
    servo = [100*(r-i)/i for r, i in zip(replica, iref)] if positive_ref else None
    normalized = {name: _stats([gate/v for gate, v in zip(windows[name], supply)])
                  for name in ('GMSR_BIAS','GMSQBN','GMSQST')} if all(v > 0 for v in supply) else None
    checks = {'supply_within_2_percent': all(abs(v/vdd-1) <= .02 for v in supply),
              'iref_within_2_percent': all(abs(i/target-1) <= .02 for i in iref),
              'servo_within_2_percent': servo is not None and all(abs(x) <= 2 for x in servo),
              'kick_below_0p01_uA': all(abs(i) < .01 for i in kick)}
    return {'checks':checks,'window_requested_start_s':start,
            'window_first_sample_s':times[selected[0]], 'window_last_sample_s':times[selected[-1]],
            'window_samples':len(selected), 'target_iref_uA':target,
            'iref_uA':_stats(iref), 'replica_uA':_stats(replica), 'startup_kick_uA':_stats(kick),
            'servo_error_percent':_stats(servo) if servo is not None else None,
            'settled_node_voltages_V':{name:_stats(vals) for name, vals in windows.items()},
            'gate_voltages_over_supply':normalized}


def _kick_evidence(times, signals, start, stop):
    rows = _window(times,start,stop)
    values = [(signals['GMSQBP'][i]-signals['GMSQK'][i])/50e3*1e6 for i in rows]
    index = max(range(len(rows)),key=lambda i:abs(values[i]))
    return {'peak_signed_uA':values[index],'at_s':times[rows[index]],'samples':len(rows),
            'GMSQST_V_at_peak':signals['GMSQST'][rows[index]],
            'GF_VDD_V_at_peak':signals['GF_VDD'][rows[index]]}


def startup_metrics(data, case):
    """Evaluate final and restart-first supply/replica settling windows."""
    try:
        times, settle, stop = _time(data,case)
        profile = case['profile']
        vdd = _number(case['vdd_V'])
        target = TARGET_IREF_UA[case['process'].lower()]
        if vdd <= 0 or profile not in ('slow','fast','restart'):
            raise ValueError('Invalid startup profile or rail target')
        signals = {name:_vector(data,name,len(times)) for name in STARTUP_NODES}
        start = max(settle,stop-min(.1*stop,25e-6))
        result = _startup_window(signals,times,start,stop+max(1e-15,stop*1e-8),vdd,target)
        checks = result['checks']
        checks['initial_supply_off'] = abs(signals['GF_VDD'][0]) <= .02*vdd
        if profile=='restart':
            first = _number(case['restart_first_settle_s'])
            off = _number(case['restart_off_s'])
            if not 0 < first < off < settle:
                raise ValueError('Invalid cold-restart window ordering')
            first_start = max(first,off-min(.1*off,25e-6))
            first_plateau = _startup_window(signals,times,first_start,off,vdd,target)
            off_rows = [i for i,t in enumerate(times) if off < t < settle and abs(signals['GF_VDD'][i])<=.02*vdd]
            checks['first_plateau_settled'] = all(first_plateau['checks'].values())
            checks['restart_off_observed'] = len(off_rows)>=2
            result['restart_rail_cycle_observed'] = (checks['first_plateau_settled'] and
                checks['restart_off_observed'] and checks['supply_within_2_percent'])
            result['restart_first_plateau'] = first_plateau
            result['restart_off_samples'] = len(off_rows)
            result['restart_off_duration_observed_s'] = (times[off_rows[-1]]-times[off_rows[0]]) if off_rows else None
            result['initial_kick'] = _kick_evidence(times,signals,times[0],first_start)
            result['restart_kick'] = _kick_evidence(times,signals,times[off_rows[-1]] if off_rows else off,start)
        else:
            result['restart_rail_cycle_observed'] = None
            result['initial_kick'] = _kick_evidence(times,signals,times[0],start)
        passed = all(checks.values())
        return dict(result,status='pass' if passed else 'fail',passed=passed,profile=profile)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        return _review(error)


def _unit(data, name):
    """Read units from the PSF descriptor, including Spectre's native type names."""
    explicit = data.unit(name)
    if explicit:
        return str(explicit).lower()
    typename = data.trace_types.get(name) or data.sweep_types.get(name)
    return typename.lower() if isinstance(typename, str) else None


def _margin_scalar(data, name, units):
    rows = _values(data, name, 1)
    unit = _unit(data, name)
    if unit not in units:
        raise ValueError('Unrecognized units for '+name+': '+str(unit))
    return _number(rows[0])*units[unit]


def _crossings(values):
    """Return all crossings/contacts as (left index, right index, fraction)."""
    crossings = []
    for i, value in enumerate(values):
        if value == 0:
            crossings.append((i,i,0.0))
        elif i and values[i-1]*value < 0:
            previous = values[i-1]
            crossings.append((i-1,i,previous/(previous-value)))
    return crossings


def _interpolate(values, crossing):
    left, right, fraction = crossing
    return values[left]*(1-fraction) + values[right]*fraction


def _frequency(frequency, crossing):
    left, right, fraction = crossing
    return frequency[left]*(frequency[right]/frequency[left])**fraction


def _native_frequency(data, name, frequency, crossing):
    if name not in data.values:
        return None
    native = _margin_scalar(data, name, {'hz':1.0})
    left, right, _ = crossing
    if not frequency[left]*.999 <= native <= frequency[right]*1.001:
        raise ValueError(name+' differs from the sampled crossing interval')
    return native


def stb_metrics(trace_data, margin_data):
    """Retain the complete complex return ratio and verify native Spectre margins."""
    result = {'phase_margin_deg':None, 'gain_margin_db':None,
              'thresholds':{'phase_margin_deg':PM_MIN_DEG,'gain_margin_db':GM_MIN_DB}}
    try:
        frequency = _vector(trace_data,'freq')
        gains = [complex(x) for x in _values(trace_data,'loopGain',len(frequency))]
        if not (len(frequency) >= 2 and all(0 < a < b for a,b in zip(frequency,frequency[1:])) and
                all(math.isfinite(x.real) and math.isfinite(x.imag) for x in gains)):
            raise ValueError('Invalid STB frequency grid or complex loopGain')
        result['frequency_Hz'] = frequency
        result['loopGain_real_imag'] = [[g.real,g.imag] for g in gains]
        if _unit(trace_data,'freq') not in ('hz',):
            raise ValueError('STB frequency unit does not establish Hz')
        magnitudes = [20*math.log10(abs(g)) if g else -6000.0 for g in gains]
        unity = _crossings(magnitudes)
        positive_real = [point for point in _crossings([g.imag for g in gains])
                         if _interpolate(gains,point).real > 0]
        result['unity_crossings_Hz'] = [_frequency(frequency,point) for point in unity]
        result['zero_phase_crossings_Hz'] = [_frequency(frequency,point) for point in positive_real]
        if margin_data is None or margin_data.sweep_names:
            raise ValueError('Missing native scalar STB margins')
        if (trace_data.header.get('probe') and margin_data.header.get('probe') and
                trace_data.header['probe'] != margin_data.header['probe']):
            raise ValueError('STB trace and native margin probes differ')
        pm = _margin_scalar(margin_data,'phaseMargin',{'deg':1.0,'rad':180/math.pi})
        gm = _margin_scalar(margin_data,'gainMargin',{'db':1.0})
        result.update(phase_margin_deg=pm,gain_margin_db=gm)
        state = margin_data.values.get('stb_state',[])
        if len(state)==1 and isinstance(state[0],str):
            result['native_state'] = state[0]
        if len(unity)!=1 or len(positive_real)!=1:
            raise ValueError('Missing or multiple sampled unity/zero-phase crossings')
        # Spectre's native loopGain critical phase is 0 degrees on the
        # positive real axis. Preserve native signs and compare independently.
        phases = [math.degrees(math.atan2(g.imag,g.real)) for g in gains]
        left,right,fraction = unity[0]
        phase_delta = (phases[right]-phases[left]+180)%360-180
        sampled_pm = (phases[left]+phase_delta*fraction+180)%360-180
        sampled_gm = -_interpolate(magnitudes,positive_real[0])
        result.update(sampled_phase_margin_deg=sampled_pm,sampled_gain_margin_db=sampled_gm,
                      phase_margin_frequency_Hz=_native_frequency(margin_data,'phaseMarginFreq',frequency,unity[0]),
                      gain_margin_frequency_Hz=_native_frequency(margin_data,'gainMarginFreq',frequency,positive_real[0]))
        if abs(pm-sampled_pm)>2 or abs(gm-sampled_gm)>.25:
            raise ValueError('Native signed margins differ from sampled loopGain')
        native_state = result.get('native_state','').lower()
        unstable = 'not stable' in native_state or 'unstable' in native_state
        if unstable and pm >= PM_MIN_DEG and gm >= GM_MIN_DB:
            raise ValueError('Native stability state conflicts with reported margins')
        passed = pm >= PM_MIN_DEG and gm >= GM_MIN_DB and not unstable
        return dict(result,status='pass' if passed else 'fail',passed=passed)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as error:
        return dict(result,**_review(error))


def _region(value):
    if isinstance(value,str) and value.strip():
        return value
    numeric = _number(value)
    if numeric == int(numeric):
        return str(int(numeric))
    raise ValueError('Invalid Spectre region code')


def xt2_metrics(data, case):
    """Report actual XT2 tail headroom and raw Spectre region occupancy."""
    try:
        times, settle, _ = _time(data,case)
        selected = _window(times,settle,times[-1])
        paths = case.get('xt2_paths',XT2_PATHS)
        if len(paths)!=16 or len(set(paths))!=16 or not all(isinstance(n,str) and n for n in paths):
            raise ValueError('Expected exactly sixteen unique XT2 tails')
        reports = {}
        durations = [times[b]-times[a] for a,b in zip(selected,selected[1:])]
        for path in paths:
            vds = _vector(data,path+':vds',len(times))
            vdsat = _vector(data,path+':vdsat',len(times))
            regions = _values(data,path+':region',len(times))
            margins = [vds[i]-vdsat[i] for i in selected]
            labels = [_region(regions[i]) for i in selected]
            total_time = sum(durations)
            occupancy = {name:{'sample_count':labels.count(name),
                               'sample_fraction':labels.count(name)/len(labels),
                               'time_fraction':sum(dt for label,dt in zip(labels,durations) if label==name)/total_time}
                         for name in sorted(set(labels))}
            minimum = min(margins)
            worst_index = margins.index(minimum)
            reports[path] = {'minimum_margin_V':minimum,'minimum_at_s':times[selected[worst_index]],
                             'region_at_minimum':labels[worst_index],
                             'negative_margin_sample_fraction':sum(m < 0 for m in margins)/len(margins),
                             'region_occupancy':occupancy}
        worst = min(reports,key=lambda path:reports[path]['minimum_margin_V'])
        minimum = reports[worst]['minimum_margin_V']
        return {'status':'measured','passed':None,'all_positive_margin':minimum>0,
                'minimum_margin_V':minimum,'minimum_margin_tail':worst,
                'window_first_sample_s':times[selected[0]],'window_last_sample_s':times[selected[-1]],
                'window_samples':len(selected),'devices':reports,
                'region_time_fraction_convention':'region at left sample held to the next sample'}
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        return _review(error)
