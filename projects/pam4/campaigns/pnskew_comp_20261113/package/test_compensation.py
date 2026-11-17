import cmath
import math
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import comp_cell as cell
import comp_measure as measure
import comp_plan
import comp_run
import comp_summary
import pilot_controller as controller


def pilot(delta, common=0.):
    out = {}
    for f in controller.FREQUENCIES_HZ:
        p = .01*cmath.exp(-2j*math.pi*f*(common+delta/2)*1e-12)
        n = -.008*cmath.exp(-2j*math.pi*f*(common-delta/2)*1e-12)
        out[str(int(f))] = {'p': [p.real,p.imag], 'n': [n.real,n.imag]}
    return out


class CompensationTests(unittest.TestCase):
    def test_blind_signed_search_and_holdout_disagreement(self):
        def candidate(p,dt,verify=None):
            return dict(p_code=p,n_code=63-p,train=pilot(dt,5.),verify=pilot(dt if verify is None else verify,8.))
        rows = [candidate(16,-2.2),candidate(24,.16),candidate(32,2.6)]
        result = controller.select(rows,.25,.075)
        self.assertEqual((result['status'],result['p_code'],result['n_code']),('LOCK',24,39))
        self.assertAlmostEqual(result['verification_fit']['estimated_residual_ps'],.16,places=9)
        rows[1] = candidate(24,.16,.42)
        self.assertEqual(controller.select(rows,.25,.075)['status'],'NO_LOCK')
        rows[1]['true_skew_ps'] = 4.464
        with self.assertRaisesRegex(ValueError,'only codes and pilot'):
            controller.select(rows,.25,.075)

    def test_fixed_plan_27_full_codes_and_20_seeds(self):
        plan = comp_plan.build()
        for corner in comp_plan.CORNERS:
            rows = [c for c in plan['cases'] if c['source_ohm']==25 and
                    (c['process'],c['temperature_C'],c['vdd_V'])==corner]
            self.assertEqual(len(rows),130)
            self.assertEqual({(c['p_code'],c['n_code'],c['drive']) for c in rows if not c['bypass']},
                             {(k,63-k,drive) for k in range(64) for drive in ('p','n')})
        seeds = [(r['injected_skew_UI'],r['seed']) for r in plan['integrated_plan'] if r['study']=='noise']
        self.assertEqual(set(seeds),{(d,s) for d in (-.5,0.,.5) for s in range(1001,1021)})

    def test_parent_circuit_and_corner_geometry_are_preserved(self):
        ac,r5 = cell.load_inputs()
        cards = cell.device_cards(r5)
        c = comp_plan.ac_case(('ss',85,.81),63,'p',25,False,'unit')
        deck = cell.ac_deck(ac,cards,c,cell.MODEL_TOKEN)
        self.assertIn('section=ss',deck)
        self.assertIn('options temp=85 tnom=25',deck)
        self.assertIn('XVs (X_vdd 0) vsource dc=0.81',deck)
        self.assertIn('PNCP0TN0 (PNCP0C0 PNCPGN0 PNCP0M 0) '+cards['N'],deck)
        self.assertIn('PNCN3TP5 (PNCN3C5 PNCNGP5 PNCN3M PNC_VDD) '+cards['P'],deck)
        self.assertEqual([l for l in ac.splitlines() if l.startswith(('XM','XT','XS','XRdeg'))],
                         [l for l in deck.splitlines() if l.startswith(('XM','XT','XS','XRdeg'))])

    def test_exact_r5_stimulus_then_only_named_integration_changes(self):
        _,r5 = cell.load_inputs()
        admission = {'model_root':'/test/private','original_model_root':'<PDK_ROOT>',
                     'source_decks':{'noiseless':{'sha256':cell.R5_SHA,'original_vm_sha256':cell.R5_SHA}}}
        c = dict(stimulus=dict(case_id='unit',kind='pam4_noiseless',delta_ui=0,noise_seed=None),
                 p_code=31,n_code=32,vdd_V=.9,added_differential_stress_ps=0)
        _, deck, profile = cell.tran_deck(r5,admission,c,cell.device_cards(r5))
        self.assertIn('CHB2p (PNC_PREP X_cm CH2_p X_cm) vcvs gain=1',deck)
        self.assertEqual(next(l for l in deck.splitlines() if l.startswith('tranResponse ')),
                         next(l for l in r5.splitlines() if l.startswith('tranResponse ')))
        self.assertAlmostEqual(profile['stop_s'],2.941428571428571e-08)
        _, short, pilot = cell.pilot_deck(r5,admission,c,cell.device_cards(r5))
        self.assertLess(pilot['pilot_stop_s'],1e-8)
        self.assertLess(len(short),len(deck))
        self.assertIn('save X_ip X_im\n',short)
        for name in ('PAM4Vp','PAM4Vm'):
            t = cell.pn_stage.pwl_block(short.encode('ascii'),name)[4]
            self.assertLess(t[-1]-pilot['pilot_stop_s'],3*cell.UI)

    def test_native_pilot_sample_reduction_with_known_time_skew(self):
        t = [k*cell.UI/32 for k in range(33632)]
        dt = .37e-12
        def signal(x):
            return sum(.004*math.sin(2*math.pi*f*x) for f in controller.FREQUENCIES_HZ)
        raw = SimpleNamespace(sweep_names=['time'],values={'time':t,
                     'X_ip':[.7+signal(x-dt/2) for x in t],'X_im':[.7-signal(x+dt/2) for x in t]})
        result = measure.pilot_report(raw,t[-1])
        self.assertAlmostEqual(controller.fit(result['train'])['estimated_residual_ps'],.37,places=4)
        self.assertAlmostEqual(controller.fit(result['verify'])['estimated_residual_ps'],.37,places=4)

    def test_missing_phase_probe_cannot_be_labeled_measured(self):
        rows={0:{'P_delay':{'fit_delay_ps':0},'N_delay':{'fit_delay_ps':1}}}
        self.assertEqual(comp_summary.codebook(rows)['status'],'PARTIAL')


if __name__ == '__main__':
    unittest.main()
