"""One physical scale, unchanged scoring/timing, renewed authorization and pins."""

from collections import Counter
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import sar7_read_overlap as pilot


def blocks(lines):
    result={};name=None
    for line in lines:
        if line.startswith('subckt '):name=line.split()[1];result[name]=[]
        if name is not None:result[name].append(line)
        if line.startswith('ends '):name=None
    return result


class ReadOverlapTests(unittest.TestCase):
    def test_exact_twelve_pulses_only_and_original_physical_design(self):
        old,_=pilot.parent.build(pilot.parent.case_record());new,_=pilot.build(pilot.case_record())
        prior=old.decode('ascii').splitlines();current=new.decode('ascii').splitlines()
        removed=list((Counter(prior)-Counter(current)).elements());added=list((Counter(current)-Counter(prior)).elements())
        self.assertEqual((len(removed),len(added)),(12,12))
        self.assertEqual({line.split()[0] for line in removed},{f'V_{kind}{bit}' for kind in ('trial','clk') for bit in range(6)})
        self.assertEqual({line.split()[0] for line in removed},{line.split()[0] for line in added})
        old_by_name={line.split()[0]:line for line in removed}
        restored=[old_by_name.get(line.split()[0],line) for line in current]
        self.assertTrue(restored==prior,'Any change outside the12 original pulse rows is forbidden')
        self.assertTrue(blocks(prior)==blocks(current),'Physical cells or CDF cards changed')
        self.assertTrue([r for r in prior if r.startswith('save ')]==[r for r in current if r.startswith('save ')])

    def test_finite_trial_edges_start_at_previous_read_and_exact_budget(self):
        source,meta=pilot.build(pilot.case_record());schedule=pilot.timing_schedule()
        expected={6:(78,120,159,161),5:(159.5,204.5,248.5,250.5),4:(249,274,314,316),
            3:(314.5,340.5,380.5,382.5),2:(381,412,450,452),1:(450.5,458.5,499.5,501.5),0:(500,506,552,554)}
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
        self.assertEqual(pilot.rail_command([.9,0.,0.,.9],.9),'O')
        self.assertEqual(pilot.rail_command([0.,.9,.9,0.],.9),'Z')
        measured={'screen_pass':True,'logic_smoke_pass':True}
        self.assertFalse(pilot.parent.apply_physical_screen(measured,True,False)['screen_pass'])
        self.assertTrue(pilot.parent.apply_physical_screen(measured,True,False)['logic_smoke_pass'])

    def test_collector_extended_window_and_accepted_command_margin(self):
        _,meta=pilot.build(pilot.case_record());wave=meta['wave'];cv=wave['conversions'][0];trial=cv['trials'][0]
        time=[i*pilot.native.PS/4 for i in range(2801)]
        values={node:[0.]*len(time) for node in wave['saved_signals']}
        for node in ('q6p','qmid6n','qdecode6p','bit6','c6o','cb6z'):
            values[node]=[.9]*len(time)
        result=pilot.q_buffer_detail(values,time,cv,trial,wave)['reference_path']
        self.assertAlmostEqual(result['accepted_command_margin_before_next_compare_ps'],43.5)
        self.assertEqual(result['wanted_accepted_command'],'O')
        self.assertEqual(result['phase_observations']['victim_compare']['command'],'O')
        self.assertEqual(result['extended_window_end_s'],cv['trials'][1]['read_s'])
        self.assertAlmostEqual(result['postrelease_command_runs'][-1]['end_s']/pilot.native.PS,248.5)
        self.assertIn('victim_compare_plus_30ps',result['phase_observations'])
        self.assertGreater(result['extended_window_end_s'],cv['trials'][1]['launch_s'])
        self.assertAlmostEqual(result['phase_observations']['compare_plus_15ps']['ps_from_compare'],15.)

    def test_prior_latch_observations_use_actual_edge_and_inverted_xy_polarity(self):
        _,meta=pilot.build(pilot.case_record());wave=meta['wave'];cv=wave['conversions'][0]
        time=[i*pilot.native.PS/4 for i in range(2801)]
        values={node:[0.]*len(time) for node in wave['saved_signals']}
        for node in ('XCMP6.y','q6p','qmid6n','qdecode6p','bit6','c6o','cb6z'):
            values[node]=[.9]*len(time)
        result=pilot.q_buffer_detail(values,time,cv,cv['trials'][1],wave)['prior_latch_during_overlap']
        self.assertEqual(result['initial_internal_class'],1)
        self.assertEqual(result['prior_internal_unresolved_samples'],0)
        self.assertEqual(result['prior_internal_opposite_rail_samples'],0)
        self.assertAlmostEqual(result['edge_start_minus_previous_read_ps'],0.)
        self.assertAlmostEqual(result['previous_release_minus_new_midpoint_ps'],1.5)
        self.assertAlmostEqual(result['previous_fall_end_minus_new_rise_start_ps'],2.5)
        self.assertAlmostEqual(result['observations']['new_trial_edge_start']['at_s']/pilot.native.PS,159.)


if __name__=='__main__':unittest.main()
