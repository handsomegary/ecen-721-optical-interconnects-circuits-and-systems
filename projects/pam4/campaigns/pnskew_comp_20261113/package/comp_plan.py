"""Create the predeclared case schedule and per-case resource estimates."""
import itertools
import json
from pathlib import Path

CORNERS = tuple(itertools.product(('tt','ss','ff'), (-40,25,85), (.81,.90,.99)))
BASE = ('tt',25,.90)
ENDPOINTS = (('ss',85,.81), ('ff',-40,.99))
ANCHORS = (0,4,8,16,24,32,40,48,56,63)
UI_PS = 1000 / 112


def tag(corner):
    p,t,v = corner
    return '%s_%s%02d_v%03d' % (p, 'm' if t < 0 else 'p', abs(t), round(v*100))


def ac_case(corner, code, drive, rs, bypass, stage):
    p,t,v = corner
    return dict(case_id='ac_%s_%s_%s_r%d' % (tag(corner), 'bypass' if bypass else '%02d'%code, drive, rs),
                stage=stage, kind='ac', process=p, temperature_C=t, vdd_V=v,
                p_code=code, n_code=0 if bypass else 63-code, drive=drive, source_ohm=rs, load_fF=0,
                bypass=bypass, cpus=1, memory_GiB=4, requested_wall_min=30,
                estimated_spectre_min=[.2, 5.])


def integrated(study, corner, delta, seed=None, stress=0.):
    p,t,v = corner
    index = round(delta*1000)
    return dict(case_id='%s_%s_%s%03d_s%d_r%+d' % (
        study, tag(corner), 'm' if delta < 0 else 'p', abs(index), seed or 0, round(stress*100)),
        study=study, process=p, temperature_C=t, vdd_V=v, injected_skew_UI=delta,
        seed=seed, added_differential_stress_ps=stress,
        cpus=1, memory_GiB=8, requested_wall_min=240,
        estimated_spectre_min=[65,155] if seed is not None else [55,130])


def build():
    ac = {}
    def add(corner, codes, drives, impedances, stage):
        for code, drive, rs in itertools.product(codes, drives, impedances):
            c = ac_case(corner, code or 0, drive, rs, code is None, stage)
            ac.setdefault(c['case_id'], c)
    add(BASE, (None,0,16,32,48,63), ('p','n'), (0,25,50), 'standalone_pilot_TT')
    for c in ENDPOINTS:
        add(c, (None,0,16,32,48,63), ('p','n'), (25,), 'standalone_pilot_endpoints')
    for c in CORNERS:
        add(c, (None,) + tuple(range(64)), ('p','n'), (25,), 'standalone_full_code_PVT')
    quiet = [integrated('quiet',BASE,i/8) for i in range(-4,5)]
    fine = [integrated('fine',BASE,s*i/32) for s in (-1,1) for i in (9,10,11)]
    stress = [integrated('stress',BASE,s*.5,stress=r) for s in (-1,1)
              for r in (-1.,-.5,-.25,0.,.25,.5,1.)]
    noise = [integrated('noise',BASE,d,seed) for d in (-.5,0.,.5) for seed in range(1001,1021)]
    endpoints = [integrated('pvt',c,d) for c in ENDPOINTS for d in (-.5,0.,.5)]
    return {'format':'pn_comp_review_plan_v1', 'status':'PROPOSED_AWAITING_USER_APPROVAL',
            'existing_solver':'Spectre 23.1.0.722.isr15 classic +mt=1; one CPU per job',
            'cases':list(ac.values()),
            'integrated_plan':quiet+fine+stress+noise+endpoints,
            'nominal_search_coarse_symmetric_codes': [[c,63-c] for c in ANCHORS],
            'nominal_search_fine_rule':'scan complementary offsets -3..+3 about best coarse code; verify independently; do not assume monotonicity',
            'training_window_UI':224, 'train_windows':2, 'independent_check_windows':2,
            'estimator_required_phase_band_Hz':[7e9,49e9],
            'pilot_job_resource':{'cpus':1,'memory_GiB':6,'requested_wall_min':120,
                                  'estimated_spectre_min':[12,60]},
            'qos_upper':{'CPUs_per_job':6,'wall_h_per_job':12},
            'execution_order':['review','sparse standalone','full standalone if sparse cell viable',
                               'blind pilot at selected skew/corner','integrated quiet',
                               'local onset and residual stress','paired noise and corner endpoints'],
            'runtime_estimates_status':'PLANNING_ONLY; use first successful Spectre wall, MaxRSS and raw size before dispatching any sweep'}


if __name__ == '__main__':
    print(json.dumps(build(), indent=2, allow_nan=False))
