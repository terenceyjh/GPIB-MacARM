"""Native parser and ABI checks. Skip when a native library is not built."""
import ctypes as ct
from pathlib import Path
import sys
import unittest

from gpib_macarm import ClosedError, DeviceNotFoundError
from gpib_macarm._backend import NativeBackend
from gpib_macarm import _backend

ROOT = Path(__file__).resolve().parents[1]
SUFFIX = ".dylib" if sys.platform == "darwin" else ".so"
READY = sys.platform in ("darwin", "linux") and Path(_backend.__file__).with_name("_driver" + SUFFIX).is_file()


@unittest.skipUnless(READY, "Build the native library first (macOS/Linux)")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = NativeBackend()
        cls.parse = cls.backend.lib.parse_board_ibrd_readback
        cls.parse.argtypes = [ct.c_void_p, ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_int, ct.POINTER(ct.c_int)]
        cls.parse.restype = ct.c_int

    def frame(self, payload=b"123.45", extended=False, register_status=True, capacity=256):
        size = 30 if extended else 15
        blocks = b"".join((b"\x37\x00" if extended else b"\x36") + payload[i:i+size].ljust(size,b"\0")
                          for i in range(0, len(payload), size))
        last = (len(payload) - 1) % size + 1 if payload else 0
        registers = bytes([9,0,0,0,0,0,0,0,2,0,0,0]) if register_status else b""
        residual = (len(payload) - capacity) & 0xffff
        return bytearray(blocks
            + bytes([0x38,0,0,0,residual & 255,residual >> 8,0,0]) + bytes([0,last,0,0])
            + registers + bytes([4,0,0,0]))

    def decode(self, frame, capacity=256):
        incoming = ct.create_string_buffer(bytes(frame))
        status, data, actual = ct.create_string_buffer(64), ct.create_string_buffer(256), ct.c_int()
        result = self.parse(incoming,len(frame),status,data,capacity,ct.byref(actual))
        return result, data.raw[:actual.value]

    def test_normal_short_and_extended_packets(self):
        for extended in (False,True):
            frame=self.frame(extended=extended)
            result,data=self.decode(frame)
            self.assertEqual(result,len(frame))
            self.assertEqual(data,b"123.45")

    def test_hardware_compact_trailer(self):
        # The connected HS returns IBRD status/ADR1/count/TERM without the
        # optional register-write acknowledgement. Exercise several data blocks.
        for payload in (b"", b"123.45", b"K" * 80):
            for extended in (False, True):
                with self.subTest(length=len(payload), extended=extended):
                    frame = self.frame(payload, extended, register_status=False)
                    result, data = self.decode(frame)
                    self.assertEqual(result, len(frame))
                    self.assertEqual(data, payload)

    def test_every_truncation_is_rejected(self):
        for registers in (False, True):
            frame=self.frame(register_status=registers)
            for length in range(len(frame)):
                with self.subTest(length=length, registers=registers):
                    self.assertLess(self.decode(frame[:length])[0],0)

    def test_compact_trailer_rejects_bad_count_padding_and_termination(self):
        for index, value in ((16, 0xff), (20, 0xff), (26, 1), (28, 9), (31, 1)):
            frame = self.frame(register_status=False)
            frame[index] = value
            self.assertLess(self.decode(frame)[0], 0)
        frame = self.frame(register_status=False)
        self.assertLess(self.decode(frame + b"\0")[0], 0)

    def test_hardware_count_limited_short_block(self):
        # Observed HS compact frames have an unreliable last-block count for
        # reads of 2..15 bytes that fill the request. The status
        # residual is zero and provides the trustworthy count in this case.
        for size, last in ((2, 0xe4), (3, 0xc7), (4, 0xaa), (7, 0x53),
                           (8, 0x36), (14, 0x88), (15, 0x6b)):
            payload = b"123456789abcdef"[:size]
            frame = self.frame(payload, register_status=False, capacity=size)
            frame[25] = last
            result, data = self.decode(frame, capacity=size)
            self.assertEqual(result, len(frame))
            self.assertEqual(data, payload)
            frame[17] = 0x20  # END can coincide with a count-limited read.
            self.assertEqual(self.decode(frame, capacity=size)[1], payload)
            # Reject a residual exceeding the request, or a byte count that
            # does not fit the received data blocks.
            frame[20:22] = b"\xff\xfe"
            self.assertLess(self.decode(frame, capacity=size)[0], 0)

    def test_compact_residual_must_match_data_blocks(self):
        frame = self.frame(b"K" * 80, extended=True, register_status=False)
        self.assertLess(self.decode(frame, capacity=256-80)[0], 0)  # zero data vs three blocks
        self.assertLess(self.decode(frame, capacity=256+11)[0], 0)  # 91 bytes vs 90 available
        empty = self.frame(b"", register_status=False)
        self.assertLess(self.decode(empty, capacity=257)[0], 0)  # data claimed without a block

    def test_invalid_status_or_register_error(self):
        for index,value in ((16,0xff),(31,10),(36,3),(40,0xff),(25,16)):
            frame=self.frame(); frame[index]=value
            self.assertLess(self.decode(frame)[0],0)

    def test_null_controller_raises_closed(self):
        with self.assertRaises(ClosedError):
            self.backend.timeout(None,3000000)

    def test_null_recovery_raises_closed(self):
        with self.assertRaises(ClosedError):
            self.backend.recover(None)

    def test_missing_index_does_not_initialize_real_hardware(self):
        # Enumeration only: an impossibly large index never opens a USB handle.
        with self.assertRaises(DeviceNotFoundError):
            self.backend.open(1000000,0,3000000,None)

    def test_invalid_open_parameters(self):
        with self.assertRaises(ValueError):
            self.backend.open(0,31,3000000,None)


if __name__ == "__main__":
    unittest.main()
