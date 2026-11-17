"""Read-only retained-waveform timing audit: 761321 (1.75 GS/s) vs 761279 (0.926 GS/s).

Uses each case's case.json event times, measurements.json read classification, and the
admitted PSF parser (gm_switch64_psf.parse_selected via the fast package import chain).
Writes one compact JSON. Never modifies inputs.
"""
import hashlib, json, os, sys
from bisect import bisect_left, bisect_right

sys.path.insert(0, os.environ['PAM4_SAR7_FAST_PACKAGE'])
import sar7_fast  # noqa: E402
review = sar7_fast.offset.base.review
parse_selected = review.parse_selected

LSB = 0.1 / 128  # 100 mV / 128
CASES = {
    'fast_761321': dict(dir=os.path.expanduser('~/ecen720_28nm/runs/pam4_sar7_fast_pilot_20261116.bNXKcy/sar7_12_tt_175gs_matched_q'),
                        summary=os.path.expanduser('~/ecen720_28nm/runs/pam4_sar7_fast_pilot_20261116.bNXKcy/sar7_fast_summary.json'),
                        sha=dict(summary='a5432be72f2c293c8577bdb3c5d0f886e4765d7c61852ba93a0a69c164f9ae5a',
                                 measurements='935150c70665c0effde4c63cf47fcac6ffafc2412706a096420d7143c75c9cb5',
                                 tran='6d6ab5f3f5052bc30e227772310ff35423067a81dfd580ee0a232ada9bab35b7')),
    'slow_761279': dict(dir=os.path.expanduser('~/ecen720_28nm/runs/pam4_sar7_offset_pilot_20261116.oGLb07/sar7_10_tt_matched_q_load'),
                        summary=os.path.expanduser('~/ecen720_28nm/runs/pam4_sar7_offset_pilot_20261116.oGLb07/sar7_10_tt_matched_q_load/sar7_offset_pilot_summary.json'),
                        sha=dict(summary='84b051d79c71979637416674aeb17b851104b199e544d9035870f8116f761a0a',
                                 measurements='b3a514de93049c737b9c1c7c18cafda99be78373e0638255f8127ea8e5af8394',
                                 tran='d2e900facf2c569801cfb61e0794e0420f7b5cf62129f2ab98cdc1fe1131bc00')),
}
SAMPLE_BITS = (6, 5, 4, 3)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for blk in iter(lambda: f.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def interp(t, y, at):
    i = bisect_left(t, at)
    if i < len(t) and t[i] == at:
        return y[i]
    if i == 0 or i >= len(t):
        return None
    w = (at - t[i - 1]) / (t[i] - t[i - 1])
    return y[i - 1] + w * (y[i] - y[i - 1])


def crossings(t, y, thr, lo, hi, direction=None):
    out = []
    a, b = bisect_left(t, lo), bisect_right(t, hi)
    for k in range(max(a, 1), b):
        y0, y1 = y[k - 1] - thr, y[k] - thr
        if y0 == y1 or (y0 < 0) == (y1 < 0) and y1 != 0:
            continue
        if y0 == 0:
            continue
        rising = y1 > y0
        if direction == 'rise' and not rising:
            continue
        if direction == 'fall' and rising:
            continue
        tc = t[k - 1] + (t[k] - t[k - 1]) * (-y0) / (y1 - y0)
        out.append((tc, 'rise' if rising else 'fall'))
    return out


def classify(h, l, vdd):
    if h >= .8 * vdd and l <= .2 * vdd:
        return 1
    if l >= .8 * vdd and h <= .2 * vdd:
        return 0
    return None


def stable_from(t, hv, lv, lo, hi, vdd):
    """Final logic at hi, and earliest saved sample after lo that keeps it through hi."""
    fh, fl = interp(t, hv, hi), interp(t, lv, hi)
    final = classify(fh, fl, vdd)
    if final is None:
        return None, None
    first, last = bisect_left(t, lo), bisect_right(t, hi)
    stable = None
    for k in range(last - 1, first - 1, -1):
        if classify(hv[k], lv[k], vdd) != final:
            break
        stable = t[k]
    return final, stable


def ps(x):
    return None if x is None else round(x * 1e12, 3)


def r(x, n=6):
    return None if x is None else round(x, n)


def load(name, spec):
    d = spec['dir']
    got = dict(summary=sha(spec['summary']), measurements=sha(d + '/measurements.json'),
               tran=sha(d + '/raw/tranResponse.tran.tran'))
    if got != spec['sha']:
        raise SystemExit(f'SHA mismatch for {name}: {got}')
    case = json.load(open(d + '/case.json'))
    meas = json.load(open(d + '/measurements.json'))
    wave = case['wave']
    req = {'time', *wave['saved_signals']}
    data = parse_selected(d + '/raw/tranResponse.tran.tran', req)
    if data.sha256 != spec['sha']['tran']:
        raise SystemExit('parser SHA mismatch')
    vals = {k: list(v) for k, v in data.values.items()}
    return case, meas, wave, vals, got


def diff_sig(vals, p, n):
    return [a - b for a, b in zip(vals[p], vals[n])]


def analyze(name, spec):
    case, meas, wave, vals, got = load(name, spec)
    t = vals['time']
    vdd = wave['vdd_V']
    half = vdd / 2
    D = {
        'dac_mp_mn': diff_sig(vals, 'mp', 'mn'),
        'low_lp_ln': diff_sig(vals, 'lp', 'ln'),
        'sense_p_n': diff_sig(vals, 'sensep', 'sensen'),
    }
    for b in range(7):
        D[f'xy{b}'] = diff_sig(vals, f'XCMP{b}.x', f'XCMP{b}.y')
        D[f'q{b}'] = diff_sig(vals, f'q{b}p', f'q{b}n')
    convs = []
    for cv, mc in zip(wave['conversions'], meas['conversions']):
        assert cv['index'] == mc['index']
        trials = cv['trials']
        tr_meas = {x['bit']: x for x in mc['trial_results']}
        reg_bits = {}
        for k, (p, n) in enumerate(cv['code_pairs']):
            reg_bits[6 - k] = classify(interp(t, vals[p], cv['end_s']), interp(t, vals[n], cv['end_s']), vdd)
        rows = []
        for j, tr in enumerate(trials):
            b = tr['bit']
            m = tr_meas[b]
            L, P, C, R, REL = (tr[k] for k in ('launch_s', 'pre_s', 'compare_s', 'read_s', 'trial_release_s'))
            prev = trials[j - 1] if j else None
            lo_win = prev['read_s'] if prev else cv['sample_s']
            # read classification / margin (from original measurements)
            dec = m['decision']
            sd = m['stable_rail_delay_s']
            if dec is None:
                rclass, margin, mstat = 'unresolved', None, 'n/a'
            elif sd is None:
                rclass, margin, mstat = f'resolved_{dec}', None, 'unproven'
            else:
                rclass, margin, mstat = f'resolved_{dec}', ps(m['compare_to_read_s'] - sd), 'evidence'
            row = dict(bit=b, read_class=rclass, decision=dec, expected_bit=m['expected_bit'],
                       pre_clock_complementary=m['comparator_already_complementary_before_clock'],
                       read_margin_ps=margin, read_margin_status=mstat,
                       event_ps=dict(launch=ps(L), pre=ps(P), compare=ps(C), read=ps(R), release=ps(REL)))
            # previous trial release (measured) and previous registered rail
            if prev:
                pb = prev['bit']
                fall = crossings(t, vals[f'trial{pb}'], half, prev['read_s'], C, 'fall')
                row['prev_trial_release_meas_ps'] = ps(fall[0][0]) if fall else None
                row['prev_trial_release_nominal_ps'] = ps(prev['trial_release_s'])
                pp, pn = cv['code_pairs'][6 - pb]
                fin, st = stable_from(t, vals[pp], vals[pn], prev['compare_s'], C, vdd)
                row['prev_registered_at_compare'] = fin
                row['prev_registered_rail_ps'] = ps(st)
                row['prev_registered_rail_before_launch'] = None if st is None else st <= L
            else:
                row['prev_trial_release_meas_ps'] = None
                row['prev_registered_rail_ps'] = None
                row['sample_ps'] = ps(cv['sample_s'])
            rise = crossings(t, vals[f'trial{b}'], half, lo_win, R, 'rise')
            row['trial_rise_meas_ps'] = ps(rise[0][0]) if rise else None
            crise = crossings(t, vals[f'clk{b}'], half, L - 5e-12, R, 'rise')
            row['compare_rise_meas_ps'] = ps(crise[0][0]) if crise else None
            if b in SAMPLE_BITS:
                pts = [('L+5', L + 5e-12), ('L+10', L + 10e-12), ('L+15', L + 15e-12),
                       ('C-6', C - 6e-12), ('C-3', C - 3e-12), ('C-1', C - 1e-12),
                       ('C+1', C + 1e-12), ('C+3', C + 3e-12), ('C+6', C + 6e-12), ('C+12', C + 12e-12),
                       ('read', R)]
                pts = [(lab, at) for lab, at in pts if L <= at <= REL]
                sig = {'dac': D['dac_mp_mn'], 'low': D['low_lp_ln'], 'sense': D['sense_p_n'],
                       'xy': D[f'xy{b}'], 'q': D[f'q{b}']}
                samples = {}
                for lab, at in pts:
                    s = {k: r(interp(t, v, at)) for k, v in sig.items()}
                    s['x'] = r(interp(t, vals[f'XCMP{b}.x'], at))
                    s['y'] = r(interp(t, vals[f'XCMP{b}.y'], at))
                    s['qp'] = r(interp(t, vals[f'q{b}p'], at))
                    s['qn'] = r(interp(t, vals[f'q{b}n'], at))
                    s['t_ps'] = ps(at)
                    for k in ('dac', 'low', 'sense'):
                        s[k + '_LSB'] = r(s[k] / LSB, 3)
                    samples[lab] = s
                row['samples'] = samples
                flips = {}
                for k, v in sig.items():
                    xs = crossings(t, v, 0.0, lo_win, REL)
                    flips[k] = [dict(t_ps=ps(tc), dir=dr, rel_compare_ps=ps(tc - C), rel_read_ps=ps(tc - R),
                                     rel_release_ps=ps(tc - REL), rel_launch_ps=ps(tc - L)) for tc, dr in xs[:12]]
                    if len(xs) > 12:
                        flips[k].append(dict(truncated=len(xs)))
                row['sign_flips'] = flips
                # derived features
                g = lambda lab, k: samples.get(lab, {}).get(k)
                c6, c1 = g('C-6', 'dac'), g('C-1', 'dac')
                row['dac_slope_C6_to_C1_LSB_per_ps'] = None if None in (c6, c1) else r((c1 - c6) / LSB / 5, 4)
                row['dac_C1_LSB'] = None if c1 is None else r(c1 / LSB, 3)
                for lab in ('C+3', 'C+6', 'C+12', 'read'):
                    v = g(lab, 'dac')
                    row[f'dac_jump_C1_to_{lab}_LSB'] = None if None in (v, c1) else r((v - c1) / LSB, 3)
                # direct DAC trial-step timing (saved samples only, no extrapolation)
                dv = D['dac_mp_mn']
                dL, dR = interp(t, dv, L), interp(t, dv, R)
                step = dR - dL
                row['dac_at_launch_LSB'] = r(dL / LSB, 3)
                row['dac_step_launch_to_read_LSB'] = r(step / LSB, 3)
                row['trial_step_fraction_at_C1'] = r((c1 - dL) / step, 3) if c1 is not None and abs(step) > 2 * LSB else None
                a, bb = bisect_left(t, L), bisect_right(t, R)
                mv = next((t[k] for k in range(a, bb) if abs(dv[k] - dL) > LSB), None)
                row['dac_first_move_1LSB_after_launch_ps'] = ps(None if mv is None else mv - L)
                st = None
                for k in range(bb - 1, a - 1, -1):
                    if abs(dv[k] - dR) > LSB:
                        break
                    st = t[k]
                row['dac_within_1LSB_of_read_after_launch_ps'] = ps(None if st is None else st - L)
                row['dac_within_1LSB_of_read_before_compare'] = None if st is None else st <= C
                xs = vals[f'XCMP{b}.x']; ys = vals[f'XCMP{b}.y']
                reg = next((t[k] for k in range(bisect_left(t, C), bb) if abs(xs[k] - ys[k]) > 0.1 * vdd), None)
                row['xy_regen_10pct_after_compare_ps'] = ps(None if reg is None else reg - C)
                row['xy_at_read_V'] = g('read', 'xy')
                row['q_at_read_V'] = g('read', 'q')
                row['q_rail_at_read'] = classify(g('read', 'qp'), g('read', 'qn'), vdd)
            rows.append(row)
        convs.append(dict(index=cv['index'], expected=cv['expected_code'],
                          comparator_code=mc['observed_comparator_code'], registered_code=mc['observed_registered_code'],
                          registered_bits={str(k): v for k, v in reg_bits.items()},
                          sample_ps=ps(cv['sample_s']), end_ps=ps(cv['end_s']), trials=rows))
    return dict(case=name, input_sha256=got, parser='gm_switch64_psf.parse_selected (pkg_f)',
                period_ps=ps(wave['period_s']), lsb_V=LSB, vdd_V=vdd, conversions=convs)


def compare(fast, slow):
    out = []
    for fc, sc in zip(fast['conversions'], slow['conversions']):
        assert fc['expected'] == sc['expected']
        fd = {x['bit']: x for x in fc['trials']}
        sd = {x['bit']: x for x in sc['trials']}
        failed = fc['registered_code'] != fc['expected'] or fc['comparator_code'] is None
        first_cmp_div = next((b for b in range(6, -1, -1) if fd[b]['decision'] != sd[b]['decision']), None)
        first_reg_div = next((b for b in range(6, -1, -1)
                              if fc['registered_bits'][str(b)] != sc['registered_bits'][str(b)]), None)
        bits = []
        for b in SAMPLE_BITS:
            hist_same = all(fd[k]['decision'] == sd[k]['decision'] for k in range(6, b, -1))
            f, s = fd[b], sd[b]
            item = dict(bit=b, same_history=hist_same,
                        fast_decision=f['decision'], slow_decision=s['decision'],
                        fast_dac_C1_LSB=f.get('dac_C1_LSB'), slow_dac_C1_LSB=s.get('dac_C1_LSB'),
                        fast_slope=f.get('dac_slope_C6_to_C1_LSB_per_ps'), slow_slope=s.get('dac_slope_C6_to_C1_LSB_per_ps'),
                        fast_jump_C1_read=f.get('dac_jump_C1_to_read_LSB'), slow_jump_C1_read=s.get('dac_jump_C1_to_read_LSB'),
                        fast_jump_C1_C3=f.get('dac_jump_C1_to_C+3_LSB'), slow_jump_C1_C3=s.get('dac_jump_C1_to_C+3_LSB'),
                        fast_margin_ps=f['read_margin_ps'], slow_margin_ps=s['read_margin_ps'],
                        fast_q_rail_at_read=f.get('q_rail_at_read'), fast_xy_at_read_V=f.get('xy_at_read_V'),
                        fast_prev_reg_rail_ps=f.get('prev_registered_rail_ps'), fast_launch_ps=f['event_ps']['launch'],
                        fast_compare_ps=f['event_ps']['compare'])
            for tag, src in (('fast', f), ('slow', s)):
                for k in ('trial_step_fraction_at_C1', 'dac_first_move_1LSB_after_launch_ps',
                          'dac_within_1LSB_of_read_after_launch_ps', 'dac_within_1LSB_of_read_before_compare',
                          'xy_regen_10pct_after_compare_ps', 'dac_step_launch_to_read_LSB', 'dac_at_launch_LSB'):
                    item[f'{tag}_{k}'] = src.get(k)
            if hist_same and None not in (item['fast_dac_C1_LSB'], item['slow_dac_C1_LSB']):
                item['delta_C1_fast_minus_slow_LSB'] = r(item['fast_dac_C1_LSB'] - item['slow_dac_C1_LSB'], 3)
                item['sign_C1_matches_slow'] = (item['fast_dac_C1_LSB'] > 0) == (item['slow_dac_C1_LSB'] > 0)
            bits.append(item)
        out.append(dict(index=fc['index'], expected=fc['expected'], fast_cmp=fc['comparator_code'],
                        fast_reg=fc['registered_code'], slow_cmp=sc['comparator_code'], slow_reg=sc['registered_code'],
                        fast_failed=failed, first_comparator_divergence_bit=first_cmp_div,
                        first_registered_divergence_bit=first_reg_div, bits=bits))
    return out


def main(outpath):
    res = {k: analyze(k, v) for k, v in CASES.items()}
    res['comparison'] = compare(res['fast_761321'], res['slow_761279'])
    res['notes'] = ['LSB = 100 mV/128 = 0.78125 mV', 'sign: decision 1 <-> mp-mn > 0 at pre (original scorer)',
                    'read margin = compare_to_read - stable_rail_delay from original measurements.json',
                    'sample points outside [launch, trial_release] dropped', 'no extrapolation; missing traces -> null']
    txt = json.dumps(res, separators=(',', ':'))
    open(outpath, 'w').write(txt)
    print(outpath, hashlib.sha256(txt.encode()).hexdigest(), len(txt))


if __name__ == '__main__':
    main(sys.argv[1])
