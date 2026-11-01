"""Transport acceptance must reject bad readings and unknown output state."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from gpib_macarm import GpibTimeoutError

spec = importlib.util.spec_from_file_location('keithley_acquire', Path(__file__).parents[1] / 'tools/keithley_2400_acquire.py')
acquire = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acquire)


class AcquisitionTests(unittest.TestCase):
    def test_accepts_finite_four_wire_reading_and_keeps_source_field_label(self):
        rows = acquire.parse_readings('15.8,2.5e-6,1,4230148', 1, 2.5e-6, 21)
        self.assertEqual(rows[0]['programmed_current_a'], 2.5e-6)
        self.assertEqual(rows[0]['measured_voltage_v'], 15.8)

    def test_rejects_overflow_bad_status_source_mismatch_and_compliance(self):
        for reply in ('9.91e37,2.5e-6,1,4230148', '15.8,2.5e-6,1,4230156',
                      '15.8,3e-6,1,4230148', '20.5,2.5e-6,1,4230148',
                      'nan,2.5e-6,1,4230148', '15.8,2.5e-6,1,4230148.5',
                      '15.8,2.5e-6,1', '15.8,2.5e-6,1,0'):
            with self.subTest(reply=reply), self.assertRaises(ValueError):
                acquire.parse_readings(reply, 1, 2.5e-6, 21)

    def test_rejects_backwards_time_and_wrong_number_of_readings(self):
        reply = '1,2.5e-6,2,4230148,1,2.5e-6,1,4230148'
        with self.assertRaisesRegex(ValueError, 'backwards'):
            acquire.parse_readings(reply, 2, 2.5e-6, 21)
        with self.assertRaisesRegex(ValueError, 'fields'):
            acquire.parse_readings(reply, 1, 2.5e-6, 21)

    def test_shutdown_never_claims_output_off_after_communication_loss(self):
        class FailedInstrument:
            def write(self, command):
                raise RuntimeError('Communication lost')

            def query(self, command):
                raise RuntimeError('Communication lost')
        result = acquire.shutdown(FailedInstrument())
        self.assertFalse(result['output_off_confirmed'])
        self.assertTrue(result['manual_output_check_required'])
        self.assertEqual(len(result['errors']), 4)

    def test_batch_timeout_is_never_replayed(self):
        class Instrument:
            reads = 0
            automatic_clear = '1'

            def write(self, command):
                pass

            def query(self, command):
                if command == ':READ?':
                    self.reads += 1
                    raise GpibTimeoutError('Measurement may have executed')
                return {'*IDN?': 'Maker,MODEL 2400,TEST,1.0', ':OUTP?': '0',
                        ':TRAC:POIN:ACT?': '0', ':SOUR:FUNC?': 'CURR', ':SOUR:CURR?': '2.5e-6',
                        ':SENS:FUNC?': 'VOLT', ':SENS:VOLT:PROT?': '21', ':SYST:RSEN?': '1',
                        ':SOUR:CLE:AUTO?': self.automatic_clear, ':SOUR:CLE:AUTO:MODE?': 'TCO',
                        ':TRIG:COUN?': '1', ':SYST:ERR?': '0,"No error"'}[command]
        with tempfile.TemporaryDirectory() as folder, patch.object(acquire.time, 'sleep'):
            args = SimpleNamespace(current=2.5e-6, compliance=21, nplc=5, delay=.05,
                                   points=1, seconds=600, output=Path(folder) / 'timeout')
            inst = Instrument()
            with self.assertRaises(GpibTimeoutError):
                acquire.acquire(inst, args, {}, lambda: None)
            self.assertEqual(inst.reads, 1)
            inst = Instrument()
            inst.automatic_clear = '0'
            args.output = Path(folder) / 'unsafe-config'
            with self.assertRaisesRegex(ValueError, 'automatic output-off'):
                acquire.acquire(inst, args, {}, lambda: None)
            self.assertEqual(inst.reads, 0)


if __name__ == '__main__':
    unittest.main()
