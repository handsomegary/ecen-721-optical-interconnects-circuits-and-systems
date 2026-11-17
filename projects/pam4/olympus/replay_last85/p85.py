#!/usr/bin/env python3
"""Replay of the last 85 historical PAM4 (project6) runs on Olympus: 79 deterministic cases (exact replay against the
archived measurements) + 6 transient-noise cases (range method, original seed + 301..319, 20 runs each).

Decks: original VM bench.scs bytes; only reversible root-prefix substitutions (foundry model root -> private VM model
copy; LA5 project root -> mirrored la5_foundry_corners.scs). Each rendered deck's literal include closure must equal the
fresh VM closure (vm_closure.json). Command and environment as in the original logs:
spectre -64 bench.scs -format psfascii -raw raw +log spectre.log +lqtimeout 30, SPECTRE_DEFAULTS=-E.
Analysis: the original family analyzers (scripts/ mirror, sha-checked against recorded identities where the record
has one) are applied to the new raw; old/new measurements compared without an invented tolerance. Raw removed after
analysis. Resumable (out/<id>.json)."""
import concurrent.futures, copy, hashlib, json, math, os, re, shutil, subprocess, sys, threading, time
from pathlib import Path
sys.dont_write_bytecode = True
RUN = Path.cwd().resolve(); SRC = RUN / 'src'
PDK = os.environ['PAM4_PDK_ROOT']  # private copy of the VM model tree
OLD_PDK = '<PDK_ROOT>'
OLD_LA5 = '/home/user/Desktop/cadence_projects/la5_10g_20261004'
NEW_LA5 = str(RUN / 'la5')
CMD = ['spectre', '-64', 'bench.scs', '-format', 'psfascii', '-raw', 'raw', '+log', 'spectre.log', '+lqtimeout', '30']
BUILD = '23.1.0.722.isr15'
NOISY = {'adc_acquisition_r5_20261013': ['cml2_late32_s10_noise181', 'cml2_late32_s10_noise191'],
         'adc_isolation_r4_20261013': ['cml8_m25_sw4_c25_noise41', 'cml8_m25_sw4_c25_noise83'],
         'adc_isolation_r5_20261013': ['cml_w2_m5_s10_noise101', 'cml_w2_m5_s10_noise151']}
DETERMINISTIC = ['adc_comparator_r5_20261013', 'adc_reset_r4_20261013', 'adc_comparator_r3_diag', 'adc_comparator_r3_tt',
                 'adc_comparator_burst_r5_20261013', 'adc_doubletail_r5_20261013', 'adc_equalizer_r4_20261013',
                 'adc_frontend_load_r4_20261013', 'adc_reset_clamp_r5_20261013', 'native_baseline', 'native_capacitor_r5_20261013',
                 'native_geometry_r5_20261013', 'native_verification_r3', 'optimization_op_probe']
EXTRA_SEEDS = list(range(301, 320))
LOCK = threading.Lock()
M = {}


def need(ok, msg):
    if not ok:
        raise RuntimeError(msg)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def jl(p):
    return json.loads(Path(p).read_text())


def wj(p, v):
    t = Path(str(p) + '.tmp'); t.write_text(json.dumps(v, indent=1, sort_keys=True, default=str) + '\n'); t.replace(p)


def compare(old, new, path='', acc=None):
    acc = acc if acc is not None else dict(shape=[], discrete=[], numeric=[])
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) ^ set(new), key=str):
            acc['shape'].append(path + '/' + str(k))
        for k in sorted(set(old) & set(new), key=str):
            compare(old[k], new[k], path + '/' + str(k), acc)
    elif isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            acc['shape'].append(path + ' length %d->%d' % (len(old), len(new)))
        for i, (a, b) in enumerate(zip(old, new)):
            compare(a, b, path + '/' + str(i), acc)
    elif isinstance(old, (int, float)) and isinstance(new, (int, float)) and not isinstance(old, bool) and not isinstance(new, bool) and (isinstance(old, float) or isinstance(new, float)):
        if old != new and not (isinstance(old, float) and isinstance(new, float) and math.isnan(old) and math.isnan(new)):
            acc['numeric'].append(dict(path=path, old=old, new=new, rel=abs(new - old) / max(abs(old), abs(new))))
    elif old != new:
        acc['discrete'].append(dict(path=path, old=old, new=new))
    return acc


def flatten(v, path='', out=None):
    out = {} if out is None else out
    if isinstance(v, dict):
        for k, x in v.items():
            flatten(x, path + '/' + str(k), out)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            flatten(x, path + '/' + str(i), out)
    else:
        out[path] = v
    return out


def render(data):
    out = data
    need(out.count(OLD_PDK) >= 1 or out.count(OLD_LA5) >= 1, 'model root absent (neither direct nor via LA5 corners)')
    out = out.replace(OLD_PDK, PDK).replace(OLD_LA5, NEW_LA5)
    need(out.replace(NEW_LA5, OLD_LA5).replace(PDK, OLD_PDK) == data and PDK not in data and NEW_LA5 not in data, 'non-reversible')
    return out


def setup():
    sys.path.insert(0, str(RUN)); sys.path.insert(0, str(SRC / 'scripts'))
    import importlib
    for name in ('adc_comparator_probe', 'adc_comparator_r5', 'adc_doubletail_r5', 'adc_comparator_burst_r5', 'adc_reset_clamp_r5',
                 'adc_reset_sweep_r4', 'adc_frontend_load_r4', 'adc_comparator_diagnostic', 'native_baseline', 'native_geometry_r5',
                 'native_capacitor_r5', 'adc_isolation_r4', 'adc_isolation_r5', 'adc_acquisition_r5', 'psf_ascii'):
        M[name] = importlib.import_module(name)
        need(Path(M[name].__file__).resolve().parent == (SRC / 'scripts').resolve(), 'unpinned import ' + name)
    M['psf_ascii'].MAX_FILE_BYTES = 512 * 1024 ** 2  # reader resource bound only
    la5 = (SRC / 'la5/scripts/la5_foundry_corners.scs').read_text()
    (RUN / 'la5/scripts').mkdir(parents=True, exist_ok=True)
    out = la5.replace(OLD_PDK, PDK); need(out.replace(PDK, OLD_PDK) == la5, 'la5 non-reversible')
    (RUN / 'la5/scripts/la5_foundry_corners.scs').write_text(out)


def raw_of(d):
    a = M['adc_comparator_probe']
    return a.parse_file(a._raw_file(d))


def script_check(ident, keys):
    """Recorded analyzer hashes must equal the mirrored scripts (when the record carries them)."""
    names = {hashlib.sha256((SRC / 'scripts' / f).read_bytes()).hexdigest(): f for f in os.listdir(SRC / 'scripts') if f.endswith('.py')}
    bad = {k: ident[k] for k in keys if k in ident and ident[k] not in names}
    need(not bad, 'analyzer version not in mirror: %s' % bad)
    return {k: names[ident[k]] for k in keys if k in ident}


def analyze(fam, case, d, src, seed=None):
    """Return (old_measurement, new_measurement, analyzer_note)."""
    a = M['adc_comparator_probe']
    if fam in ('adc_comparator_r5_20261013', 'adc_doubletail_r5_20261013', 'adc_comparator_burst_r5_20261013', 'adc_reset_clamp_r5_20261013'):
        rec = jl(src / {'adc_comparator_r5_20261013': 'comparator_r5_summary.json', 'adc_doubletail_r5_20261013': 'doubletail_r5_summary.json',
                        'adc_comparator_burst_r5_20261013': 'comparator_burst_r5_summary.json', 'adc_reset_clamp_r5_20261013': 'reset_clamp_r5_summary.json'}[fam])
        idt = rec['identity']; note = script_check(idt, [k for k in idt if k.endswith('script_sha256') or k in ('helper_sha256', 'probe_helpers_sha256', 'geometry_helper_sha256')])
        raw = raw_of(d); cfg, tm = idt['configuration'], idt['timing']
        if fam == 'adc_comparator_r5_20261013':
            r = M['adc_comparator_r5']; rows = r.analyze_values(raw.values[raw.sweep_names[0]], raw.values, cfg, tm); summ = r.summarize(rows, tm)
        elif fam == 'adc_doubletail_r5_20261013':
            rows, summ = M['adc_doubletail_r5'].analyze(raw, cfg, tm)
        elif fam == 'adc_comparator_burst_r5_20261013':
            rows, summ = M['adc_comparator_burst_r5'].analyze(raw, cfg, tm, idt['topology'])
        else:
            rows, summ = M['adc_reset_clamp_r5'].analyze(raw, cfg, tm)
        return dict(cycles=rec['cycles'], summary=rec['summary']), dict(cycles=rows, summary=summ), note
    if fam in ('adc_reset_r4_20261013', 'adc_equalizer_r4_20261013'):
        top = jl(src.parent / ('sweep_identity.json' if fam == 'adc_reset_r4_20261013' else 'equalizer_identity.json'))
        note = script_check(top, [k for k in top if k.endswith('script_sha256')])
        rec = jl(src / ('reset_case_summary.json' if fam == 'adc_reset_r4_20261013' else 'equalizer_case_summary.json'))
        cc = copy.deepcopy(top['base_configuration']); cc['copies'].update(precharge=rec['precharge_copies'], tail=rec['tail_copies'])
        r = M['adc_reset_sweep_r4']; raw = raw_of(d)
        rows = r.analyze_values(raw.values[raw.sweep_names[0]], raw.values, cc, rec['timing'])
        return dict(cycles=rec['cycles'], summary=rec['summary']), dict(cycles=rows, summary=r.summarize(rows, rec['timing'])), note
    if fam == 'adc_frontend_load_r4_20261013':
        top = jl(src.parent / 'load_identity.json'); note = script_check(top, ['script_sha256'])
        rec = jl(src / 'load_case_summary.json')
        new = M['adc_frontend_load_r4'].metrics(d, rec['eight_buffer_banks_present'], top['comparator_load'])
        return rec['metrics'], new, note
    if fam == 'adc_comparator_r3_tt':
        summ = jl(src.parent / 'comparator_probe_summary.json'); cr = summ['cases'][int(case.split('_')[-1])]
        raw = raw_of(d); rows = a.analyze_values(raw.values[raw.sweep_names[0]], raw.values, summ['configuration'], cr['magnitude_LSB'])
        return dict(cycles=cr['cycles'], summary=cr['summary']), dict(cycles=rows, summary=a.summarize(rows, summ['configuration'])), \
            'record has no analyzer hash; current mirrored adc_comparator_probe.py used'
    if fam == 'adc_comparator_r3_diag':
        rec = jl(src / 'diagnostic_summary.json'); g = M['adc_comparator_diagnostic']
        old_p, old_r = a.PERIOD, g.RESET_LEAD
        try:
            a.PERIOD = rec['period_s']
            if 'reset_lead_s' in rec:
                g.RESET_LEAD = rec['reset_lead_s']
            rows, summ = g.analyze(raw_of(d), rec['configuration'], rec['magnitude_LSB'])
        finally:
            a.PERIOD, g.RESET_LEAD = old_p, old_r
        return dict(cycles=rec['cycles'], summary=rec['summary']), dict(cycles=rows, summary=summ), \
            'record has no analyzer hash; current mirrored adc_comparator_diagnostic.py used (reset_lead from record: %s)' % ('reset_lead_s' in rec)
    nb = M['native_baseline']
    if fam == 'native_baseline':
        res = jl(SRC / 'results/native_baseline_summary.json')
        if case == 'oa_tt25':
            old = dict(res['native_OA_TT25']); old.pop('run_status', None)
            return old, nb.metrics(d, ('inp', 'inn', 'outp', 'outn', 'h0p', 'h0n', 'VDD:p'), .9), 'native_baseline.metrics (no analyzer hash recorded)'
        row = next(r for r in res['three_corner_smoke_results'] if r['name'] == case)
        old = {k: v for k, v in row.items() if k not in ('name', 'model_section', 'temperature_C', 'supply_V', 'run_status')}
        return old, nb.metrics(d, ('X_ip', 'X_im', 'X_o_p', 'X_o_m', 'X_h0p', 'X_h0m', 'XVs:p'), row['supply_V']), 'native_baseline.metrics (no analyzer hash recorded)'
    if fam == 'native_verification_r3':
        res = jl(SRC / 'results/native_verification_r3.json'); vdd = res['config'].get('vdd', .9)
        sig = ('inp', 'inn', 'outp', 'outn', 'h0p', 'h0n', 'VDD:p') if case == 'native' else ('X_ip', 'X_im', 'X_o_p', 'X_o_m', 'X_h0p', 'X_h0m', 'XVs:p')
        return res[case], nb.metrics(d, sig, vdd), 'native_baseline.metrics as used by verify_revision.py'
    if fam == 'native_geometry_r5_20261013':
        ps = M['psf_ascii']; ng = M['native_geometry_r5']
        if case == 'native_fixture':
            res = jl(SRC / 'results/native_geometry_r5_summary.json'); dc = ps.parse_file(d / 'raw/dcOp.dc')
            return res['native_fixture_dc_currents_A'], {k: dc.values['VD' + k + ':p'][0] for k, p, w, l in ng.geometries()}, 'native_geometry_r5 extract() current read'
        res = jl(SRC / 'results/native_geometry_speed_r5.json'); dc = ps.parse_file(d / 'raw/dcOp.dc'); ac = ps.parse_file(d / 'raw/acResponse.ac')
        f = ac.values[ac.sweep_names[0]]; new = []
        for row in res['results']:
            g = row['geometry']; gain = [abs(x / y) for x, y in zip(ac.values['VD' + g + ':p'], ac.values['VG' + g + ':p'])]
            i56 = min(range(len(f)), key=lambda i: abs(f[i] - 56e9))
            cross = None
            for i in range(1, len(f)):
                if gain[i - 1] >= 1 > gain[i]:
                    x0, x1, y0, y1 = math.log(f[i - 1]), math.log(f[i]), math.log(gain[i - 1]), math.log(gain[i])
                    cross = math.exp(x0 + (0 - y0) * (x1 - x0) / (y1 - y0)); break
            new.append(dict(geometry=g, drain_current_A=dc.values['VD' + g + ':p'][0], short_circuit_current_gain_56GHz=gain[i56], first_unity_crossing_Hz=cross))
        return res['results'], new, 'RECONSTRUCTED analyzer (original speed script not in project): |I(VD)/I(VG)| at 56 GHz, log-log unity crossing'
    if fam == 'native_capacitor_r5_20261013':
        res = jl(SRC / 'results/native_capacitor_r5_summary.json'); nc = M['native_capacitor_r5']; ps = M['psf_ascii']
        new = {k: [] for k, _ in nc.geometries()}
        for label, freq in nc.FREQUENCIES:
            raw = ps.parse_file(d / 'raw' / ('ac' + label + '.ac')); fr = raw.values[raw.sweep_names[0]][0]
            for k, _ in nc.geometries():
                new[k].append(nc.measure_admittance(fr, raw.values['drive'][0], raw.values['VP' + k + ':p'][0], raw.values['VN' + k + ':p'][0]))
        return {k: v['AC'] for k, v in res['cases'].items()}, new, 'native_capacitor_r5.measure_admittance'
    if fam == 'optimization_op_probe':
        res = jl(SRC / 'results/optimization_op_probe.json'); ps = M['psf_ascii']
        dc = ps.parse_file(d / 'raw/dcOp.dc'); op = ps.parse_file(d / 'raw/dcOpInfo.info')
        fields = ['gm', 'gds', 'vds', 'vdsat', 'vgs', 'ids', 'id', 'region']; new = []
        for i, old in enumerate(res['results']):
            tag = 'X%d' % i; selected = {}
            for role in ['M1p0', 'T1p0', 'M2p0', 'T2p0']:
                matches = {}
                for key, value in op.values.items():
                    if not (key == tag + role or key.startswith(tag + role + '.')):
                        continue
                    if value and isinstance(value[0], dict):
                        e = {f: value[0][f] for f in fields if f in value[0]}
                        if 'gm' in e or 'gds' in e:
                            if 'vds' in e and 'vdsat' in e:
                                e['vds_minus_vdsat_V'] = e['vds'] - e['vdsat']
                            if e.get('gds', 0):
                                e['output_resistance_ohm'] = 1.0 / e['gds']
                            matches[key] = e
                selected[role] = matches
            node = {x: dc.values[tag + '_' + x][0] for x in ['ip', 'im', 'c_p', 'c_m', 'o_p', 'o_m', 's1_p', 's1_m', 's2_p', 's2_m', 'h0p', 'h0m']}
            new.append(dict(node_DC_V=node, VDD_power_W=-.9 * dc.values[tag + 'Vs:p'][0], selected_primitive_op=selected))
        return [{k: r[k] for k in ('node_DC_V', 'VDD_power_W', 'selected_primitive_op')} for r in res['results']], new, 'optimization_op_probe.main() loop (inline copy)'
    if fam in NOISY:
        rec = jl(src / 'summary.json'); note = script_check(rec, [k for k in rec if k.endswith('script_sha256')])
        cfg = copy.deepcopy(rec['configuration']); cfg['noise_seed'] = seed
        raw = raw_of(d)
        if fam == 'adc_acquisition_r5_20261013':
            cyc, summ, _ = M['adc_acquisition_r5'].analyze(raw, cfg)
        elif fam == 'adc_isolation_r4_20261013':
            cyc, summ = M['adc_isolation_r4'].analyze(raw, cfg)
        else:
            cyc, summ = M['adc_isolation_r5'].analyze(raw, cfg)
        return rec['summary'], summ, note
    raise RuntimeError('no adapter ' + fam)


def main():
    from model_closure_readonly import closure
    (RUN / 'out').mkdir(exist_ok=True); (RUN / ('.started_%s' % os.environ.get('SLURM_JOB_ID', 'x'))).mkdir()
    setup()
    vmc = jl(RUN / 'vm_closure.json')
    jobs = []
    for fam in DETERMINISTIC:
        for deck in sorted((SRC / 'runs' / fam).rglob('bench.scs')):
            jobs.append(dict(fam=fam, src=deck.parent, case=deck.parent.relative_to(SRC / 'runs' / fam).as_posix() or '.', seed=None))
    for fam, cases in NOISY.items():
        for c in cases:
            orig = int(re.search(r'noise(\d+)$', c).group(1))
            for s in [orig] + EXTRA_SEEDS:
                jobs.append(dict(fam=fam, src=SRC / 'runs' / fam / c, case=c, seed=s, orig_seed=orig))
    need(sum(1 for j in jobs if j['seed'] is None) == 79 and sum(1 for j in jobs if j['seed'] is not None) == 120, 'job count %d' % len(jobs))
    env = dict(os.environ, SPECTRE_DEFAULTS='-E', LC_ALL='C', OMP_NUM_THREADS='1')
    t0 = time.time(); limit = int(os.environ.get('P85_WALL_S', '9000'))

    def jid(j):
        return (j['fam'] + '__' + j['case'].replace('/', '__') + ('' if j['seed'] is None else '__seed%d' % j['seed']))

    def one(j):
        outp = RUN / 'out' / (jid(j) + '.json')
        if outp.exists():
            return 'done'
        if time.time() > t0 + limit:
            return 'deferred'
        w = RUN / 'work' / jid(j)
        try:
            data = (j['src'] / 'bench.scs').read_text()
            rel = 'runs/' + j['fam'] + ('' if j['case'] == '.' else '/' + j['case'])
            if w.exists():
                shutil.rmtree(str(w))
            w.mkdir(parents=True)
            text = render(data)
            (w / 'bench.scs').write_text(text)
            g = closure(w / 'bench.scs', {'PDK': PDK, 'PROJECT': str(RUN / 'src'), 'LA5': NEW_LA5})
            need(g['normalized_closure_sha256'] == vmc[rel]['closure'] and len(g['nodes']) == vmc[rel]['nodes'] and len(g['edges']) == vmc[rel]['edges'], 'closure differs from VM')
            if j['seed'] is not None and j['seed'] != j['orig_seed']:
                tok = 'noiseseed=%d' % j['orig_seed']; need(text.count(tok) == 1, 'noiseseed token')
                text = text.replace(tok, 'noiseseed=%d' % j['seed']); (w / 'bench.scs').write_text(text)
            s = time.monotonic()
            with (w / 'console.log').open('w') as f:
                rc = subprocess.run(CMD, cwd=str(w), env=env, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, timeout=3600).returncode
            log = (w / 'spectre.log').read_text(errors='replace') if (w / 'spectre.log').exists() else ''
            need(rc == 0 and BUILD in log and 'spectre completes with 0 errors' in log, 'Spectre failed rc=%s' % rc)
            secs = round(time.monotonic() - s, 1)
            with LOCK:
                old, new, note = analyze(j['fam'], j['case'], w, j['src'], j['seed'])
            new = json.loads(json.dumps(new, default=str))
            res = dict(id=jid(j), fam=j['fam'], case=j['case'], seed=j['seed'], seconds=secs, analyzer=note,
                       original_seconds=jl(j['src'] / 'run_status.json').get('seconds'))
            if j['seed'] is None:
                c = compare(old, new)
                rels = [x['rel'] for x in c['numeric'] if max(abs(x['old']), abs(x['new'])) > 1e-12]
                res.update(shape=c['shape'][:30], n_shape=len(c['shape']), discrete=c['discrete'][:30], n_discrete=len(c['discrete']),
                           n_numeric_diff=len(c['numeric']), max_rel=max(rels, default=0.0),
                           worst=sorted(c['numeric'], key=lambda x: -x['rel'])[:5])
            else:
                res.update(orig_seed=j['orig_seed'], original=flatten(old), new=flatten(new))
            wj(outp, res)
            shutil.rmtree(str(w))
            return 'ran'
        except Exception as e:
            wj(outp, dict(id=jid(j), fam=j['fam'], case=j['case'], seed=j['seed'], error=type(e).__name__ + ': ' + str(e)[:800]))
            if w.exists():
                rawd = w / 'raw'
                if rawd.exists():
                    shutil.rmtree(str(rawd))
            return 'error'

    counts = {}
    order = sorted(jobs, key=lambda j: (j['seed'] is None, j['fam'], j['case'], j['seed'] or 0))
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(os.environ.get('P85_WORKERS', '6'))) as pool:
        for r in pool.map(one, order):
            counts[r] = counts.get(r, 0) + 1
    done = [jl(p) for p in (RUN / 'out').glob('*.json')]
    det = [x for x in done if x.get('seed') is None]; noi = [x for x in done if x.get('seed') is not None]
    fams = {}
    for x in det:
        f = fams.setdefault(x['fam'], dict(n=0, errors=0, shape=0, discrete=0, max_rel=0.0))
        f['n'] += 1
        if 'error' in x:
            f['errors'] += 1; continue
        f['shape'] += bool(x['n_shape']); f['discrete'] += bool(x['n_discrete']); f['max_rel'] = max(f['max_rel'], x['max_rel'])
    rng = {}
    for (fam, case) in sorted({(x['fam'], x['case']) for x in noi}):
        runs = [x for x in noi if x['fam'] == fam and x['case'] == case and 'error' not in x]
        if not runs:
            continue
        orig = runs[0]['original']; leaves = {}
        for k, v in orig.items():
            vals = [r['new'].get(k) for r in runs]
            if isinstance(v, (int, float)) and not isinstance(v, bool) and all(isinstance(z, (int, float)) and not isinstance(z, bool) for z in vals):
                fin = [z for z in vals if isinstance(z, (int, float)) and math.isfinite(z)]
                if fin and math.isfinite(v):
                    leaves[k] = dict(original=v, min=min(fin), max=max(fin), within=min(fin) <= v <= max(fin), distinct=len(set(fin)))
        varying = {k: l for k, l in leaves.items() if l['distinct'] > 1 or l['min'] != l['original']}
        rng[fam + '/' + case] = dict(n=len(runs), leaves=len(leaves), leaves_varying_or_differing=len(varying),
                                     within=sum(l['within'] for l in varying.values()), out_of_range={k: l for k, l in varying.items() if not l['within']})
    agg = dict(jobs=len(jobs), finished=len(done), this_job=counts, errors=[(x['id'], x['error'][:300]) for x in done if 'error' in x],
               deterministic_by_family=fams, deterministic_cases_with_shape_or_discrete=[(x['id'], x['n_shape'], x['n_discrete']) for x in det if 'error' not in x and (x['n_shape'] or x['n_discrete'])],
               noisy_range=rng)
    wj(RUN / 'results.json', agg)
    complete = len(done) == len(jobs)
    wj(RUN / ('STOP.json' if complete else 'STOP_%s.json' % os.environ.get('SLURM_JOB_ID', 'x')),
       dict(status='complete_analyzed_cleaned_STOP' if complete else 'partial', counts=counts, errors=len(agg['errors'])))
    print('P85_END', json.dumps(dict(finished=len(done), jobs=len(jobs), errors=len(agg['errors']))), flush=True)


if __name__ == '__main__':
    main()
