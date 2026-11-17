"""Opt in with PAM4_SWITCH64_LARGE_PSF_TEST=1 to check a complete >560 MiB recovery."""

from contextlib import ExitStack, nullcontext
from math import ceil
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import gm_switch64 as design
from gm_switch64 import metrics
from native import collect_r5
from pvt import model_preflight
from pvt.reference.psf_ascii import PsfData


MIN_PSF_BYTES = 560 * 1024**2
MODEL_ROOT = '/synthetic/private-kit'
EFFECTIVE_SCALE_LOG = b'scalefactor = 0.900\nSpectre completes with 0 errors, 0 warnings.\n'
SOLVER = '/synthetic/bin/spectre'
NORMAL_BIAS = .564
SWITCHED_BIAS = .559
EXCURSION_S = 120e-12


def fixture_models(_root, process, wrapper):
    return dict(schema='PAM4_PRIVATE_VM_KIT_PREFLIGHT_V1', model_root=MODEL_ROOT,
                process=process, root_section='top_'+process,
                active_shrink_sections=model_preflight.verify_wrapper(wrapper, process),
                kit_fingerprints={name:{'bytes':size, 'sha256':digest}
                                  for name,(size,digest) in model_preflight.KIT_PINS.items()},
                active_static_mos_scale=.9, static_identity_verified=True,
                actual_spectre_effective_scale='CHECK_ACTUAL_RUN_LOG',
                model_files_written=False, model_bodies_exported=False, simulation_started=False)


def trace_constants():
    constants = {'GMSKVBIAS':NORMAL_BIAS, 'X_vb':.58}
    for leg in ('P','M'):
        constants.update({trace:.0023 if i==1 else 0.
                          for i,trace in enumerate(metrics.TAIL_NODES[leg])})
    for lane in range(8):
        constants.update({f'X_h{lane}p':.215, f'X_h{lane}m':.205})
    for tail in metrics.XT2_PATHS:
        constants.update({tail+':vds':.2, tail+':vdsat':.19, tail+':region':2.})
    return constants


def phase_clock(ui_index, lane, vdd):
    return vdd if (ui_index-lane) % 8 < 4 else 0.


def value_line(name, value):
    return f'"{name}" {value:.16e}\n'.encode('ascii')


def write_psf(path, case):
    constants = trace_constants()
    clocks = [f'X_ck{lane}' for lane in range(8)]
    extra = {f'auxiliary_{index:02}':0. for index in range(13)}
    traces = [*constants, *extra, *clocks]
    assert {name for name in traces if name not in extra} == metrics.SWEEP_TRACES - {'time'}
    steady = b''.join(value_line(name,value) for name,value in constants.items())
    toggled = steady.replace(value_line('GMSKVBIAS',NORMAL_BIAS),
                             value_line('GMSKVBIAS',SWITCHED_BIAS), 1)
    auxiliary = b''.join(value_line(name,value) for name,value in extra.items())
    clock_grid = [b''.join(value_line(name,phase_clock(phase,lane,case['vdd_V']))
                           for lane,name in enumerate(clocks)) for phase in range(8)]
    stop = case['stop_s']
    end = case['switch_time_s'] + case['slew_s'] + case['offset_s']
    prescribed_uis = round(stop/metrics.UI)
    sample_bytes = len(value_line('time',0.)) + len(steady) + len(auxiliary) + len(clock_grid[0])
    samples_per_ui = ceil(MIN_PSF_BYTES / (sample_bytes*prescribed_uis))
    intervals = prescribed_uis*samples_per_ui
    with path.open('xb',buffering=1024*1024) as psf:
        psf.write(b'HEADER\n"PSFversion" "1.00"\nTYPE\n"scalar" FLOAT DOUBLE\n'
                  b'SWEEP\n"time" "scalar" PROP("units" "s")\nTRACE\n')
        for name in traces:
            psf.write(f'"{name}" "scalar"\n'.encode('ascii'))
        psf.write(b'VALUE\n')
        for i in range(intervals+1):
            t = stop*i/intervals
            traces = toggled if end < t < end+EXCURSION_S else steady
            psf.write(value_line('time',t) + traces + auxiliary + clock_grid[(i//samples_per_ui)%8])
        psf.write(b'END\n')
    return samples_per_ui, intervals


def hold_fixture(case, samples_per_ui, intervals):
    times = [case['stop_s']*i/intervals for i in range(intervals+1)]
    data = PsfData()
    data.sweep_names = ['time']
    data.sweep_properties = {'time':{'units':'s'}}
    data.sha256 = 'synthetic_hold'
    data.values = {'time':times, **{name:[value]*len(times) for name,value in trace_constants().items()}}
    for lane in range(8):
        data.values[f'X_ck{lane}'] = [phase_clock(i//samples_per_ui,lane,case['vdd_V'])
                                    for i in range(len(times))]
    return metrics.measurement(data,case)


def simulated_link(src, dst):
    # Windows sandbox denies os.link. This fixture's exclusive copy still executes
    # the real production publication logic and creates single-link sidecars.
    with Path(src).open('rb') as source, Path(dst).open('xb') as destination:
        shutil.copyfileobj(source,destination)


@unittest.skipUnless(os.environ.get('PAM4_SWITCH64_LARGE_PSF_TEST')=='1',
                     'Set PAM4_SWITCH64_LARGE_PSF_TEST=1 for the >560 MiB integration test')
class Switch64LargeEndpoint(unittest.TestCase):
    def test_runner_to_collect_only_to_original_hold_summary(self):
        import recover_switch64_endpoint as recovery

        began = perf_counter()
        with TemporaryDirectory(prefix='sw64-large-test-') as temporary, ExitStack() as stack:
            workspace = Path(temporary).resolve(strict=True)
            original, retry = workspace/'original', workspace/'retry'
            original.mkdir()
            retry.mkdir()
            cases = design.common.read(design.PLAN)['cases']
            switch_case, hold_case = cases[84], cases[83]
            case_id = switch_case['case_id']
            prior_dir, retry_dir, hold_dir = original/case_id, retry/case_id, original/hold_case['case_id']
            common = design.common
            stack.enter_context(patch.object(model_preflight,'verify_private_kit',side_effect=fixture_models))
            if os.name=='nt':
                stack.enter_context(patch.object(os,'getuid',return_value=workspace.lstat().st_uid,create=True))
                stack.enter_context(patch.object(recovery,'lock_case',side_effect=lambda _: nullcontext()))
                stack.enter_context(patch.object(os,'link',side_effect=simulated_link))

            for case, directory in ((switch_case,prior_dir),(switch_case,retry_dir),(hold_case,hold_dir)):
                design.stage(case,directory,Path(MODEL_ROOT))

            limit_settings=[]
            fake_resource=SimpleNamespace(RLIMIT_FSIZE=1,RUSAGE_CHILDREN=2,
                                          setrlimit=lambda _,limits:limit_settings.append(limits),
                                          getrusage=lambda _:SimpleNamespace(ru_maxrss=0))
            fake_grid=None

            def produce_psf(argv, *, cwd, preexec_fn, **_kwargs):
                self.assertEqual(argv[:4],[SOLVER,'-64','+mt=1','bench.scs'])
                preexec_fn()
                if cwd==prior_dir:
                    (cwd/'spectre.log').write_bytes(b'USIMUWI-20006 not enough virtual memory\n')
                    return SimpleNamespace(returncode=1)
                self.assertEqual(cwd,retry_dir)
                (cwd/'spectre.log').write_bytes(EFFECTIVE_SCALE_LOG)
                raw_dir=cwd/'raw'
                raw_dir.mkdir()
                nonlocal fake_grid
                fake_grid=write_psf(raw_dir/'codeSwitch.tran.tran',switch_case)
                return SimpleNamespace(returncode=0)

            def run_classic(directory, *, job, bound):
                deck_sha=common.sha(directory/'bench.scs')
                meta=dict(format='pam4_gmdrive_run_v1',case_id=case_id,
                          case_sha256=common.sha(directory/'case.json'),plan_sha256=common.sha(design.PLAN))
                (directory/'.study_owned').write_bytes(f'{job}\n'.encode('ascii'))
                with (patch.dict(sys.modules,{'resource':fake_resource}),
                      patch.dict(os.environ,{'SLURM_JOB_ID':job}),
                      patch.object(common.subprocess,'run',side_effect=produce_psf)):
                    return common.run_classic(directory,deck_sha,meta,1200,SOLVER,{},max_solver_file_bytes=bound)

            with self.assertRaisesRegex(ValueError,'Solver failed'):
                run_classic(prior_dir,job='757597',bound=common.DEFAULT_SOLVER_FILE_BYTES)
            status=run_classic(retry_dir,job='757730',bound=metrics.ENDPOINT_RETRY_FILE_BYTES)
            self.assertEqual(limit_settings,[(512*1024**2,)*2,(640*1024**2,)*2])
            transient=retry_dir/'raw'/'codeSwitch.tran.tran'
            size=transient.stat().st_size
            self.assertGreaterEqual(size,MIN_PSF_BYTES)
            self.assertLess(size,metrics.ENDPOINT_RETRY_FILE_BYTES)
            with self.assertRaisesRegex(ValueError,'collector bound'):
                collect_r5.ensure_end(transient)
            original_status_hash=common.sha(prior_dir/'run_status.json')
            retry_status_hash=common.sha(retry_dir/'run_status.json')
            run_and_write=perf_counter()
            with patch.object(common.subprocess,'run',side_effect=AssertionError('Collect-only started a subprocess')):
                result=recovery.recover(original,retry,switch_case,size,'c'*64,'d'*64)
            self.assertEqual(result,'recovered')
            elapsed_collect=perf_counter()-run_and_write

            raw_hash=status['raw_inventory'][0]['sha256']
            self.assertEqual(common.sha(transient),raw_hash)
            self.assertEqual(common.sha(prior_dir/'run_status.json'),original_status_hash)
            self.assertEqual(common.sha(retry_dir/'run_status.json'),retry_status_hash)
            report=design.gm_summary.read_case(retry,switch_case,design.PLAN)
            self.assertEqual(report['recovery_mode'],'collect-only')
            self.assertEqual(report['tran_sha256'],raw_hash)
            self.assertEqual(len(report['held_by_lane']),8)
            self.assertEqual(len(report['XT2_by_window']['final']),16)
            del report

            hold=hold_fixture(hold_case,*fake_grid)
            hold_bench_sha=common.sha(hold_dir/'bench.scs')
            (hold_dir/'spectre.log').write_bytes(EFFECTIVE_SCALE_LOG)
            common.write_new(hold_dir/'run_status.json',dict(status='spectre_completed',exit_code=0,
                case_id=hold_case['case_id'],case_sha256=common.sha(hold_dir/'case.json'),
                plan_sha256=common.sha(design.PLAN),spectre_log_sha256=common.sha(hold_dir/'spectre.log'),
                input_deck_sha256_before=hold_bench_sha,input_deck_sha256_after=hold_bench_sha))
            hold.update(measurement_complete=True,bench_sha256=hold_bench_sha,
                        run_status_sha256=common.sha(hold_dir/'run_status.json'))
            common.write_new(hold_dir/'measurements.json',hold)
            common.write_new(hold_dir/'completion.json',dict(measurement_complete=True,
                measurement_sha256=common.sha(hold_dir/'measurements.json')))
            del hold

            summary=design.summarize(original,retry)
            transition=next(row for row in summary['transitions'] if row['case_id']==case_id)
            self.assertEqual(transition['reference_case_id'],hold_case['case_id'])
            pair=transition['comparison']
            self.assertTrue(pair['settled'],pair)
            self.assertEqual(pair['status'],'observed_recovery')
            self.assertAlmostEqual(pair['recovery_s_after_event'],EXCURSION_S,delta=switch_case['stop_s']/fake_grid[1])
            self.assertTrue(all(n>=8 for n in pair['post_settle_samples_by_lane']))
            self.assertEqual(summary['endpoint_retry']['case_evidence'][case_id]['transient_psf_bytes'],size)
            self.assertFalse(summary['ready_to_design_C0'])  # Other physical cases are absent from the fixture.
            print(f'PSF={size} bytes ({size/1024**2:.3f} MiB), samples={fake_grid[1]+1}, '
                  f'collect-only={elapsed_collect:.2f}s, total={perf_counter()-began:.2f}s, '
                  f'paired recovery={pair["recovery_s_after_event"]*1e12:.3f} ps', flush=True)


if __name__=='__main__':
    unittest.main()
