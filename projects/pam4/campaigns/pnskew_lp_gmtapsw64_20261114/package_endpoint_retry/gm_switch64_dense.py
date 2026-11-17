"""Refine the COMMON64 fast-fast centre-step AC measurement."""

import math
import re

import gm_center64 as design
import gm_center64_summary as center
from gm_gmtap_common_summary import same_physical_split64
import gm_tapmid_summary as mid
import gm_taptrim_summary as trim
from global_summary import fit
import olympus_common as common
import summarize_acnext as modal


PROFILES = ('base100', 'grid200', 'grid400', 'tight400')
DENSITY = {'base100':100, 'grid200':200, 'grid400':400, 'tight400':400}
CODES = (-2,-1,0,1,2)
EDGES = ((-2,-1),(-1,0),(0,1),(1,2))
STEP_LIMIT_PS = .50
CONVERGENCE_LIMIT_PS = .001
HISTORICAL_FIRST_STEPS_PS = {(-1,0):.49479191568842, (0,1):.49479191568830}
AC_PREFIX = 'acResponse ac start=1K stop=150G dec='


def render(case, model_root):
    """Change only grid density and, for the final profile, solver tolerances."""
    profile = case['dense_profile']
    common.need(profile in DENSITY and case['stage']=='dense' and case['process']=='ff',
                'Unexpected refinement case')
    if case['group']=='baseline':
        common.need(case['code']==0 and case['variant_name']=='r3','Invalid grid-weight reference')
    else:
        common.need(case['code'] in CODES and case['bias_kind']=='divider_lowz'
                    and same_physical_split64(case),'Invalid loaded Split64 fixture')
    deck,rails,ac,dc,currents,diff = design.render(case,model_root)
    if profile=='base100':
        common.need(deck.count(AC_PREFIX+'100')==1,'Expected original AC grid')
        return deck,rails,ac,dc,currents,diff
    base = design.BASE
    deck = base.replace_once(deck,AC_PREFIX+'100',AC_PREFIX+str(DENSITY[profile]))
    if profile=='tight400':
        token = 'reltol=1e-4 vabstol=1u iabstol=1p'
        options,count = re.subn(r'(?m)^(simulatorOptions options [^\n]+)'+token+r'$',
                    lambda match:match[1]+'reltol=1e-5 vabstol=0.1u iabstol=0.1p',
                    deck)
        common.need(count==1,'Expected original simulator tolerances')
        deck = options
    parent,_ = base.load_inputs()
    diff = base.unified(parent.replace(base.MODEL_TOKEN,model_root),deck)
    return deck,rails,ac,dc,currents,diff


def check_grid(grid, profile):
    density = DENSITY[profile]
    start_hz, stop_hz = 1000, 150e9
    stop_tolerance = 1e-9
    step_tolerance = .001
    count_minimum = math.floor(density * math.log10(145e9 / start_hz))
    max_ratio = 10**((1 + step_tolerance) / density)
    error = f'Incomplete {density}-point/decade refinement grid'
    common.need(len(grid) >= count_minimum and 0 < grid[0] <= 1000.01
                and 145e9 <= grid[-1] <= stop_hz * (1 + stop_tolerance)
                and all(math.isfinite(x) for x in grid)
                and all(0 < x < y <= x * max_ratio for x, y in zip(grid[:-2], grid[1:-1]))
                and grid[-2] < grid[-1], error)
    if grid[-1] <= grid[-2] * max_ratio:
        return

    # Spectre rounds the interval count and puts the requested stop in the last slot.
    # The final interval can therefore be up to half a log step longer than nominal.
    intervals = round(density * math.log10(stop_hz / start_hz))
    common.need(math.isclose(grid[-1], stop_hz, rel_tol=stop_tolerance)
                and len(grid) == intervals + 1
                and all(abs(density * math.log10(frequency / start_hz) - index) <= step_tolerance
                        for index, frequency in enumerate(grid[:-1])), error)


def evaluate_family(profile, baseline, by_code):
    if baseline is None or set(by_code)!=set(CODES):
        return None
    fs = baseline[1]['p']['frequency_Hz']
    check_grid(fs,profile)
    track = modal.matrix(baseline[1],('X_h0p','X_h0m'))
    neutral = by_code[0][2]
    rows = {}
    for code,(case,pair,matrix,_) in sorted(by_code.items()):
        common.need(pair['p']['frequency_Hz']==fs and pair['n']['frequency_Hz']==fs,
                    'Bypass and loaded AC frequency grids differ')
        metrics = fit(fs,matrix,neutral,track)
        bias = mid.bias_evidence(case,pair)
        xt2 = trim.xt2_minimum(pair)
        rows[code] = {'fit':metrics,'bias':bias,'XT2_worst_margin_V':xt2['margin_V'],
                      'XT2_static_pass':xt2['passes_static_screen']}
    steps = {}
    for a,b in EDGES:
        ta,tb = (rows[code]['fit']['delay_ps'] for code in (a,b))
        step = tb-ta if mid.numeric(ta) and mid.numeric(tb) else None
        steps[a,b] = step
    return {'points_per_decade':DENSITY[profile],'point_count':len(fs),'by_code':rows,
            'steps_ps':steps}


def decide(families):
    """Bound numerical sensitivity from observed grid and tolerance refinements."""
    exact = lambda rows: all(mid.numeric(rows['steps_ps'].get(e)) for e in EDGES)
    refinements = {}
    if not all(p in families and families[p] is not None and exact(families[p]) for p in PROFILES):
        return 'incomplete_dense_evidence', refinements
    for edge in EDGES:
        s100,s200,s400,stight = (families[p]['steps_ps'][edge] for p in PROFILES)
        grid_last = abs(s400-s200)
        solver = abs(stight-s400)
        proxy = grid_last+solver
        slack = STEP_LIMIT_PS-stight
        refinements[edge] = {
            'historical_common_first_step_ps':HISTORICAL_FIRST_STEPS_PS.get(edge),
            'base100_ps':s100,'grid200_ps':s200,'grid400_ps':s400,'tight400_ps':stight,
            'tight400_minus_base100_fs':1000*(stight-s100),
            'last_grid_delta_fs':1000*grid_last,'solver_tolerance_delta_fs':1000*solver,
            'observed_refinement_proxy_fs':1000*proxy,
            'tight400_margin_to_0p50_fs':1000*slack,
            'nominal_step_pass':all(0<s<=STEP_LIMIT_PS for s in (s100,s200,s400,stight)),
            'observed_proxy_within_1fs':proxy<=CONVERGENCE_LIMIT_PS,
            'margin_exceeds_observed_proxy':min(slack,stight)>proxy,
        }
    if any(not d['nominal_step_pass'] for d in refinements.values()):
        status = 'fails_nominal_step_screen'
    elif any(not d['observed_proxy_within_1fs'] or not d['margin_exceeds_observed_proxy']
             for d in refinements.values()):
        status = 'numerical_margin_unresolved'
    elif any(r.get('XT2_static_pass') is not True for f in families.values() for r in f['by_code'].values()):
        status = 'XT2_static_screen_unresolved_or_failed'
    else:
        status = 'passes_nominal_dense_recheck'
    return status,refinements


def summarize(root, cases, plan):
    selected = [c for c in cases if c['stage']=='dense']
    paired, missing, invalid = center.collect(root,selected,plan)
    families = {}
    for profile in PROFILES:
        baseline = None
        by_code = {}
        for fixture in paired.values():
            c = fixture[0]
            if c['dense_profile']!=profile:
                continue
            if c['group']=='baseline':
                common.need(baseline is None,'Duplicate dense bypass')
                baseline = fixture
            else:
                code = c['code']
                common.need(code not in by_code,'Duplicate dense loaded code')
                by_code[code] = fixture
        try:
            families[profile] = evaluate_family(profile,baseline,by_code)
        except (ValueError,KeyError,TypeError,OverflowError) as error:
            invalid[profile] = str(error)
            families[profile] = None
    status, comparisons = decide(families)
    label = lambda pair: f'{pair[0]}_to_{pair[1]}'
    for family in families.values():
        if family is not None:
            family['steps_ps'] = {label(edge):step for edge,step in family['steps_ps'].items()}
    return {'format':'pam4_lp14_switch64_FF_dense_summary_v1','status':status,
            'verified_nominal_dense_steps':status=='passes_nominal_dense_recheck',
            'maximum_step_ps':STEP_LIMIT_PS,
            'engineering_refinement_limit_fs':1000*CONVERGENCE_LIMIT_PS,
            'observed_proxy_definition':'|grid400-grid200| + |tight400-grid400| on each adjacent weighted step',
            'comparisons_by_edge':{label(edge):data for edge,data in comparisons.items()},
            'profiles':families,'missing_cases':missing,'invalid_cases':invalid,
            'scope':'FF schematic nominal AC refinement. No statistical mismatch, extracted parasitics or transient timing measured.'}
