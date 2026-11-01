"""Small, explicitly scoped VISA-like API for sequential SCPI communication.

Design: retain the KAME/libusb transport, bind through ctypes and serialize a
whole query on one shared controller. No Qt, NI-VISA, pyvisa or background server.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import fnmatch
import codecs
import math
import re
import threading
import time
import weakref

from ._backend import NativeBackend
from .errors import (ClosedError, GpibError, MessageTooLongError, ProtocolError,
                     SessionFaultedError)


def _integer(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def _timeout(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= value <= 1_000_000:
        raise ValueError("timeout must be finite milliseconds in 1..1000000")
    return int(math.ceil(value * 1000))


def _term(value):
    if value is not None and value not in ("", "\r", "\n", "\r\n"):
        raise ValueError("termination must be None, '', '\\r', '\\n', or '\\r\\n'")
    return value


def _settings(settings):
    allowed = {"timeout", "write_termination", "read_termination", "encoding", "query_delay",
               "chunk_size", "max_read_bytes", "send_end"}
    unknown = settings.keys() - allowed
    if unknown:
        raise TypeError("Unknown instrument settings: " + ", ".join(sorted(unknown)))
    if "timeout" in settings:
        _timeout(settings["timeout"])
    for key in ("write_termination", "read_termination"):
        if key in settings:
            _term(settings[key])
    if "chunk_size" in settings:
        _integer(settings["chunk_size"], "chunk_size", 1, 65535)
    if "max_read_bytes" in settings:
        _integer(settings["max_read_bytes"], "max_read_bytes", 1, 2**31 - 1)
    if "encoding" in settings:
        codecs.lookup(settings["encoding"])
    if "send_end" in settings and not isinstance(settings["send_end"], bool):
        raise ValueError("send_end must be bool")
    delay = settings.get("query_delay", 0)
    if isinstance(delay, bool) or not isinstance(delay, (int,float)) or not math.isfinite(delay) or delay < 0:
        raise ValueError("query_delay must be finite nonnegative seconds")


@dataclass(frozen=True)
class AdapterInfo:
    index: int
    model: str
    vendor_id: int
    product_id: int
    bus: int
    address: int
    serial: str | None
    accessible: bool


def list_adapters():
    """Enumerate USB adapters; does not scan GPIB addresses or reset the bus."""
    return [AdapterInfo(**item) for item in NativeBackend().list_adapters()]


class Controller:
    """One physical adapter. Opening initializes it, asserts REN and pulses IFC.

    Share this object for every instrument on one adapter. `timeout` is in ms.
    Serial selection is more stable than an enumeration index after replugging.
    """
    def __init__(self, index=0, *, serial=None, board_pad=0, timeout=3000, _backend=None):
        self.index = _integer(index, "index", 0, 127)
        self.board_pad = _integer(board_pad, "board_pad", 0, 30)
        if serial is not None and (not isinstance(serial, str) or not serial or "\0" in serial):
            raise ValueError("serial must be a nonempty ASCII string")
        if serial is not None:
            serial.encode("ascii")
        self.serial, self.timeout = serial, timeout
        timeout_us = _timeout(timeout)
        self._lock = threading.RLock()
        self._fault = None
        self._addresses = set()
        self._pending_reads = set()
        self._identities = {}
        self._backend = _backend if _backend is not None else NativeBackend()
        self._handle = self._backend.open(self.index, self.board_pad, timeout_us, serial)
        self._finalizer = weakref.finalize(self, self._backend.close, self._handle)

    @property
    def closed(self):
        return self._handle is None

    @property
    def faulted(self):
        return self._fault is not None

    def _check_fault(self):
        if self._fault is not None:
            raise SessionFaultedError(
                "Earlier adapter I/O failed; stop acquisition and call recover() explicitly. "
                "No command was sent. Original error: " + str(self._fault)) from self._fault

    @contextmanager
    def transaction(self, *, timeout=None):
        """Hold the adapter lock across multiple operations on its resources."""
        with self._lock:
            if self.closed:
                raise ClosedError("Controller is closed")
            self._check_fault()
            try:
                self._backend.timeout(self._handle, _timeout(self.timeout if timeout is None else timeout))
                yield
            except (ClosedError, SessionFaultedError):
                raise
            except (GpibError, KeyboardInterrupt) as exc:
                if self._fault is None:
                    self._fault = exc
                raise

    def open_instrument(self, address, **settings):
        with self._lock:
            if self.closed:
                raise ClosedError("Controller is closed")
            self._check_fault()
            _settings(settings)
            return Instrument(self, address, **settings)

    def recover(self, timeout=20000, mav_mask=0x10):
        """Wait for cancelled/late adapter completions, IFC, then known-address SDC.

        Discards pending replies and can affect instrument operations through
        device clear. Does not replay arbitrary failed commands or confirm output off.
        Previously cached identities get at most two read-only *IDN? checks. Recheck
        identity/settings before starting a NEW acquisition; failed data stays
        failed. Recovery failure keeps the shared controller faulted.

        timeout (ms) bounds the first late-completion receive, not the whole
        cleanup. Default MAV bit 4 assumes IEEE-488.2 status; override the mask
        for another instrument, or use 0 only when its queue-clear behavior is
        independently known. Discard is limited to 16 messages / 1 MiB per address.
        """
        _integer(timeout, 'recovery timeout', 1, 60000)
        _integer(mav_mask, 'MAV mask', 0, 255)
        with self._lock:
            if self.closed:
                raise ClosedError("Controller is closed")
            try:
                discarded = {address: 0 for address in self._addresses}
                # A successful count-limited read can leave a known reply in
                # progress. Finish it BEFORE IFC/SDC, which may otherwise leave
                # the talker's prefetched byte invisible to its MAV status.
                if self._fault is None:
                    for address in sorted(self._pending_reads):
                        while True:
                            data, end = self._backend.read(self._handle, address, 4096, -1)
                            discarded[address] += len(data)
                            if discarded[address] > 1024*1024:
                                raise MessageTooLongError('Pending recovery reply exceeded 1 MiB')
                            if not data and not end:
                                raise ProtocolError('Pending recovery reply made no progress')
                            if end:
                                break
                self._backend.recover(self._handle, timeout)
                self._backend.timeout(self._handle, _timeout(self.timeout))
                for address in sorted(self._addresses):
                    self._backend.clear(self._handle, address)
                    if not mav_mask:
                        continue
                    for message in range(17):
                        if not self._backend.poll(self._handle, address) & mav_mask:
                            break
                        if message == 16:
                            raise ProtocolError('Instrument MAV remained set after 16 discarded messages')
                        # Read only when IEEE-488.2 MAV reports queued data.
                        # SR830 SDC does not discard a partially read reply.
                        while True:
                            data, end = self._backend.read(self._handle, address, 4096, -1)
                            discarded[address] += len(data)
                            if discarded[address] > 1024*1024:
                                raise MessageTooLongError('Recovery discard exceeded 1 MiB')
                            if not data and not end:
                                raise ProtocolError('Recovery read made no progress despite MAV')
                            if end:
                                break
                identity_attempts = {}
                for address, known in sorted(self._identities.items()):
                    expected, write_term, read_term, encoding = known
                    for attempt in range(2):
                        payload = ('*IDN?' + (write_term or '')).encode(encoding)
                        if self._backend.write(self._handle, address, payload, True) != len(payload):
                            raise ProtocolError('Short identity verification write during recovery')
                        pieces = []
                        size = 0
                        eos = read_term.encode('ascii')[-1] if read_term else -1
                        while True:
                            data, end = self._backend.read(self._handle, address, 4096, eos)
                            pieces.append(data)
                            size += len(data)
                            if size > 65536 or (not data and not end):
                                raise ProtocolError('Invalid recovery identity response')
                            if end:
                                break
                        reply = b''.join(pieces).decode(encoding)
                        if read_term and reply.endswith(read_term):
                            reply = reply[:-len(read_term)]
                        identity_attempts[address] = attempt + 1
                        if reply == expected:
                            break
                        discarded[address] += size
                        if discarded[address] > 1024*1024:
                            raise MessageTooLongError('Recovery discard exceeded 1 MiB')
                    else:
                        raise ProtocolError('Recovery identity does not match the known instrument')
            except BaseException as exc:
                if self._fault is None:
                    self._fault = exc
                raise
            self._fault = None
            self._pending_reads.clear()
            self.last_recovery = {'discarded_bytes': discarded, 'mav_mask': mav_mask,
                                  'first_completion_wait_ms': timeout,
                                  'identity_attempts': identity_attempts}

    def interface_clear(self):
        """Pulse IFC for the entire bus; does not reset instrument settings via *RST."""
        with self.transaction():
            if self._pending_reads:
                raise ValueError('Finish the pending reply or call recover() before interface clear')
            self._backend.interface_clear(self._handle)

    def enable_remote(self, enabled=True):
        with self.transaction():
            if self._pending_reads:
                raise ValueError('Finish the pending reply or call recover() before changing REN')
            self._backend.remote(self._handle, bool(enabled))

    def check_srq(self):
        with self.transaction():
            return self._backend.srq(self._handle)

    def close(self):
        with self._lock:
            if not self.closed:
                self._handle = None
                self._finalizer()

    def __enter__(self):
        if self.closed:
            raise ClosedError("Controller is closed")
        return self

    def __exit__(self, *exc):
        self.close()


class Instrument:
    """Logical GPIB resource, borrowing its Controller. close() does not close the bus.

    Text writes append LF by default and assert EOI. Text reads detect LF or EOI.
    Raw reads ignore text EOS, preserve all bytes and require EOI to finish.
    """
    def __init__(self, controller, address, *, timeout=None, write_termination="\n",
                 read_termination="\n", encoding="ascii", query_delay=0,
                 chunk_size=4096, max_read_bytes=1024 * 1024, send_end=True):
        self.controller = controller
        timeout = controller.timeout if timeout is None else timeout
        self.address = _integer(address, "address", 0, 30)
        if self.address == controller.board_pad:
            raise ValueError("Instrument and controller addresses must differ")
        _timeout(timeout)
        _term(write_termination); _term(read_termination)
        self.timeout, self.write_termination, self.read_termination = timeout, write_termination, read_termination
        self.encoding, self.query_delay = encoding, query_delay
        self.chunk_size, self.max_read_bytes, self.send_end = chunk_size, max_read_bytes, send_end
        self._closed = False
        self.resource_name = f"GPIB{controller.index}::{self.address}::INSTR"
        with controller._lock:
            controller._addresses.add(self.address)

    @property
    def closed(self):
        return self._closed or self.controller.closed

    @contextmanager
    def _operation(self):
        _timeout(self.timeout)
        with self.controller.transaction(timeout=self.timeout):
            if self._closed:
                raise ClosedError("Instrument resource is closed")
            yield

    def _write(self, payload):
        if self.controller._pending_reads:
            raise ValueError('An earlier reply is not fully read; finish it or call recover() before writing. No command was sent.')
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise TypeError("write_raw expects bytes-like data")
        payload = bytes(payload)
        if not payload:
            raise ValueError("Cannot write an empty GPIB message")
        # Retain one adapter lock across every chunk. EOI is only on the final one.
        total = 0
        for start in range(0, len(payload), 65535):
            chunk = payload[start:start + 65535]
            final = start + len(chunk) == len(payload)
            written = self.controller._backend.write(self.controller._handle, self.address, chunk,
                                                     bool(self.send_end and final))
            if written != len(chunk):
                raise ProtocolError("Short write; command may have partially executed")
            total += written
        return total

    def write_raw(self, payload):
        with self._operation():
            return self._write(payload)

    def write(self, message, termination=None, encoding=None):
        if not isinstance(message, str):
            raise TypeError("write expects str; use write_raw for bytes")
        term = _term(self.write_termination if termination is None else termination)
        if term and not message.endswith(term):
            message += term
        payload = message.encode(encoding or self.encoding)
        with self._operation():
            return self._write(payload)

    def _check_read_address(self):
        if self.controller._pending_reads - {self.address}:
            raise ValueError('Another instrument has an unfinished reply; finish it or call recover() before reading this address')

    def _read_message(self, text_termination):
        self._check_read_address()
        chunk_size = _integer(self.chunk_size, "chunk_size", 1, 65535)
        limit = _integer(self.max_read_bytes, "max_read_bytes", 1, 2**31 - 1)
        term = _term(self.read_termination) if text_termination else None
        eos = term.encode("ascii")[-1] if term else -1
        pieces, total = [], 0
        while total < limit:
            data, end = self.controller._backend.read(self.controller._handle, self.address,
                                                      min(chunk_size, limit - total), eos)
            if end:
                self.controller._pending_reads.discard(self.address)
            else:
                self.controller._pending_reads.add(self.address)
            if not data and not end:
                raise ProtocolError("Read returned zero bytes without END; clear or reopen the session")
            pieces.append(data); total += len(data)
            if end:
                return b"".join(pieces)
        raise MessageTooLongError(f"Reply exceeded max_read_bytes={limit} before END/EOS; response was not silently truncated")

    def read_raw(self):
        with self._operation():
            return self._read_message(False)

    def read_bytes(self, count, break_on_termchar=False):
        count = _integer(count, "count", 1, 2**31 - 1)
        chunk_size = _integer(self.chunk_size, "chunk_size", 1, 65535)
        with self._operation():
            self._check_read_address()
            term = _term(self.read_termination) if break_on_termchar else None
            eos = term.encode("ascii")[-1] if term else -1
            parts, total = [], 0
            while total < count:
                data, end = self.controller._backend.read(self.controller._handle, self.address,
                                                          min(chunk_size, count-total), eos)
                if end:
                    self.controller._pending_reads.discard(self.address)
                else:
                    self.controller._pending_reads.add(self.address)
                if not data and not end:
                    raise ProtocolError("Read returned zero bytes without END")
                parts.append(data); total += len(data)
                if end:
                    break
            return b"".join(parts)

    def read(self, encoding=None):
        with self._operation():
            result = self._read_message(True).decode(encoding or self.encoding)
            term = _term(self.read_termination)
            return result[:-len(term)] if term and result.endswith(term) else result

    def query(self, message, delay=None):
        wait = self.query_delay if delay is None else delay
        if isinstance(wait, bool) or not isinstance(wait, (int, float)) or not math.isfinite(wait) or wait < 0:
            raise ValueError("query delay must be finite, nonnegative seconds")
        # The outer lock prevents a different instrument/thread from consuming
        # this response between the write and read. Nested operations use RLock.
        with self._operation():
            self.write(message)
            if wait:
                time.sleep(wait)
            reply = self.read()
            if message.strip().upper() == '*IDN?' and reply:
                self.controller._identities.setdefault(self.address,
                    (reply, self.write_termination, self.read_termination, self.encoding))
            return reply

    def query_ascii_values(self, message, converter=float, separator=","):
        result = self.query(message)
        return [converter(item) for item in result.split(separator)] if result else []

    def read_stb(self):
        with self._operation():
            if self.controller._pending_reads:
                raise ValueError('Finish the pending reply or call recover() before serial polling')
            return self.controller._backend.poll(self.controller._handle, self.address)

    @property
    def stb(self):
        return self.read_stb()

    def clear(self):
        """Selected device clear (SDC); not SCPI *CLS or *RST."""
        with self._operation():
            if self.controller._pending_reads:
                raise ValueError('Finish the pending reply or call recover() instead of clearing it mid-message')
            self.controller._backend.clear(self.controller._handle, self.address)

    def recover(self, timeout=20000, mav_mask=0x10):
        """Recover the shared adapter and clear all its known instrument queues."""
        with self.controller._lock:
            if self.closed:
                raise ClosedError("Instrument resource is closed")
            self.controller.recover(timeout, mav_mask)

    def close(self):
        with self.controller._lock:
            self._closed = True

    def __enter__(self):
        if self.closed:
            raise ClosedError("Instrument resource is closed")
        return self

    def __exit__(self, *exc):
        self.close()


class ResourceManager:
    """Small VISA-like facade; no pyvisa backend or automatic instrument scanning.

    list_resources lists adapter INTFC names only. Open instrument addresses known
    from their front panel/manual, e.g. GPIB0::22::INSTR. Closing this manager closes
    its shared adapters and invalidates every instrument borrowed from them.
    """
    def __init__(self, *, board_pad=0, _backend=None):
        self.board_pad = _integer(board_pad, "board_pad", 0, 30)
        self._backend = _backend
        self._controllers = {}
        self._lock, self._closed = threading.RLock(), False

    def _check(self):
        if self._closed:
            raise ClosedError("ResourceManager is closed")

    def list_resources(self, query="?*"):
        with self._lock:
            self._check()
            backend = self._backend if self._backend is not None else NativeBackend()
            return tuple(f"GPIB{a['index']}::INTFC" for a in backend.list_adapters()
                         if fnmatch.fnmatchcase(f"GPIB{a['index']}::INTFC", query))

    def open_resource(self, resource_name, *, serial=None, **settings):
        _settings(settings)  # validate before opening/resetting a physical adapter
        match = re.fullmatch(r"GPIB(\d+)::(\d+)(?:::INSTR)?", resource_name, flags=re.I)
        if not match:
            raise ValueError("Expected GPIB<adapter index>::<primary address>::INSTR; secondary addresses are unsupported")
        index, addr = map(int, match.groups())
        _integer(index, "index", 0, 127); _integer(addr, "address", 0, 30)
        if addr == self.board_pad:
            raise ValueError("Instrument and controller addresses must differ")
        with self._lock:
            self._check()
            key = (index, serial)
            if key not in self._controllers or self._controllers[key].closed:
                self._controllers[key] = Controller(index, serial=serial, board_pad=self.board_pad,
                    timeout=settings.get("timeout", 3000), _backend=self._backend)
            return self._controllers[key].open_instrument(addr, **settings)

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                for controller in self._controllers.values():
                    controller.close()
                self._controllers.clear()

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *exc):
        self.close()
