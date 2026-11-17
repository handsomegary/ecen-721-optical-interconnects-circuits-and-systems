"""One physical scale, unchanged scoring/timing, renewed authorization and pins."""

from collections import Counter
from datetime import timedelta
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import sar7_compare_window as pilot


def blocks(lines):
    result={};name=None
    for line in lines:
        if line.startswith('subckt '):name=line.split()[1];result[name]=[]
        if name is not None:result[name].append(line)
        if line.startswith('ends '):name=None
    return result


class CompareWindowTests(unittest.TestCase):
    def test_exact_twelve_pulses_only_and_original_physical_design(self):
        old,_=pilot.parent.build(pilot.parent.case_record());new,_=pilot.build(pilot.case_record())
        prior=old.decode('ascii').splitlines();current=new.decode('ascii').splitlines()
        removed=list((Counter(prior)-Counter(current)).elements());added=list((Counter(current)-Counter(prior)).elements())
        self.assertEqual((len(removed),len(added)),(12,12))
        self.assertEqual({line.split()[0] for line in removed},{f'V_{kind}{bit}' for kind in ('trial','clk') for bit in range(1,7)})
        self.assertEqual({line.split()[0] for line in removed},{line.split()[0] for line in added})
        for name in ('V_trial0','V_clk0'):
            self.assertEqual(next(row for row in prior if row.startswith(name+' ')),next(row for row in current if row.startswith(name+' ')))
        old_by_name={line.split()[0]:line for line in removed}
        restored=[old_by_name.get(line.split()[0],line) for line in current]
        self.assertTrue(restored==prior,'Any change outside the12 original pulse rows is forbidden')
        self.assertTrue(blocks(prior)==blocks(current),'Physical cells or CDF cards changed')
        self.assertTrue([r for r in prior if r.startswith('save ')]==[r for r in current if r.startswith('save ')])

    def test_finite_trial_edges_start_at_previous_read_and_exact_budget(self):
        source,meta=pilot.build(pilot.case_record());schedule=pilot.timing_schedule()
        expected={6:(78,108,147,149),5:(147.5,192.5,236.5,238.5),4:(237,262,302,304),
            3:(302.5,328.5,368.5,370.5),2:(369,400,447,449),1:(447.5,455.5,499.5,501.5),0:(500,506,552,554)}
        self.assertEqual(schedule,expected)
        self.assertEqual(sum(pilot.WAITS)+sum(pilot.EVALS)+6*pilot.GUARD_PS,474)
        lines=source.decode('ascii').splitlines()
        for bit in range(6):
            row=next(line for line in lines if line.startswith(f'V_trial{bit} '))
            fields=dict(re.findall(r'\b(delay|rise|fall|width|period)=([^ ]+)',row))
            prior_read=schedule[bit+1][2]
            self.assertAlmostEqual(float(fields['delay'])/pilot.native.PS,prior_read)
            self.assertEqual(float(fields['rise']),pilot.native.EDGE)
            self.assertAlmostEqual(schedule[bit+1][3]-schedule[bit][0],1.5)
            self.assertAlmostEqual(schedule[bit+1][3]+.5-float(fields['delay'])/pilot.native.PS,2.5)
        self.assertEqual(meta['primary_readout_ps'],565)
        self.assertEqual(meta['wave']['conversions'][0]['trials'][-1]['read_s'],pilot.native.timing(552))

    def test_json_roundtrip_parent_pins_and_only_trial_metadata_changes(self):
        case=pilot.case_record();first,meta=pilot.build(case)
        second,again=pilot.build(json.loads(json.dumps(case)))
        self.assertEqual(first,second);self.assertEqual(meta,again)
        old,prior=pilot.parent.build(pilot.parent.case_record())
        self.assertEqual(hashlib.sha256(old).hexdigest(),pilot.PARENT_DECK_SHA)
        restored=json.loads(json.dumps(meta['wave']))
        for cv,oldcv in zip(restored['conversions'],prior['wave']['conversions'],strict=True):cv['trials']=oldcv['trials']
        self.assertEqual(restored,json.loads(json.dumps(prior['wave'])))
        self.assertEqual(meta['authorization']['max_solver_cases_this_packet'],1)
        self.assertFalse(meta['physical_changes'])
        self.assertFalse(case['schedule_unchanged'])
        for cv,oldcv in zip(meta['wave']['conversions'],prior['wave']['conversions'],strict=True):
            self.assertEqual(cv['trials'][-1],oldcv['trials'][-1])

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
        self.assertEqual(pilot.parent.rail_command([.9,0.,0.,.9],.9),'O')
        self.assertEqual(pilot.parent.rail_command([0.,.9,.9,0.],.9),'Z')
        measured={'screen_pass':True,'logic_smoke_pass':True}
        self.assertFalse(pilot.parent.parent.apply_physical_screen(measured,True,False)['screen_pass'])
        self.assertTrue(pilot.parent.parent.apply_physical_screen(measured,True,False)['logic_smoke_pass'])

    def test_all_new_payload_and_manifest_are_lf(self):
        for name in ('sar7_compare_window.py','sar7_compare_window.sbatch','test_sar7_compare_window.py','AUTHORIZATION.json','PLAN.json','HANDOFF_zh_TW.md','SHA256SUMS.txt'):
            content=(pilot.ROOT/name).read_bytes()
            self.assertNotIn(b'\r',content,name)
            self.assertTrue(content.endswith(b'\n'),name)

    def test_full_case19_selected_parser_144_nodes_84_trials_72_boundaries(self):
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
        q_parent=pilot.parent.parent;original_extras=q_parent.summarize.__globals__['EXTRA_SAVES']
        original_parent=pilot.parent.summarize.__globals__['parent']
        with ExitStack() as stack:
            stack.enter_context(patch.object(pilot.base,'evidence',return_value=(wave,status,hashes)))
            stack.enter_context(patch.object(pilot.common,'raw_inventory',return_value=inventory))
            stack.enter_context(patch.object(pilot.common,'sha',return_value='a'*64))
            stack.enter_context(patch.object(pilot.base.review,'parse_selected',side_effect=selected))
            stack.enter_context(patch.object(pilot.base.review,'safe_raw',side_effect=safe_raw))
            stack.enter_context(patch.object(pilot.base,'collect',side_effect=AssertionError('Summary must not recollect')))
            with self.assertRaisesRegex(KeyError,'trial6'):
                pilot.child_summary_function(q_parent.summarize)(report,Path('case19_root'),case,meta)
            self.assertNotIn('trial6',selected_sets[-1]);selected_sets.clear()
            result=pilot.summarize(report,Path('case19_root'),case,meta)
        self.assertEqual(len(selected_sets),1)
        self.assertEqual(len(selected_sets[0]),144)
        self.assertEqual(result['selected_parser']['summary_psf_parse_count'],1)
        self.assertIn('Separate inherited measurement',result['selected_parser']['basic_measurement_parse'])
        self.assertTrue(set(wave['saved_signals'])<=selected_sets[0])
        self.assertEqual(result['case_id'],pilot.CASE_ID)
        self.assertEqual(result['schema'],pilot.SCHEMA)
        self.assertEqual(len(result['timing']),84)
        self.assertEqual(result['overlap_diagnostic']['observed_within_conversion_boundaries'],72)
        self.assertEqual(result['overlap_diagnostic']['polarity_assessed_boundaries'],60)
        self.assertEqual(result['overlap_diagnostic']['polarity_unassessable_boundaries'],12)
        self.assertEqual(result['overlap_diagnostic']['prior_latch_opposite_rail_boundaries'],0)
        self.assertIn('active_last_read_cm_pass',result['readout_565'])
        self.assertIs(q_parent.summarize.__globals__['EXTRA_SAVES'],original_extras)
        self.assertIs(pilot.parent.summarize.__globals__['parent'],original_parent)



if __name__=='__main__':unittest.main()
