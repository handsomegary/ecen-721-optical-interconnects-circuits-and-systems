#!/usr/bin/env python3
"""Prepare reviewable stimulus-only clones. No simulator, scheduler or deletion.

Python 3.6+. Baseline platform adaptation changes only one reversible PDK
prefix. Approved experiment overlays are recorded separately from migration.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

UI = 1.0 / 112e9
NUMBER = re.compile(r'^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Z]*)$')
SCALE = {'': 1., 'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12, 'f': 1e-15, 'a': 1e-18,
         'k': 1e3, 'K': 1e3, 'M': 1e6, 'G': 1e9}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def need(ok, message):
    if not ok:
        raise ValueError(message)


def number(token):
    if isinstance(token, bytes):
        token = token.decode('ascii')
    m = NUMBER.match(token)
    need(m is not None and m.group(2) in SCALE, 'Only literal finite Spectre numbers are admitted')
    value = float(m.group(1)) * SCALE[m.group(2)]
    need(math.isfinite(value), 'Non-finite value')
    return value


def pwl_block(data, name):
    pattern = rb'(?m)^' + name.encode('ascii') + rb'[ \t]+\([^\r\n]*\)[ \t]+vsource[ \t]+type=pwl[ \t]+wave=\['
    matches = list(re.finditer(pattern, data))
    need(len(matches) == 1, 'Expected one literal PWL source ' + name)
    begin = matches[0].end()
    end = data.find(b']', begin)
    need(end >= begin and b'[' not in data[begin:end], 'Unclosed/nested PWL')
    body = data[begin:end]
    tokens = list(re.finditer(rb'[^\s\\]+', body))
    need(len(tokens) >= 4 and len(tokens) % 2 == 0, 'Malformed PWL time/value pairs')
    values = [number(t.group()) for t in tokens]
    times = values[::2]
    need(times[0] == 0. and all(b > a for a, b in zip(times, times[1:])), 'PWL time axis must start at zero and increase')
    return begin, end, body, tokens, times, values[1::2]


def shifted_body(block, delay):
    begin, end, body, tokens, times, values = block
    if delay == 0.:
        return body
    moved = [0.] + [t + delay for t in times[1:]]
    need(all(t >= 0. for t in moved) and all(b > a for a, b in zip(moved, moved[1:])),
         'Signed skew crosses the source prehistory guard; do not silently clip or change mean latency')
    for j in reversed(range(1, len(times))):
        token = tokens[2 * j]
        body = body[:token.start()] + ('%.17g' % moved[j]).encode('ascii') + body[token.end():]
    return body


def tone_body(case, polarity):
    frequency = float(case['frequency_Hz'])
    amplitude = float(case['tone_peak_V'])
    need(math.isfinite(frequency) and 0 < frequency <= 56e9, 'Tone frequency outside predeclared band')
    need(math.isfinite(amplitude) and 0 < amplitude <= .001, 'Tone amplitude needs new approval')
    delta = float(case['delta_ui']) * UI
    delay = delta / 2 if polarity == 1 else -delta / 2
    start, end = case['measurement_window_s']
    need(start >= .8e-9 and end > start and (end - start) * frequency >= 19.999999,
         'Tone window must exclude settling and contain at least20 cycles')
    stop = end + .1e-9
    dt = 1. / (frequency * int(case['pwl_samples_per_tone_cycle']))
    need(int(case['pwl_samples_per_tone_cycle']) >= 128, 'Tone PWL discretization too coarse')
    count = int(math.ceil(stop / dt))
    sign = polarity if case['kind'] == 'tone_dm' else 1
    leg_amplitude = amplitude / 2 if case['kind'] == 'tone_dm' else amplitude
    points = []
    for i in range(count + 1):
        t = min(i * dt, stop)
        value = sign * leg_amplitude * math.sin(2 * math.pi * frequency * (t - delay))
        points.append(' %.17g %.17g \\\n' % (t, value))
    return (' \\\n' + ''.join(points) + ' ').encode('ascii')


def render_deck(source_bytes, admission, case):
    """Pure render; preserve every non-approved source byte, including clocks."""
    kind = case['kind']
    need(kind in ('pam4_noiseless', 'pam4_noise', 'tone_dm', 'tone_cm'), 'Unknown case kind')
    delta = float(case['delta_ui'])
    need(math.isfinite(delta) and abs(delta) <= .5 + 1e-14, 'Skew exceeds ±0.5UI')
    source_kind = 'noise' if kind == 'pam4_noise' else 'noiseless'
    source = admission['source_decks'][source_kind]
    need(sha(source_bytes) == source['sha256'], 'Source input changed after admission')
    old = admission['original_model_root'].encode('utf-8')
    new = admission['model_root'].encode('utf-8')
    need(old != new and b'\n' not in new and b'"' not in new, 'Unsafe/non-distinct model root')
    if sha(source_bytes) == source['original_vm_sha256']:
        need(source_bytes.count(old) == 1, 'Require one original PDK prefix')
        original = source_bytes
    else:
        need(source_bytes.count(new) == 1, 'Already-rebased input needs exactly one private prefix')
        original = source_bytes.replace(new, old)
        need(sha(original) == source['original_vm_sha256'], 'Adapted input was not path-only')
    baseline = original.replace(old, new)
    need(baseline.count(new) == 1 and baseline.replace(new, old) == original, 'PDK adaptation not reversible')
    need(not re.search(rb'(?mi)^\s*(?:ahdl_include|include)\s+"(?!' + re.escape(new) + rb')', baseline),
         'Unexpected non-admitted source/model include')
    p, n = pwl_block(baseline, 'PAM4Vp'), pwl_block(baseline, 'PAM4Vm')
    need(len(p[4]) == len(n[4]) and p[4] == n[4], 'Baseline P/N source axes differ')
    need(all(abs(a + b) < 1e-12 for a, b in zip(p[5], n[5])), 'Baseline source is not a matched differential PAM4 pair')
    analysis = re.findall(rb'(?mi)^tranResponse[ \t]+tran[^\r\n]*', baseline)
    need(len(analysis) == 1, 'Expected one original transient analysis')
    stop_token = re.search(rb'\bstop=([^\s\\]+)', analysis[0])
    need(stop_token is not None, 'Transient stop is not literal')
    stop_s = number(stop_token.group(1))
    if kind.startswith('tone_'):
        need(case['measurement_window_s'][1] + .1e-9 <= stop_s, 'Tone window exceeds unchanged native STOP')
    else:
        need(p[4][-1] + abs(delta) * UI / 2 < stop_s, 'Signed source shift exceeds unchanged native STOP')
    edits = []
    for block, sign in ((p, 1), (n, -1)):
        body = tone_body(case, sign) if kind.startswith('tone_') else shifted_body(block, sign * delta * UI / 2)
        edits.append((block[0], block[1], body))
    changed = baseline
    for begin, end, body in sorted(edits, reverse=True):
        changed = changed[:begin] + body + changed[end:]
    if kind == 'pam4_noise':
        seed = case['noise_seed']
        need(type(seed) is int and 0 < seed < 2**31, 'Invalid noise seed')
        seeds = list(re.finditer(rb'\bnoiseseed=([0-9]+)', changed))
        need(len(seeds) == 1 and int(seeds[0].group(1)) == 173, 'Expected original r5 noise173 deck')
        m = seeds[0]
        changed = changed[:m.start(1)] + str(seed).encode('ascii') + changed[m.end(1):]
    else:
        need(not re.search(rb'\bnoisefmax=', changed), 'Quiet/tone baseline unexpectedly enables transient noise')
    if delta == 0. and kind == 'pam4_noiseless':
        need(changed == baseline, 'Zero-skew quiet control must be exactly the path-only input')
    corner = case.get('pvt_corner')
    if corner is True:
        from pvt.render_transient import apply_pvt
        need(kind == 'pam4_noiseless' and delta == 0., 'PVT transient uses original quiet zero skew')
        changed = apply_pvt(changed,case,admission['model_root'])
    metadata = {'source_kind': source_kind, 'source_deck_sha256': source['sha256'],
                'normalized_original_vm_sha256': source['original_vm_sha256'],
                'path_only_baseline_sha256': sha(baseline), 'staged_deck_sha256': sha(changed),
                'mean_input_delay_s': 0., 'clock_shift_s': 0., 'p_delay_s': delta * UI / 2,
                'n_delay_s': -delta * UI / 2, 'initial_PWL_t0_anchor_preserved': not kind.startswith('tone_'),
                'source_guard_s': p[4][1], 'baseline_path_rebase_reversible': True,
                'stop_s': stop_s,
                'experiment_overlay_separate_from_migration': True,
                'allowed_overlay': 'Two P/N PWL time axes only; optional noise seed only' if not kind.startswith('tone_')
                                   else 'Two small-signal PWL tone sources only; unchanged circuit, clocks and transient controls',
                'stop_save_geometry_and_clock_bytes_unchanged': True,
                'no_new_physical_compensator': True}
    if corner is True:
        metadata['allowed_overlay'] = 'PVT model section, temperature and AFE rail only; fixed r5 stimulus and analysis'
        metadata['transient_corner'] = {name:case[name] for name in ('process','temperature_C','vdd_V')}
    return changed, metadata


def verify_stage(admission_path, run_dir):
    from admit import read_admission
    admission = read_admission(admission_path, verify=True)
    root = Path(run_dir).resolve()
    profile = load(root / 'profile.json')
    need(sha(Path(admission_path).read_bytes()) == profile['admission_sha256'], 'Admission changed')
    source = admission['source_decks'][profile['source_kind']]
    rendered, meta = render_deck(Path(source['path']).read_bytes(), admission, profile['case'])
    need(rendered == (root / 'bench.scs').read_bytes(), 'Deck differs from the admitted precise overlay')
    need(all(profile.get(k) == v for k, v in meta.items()), 'Staged provenance changed')
    if profile['case'].get('pvt_corner') is True:
        from pvt.render_transient import stage_corner
        wrapper, proof = stage_corner(profile['case']['process'],admission['model_root'])
        need((root/'la5_foundry_corners.scs').read_bytes()==wrapper and
             load(root/'corner_preflight.json')==proof,'PVT closure or staged corner include changed')
    return profile


def prepare(admission_path, plan_path, case_index, output):
    from admit import read_admission
    admission = read_admission(admission_path, verify=True)
    plan = load(plan_path)
    need(type(case_index) is int and 0 <= case_index < len(plan['cases']), 'Bad case index')
    case = plan['cases'][case_index]
    source_kind = 'noise' if case['kind'] == 'pam4_noise' else 'noiseless'
    staged, meta = render_deck(Path(admission['source_decks'][source_kind]['path']).read_bytes(), admission, case)
    root = Path(output).resolve()
    need(not root.exists() and root.parent.is_dir(), 'New independent case directory required')
    root.mkdir()
    (root / 'bench.scs').write_bytes(staged)
    if case.get('pvt_corner') is True:
        from pvt.render_transient import stage_corner
        wrapper, proof = stage_corner(case['process'],admission['model_root'])
        (root/'la5_foundry_corners.scs').write_bytes(wrapper)
        (root/'corner_preflight.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    profile = dict(meta, format='pn_skew_staged_r5_v1', case=case, case_index=case_index,
                   admission_sha256=sha(Path(admission_path).read_bytes()),
                   plan_sha256=sha(Path(plan_path).read_bytes()),
                   source_deck_path=admission['source_decks'][source_kind]['path'])
    (root / 'profile.json').write_bytes((json.dumps(profile, indent=2, sort_keys=True, allow_nan=False) + '\n').encode())
    (root / '.pn_skew_owned').write_text('new_Olympus_case_only\n')
    verify_stage(admission_path, root)
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admission', required=True)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--case-index', type=int, required=True)
    parser.add_argument('--output', required=True)
    a = parser.parse_args()
    result = prepare(a.admission, a.plan, a.case_index, a.output)
    print(json.dumps({'prepared_only': True, 'case_id': result['case']['case_id'], 'staged_deck_sha256': result['staged_deck_sha256']}))


if __name__ == '__main__':
    main()
