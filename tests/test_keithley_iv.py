"""Measurement validity and shutdown checks without opening hardware."""
import unittest

from tools.keithley_2400_iv import BAD_STATUS, FOUR_WIRE, REQUIRED_STATUS, fit_rows, parse_sweep, safe_shutdown


class FourWireSweepTests(unittest.TestCase):
    def reply(self, status=FOUR_WIRE | (1 << 15) | (1 << 11) | 4):
        return ",".join(str(v) for n, current in enumerate((-.001, 0, .001))
                        for v in (current * 2 + 3e-6, current, n * .2, status))

    def test_fit_removes_constant_thermoelectric_offset(self):
        rows = parse_sweep(self.reply(), -.001, .001, 3, .1)
        fit = fit_rows(rows)
        self.assertAlmostEqual(fit["resistance_ohm"], 2)
        self.assertAlmostEqual(fit["offset_v"], 3e-6)
        self.assertAlmostEqual(fit["r_squared"], 1)

    def test_invalid_status_cannot_be_reported_as_good_data(self):
        for bit in (1 << n for n in range(24) if BAD_STATUS & (1 << n)):
            with self.subTest(bit=bit), self.assertRaises(ValueError):
                parse_sweep(self.reply(REQUIRED_STATUS | bit), -.001, .001, 3, .1)
        for status in (0, FOUR_WIRE, REQUIRED_STATUS & ~(1 << 11), REQUIRED_STATUS & ~(1 << 15)):
            with self.subTest(status=status), self.assertRaises(ValueError):
                parse_sweep(self.reply(status), -.001, .001, 3, .1)

    def test_short_or_wrong_current_reply_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_sweep(self.reply().rsplit(",", 1)[0], -.001, .001, 3, .1)
        with self.assertRaises(ValueError):
            parse_sweep(self.reply(), -.01, .01, 3, .1)

    def test_overflow_and_compliance_proximity_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_sweep(self.reply().replace("-0.001997", "9.91e37"), -.001, .001, 3, .1)
        with self.assertRaises(ValueError):
            parse_sweep(self.reply(), -.001, .001, 3, .002)

    def test_failed_shutdown_requires_manual_output_check(self):
        class UnresponsiveMeter:
            def write(self, command):
                raise TimeoutError("lost connection")

            def query(self, command):
                raise TimeoutError("lost connection")

        result = safe_shutdown(UnresponsiveMeter())
        self.assertTrue(result["manual_output_off_required"])
        self.assertFalse(result["output_off_confirmed"])
        self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main()
