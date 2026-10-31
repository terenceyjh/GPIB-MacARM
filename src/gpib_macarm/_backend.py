"""ctypes boundary. CDLL releases the GIL during synchronous native calls."""
import ctypes as ct
import json
import os
from pathlib import Path
import sys

from .errors import (ClosedError, DeviceNotFoundError, GpibError,
                     GpibTimeoutError, ProtocolError, ResourceBusyError)


class NativeBackend:
    def __init__(self):
        suffix = ".dylib" if sys.platform == "darwin" else ".so"
        self.path = Path(os.environ.get("GPIB_MACARM_LIBRARY", Path(__file__).with_name("_driver" + suffix)))
        try:
            self.lib = ct.CDLL(str(self.path.resolve()))
        except OSError as exc:
            raise GpibError(f"Cannot load {self.path}: {exc}. Install libusb and rebuild with "
                            "python -m pip install --no-cache-dir .; Python and libusb must have the same architecture.") from exc
        lib = self.lib
        ptr, size, integer, uint = ct.c_void_p, ct.c_size_t, ct.c_int, ct.c_uint
        self._declare("kg_version", [], ct.c_char_p)
        self._declare("kg_last_error", [], ct.c_char_p)
        self._declare("kg_open", [integer, integer, uint, ct.c_char_p, ct.POINTER(ptr)])
        self._declare("kg_close", [ptr], None)
        self._declare("kg_timeout", [ptr, uint])
        self._declare("kg_list", [ct.POINTER(ct.c_char_p)])
        self._declare("kg_write", [ptr, integer, ptr, size, integer, ct.POINTER(size)])
        self._declare("kg_read", [ptr, integer, ptr, size, integer, ct.POINTER(size), ct.POINTER(integer)])
        self._declare("kg_clear", [ptr, integer])
        self._declare("kg_ifc", [ptr])
        self._declare("kg_recover", [ptr, uint])
        self._declare("kg_remote", [ptr, integer])
        self._declare("kg_poll", [ptr, integer, ct.POINTER(integer)])
        self._declare("kg_srq", [ptr, ct.POINTER(integer)])
        if lib.kg_version() != b"0.1.0":
            raise GpibError("Native/Python driver versions do not match. Rebuild and reinstall.")

    def _declare(self, name, args, result=ct.c_int):
        try:
            fn = getattr(self.lib, name)
        except AttributeError as exc:
            raise GpibError("Native driver is older than the Python API. Rebuild with "
                            "python -m pip install --no-cache-dir --force-reinstall --no-deps -e .") from exc
        fn.argtypes, fn.restype = args, result

    def _check(self, code):
        if code:
            message = (self.lib.kg_last_error() or b"Native GPIB failure").decode("utf-8", "replace")
            cls = {2: GpibTimeoutError, 3: DeviceNotFoundError, 4: ResourceBusyError,
                   5: ProtocolError, 6: ClosedError, 7: ValueError}.get(code, GpibError)
            exc = cls(message)
            exc.status_code = code
            raise exc

    def list_adapters(self):
        result = ct.c_char_p()
        self._check(self.lib.kg_list(ct.byref(result)))
        return json.loads(result.value.decode("utf-8"))

    def open(self, index, board_pad, timeout_us, serial):
        handle = ct.c_void_p()
        self._check(self.lib.kg_open(index, board_pad, timeout_us,
                                   serial.encode("ascii") if serial else None, ct.byref(handle)))
        if not handle.value:
            raise ProtocolError("Native open returned no handle.")
        return handle

    def close(self, handle):
        self.lib.kg_close(handle)

    def timeout(self, handle, usec):
        self._check(self.lib.kg_timeout(handle, usec))

    def write(self, handle, addr, payload, eoi):
        data = ct.create_string_buffer(payload, len(payload))
        count = ct.c_size_t()
        self._check(self.lib.kg_write(handle, addr, data, len(payload), eoi, ct.byref(count)))
        return count.value

    def read(self, handle, addr, size, eos):
        data = ct.create_string_buffer(size)
        count, end = ct.c_size_t(), ct.c_int()
        self._check(self.lib.kg_read(handle, addr, data, size, eos, ct.byref(count), ct.byref(end)))
        if count.value > size:
            raise ProtocolError("Native read exceeded the supplied buffer.")
        return data.raw[:count.value], bool(end.value)

    def clear(self, handle, addr):
        self._check(self.lib.kg_clear(handle, addr))

    def interface_clear(self, handle):
        self._check(self.lib.kg_ifc(handle))

    def recover(self, handle, timeout_ms=20000):
        self._check(self.lib.kg_recover(handle, timeout_ms))

    def remote(self, handle, enabled):
        self._check(self.lib.kg_remote(handle, enabled))

    def poll(self, handle, addr):
        stb = ct.c_int()
        self._check(self.lib.kg_poll(handle, addr, ct.byref(stb)))
        return stb.value

    def srq(self, handle):
        value = ct.c_int()
        self._check(self.lib.kg_srq(handle, ct.byref(value)))
        return bool(value.value)
