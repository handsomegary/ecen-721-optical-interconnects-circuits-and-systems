"""Bound physical replicas, independent dependencies, timing and output validity."""

from collections import Counter
from datetime import timedelta
import itertools
import json
import re
import unittest
from unittest.mock import patch

import sar7_strong_decode as pilot


class StrongDecoderTests(unittest.TestCase):
    def test_complete_cdf_replicas_and_series_counts(self):
        _,(_,_,n,p)=pilot.native.read_cdf(pilot.base.review.R5/'quiet.scs')
        text='\n'.join(pilot.decoder_subcircuits())
        expected={'SAR_OAI21_X2':(6,5),'SAR_NOR3_P3':(3,9),'SAR_NDINV2':(2,2)}
        for circuit,(nc,pc) in expected.items():
            body=text.split('subckt '+circuit+' ',1)[1].split('ends '+circuit,1)[0]
            records=re.findall(r'^(M\w+) \(([^)]*)\) (.+)$',body,re.M)
            self.assertEqual(sum(card==n for name,pins,card in records),nc)
            self.assertEqual(sum(card==p for name,pins,card in records),pc)
            self.assertTrue(all(card in (n,p) for name,pins,card in records))
            if circuit=='SAR_OAI21_X2':
                self.assertEqual(sum(name.startswith('MP3_R') for name,pins,card in records),1)
            if circuit=='SAR_NOR3_P3':
                for index in (1,2,3):
                    self.assertEqual(sum(name.startswith(f'MP{index}_R') for name,pins,card in records),3)

    def test_physical_gate_truth_tables(self):
        text='\n'.join(pilot.decoder_subcircuits())
        for a,b,en in itertools.product((0,1),repeat=3):
            states=dict(a=a,b=b,en=en,enb=1-en)
            for circuit,expected in (('SAR_OAI21_X2',int(not(en and(a or b)))),
                                      ('SAR_NOR3_P3',int(en and not(a or b)))):
                body=text.split('subckt '+circuit+' ',1)[1].split('ends '+circuit,1)[0]
                transistors=re.findall(r'^M\w+ \((\w+) (\w+) (\w+) (\w+)\) ([np])ch',body,re.M)
                reached={'y'}
                for _ in transistors:
                    for drain,gate,source,bulk,polarity in transistors:
                        if states[gate]==(polarity=='n') and {drain,source}&reached:
                            reached.update((drain,source))
                self.assertEqual(('vdd'in reached,'0'in reached),(bool(expected),not expected))

    def test_exact_local_change_and_unchanged_tg_registers_analog(self):
        prior,_=pilot.parent.build(pilot.parent.case_record())
        current,_=pilot.build(pilot.case_record())
        old=prior.decode('ascii').splitlines();new=current.decode('ascii').splitlines()
        removed=list((Counter(old)-Counter(new)).elements())
        added=list((Counter(new)-Counter(old)).elements())
        self.assertEqual((len(removed),len(added)),(85,102))
        prefixes=('XRef','XNDLOAD','XBit','XQCOMPLOAD','XTrack','XLowTrack','XReset','XDconv',
                  'VDD ','V_RHI ','V_RLO ','V_RCM ','V_src','V_conv','V_reset','V_track','V_lowtrack','save ','tranResponse ')
        self.assertEqual([line for line in old if line.startswith(prefixes)],
                         [line for line in new if line.startswith(prefixes)])
        def subckt(rows,name):
            text='\n'.join(rows)
            return text.split('subckt '+name+' ',1)[1].split('ends '+name,1)[0]
        for name in ('SAR_INV','SAR_TG','SAR_NOR','SAR_CMP'):
            self.assertEqual(subckt(old,name),subckt(new,name))
        self.assertEqual(sum(line.startswith('X') and line.endswith(' SAR_OAI21_X2') for line in new),14)
        self.assertEqual(sum(line.startswith('X') and line.endswith(' SAR_NOR3_P3') for line in new),14)
        self.assertEqual(sum(line.startswith('X') and line.endswith(' SAR_NDINV2') for line in new),28)
        self.assertFalse(any('bsource' in line for line in added))

    def test_schedule_period_codes_and_formal_565ps_window(self):
        case=pilot.case_record();_,meta=pilot.build(case)
        _,old=pilot.parent.build(pilot.parent.case_record())
        self.assertEqual(json.loads(json.dumps(meta)),meta)
        self.assertEqual(pilot.timing_schedule()[0],(492,498,552,554))
        self.assertEqual(pilot.timing_schedule()[5],(162,207,251,253))
        self.assertAlmostEqual(1/meta['wave']['period_s'],1.75e9)
        self.assertEqual(pilot.CLOCK_OFF_PS,568)
        self.assertLess(565,566)
        for before,after in zip(old['wave']['conversions'],meta['wave']['conversions'],strict=True):
            for key in ('sample_s','expected_code','source_diff_V','code_pairs'):
                self.assertEqual(before[key],after[key])
            origin=after['index']*meta['wave']['period_s']
            self.assertAlmostEqual((after['end_s']-origin)/pilot.native.PS,565,places=8)
            self.assertLessEqual(after['end_s'],meta['wave']['stop_s'])
            self.assertGreaterEqual((after['end_s']-after['trials'][-1]['trial_release_s'])/pilot.native.PS,10.999999)
            for bit,wait,observe in zip(pilot.BITS,pilot.WAITS,pilot.READS,strict=True):
                trial=next(t for t in after['trials'] if t['bit']==bit)
                self.assertAlmostEqual((trial['compare_s']-trial['launch_s'])/pilot.native.PS,wait,places=8)
                self.assertAlmostEqual((trial['read_s']-trial['compare_s'])/pilot.native.PS,observe,places=8)
                self.assertLess(trial['compare_s']+pilot.native.timing(30),trial['read_s'])

    def test_nested_parent_verification_and_json_roundtrip_after_bind(self):
        base=pilot.base;saved=(base.build,base.PLAN,base.MANIFEST,base.SCHEMA)
        try:
            base.build,base.PLAN,base.MANIFEST,base.SCHEMA=pilot.build,pilot.PLAN,pilot.MANIFEST,pilot.SCHEMA
            case,meta=pilot.verify()
            self.assertIs(base.build,pilot.build)
            self.assertEqual(meta['portable_sha256'],pilot.REVIEWED_DECK_SHA)
            self.assertEqual(json.loads(json.dumps(meta)),meta)
        finally:
            base.build,base.PLAN,base.MANIFEST,base.SCHEMA=saved

    def test_deadline_blocks_new_stage_but_checks_actual_queued_submission(self):
        before=pilot.EXPIRES-timedelta(seconds=1)
        pilot.check_stage_deadline(before)
        for now in (pilot.EXPIRES,pilot.EXPIRES+timedelta(seconds=1)):
            with self.assertRaises(ValueError):pilot.check_stage_deadline(now)
        with patch.object(pilot.fast.offset,'query_preexpiry_slurm_submission',return_value={'job_id':'123'}) as query:
            self.assertIsNone(pilot.check_run_submission(before));query.assert_not_called()
            self.assertEqual(pilot.check_run_submission(pilot.EXPIRES),{'job_id':'123'})
            query.assert_called_once_with(pilot.EXPIRES)
        with patch.object(pilot.fast.offset,'query_preexpiry_slurm_submission',side_effect=ValueError('Late submission')):
            with self.assertRaises(ValueError):pilot.check_run_submission(pilot.EXPIRES)

    def test_active_cm_and_read_window_gate_do_not_change_digital_zero_error(self):
        digital=dict(screen_pass=True,logic_smoke_pass=True)
        for window,active in ((False,True),(True,False),(False,False)):
            result=pilot.apply_physical_screen(digital,window,active)
            self.assertFalse(result['screen_pass'])
            self.assertTrue(result['logic_smoke_pass'])
        self.assertTrue(pilot.apply_physical_screen(digital,True,True)['screen_pass'])
        failed=dict(screen_pass=False,logic_smoke_pass=False)
        self.assertFalse(pilot.apply_physical_screen(failed,True,True)['logic_smoke_pass'])


if __name__=='__main__':
    unittest.main()
