"""Foreground deskew using shared-timebase P/N pilot phasors."""
import argparse
import cmath
import hashlib
import json
import math
from pathlib import Path

FREQUENCIES_HZ = tuple(7e9 * n for n in range(1, 8))
FIT_LIMIT_PS = 12.0


def fit(phasors):
    if set(phasors) != {str(int(f)) for f in FREQUENCIES_HZ}:
        raise ValueError('Expected all seven pilot frequencies')
    ratios, amplitudes = [], []
    for f in FREQUENCIES_HZ:
        row = phasors[str(int(f))]
        p, n = complex(*row['p']), -complex(*row['n'])
        if not (math.isfinite(abs(p)) and math.isfinite(abs(n)) and min(abs(p), abs(n)) >= 20e-6):
            raise ValueError('Missing or weak branch pilot')
        ratios.append((p / n) / abs(p / n))
        amplitudes.append(20 * math.log10(abs(p / n)))
    phase = [cmath.phase(v) for v in ratios]
    for i in range(1, len(phase)):
        phase[i] = phase[i-1] + math.remainder(phase[i] - phase[i-1], 2 * math.pi)
    f_ps = [f * 1e-12 for f in FREQUENCIES_HZ]
    f_mean, p_mean = sum(f_ps)/len(phase), sum(phase)/len(phase)
    slope = sum((f-f_mean)*(p-p_mean) for f,p in zip(f_ps,phase)) / sum(
        (f-f_mean)**2 for f in f_ps)
    delay_ps = -slope / (2 * math.pi)
    residual = [math.remainder(p + 2*math.pi*f*delay_ps, 2*math.pi)
                for f,p in zip(f_ps,phase)]
    if abs(delay_ps) > FIT_LIMIT_PS:
        raise ValueError('Pilot delay outside unambiguous range')
    return {'estimated_residual_ps': delay_ps, 'phase_error_rad': residual,
            'max_phase_equivalent_residual_ps': max(abs(p)/(2*math.pi*f)
                                                    for f,p in zip(f_ps,residual)),
            'gain_imbalance_dB': amplitudes}


def score(window):
    return max(abs(window['estimated_residual_ps']), window['max_phase_equivalent_residual_ps'])


def select(observations, residual_budget_ps, repeat_budget_ps):
    """Rank training pilot rows only. Evaluate the chosen row on a second window."""
    if not (math.isfinite(residual_budget_ps) and residual_budget_ps > 0 and
            math.isfinite(repeat_budget_ps) and repeat_budget_ps > 0):
        raise ValueError('Finite positive engineering budgets required')
    choices, seen = [], set()
    for item in observations:
        if set(item) != {'p_code', 'n_code', 'train', 'verify'}:
            raise ValueError('Controller input must contain only codes and pilot observations')
        p, n = item['p_code'], item['n_code']
        if any(type(k) is not int or not 0 <= k <= 63 for k in (p,n)) or (p,n) in seen:
            raise ValueError('Invalid or repeated code pair')
        seen.add((p,n))
        try:
            training = fit(item['train'])
        except (ValueError, TypeError, KeyError):
            continue
        choices.append((score(training), p, n, training, item['verify']))
    if not choices:
        return {'status': 'NO_LOCK', 'reason': 'No usable pilot observations'}
    _, p, n, training, verification_data = min(choices, key=lambda row: row[:3])
    try:
        verification = fit(verification_data)
    except (ValueError, TypeError, KeyError) as error:
        return {'status': 'NO_LOCK', 'p_code': p, 'n_code': n, 'reason': str(error)}
    difference = abs(training['estimated_residual_ps'] - verification['estimated_residual_ps'])
    locked = (max(score(training), score(verification)) <= residual_budget_ps and
              difference <= repeat_budget_ps)
    return {'status': 'LOCK' if locked else 'NO_LOCK',
            'p_code': p, 'n_code': n, 'train_fit': training, 'verification_fit': verification,
            'window_repeatability_ps': difference, 'usable_code_pairs': len(choices),
            'gate_status': 'PROPOSED_ENGINEERING_SCREEN',
            'residual_budget_ps': residual_budget_ps, 'repeat_budget_ps': repeat_budget_ps}


def read_pilot(path):
    document = json.loads(path.read_bytes())
    if document.get('format') != 'pn_comp_blind_observations_v1':
        raise ValueError('Wrong observation format')
    return document


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--observations', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--residual-ps', type=float, required=True)
    p.add_argument('--repeat-ps', type=float, required=True)
    a = p.parse_args()
    doc = read_pilot(a.observations)
    result = select(doc['observations'], a.residual_ps, a.repeat_ps)
    result.update(format='pn_comp_code_selection_v1',
                  observation_sha256=hashlib.sha256(a.observations.read_bytes()).hexdigest())
    with a.output.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write('\n')
