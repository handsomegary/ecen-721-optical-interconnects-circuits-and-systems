"""Small-gain screen for the beta multiplier's nonzero operating point."""
import math

from diag_metrics import _unit, _vector, _values, _crossings, _frequency, stb_metrics


def beta_metrics(trace, margins):
    native = stb_metrics(trace,margins)
    result = dict(native, passed=None, status='review',
                  native_margin_status=native['status'],
                  screen='beta_small_gain_10dB_sampled_band')
    try:
        freq = _vector(trace,'freq')
        loop = [complex(v) for v in _values(trace,'loopGain',len(freq))]
        if (_unit(trace,'freq')!='hz' or freq[0]>1.01 or freq[-1]<.99e9 or
            len(freq)<400 or not all(0<a<b<=a*10**.021 for a,b in zip(freq,freq[1:])) or
            not all(math.isfinite(z.real) and math.isfinite(z.imag) for z in loop)):
            raise ValueError('Incomplete beta sweep or frequency units')
        size = [abs(z) for z in loop]
        distance = [abs(1-z) for z in loop]
        peak = max(range(len(loop)),key=size.__getitem__)
        closest = min(range(len(loop)),key=distance.__getitem__)
        unity = [_frequency(freq,x) for x in _crossings([v-1 for v in size])]
        low = [z for z,f in zip(loop,freq) if f<=10]
        low_flat = max(abs(z-loop[0]) for z in low)<=max(.005,.02*size[0])
        high_rolloff = max(v for f,v in zip(freq,size) if f>=freq[-1]/10)<=.1 and size[-1]<=size[-51]
        states = margins.values.get('stb_state',[]) if margins is not None else []
        state = str(states[0]) if len(states)==1 else result.get('native_state','')
        result['native_state'] = state or None
        state = state.lower()
        conflicts = any(s in state for s in ('unstable','not stable'))
        screen_pass = (not unity and size[peak]<=10**(-10/20) and
                       low_flat and high_rolloff and not conflicts)
        result.update(critical_point=[1,0],lf_return=[loop[0].real,loop[0].imag],
                      peak_abs_return=size[peak],peak_at_Hz=freq[peak],
                      min_distance_to_critical=distance[closest],closest_at_Hz=freq[closest],
                      sampled_gain_reserve_dB=-20*math.log10(size[peak]) if size[peak]>0 else None,
                      unity_crossings_Hz=unity,low_frequency_plateau=low_flat,
                      high_frequency_rolloff=high_rolloff,native_instability_reported=conflicts,
                      sampled_screen_pass=screen_pass)
        if screen_pass:
            result.update(status='screen_pass',reason='Sampled beta return meets the 10 dB small-gain screen; closed-circuit corroboration pending')
        elif conflicts:
            result.update(status='fail',passed=False,reason='Native Spectre flags instability')
        else:
            result['reason']='Beta small-gain screen unresolved; inspect Nyquist, poles or perturbation'
    except (AttributeError,KeyError,ValueError,TypeError,OverflowError) as err:
        result['reason']=str(err)
    return result
