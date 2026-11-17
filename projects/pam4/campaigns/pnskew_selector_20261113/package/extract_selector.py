#!/usr/bin/env python3
"""Read the pinned compact ACNEXT TT0-13 evidence without running Spectre."""
import argparse
import bisect
import cmath
import hashlib
import json
import math
from pathlib import Path
import re
import tarfile
import zipfile


OUTPUTS = Path(__file__).resolve().parents[1]
RESULTS = OUTPUTS / 'pam4_pnskew_acnext_20261113_results'
INPUTS = {
    'archive': (RESULTS / 'olympus_compact_acnext_tt0_13.tgz',
                '1fd5b761f6c5aab6e2c15093837d5bcdadad72d128c0ae2f0c33e200af2f4717'),
    'summary': (RESULTS / 'acnext_tt0_13_summary.json',
                '370294a79bc9dc0fe7c6deda373c623d3d4610b3c477a2fed9b8c66e68245c3b'),
    'package': (OUTPUTS / 'ECEN721_PAM4_PNSKEW_COMP_ACNEXT_20261113.zip',
                '9a676e5032b6f39fd9140293e3521b3cd2d2f9dd838dfeb0232abf8f4da24ec4'),
}
FREQUENCIES = (1e3, 1e6, 1e9, 7e9, 14e9, 28e9, 56e9)
SOURCE_OHM = 25.
SECTION = {'L_total_pH': 13., 'C_shunt_fF': 20.8, 'R_total_ohm': .305}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pair(value):
    return [value.real, value.imag]


def db(value):
    return 20. * math.log10(abs(value))


def at(report, name, frequency):
    grid = report['frequency_Hz']
    trace = report['traces'][name]
    i = bisect.bisect_left(grid, frequency)
    if i < len(grid) and grid[i] == frequency:
        return complex(*trace[i])
    require(0 < i < len(grid), 'Frequency outside recorded grid')
    t = math.log(frequency/grid[i-1])/math.log(grid[i]/grid[i-1])
    return (1-t)*complex(*trace[i-1]) + t*complex(*trace[i])


def mul(first, second):
    a,b,c,d = first
    e,f,g,h = second
    return (a*e+b*g, a*f+b*h, c*e+d*g, c*f+d*h)


def inverse(matrix):
    a,b,c,d = matrix
    determinant = a*d-b*c
    require(abs(determinant) > 1e-15, 'Singular bypass matrix')
    return d/determinant, -b/determinant, -c/determinant, a/determinant


def ladder(frequency, sections):
    omega = 2j*math.pi*frequency
    z = SECTION['R_total_ohm']/2 + omega*SECTION['L_total_pH']*.5e-12
    y = omega*SECTION['C_shunt_fF']*1e-15
    unit = (1+z*y, 2*z+z*z*y, y, 1+z*y)
    result = (1,0,0,1)
    for _ in range(sections):
        result = mul(result, unit)
    return result


def read_evidence(tgz, package, summary):
    with zipfile.ZipFile(package) as zipfile_:
        pins = dict((name,digest) for digest,name in
                    (line.split('  ',1) for line in zipfile_.read('SHA256SUMS.txt').decode().splitlines()))
        require(set(pins) == set(zipfile_.namelist())-{'SHA256SUMS.txt'}, 'Incomplete package manifest')
        for name,digest in pins.items():
            require(sha(zipfile_.read(name)) == digest, 'Package member SHA mismatch: ' + name)
        plan = json.loads(zipfile_.read('case_plan.json'))['cases']
        parent = zipfile_.read('pvt/cases/nominal_parent.scs.txt').decode('ascii')
        r5 = zipfile_.read('r5_original/quiet.scs').decode('ascii')
    reports, evidence = {}, {}
    with tarfile.open(tgz,'r:gz') as archive:
        members = [member.name for member in archive.getmembers() if member.isfile()]
        require(len(members) == len(set(members)), 'Duplicate compact members')
        require({name for name in members if name.endswith('/measurements.json')} ==
                {'run/'+c['case_id']+'/measurements.json' for c in plan[:14]}, 'Unexpected measured-case census')
        for expected in plan[:14]:
            key = expected['case_id']
            prefix = 'run/' + key + '/'
            def get(name):
                member = archive.getmember(prefix+name)
                require(member.isfile(), 'Unexpected compact member type')
                return archive.extractfile(member).read()
            names = ('case.json','measurements.json','completion.json','run_status.json',
                     'raw_retirement_manual_20261113.json')
            files = {name:get(name) for name in names}
            c,m,completion,status,receipt = (json.loads(files[name]) for name in names)
            require(all(c[name]==value for name,value in expected.items()) and c['case_id']==m['case_id']==
                    status['case_id']==receipt['case']==key, 'Cross-case evidence')
            require(m['measurement_complete'] is completion['measurement_complete'] is True and
                    sha(files['measurements.json'])==completion['measurement_sha256']==receipt['measurement_sha256'],
                    'Completion/retirement does not bind the measurements')
            require(sha(files['case.json'])==status['case_sha256'] and sha(files['run_status.json'])==m['run_status_sha256'] and
                    status['plan_sha256']==pins['case_plan.json'], 'Case/runner/plan hash chain differs')
            require(status['status']=='spectre_completed' and status['exit_code']==0 and
                    status['simulator_build']=='23.1.0.722.isr15' and status['solver_mode']=='classic' and
                    status['cpus_allocated']==1 and '+mt=1' in status['actual_argv'], 'Unexpected solver evidence')
            log,diff = get('spectre.log'),get('parent_diff.txt')
            require(status['spectre_log_sha256']==sha(log) and
                    re.search(rb'(?mi)^\s*spectre completes with\s+0\s+errors\b',log), 'Log does not bind clean completion')
            require(sha(diff)==c['staged_source_sha256']['parent_diff.txt'] and
                    m['bench_sha256']==c['staged_source_sha256']['bench.scs']==
                    status['input_deck_sha256_before']==status['input_deck_sha256_after'], 'Deck/diff hash chain differs')
            reconstructed = apply_diff(parent.replace('__pdk_root__', c['model_preflight']['model_root']),
                                       diff.decode('ascii'))
            require(sha(reconstructed.encode('ascii'))==m['bench_sha256'], 'Runtime deck did not reconstruct exactly')
            if c['variant']=='ttd_switch':
                verify_selector(reconstructed,c,r5)
            inventory = {row['path']:(row['bytes'],row['sha256']) for row in status['raw_inventory']}
            removed = {row['path']:(row['bytes'],row['sha256']) for row in receipt['removed']}
            require(inventory==removed and len(inventory)==len(receipt['removed'])==len(status['raw_inventory']),
                    'Retired raw inventory differs')
            signature = (c['variant'],c['p_code'],c['n_code'])
            reports.setdefault(signature,{})[c['drive']] = (c,m)
            evidence[key] = {'bench_sha256_reconstructed': m['bench_sha256'], 'case_sha256': status['case_sha256'],
                             'measurements_sha256': completion['measurement_sha256'],
                             'runner_sha256': m['run_status_sha256'], 'raw_entries_bound': len(inventory),
                             'job_id': status['slurm_job_id'], 'spectre_wall_s': status['spectre_wall_seconds'],
                             'peak_RSS_KiB': status['child_peak_rss_KiB_after_solver']}
    require(not summary['invalid_cases'] and len(summary['missing_cases'])==80 and
            len(summary['paired_rows'])==len(reports)==7 and all(set(group)=={'p','n'} for group in reports.values()),
            'Summary pair census differs')
    return reports,evidence,{name:pins[name] for name in ('ac_next.py','case_plan.json','pvt/cases/nominal_parent.scs.txt',
                                                        'r5_original/quiet.scs','weighted_delay.py')}


def apply_diff(parent, diff):
    """Read the retained unified diff and verify every removed/context line."""
    old = parent.splitlines(keepends=True)
    result, consumed = [], 0
    lines = diff.splitlines(keepends=True)
    require(lines[:2]==['--- parent.scs\n','+++ bench.scs\n'], 'Unexpected deck diff headers')
    for line in lines[2:]:
        if line.startswith('@@'):
            match = re.match(r'@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@',line)
            require(match is not None, 'Invalid deck diff hunk')
            start = int(match.group(1))-1
            require(start>=consumed,'Overlapping deck diff hunk')
            result.extend(old[consumed:start])
            consumed = start
        elif line[0] in ' -':
            require(old[consumed]==line[1:],'Deck diff context differs from pinned parent')
            if line[0]==' ':
                result.append(line[1:])
            consumed += 1
        else:
            require(line.startswith('+'),'Invalid deck diff line')
            result.append(line[1:])
    return ''.join(result+old[consumed:])


def verify_selector(deck, case, r5):
    instance = re.findall(r'^(ACN[PN][FS][AB][NP]) \(([^\r\n)]+)\) ([^\r\n]+)$',deck,re.M)
    require(len(instance)==16,'Expected 16 MOS across eight TGs')
    cards = {label:re.search(r'^'+name+r' \([^\r\n)]+\) ([^\r\n]+)$',r5,re.M).group(1)
             for label,name in [('N','XSN0p'),('P','XSP0p')]}
    for name,nodes,card in instance:
        device = name[-1]
        require(card==cards[device] and 'l=30n w=3u multi=1 nf=1' in card,
                'Selector does not use exact original 3um card')
        stem,edge,leg = name[:-2],name[-2],name[3]
        rail = '0' if device=='N' else 'ACN_VDD'
        external = 'ACN'+leg+'I' if edge=='A' else ('X_ip' if leg=='P' else 'X_im')
        require(nodes=='%s%s %sG%s %s %s'%(stem,'I' if edge=='A' else 'O',stem,device,external,rail),
                'TG terminal connectivity mismatch')
    for leg in 'PN':
        fast = case[leg.lower()+'_code']==6
        out = 'X_ip' if leg=='P' else 'X_im'
        pre = 'PNC_PRE'+leg
        require('ACN%sRS (%s ACN%sI) resistor r=25'%(leg,pre,leg) in deck and
                'ACN%sRT (%s X_cm) resistor r=25'%(leg,out) in deck, '25ohm fixture mismatch')
        for route,on,sections in [('F',fast,6),('S',not fast,16)]:
            tag = 'ACN'+leg+route
            for transistor,voltage in [('N',.9 if on else 0.),('P',0. if on else .9)]:
                require('%sV%s (%sG%s 0) vsource dc=%.9g'%(tag,transistor,tag,transistor,voltage) in deck,
                        'Selected/off TG gate voltage mismatch')
            for suffix,value in [('LA','inductor l=6.5p'),('LB','inductor l=6.5p'),('RA','resistor r=0.1525'),
                                 ('RB','resistor r=0.1525'),('C','capacitor c=20.8f')]:
                require(len(re.findall(r'^'+tag+r'\d\d'+suffix+r' \([^\r\n]+\) '+re.escape(value)+r'$',deck,re.M))==sections,
                        'Fixed ladder section count/value differs')


def load_matrix(bypass, frequency):
    p,n = (bypass[leg][1] for leg in 'pn')
    h = tuple(at(record,node,frequency) for record,node in
              ((p,'X_ip'),(n,'X_ip'),(p,'X_im'),(n,'X_im')))
    a,b,c,d = inverse(h)
    return ((a-1)/SOURCE_OHM,b/SOURCE_OHM,c/SOURCE_OHM,(d-1)/SOURCE_OHM)


def modal(group, frequency, nodes):
    p,n = (group[leg][1] for leg in 'pn')
    pp,pn,np,nn = (at(report,node,frequency) for report,node in
                  ((p,nodes[0]),(n,nodes[0]),(p,nodes[1]),(n,nodes[1])))
    return (pp-pn-np+nn)/2


def selector_kcl(selected, bypass, frequency, leg):
    record = selected[leg.lower()][1]
    tag = 'ACN'+leg
    input_v = at(record,tag+'I',frequency)
    pin = 'X_ip' if leg=='P' else 'X_im'
    output_v = at(record,pin,frequency)
    source_v = at(record,'PNC_PRE'+leg,frequency)
    source_i = -at(record,'XVin:p' if leg=='P' else 'PNCVN:p',frequency)
    load = load_matrix(bypass,frequency)
    ports = [at(record,n,frequency) for n in ('X_ip','X_im')]
    load_terms = load[:2] if leg=='P' else load[2:]
    load_i = sum(y*v for y,v in zip(load_terms,ports))
    route_data, routes_in, routes_out = {},0j,0j
    for route,sections in [('F',6),('S',16)]:
        a,b,c,d = ladder(frequency,sections)
        vi,vo = (at(record,tag+route+edge,frequency) for edge in 'IO')
        route_in,route_out = (d*vi-vo)/b,(vi-a*vo)/b
        routes_in += route_in
        routes_out += route_out
        drops = (input_v-vi,vo-output_v)
        currents = (route_in,route_out)
        apparent_y = [i/v for i,v in zip(currents,drops)]
        route_data[route] = {'ladder_terminal_currents_into_signal_path_A_per_V': [pair(i) for i in currents],
            'TG_voltage_drops_V_per_V': [pair(v) for v in drops],
            'apparent_terminal_Z_ohm': [pair(1/y) for y in apparent_y],
            'apparent_terminal_ImY_over_omega_fF': [y.imag/(2*math.pi*frequency)*1e15 for y in apparent_y]}
    residual = (source_i-routes_in,routes_out-load_i)
    require(abs(source_i-(source_v-input_v)/SOURCE_OHM)<1e-8, 'Source current does not close 25ohm KCL')
    return {'source_current_A_per_V':pair(source_i), 'load_current_A_per_V':pair(load_i),
            'source_to_selected_input_voltage_V_per_V':pair(input_v), 'output_voltage_V_per_V':pair(output_v),
            'terminated_r3_load_Y_modal_diff_S':pair(load[0]-load[1]), 'routes':route_data,
            'unmodeled_selector_plane_current_A_per_V':[pair(x) for x in residual],
            'unmodeled_fraction_of_external_current':[abs(residual[0])/abs(source_i),abs(residual[1])/abs(load_i)],
            'apparent_shunt_ImY_over_omega_fF':[(i/v).imag/(2*math.pi*frequency)*1e15
                                                for i,v in zip(residual,(input_v,output_v))]}


def approximate(frequency, ron, load_y, cin=0., cout=0.):
    # Equal-code differential mode. Drop the unused path and model each selected
    # TG with the low-frequency apparent Ron. Optional shunts are net estimates.
    w = 2j*math.pi*frequency
    r = (1,ron,0,1)
    network = (1,SOURCE_OHM,0,1)
    for element in ((1,0,w*cin,1),r,ladder(frequency,6),r,(1,0,w*cout,1)):
        network = mul(network,element)
    a,b,_,_ = network
    return 1/(a+b*load_y)


def analyze(paths):
    identity = {}
    for name,(default,digest) in INPUTS.items():
        path = paths.get(name,default)
        require(sha(path.read_bytes())==digest,'Input hash differs: '+name)
        identity[name] = {'file':path.name,'bytes':path.stat().st_size,'sha256':digest}
    summary = json.loads(paths['summary'].read_bytes())
    groups,evidence,pins = read_evidence(paths['archive'],paths['package'],summary)
    bypass,ideal,switched = [groups[key] for key in [('bypass',0,0),('ttd_selected',6,6),('ttd_switch',6,6)]]
    kcl = {str(int(f)):{leg:selector_kcl(switched,bypass,f,leg) for leg in 'PN'} for f in FREQUENCIES}
    ron = sum(z[0] for leg in 'PN' for z in kcl['1000'][leg]['routes']['F']['apparent_terminal_Z_ohm'])/4
    sweep = {}
    for frequency in FREQUENCIES:
        trim_nodes,afe_nodes = ('X_ip','X_im'),('X_o_p','X_o_m')
        reference = modal(bypass,frequency,trim_nodes)
        actual = modal(switched,frequency,trim_nodes)
        load = load_matrix(bypass,frequency)
        load_y = load[0]-load[1]
        out = {'bypass_trim_Hdd':pair(reference),'ideal_equal_trim_Hdd':pair(modal(ideal,frequency,trim_nodes)),
               'native_equal_trim_Hdd':pair(actual),'native_equal_trim_vs_bypass_dB':db(actual/reference),
               'ideal_equal_trim_vs_bypass_dB':db(modal(ideal,frequency,trim_nodes)/reference),
               'native_equal_AFE_vs_bypass_dB':db(modal(switched,frequency,afe_nodes)/modal(bypass,frequency,afe_nodes)),
               'approximations':{}}
        for name,cin,cout in [('Ron_only',0.,0.),('Ron_plus_1MHz_net_shunts',9.46e-15,36.15e-15),
                             ('Ron_plus_56GHz_net_shunts',5.40e-15,26.49e-15)]:
            prediction = approximate(frequency,ron,load_y,cin,cout)
            out['approximations'][name] = {'Hdd':pair(prediction),'gain_vs_bypass_dB':db(prediction/reference),
                'gain_error_dB':db(prediction/actual),'phase_error_deg':math.degrees(cmath.phase(prediction/actual)),
                'relative_complex_residual':abs(prediction-actual)/abs(actual)}
        sweep[str(int(frequency))] = out
    rows = []
    for row in summary['paired_rows']:
        c = row['config']
        key = (c['variant'],c['p_code'],c['n_code'])
        source,m = groups[key]['p']
        require(m['noise']==row['noise'] and m['DC_supply_power_W']==row['DC_supply_power_W'],
                'Retained noise/DC does not match original summary')
        actual = db(modal(groups[key],56e9,('X_o_p','X_o_m'))/modal(bypass,56e9,('X_o_p','X_o_m')))
        require(abs(actual-row['unskewed_AFE_56GHz']['Hdd_vs_bypass_dB'])<1e-9,'56GHz Hdd summary differs')
        rail_currents = {name:(-power/source['rail_voltages_V'][name] if source['rail_voltages_V'][name] else None)
                         for name,power in m['DC_supply_power_W'].items()}
        rows.append({'variant':key[0],'PN_sections':list(key[1:]),'AFE_56GHz_vs_bypass_dB':actual,
                     'DC_supply_current_A_positive_into_source':rail_currents,'input_DC_V':m['DC_voltage_V'],
                     'stationary_differential_input_noise_mVrms':1000*m['noise']['Vrms_1MHz_to_56GHz']})
    octaves = [(a,b) for a,b in zip(FREQUENCIES[-4:],FREQUENCIES[-3:])]
    return {'format':'pam4_selector_TT0_13_measured_v1','inputs':identity,'package_member_sha256':pins,
            'verified_runtime_decks':len(evidence),'verified_raw_retirement_inventory_entries':sum(x['raw_entries_bound'] for x in evidence.values()),
            'measured_cases':evidence,'selector':{'native_drawn_W_um':3.,'native_drawn_L_nm':30.,'nf':1,'multi':1,
                'MOS_instances':16,'TG_pairs':8,'selected_series_TG_per_leg':2,'Rs_per_leg_ohm':25.,'Rt_per_leg_ohm':25.,
                'VDD_V':.9,'common_mode_near_V':.7,'ladder_per_section':SECTION},'seven_paired_configs':rows,
            'equal_06_06_native_KCL':kcl,'equal_06_06_frequency_response':sweep,
            'equal_native_incremental_loss_dB_per_octave':{str(int(a))+'-'+str(int(b)):
                sweep[str(int(b))]['native_equal_trim_vs_bypass_dB']-sweep[str(int(a))]['native_equal_trim_vs_bypass_dB']
                for a,b in octaves},'mean_1kHz_selected_terminal_Ron_ohm':ron,
            'limits':{'Ron':'Low-frequency small-signal effective selected terminal drop divided by reconstructed exact passive ladder endpoint current. This is not a standalone transistor OP extraction.',
                      'Coff':'Off-route Im(Y)/omega and external selector-plane shunt values are apparent quantities. TG is multi-terminal; off route bias, cross-admittance and cancellation are included. No unique device Coff is identifiable from these probes.',
                      'DC':'The collector retained rail power, not direct DC branch currents. I=-P/V applies only to nonzero-voltage rails; zero-volt gate and relative stimulus-source DC currents are unobserved. AC source currents are measured per 1 V excitation.',
                      'network':'Model uses independently recovered complex r3+25ohm load from bypass and 1kHz Ron. Optional shunts illustrate limitations of lumping, not a claimed physical fit or a process-corner prediction.',
                      'scope':'TT fixed-bias AC only. No new simulator, PVT result or transistor mechanism isolation.'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name,(default,_) in INPUTS.items():
        parser.add_argument('--'+name,type=Path,default=default)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = analyze({name:getattr(args,name) for name in INPUTS})
    with args.output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(result,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
    print('Verified %d runtime decks and %d retired raw inventory entries' %
          (result['verified_runtime_decks'],result['verified_raw_retirement_inventory_entries']))


if __name__ == '__main__':
    main()
