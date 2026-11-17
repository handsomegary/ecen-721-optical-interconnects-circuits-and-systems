"""One physical-design-frozen timing probe with complete provenance and original scoring gates."""

from collections import Counter
from datetime import timedelta
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import sar7_accept_gap as pilot


def blocks(lines):
    result={};name=None
    for line in lines:
        if line.startswith('subckt '):name=line.split()[1];result[name]=[]
        if name is not None:result[name].append(line)
        if line.startswith('ends '):name=None
    return result


class AcceptGapTests(unittest.TestCase):
    def test_exact_ten_pulse_rows_and_no_physical_input_or_save_changes(self):
        old,_=pilot.parent.build(pilot.parent.case_record());new,meta=pilot.build(pilot.case_record())
        before=old.decode('ascii').splitlines();after=new.decode('ascii').splitlines()
        removed=list((Counter(before)-Counter(after)).elements())
        added=list((Counter(after)-Counter(before)).elements())
        expected={f'V_trial{bit}' for bit in range(1,7)}|{f'V_clk{bit}' for bit in range(2,6)}
        self.assertEqual((len(removed),len(added)),(10,10))
        self.assertEqual({row.split()[0] for row in removed},expected)
        self.assertEqual({row.split()[0] for row in added},expected)
        by_name={row.split()[0]:row for row in removed}
        restored=[by_name.get(row.split()[0],row) if row.split() else row for row in after]
        self.assertTrue(restored==before,'Any physical cell/card/port/source/save or nonselected pulse changed')
        self.assertTrue(blocks(before)==blocks(after),'An existing subckt or MOS card changed')
        self.assertEqual([row for row in before if row.startswith('save ')],[row for row in after if row.startswith('save ')])
        for name in ['V_trial0','V_clk0','V_clk1','V_clk6']:
            self.assertEqual(next(row for row in before if row.startswith(name+' ')),next(row for row in after if row.startswith(name+' ')))
        self.assertEqual(meta['changed_pulse_rows'],10)
        self.assertFalse(meta['physical_changes'])

    def test_frozen_parent_bytes_and_case_cannot_be_replaced(self):
        case=pilot.case_record()
        with self.assertRaises(Exception):pilot.build(dict(case,case_id='unauthorized_alternative'))
        source,meta=pilot.parent.build(pilot.parent.case_record())
        self.assertEqual(hashlib.sha256(source).hexdigest(),pilot.PARENT_DECK_SHA)
        lines=source.decode('ascii').splitlines()
        # Change a real non-pulse design line while retaining parent metadata to detect blind trust of that metadata.
        card=next(row for row in lines if row.startswith('M') and ' w=' in row)
        modified=card.replace(' w=',' w=2*',1)
        tampered=('\n'.join(modified if row==card else row for row in lines)+'\n').encode('ascii')
        with patch.object(pilot.parent,'build',return_value=(tampered,meta)),self.assertRaises(Exception):
            pilot.build(case)

    def test_finite_trial_edges_budget_and_fixed_b1_compare_b0(self):
        source,meta=pilot.build(pilot.case_record());schedule=pilot.timing_schedule()
        expected={6:(78,108,143,145),5:(143.5,188.5,232.5,234.5),4:(233,258,298,300),
            3:(298.5,324.5,364.5,366.5),2:(365,396,440,442),1:(440.5,453.5,497.5,499.5),0:(498,504,552,554)}
        self.assertEqual(pilot.WAITS,(30,45,25,26,31,13,6))
        self.assertEqual(pilot.EVALS,(35,44,40,40,44,44,48))
        self.assertEqual(schedule,expected)
        self.assertEqual(sum(pilot.WAITS)+sum(pilot.EVALS)+6*pilot.GUARD_PS,474)
        self.assertEqual(schedule[1][1:],pilot.parent.timing_schedule()[1][1:])
        self.assertEqual(schedule[0],pilot.parent.timing_schedule()[0])
        self.assertEqual(schedule[1][1]-schedule[2][3],11.5)
        lines=source.decode('ascii').splitlines()
        for bit in range(6):
            row=next(line for line in lines if line.startswith(f'V_trial{bit} '))
            fields=dict(re.findall(r'\b(delay|rise|fall|width|period)=([^ ]+)',row))
            self.assertAlmostEqual(float(fields['delay'])/pilot.native.PS,schedule[bit+1][2])
            self.assertEqual(float(fields['rise']),pilot.native.EDGE)
            self.assertAlmostEqual(schedule[bit+1][3]-schedule[bit][0],1.5)
        self.assertEqual(meta['primary_readout_ps'],565)
        self.assertEqual(meta['wave']['conversions'][0]['trials'][-1]['read_s'],pilot.native.timing(552))
        self.assertEqual(meta['wave']['conversions'][0]['trials'][-1]['trial_release_s'],pilot.native.timing(554))

    def test_roundtrip_parent_pins_and_only_trial_wave_metadata_changes(self):
        case=pilot.case_record();first,meta=pilot.build(case)
        second,again=pilot.build(json.loads(json.dumps(case)))
        self.assertEqual(first,second);self.assertEqual(meta,again)
        old,prior=pilot.parent.build(pilot.parent.case_record())
        self.assertEqual(hashlib.sha256(old).hexdigest(),pilot.PARENT_DECK_SHA)
        restored=json.loads(json.dumps(meta['wave']))
        for cv,oldcv in zip(restored['conversions'],prior['wave']['conversions'],strict=True):cv['trials']=oldcv['trials']
        self.assertEqual(restored,json.loads(json.dumps(prior['wave'])))
        self.assertEqual(meta['authorization']['max_solver_cases_this_packet'],1)
        self.assertEqual(meta['authorization']['cpus_this_job'],1)
        self.assertEqual(meta['authorization']['max_concurrent_sar7_cpus'],2)
        self.assertEqual(meta['parent_job'],'761688')
        self.assertFalse(meta['physical_changes'])

    def test_renewed_deadline_allows_now_after_old_expiry(self):
        now=pilot.STARTS+timedelta(minutes=5)
        pilot.check_stage_deadline(now)
        with patch.object(pilot,'query_preexpiry_slurm_submission') as query,patch.object(pilot.parent,'check_run_submission',side_effect=AssertionError('Old deadline called')):
            self.assertIsNone(pilot.check_run_submission(now));query.assert_not_called()
        for bad in (pilot.STARTS-timedelta(seconds=1),pilot.EXPIRES):
            with self.assertRaises(Exception):pilot.check_stage_deadline(bad)

    def test_queued_submit_time_exact_job_and_new_cutoff(self):
        now=pilot.EXPIRES+timedelta(minutes=5);job='761600'
        def receipt(at):return f'JobId={job} SubmitTime={int(at.timestamp())} Other=value'
        record=pilot.validate_submission(receipt(pilot.EXPIRES-timedelta(seconds=1)),job,now)
        self.assertEqual(record['slurm_job_id'],job)
        for at in (pilot.STARTS-timedelta(seconds=1),pilot.EXPIRES,pilot.EXPIRES+timedelta(seconds=1)):
            with self.assertRaises(Exception):pilot.validate_submission(receipt(at),job,now)
        for text in ('JobId=1 SubmitTime=1794890000',f'JobId={job} SubmitTime=Unknown',f'JobId={job} JobId={job} SubmitTime=0'):
            with self.assertRaises(Exception):pilot.validate_submission(text,job,now)

    def test_postexpiry_queries_once_and_only_reads_existing_stage(self):
        root=Path('newroot').absolute();case={'case_id':pilot.CASE_ID};now=pilot.EXPIRES+timedelta(seconds=1)
        with patch.object(pilot,'query_preexpiry_slurm_submission',return_value={'ok':True}) as query,patch.object(pilot,'existing_stage',return_value=root/pilot.CASE_ID) as existing,patch.object(pilot.base,'stage') as stage:
            self.assertEqual(pilot.stage_for_run(root,case,Path('private'),now),root/pilot.CASE_ID)
            query.assert_called_once_with(now);existing.assert_called_once();stage.assert_not_called()
        with patch.dict(pilot.os.environ,{'SLURM_JOB_ID':''}),patch.object(pilot.subprocess,'run') as rpc:
            with self.assertRaises(Exception):pilot.query_preexpiry_slurm_submission(now)
            rpc.assert_not_called()

    def test_rpc_is_one_readonly_call_with_epoch_format(self):
        now=pilot.EXPIRES+timedelta(seconds=1);at=pilot.EXPIRES-timedelta(seconds=10)
        class Receipt:stdout=f'JobId=761600 SubmitTime={int(at.timestamp())}'
        with patch.dict(pilot.os.environ,{'SLURM_JOB_ID':'761600'}),patch.object(pilot.subprocess,'run',return_value=Receipt()) as rpc:
            pilot.query_preexpiry_slurm_submission(now)
            args,kw=rpc.call_args;self.assertEqual(args[0],['scontrol','--oneliner','show','job','761600'])
            self.assertEqual(kw['env']['SLURM_TIME_FORMAT'],'%s');self.assertEqual(kw['timeout'],15)
            self.assertTrue(kw['check'] and kw['capture_output'] and kw['text']);rpc.assert_called_once()

    def test_nested_verify_after_binding_and_summary_own_directory(self):
        saved=pilot.base.build,pilot.base.PLAN,pilot.base.MANIFEST,pilot.base.SCHEMA
        try:
            pilot.base.build,pilot.base.PLAN,pilot.base.MANIFEST,pilot.base.SCHEMA=pilot.build,pilot.PLAN,pilot.MANIFEST,pilot.SCHEMA
            case,meta=pilot.verify();self.assertEqual(case['case_id'],pilot.CASE_ID)
            parent_id=pilot.parent.CASE_ID
            with patch.object(pilot.base,'evidence',side_effect=RuntimeError('stop before raw parse')) as evidence:
                with self.assertRaises(RuntimeError):pilot.summarize({},Path('root'),case,meta)
                self.assertEqual(evidence.call_args.args[1],Path('root')/pilot.CASE_ID)
            self.assertEqual(pilot.parent.CASE_ID,parent_id)
        finally:pilot.base.build,pilot.base.PLAN,pilot.base.MANIFEST,pilot.base.SCHEMA=saved

    def test_command_polarity_and_physical_gate_not_relaxed(self):
        self.assertEqual(pilot.SUMMARY_PARENT.rail_command([.9,0.,0.,.9],.9),'O')
        self.assertEqual(pilot.SUMMARY_PARENT.rail_command([0.,.9,.9,0.],.9),'Z')
        measured={'screen_pass':True,'logic_smoke_pass':True}
        self.assertFalse(pilot.Q_PARENT.apply_physical_screen(measured,True,False)['screen_pass'])
        self.assertTrue(pilot.Q_PARENT.apply_physical_screen(measured,True,False)['logic_smoke_pass'])

    def test_original_completeness_error_and_agreement_gates(self):
        rows=[dict(expected_code=64,observed_comparator_code=64,observed_registered_code=64,
            trial_results=[dict(decision=1) for _ in range(7)]) for _ in range(12)]
        observed=[dict(expected_code=64,observed_registered_code=64) for _ in range(12)]; cm=[0.,0.]
        self.assertTrue(pilot.Q_PARENT.screen(rows,observed,cm)['screen_pass'])
        bad=json.loads(json.dumps(rows));bad[0]['trial_results'][0]['decision']=None
        self.assertFalse(pilot.Q_PARENT.screen(bad,observed,cm)['screen_pass'])
        bad=json.loads(json.dumps(rows));bad[0]['observed_comparator_code']=None
        self.assertFalse(pilot.Q_PARENT.screen(bad,observed,cm)['screen_pass'])
        bad=json.loads(json.dumps(rows));bad[0]['observed_comparator_code']=63
        self.assertFalse(pilot.Q_PARENT.screen(bad,observed,cm)['screen_pass'])
        seven_wrong=[65]*7+[64]*5
        bad=json.loads(json.dumps(rows))
        for row,value in zip(bad,seven_wrong,strict=True):row['observed_comparator_code']=value
        bad_registered=[dict(expected_code=64,observed_registered_code=value) for value in seven_wrong]
        self.assertFalse(pilot.Q_PARENT.screen(bad,bad_registered,cm)['screen_pass'])
        one_2lsb=[66]+[64]*11
        bad=json.loads(json.dumps(rows));bad[0]['observed_comparator_code']=66
        bad_registered=[dict(expected_code=64,observed_registered_code=value) for value in one_2lsb]
        self.assertFalse(pilot.Q_PARENT.screen(bad,bad_registered,cm)['screen_pass'])
        self.assertFalse(pilot.Q_PARENT.screen(rows,observed,[10.0001,0.])['screen_pass'])

    def test_final_trailing_acceptance_and_unavailable_msb_half_are_not_overcredited(self):
        ps=pilot.native.PS
        def bit2(index,runs):
            return dict(conversion=index,bit=2,q_buffer=dict(raw_stable_rail_delay_ps=40.,reference_path=dict(
                wanted_accepted_command='Z',phase_observations={'release':{'at_s':100*ps}},
                following_compare_s=110*ps,postrelease_command_runs=runs)))
        def run(command,start,end):return dict(command=command,start_s=start*ps,end_s=end*ps,samples=2)
        # An early Z glitch cannot earn the final Z arrival; the trailing wanted run starts at +4ps.
        rows=[bit2(0,[run('Z',100.5,101),run('O',101.25,103.75),run('Z',104,120)]),
              bit2(1,[run('Z',100.5,101),run('O',101.25,120)])]
        for index,edges in [(0,[(-1.,'rise'),(20.,'fall'),(40.,'rise')]),(1,[])]:
            rows.append(dict(conversion=index,bit=6,decision=1,sampled_margin_ps=2.,q_buffer=dict(
                raw_stable_rail_delay_ps=33.,reference_path=dict(wanted_accepted_command='O',
                phase_observations={'release':{'at_s':37*ps},'compare_plus_0ps':{'at_s':0.}},
                postrelease_command_runs=[run('O',37.25,80)],accepted_command_margin_before_next_compare_ps=30.,
                extended_half_vdd_crossings_ps={'qdecode6p':edges}))))
        result=pilot.acceptance_diagnostics({'timing':rows},{})
        self.assertEqual(result['b2_Z_command_count'],2)
        self.assertEqual(result['b2_Z_unconfirmed_count'],1)
        self.assertAlmostEqual(result['b2_latest_Z_arrival_after_release_ps'],4.)
        self.assertAlmostEqual(result['b2_all_conversions'][0]['margin_before_next_compare_ps'],6.)
        self.assertFalse(result['b2_all_conversions'][1]['trailing_command_confirmed'])
        self.assertIsNone(result['b2_all_conversions'][1]['final_arrival_after_release_ps'])
        self.assertIsNone(result['b2_all_conversions'][1]['margin_before_next_compare_ps'])
        self.assertEqual(result['msb_O_count'],2)
        self.assertEqual(result['msb_O_half_unavailable_count'],1)
        self.assertAlmostEqual(result['msb_latest_O_qdecode_half_from_compare_ps'],40.)
        self.assertAlmostEqual(result['msb_latest_O_qdecode_half_after_release_ps'],3.)

    def test_all_new_payload_and_manifest_are_lf(self):
        for name in ('sar7_accept_gap.py','sar7_accept_gap.sbatch','test_sar7_accept_gap.py','AUTHORIZATION.json','PLAN.json','HANDOFF_zh_TW.md','SHA256SUMS.txt'):
            content=(pilot.ROOT/name).read_bytes()
            self.assertNotIn(b'\r',content,name)
            self.assertTrue(content.endswith(b'\n'),name)

    def test_full_case21_selected_parser_144_nodes_84_trials_72_boundaries(self):
        case=pilot.case_record();_,meta=pilot.build(case);wave=meta['wave']
        step=wave['strobe_s'];count=int(wave['stop_s']/step)
        time=[i*step for i in range(count+1)]
        if time[-1]<wave['stop_s']:time.append(wave['stop_s'])
        zero=[0.]*len(time);high=[wave['vdd_V']]*len(time);cm=[.45]*len(time)
        values={node:zero for node in wave['saved_signals']};values['time']=time
        for node in wave['saved_signals']:
            if node.startswith('clk') or (node.startswith('bit') and not node.endswith('b')):values[node]=high
            if node.startswith('qmid') and node.endswith('n'):values[node]=high
            if node.startswith('q') and not node.startswith('qmid') and node.endswith('p'):values[node]=high
            if node.startswith('XCMP') and node.endswith('.y'):values[node]=high
            if node in wave['dac_pair'] or node in ('sensep','sensen'):values[node]=cm
            if node.startswith('c') and not node.startswith('cb') and node.endswith('o') or node.startswith('cb') and node.endswith('z'):values[node]=high
        # Deliberately unassessable prior-b6 polarity checks that None is not reported as stable.
        values['XCMP6.x']=cm;values['XCMP6.y']=cm
        digest='b'*64;inventory=[dict(path=pilot.base.review.RAW_NAME,sha256=digest,bytes=123)]
        hashes={'bench.scs':'c'*64,'spectre.log':'d'*64};status=dict(raw_inventory=inventory)
        rows=[]
        for cv in wave['conversions']:
            trials=[dict(bit=t['bit'],decision=1,stable_rail_delay_s=20*pilot.native.PS,
                compare_to_read_s=t['read_s']-t['compare_s']) for t in cv['trials']]
            rows.append(dict(index=cv['index'],scored=True,expected_code=cv['expected_code'],
                observed_comparator_code=127,observed_registered_code=127,sample_dac_common_mode_V=.45,trial_results=trials))
        report=dict(conversions=rows,tested_conversions=12,execution_files_sha256=hashes,tran_sha256=digest,
            max_abs_sample_error_lsb=0.,max_observed_resolve_delay_s=20e-12,slurm_task_id='fixture',solver_seconds=1.,raw_bytes=123)
        selected_sets=[]
        class Raw:
            sha256=digest;sweep_names=['time']
            def __init__(self,admitted):self.values=admitted
            def unit(self,key):return 's' if key=='time' else 'A' if key.endswith(':p') else 'V'
        def selected(path,required):
            selected_sets.append(set(required));self.assertTrue(set(required)<=set(values))
            return Raw({key:values[key] for key in required})
        def safe_raw(directory,status,name,parser):return parser(Path('existing_fixture'))
        q_parent=pilot.Q_PARENT;original_extras=q_parent.summarize.__globals__['EXTRA_SAVES']
        original_parent=pilot.SUMMARY_PARENT.summarize.__globals__['parent']
        with ExitStack() as stack:
            stack.enter_context(patch.object(pilot.base,'evidence',return_value=(wave,status,hashes)))
            stack.enter_context(patch.object(pilot.common,'raw_inventory',return_value=inventory))
            stack.enter_context(patch.object(pilot.common,'sha',return_value='a'*64))
            stack.enter_context(patch.object(pilot.base.review,'parse_selected',side_effect=selected))
            stack.enter_context(patch.object(pilot.base.review,'safe_raw',side_effect=safe_raw))
            stack.enter_context(patch.object(pilot.base,'collect',side_effect=AssertionError('Summary must not recollect')))
            with self.assertRaisesRegex(KeyError,'trial6'):
                pilot.child_summary_function(q_parent.summarize)(report,Path('case21_root'),case,meta)
            self.assertNotIn('trial6',selected_sets[-1]);selected_sets.clear()
            result=pilot.summarize(report,Path('case21_root'),case,meta)
        self.assertEqual(len(selected_sets),1)
        self.assertEqual(len(selected_sets[0]),144)
        self.assertEqual(result['selected_parser']['summary_psf_parse_count'],1)
        self.assertIn('Separate inherited measurement',result['selected_parser']['basic_measurement_parse'])
        self.assertTrue(set(wave['saved_signals'])<=selected_sets[0])
        self.assertEqual(result['case_id'],pilot.CASE_ID)
        self.assertEqual(result['schema'],pilot.SCHEMA)
        self.assertEqual(result['authorization'],pilot.AUTH_RECORD)
        self.assertEqual(result['provenance']['manifest_sha256'],'a'*64)
        self.assertEqual(result['provenance']['portable_deck_sha256'],meta['portable_sha256'])
        self.assertEqual(result['provenance']['parent_manifest_sha256'],pilot.PARENT_MANIFEST_SHA)
        self.assertEqual(result['provenance']['parent_portable_deck_sha256'],pilot.PARENT_DECK_SHA)
        self.assertEqual(result['provenance']['parent_reported_summary_sha256'],pilot.PARENT_SUMMARY_SHA)
        self.assertEqual(len(result['timing']),84)
        self.assertEqual(result['overlap_diagnostic']['observed_within_conversion_boundaries'],72)
        self.assertEqual(result['overlap_diagnostic']['polarity_assessed_boundaries'],60)
        self.assertEqual(result['overlap_diagnostic']['polarity_unassessable_boundaries'],12)
        self.assertEqual(result['overlap_diagnostic']['prior_latch_opposite_rail_boundaries'],0)
        self.assertIn('active_last_read_cm_pass',result['readout_565'])
        self.assertIs(q_parent.summarize.__globals__['EXTRA_SAVES'],original_extras)
        self.assertIs(pilot.SUMMARY_PARENT.summarize.__globals__['parent'],original_parent)



if __name__=='__main__':unittest.main()
