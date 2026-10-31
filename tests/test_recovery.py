"""Recovery must isolate failed data and never silently resume a query."""
import unittest

from gpib_macarm import (ClosedError, Controller, GpibTimeoutError,
                         MessageTooLongError, SessionFaultedError)
from test_api import FakeBackend


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.backend.recover = lambda handle, timeout: self.backend.events.append(('recover', timeout))
        self.backend.poll = lambda *_: 0
        self.bus = Controller(_backend=self.backend)
        self.first = self.bus.open_instrument(8)
        self.other = self.bus.open_instrument(24)
        self.addCleanup(self.bus.close)

    def fail_read(self):
        original = GpibTimeoutError('original timeout')
        self.backend.replies = [original]
        with self.assertRaises(GpibTimeoutError) as caught:
            self.first.query('READ?')
        self.assertIs(caught.exception, original)
        return original

    def test_fault_blocks_all_resources_without_io_and_keeps_cause(self):
        original = self.fail_read()
        before = list(self.backend.events)
        for operation in (lambda: self.first.query('*IDN?'), lambda: self.other.write('ON'),
                          self.other.read_stb, self.first.clear,
                          lambda: self.bus.open_instrument(3)):
            with self.assertRaises(SessionFaultedError) as caught:
                operation()
            self.assertIs(caught.exception.__cause__, original)
        self.assertEqual(self.backend.events, before)
        self.assertTrue(self.bus.faulted)

    def test_explicit_recovery_clears_every_known_queue_before_reuse(self):
        self.fail_read()
        start = len(self.backend.events)
        self.first.recover()
        self.assertFalse(self.bus.faulted)
        self.assertEqual(self.backend.events[start:], [('recover', 20000), ('timeout', 3000000),
                                                       ('clear', 8), ('clear', 24)])
        self.backend.replies = [(b'SR830\n', True)]
        self.assertEqual(self.first.query('*IDN?'), 'SR830')

    def test_recovery_failure_does_not_unlock_adapter(self):
        original = self.fail_read()
        def fail(handle, timeout):
            raise GpibTimeoutError('recovery failed')
        self.backend.recover = fail
        with self.assertRaises(GpibTimeoutError):
            self.bus.recover()
        with self.assertRaises(SessionFaultedError) as caught:
            self.other.query('*IDN?')
        self.assertIs(caught.exception.__cause__, original)

    def test_device_clear_failure_keeps_adapter_faulted(self):
        self.fail_read()
        self.backend.clear = lambda *_: (_ for _ in ()).throw(GpibTimeoutError('SDC failed'))
        with self.assertRaises(GpibTimeoutError):
            self.first.recover()
        self.assertTrue(self.bus.faulted)

    def test_mav_gated_discard_removes_partial_reply_without_queries(self):
        self.fail_read()
        states = iter([0x10, 0, 0])  # addr 8 queued data, then empty; addr 24 empty
        self.backend.poll = lambda *_: next(states)
        self.backend.replies = [(b'0000\n', True)]
        before = len([e for e in self.backend.events if e[0] == 'write'])
        self.first.recover()
        self.assertEqual(self.bus.last_recovery['discarded_bytes'], {8: 5, 24: 0})
        self.assertEqual(len([e for e in self.backend.events if e[0] == 'write']), before)

    def test_bad_mav_discard_keeps_original_fault(self):
        original = self.fail_read()
        self.backend.poll = lambda *_: 0x10
        self.backend.replies = [(b'', False)]
        with self.assertRaisesRegex(Exception, 'no progress'):
            self.first.recover()
        self.assertTrue(self.bus.faulted)
        self.assertIs(self.bus._fault, original)

    def test_known_partial_reply_is_discarded_before_bus_clear(self):
        self.backend.replies = [(b'1', False), (b'0000\n', True)]
        self.assertEqual(self.first.read_bytes(1), b'1')
        start = len(self.backend.events)
        self.first.recover()
        events = self.backend.events[start:]
        self.assertEqual(events[0][0], 'read')
        self.assertEqual(events[1], ('recover', 20000))
        self.assertEqual(self.bus.last_recovery['discarded_bytes'][8], 5)
        self.assertFalse(self.bus._pending_reads)

    def test_pending_reply_blocks_new_writes_but_allows_continuation(self):
        self.backend.replies = [(b'1', False), (b'0000\n', True)]
        self.first.read_bytes(1)
        before = len([e for e in self.backend.events if e[0] == 'write'])
        for operation in (lambda: self.first.query('*IDN?'), lambda: self.other.write('ON'),
                          self.first.read_stb, self.first.clear, self.bus.interface_clear):
            with self.assertRaises(ValueError):
                operation()
        self.assertFalse(self.bus.faulted)
        self.assertEqual(len([e for e in self.backend.events if e[0] == 'write']), before)
        self.assertEqual(self.first.read(), '0000')
        self.assertFalse(self.bus._pending_reads)

    def test_identity_handshake_rejects_prefetched_byte_then_verifies(self):
        identity = b'Maker,SR830,SERIAL,1.0\n'
        self.backend.replies = [(identity, True)]
        self.first.query('*IDN?')
        self.fail_read()
        self.backend.replies = [(b'S'+identity, True), (identity, True)]
        before = len([e for e in self.backend.events if e[0] == 'write'])
        self.first.recover()
        writes = [e for e in self.backend.events if e[0] == 'write'][before:]
        self.assertEqual([e[2] for e in writes], [b'*IDN?\n', b'*IDN?\n'])
        self.assertEqual(self.bus.last_recovery['identity_attempts'], {8: 2})
        self.assertFalse(self.bus.faulted)

    def test_identity_mismatch_keeps_controller_faulted(self):
        self.backend.replies = [(b'Expected\n', True)]
        self.first.query('*IDN?')
        original = self.fail_read()
        self.backend.replies = [(b'Other\n', True), (b'Other\n', True)]
        with self.assertRaisesRegex(Exception, 'identity'):
            self.first.recover()
        self.assertTrue(self.bus.faulted)
        self.assertIs(self.bus._fault, original)

    def test_incomplete_message_faults_shared_controller(self):
        self.first.max_read_bytes = 1
        self.backend.replies = [(b'1', False)]
        with self.assertRaises(MessageTooLongError):
            self.first.read_raw()
        with self.assertRaises(SessionFaultedError):
            self.other.query('FREQ?')

    def test_local_validation_and_logical_close_do_not_fault_bus(self):
        self.first.timeout = 0
        with self.assertRaises(ValueError):
            self.first.read()
        self.assertFalse(self.bus.faulted)
        self.first.timeout = 3000
        self.first.close()
        with self.assertRaises(ClosedError):
            self.first.read()
        self.assertFalse(self.bus.faulted)
        self.assertEqual(self.other.query('OK'), 'OK')

    def test_closed_resources_cannot_recover(self):
        self.first.close()
        before = list(self.backend.events)
        with self.assertRaises(ClosedError):
            self.first.recover()
        self.assertEqual(self.backend.events, before)

    def test_invalid_recovery_wait_does_not_access_backend(self):
        before = list(self.backend.events)
        for timeout in (0, -1, True, 60001, 1.5):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.first.recover(timeout)
        self.assertEqual(self.backend.events, before)

    def test_bus_controls_are_blocked_after_failed_io(self):
        self.fail_read()
        before = list(self.backend.events)
        for call in (self.bus.interface_clear, self.bus.enable_remote, self.bus.check_srq):
            with self.assertRaises(SessionFaultedError):
                call()
        self.assertEqual(self.backend.events, before)

    def test_interrupt_with_pending_reply_faults_bus(self):
        def interrupted(*_):
            raise KeyboardInterrupt()
        self.backend.read = interrupted
        with self.assertRaises(KeyboardInterrupt):
            self.first.query('READ?')
        self.assertTrue(self.bus.faulted)


if __name__ == '__main__':
    unittest.main()
