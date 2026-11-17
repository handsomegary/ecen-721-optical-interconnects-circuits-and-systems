import re
import unittest

import gm_gmtap_common
import gm_switch64_rf as switch


def fixture(initial=1, final=2, process='ss', **updates):
    case = next(c for c in gm_gmtap_common.build_plan()['cases'] if
                c['process']==process and c['code']==initial and c['drive']=='p' and c['group']=='divider')
    case = dict(case,initial_code=initial,final_code=final,switch_time_s=2e-9,stop_s=12e-9,
                slew_s=2e-12,skew_ps=0.)
    return dict(case,**updates)


def rendered(case):
    return switch.render(case,switch.BASE.MODEL_TOKEN)[0]


class SwitchRendering(unittest.TestCase):
    def test_adjacent_carry_only_changes_exact_native_enable_sources(self):
        case = fixture(offset_s=3e-12)
        deck = rendered(case)
        lines = re.findall(r'(?m)^GMSK\d{2}VE\d+ [^\n]+type=pwl[^\n]+$',deck)
        self.assertEqual({row.split(' ',1)[0] for row in lines},
                         {'GMSK11VE16','GMSK16VE15','GMSK16VE16'})
        self.assertEqual(len(re.findall(r'(?m)^GMSK\d{2}VE\d+ ',deck)),54)
        for row in lines:
            wave = re.search(r'wave=\[(.*)\]',row)[1]
            t0,v0,t1,v1,t2,v2 = map(float,wave.split())
            self.assertEqual((t0,v1),(0.,v0))
            self.assertAlmostEqual(t2-t1,case['slew_s'],places=18)
            self.assertAlmostEqual(t1,case['switch_time_s']+case['offset_s']*(v2>v1),places=18)
            self.assertEqual(float(re.search(r' dc=(\S+)',row)[1]),v0)
        without_switch = rendered(fixture(final=1))
        changeable = re.compile(r'(?m)^GMSK\d{2}VE\d+ [^\n]+\n|^save [^\n]+\n')
        self.assertEqual(changeable.sub('',deck),changeable.sub('',without_switch))

    def test_fixed_destination_retains_native_bias_and_runs_only_the_switch_transient(self):
        deck = rendered(fixture(initial=0,final=0))
        self.assertNotRegex(deck,re.compile(r'(?m)^GMSK\d{2}VE\d+ [^\n]+type=pwl'))
        self.assertIn('XVb (X_vb 0) vsource dc=0.58',deck)
        self.assertIn('GMSKVRU (GMSKVDIVIN GMSKV1RAW) resistor r=375',deck)
        self.assertIn('GMSKVRD (GMSKV1RAW 0) resistor r=14125',deck)
        self.assertIn('GMSKVC1 (GMSKVBIAS 0) capacitor c=2p',deck)
        analyses = re.findall(r'(?m)^(\w+) (?:tran|ac|noise)\b',deck)
        self.assertEqual(analyses,['codeSwitch'])
        saved = set(re.search(r'(?m)^save ([^\n]+)$',deck)[1].split())
        self.assertEqual(saved,set(switch.TRACES))

    def test_r5_clock_gates_are_restored_on_all_eight_lanes_at_corner_vdd(self):
        deck = rendered(fixture(initial=0,final=-60,process='ff'))
        for i in range(8):
            self.assertIn(f'XCK{i} (X_ck{i} 0) vsource type=pulse val0=0 val1=0.99',deck)
            self.assertIn(f'XKB{i} (X_kb{i} 0) vsource type=pulse val0=0.99 val1=0',deck)
            for leg in 'pm':
                self.assertIn(f'XSN{i}{leg} (X_h{i}{leg} X_ck{i} X_o_{leg} 0)',deck)
                self.assertIn(f'XSP{i}{leg} (X_h{i}{leg} X_kb{i} X_o_{leg} X_vdd)',deck)

    def test_pam4_levels_and_skew(self):
        case = fixture(skew_ps=4.464285714285714)
        p = switch.stimulus(case,'p')
        m = switch.stimulus(case,'m')
        self.assertEqual(len(p),len(m))
        self.assertEqual(p[0],m[0])
        for (tp,vp),(tm,vm) in zip(p[1:],m[1:]):
            self.assertAlmostEqual(tp-tm,case['skew_ps']*1e-12,places=18)
            self.assertAlmostEqual(vp,-vm)
        self.assertAlmostEqual(2*(max(v for _,v in p)-min(v for _,v in p)),.4)
        self.assertAlmostEqual(p[25][0]-p[1][0],16*switch.UI,places=18)

    def test_case_must_match_initial_static_weights(self):
        with self.assertRaises(ValueError):
            rendered(fixture(code=0))
        with self.assertRaises(ValueError):
            rendered(fixture(stop_s=1.9e-9))
