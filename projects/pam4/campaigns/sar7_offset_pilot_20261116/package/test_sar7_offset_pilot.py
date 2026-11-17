"""Check independent electrical changes, measured gates, probe names and deadline policy."""

import copy
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import sar7_offset_pilot as pilot


class OffsetPilotTest(TestCase):
    def without_probes(self,bench):
        probes={node for pair in pilot.INTERNAL_PAIRS.values() for node in pair}
        rows=[]
        for line in bench.decode('ascii').splitlines():
            if line.startswith('save '):
                line=' '.join(part for part in line.split() if part not in probes)
            rows.append(line)
        return rows

    def test_independent_cases_have_only_the_fixed_electrical_differences(self):
        old,old_meta=pilot.parent.build(pilot.original_case())
        old_rows=old.decode('ascii').splitlines()
        cases=pilot.plan_cases()
        self.assertEqual(len(cases),2)
        first,first_meta=pilot.build(cases[0])
        rows=self.without_probes(first)
        dummy=[line for line in rows if line.startswith('XQCOMPLOAD')]
        self.assertEqual(set(dummy),{f'XQCOMPLOAD{bit} (trial{bit} q{bit}n dqload{bit} vdd) SAR_NOR'
                                     for bit in range(7)})
        self.assertEqual([line for line in rows if line not in dummy],old_rows)
        second,second_meta=pilot.build(cases[1])
        rows=self.without_probes(second)
        self.assertFalse(any(line.startswith('XQCOMPLOAD') for line in rows))
        changes=[(a,b) for a,b in zip(old_rows,rows,strict=True) if a!=b]
        self.assertEqual([a.split()[0] for a,b in changes],['RSENSE_P','RSENSE_N'])
        self.assertEqual([b.rsplit('r=',1)[1] for a,b in changes],['498.5','501.5'])
        for meta in (first_meta,second_meta):
            wave=copy.deepcopy(meta['wave'])
            wave.pop('internal_regeneration_pairs');wave.pop('internal_regeneration_sign')
            probes={node for pair in pilot.INTERNAL_PAIRS.values() for node in pair}
            wave['saved_signals']=[node for node in wave['saved_signals'] if node not in probes]
            self.assertEqual(wave,old_meta['wave'])

    def test_probe_nodes_are_the_actual_internal_nodes_before_the_output_inverters(self):
        pilot.confirm_internal_nodes()
        case=pilot.plan_cases()[0]
        bench,meta=pilot.build(case)
        saved=next(line.split()[1:] for line in bench.decode('ascii').splitlines() if line.startswith('save '))
        self.assertEqual(meta['wave']['internal_regeneration_pairs'],
                         {str(bit):[f'XCMP{bit}.x',f'XCMP{bit}.y'] for bit in range(6,-1,-1)})
        for pair in pilot.INTERNAL_PAIRS.values():
            for node in pair:
                self.assertEqual(saved.count(node),1)

    def test_input_cdac_or_unapproved_trim_changes_are_rejected(self):
        for alter in ('input','cdac','trim'):
            case=copy.deepcopy(pilot.plan_cases()[1])
            if alter=='input':case['input_cm_V']+=.01
            elif alter=='cdac':case['correction']['reference_span_V']+=.001
            else:case['offset_fix']['rsense_n_ohm']=502.
            with self.assertRaises(ValueError):pilot.build(case)

    def test_gate_allows_only_target_or_nonworse_valid_case_zero(self):
        def summary(peak,total,valid=True,cm=4):
            return dict(valid=valid,final_cm_change_mV=[-cm,-cm],
                        comparator=dict(max_abs_code_error=peak,sum_abs_code_error=total),
                        registered=dict(max_abs_code_error=peak,sum_abs_code_error=total))
        for result,expected in ((summary(1,12),'STOP_TARGET'),(summary(2,7),'ALLOW_INDEX1'),
                                (summary(2,8),'STOP_REVIEW'),(summary(3,7),'STOP_REVIEW'),
                                (summary(1,1,False),'STOP_REVIEW'),(summary(1,1,cm=10.001),'STOP_REVIEW')):
            self.assertEqual(pilot.gate_recommendation(result)['recommendation'],expected)
        for reason in ('STOP_TARGET','STOP_REVIEW'):
            with patch.object(pilot,'measured_gate',return_value={'recommendation':reason}):
                with self.assertRaises(ValueError):
                    pilot.require_index1_gate(Path('/campaign'),pilot.plan_cases())

    def test_missing_or_inconsistent_registered_codes_are_not_valid(self):
        case=pilot.plan_cases()[0]
        rows=[]
        for index,code in enumerate(case['pattern_codes']):
            rows.append(dict(index=index,scored=True,expected_code=code,
                observed_comparator_code=code,observed_registered_code=code,
                final_dac_common_mode_change_from_sample_V=-.004,
                trial_results=[dict(bit=bit,decision=(code>>bit)&1) for bit in range(6,-1,-1)]))
        report=dict(conversions=rows,tested_conversions=12,case=case,tran_sha256='a'*64,
            slurm_task_id='123',max_abs_sample_error_lsb=1.,max_observed_resolve_delay_s=45e-12,
            logic_smoke_pass=True,solver_seconds=180,raw_bytes=1000,execution_files_sha256={})
        sense=dict(pairs=84,tran_sha256='a'*64)
        with patch.object(pilot.common,'sha',return_value='b'*64):
            self.assertTrue(pilot.summarize(report,sense,Path('/campaign'),0,case)['valid'])
            for changed in (None,63):
                altered=copy.deepcopy(report)
                altered['conversions'][0]['observed_registered_code']=changed
                self.assertFalse(pilot.summarize(altered,sense,Path('/campaign'),0,case)['valid'])
            altered=copy.deepcopy(report)
            altered['conversions'][0]['trial_results'][0]['decision']=None
            self.assertFalse(pilot.summarize(altered,sense,Path('/campaign'),0,case)['valid'])

    def test_threshold_interval_is_descriptive_and_detects_nonseparable_data(self):
        points=[dict(decision=0,x=-1.),dict(decision=1,x=-.5)]
        bracket=pilot.threshold_bracket(points,'x',1.)
        self.assertEqual(bracket['largest_zero_input_LSB'],-1.)
        self.assertEqual(bracket['smallest_one_input_LSB'],-.5)
        self.assertTrue(bracket['constant_threshold_feasible'])
        points.append(dict(decision=0,x=.25))
        self.assertFalse(pilot.threshold_bracket(points,'x',1.)['constant_threshold_feasible'])

    def test_after_deadline_queued_case_requires_existing_proof_and_never_creates_stage(self):
        after=pilot.EXPIRES+timedelta(seconds=1)
        root=Path('/campaign');case=pilot.plan_cases()[0];kit=Path('/private')
        with patch.object(pilot,'utcnow',return_value=after),patch.object(pilot,'_ORIGINAL_STAGE') as stage,\
             patch.object(pilot,'query_preexpiry_slurm_submission') as query:
            with patch.object(pilot,'existing_preexpiry_stage',return_value=root/case['case_id']) as existing:
                self.assertEqual(pilot.stage_for_run(root,case,kit),root/case['case_id'])
                existing.assert_called_once_with(root,case,kit)
                query.assert_called_once_with(after)
            with patch.object(pilot,'existing_preexpiry_stage',side_effect=ValueError('Missing proof')):
                with self.assertRaises(ValueError):pilot.stage_for_run(root,case,kit)
            with self.assertRaises(ValueError):pilot.stage_before_expiry(root,case,kit)
            stage.assert_not_called()

    def test_slurm_submission_receipt_rejects_cutoff_wrong_job_and_malformed_output(self):
        cutoff=int(pilot.EXPIRES.timestamp())
        after=pilot.EXPIRES+timedelta(seconds=20)
        receipt=pilot.validate_preexpiry_slurm_submission(f'JobId=123 SubmitTime={cutoff-1}','123',after)
        self.assertEqual(receipt['submit_time_epoch'],cutoff-1)
        for output in (f'JobId=123 SubmitTime={cutoff}',f'JobId=123 SubmitTime={cutoff+1}',
                       f'JobId=124 SubmitTime={cutoff-1}',f'JobId=123 JobId=123 SubmitTime={cutoff-1}',
                       f'JobId=123 SubmitTime={cutoff-1} SubmitTime={cutoff-1}',
                       'JobId=123 SubmitTime=Unknown','JobId=123 SubmitTime=2026-11-16T23:00:00'):
            with self.assertRaises(ValueError):pilot.validate_preexpiry_slurm_submission(output,'123',after)
        with self.assertRaises(ValueError):
            pilot.validate_preexpiry_slurm_submission(f'JobId=123 SubmitTime={cutoff-1}','123',
                                                      pilot.EXPIRES-timedelta(seconds=2))

    def test_one_readonly_slurm_query_with_epoch_utc_environment(self):
        before=int(pilot.EXPIRES.timestamp())-1
        result=SimpleNamespace(stdout=f'JobId=123 SubmitTime={before} JobState=RUNNING')
        with patch.dict(pilot.os.environ,{'SLURM_JOB_ID':'123'}),\
             patch.object(pilot.subprocess,'run',return_value=result) as rpc:
            receipt=pilot.query_preexpiry_slurm_submission(pilot.EXPIRES)
        self.assertEqual(receipt['job_id'],'123')
        rpc.assert_called_once()
        args,kwargs=rpc.call_args
        self.assertEqual(args[0],['scontrol','--oneliner','show','job','123'])
        self.assertEqual(kwargs['timeout'],15)
        self.assertTrue(kwargs['check'] and kwargs['capture_output'] and kwargs['text'])
        self.assertEqual({k:kwargs['env'][k] for k in ('SLURM_TIME_FORMAT','TZ','LC_ALL')},
                         dict(SLURM_TIME_FORMAT='%s',TZ='UTC',LC_ALL='C'))
        with patch.dict(pilot.os.environ,{'SLURM_JOB_ID':''}),patch.object(pilot.subprocess,'run') as rpc:
            with self.assertRaises(ValueError):pilot.query_preexpiry_slurm_submission(pilot.EXPIRES)
            rpc.assert_not_called()

    def test_before_deadline_run_has_no_slurm_rpc(self):
        before=pilot.EXPIRES-timedelta(seconds=1)
        root=Path('/campaign');case=pilot.plan_cases()[0];kit=Path('/private')
        with patch.object(pilot,'utcnow',return_value=before),\
             patch.object(pilot,'stage_before_expiry',return_value=root/case['case_id']) as stage,\
             patch.object(pilot,'query_preexpiry_slurm_submission') as rpc:
            self.assertEqual(pilot.stage_for_run(root,case,kit),root/case['case_id'])
            stage.assert_called_once_with(root,case,kit)
            rpc.assert_not_called()

    def test_stage_proof_binds_deck_root_and_a_strictly_preexpiry_timestamp(self):
        fields=dict(case_id='case0',root='/campaign',deck='a'*64)
        before=pilot.EXPIRES-timedelta(seconds=1)
        proof=dict(fields,authorized_at_utc=before.isoformat())
        self.assertEqual(pilot.validate_stage_proof(proof,fields,pilot.EXPIRES),proof)
        for altered in (dict(proof,authorized_at_utc=pilot.EXPIRES.isoformat()),
                        dict(proof,deck='b'*64),dict(proof,extra='unexpected')):
            with self.assertRaises(ValueError):pilot.validate_stage_proof(altered,fields,pilot.EXPIRES)

    def test_approval_covers_every_independent_deck_and_expiry(self):
        verified=[(case,pilot.build(case)[1]) for case in pilot.plan_cases()]
        with patch.object(pilot.common,'sha',return_value='a'*64):
            approval=pilot.expected_approval(Path('/campaign'),verified)
        self.assertEqual(approval['case_ids'],[case['case_id'] for case,meta in verified])
        self.assertEqual(approval['deck_sha256_by_case'],
                         {case['case_id']:meta['portable_sha256'] for case,meta in verified})
        self.assertEqual(approval['authorization_expires_at_utc'],'2026-11-17T05:15:00Z')
