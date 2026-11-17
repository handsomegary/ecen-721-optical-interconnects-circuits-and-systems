"""Read-only retained-evidence audit guards and time/polarity semantics."""

import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import sar7_qbuffer_audit as audit


class AuditTests(unittest.TestCase):
    def test_exact_source_hash_and_mutation_guards(self):
        content=b'{"source":"existing"}'
        self.assertEqual(audit.verify_receipt(content,hashlib.sha256(content).hexdigest(),'test'),{'source':'existing'})
        with self.assertRaises(Exception):audit.verify_receipt(content,'0'*64,'test')
        audit.unchanged({'a':'1'},{'a':'1'})
        with self.assertRaises(Exception):audit.unchanged({'a':'1'},{'a':'2'})

    def test_source_output_separation(self):
        source=Path('source').absolute()
        for output in (source,source/'new',source.parent):
            with self.assertRaises(Exception):audit.separate_paths([source],output)
        audit.separate_paths([source],source.parent/'independent_audit')

    def test_timestamp_origins_and_actual_39ps_read(self):
        _,meta=audit.qbuffer.build(audit.qbuffer.case_record())
        conversion=meta['wave']['conversions'][0]
        trial=conversion['trials'][0]
        self.assertAlmostEqual((trial['read_s']-trial['compare_s'])/audit.native.PS,39.)
        result=audit.edges([100e-12,102e-12],[0.,.9],100e-12,102e-12,.45,80e-12,90e-12)
        self.assertEqual(len(result),1)
        self.assertAlmostEqual(result[0]['ps_from_conversion'],21.)
        self.assertAlmostEqual(result[0]['ps_from_current_compare'],11.)
        self.assertEqual(result[0]['direction'],'rise')

    def test_window_extends_past_next_launch_and_uses_each_source_schedule(self):
        ps=audit.native.PS
        cv={'trials':[dict(bit=4,launch_s=20*ps,compare_s=23*ps,read_s=28*ps,trial_release_s=30*ps),
                      dict(bit=3,launch_s=31*ps,compare_s=40*ps,read_s=50*ps,trial_release_s=52*ps),
                      dict(bit=2,launch_s=53*ps,compare_s=70*ps,read_s=110*ps,trial_release_s=112*ps)]}
        window=audit.window_for(cv,3,150*ps)
        self.assertAlmostEqual(window['lo']/ps,25.)
        self.assertAlmostEqual(window['hi']/ps,110.)
        self.assertGreater(window['hi'],cv['trials'][2]['launch_s'])
        cv['trials'][2]['compare_s']=120*ps
        self.assertAlmostEqual(audit.window_for(cv,3,200*ps)['hi']/ps,150.)
        self.assertAlmostEqual(audit.window_for(cv,3,125*ps)['hi']/ps,125.)

    def test_o_z_commands_and_transition_are_not_inverted(self):
        self.assertEqual(audit.command(.9,0.,0.,.9,.9),'O_rail_command')
        self.assertEqual(audit.command(0.,.9,.9,0.,.9),'Z_rail_command')
        self.assertEqual(audit.command(.9,0.,.9,0.,.9),'both_rail_commands')
        self.assertEqual(audit.command(0.,.9,0.,.9,.9),'neither_rail_command')
        self.assertEqual(audit.command(.45,.45,0.,.9,.9),'transition_or_noncomplementary')
        self.assertEqual(audit.score.classify(.9,0.,.9),1)
        self.assertEqual(audit.score.classify(0.,.9,.9),0)

    def test_missing_source_refuses_before_evidence_or_collect(self):
        missing=Path('this_audit_source_does_not_exist_761549').absolute()
        with patch.object(audit.base,'evidence') as evidence,patch.object(audit.base,'collect') as collect:
            with self.assertRaises(Exception):audit.audit_source(missing,'qbuffer')
            evidence.assert_not_called();collect.assert_not_called()

    def test_frozen_sources_and_json_roundtrip(self):
        for module,kind in ((audit.qbuffer,'qbuffer'),(audit.strong,'strong')):
            case=module.case_record()
            first,meta=module.build(case)
            second,other=module.build(json.loads(json.dumps(case)))
            self.assertEqual(first,second)
            self.assertEqual(meta,other)
            self.assertEqual(hashlib.sha256(first).hexdigest(),audit.PINS[kind]['portable'])
        self.assertEqual(len(audit.TARGETS),7)

    def test_selected_samples_preserve_original_miss_and_late_valid_diagnostic(self):
        _,meta=audit.qbuffer.build(audit.qbuffer.case_record());wave=meta['wave']
        times=[i*audit.native.PS for i in range(301)]
        values={node:[0.]*len(times) for node in wave['saved_signals']};values['time']=times
        for node in wave['saved_signals']:
            if node.startswith('q') and node.endswith('p'):values[node]=[.9]*len(times)
        row=dict(trial_results=[dict(bit=b,decision=None if b==6 else 1) for b in range(7)],observed_registered_code=127)
        compact,dense=audit.selected_window(values,wave,wave['conversions'][0],6,'qbuffer',row)
        target=compact['contexts'][0]
        self.assertIsNone(target['original_read_decision'])
        self.assertEqual(target['release_raw_class'],1)
        self.assertIn('does not replace',target['late_class_label'])
        self.assertGreater(compact['window_end_s'],wave['conversions'][0]['trials'][1]['launch_s'])
        self.assertTrue(any(r['phase']=='compare_plus_30ps' for r in dense['phase_observations']))
        direct,raw=audit.selected_window(values,wave,wave['conversions'][0],6,'strong',row)
        self.assertTrue(all(r['mid_V'] is None and r['decoder_input_source']=='direct_raw_q' for r in raw['phase_observations']))


if __name__=='__main__':unittest.main()
