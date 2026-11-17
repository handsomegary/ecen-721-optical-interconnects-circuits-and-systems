#!/usr/bin/env python3
"""Audit pinned GMSELECT compact results and regenerate GM_EVIDENCE.json."""
import argparse
import cmath
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import tarfile
import zipfile

OUTPUTS = Path(__file__).resolve().parents[1]
BASE = OUTPUTS / 'pam4_pnskew_gmselect_20261113_results'
INPUTS = {
    'package': (OUTPUTS / 'ECEN721_PAM4_PNSKEW_GMSELECT_20261113.zip', '51268ada6d19e22f8bee0d721149eb08c9a5915aa4149f6dedf09de0e8d756d7'),
    'archive': (BASE / 'olympus_compact_gmselect.tgz', 'e1bf72c2a782f8ec48ef218aecb283327796ece0573aeae1e122122efee4b366'),
    'summary': (BASE / 'gmselect_summary.json', '920a67351006cbe0906edf6aba50661a62887a81a895731aecc491bc5428dbe4'),
}
KEYS = ('process','temperature_C','vdd_V','variant','route_a','route_b','active')
BAND = '7_to_56_GHz'
TARGET = .5 / 112e9 * 1e12


def need(value, detail):
    if not value:
        raise ValueError(detail)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def db(value):
    return 20 * math.log10(abs(value))


def equal(left, right, label):
    need(math.isclose(left,right,rel_tol=1e-10,abs_tol=1e-10), 'Summary mismatch: '+label)


def key(row):
    return tuple(tuple(row[k]) if isinstance(row[k],list) else row[k] for k in KEYS) + (
        row.get('off_probe',row.get('dormant_only_probe')),)


def load_helpers(package):
    selector_audit = OUTPUTS / 'PAM4_PNSKEW_SELECTOR_20261113/extract_selector.py'
    payload = selector_audit.read_bytes()
    need(sha(payload)=='c224e048e4e801f9cdf61c269199ae3c99fb92388d450864f6e3a470d6856546','Prior diff-reader changed')
    spec = importlib.util.spec_from_file_location('_selector_diff_audit',selector_audit)
    diff = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diff)
    source = OUTPUTS / 'PAM4_PNSKEW_GMSELECT_20261113'
    for member in ('weighted_delay.py','summarize_acnext.py','ac_next.py','comp_measure.py','comp_cell.py','olympus_common.py',
                   'pilot_controller.py','native/admit.py','native/pn_stage.py','native/collect_r5.py','pvt/model_preflight.py','pvt/generate.py'):
        need((source/member).read_bytes()==package.read(member), 'Unpinned helper: '+member)
    sys.path.insert(0,str(source))
    import summarize_acnext as modal
    import weighted_delay
    from comp_measure import at
    return diff.apply_diff,modal,weighted_delay,at


def read_archive(package, archive, apply_diff):
    manifest = dict((name,digest) for digest,name in
                    (line.split('  ',1) for line in package.read('SHA256SUMS.txt').decode().splitlines()))
    need(set(manifest)==set(package.namelist())-{'SHA256SUMS.txt'},'Package manifest census differs')
    for name,digest in manifest.items():
        need(sha(package.read(name))==digest,'Package member changed: '+name)
    plan = json.loads(package.read('case_plan.json'))['cases']
    parent = package.read('pvt/cases/nominal_parent.scs.txt').decode('ascii')
    available = {m.name for m in archive.getmembers() if m.isfile()}
    need(len(plan)==48 and len(available)==sum(m.isfile() for m in archive.getmembers()),'Archive census differs')
    need({n for n in available if n.endswith('/measurements.json')}==
         {'run/'+c['case_id']+'/measurements.json' for c in plan},'Unexpected measured cases')
    groups, receipt_entries, receipt_bytes, runtime, hashes = {},0,0,[],{}
    for expected in plan:
        prefix = 'run/'+expected['case_id']+'/'
        def get(name):
            need(prefix+name in available,'Missing compact file: '+prefix+name)
            return archive.extractfile(prefix+name).read()
        names = ('case.json','measurements.json','run_status.json','completion.json','raw_retirement_manual_20261113.json')
        data = {name:get(name) for name in names}
        case,meas,status,done,retire = [json.loads(data[n]) for n in names]
        need(all(case[k]==v for k,v in expected.items()) and case['case_id']==meas['case_id']==
             status['case_id']==retire['case']==expected['case_id'],'Case binding differs')
        need(status['plan_sha256']==manifest['case_plan.json'] and status['case_sha256']==sha(data['case.json']) and
             meas['run_status_sha256']==sha(data['run_status.json']),'Plan/case/runner binding differs')
        need(meas['measurement_complete'] is done['measurement_complete'] is True and
             done['measurement_sha256']==retire['measurement_sha256']==sha(data['measurements.json']),
             'Measurement/retirement binding differs')
        log,diff = get('spectre.log'),get('parent_diff.txt')
        need(status['status']=='spectre_completed' and status['exit_code']==0 and status['solver_mode']=='classic' and
             status['cpus_allocated']==1 and status['simulator_build']=='23.1.0.722.isr15' and
             status['spectre_log_sha256']==sha(log) and re.search(rb'(?mi)^\s*spectre completes with\s+0\s+errors\b',log),
             'Solver proof differs')
        need(sha(diff)==case['staged_source_sha256']['parent_diff.txt'],'Deck diff SHA differs')
        deck = apply_diff(parent.replace('__pdk_root__',case['model_preflight']['model_root']),diff.decode('ascii'))
        need(sha(deck.encode('ascii'))==status['input_deck_sha256_before']==status['input_deck_sha256_after']==
             meas['bench_sha256']==case['staged_source_sha256']['bench.scs'],'Reconstructed runtime deck SHA differs')
        if case['off_probe']:
            active = case['active'].upper()
            dormant = 'B' if active=='A' else 'A'
            for bank, gain in ((active,0),(dormant,1)):
                for leg in 'PM':
                    prefix_ = 'GMS'+bank+leg
                    need(re.search(r'^'+prefix_+r'DRV .* vcvs gain='+str(gain)+r'$',deck,re.M), 'Dormant-only launch differs')
        inventory = {r['path']:(r['bytes'],r['sha256']) for r in status['raw_inventory']}
        removed = {r['path']:(r['bytes'],r['sha256']) for r in retire['removed']}
        need(inventory==removed and len(inventory)==len(status['raw_inventory'])==len(retire['removed']),'Raw receipt differs')
        receipt_entries += len(inventory)
        receipt_bytes += sum(r[0] for r in inventory.values())
        runtime.append(status['spectre_wall_seconds'])
        hashes[expected['case_id']] = meas['bench_sha256']
        groups.setdefault(key(case),{})[case['drive']] = meas
    need(len(groups)==24 and all(set(p)=={'p','n'} for p in groups.values()),'P/N pair census differs')
    return groups, {'manifest_files':len(manifest),'exact_runtime_decks':len(hashes),
        'retired_raw_files':receipt_entries,'retired_raw_logical_bytes':receipt_bytes,
        'solver_wall_s_min_max':[min(runtime),max(runtime)],'case_plan_sha256':manifest['case_plan.json']}


def phasors(modal, at, pair):
    matrix = modal.matrix(pair,('X_o_p','X_o_m'))
    return modal.modes([at(pair['p']['frequency_Hz'],row,56e9) for row in zip(*matrix)])


def analyze():
    inputs = {}
    for name,(path,digest) in INPUTS.items():
        need(sha(path.read_bytes())==digest,'Wrong pinned input: '+name)
        inputs[name]={'file':path.name,'bytes':path.stat().st_size,'sha256':digest}
    original = json.loads(INPUTS['summary'][0].read_bytes())
    need(not original['invalid_cases'] and not original['missing_cases'],'Existing summary incomplete')
    with zipfile.ZipFile(INPUTS['package'][0]) as package, tarfile.open(INPUTS['archive'][0],'r:gz') as archive:
        apply_diff,modal,delay,at=load_helpers(package)
        groups,verify=read_archive(package,archive,apply_diff)
    rows, dormant_rows = [],[]
    for reference in original['paired_rows']:
        signature=key(reference)
        process,temp,vdd,variant,a,b,active,off=signature
        current=groups[signature]
        bypass=groups[(process,temp,vdd,'bypass',(0,0),(0,0),'a',False)]
        base=phasors(modal,at,bypass)
        observed=phasors(modal,at,current)
        meta={k:reference[k] for k in KEYS}
        if off:
            full=phasors(modal,at,groups[signature[:-1]+(False,)])
            selected=tuple(u-v for u,v in zip(full,observed))
            from_summary=reference['dormant_to_full_AFE_DM_at_56']
            equal(db(observed[0]/full[0]),from_summary['Hdd_vs_bypass_dB'],'off/full DM')
            equal(abs(observed[1]-full[1])/abs(full[0]),from_summary['Hdc_increment_over_abs_Hdd_bypass'],'off-minus-full Hdc')
            equal(db(selected[0]/base[0]),reference['selected_only_AFE_56GHz_by_linear_subtraction']['Hdd_vs_bypass_dB'],'selected subtraction')
            dormant_rows.append(dict(meta, full_Hdd_vs_same_bypass_dB=db(full[0]/base[0]),
                dormant_Hdd_vs_full_dB=db(observed[0]/full[0]),dormant_Hdd_vs_same_bypass_dB=db(observed[0]/base[0]),
                selected_complex_subtraction_Hdd_vs_same_bypass_dB=db(selected[0]/base[0]),
                dormant_DM_fraction_of_full=abs(observed[0]/full[0]),dormant_DM_fraction_of_selected=abs(observed[0]/selected[0]),
                dormant_vs_selected_DM_phase_deg=math.degrees(cmath.phase(observed[0]/selected[0])),
                dormant_Hdc_over_abs_Hdd_same_bypass=abs(observed[1]/base[0]),
                dormant_Hdc_over_abs_Hdd_full=abs(observed[1]/full[0]),
                off_minus_full_Hdc_over_abs_Hdd_full=abs(observed[1]-full[1])/abs(full[0])))
            continue
        record=current['p']
        reference_record=bypass['p']
        fs=record['frequency_Hz']
        active_gates=('X_ip','X_im') if variant.startswith('bypass') else ('GMS'+active.upper()+'PG','GMS'+active.upper()+'MG')
        computed=delay.evaluate(fs,modal.matrix(current,active_gates),modal.matrix(bypass,('X_ip','X_im')),
                                modal.matrix(bypass,('X_h0p','X_h0m')))['bands'][BAND]
        d={k:computed[k] for k in ('tau_effective_ps','weighted_phase_rms_ps','worst_phase_error_ps',
                                    'signed_phase_delay_error_at_56_GHz_ps')}
        for k,v in d.items():
            equal(v,reference['gate_delay']['bands'][BAND][k],k)
        gain=db(observed[0]/base[0])
        equal(gain,reference['AFE_56GHz_vs_same_termination_bypass']['Hdd_vs_bypass_dB'],'AFE 56GHz gain')
        need(record['noise']==reference['stationary_noise'] and record['DC_supply_power_W']==reference['DC_supply_power_W'],
             'Power/noise compact binding differs')
        output=modal.matrix(current,('X_o_p','X_o_m'))
        control=modal.matrix(bypass,('X_o_p','X_o_m'))
        corrections={str(sign*TARGET):modal.plane56(fs,modal.cancel_input_skew(fs,output,sign*TARGET),control) for sign in (-1,1)}
        for shift,values in corrections.items():
            for metric,val in values.items():
                equal(val,reference['AFE_known_input_skew_56GHz_diagnostic'][shift][metric],'known-skew '+metric)
        power=sum(record['DC_supply_power_W'].values())
        base_power=sum(reference_record['DC_supply_power_W'].values())
        noise=record['noise']['Vrms_1MHz_to_56GHz']
        base_noise=reference_record['noise']['Vrms_1MHz_to_56GHz']
        inactive='B' if active=='a' else 'A'
        off_tails=[v for name,v in record['DC_current_A'].items() if name.startswith('GMS'+inactive) and name.endswith('VT:p')]
        rows.append(dict(meta, **d, Hdd_56GHz_vs_same_bypass_dB=gain,
            Hdd_56GHz_vs_original_unterminated_dB=reference.get('AFE_56GHz_vs_original_unterminated',{}).get('Hdd_vs_bypass_dB'),
            static_schematic_rail_power_mW=power*1e3,static_rail_power_change_vs_same_bypass_nW=(power-base_power)*1e9,
            stationary_tracking_noise_mVrms=noise*1e3,stationary_tracking_noise_bypass_mVrms=base_noise*1e3,
            stationary_tracking_noise_delta_percent=100*(noise/base_noise-1),
            dormant_tail_total_nA=sum(off_tails)*1e9 if off_tails else None,
            known_input_skew_AC_diagnostic=corrections))
    return {'format':'pam4_gmselect_independent_readback_v1','inputs':inputs,'verification':verify,
            'weighted_band':BAND,'signed_target_each_side_ps':TARGET,
            'cases':rows,'TT_dormant_only_probes':dormant_rows,
            'limits':{'dormant_normalization':'The existing off/full dB uses full enabled Hdd, not bypass. Off-minus-full Hdc includes removed selected response, not dormant conversion.',
                'plane':'Power is static ideal-bias schematic rail power; launch driver power is unmeasured. Noise is stationary fixed-track h0p-h0m, 1 MHz–56 GHz.',
                'fine_resolution':'The ±2.10 ps intermediate fixed routes are sparse demonstration points. No fine step, monotone dense codebook, residual qualification or transient SER was measured.',
                'gain_reference':'Same-termination bypass has Rs=Rt=25 ohm per leg. Only TT has an original 0-ohm unterminated bypass comparison.',
                'leakage_scope':'OFF-only transfer was measured in TT. SS/FF dormant tail DC current is available, not dormant AC leakage.'}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=analyze()
    with args.output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')


if __name__=='__main__':
    main()
