"""One impedance-scaled CML input stage; immutable SAR timing and original ADC gates."""

from array import array
from bisect import bisect_left, bisect_right
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import copy
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import sar7_cml_drive2 as pilot


def blocks(lines):
    result={};active=None
    for line in lines:
        if line.startswith('subckt '):active=line.split()[1];result[active]=[]
        if active is not None:result[active].append(line)
        if line.startswith('ends '):active=None
    return result


def top_rows(source,prefix):
    result={};inside=False
    for row in source.decode('ascii').splitlines():
        if row.startswith('subckt '):inside=True
        elif row.startswith('ends '):inside=False
        elif not inside and row.startswith(prefix):result[row.split()[0]]=row
    return result


class CMLDrive2Tests(unittest.TestCase):
    def test_exact_four_complete_cdf_replicas_three_resistors_and_nothing_else(self):
        old,_=pilot.parent.build(pilot.parent.case_record());new,meta=pilot.build(pilot.case_record())
        before=old.decode('ascii').splitlines();after=new.decode('ascii').splitlines()
        self.assertTrue(blocks(before)==blocks(after),'All existing cell/CDF blocks must remain exact')
        a,b=top_rows(old,'M'),top_rows(new,'M')
        originals={'MSENSE_P','MSENSE_N','MTAIL_P','MTAIL_N'}
        self.assertTrue(originals<=set(a))
        self.assertTrue(set(a)<=set(b))
        for name in a:self.assertTrue(a[name]==b[name],'Original top-level MOS card changed: '+name)
        added=set(b)-set(a);self.assertEqual(len(added),4)
        oldtails=Counter(a[name].split(' ',1)[1] for name in originals)
        newtails=Counter(b[name].split(' ',1)[1] for name in added)
        self.assertTrue(oldtails==newtails,'A complete CDF body/port/parameter was lost or changed')
        oldr,newr=top_rows(old,'R'),top_rows(new,'R')
        targets={'RSENSE_P':(500,250),'RSENSE_N':(500,250),'RSENSE_DEG':(250,125)}
        self.assertEqual(set(oldr),set(newr))
        for name,row in oldr.items():
            if name in targets:
                prior,current=targets[name]
                self.assertEqual(row.rsplit('r=',1)[1],str(prior))
                self.assertTrue(newr[name]==row.rsplit('r=',1)[0]+'r='+str(current),'Scaled resistor changed ports/role: '+name)
            else:self.assertTrue(row==newr[name],'Other resistor changed: '+name)
        removed=list((Counter(before)-Counter(after)).elements());inserted=list((Counter(after)-Counter(before)).elements())
        self.assertEqual((len(removed),len(inserted)),(3,7))
        restored=[]
        for row in after:
            label=row.split()[0] if row.split() else ''
            if label in added:continue
            restored.append(oldr[label] if label in targets else row)
        self.assertTrue(restored==before,'A source/save/clock/CMP port or other physical card changed')
        self.assertTrue(top_rows(old,'XCMP')==top_rows(new,'XCMP'),'Comparator ports changed')
        self.assertEqual([r for r in before if r.startswith('save ')],[r for r in after if r.startswith('save ')])
        self.assertFalse(any('diag_p' in row or 'diag_n' in row for row in after))
        self.assertTrue('V_SENSE_B (sbias 0) vsource dc=0.5' in after,'Frozen bias source changed')

    def test_missing_duplicate_wrong_mos_port_or_resistor_selector_is_rejected(self):
        source,_=pilot.parent.build(pilot.parent.case_record());lines=source.decode('ascii').splitlines()
        card=next(row for row in lines if row.startswith('MSENSE_P '))
        self.assertTrue('(sensen mp sem 0)' in card,'Original CML input ports differ')
        missing=lines.copy();missing.remove(card)
        wrong=[row.replace('(sensen mp sem 0)','(sensen mn sem 0)',1) if row==card else row for row in lines]
        bridge=next(row for row in lines if row.startswith('RSENSE_DEG '))
        changed_r=[row.rsplit('r=',1)[0]+'r=125' if row==bridge else row for row in lines]
        for name,rows in [('missing',missing),('duplicate',lines+[card]),('wrong_port',wrong),('already_scaled_R',changed_r)]:
            with self.subTest(mutation=name),self.assertRaises(Exception):pilot.physical_patch(('\n'.join(rows)+'\n').encode('ascii'))
        _,counts=pilot.physical_patch(source);self.assertIsInstance(counts,dict)

    def test_frozen_parent_bytes_full_waveform_timing_and_twelve_center_inputs(self):
        case=pilot.case_record();first,meta=pilot.build(case)
        second,again=pilot.build(json.loads(json.dumps(case)))
        self.assertTrue(first==second,'Deck generation changed on JSON roundtrip');self.assertTrue(meta==again,'Metadata changed on JSON roundtrip')
        old,prior=pilot.parent.build(pilot.parent.case_record())
        self.assertEqual(hashlib.sha256(old).hexdigest(),pilot.PARENT_DECK_SHA)
        self.assertTrue(meta['wave']==prior['wave'],'Every original clock/trial/stimulus/readpoint must remain exact')
        self.assertEqual(len(meta['wave']['conversions']),12)
        self.assertEqual(len(set(meta['wave']['saved_signals'])|{'time'}),144)
        self.assertFalse(meta['wave'].get('adc_scoring_applicable') is False)
        self.assertEqual(meta['authorization']['cpus_this_job'],1)
        with self.assertRaises(Exception):pilot.build(dict(case,case_id='unauthorized_other_physical_case'))
        rows=old.decode('ascii').splitlines();card=next(row for row in rows if row.startswith('M') and ' w=' in row)
        tampered=('\n'.join(row.replace(' w=',' w=2*',1) if row==card else row for row in rows)+'\n').encode('ascii')
        with patch.object(pilot.parent,'build',return_value=(tampered,prior)),self.assertRaises(Exception):pilot.build(case)


    def test_original_completeness_error_cm_agreement_and_physical_read_gates(self):
        self.assertEqual(pilot.SUMMARY_PARENT.rail_command([.9,0.,0.,.9],.9),'O')
        self.assertEqual(pilot.SUMMARY_PARENT.rail_command([0.,.9,.9,0.],.9),'Z')
        rows=[dict(expected_code=64,observed_comparator_code=64,observed_registered_code=64,
            trial_results=[dict(decision=1) for _ in range(7)]) for _ in range(12)]
        observed=[dict(expected_code=64,observed_registered_code=64) for _ in range(12)]
        self.assertTrue(pilot.Q_PARENT.screen(rows,observed,[0.,0.])['screen_pass'])
        bad=copy.deepcopy(rows);bad[0]['trial_results'][0]['decision']=None
        self.assertFalse(pilot.Q_PARENT.screen(bad,observed,[0.,0.])['screen_pass'])
        bad=copy.deepcopy(rows);bad[0]['observed_comparator_code']=None
        self.assertFalse(pilot.Q_PARENT.screen(bad,observed,[0.,0.])['screen_pass'])
        bad=copy.deepcopy(rows);bad[0]['observed_comparator_code']=63
        self.assertFalse(pilot.Q_PARENT.screen(bad,observed,[0.,0.])['screen_pass'])
        for codes in ([65]*7+[64]*5,[66]+[64]*11):
            bad=copy.deepcopy(rows);registered=[]
            for row,code in zip(bad,codes,strict=True):
                row['observed_comparator_code']=code;registered.append(dict(expected_code=64,observed_registered_code=code))
            self.assertFalse(pilot.Q_PARENT.screen(bad,registered,[0.,0.])['screen_pass'])
        self.assertFalse(pilot.Q_PARENT.screen(rows,observed,[10.0001,0.])['screen_pass'])
        measured=dict(screen_pass=True,logic_smoke_pass=True)
        for window,active_cm in [(False,True),(True,False)]:
            self.assertFalse(pilot.Q_PARENT.apply_physical_screen(measured,window,active_cm)['screen_pass'])

    def test_fresh_open_ended_authorization_and_exact_submit_time_binding(self):
        self.assertFalse(hasattr(pilot,'EXPIRES'))
        self.assertEqual(pilot.STARTS,datetime(2026,11,17,13,55,tzinfo=timezone.utc))
        self.assertTrue(pilot.AUTH_RECORD['no_expiry'])
        self.assertEqual(pilot.AUTH_RECORD['source_note'],'20261117T0755_user_delegates_sar7_papers_direction.md')
        self.assertEqual(pilot.AUTH_RECORD['source_note_sha256'],'d9491abfb1429caf097c1c798d763d6529264fb3fa9cbbf2b82cd78b0d4183ea')
        self.assertEqual(pilot.AUTH_RECORD['max_solver_cases_this_packet'],1)
        self.assertEqual(pilot.AUTH_RECORD['max_accepted_slurm_jobs'],1)
        self.assertEqual(pilot.AUTH_RECORD['max_concurrent_sar7_jobs'],1)
        now=pilot.STARTS+timedelta(days=2);pilot.check_started(now)
        with self.assertRaises(Exception):pilot.check_started(pilot.STARTS-timedelta(seconds=1))
        job='761900'
        def receipt(at):return f'JobId={job} SubmitTime={int(at.timestamp())}'
        record=pilot.validate_submission(receipt(now-timedelta(minutes=1)),job,now)
        self.assertEqual(record['slurm_job_id'],job)
        self.assertEqual(record['authorization_source_sha256'],pilot.AUTH_RECORD['source_note_sha256'])
        for at in (pilot.STARTS-timedelta(seconds=1),now+timedelta(seconds=1)):
            with self.assertRaises(Exception):pilot.validate_submission(receipt(at),job,now)
        for text in ('JobId=1 SubmitTime=1794900000',f'JobId={job} SubmitTime=Unknown',f'JobId={job} JobId={job} SubmitTime=0'):
            with self.assertRaises(Exception):pilot.validate_submission(text,job,now)

    def test_readonly_slurm_query_is_always_required_before_existing_stage(self):
        now=pilot.STARTS+timedelta(days=2);submitted=now-timedelta(minutes=1)
        class Receipt:stdout=f'JobId=761900 SubmitTime={int(submitted.timestamp())}'
        with patch.dict(pilot.os.environ,{'SLURM_JOB_ID':'761900'}),patch.object(pilot.subprocess,'run',return_value=Receipt()) as rpc:
            pilot.query_submission(now)
            args,kw=rpc.call_args;self.assertEqual(args[0],['scontrol','--oneliner','show','job','761900'])
            self.assertEqual(kw['env']['SLURM_TIME_FORMAT'],'%s');self.assertEqual(kw['timeout'],15)
            self.assertTrue(kw['check'] and kw['capture_output'] and kw['text']);rpc.assert_called_once()
        for bad in ('','761900_0','one;command'):
            with patch.dict(pilot.os.environ,{'SLURM_JOB_ID':bad}),patch.object(pilot.subprocess,'run') as rpc:
                with self.assertRaises(Exception):pilot.query_submission(now)
                rpc.assert_not_called()
        events=[];root=Path('unit_new_case23').absolute();case={'case_id':pilot.CASE_ID};proof={'job':'761900'}
        def query(at):events.append('query');return proof
        def stage(*args):events.append('stage');return root/pilot.CASE_ID
        with patch.object(pilot,'query_submission',side_effect=query) as query_rpc,patch.object(pilot,'existing_stage',side_effect=stage):
            directory,receipt=pilot.stage_for_run(root,case,Path('private'),now)
        self.assertEqual(events,['query','stage']);self.assertEqual(directory,root/pilot.CASE_ID)
        self.assertEqual(receipt,proof);query_rpc.assert_called_once_with(now)

    def test_cloned_execution_keeps_original_adc_collector_and_parent_globals(self):
        names=('build','PLAN','MANIFEST','SCHEMA','collect','stage','evidence')
        saved={name:pilot.base.run.__globals__[name] for name in names}
        namespace=pilot.execution_namespace()
        self.assertIs(namespace['build'],pilot.build)
        for name in ('PLAN','MANIFEST','SCHEMA'):self.assertEqual(namespace[name],getattr(pilot,name))
        for name in ('stage','evidence','collect'):
            self.assertTrue(namespace[name].__globals__ is namespace,'Execution function is not bound to own namespace: '+name)
            self.assertTrue(namespace[name].__code__ is getattr(pilot.base,name).__code__,'Original ADC function code changed: '+name)
        for name in names:self.assertTrue(pilot.base.run.__globals__[name] is saved[name],'Parent global changed: '+name)

    @staticmethod
    def summary_fixture():
        case=pilot.case_record();_,meta=pilot.build(case);wave=meta['wave']
        step=wave['strobe_s'];time=[i*step for i in range(int(wave['stop_s']/step)+1)]
        if time[-1]<wave['stop_s']:time.append(wave['stop_s'])
        zero=[0.]*len(time);high=[wave['vdd_V']]*len(time);cm=[.45]*len(time)
        values={node:zero for node in wave['saved_signals']};values['time']=time
        for node in wave['saved_signals']:
            if node.startswith('clk') or (node.startswith('bit') and not node.endswith('b')):values[node]=high
            if node.startswith('qmid') and node.endswith('n'):values[node]=high
            if node.startswith('q') and not node.startswith('qmid') and node.endswith('p'):values[node]=high
            if node.startswith('XCMP') and node.endswith('.y'):values[node]=high
            if node in wave['dac_pair'] or node in ('sensep','sensen'):values[node]=cm
            if (node.startswith('c') and not node.startswith('cb') and node.endswith('o')) or (node.startswith('cb') and node.endswith('z')):values[node]=high
        values['XCMP6.x']=cm;values['XCMP6.y']=cm
        values={node:array('d',trace) for node,trace in values.items()}
        digest='b'*64;inventory=[dict(path=pilot.base.review.RAW_NAME,sha256=digest,bytes=123)]
        hashes={'bench.scs':'c'*64,'spectre.log':'d'*64};status=dict(raw_inventory=inventory)
        rows=[]
        for cv in wave['conversions']:
            trials=[dict(bit=t['bit'],decision=1,stable_rail_delay_s=20*pilot.native.PS,
                compare_to_read_s=t['read_s']-t['compare_s']) for t in cv['trials']]
            rows.append(dict(index=cv['index'],scored=True,expected_code=cv['expected_code'],observed_comparator_code=127,
                observed_registered_code=127,sample_dac_common_mode_V=.45,trial_results=trials))
        report=dict(conversions=rows,tested_conversions=12,execution_files_sha256=hashes,tran_sha256=digest,
            max_abs_sample_error_lsb=0.,max_observed_resolve_delay_s=20e-12,slurm_task_id='761900',solver_seconds=1.,raw_bytes=123)
        return case,meta,wave,values,inventory,status,hashes,report

    def run_synthetic_summary(self,missing=False,changed_inventory=False):
        case,meta,wave,values,inventory,status,hashes,report=self.summary_fixture()
        if missing:values.pop('trial6')
        selected_sets=[];raw_values=[];diagnostic_values=[];directories=[];digest=inventory[0]['sha256']
        class Raw:
            sha256=digest;sweep_names=['time']
            def __init__(self,admitted):self.values=admitted
            def unit(self,node):return 's' if node=='time' else 'A' if node.endswith(':p') else 'V'
        def selected(path,required):
            selected_sets.append(set(required));raw=Raw({node:values[node] for node in required});raw_values.append(raw.values);return raw
        def safe_raw(directory,status,name,parser):return parser(Path('synthetic_new_case23_psf'))
        def evidence(case,directory):directories.append(directory);return wave,status,hashes
        original_diagnostic=pilot.cml_diagnostics
        def diagnostic(values,wave):diagnostic_values.append(values);return original_diagnostic(values,wave)
        live=[inventory,copy.deepcopy(inventory)]
        if changed_inventory:live[1][0]['sha256']='e'*64
        with ExitStack() as stack:
            stack.enter_context(patch.object(pilot,'execution_namespace',return_value={'evidence':evidence}))
            stack.enter_context(patch.object(pilot.common,'raw_inventory',side_effect=live))
            stack.enter_context(patch.object(pilot.common,'sha',return_value='a'*64))
            stack.enter_context(patch.object(pilot.base.review,'parse_selected',side_effect=selected))
            raw_read=stack.enter_context(patch.object(pilot.base.review,'safe_raw',side_effect=safe_raw))
            stack.enter_context(patch.object(pilot.base,'collect',side_effect=AssertionError('Summary must not recollect/rescore')))
            stack.enter_context(patch.object(pilot,'cml_diagnostics',side_effect=diagnostic))
            result=pilot.summarize(report,Path('unit_case23_root'),case,meta)
        return result,meta,selected_sets,raw_values,diagnostic_values,directories,raw_read.call_count

    def test_complete_adc_summary144_nodes84_trials72_boundaries_same_single_parse_for_cml(self):
        parent_extras=pilot.Q_PARENT.summarize.__globals__['EXTRA_SAVES']
        parent_link=pilot.SUMMARY_PARENT.summarize.__globals__['parent']
        result,meta,selected,raw_values,diagnostic_values,directories,reads=self.run_synthetic_summary()
        self.assertEqual(reads,1);self.assertEqual(len(selected),1);self.assertEqual(len(selected[0]),144)
        self.assertEqual(selected[0],{'time',*meta['wave']['saved_signals']})
        self.assertTrue(all(f'{prefix}{bit}' in selected[0] for prefix in ('clk','trial') for bit in range(7)))
        self.assertEqual(result['selected_parser']['summary_psf_parse_count'],1)
        self.assertIsInstance(raw_values[0]['time'],array)
        self.assertEqual(len(diagnostic_values),1);self.assertTrue(diagnostic_values[0] is raw_values[0],'CML diagnostics must reuse the same parsed data object')
        self.assertTrue(all(directory==Path('unit_case23_root')/pilot.CASE_ID for directory in directories))
        self.assertEqual(result['case_id'],pilot.CASE_ID);self.assertEqual(result['schema'],pilot.SCHEMA)
        self.assertEqual(result['provenance']['manifest_sha256'],'a'*64)
        self.assertEqual(result['provenance']['portable_deck_sha256'],meta['portable_sha256'])
        self.assertEqual(result['provenance']['parent_manifest_sha256'],pilot.PARENT_MANIFEST_SHA)
        self.assertEqual(result['provenance']['parent_portable_deck_sha256'],pilot.PARENT_DECK_SHA)
        self.assertEqual(result['provenance']['parent_reported_summary_sha256'],pilot.PARENT_SUMMARY_SHA)
        self.assertEqual(result['authorization'],pilot.AUTH_RECORD)
        self.assertEqual(len(result['timing']),84)
        self.assertEqual(result['overlap_diagnostic']['observed_within_conversion_boundaries'],72)
        self.assertEqual(result['overlap_diagnostic']['polarity_assessed_boundaries'],60)
        self.assertEqual(result['overlap_diagnostic']['polarity_unassessable_boundaries'],12)
        self.assertEqual(result['overlap_diagnostic']['prior_latch_opposite_rail_boundaries'],0)
        self.assertIn('screen_pass',result['readout_565']);self.assertNotIn('adc_screen_applicable',result)
        self.assertEqual(len(result['cml_diagnostic']['active_windows']),12)
        self.assertEqual(len(result['cml_diagnostic']['trial_phase_points']),84)
        self.assertTrue(pilot.Q_PARENT.summarize.__globals__['EXTRA_SAVES'] is parent_extras,'Original parser globals changed')
        self.assertTrue(pilot.SUMMARY_PARENT.summarize.__globals__['parent'] is parent_link,'Original summary parent changed')

    def test_missing_required_trial_trace_or_changed_source_inventory_is_rejected(self):
        with self.assertRaisesRegex(KeyError,'trial6'):self.run_synthetic_summary(missing=True)
        with self.assertRaisesRegex(ValueError,'Evidence changed|Execution evidence|changed during summary|Evidence/raw changed'):
            self.run_synthetic_summary(changed_inventory=True)

    def test_time_weighted_analytic_resistor_current_signed_source_power_and_units(self):
        _,meta=pilot.build(pilot.case_record());wave=meta['wave'];time=[];current=[]
        for cv in wave['conversions']:
            origin=cv['index']*wave['period_s']
            for phase in (0,50,100,300,560,568):
                at=origin+phase*pilot.native.PS
                if at<=wave['stop_s']:
                    time.append(at);current.append(.0004+.0002*(phase-78)/487)
        if time[-1]<wave['stop_s']:
            phase=(wave['stop_s']-(len(wave['conversions'])-1)*wave['period_s'])/pilot.native.PS
            time.append(wave['stop_s']);current.append(.0004+.0002*(phase-78)/487)
        held=.001;gain=.6;sense_cm=[pilot.SUPPLY_V-pilot.LOAD_OHM*i/2 for i in current]
        values={'time':array('d',time),'V_SENSE_DD:p':array('d',[-i for i in current]),
            'sensep':array('d',[cm+gain*held/2 for cm in sense_cm]),'sensen':array('d',[cm-gain*held/2 for cm in sense_cm]),
            wave['dac_pair'][0]:array('d',[.45+held/2]*len(time)),wave['dac_pair'][1]:array('d',[.45-held/2]*len(time))}
        report=pilot.cml_diagnostics(values,wave)
        self.assertEqual(report['active_window_ps'],[78,565]);self.assertEqual(len(report['active_windows']),12)
        self.assertEqual(report['trial_records'],84);self.assertEqual(len(report['trial_phase_points']),84)
        for window in report['active_windows']:
            self.assertAlmostEqual(window['mean_signed_source_current_A'],-.0005,delta=1e-13)
            self.assertAlmostEqual(window['mean_draw_current_A'],.0005,delta=1e-13)
            self.assertAlmostEqual(window['mean_supply_power_W'],.00045,delta=1e-13)
            self.assertAlmostEqual(window['supply_energy_J'],.00045*487*pilot.native.PS,delta=1e-22)
            self.assertAlmostEqual(window['minimum_draw_current_A'],.0004,delta=1e-13)
            self.assertAlmostEqual(window['maximum_draw_current_A'],.0006,delta=1e-13)
            self.assertLess(window['maximum_abs_analytical_minus_draw_A'],1e-14)
        for trial in report['trial_phase_points']:
            self.assertEqual(len(trial['phases']),7)
            for point in trial['phases'].values():
                self.assertAlmostEqual(point['held_diff_lsb'],held/wave['lsb_V'],places=10)
                self.assertAlmostEqual(point['sense_diff_lsb'],gain*held/wave['lsb_V'],places=10)
                self.assertAlmostEqual(point['analytical_load_current_A'],point['supply_draw_current_A'],delta=1e-14)
                self.assertAlmostEqual(point['supply_power_W'],-pilot.SUPPLY_V*point['signed_source_current_A'],delta=1e-15)
        # Reversing source-current sign must expose negative draw/power, never be hidden by abs().
        reversed_values=dict(values,**{'V_SENSE_DD:p':array('d',current)})
        reversed_report=pilot.cml_diagnostics(reversed_values,wave)
        self.assertAlmostEqual(reversed_report['active_windows'][0]['mean_draw_current_A'],-.0005,delta=1e-13)
        self.assertAlmostEqual(reversed_report['active_windows'][0]['mean_supply_power_W'],-.00045,delta=1e-13)
        self.assertGreater(reversed_report['active_windows'][0]['maximum_abs_analytical_minus_draw_A'],.001)
        missing=dict(values);missing.pop('V_SENSE_DD:p')
        with self.assertRaises(Exception):pilot.cml_diagnostics(missing,wave)

    def test_own_manifest_verify_and_all_new_payloads_lf(self):
        case,meta=pilot.verify();self.assertEqual(case['case_id'],pilot.CASE_ID)
        self.assertEqual(meta['authorization'],pilot.AUTH_RECORD)
        self.assertEqual(meta['parent_job'],'761700');self.assertFalse(meta['automatic_followup'])
        self.assertEqual(meta['changed_pulse_rows'],0)
        for name in sorted(pilot.FILES|{'SHA256SUMS.txt'}):
            content=(pilot.ROOT/name).read_bytes();self.assertNotIn(b'\r',content,name);self.assertTrue(content.endswith(b'\n'),name)



if __name__=='__main__':unittest.main()
