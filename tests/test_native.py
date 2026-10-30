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

    def frame(self, payload=b"123.45", extended=False):
        size = 30 if extended else 15
        return bytearray((b"\x37\x00" if extended else b"\x36") + payload.ljust(size,b"\0")
            + bytes([0x38,0,0,0,0,0,0,0]) + bytes([0,len(payload),0,0])
            + bytes([9,0,0,0,0,0,0,0]) + bytes([2,0,0,0,4,0,0,0]))

    def decode(self, frame):
        incoming = ct.create_string_buffer(bytes(frame))
        status, data, actual = ct.create_string_buffer(64), ct.create_string_buffer(256), ct.c_int()
        result = self.parse(incoming,len(frame),status,data,256,ct.byref(actual))
        return result, data.raw[:actual.value]

    def test_normal_short_and_extended_packets(self):
        for extended in (False,True):
            frame=self.frame(extended=extended)
            result,data=self.decode(frame)
            self.assertEqual(result,len(frame))
            self.assertEqual(data,b"123.45")

    def test_every_truncation_is_rejected(self):
        frame=self.frame()
        for length in range(len(frame)):
            with self.subTest(length=length):
                self.assertLess(self.decode(frame[:length])[0],0)

    def test_invalid_status_or_register_error(self):
        for index,value in ((16,0xff),(31,10),(36,3),(40,0xff),(25,16)):
            frame=self.frame(); frame[index]=value
            self.assertLess(self.decode(frame)[0],0)

    def test_null_controller_raises_closed(self):
        with self.assertRaises(ClosedError):
            self.backend.timeout(None,3000000)

    def test_missing_index_does_not_initialize_real_hardware(self):
        # Enumeration only: an impossibly large index never opens a USB handle.
        with self.assertRaises(DeviceNotFoundError):
            self.backend.open(1000000,0,3000000,None)

    def test_invalid_open_parameters(self):
        with self.assertRaises(ValueError):
            self.backend.open(0,31,3000000,None)


if __name__ == "__main__":
    unittest.main()
