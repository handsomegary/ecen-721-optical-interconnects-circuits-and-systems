"""Screen the replica STB return ratio when Spectre reports no finite GM."""
import math

from diag_metrics import (
    GM_MIN_DB, PM_MIN_DEG, _crossings, _frequency, _interpolate, _margin_scalar,
    _native_frequency, _unit, stb_metrics,
)


RETURN_LIMIT = 10**(-GM_MIN_DB/20)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _gm_missing(margins):
    if margins is None:
        return False
    if 'gainMargin' not in margins.values:
        return True
    rows = margins.values['gainMargin']
    if len(rows)!=1 or _unit(margins,'gainMargin')!='db':
        return False
    value = rows[0]
    return value is None or isinstance(value,float) and math.isnan(value)


def replica20_metrics(trace, margins):
    """Retain finite native margins; otherwise report a sampled-band screen."""
    native = stb_metrics(trace,margins)
    result = dict(native,native_margin_status=native['status'],
                  formal_margin_pass=native['passed'] is True,sampled_screen_pass=False)
    if not _gm_missing(margins):
        return result

    result.update(status='review',passed=None,gain_margin_db=None,
                  screen='replica_no_native_gm_20GHz_sampled_band',
                  critical_point=[1,0],critical_return_limit=RETURN_LIMIT)
    try:
        frequency = result.get('frequency_Hz',[])
        loop = [complex(*value) for value in result.get('loopGain_real_imag',[])]
        complete = (len(frequency)==len(loop) and len(frequency)>=1000 and
                    _unit(trace,'freq')=='hz' and .99<=frequency[0]<=1.01 and
                    frequency[-1]>=19.8e9 and
                    all(0<a<b<=a*10**.0101 for a,b in zip(frequency,frequency[1:])))
        result['extended_frequency_grid'] = complete
        _require(complete,'Incomplete 1 Hz–20 GHz sweep or frequency units')
        _require(not margins.sweep_names,'Native STB margins must be scalar')
        _require(not (trace.header.get('probe') and margins.header.get('probe')) or
                 trace.header['probe']==margins.header['probe'],
                 'STB trace and native margin probes differ')

        state = margins.values.get('stb_state',[])
        _require(len(state)==1 and isinstance(state[0],str),'Native stability state unavailable')
        result['native_state'] = state[0]
        state_text = state[0].lower()
        _require('the circuit is stable' in state_text and 'not stable' not in state_text and
                 'unstable' not in state_text,'Native Spectre state does not confirm stability')
        _require('both found' not in state_text,'Native state reports a GM that is missing')

        pm = _margin_scalar(margins,'phaseMargin',{'deg':1.0,'rad':180/math.pi})
        result['phase_margin_deg'] = pm
        absolute_return = list(map(abs,loop))
        db_return = [20*math.log10(value) if value else -6000. for value in absolute_return]
        unity = _crossings(db_return)
        _require(len(unity)==1 and absolute_return[0]>1>absolute_return[-1],
                 'Expected one downward sampled unity crossing')
        unity_point = unity[0]
        unity_frequency = _frequency(frequency,unity_point)
        native_frequency = _native_frequency(margins,'phaseMarginFreq',frequency,unity_point)
        _require(native_frequency is not None,'Native phase-margin frequency missing')
        left,right,fraction = unity_point
        first_phase = math.degrees(math.atan2(loop[left].imag,loop[left].real))
        second_phase = math.degrees(math.atan2(loop[right].imag,loop[right].real))
        delta = (second_phase-first_phase+180)%360-180
        sampled_pm = (first_phase+delta*fraction+180)%360-180
        result.update(phase_margin_frequency_Hz=native_frequency,unity_crossings_Hz=[unity_frequency],
                      sampled_phase_margin_deg=sampled_pm)
        _require(pm>=PM_MIN_DEG and abs(pm-sampled_pm)<=2,
                 'Native PM misses the threshold or disagrees with the sampled phase')

        contacts = []
        for point in _crossings([value.imag for value in loop]):
            contact = _interpolate(loop,point).real
            if contact>0:
                contacts.append({'frequency_Hz':_frequency(frequency,point),'absolute_return':contact})
        low = [value for f,value in zip(frequency,loop) if f<=10]
        low_flat = (loop[0].real<0 and abs(loop[0].imag)<=.1*absolute_return[0] and
                    max(abs(value-loop[0]) for value in low)<=.02*absolute_return[0])
        last_octave = max(value for f,value in zip(frequency,absolute_return) if f>=frequency[-1]/2)
        tail = (last_octave<=RETURN_LIMIT and
                (last_octave<=.01 or absolute_return[-1]<=.9*last_octave))
        last_above = max(i for i,value in enumerate(absolute_return) if value>RETURN_LIMIT)
        suffix_start = last_above+1
        result.update(low_frequency_return=[loop[0].real,loop[0].imag],low_frequency_plateau=low_flat,
                      last_octave_peak_abs_return=last_octave,end_abs_return=absolute_return[-1],
                      end_return=[loop[-1].real,loop[-1].imag],high_frequency_rolloff=tail,
                      critical_ray_contacts=contacts,
                      persistent_low_return_from_Hz=frequency[suffix_start] if suffix_start<len(frequency) else None,
                      persistent_low_return_samples=len(frequency)-suffix_start)
        _require(not any(row['absolute_return']>RETURN_LIMIT for row in contacts),
                 'Sampled positive-real ray contact exceeds the return threshold')
        _require(low_flat and tail and suffix_start<len(frequency) and
                 unity_frequency<frequency[suffix_start]<=frequency[-1]/2,
                 'Low-frequency plateau or persistent high-frequency decay is unresolved')
        result.update(status='screen_pass',sampled_screen_pass=True,
                      reason='Native stable state and PM with a bounded sampled return; GM remains undefined')
    except (AttributeError,KeyError,TypeError,ValueError,OverflowError) as error:
        result['reason'] = str(error)
    return result
