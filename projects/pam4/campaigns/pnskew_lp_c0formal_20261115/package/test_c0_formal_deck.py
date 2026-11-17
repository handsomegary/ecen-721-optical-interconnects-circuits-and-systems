"""Protect source/clock-only C0 changes and signed skew generation."""

import hashlib
import math
import re
import unittest

import c0_formal  # Set up the pinned C0 dependencies for the formal package.
import c0_formal_deck as deck


def without_pwl(data):
    for name in ('PAM4Vp','PAM4Vm'):
        begin,end,*_ = deck.review.pn_stage.pwl_block(data,name)
        data = data[:begin]+data[end:]
    return data


class FormalDeck(unittest.TestCase):
    def test_common_phase_moves_all_primary_and_secondary_clock_sources(self):
        base, original = deck.render('zero',0,0,'training')
        for phase in (-1,1):
            data, shifted = deck.render('zero',0,phase,'training')
            before = list(deck.PULSE.finditer(base.decode('ascii')))
            after = list(deck.PULSE.finditer(data.decode('ascii')))
            self.assertEqual(len(before),144)
            self.assertEqual(len(after),144)
            delta = phase*deck.review.UI/8
            for x,y in zip(before,after,strict=True):
                self.assertEqual(x[1],y[1])
                self.assertEqual(deck.DELAY.sub('delay=*',x[0]),deck.DELAY.sub('delay=*',y[0]))
                x_delay = deck.review.pn_stage.number(deck.DELAY.search(x[0])[1])
                y_delay = deck.review.pn_stage.number(deck.DELAY.search(y[0])[1])
                self.assertTrue(math.isclose(y_delay-x_delay,delta,abs_tol=1e-24))
            self.assertEqual(deck.PULSE.sub('',base.decode('ascii')),deck.PULSE.sub('',data.decode('ascii')))
            for names,fields in (('primary_clocks',('delay','first_rise_midpoint_s','first_fall_midpoint_s')),
                                 ('secondary_clocks',('first_open_midpoint_s','first_close_midpoint_s'))):
                for x,y in zip(original['clock_spec'][names],shifted['clock_spec'][names],strict=True):
                    for key,value in x.items():
                        self.assertEqual(y[key],value+delta if key in fields else value)

    def test_fresh_streams_skew_and_guard_preserve_the_reviewed_netlist(self):
        source = deck.review.ROOT/'decks'/'c0_00_tt_zero.scs'
        template = re.sub(rb'(?m)^(tranResponse tran stop=)[^\s]+',rb'\g<1>6.5e-09',source.read_bytes())
        for stimulus in ('training','payload'):
            sequence = deck.symbols(stimulus)
            for condition,skew in deck.SKEW_PS.items():
                data,info = deck.render(condition,0,0,stimulus)
                self.assertEqual(without_pwl(data),without_pwl(template))
                self.assertEqual(hashlib.sha256(data).hexdigest(),info['deck_sha256'])
                for name,sign in (('PAM4Vp',1),('PAM4Vm',-1)):
                    *_, times, values = deck.review.pn_stage.pwl_block(data,name)
                    self.assertGreater(times[-1],info['stop_s'])
                    self.assertEqual(len(times),1+2*(len(sequence)-1))
                    for i in (deck.WARMUP,deck.WARMUP+deck.SCORED_INPUTS-1):
                        offset = sign*skew*1e-12/2
                        self.assertAlmostEqual(times[2*i],deck.T0+i*deck.review.UI+offset+deck.EDGE,places=23)
                        self.assertAlmostEqual(values[2*i],sign*(sequence[i]-1.5)*(.4/6),places=14)
        self.assertNotEqual(deck.symbols('training'),deck.symbols('payload'))


if __name__ == '__main__':
    unittest.main()
