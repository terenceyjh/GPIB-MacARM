"""Validate the real 2400's indefinite IEEE-754 framing without stripping bytes."""
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location('keithley_check', Path(__file__).parents[1] / 'tools/keithley_2400_check.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class BinaryTests(unittest.TestCase):
    def test_both_orders_preserve_nul_cr_and_lf_inside_payload(self):
        # Valid finite float bits contain all three bytes that text I/O strips.
        payload = b'\x3f\x00\x0d\x0a'
        for order, prefix in (('NORM', '>'), ('SWAP', '<')):
            with self.subTest(order=order):
                raw = b'#0' + payload + b'\n'
                self.assertEqual(check.decode_sreal(raw, 1, order), struct.unpack(prefix + 'f', payload))

    def test_short_extra_or_wrong_terminators_are_rejected(self):
        valid = b'#0' + struct.pack('>2f', 1.5, 2.5) + b'\n'
        for raw in (valid[:-1], valid[:-2] + b'\n', valid + b'\n', b'#1' + valid[2:],
                    valid[:-1] + b'\r', valid[:4] + valid[5:]):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                check.decode_sreal(raw, 2, 'NORM')

    def test_count_and_byte_order_must_match_the_known_buffer(self):
        raw = b'#0' + struct.pack('>f', 1.5) + b'\n'
        with self.assertRaises(ValueError):
            check.decode_sreal(raw, 2, 'NORM')
        with self.assertRaises(ValueError):
            check.decode_sreal(raw, 1, 'GUESS')


if __name__ == '__main__':
    unittest.main()
