"""One physical scale, unchanged scoring/timing, renewed authorization and pins."""

from collections import Counter
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import sar7_refpath2 as pilot


def blocks(lines):
    result={};name=None
    for line in lines:
        if line.startswith('subckt '):name=line.split()[1];result[name]=[]
        if name is not None:result[name].append(line)
        if line.startswith('ends '):name=None
    return result


class RefPathTests(unittest.TestCase):
    def test_exact_local_instance_delta_and_no_global_cell_changes(self):
        prior,_=pilot.parent.build(pilot.parent.case_record());new,_=pilot.build(pilot.case_record())
        old=prior.decode('ascii').splitlines();current=new.decode('ascii').splitlines()
        before,after=blocks(old),blocks(current)
        self.assertEqual(set(after)-set(before),{'SAR_REFTG2','SAR_OAI21_RP2','SAR_NOR3_RP2','SAR_NDINV4'})
        for name,rows in before.items():self.assertTrue(rows==after[name],'Original cell changed: '+name)
        restored=[];skip=False
        for line in current:
            if line.startswith('subckt ') and line.split()[1] not in before:skip=True
            if skip:
                if line.startswith('ends '):skip=False
                continue
            for newcell,oldcell in [('SAR_REFTG2','SAR_TG'),('SAR_OAI21_RP2','SAR_OAI21_X2'),('SAR_NOR3_RP2','SAR_NOR3_P3'),('SAR_NDINV4','SAR_NDINV2')]:
                if line.endswith(' '+newcell):line=line[:-len(newcell)]+oldcell
            restored.append(line)
        self.assertTrue(restored==old,'Changes escaped permitted instance cells/local definitions')
        self.assertEqual(sum((Counter(old)-Counter(current)).values()),126)
        self.assertEqual(sum(line.startswith('XQIN') and line.endswith(' SAR_INV') for line in current),14)
        self.assertEqual(sum(line.startswith('XQOUT') and line.endswith(' SAR_NDINV4') for line in current),14)
        self.assertEqual(sum(line.startswith('X') and line.endswith(' SAR_REFTG2') for line in current),56)

    def test_full_cdf_copies_replicas_and_mirror_port_identity(self):
        old,_=pilot.parent.build(pilot.parent.case_record());new,_=pilot.build(pilot.case_record())
        a,b=blocks(old.decode('ascii').splitlines()),blocks(new.decode('ascii').splitlines())
        for original,scaled in [('SAR_TG','SAR_REFTG2'),('SAR_OAI21_X2','SAR_OAI21_RP2'),('SAR_NOR3_P3','SAR_NOR3_RP2'),('SAR_NDINV2','SAR_NDINV4')]:
            oldcards=Counter(line.split(' ',1)[1] for line in a[original][1:-1])
            newcards=Counter(line.split(' ',1)[1] for line in b[scaled][1:-1])
            self.assertTrue(newcards==Counter({card:count*2 for card,count in oldcards.items()}),'CDF role/pins/card changed')
        def top_ports(source):
            out={};inside=False
            for line in source.decode('ascii').splitlines():
                if line.startswith('subckt '):inside=True
                if line.startswith('ends '):inside=False;continue
                if not inside and line.startswith('X'):out[line.split()[0]]=line.split('(',1)[1].split(')',1)[0]
            return out
        self.assertTrue(top_ports(old)==top_ports(new),'A port, q fanout or mirrored branch changed')

    def test_json_roundtrip_parent_pin_and_identical_waveform(self):
        case=pilot.case_record();first,meta=pilot.build(case)
        second,again=pilot.build(json.loads(json.dumps(case)))
        self.assertEqual(first,second);self.assertEqual(meta,again)
        old,prior=pilot.parent.build(pilot.parent.case_record())
        self.assertEqual(hashlib.sha256(old).hexdigest(),pilot.PARENT_DECK_SHA)
        self.assertEqual(meta['wave'],prior['wave'])
        self.assertEqual(meta['schedule_ps'],prior['schedule_ps'])
        self.assertEqual(meta['primary_readout_ps'],565)
        self.assertEqual(meta['authorization']['max_solver_cases_this_packet'],1)

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
        self.assertAlmostEqual(result['accepted_command_margin_before_next_compare_ps'],46.)
        self.assertEqual(result['wanted_accepted_command'],'O')
        self.assertEqual(result['phase_observations']['victim_compare']['command'],'O')
        self.assertEqual(result['extended_window_end_s'],cv['trials'][1]['read_s'])
        self.assertAlmostEqual(result['postrelease_command_runs'][-1]['end_s']/pilot.native.PS,251.)
        self.assertIn('victim_compare_plus_30ps',result['phase_observations'])
        self.assertGreater(result['extended_window_end_s'],cv['trials'][1]['launch_s'])
        self.assertAlmostEqual(result['phase_observations']['compare_plus_15ps']['ps_from_compare'],15.)


if __name__=='__main__':unittest.main()
