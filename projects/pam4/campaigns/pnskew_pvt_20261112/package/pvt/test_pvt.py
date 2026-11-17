"""Local structural and analyzer checks. No simulator or PDK access."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from collect_ac import measure, require_effective_scale, validate_sweep
from generate import CORNER_FILE, REFERENCE, PVT_POINTS, case_id, render_case, render_nominal, sha
from model_preflight import CORE, MODEL_TOP, SHRINK, check_kit_contents, materialize_corner, read_portable_case, stage
from render_transient import apply_pvt

HERE = Path(__file__).resolve().parent


class PvtDeckTests(unittest.TestCase):
    def test_grid_matches_frozen_parent_and_retained_metadata(self):
        grid = HERE/'cases'
        records = json.loads((grid/'pvt_ac_matrix.json').read_text(encoding='utf-8'))['cases']
        nominal = (grid/'nominal_parent.scs.txt').read_bytes()
        cards = json.loads((REFERENCE/'native_geometry.json').read_text(encoding='utf-8'))['cards']
        self.assertEqual(render_nominal(cards),nominal)
        self.assertEqual(len(records),27)
        self.assertEqual(len({record['case_id'] for record in records}),27)
        for process,temp,vdd in PVT_POINTS:
            with self.subTest(process=process,temp=temp,vdd=vdd):
                directory = grid/case_id(process,temp,vdd)
                case,deck,wrapper = read_portable_case(directory)
                self.assertEqual(case,next(record for record in records if record['case_id']==case['case_id']))
                self.assertEqual(case['estimate']['requested_wall_minutes'],30)
                self.assertEqual(render_case(nominal,process,temp,vdd),(deck,case['modified_deck_lines_one_based']))
                self.assertLessEqual(set(case['modified_deck_lines_one_based']),{2,3,5})
                self.assertEqual(wrapper is None,process=='tt')
        self.assertEqual((grid/'r3_pvt_ac_tt_t25_v090'/'bench.scs').read_bytes(),nominal)

    def test_three_exact_quiet_transient_edits(self):
        quiet = (HERE.parent/'r5_original'/'quiet.scs').read_bytes()
        root = '<PDK_ROOT>'
        for process,temp,vdd in (('ss',85,.81),('ff',-40,.99)):
            case = dict(process=process,temperature_C=temp,vdd_V=vdd,kind='pam4_noiseless',delta_ui=0)
            changed = apply_pvt(quiet,case,root)
            self.assertEqual([i for i,(a,b) in enumerate(zip(quiet.splitlines(),changed.splitlines()),1) if a!=b],
                             [2,3,5])
            self.assertIn(f'include "{CORNER_FILE}" section=top_{process}'.encode(),changed)
            self.assertIn(f'dc={vdd}'.encode(),changed)
            with self.assertRaisesRegex(ValueError,'quiet, zero-skew'):
                apply_pvt(quiet,dict(case,delta_ui=.1),root)

    def test_original_model_routes_and_exact_root_materialization(self):
        wrapper = (REFERENCE/CORNER_FILE).read_bytes()
        for process in ('tt','ss','ff'):
            suffixes = ('macro_mos_moscap','_res_bip_dio_disres','_mom','_r_metal')
            names = [process+x for x in suffixes]
            sections = [f'section {name}\nendsection {name}\n' for name in names]
            sections[0] = (f'section {names[0]}\na options scalefactor=0.9\n'
                           f'include "{CORE}" section={process}\nendsection {names[0]}\n')
            files = {MODEL_TOP:('section tt\n'+''.join(f'include "{SHRINK}" section={name}\n' for name in names)
                                +'endsection tt\n').encode(),
                     SHRINK:''.join(sections).encode(), CORE:f'section {process}\nendsection {process}\n'.encode()}
            self.assertEqual(check_kit_contents(files,process,wrapper),names)
            bad = dict(files,**{SHRINK:files[SHRINK].replace(b'0.9',b'1.0')})
            with self.assertRaisesRegex(ValueError,'scalefactor'):
                check_kit_contents(bad,process,wrapper)
            with self.assertRaisesRegex(ValueError,'core-model section absent'):
                check_kit_contents(dict(files,**{CORE:b'section another_process\nendsection\n'}),process,wrapper)
        resolved = materialize_corner(wrapper,'/auth/private/kit')
        self.assertEqual(resolved.replace(b'/auth/private/kit',b'@pdk_28nm_root@'),wrapper)

    def test_stage_copies_resolved_wrapper_and_refuses_existing_destination(self):
        parent = HERE/'cases'/'r3_pvt_ac_ss_t85_v081'
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'single_case'
            proof = dict(model_root='/auth/private/kit', static_identity_verified=True, process='ss')
            with patch('model_preflight.verify_private_kit',return_value=proof):
                stage(parent,'unused',target)
                with self.assertRaises(FileExistsError):
                    stage(parent,'unused',target)
            case = json.loads((target/'case.json').read_text(encoding='utf-8'))
            self.assertEqual(case['preflight_sha256'],sha((target/'model_preflight.json').read_bytes()))
            self.assertEqual(case['bench_sha256'],sha((target/'bench.scs').read_bytes()))
            self.assertEqual(case['inputs_sha256'][CORNER_FILE],sha((target/CORNER_FILE).read_bytes()))


def log_grid(start,stop,dec):
    x = [start]
    while x[-1]*10**(1/dec)<stop:
        x.append(x[-1]*10**(1/dec))
    return x


class PvtMeasurementTests(unittest.TestCase):
    def test_frozen_track_measurement_and_noise_band(self):
        fx,nx = log_grid(1e3,150e9,50),log_grid(1e6,56e9,40)
        real_input = {'X_ip':[.5]*len(fx),'X_im':[-.5]*len(fx)}
        shape = [2 if f<1e10 else 20 for f in fx]
        ac = SimpleNamespace(sweep_names=['freq'],values=dict(real_input,freq=fx,X_o_p=shape,X_o_m=[0]*len(fx),
                                                             X_h0p=[v/2 for v in shape],X_h0m=[0]*len(fx)))
        dc = SimpleNamespace(values={'X_'+n:[.43] for n in ('o_p','o_m','c_p','c_m','s1_p','s1_m','s2_p','s2_m')})
        dc.values['XVs:p'] = [-.01]
        op = SimpleNamespace(values={'XT1p0.sub_device':[dict(vds=.14,vdsat=.10,gm=.02)]})
        noise = SimpleNamespace(sweep_names=['freq'],values={'freq':nx,'out':[1e-9]*len(nx)},unit=lambda _: 'V/sqrt(Hz)')
        summary = measure(ac,dc,op,noise,.9)
        self.assertAlmostEqual(summary['afe_output']['peaking_56GHz_vs_1kHz_dB'],20)
        self.assertAlmostEqual(summary['afe_output']['gain_56GHz_VV'],20)
        self.assertAlmostEqual(summary['frozen_tracking_lane0']['gain_56GHz_VV'],10)
        self.assertAlmostEqual(summary['frozen_tracking_noise_1MHz_to_56GHz_Vrms'],(56e9-1e6)**.5*1e-9)
        self.assertAlmostEqual(summary['static_afe_supply_power_W'],.009)
        self.assertAlmostEqual(summary['representative_tail_primitive_OP']['XT1p0']['vds_minus_vdsat_V'],.04)
        self.assertTrue(summary['afe_output_56GHz_max_peaking_metric_met'])

    def test_missing_sweep_or_wrong_effective_scale_blocks(self):
        frequencies = log_grid(1e6,56e9,40)
        del frequencies[8]
        data = SimpleNamespace(sweep_names=['freq'],values={'freq':frequencies})
        with self.assertRaisesRegex(ValueError,'sparse'):
            validate_sweep(data,'freq',1e6,56e9,40)
        require_effective_scale(b'    scalefactor = 0.9\n')
        require_effective_scale(b"WARNING (SFE-1131): `scalefactor` specified twice. The last value is 0.9.\n")
        for log in (b'Spectre complete',b'scalefactor = 0.9\nscalefactor = 1.0'):
            with self.assertRaisesRegex(ValueError,'scalefactor'):
                require_effective_scale(log)


if __name__=='__main__':
    unittest.main()
