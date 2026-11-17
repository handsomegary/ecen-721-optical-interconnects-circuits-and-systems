"""Offline recovery regressions using only synthetic deck and output fixtures."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import unittest
from unittest import mock
from uuid import uuid4

import recover_bias as recovery
from pvt.reference.psf_ascii import parse_text


ROOT = Path(__file__).resolve().parent
CURRENT_DECK = '''simulator lang=spectre
GFVDD (GF_VDD 0) vsource dc=0.81
GMSAPVD (GMSAPD GMSAPS) vcvs gain=1
GMSRIREF (GMSR_REF 0) isource dc=0.0003
GMSRRREF (GF_VDD GMSR_REF) resistor r=462
save GFVDD:p GMSAPVD:p GMSR_REF
'''
CURRENT_RECORD = {'rail_voltages_V': {'GFVDD:p': .81}, 'DC_currents': ['GMSAPVD:p'],
                  'DC_nodes': ['GMSR_REF'], 'AC_traces': ['GMSR_REF'],
                  'target_mA_per_leg': 4.2, 'vdd_V': .81}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root):
    return {path.relative_to(root).as_posix(): (sha(path), path.stat().st_mtime_ns)
            for path in root.rglob('*') if path.is_file()}


class SaveCurrents(unittest.TestCase):
    def test_voltage_source_current_names_are_scoped_to_existing_instances(self):
        recovery.validate_save_currents(CURRENT_DECK, CURRENT_RECORD)

    def test_rejects_unsupported_or_unbound_current_names(self):
        for trace in ('GMSRIREF:p', 'missing:p', 'GFVDD:missing'):
            with self.subTest(trace=trace):
                record = dict(CURRENT_RECORD, DC_currents=['GMSAPVD:p', trace])
                deck = CURRENT_DECK.replace('save ', f'save {trace} ')
                with self.assertRaises(ValueError):
                    recovery.validate_save_currents(deck, record)

    def test_rejects_expected_current_omitted_from_save(self):
        with self.assertRaises(ValueError):
            recovery.validate_save_currents(CURRENT_DECK.replace('GFVDD:p ', ''), CURRENT_RECORD)

    def test_rejects_unsupported_unexpected_saved_current(self):
        with self.assertRaises(ValueError):
            recovery.validate_save_currents(CURRENT_DECK.replace('save ', 'save GMSRIREF:p '), CURRENT_RECORD)

    def test_ideal_sink_is_derived_from_attested_voltage_drop(self):
        vref = .81 - 462*.0003
        report = {'DC_voltage_V': {'GMSR_REF': vref}, 'DC_current_A': {}}
        result = recovery.reference_current(CURRENT_DECK, CURRENT_RECORD, report)
        self.assertAlmostEqual(result['programmed_A'], .0003, places=12)
        self.assertAlmostEqual(result['recovered_A'], .0003, places=12)
        self.assertEqual(report['DC_current_A'], {})

    def test_inconsistent_sink_setting_or_voltage_drop_is_rejected(self):
        good = {'DC_voltage_V': {'GMSR_REF': .81 - 462*.0003}}
        changed = CURRENT_DECK.replace('dc=0.0003', 'dc=0.0006')
        for deck, report in ((changed, good), (CURRENT_DECK, {'DC_voltage_V': {'GMSR_REF': .81}})):
            with self.subTest(deck=deck, report=report), self.assertRaises(ValueError):
                recovery.reference_current(deck, CURRENT_RECORD, report)

    def test_fixed_render_removes_only_legacy_current_and_disconnected_rail(self):
        case = recovery.lp_bias.build_plan()['cases'][30]
        token = recovery.lp_bias.DRIVE.gm.original.base.MODEL_TOKEN
        legacy, old_rails, old_ac, old_dc, old_cur, _ = recovery.lp_bias.render(case, token)
        deck, rails, ac, dc, currents, _ = recovery.fixed_render(case, token)
        self.assertIn('GMSRIREF:p', legacy)
        self.assertIn('GFVCTL:p', old_rails)
        self.assertEqual(ac, old_ac)
        self.assertEqual(dc, old_dc)
        self.assertEqual(currents, [n for n in old_cur if n != 'GMSRIREF:p'])
        self.assertEqual(rails, {n: v for n, v in old_rails.items() if n != 'GFVCTL:p'})
        fixed_circuit = re.sub(r'(?m)^save .*\n', '', deck)
        old_circuit = re.sub(r'(?m)^(?:save |GFVCTL ).*\n', '', legacy)
        self.assertEqual(fixed_circuit, old_circuit)


class Publication(unittest.TestCase):
    def setUp(self):
        self.root = ROOT/('recovery_test_'+uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        (self.root/'raw').mkdir()
        (self.root/'raw'/'dcOp.dc').write_bytes(b'synthetic recorded DC bytes\n')
        (self.root/'bench.scs').write_text(CURRENT_DECK, encoding='ascii')
        (self.root/'case.json').write_text('{}\n', encoding='ascii')
        (self.root/'run_status.json').write_text('{}\n', encoding='ascii')
        self.original = snapshot(self.root)
        self.report = {'measurement_complete': True, 'case_id': 'offline-test'}
        self.receipt = {'format': 'offline-test', 'case_id': 'offline-test'}

    def test_publish_uses_only_new_measurement_files_and_is_idempotent(self):
        with mock.patch('subprocess.Popen', side_effect=AssertionError('Solver process requested')):
            recovery.publish(self.root, self.report, self.receipt)
            first = snapshot(self.root)
            recovery.publish(self.root, self.report, self.receipt)
            self.assertEqual(snapshot(self.root), first)
        self.assertEqual(set(first) - set(self.original),
                         {'measurements.json', 'recovery.json', 'completion.json'})
        self.assertEqual({name: first[name] for name in self.original}, self.original)
        completion = json.loads((self.root/'completion.json').read_text(encoding='utf-8'))
        self.assertTrue(completion['measurement_complete'])
        self.assertEqual(completion['measurement_sha256'], sha(self.root/'measurements.json'))
        self.assertEqual(completion['recovery_sha256'], sha(self.root/'recovery.json'))
        self.assertEqual(completion['mode'], 'collect-only')

    def test_publish_refuses_to_replace_conflicting_measurement(self):
        path = self.root/'measurements.json'
        path.write_text('{"already_present": true}\n', encoding='ascii')
        before = snapshot(self.root)
        with self.assertRaises((ValueError, FileExistsError)):
            recovery.publish(self.root, self.report, self.receipt)
        self.assertEqual(snapshot(self.root), before)

    def test_resume_after_measurement_before_completion(self):
        real_link = recovery.os.link
        def interrupt(source,target):
            if Path(target).name=='completion.json':
                raise OSError('interrupted before commit')
            return real_link(source,target)
        with mock.patch.object(recovery.os,'link',side_effect=interrupt):
            with self.assertRaisesRegex(OSError,'before commit'):
                recovery.publish(self.root,self.report,self.receipt)
        self.assertFalse((self.root/'completion.json').exists())
        self.assertTrue((self.root/'measurements.json').is_file())
        self.assertEqual(recovery.publish(self.root,self.report,self.receipt),'recovered')


class RecoveryRoundTrip(unittest.TestCase):
    def setUp(self):
        self.root = ROOT/('recovery_test_'+uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.case_dir = self.root/'lpbias_030_ss_i420_p'
        self.case_dir.mkdir()
        if os.name == 'nt':
            # Olympus performs the real POSIX ownership check. Windows fixtures
            # expose st_uid without os.getuid, so supply the local fixture UID.
            uid = mock.patch.object(os, 'getuid', lambda: self.case_dir.stat().st_uid, create=True)
            uid.start()
            self.addCleanup(uid.stop)
        d = self.case_dir
        (d/'raw').mkdir()
        for name in ('acResponse.ac', 'dcOp.dc', 'dcOpInfo.info', 'logFile', 'noiseResponse.noise'):
            (d/'raw'/name).write_bytes(f'synthetic {name}\n'.encode('ascii'))
        deck = CURRENT_DECK.replace('save ', 'save GMSRIREF:p ')
        (d/'bench.scs').write_text(deck, encoding='ascii')
        (d/'parent_diff.txt').write_bytes(b'synthetic diff\n')
        (d/'la5_foundry_corners.scs').write_bytes(b'synthetic corner\n')
        (d/'spectre.log').write_bytes(b'synthetic log, no Spectre process\n')
        (d/'.study_owned').write_bytes(b'753787\n')
        self.case = dict(CURRENT_RECORD, case_id=d.name, drive='p', bias_mode='replica',
                         DC_currents=['GMSAPVD:p', 'GMSRIREF:p'],
                         staged_source_sha256={n: sha(d/n) for n in
                                               ('bench.scs', 'parent_diff.txt', 'la5_foundry_corners.scs')})
        self.write('case.json', self.case)
        self.intent = {'case_id': d.name, 'plan_sha256': recovery.ORIGINAL_PLAN_SHA,
                       'case_sha256': sha(d/'case.json'), 'slurm_job_id': '753787',
                       'input_deck_sha256_before': sha(d/'bench.scs')}
        self.write('execution_intent.json', self.intent)
        self.status = dict(self.intent, status='spectre_completed', exit_code=0,
                           solver_completion_errors=0, input_deck_sha256_after=sha(d/'bench.scs'),
                           spectre_log_sha256=sha(d/'spectre.log'),
                           raw_inventory=recovery.common.raw_inventory(d))
        self.write('run_status.json', self.status)
        self.pin = {'index': 30, 'case_id': d.name, 'files': {p.name: sha(p) for p in d.iterdir()
                                                          if p.is_file()}}

    def write(self, name, data):
        (self.case_dir/name).write_text(json.dumps(data), encoding='ascii')

    def test_raw_checksum_change_rejected_even_with_original_size_and_mtime(self):
        p = self.case_dir/'raw'/'dcOp.dc'
        data = p.read_bytes()
        prior = p.stat()
        p.write_bytes(b'!' + data[1:])
        os.utime(p, ns=(prior.st_atime_ns, prior.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, 'Historical raw inventory differs'):
            recovery.verify_case(self.case_dir, self.pin)
        self.assertFalse((self.case_dir/'completion.json').exists())

    def test_recovery_projects_missing_trace_and_preserves_source_sha_without_solver(self):
        d = self.case_dir
        before = snapshot(d)
        devices = ('GMSRCS0', *(f'GMSH{leg}CS{i}' for leg in 'PM' for i in range(14)))
        measured = {'case_id': d.name, 'measurement_complete': True,
                    'bench_sha256': self.pin['files']['bench.scs'],
                    'run_status_sha256': self.pin['files']['run_status.json'],
                    'DC_voltage_V': {'GMSR_REF': .81 - 462*.0003},
                    'DC_current_A': {'GMSAPVD:p': .001},
                    'saved_mos_oppoint': {name: {'ids': .0003, 'gm': .01, 'vds': .65, 'vdsat': .2}
                                          for name in devices}}
        manifest_sha = 'a'*64
        real_sha = recovery.common.sha

        def digest(path):
            return manifest_sha if Path(path) == ROOT/'SHA256SUMS.txt' else real_sha(path)

        # The production runner locks a POSIX directory descriptor. On Windows
        # only, substitute a local file descriptor and stand-in fcntl lock.
        if os.name == 'nt':
            real_open = os.open
            lockfile = self.root/'mock-lock'
            lockfile.touch()

            def open_directory(path, flags, *args, **kwargs):
                if path == d:
                    return real_open(lockfile, os.O_RDONLY)
                return real_open(path, flags, *args, **kwargs)

            for patch in (mock.patch.object(os, 'O_DIRECTORY', 0, create=True),
                          mock.patch.object(os, 'O_NOFOLLOW', 0, create=True),
                          mock.patch.object(os, 'open', side_effect=open_directory),
                          mock.patch.dict(sys.modules, {'fcntl': mock.Mock(LOCK_EX=2, LOCK_NB=4)})):
                patch.start()
                self.addCleanup(patch.stop)
        with mock.patch('subprocess.Popen', side_effect=AssertionError('Solver process requested')), \
             mock.patch.object(recovery.common, 'run_classic', side_effect=AssertionError('Solver requested')), \
             mock.patch.object(recovery.common, 'retire_case_raw', side_effect=AssertionError('Raw retirement requested')), \
             mock.patch.object(recovery.common, 'sha', side_effect=digest), \
             mock.patch.object(recovery.gm_select, 'measure', return_value=measured) as measure:
            self.assertEqual(recovery.recover_case(d, self.pin), 'recovered')
            after_first = snapshot(d)
            self.assertEqual(recovery.recover_case(d, self.pin), 'already_recovered')
            self.assertEqual(snapshot(d), after_first)
        projected = dict(self.case, DC_currents=['GMSAPVD:p'])
        measure.assert_called_once_with(d, projected, self.status)
        self.assertEqual({name: after_first[name] for name in before}, before)
        report = json.loads((d/'measurements.json').read_text(encoding='utf-8'))
        receipt = json.loads((d/'recovery.json').read_text(encoding='utf-8'))
        self.assertEqual(report['DC_current_A'], {'GMSAPVD:p': .001})
        self.assertAlmostEqual(report['reference_current']['recovered_A'], .0003)
        self.assertEqual(receipt['source_files_sha256'], self.pin['files'])
        self.assertEqual(receipt['raw_files_verified'], len(self.status['raw_inventory']))

    def test_real_collector_accepts_psf_dc_without_legacy_terminal_and_rejects_other_missing_trace(self):
        deck = self.case_dir/'bench.scs'
        case = dict(self.case, drive='n', AC_traces=['PNC_PREP','PNC_PREN'],
                    DC_currents=['GMSAPVD:p'])
        ac = mock.Mock(sweep_names=['freq'],values={
            'freq':[1000*10**(k/100) for k in range(819)],
            'PNC_PREP':[0.]*819,'PNC_PREN':[1.]*819})
        dc = parse_text('''HEADER
"analysis name" "dcOp"
TYPE
"V" FLOAT DOUBLE PROP("units" "V")
"I" FLOAT DOUBLE PROP("units" "A")
VALUE
"GMSR_REF" "V" 0.6714
"GFVDD:p" "I" -0.012
"GMSAPVD:p" "I" 0.001
END
''')
        op = mock.Mock(values={})
        inputs = dict(zip(('acResponse.ac','dcOp.dc','dcOpInfo.info'),(ac,dc,op)))
        self.assertNotIn('GMSRIREF:p',dc.values)
        with mock.patch.object(recovery.gm_select.comp_measure,'safe_raw',
                               side_effect=lambda root,status,name:inputs[name]):
            report = recovery.gm_select.measure(self.case_dir,case,self.status)
            self.assertAlmostEqual(report['reference_current']['recovered_A'],.0003)
            self.assertEqual(report['bench_sha256'],sha(deck))
            self.assertNotIn('GMSRIREF:p',report['DC_current_A'])
            del dc.values['GMSAPVD:p']
            with self.assertRaisesRegex(KeyError,'GMSAPVD'):
                recovery.gm_select.measure(self.case_dir,case,self.status)


if __name__ == '__main__':
    unittest.main()
