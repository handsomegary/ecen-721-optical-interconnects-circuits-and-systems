#!/usr/bin/env python3
"""Verify GMFINE compact provenance and classify static MOS headroom by role."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import tarfile
import zipfile


OUTPUTS = Path(__file__).resolve().parents[1]
RESULTS = OUTPUTS / 'pam4_pnskew_gmfine_20261113_results'
INPUTS = {
    'zip': (OUTPUTS/'ECEN721_PAM4_PNSKEW_GMFINE_20261113.zip','2e07095da94f2aae83581a0c7efe18b8a5089821e686f3d325cbf56e25614179'),
    'compact': (RESULTS/'olympus_compact_gmfine.tgz','396e2102c89464e65994d5e546a9c1f60afa4d1b7ba2e30157ffce7cb85bb2e9'),
    'summary': (RESULTS/'gmfine_summary.json','941a0f3b90e7d601a3803c538801790bfa9027791f4c3fdc365e0bfd2cade2df'),
}
ANALOG = {'AFE_input_active_bank', 'AFE_tail_enabled', 'follower_enabled',
          'original_stage1_input', 'original_stage1_tail', 'original_stage2_input', 'original_stage2_tail'}


def need(condition, detail):
    if not condition:
        raise ValueError(detail)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def apply_diff(parent, diff):
    """Apply retained hunks while checking all context and removed lines."""
    old = parent.splitlines(keepends=True)
    lines = diff.splitlines(keepends=True)
    need(lines[:2] == ['--- parent.scs\n', '+++ bench.scs\n'], 'Unexpected diff headers')
    output, used = [], 0
    for line in lines[2:]:
        if line.startswith('@@'):
            hit = re.match(r'@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@', line)
            need(hit is not None, 'Unexpected hunk')
            start = int(hit[1])-1
            need(used <= start <= len(old), 'Invalid hunk offset')
            output.extend(old[used:start])
            used = start
        elif line[0] in ' -':
            need(used < len(old) and old[used] == line[1:], 'Diff context differs')
            if line[0] == ' ':
                output.append(line[1:])
            used += 1
        else:
            need(line.startswith('+'), 'Unexpected diff line')
            output.append(line[1:])
    return ''.join(output+old[used:])


def classify(name, nodes, case):
    count = {'A':8-case['count_b'],'B':case['count_b']}
    match = re.fullmatch(r'GMS([AB])([PM])(M|T|F|CL)(\d+)',name)
    if match:
        bank,leg,device,index = match.groups()
        bank_count = count[bank]
        if device=='M':
            # Every input M in that bank shares one source node. Its own index
            # does not determine whether it conducts, unlike each tail T.
            return 'AFE_input_active_bank' if bank_count else 'AFE_input_dormant_bank'
        if device=='T':
            enabled = int(index)<bank_count
            expected_gate = 'GMS%sVB%s'%(bank,index) if case['mode'] in ('driver','driver_open','bias') else ('X_vb' if enabled else '0')
            need(nodes[1]==expected_gate,'Tail bias wiring differs: '+name)
            return 'AFE_tail_enabled' if enabled else 'AFE_tail_disabled'
        if device=='F':
            need(nodes[0]=='GF_VDD','Unexpected follower topology: '+name)
            return 'follower_enabled' if bank_count else 'follower_disabled'
        on = case['mode']=='driver' and not bank_count
        need(nodes[1]==('GF_CTL' if on else '0'),'Unexpected follower clamp gate: '+name)
        return 'follower_clamp_on' if on else 'follower_clamp_off'
    match = re.fullmatch(r'GMS([AB])(IN|IP|BN|BP|BD)(\d+)',name)
    if match:
        bank,device,index = match.groups()
        enabled = int(index)<count[bank]
        on = enabled if device in ('IN','BN','BP') else not enabled
        labels = {'IN':'bias_inverter_pull_down_N','IP':'bias_inverter_pull_up_P',
                  'BN':'bias_transfer_N','BP':'bias_transfer_P','BD':'bias_discharge_N'}
        return labels[device]+('_commanded_on' if on else '_commanded_off')
    match = re.fullmatch(r'X([MT])([12])[pm]\d+',name)
    if match:
        device,stage = match.groups()
        return 'original_stage'+stage+('_input' if device=='M' else '_tail')
    raise ValueError('Unknown device role: '+name)


def measurements(archive, package, summary):
    manifest = dict((name,digest) for digest,name in
                    (line.split('  ',1) for line in package.read('SHA256SUMS.txt').decode().splitlines()))
    need(set(manifest)==set(package.namelist())-{'SHA256SUMS.txt'},'ZIP manifest census differs')
    for name,digest in manifest.items():
        need(sha(package.read(name))==digest,'ZIP payload hash differs: '+name)
    plan=json.loads(package.read('case_plan.json'))['cases']
    parent=package.read('pvt/cases/nominal_parent.scs.txt').decode('ascii')
    members=[m.name for m in archive.getmembers() if m.isfile()]
    need(len(set(members))==len(members) and len(plan)==92 and
         {n for n in members if n.endswith('/measurements.json')}=={'run/'+c['case_id']+'/measurements.json' for c in plan},
         'Compact case census differs')
    existing = {(r['process'],r['mode'],r['count_b'],tuple(map(tuple,r['routes'])),r['probe']):r
                for r in summary['paired_rows']}
    op_rows,headroom,raw_count,raw_bytes = [],collections.defaultdict(list),0,0
    names=('case.json','measurements.json','run_status.json','completion.json','raw_retirement_manual_20261113.json')
    wanted={'run/'+case['case_id']+'/'+name for case in plan for name in names+('spectre.log','parent_diff.txt')}
    payload={member.name:archive.extractfile(member).read() for member in archive.getmembers()
             if member.isfile() and member.name in wanted}
    need(set(payload)==wanted,'Missing compact source proof')
    for expected in plan:
        prefix='run/'+expected['case_id']+'/'
        def read(name):
            return payload[prefix+name]
        files={name:read(name) for name in names}
        case,report,status,completion,retirement=[json.loads(files[n]) for n in names]
        need(all(case[k]==v for k,v in expected.items()) and
             case['case_id']==report['case_id']==status['case_id']==retirement['case'],'Case identity mismatch')
        need(report['measurement_complete'] is completion['measurement_complete'] is True and
             sha(files['measurements.json'])==completion['measurement_sha256']==retirement['measurement_sha256'],
             'Completion/retirement hash mismatch')
        need(sha(files['case.json'])==status['case_sha256'] and sha(files['run_status.json'])==report['run_status_sha256'] and
             status['plan_sha256']==manifest['case_plan.json'] and status['status']=='spectre_completed' and
             status['exit_code']==0 and status['solver_mode']=='classic' and status['cpus_allocated']==1 and
             status['simulator_build']=='23.1.0.722.isr15' and sha(read('spectre.log'))==status['spectre_log_sha256'],
             'Runner/plan/log hash or status mismatch')
        diff=read('parent_diff.txt')
        need(sha(diff)==case['staged_source_sha256']['parent_diff.txt'],'Runtime parent diff differs')
        deck=apply_diff(parent.replace('__pdk_root__',case['model_preflight']['model_root']),diff.decode('ascii'))
        bench_sha=sha(deck.encode('ascii'))
        need(bench_sha==status['input_deck_sha256_before']==status['input_deck_sha256_after']==
             report['bench_sha256']==case['staged_source_sha256']['bench.scs'],'Exact reconstructed deck SHA differs')
        inventory={r['path']:(r['bytes'],r['sha256']) for r in status['raw_inventory']}
        removed={r['path']:(r['bytes'],r['sha256']) for r in retirement['removed']}
        need(inventory==removed and len(inventory)==len(status['raw_inventory'])==len(retirement['removed']),
             'Retirement inventory differs')
        raw_count+=len(removed)
        raw_bytes+=sum(v[0] for v in removed.values())
        mos={name:(nodes.split(),model[0].lower()) for name,nodes,model in
             re.findall(r'^(\w+) \(([^\r\n)]+)\) ([np]ch_\w+)\b',deck,re.M)}
        matched=existing[(case['process'],case['mode'],case['count_b'],tuple(map(tuple,(case['route_a'],case['route_b']))),case['probe'])]
        negatives, roles = [],collections.Counter()
        for name,op in report['saved_mos_oppoint'].items():
            if 'vds' not in op or 'vdsat' not in op:
                continue
            need(name in mos,'MOS OP instance absent from exact deck: '+name)
            nodes,polarity=mos[name]
            role=classify(name,nodes,case)
            signed=op['vds']-op['vdsat']
            margin=signed if polarity=='n' else -signed
            if case['drive']=='p':
                need(signed==matched['saved_saturation_margins_V'][name],'Saved summary OP does not match compact result')
            roles[role]+=1
            detail={'instance':name,'role':role,'polarity':polarity,'gate':nodes[1],
                    'raw_vds_minus_vdsat_V':signed,'polarity_corrected_margin_V':margin,
                    'vds_V':op['vds'],'vdsat_V':op['vdsat'],'vgs_V':op.get('vgs'),'vth_V':op.get('vth'),
                    'ids_A':op.get('ids'),'model_region_code':op.get('region')}
            headroom[(case['process'],role)].append(dict(detail,case_id=case['case_id']))
            if signed<0 or margin<0:
                negatives.append(detail)
        need(bool(roles),'No MOS OP evidence')
        op_rows.append({'case_id':case['case_id'],'process':case['process'],'mode':case['mode'],
                        'count_b':case['count_b'],'probe':case['probe'],'drive':case['drive'],
                        'bench_sha256_reconstructed':bench_sha,'role_counts':dict(roles),'negative_rows':negatives})
    census={}
    for (corner,role),rows in sorted(headroom.items()):
        census.setdefault(corner,{})[role]={
            'instances_across_columns':len(rows),
            'raw_signed_negative_count':sum(x['raw_vds_minus_vdsat_V']<0 for x in rows),
            'polarity_corrected_negative_count':sum(x['polarity_corrected_margin_V']<0 for x in rows),
            'minimum_raw_signed':min(rows,key=lambda x:x['raw_vds_minus_vdsat_V']),
            'minimum_polarity_corrected':min(rows,key=lambda x:x['polarity_corrected_margin_V'])}
    return op_rows,census,{'manifest_files':len(manifest),'reconstructed_runtime_decks':len(op_rows),
                          'raw_retirement_files':raw_count,'raw_retirement_bytes':raw_bytes}


def analyze():
    inputs={}
    for label,(path,pin) in INPUTS.items():
        need(sha(path.read_bytes())==pin,'Pinned input differs: '+label)
        inputs[label]={'file':path.name,'sha256':pin}
    summary=json.loads(INPUTS['summary'][0].read_bytes())
    need(not summary['missing_cases'] and not summary['invalid_cases'] and len(summary['paired_rows'])==46,
         'Compact summary incomplete')
    with tarfile.open(INPUTS['compact'][0],'r:gz') as archive,zipfile.ZipFile(INPUTS['zip'][0]) as package:
        op,census,counts=measurements(archive,package,summary)
    responses=[]
    for row in summary['paired_rows']:
        if row['mode'] not in ('driver','interpolation','muted') or row['probe']!='full' or row['count_b'] not in (0,2,8):
            continue
        delay=row['AFE_column_delay_diagnostic']['bands']['7_to_56_GHz']
        responses.append({'process':row['process'],'mode':row['mode'],'count_b':row['count_b'],'routes':row['routes'],
                          'tau_ps':delay['tau_effective_ps'],'phase_rms_ps':delay['weighted_phase_rms_ps'],
                          'Hdd_56GHz_vs_matched_bypass_dB':row['AFE_56GHz_vs_matched_bypass']['Hdd_vs_bypass_dB'],
                          'power_mW':sum(row['DC_supply_power_W'].values())*1e3})
    return {'format':'pam4_gmfine_operating_point_audit_v1','inputs':inputs,'verification':counts,
            'role_summary_by_corner':census,'case_negative_rows':op,'response_examples_from_pinned_summary':responses,
            'analog_roles_checked':sorted(ANALOG),
            'any_negative_in_analog_roles':any(v['polarity_corrected_negative_count'] for corner in census.values()
                                              for role,v in corner.items() if role in ANALOG),
            'interpretation':{'polarity':'NMOS VDS−VDSAT; PMOS VSD−|VDSAT| for saved signed PMOS VDS/VDSAT. This is meaningful for conducting amplifying devices only.',
                              'switches':'ON bias pass, inverter pull-down/up, discharge and clamp roles are switches; low VDS and triode operation are expected. Command state is not a claim both pass devices conduct strongly.',
                              'shared_source':'All input M devices share their bank source. Tail count determines bank activity and individual T state. M index alone cannot label a unit off.',
                              'scope':'Static saved operating point and existing AC summary; no claim about dynamic saturation, swings or transistor OP fields not exported.'}}


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
