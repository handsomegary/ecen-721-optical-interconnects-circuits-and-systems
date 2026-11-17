"""Regression fixtures for native Spectre 23.1 PSF unit declarations."""
import unittest

from pvt.reference.psf_ascii import parse_text


class PsfDeclarationUnits(unittest.TestCase):
    def test_spectre_stb_sweep_inline_unit_is_retained(self):
        data = parse_text('''HEADER
"analysis type" "stb"
TYPE
"sweep" FLOAT DOUBLE
"complex" COMPLEX DOUBLE
SWEEP
"freq" "sweep" PROP("sweep direction" "ascending" "units" "Hz")
TRACE
"loopGain" "complex" PROP("units" "1")
VALUE
"freq" 1
"loopGain" (-451.17 0.001)
"freq" 10
"loopGain" (-450.14 0.1)
END
''')
        self.assertEqual(data.sweep_names, ['freq'])
        self.assertEqual(data.sweep_types, {'freq':'sweep'})
        self.assertEqual(data.sweep_properties['freq'], {'sweep direction':'ascending','units':'Hz'})
        self.assertEqual(data.trace_types, {'loopGain':'complex'})
        self.assertEqual(data.trace_properties, {'loopGain':{'units':'1'}})
        self.assertEqual(data.unit('freq'), 'Hz')
        self.assertEqual(data.unit('loopGain'), '1')
        self.assertEqual(data.values['loopGain'], [complex(-451.17,.001),complex(-450.14,.1)])

    def test_value_unit_overrides_trace_and_trace_overrides_type(self):
        data = parse_text('''TYPE
"number" FLOAT DOUBLE PROP("units" "TYPE_UNIT")
SWEEP
"time" "number" PROP("units" "s")
TRACE
"XT2p0:vds" "number" PROP("units" "V")
"override" "number" PROP("units" "TRACE_UNIT")
"onlyType" "number" PROP("name" "source")
VALUE
"time" 0
"XT2p0:vds" 0.2
"override" 1 PROP("units" "VALUE_UNIT")
"onlyType" 1
END
''')
        self.assertEqual(data.unit('time'), 's')
        self.assertEqual(data.unit('XT2p0:vds'), 'V')
        self.assertEqual(data.unit('override'), 'VALUE_UNIT')
        self.assertEqual(data.unit('onlyType'), 'TYPE_UNIT')
        self.assertIsNone(data.unit('missing'))

    def test_native_margin_explicit_value_types_remain_available(self):
        data = parse_text('''HEADER
"analysis type" "margin.stb"
TYPE
"Deg" FLOAT DOUBLE
"dB" FLOAT DOUBLE
"Hz" FLOAT DOUBLE
VALUE
"phaseMargin" "Deg" 84.034
"gainMargin" "dB" 19.625
"phaseMarginFreq" "Hz" 1.0336e7
"gainMarginFreq" "Hz" 5.1316e8
END
''')
        self.assertEqual(data.sweep_names, [])
        self.assertEqual(data.trace_types, {'phaseMargin':'Deg','gainMargin':'dB',
                                          'phaseMarginFreq':'Hz','gainMarginFreq':'Hz'})
        self.assertEqual(data.values['phaseMargin'], [84.034])
        self.assertEqual(data.values['gainMargin'], [19.625])
        self.assertEqual(data.values['phaseMarginFreq'], [1.0336e7])
        self.assertEqual(data.values['gainMarginFreq'], [5.1316e8])


if __name__=='__main__':
    unittest.main()
