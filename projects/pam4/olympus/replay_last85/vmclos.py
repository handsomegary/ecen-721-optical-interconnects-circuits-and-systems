import json, os, sys
sys.path.insert(0, '/tmp'); from model_closure_readonly import closure
P = '/home/user/Desktop/cadence_projects/project6_28nm'
roots = {'PDK': '<PDK_ROOT>', 'PROJECT': P, 'LA5': '/home/user/Desktop/cadence_projects/la5_10g_20261004'}
fams = sys.argv[1:]
out = {}
for f in fams:
    for a, ds, fs in os.walk(os.path.join(P, 'runs', f)):
        if 'bench.scs' in fs:
            g = closure(os.path.join(a, 'bench.scs'), roots)
            out[os.path.relpath(a, P)] = dict(closure=g['normalized_closure_sha256'], nodes=len(g['nodes']), edges=len(g['edges']),
                                             files=sorted(k for k in g['nodes'] if not k.startswith('@PDK@')))
print(json.dumps(out))
