"""Regression through the actual selected-parser/full84-trial/72-boundary summary path."""

from contextlib import ExitStack
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

import sar7_read_overlap_collect_fix as fix


class CollectFixTests(unittest.TestCase):
    def test_source_pins_and_hash_mutation_guards(self):
        case,meta=fix.source.verify()
        self.assertEqual(meta['portable_sha256'],fix.SOURCE['portable_sha256'])
        self.assertEqual(fix.common.sha(fix.source.MANIFEST),fix.SOURCE['manifest_sha256'])
        self.assertEqual(fix.common.sha(fix.source.AUTHORIZATION),fix.SOURCE['authorization_sha256'])
        value=b'unchanged'
        self.assertEqual(fix.verify_bytes(value,hashlib.sha256(value).hexdigest(),'fixture'),value)
        with self.assertRaises(Exception):fix.verify_bytes(value,'0'*64,'fixture')
        with self.assertRaises(Exception):fix.unchanged({'hash':'one'},{'hash':'two'})

    def test_separate_output_and_no_stage_or_solver_cli(self):
        source=Path('source').absolute()
        for output in (source,source/'inside',source.parent):
            with self.assertRaises(Exception):fix.separate_paths(source,output)
        fix.separate_paths(source,source.parent/'independent_collector')
        for mode in ('run','stage','approval-template'):
            with patch('sys.argv',['collector',mode]),patch.object(fix,'verify') as verify:
                with self.assertRaises(SystemExit):fix.main()
                verify.assert_not_called()

    def test_every_new_payload_and_manifest_is_lf(self):
        for name in (*fix.FILES,'SHA256SUMS.txt'):
            content=(fix.ROOT/name).read_bytes()
            self.assertNotIn(b'\r',content,name)
            self.assertTrue(content.endswith(b'\n'),name)
        self.assertTrue((fix.ROOT/'sar7_read_overlap_collect_fix.sbatch').read_bytes().startswith(b'#!/bin/bash\n'))

    def test_full_selected_parser_regression_original_fails_fix_completes72(self):
        case=fix.source.case_record();_,meta=fix.source.build(case);wave=meta['wave']
        step=wave['strobe_s'];count=int(wave['stop_s']/step)
        time=[i*step for i in range(count+1)]
        if time[-1]<wave['stop_s']:time.append(wave['stop_s'])
        zero=[0.]*len(time);high=[wave['vdd_V']]*len(time);cm=[.45]*len(time)
        all_values={node:zero for node in wave['saved_signals']};all_values['time']=time
        for node in wave['saved_signals']:
            if node.startswith('clk') or (node.startswith('bit') and not node.endswith('b')):
                all_values[node]=high
            if node.startswith('qmid') and node.endswith('n'):all_values[node]=high
            if (node.startswith('qdecode') or (node.startswith('q') and not node.startswith('qmid'))) and node.endswith('p'):
                all_values[node]=high
            if node.startswith('XCMP') and node.endswith('.y'):all_values[node]=high
            if node in wave['dac_pair'] or node in ('sensep','sensen'):all_values[node]=cm
            if node.startswith('c') and not node.startswith('cb') and node.endswith('o') or node.startswith('cb') and node.endswith('z'):
                all_values[node]=high
        inventory=[dict(path=fix.base.review.RAW_NAME,sha256=fix.SOURCE['tran_sha256'],bytes=123)]
        hashes={'bench.scs':fix.SOURCE['staged_deck_sha256'],'spectre.log':fix.SOURCE['spectre_log_sha256']}
        status=dict(raw_inventory=inventory)
        rows=[]
        for cv in wave['conversions']:
            trials=[dict(bit=t['bit'],decision=1,stable_rail_delay_s=20*fix.source.native.PS,
                compare_to_read_s=t['read_s']-t['compare_s']) for t in cv['trials']]
            rows.append(dict(index=cv['index'],scored=True,expected_code=cv['expected_code'],
                observed_comparator_code=127,observed_registered_code=127,sample_dac_common_mode_V=.45,trial_results=trials))
        report=dict(conversions=rows,tested_conversions=12,execution_files_sha256=hashes,
            tran_sha256=fix.SOURCE['tran_sha256'],max_abs_sample_error_lsb=0.,max_observed_resolve_delay_s=20e-12,
            slurm_task_id='761649',solver_seconds=1.,raw_bytes=123)
        admitted=[]
        class Raw:
            sha256=fix.SOURCE['tran_sha256'];sweep_names=['time']
            def __init__(self,values):self.values=values
            def unit(self,key):return 's' if key=='time' else 'A' if key.endswith(':p') else 'V'
        def selected(path,required):
            admitted.append(set(required))
            self.assertTrue(set(required)<=set(all_values))
            return Raw({name:all_values[name] for name in required})
        def safe_raw(directory,status,name,parser):return parser(Path('retained_fixture'))
        original_parent=fix.source.summarize.__globals__['parent']
        original_extras=fix.source.parent.summarize.__globals__['EXTRA_SAVES']
        with ExitStack() as stack:
            stack.enter_context(patch.object(fix.base,'evidence',return_value=(wave,status,hashes)))
            stack.enter_context(patch.object(fix.common,'raw_inventory',return_value=inventory))
            stack.enter_context(patch.object(fix.common,'sha',return_value='a'*64))
            stack.enter_context(patch.object(fix.base.review,'parse_selected',side_effect=selected))
            stack.enter_context(patch.object(fix.base.review,'safe_raw',side_effect=safe_raw))
            stack.enter_context(patch.object(fix.base,'collect',side_effect=AssertionError('No base.collect')))
            stack.enter_context(patch.object(fix.base,'stage',side_effect=AssertionError('No stage')))
            stack.enter_context(patch.object(fix.base,'run',side_effect=AssertionError('No solver')))
            with self.assertRaisesRegex(KeyError,'trial6'):
                fix.source.summarize(report,Path('completed_source'),case,meta)
            self.assertNotIn('trial6',admitted[-1]);admitted.clear()
            result,proof=fix.fixed_summarize(report,Path('completed_source'),case,meta)
        self.assertEqual(len(admitted),1)
        self.assertEqual(proof['psf_parse_count'],1)
        self.assertTrue(set(wave['saved_signals'])<=admitted[0])
        self.assertTrue({f'{kind}{bit}' for kind in ('trial','clk') for bit in range(7)}<=admitted[0])
        self.assertEqual(len(result['timing']),84)
        self.assertEqual(result['case_id'],fix.SOURCE['case_id'])
        self.assertEqual(result['primary_readout_ps'],565)
        self.assertEqual(result['overlap_diagnostic']['observed_within_conversion_boundaries'],72)
        self.assertEqual(result['overlap_diagnostic']['prior_read_internal_class_available'],72)
        self.assertIn('active_last_read_cm_pass',result['readout_565'])
        self.assertEqual(len(proof['supplemental_diagnostics']['b6']),12)
        self.assertEqual([o['ps_from_launch'] for o in proof['supplemental_diagnostics']['b6'][0]['observations']],[30,35,38,41])
        self.assertIs(fix.source.summarize.__globals__['parent'],original_parent)
        self.assertIs(fix.source.parent.summarize.__globals__['EXTRA_SAVES'],original_extras)

    def test_source_bindings_restore_on_failure(self):
        saved=fix.base.build,fix.base.PLAN,fix.base.MANIFEST,fix.base.SCHEMA
        root=Path(fix.SOURCE['root_name']).absolute();output=root.parent/'independent_collector'
        with patch.object(Path,'resolve',return_value=root),patch.object(Path,'is_dir',return_value=True),patch.object(fix,'source_snapshot',side_effect=RuntimeError('bad source proof')):
            with self.assertRaises(RuntimeError):fix.collect_only(root,output,{'case_id':fix.SOURCE['case_id']},{})
        self.assertEqual((fix.base.build,fix.base.PLAN,fix.base.MANIFEST,fix.base.SCHEMA),saved)


if __name__=='__main__':unittest.main()
