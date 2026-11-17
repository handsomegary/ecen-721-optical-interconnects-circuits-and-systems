"""Bound q-only isolation, polarity, saved timing observations and deadline behavior."""

from collections import Counter
from datetime import timedelta
import copy
import json
import re
import unittest
from unittest.mock import patch

import sar7_qbuffer as pilot


class QBufferTests(unittest.TestCase):
    def test_exact_q_only_local_delta_and_unchanged_subcircuits(self):
        old,_=pilot.parent.build(pilot.parent.case_record())
        new,_=pilot.build(pilot.case_record())
        prior=old.decode('ascii').splitlines();current=new.decode('ascii').splitlines()
        self.assertEqual((sum((Counter(prior)-Counter(current)).values()),
                          sum((Counter(current)-Counter(prior)).values())),(29,57))
        self.assertTrue([line for line in prior if line.startswith(('subckt ','ends ','M'))]==
                        [line for line in current if line.startswith(('subckt ','ends ','M'))],
                        'Original subcircuit definitions changed')
        restored=[]
        for line in current:
            if re.match(r'^XQ(IN|OUT)[0-6][pn] ',line):continue
            if re.match(r'^XND[OZ][pn][0-6] ',line):
                line=re.sub(r'\bqdecode([0-6])([pn])\b',r'q\1\2',line)
            if line.startswith('save '):
                line=' '.join(token for token in line.split() if token not in pilot.Q_SAVES)
            restored.append(line)
        self.assertTrue(restored==prior,'A change outside the permitted q-only delta was found')
        self.assertEqual(sum(line.startswith('XQIN') for line in current),14)
        self.assertEqual(sum(line.startswith('XQOUT') for line in current),14)

    def test_two_inverting_cells_form_the_frozen_noninverting_buffer(self):
        source,_=pilot.build(pilot.case_record());lines=source.decode('ascii').splitlines()
        for bit,branches in pilot.Q_NODES.items():
            for side,nodes in branches.items():
                self.assertTrue(f'XQIN{bit}{side} ({nodes["raw"]} {nodes["mid"]} vdd) SAR_INV' in lines)
                self.assertTrue(f'XQOUT{bit}{side} ({nodes["mid"]} {nodes["decode"]} vdd) SAR_NDINV2' in lines)
                real=next(line for line in lines if line.startswith(f'XBitb{bit} '))
                self.assertIn(f'q{bit}p',real)
        for raw in (0,1):
            mid=1-raw;decoded=1-mid
            self.assertEqual(decoded,raw)

    def test_schedule_waveform_codes_and_saved_probes_are_unchanged(self):
        _,old=pilot.parent.build(pilot.parent.case_record())
        source,meta=pilot.build(pilot.case_record())
        self.assertEqual(json.loads(json.dumps(meta)),meta)
        wave=copy.deepcopy(meta['wave'])
        wave.pop('q_buffer_nodes');wave.pop('q_buffer_polarity')
        wave['saved_signals']=[node for node in wave['saved_signals'] if node not in pilot.Q_SAVES]
        self.assertEqual(wave,old['wave'])
        self.assertEqual(meta['schedule_ps'],old['schedule_ps'])
        self.assertEqual(meta['primary_readout_ps'],565)
        saved=next(line.split()[1:] for line in source.decode('ascii').splitlines() if line.startswith('save '))
        self.assertEqual(len(pilot.Q_SAVES),28)
        self.assertEqual(len(set(pilot.Q_SAVES)),28)
        self.assertTrue(all(saved.count(node)==1 for node in pilot.Q_SAVES))
        self.assertAlmostEqual(1/meta['wave']['period_s'],1.75e9)

    def fake_observation(self,decision=1,bit=1,last=70e-12):
        times=[0.,last];values={'time':times}
        for side,nodes in pilot.Q_NODES[str(bit)].items():
            raw=.9*(decision if side=='p' else 1-decision)
            values[nodes['raw']]=[raw,raw]
            values[nodes['mid']]=[.9-raw,.9-raw]
            values[nodes['decode']]=[raw,raw]
        trial=dict(bit=bit,compare_s=10e-12,read_s=60e-12,trial_release_s=62e-12,
                   cmp_pair=[pilot.Q_NODES[str(bit)][side]['raw'] for side in 'pn'])
        following=dict(bit=bit-1,launch_s=65e-12)
        conversion=dict(index=0,trials=[trial,following] if bit else [trial])
        wave=dict(vdd_V=.9,period_s=1/1.75e9)
        return values,times,conversion,trial,wave

    def test_timed_raw_mid_decode_observations_and_polarity(self):
        for decision in (0,1):
            args=self.fake_observation(decision)
            detail=pilot.q_buffer_detail(*args)
            self.assertEqual(set(detail['observations']),
                             {'compare_plus_15ps','compare_plus_30ps','read','release','next_launch'})
            for record in detail['observations'].values():
                self.assertEqual(record['raw_class'],decision)
                self.assertEqual(record['decode_class'],decision)
                self.assertEqual(record['mid_class_in_raw_polarity'],decision)
                self.assertTrue(record['noninverting_match'])
            self.assertTrue(detail['next_launch_within_saved_trace'])
            self.assertEqual(set(detail['gate_half_crossings_ps_from_compare']),{'raw','mid','decode'})

    def test_final_b0_next_cycle_is_not_extrapolated_past_stop(self):
        detail=pilot.q_buffer_detail(*self.fake_observation(bit=0))
        self.assertFalse(detail['next_launch_within_saved_trace'])
        self.assertNotIn('next_launch',detail['observations'])

    def test_nested_parent_verify_preserves_child_binding_and_json(self):
        base=pilot.base;saved=(base.build,base.PLAN,base.MANIFEST,base.SCHEMA)
        parent_id=pilot.parent.CASE_ID
        try:
            base.build,base.PLAN,base.MANIFEST,base.SCHEMA=pilot.build,pilot.PLAN,pilot.MANIFEST,pilot.SCHEMA
            case,meta=pilot.verify()
            self.assertIs(base.build,pilot.build)
            self.assertEqual(pilot.parent.CASE_ID,parent_id)
            self.assertEqual(meta['portable_sha256'],pilot.REVIEWED_DECK_SHA)
            self.assertEqual(json.loads(json.dumps(meta)),meta)
        finally:base.build,base.PLAN,base.MANIFEST,base.SCHEMA=saved

    def test_deadline_and_physical_gates_preserve_original_semantics(self):
        pilot.check_stage_deadline(pilot.EXPIRES-timedelta(seconds=1))
        with self.assertRaises(ValueError):pilot.check_stage_deadline(pilot.EXPIRES)
        with patch.object(pilot.fast.offset,'query_preexpiry_slurm_submission',return_value={'job_id':'123'}) as query:
            self.assertIsNone(pilot.check_run_submission(pilot.EXPIRES-timedelta(seconds=1)))
            query.assert_not_called()
            self.assertEqual(pilot.check_run_submission(pilot.EXPIRES),{'job_id':'123'})
            query.assert_called_once_with(pilot.EXPIRES)
        result=pilot.apply_physical_screen(dict(screen_pass=True,logic_smoke_pass=True),True,False)
        self.assertFalse(result['screen_pass']);self.assertTrue(result['logic_smoke_pass'])


if __name__=='__main__':unittest.main()
