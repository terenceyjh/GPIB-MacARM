"""No hardware required; verify data integrity and session/transaction behavior."""
import threading
import time
import unittest

from gpib_macarm import (ClosedError, Controller, GpibTimeoutError,
                       MessageTooLongError, ProtocolError, ResourceManager)


class FakeBackend:
    def __init__(self):
        self.events, self.replies, self.opens, self.closes = [], [], 0, 0
        self.latest = b""

    def open(self, *args):
        self.opens += 1
        return object()

    def close(self, handle):
        self.closes += 1

    def timeout(self, handle, usec):
        self.events.append(("timeout", usec))

    def write(self, handle, addr, data, eoi):
        self.events.append(("write", addr, data, eoi))
        self.latest = data
        return len(data)

    def read(self, handle, addr, size, eos):
        self.events.append(("read", addr, size, eos))
        if self.replies:
            response = self.replies.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return self.latest, True

    def clear(self, handle, addr):
        self.events.append(("clear", addr))

    def poll(self, handle, addr):
        return 0x50

    def srq(self, handle):
        return True

    def list_adapters(self):
        return [dict(index=0)]


class APITests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeBackend()
        self.bus = Controller(_backend=self.fake)
        self.inst = self.bus.open_instrument(22)
        self.addCleanup(self.bus.close)

    def test_default_text_terminator_and_eoi(self):
        self.assertEqual(self.inst.write("*IDN?"), 6)
        self.assertEqual(self.fake.events[-1], ("write", 22, b"*IDN?\n", True))
        self.inst.write("*IDN?\n")
        self.assertEqual(self.fake.events[-1][2], b"*IDN?\n")

    def test_none_termination_and_no_eoi(self):
        self.inst.write_termination = None
        self.inst.send_end = False
        self.inst.write("*IDN?")
        self.assertEqual(self.fake.events[-1], ("write", 22, b"*IDN?", False))

    def test_binary_preserves_nul_and_trailing_crlf(self):
        payload = b"\x00\xff\r\n"
        self.fake.replies = [(payload, True)]
        self.assertEqual(self.inst.read_raw(), payload)
        self.assertEqual(self.fake.events[-1][-1], -1)

    def test_long_message_until_end(self):
        self.inst.chunk_size = 1024
        self.fake.replies = [(b"a"*1024,False), (b"b"*1024,False), (b"tail\n",True)]
        self.assertEqual(self.inst.read(), "a"*1024 + "b"*1024 + "tail")

    def test_limit_does_not_silently_truncate(self):
        self.inst.max_read_bytes = 4
        self.fake.replies = [(b"abcd", False)]
        with self.assertRaises(MessageTooLongError):
            self.inst.read_raw()

    def test_zero_progress_is_error(self):
        self.fake.replies = [(b"",False)]
        with self.assertRaises(ProtocolError):
            self.inst.read()

    def test_exact_read_stops_at_eoi(self):
        self.fake.replies = [(b"abc",True)]
        self.assertEqual(self.inst.read_bytes(10), b"abc")

    def test_exact_read_loops_and_can_detect_eos(self):
        self.inst.chunk_size = 2
        self.fake.replies = [(b"ab",False), (b"c\n",True)]
        self.assertEqual(self.inst.read_bytes(4, True), b"abc\n")
        self.assertEqual(self.fake.events[-1][-1], 10)

    def test_raw_write_chunks_and_only_last_eoi(self):
        self.inst.write_raw(b"x"*65536)
        writes = [e for e in self.fake.events if e[0]=="write"]
        self.assertEqual([(len(e[2]),e[3]) for e in writes], [(65535,False),(1,True)])

    def test_raw_write_no_eoi_on_any_chunk(self):
        self.inst.send_end = False
        payload = b'\x00\xff' * 32768
        self.assertEqual(self.inst.write_raw(payload), len(payload))
        writes = [e for e in self.fake.events if e[0] == 'write']
        self.assertEqual([(len(e[2]), e[3]) for e in writes], [(65535, False), (1, False)])
        self.assertEqual(b''.join(e[2] for e in writes), payload)

    def test_missing_intermediate_completion_does_not_send_final_eoi(self):
        original = GpibTimeoutError('write completion missing')
        calls = []
        def no_ack(handle, addr, data, eoi):
            calls.append((addr, data, eoi))
            raise original
        self.fake.write = no_ack
        with self.assertRaises(GpibTimeoutError) as caught:
            self.inst.write_raw(b'x' * 65536)
        self.assertIs(caught.exception, original)
        self.assertEqual([(len(data), eoi) for _, data, eoi in calls], [(65535, False)])
        self.assertTrue(self.bus.faulted)

    def test_partial_write_is_not_retried(self):
        calls = []
        def short(*args):
            calls.append(1)
            return 0
        self.fake.write = short
        with self.assertRaises(ProtocolError):
            self.inst.write("OUTP ON")
        self.assertEqual(len(calls), 1)

    def test_timeout_propagates_no_retry(self):
        self.fake.replies = [GpibTimeoutError("slow")]
        with self.assertRaises(GpibTimeoutError):
            self.inst.query("READ?")
        self.assertEqual(len([e for e in self.fake.events if e[0]=="write"]), 1)
        self.assertTrue(issubclass(GpibTimeoutError, TimeoutError))

    def test_per_instrument_timeout(self):
        other=self.bus.open_instrument(5, timeout=12000)
        other.write("A")
        self.inst.write("B")
        values=[e[1] for e in self.fake.events if e[0]=="timeout"]
        self.assertEqual(values[-2:], [12000000,3000000])

    def test_query_transaction_is_atomic_across_threads(self):
        original=self.fake.write
        def slow(*args):
            result=original(*args)
            time.sleep(0.002)  # yields so an unlocked implementation would interleave
            return result
        self.fake.write=slow
        other=self.bus.open_instrument(5)
        failures=[]
        def worker(inst, text):
            for _ in range(20):
                if inst.query(text) != text:
                    failures.append(text)
        a=threading.Thread(target=worker,args=(self.inst,"ONE"))
        b=threading.Thread(target=worker,args=(other,"TWO"))
        a.start(); b.start(); a.join(); b.join()
        self.assertEqual(failures, [])

    def test_closed_resources_do_not_close_other_resources(self):
        self.inst.close()
        with self.assertRaises(ClosedError):
            self.inst.write("X")
        self.assertFalse(self.bus.closed)
        self.assertEqual(self.bus.open_instrument(5).query("OK"), "OK")

    def test_bus_close_is_idempotent(self):
        self.bus.close(); self.bus.close()
        self.assertEqual(self.fake.closes, 1)
        with self.assertRaises(ClosedError):
            self.inst.read()

    def test_resource_manager_shares_adapter(self):
        with ResourceManager(_backend=self.fake) as rm:
            a=rm.open_resource("GPIB0::22::INSTR")
            b=rm.open_resource("gpib0::5")
            self.assertIs(a.controller, b.controller)
            self.assertEqual(rm.list_resources(), ("GPIB0::INTFC",))
            self.assertEqual(rm.list_resources("*::INSTR"), ())
        with self.assertRaises(ClosedError):
            a.query("X")

    def test_validation(self):
        for address in (-1,31,0,True):
            with self.subTest(address=address), self.assertRaises(ValueError):
                self.bus.open_instrument(address)
        for timeout in (0,None,float("inf"),float("nan"),True,1000001):
            self.inst.timeout=timeout
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.inst.write("X")

    def test_secondary_address_rejected(self):
        with ResourceManager(_backend=self.fake) as rm:
            with self.assertRaises(ValueError):
                rm.open_resource("GPIB0::22::3::INSTR")

    def test_bad_settings_do_not_open_hardware(self):
        before = self.fake.opens
        with ResourceManager(_backend=self.fake) as rm:
            for settings in ({"chunk_size":0}, {"timeout":None}, {"query_delai":1}):
                with self.assertRaises((ValueError,TypeError)):
                    rm.open_resource("GPIB0::22::INSTR", **settings)
        self.assertEqual(self.fake.opens,before)

    def test_instrument_inherits_controller_timeout(self):
        self.bus.timeout = 10000
        inst=self.bus.open_instrument(5)
        self.assertEqual(inst.timeout,10000)

    def test_crlf_removes_only_configured_suffix(self):
        self.inst.read_termination="\r\n"
        self.fake.replies=[(b"  1.2 \r\n",True)]
        self.assertEqual(self.inst.read(), "  1.2 ")

    def test_query_ascii_values(self):
        self.fake.replies=[(b"1.2,3.4\n",True)]
        self.assertEqual(self.inst.query_ascii_values("FETCh?"),[1.2,3.4])


if __name__ == "__main__":
    unittest.main()
