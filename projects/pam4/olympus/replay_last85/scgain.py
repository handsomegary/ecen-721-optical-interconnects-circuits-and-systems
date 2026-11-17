import json, math, os, shutil, subprocess, sys, tempfile, cmath
P = '/home/user/Desktop/cadence_projects/project6_28nm'
sys.path.insert(0, P + '/scripts')
import psf_ascii as ps
src = P + '/runs/native_geometry_r5_20261013/short_circuit_gain/bench.scs'
res = json.load(open(P + '/results/native_geometry_speed_r5.json'))
d = tempfile.mkdtemp(prefix='scgain_', dir='/tmp')
try:
    shutil.copy(src, d + '/bench.scs')
    env = dict(os.environ, SPECTRE_DEFAULTS='-E')
    rc = subprocess.run(['/opt/eda/cadence/SPECTRE181/tools.lnx86/bin/spectre', '-64', 'bench.scs', '-format', 'psfascii', '-raw', 'raw', '+log', 'spectre.log'],
                        cwd=d, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    ac = ps.parse_file(d + '/raw/acResponse.ac'); dc = ps.parse_file(d + '/raw/dcOp.dc')
    print('rc', rc, 'ac sha', ac.sha256 == res['raw_sha256']['ac'], 'dc sha', dc.sha256 == res['raw_sha256']['dc'])
    f = ac.values[ac.sweep_names[0]]
    print('grid', len(f), f[:3], f[-3:], [x for x in f if 50e9 < x < 60e9][:6])
    out = {}
    for row in res['results']:
        g = row['geometry']; idd = ac.values['VD' + g + ':p']; ig = ac.values['VG' + g + ':p']
        gain = [abs(a / b) for a, b in zip(idd, ig)]
        i56 = min(range(len(f)), key=lambda i: abs(f[i] - 56e9))
        # candidates
        j = max(i for i in range(len(f)) if f[i] <= 56e9); k = j + 1
        lin = gain[j] + (gain[k] - gain[j]) * (56e9 - f[j]) / (f[k] - f[j]) if k < len(f) else None
        loglin = math.exp(math.log(gain[j]) + (math.log(gain[k]) - math.log(gain[j])) * (math.log(56e9) - math.log(f[j])) / (math.log(f[k]) - math.log(f[j]))) if k < len(f) else None
        cplx = abs((idd[j] + (idd[k] - idd[j]) * (56e9 - f[j]) / (f[k] - f[j])) / (ig[j] + (ig[k] - ig[j]) * (56e9 - f[j]) / (f[k] - f[j]))) if k < len(f) else None
        real_only = abs(idd[i56].real / ig[i56].imag) if ig[i56].imag else None
        idd_over_omegaC = None
        out[g] = dict(orig=row['short_circuit_current_gain_56GHz'], nearest=gain[i56], f_nearest=f[i56], lin=lin, loglin=loglin, cplx_lin=cplx, real_over_imag=real_only,
                      drain_dc=dc.values['VD' + g + ':p'][0], orig_drain=row['drain_current_A'])
    g0 = res['results'][0]['geometry']
    print(json.dumps(out[g0], indent=0))
    for name in ('nearest', 'lin', 'loglin', 'cplx_lin', 'real_over_imag'):
        errs = [abs(v[name] - v['orig']) / v['orig'] for v in out.values() if v[name] is not None]
        print(name, 'max rel err vs recorded', max(errs) if errs else None)
finally:
    shutil.rmtree(d)
    print('tmp removed', not os.path.exists(d))
