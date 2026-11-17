#!/usr/bin/env python3
"""Analyze existing noiseless TRAINING only; never launch Spectre or fit FFE."""
import sys
sys.dont_write_bytecode = True
import collections
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil

P = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
R = P/'runs/secondary_cap_training_r7_20261022'
OUT = P/'notes/secondary_hold_mechanism_r8_20261029.json'
SCRIPT_SHA = 'a83a0795f0cfb341889649f9578cfd82dbf7ecf380d2cea799938dd84ce1bbac'
PROTOCOL_SHA = '52589424ae376221ffb488b3e1a92d5ca1e411768eed96825defa8f4cd3af1f0'
CASES = ('noiseless_baseline_r5', 'noiseless_secondary_c25_w2')

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def stats(xs):
    mu = math.fsum(xs)/len(xs)
    return dict(count=len(xs), mean=mu,
                rms=math.sqrt(math.fsum(x*x for x in xs)/len(xs)),
                peak_abs=max(abs(x) for x in xs))

def corr(xs, ys):
    mx, my = math.fsum(xs)/len(xs), math.fsum(ys)/len(ys)
    x, y = [v-mx for v in xs], [v-my for v in ys]
    den = math.sqrt(math.fsum(v*v for v in x)*math.fsum(v*v for v in y))
    return math.fsum(a*b for a,b in zip(x,y))/den if den else None

def main():
    assert os.name == 'posix' and P.resolve() == P
    assert Path(__file__).resolve().parent == P/'scripts'
    assert (P/'.codex_project6_owned').is_file()
    assert not OUT.exists(), 'Diagnostic receipt already exists; inspect instead of overwriting'
    source = P/'scripts/secondary_cap_training_r7_20261022.py'
    assert sha(source) == SCRIPT_SHA and sha(R/'protocol.json') == PROTOCOL_SHA
    spec = importlib.util.spec_from_file_location('r8_training_reader', str(source))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    helper, runner, frozen, backend, ffe, metrics, psf = m.load_verified()
    state = json.loads((R/'status.json').read_text())
    protocol = json.loads((R/'protocol.json').read_text())
    assert state['status'] == 'complete' and protocol['data_seed'] == 2026102202
    assert all(x.startswith('noiseless_') for x in CASES)
    m.assert_unchanged(protocol)
    hashes_before = {str(R/'status.json'):sha(R/'status.json'),
                     str(R/'protocol.json'):sha(R/'protocol.json'),
                     str(m.FROZEN):sha(m.FROZEN)}
    for candidate in m.CANDIDATES:
        q = R/(candidate+'_detectors.json')
        hashes_before[str(q)] = sha(q)
    completed = {x['name']:x for x in state['completed_cases']}
    result = dict(created_utc=datetime.datetime.utcnow().isoformat()+'Z',
        status='existing_training_diagnostic_complete',
        scope='Two existing noiseless r7 training cases, physical aperture indices256..767; no holdout opened, no fitting, no simulation, no hardware mutation.',
        script_sha256=sha(__file__), training_protocol_sha256=PROTOCOL_SHA,
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        free_bytes=shutil.disk_usage(str(P)).free, simulations_started=0,
        full_ADC_verified=False, cases={}, limitations=[
            'Observational waveform differences cannot isolate the causal source of disturbance.',
            'Saved strobe interval about1.116ps;3ps edge brackets include signal dynamics and are not resolved charge-injection measurements.',
            'Buffer nodes are saved only for banks0and7; primary and secondary hold nodes cover all8banks.',
            'Noiseless excludes simulated random transient noise; no SNR/SER improvement is claimed.',
            'Ideal numeric quantization, reset comparators and ideal clocks remain in the historical testbench.'])
    for name in CASES:
        d = R/name
        assert d.resolve() == d and not d.is_symlink()
        s = json.loads((d/'summary.json').read_text())
        prepared = json.loads((d/'prepared.json').read_text())
        assert sha(d/'summary.json') == completed[name]['summary_sha256']
        assert s['run_status']['exit_code'] == 0 and s['noise_seed'] is None
        assert s['training_only'] and not s['independent_holdout']
        assert sha(d/'bench.scs') == prepared['deck_sha256'] == s['deck_sha256']
        assert sha(d/'prepared.json') == state['prepared_sha256'][name]
        raw_path = backend.a._raw_file(d)
        psf.MAX_FILE_BYTES = 512*1024*1024
        raw = psf.parse_file(raw_path)
        assert raw.sha256 == s['raw_transient_sha256']
        records, audit = backend.extract_records(raw, prepared['clock_specification'])
        primary = {x[0]:x for x in records['primary']}
        secondary = {x[0]:x for x in records['secondary']}
        t, values = raw.values[raw.sweep_names[0]], raw.values
        def get(node, when):
            assert t[0] <= when <= t[-1]
            return backend.a.interpolate(t, values[node], when)
        def diff(prefix, when):
            return get(prefix+'p', when)-get(prefix+'m', when)
        rows=[]
        for index in range(256, 768):
            p, q = primary[index], secondary[index]
            bank, close = p[4], p[3]
            master = prepared['clock_specification']['primary_clocks'][bank]
            cycle = int(round((close-master['first_fall_midpoint_s'])/master['period']))
            branch = cycle%8
            sec_close = q[2]-1.5e-12
            before, after = sec_close-1.5e-12, sec_close+1.5e-12
            next_rise = master['first_rise_midpoint_s']+(cycle+1)*master['period']
            assert after < next_rise-master['rise']/2
            hp, hs = 'X_h%d'%bank, 'B%d_h%d'%(bank,branch)
            p_initial, p_late = diff(hp,p[2]), diff(hp,before)
            row=dict(bank=bank,primary_initial_V=p_initial,primary_late_V=p_late,
                primary_hold_change_V=p_late-p_initial,
                primary_final8ps_change_V=p_late-diff(hp,before-8e-12),
                primary_secondary_edge_bracket_change_V=diff(hp,after)-p_late,
                secondary_edge_bracket_change_V=diff(hs,after)-diff(hs,before),
                secondary_late_V=diff(hs,before),
                secondary_close_delay_ps=(sec_close-close)*1e12,
                secondary_to_primary_rise_midpoint_ps=(next_rise-sec_close)*1e12)
            if bank in (0,7):
                bf='B%d_f'%bank
                row.update(buffer_late_V=diff(bf,before),
                    buffer_final8ps_change_V=diff(bf,before)-diff(bf,before-8e-12),
                    secondary_to_buffer_lag_V=diff(hs,before)-diff(bf,before),
                    buffer_primary_close_to_secondary_close_change_V=diff(bf,before)-diff(bf,p[2]))
            rows.append(row)
        assert len(rows)==512 and all(sum(x['bank']==b for x in rows)==64 for b in range(8))
        buf=[x for x in rows if 'buffer_late_V' in x]
        assert len(buf)==128
        fields=[k for k in rows[0] if k.endswith('_V') or k.endswith('_ps')]
        stats_all={k:stats([x[k] for x in rows if k in x]) for k in fields}
        fields_buf=[k for k in buf[0] if (k.startswith('buffer_') or k=='secondary_to_buffer_lag_V')]
        stats_all.update({k:stats([x[k] for x in buf]) for k in fields_buf})
        result['cases'][name]=dict(raw_sha256=raw.sha256,
            summary_sha256=sha(d/'summary.json'),physical_apertures=512,
            buffer_apertures=128,statistics=stats_all,
            per_bank_primary_hold_change_V={str(b):stats([x['primary_hold_change_V'] for x in rows if x['bank']==b]) for b in range(8)},
            final8ps_primary_buffer_change_correlation=corr([x['primary_final8ps_change_V'] for x in buf],[x['buffer_final8ps_change_V'] for x in buf]),
            strobe_period_s=prepared['clock_specification']['strobe_period_s'],
            source_clock_mapping_verified=True)
        assert sha(d/'summary.json') == completed[name]['summary_sha256']
        del raw, records, values, t, primary, secondary, rows, buf
    m.assert_unchanged(protocol)
    assert all(sha(Path(p))==v for p,v in hashes_before.items())
    result['source_state_protocol_frozen_detectors_unchanged']=True
    result['protected_hashes']=hashes_before
    with OUT.open('x') as f:
        json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps(dict(receipt=str(OUT),receipt_sha256=sha(OUT),result=result)))

if __name__ == '__main__':
    main()
