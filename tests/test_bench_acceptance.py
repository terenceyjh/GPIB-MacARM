"""Exercise physical-test coordination without a device or human interaction."""
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import gpib_macarm as gpib

ROOT = Path(__file__).parents[1]


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench_tool = load_tool('bench_acceptance')
check_tool = load_tool('keithley_2400_check')
bus_tool = load_tool('bus_smoke')


class Clock:
    value = 0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class BenchBackend:
    def __init__(self):
        self.connected, self.powered, self.generation, self.index = True, True, 0, 0
        self.serial = 'TEST-ADAPTER'
        self.identities = {24: 'KEITHLEY,MODEL 2400,TEST,1.0', 8: 'SRS,SR830,TEST,1.0'}
        self.settings = {q: '0' for q in bench_tool.SETTINGS}
        self.settings[':SOUR:FUNC?'] = 'VOLT'
        self.pending, self.events, self.handles = {}, [], []
        self.output, self.no_eoi_ack, self.short_large_write = '0', True, False
        self.trace_points, self.fail_trace_read = 0, False

    def list_adapters(self):
        return ([dict(index=self.index, serial=self.serial, accessible=True, product_id=0x709b)]
                if self.connected else [])

    def open(self, index, pad, timeout, serial):
        if not self.connected or index != self.index or serial != self.serial:
            raise gpib.DeviceNotFoundError('Wrong or absent adapter')
        self.handles.append(self.generation)
        return self.generation

    def close(self, handle):
        self.events.append(('close', handle))

    def timeout(self, handle, usec):
        pass  # The real native timeout setter does not access USB.

    def check_handle(self, handle):
        if not self.connected or handle != self.generation:
            raise gpib.DeviceNotFoundError('Adapter was removed')

    def write(self, handle, addr, data, eoi):
        self.events.append(('write', handle, addr, data, eoi))
        self.check_handle(handle)
        if addr == 24 and not self.powered:
            raise gpib.GpibTimeoutError('Instrument is powered off')
        if self.short_large_write and len(data) >= 65535:
            return len(data) - 1
        query = data.decode('ascii').splitlines()[-1]
        if query == '*IDN?':
            self.pending[addr] = (self.identities[addr] + '\n').encode()
        elif query == ':OUTP?':
            self.pending[addr] = (self.output + '\n').encode()
        elif query == ':SYST:ERR?':
            self.pending[addr] = b'0,"No error"\n'
        elif query == ':TRAC:POIN:ACT?':
            self.pending[addr] = f'{self.trace_points}\n'.encode()
        elif query == ':TRAC:DATA?':
            self.pending[addr] = b'1,2,3,4\n'
        elif query.startswith(':FORM:DATA '):
            self.settings[':FORM:DATA?'] = query.split()[-1]
        elif query in self.settings:
            self.pending[addr] = (self.settings[query] + '\n').encode()
        elif query == 'NUM?':
            self.pending[addr] = f'{addr},1.5\n'.encode()
        elif query != '*WAI':
            raise AssertionError('Unexpected instrument command: ' + query)
        if not eoi and not self.no_eoi_ack:
            raise gpib.GpibTimeoutError('Write reached device but has no completion')
        return len(data)

    def read(self, handle, addr, size, eos):
        self.events.append(('read', handle, addr))
        self.check_handle(handle)
        if self.fail_trace_read and self.pending.get(addr) == b'1,2,3,4\n':
            raise gpib.GpibTimeoutError('Buffer backup failed')
        data = self.pending.pop(addr, b'')
        if not data:
            raise gpib.GpibTimeoutError('No pending reply')
        if len(data) > size:
            self.pending[addr] = data[size:]
        return data[:size], len(data) <= size

    def recover(self, handle, timeout):
        self.events.append(('recover', handle))
        self.check_handle(handle)
        if not self.powered:
            raise gpib.GpibTimeoutError('Instrument still off')
        self.pending.clear()

    def clear(self, handle, addr):
        self.check_handle(handle)
        self.pending.pop(addr, None)

    def poll(self, handle, addr):
        self.check_handle(handle)
        return 0


class BenchTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.backend, self.clock, self.steps = BenchBackend(), Clock(), []
        self.journal = bench_tool.Journal(Path(self.folder.name) / 'run', {})
        self.bench = bench_tool.PhysicalBench(
            ['GPIB0::24::INSTR', 'GPIB0::8::INSTR'], self.backend, self.journal,
            operator=self.operator, manager_factory=lambda: gpib.ResourceManager(_backend=self.backend),
            clock=self.clock.now, pause=self.clock.sleep, wait_seconds=2)
        self.addCleanup(self.bench.close)

    def operator(self, phase, instruction):
        self.steps.append(phase)
        if phase == 'usb_unplug':
            self.backend.connected = False
        elif phase in ('usb_replug', 'initial_usb_replug'):
            self.backend.connected = True
            self.backend.generation += 1
            self.backend.index = 3  # OS enumeration order is allowed to change.
        elif phase == 'power_off':
            self.backend.powered = False
        elif phase == 'power_on':
            self.backend.powered = True
            self.backend.settings[':SOUR:FUNC?'] = 'CURR'
        return True

    def connect(self):
        self.bench.discover()
        self.bench.connect()

    def test_usb_replug_keeps_serial_identity_and_replaces_the_old_controller(self):
        self.connect()
        old = self.bench.primary.controller
        self.bench.usb_cycle()
        self.assertEqual(self.steps, ['usb_unplug', 'usb_replug'])
        self.assertTrue(old.closed)
        self.assertIsNot(old, self.bench.primary.controller)
        self.assertEqual(self.bench.primary.resource_name, 'GPIB3::24::INSTR')
        self.assertEqual(self.backend.handles, [0, 1])  # one handle for both instruments, each generation
        self.assertGreaterEqual(self.clock.value, 5)
        self.assertEqual(self.journal.data['checks'][-1]['phase'], 'usb_replug_new_session')

    def test_power_cycle_records_settings_changes_without_reconfiguring_source(self):
        self.connect()
        self.bench.power_cycle()
        self.assertEqual(self.steps, ['power_off', 'power_on'])
        last = self.journal.data['checks'][-1]
        self.assertEqual(last['phase'], 'power_recovery')
        self.assertIn(':SOUR:FUNC?', last['changed_settings'])
        payloads = [e[3] for e in self.backend.events if e[0] == 'write']
        self.assertTrue(all(p.endswith(b'?\n') for p in payloads))

    def test_operator_cancel_and_empty_confirmation_do_not_open_missing_hardware(self):
        self.backend.connected = False
        for response in (False, None, ''):
            self.bench.operator = lambda *args: response
            with self.assertRaises(bench_tool.OperatorCancelled):
                self.bench.discover()
        self.assertFalse(self.backend.handles)
        self.assertEqual(self.journal.data['waiting']['phase'], 'initial_usb_replug')

    def test_replacement_adapter_cannot_be_mistaken_for_the_original(self):
        self.connect()
        def replacement(phase, instruction):
            result = self.operator(phase, instruction)
            if phase == 'usb_replug':
                self.backend.serial = 'DIFFERENT-ADAPTER'
            return result
        self.bench.operator = replacement
        with self.assertRaises(TimeoutError):
            self.bench.usb_cycle()
        self.assertEqual(self.backend.handles, [0])

    def test_changed_identity_after_replug_is_not_accepted(self):
        self.connect()
        def replacement(phase, instruction):
            result = self.operator(phase, instruction)
            if phase == 'usb_replug':
                self.backend.identities[24] = 'KEITHLEY,MODEL 2400,OTHER,1.0'
            return result
        self.bench.operator = replacement
        with self.assertRaisesRegex(ValueError, 'Identity changed'):
            self.bench.usb_cycle()
        self.assertIsNone(self.bench.manager)

    def test_power_restore_with_output_on_stops_before_further_test_phases(self):
        self.connect()
        def output_on(phase, instruction):
            result = self.operator(phase, instruction)
            if phase == 'power_on':
                self.backend.output = '1'
            return result
        self.bench.operator = output_on
        with self.assertRaisesRegex(ValueError, 'output is not off'):
            self.bench.power_cycle()
        self.assertNotIn('power_recovery', [e['phase'] for e in self.journal.data['checks']])

    def test_shared_fault_blocks_both_resources_until_explicit_recovery(self):
        self.connect()
        self.bench.shared_recovery()
        self.assertEqual(self.journal.data['checks'][-1]['instruments'], 2)
        self.assertFalse(self.bench.primary.controller.faulted)

    def test_power_test_saves_existing_buffer_and_restores_its_transfer_format_first(self):
        self.backend.trace_points = 1
        self.backend.settings[':FORM:DATA?'] = 'SREAL'
        self.connect()
        self.bench.power_cycle()
        saved = self.journal.directory / 'pre-power-buffer.txt'
        self.assertEqual(saved.read_text(), '1,2,3,4\n')
        self.assertEqual(self.backend.settings[':FORM:DATA?'], 'SREAL')
        phases = [e['phase'] for e in self.journal.data['checks']]
        self.assertLess(phases.index('pre_power_buffer'), phases.index('power_off'))

    def test_failed_buffer_backup_stops_before_asking_for_power_off(self):
        self.backend.trace_points, self.backend.fail_trace_read = 1, True
        self.connect()
        with self.assertRaises(gpib.GpibTimeoutError):
            self.bench.power_cycle()
        self.assertFalse(self.steps)
        self.assertTrue(self.bench.primary.controller.faulted)

    def test_ordinary_bus_queries_share_the_existing_handle(self):
        self.connect()
        results = bus_tool.run_queries(self.bench.instruments, ['NUM?', 'NUM?'], count=20, numeric=True)
        self.assertEqual([r['queries'] for r in results], [20, 20])
        self.assertEqual(self.backend.handles, [0])

    def test_bad_numeric_query_never_becomes_a_passed_bus_result(self):
        self.connect()
        with self.assertRaises(ValueError):
            bus_tool.run_queries(self.bench.instruments, ['*IDN?', 'NUM?'], count=20, numeric=True)

    def test_unconfirmed_no_eoi_blocks_large_write_without_replay(self):
        self.connect()
        self.backend.no_eoi_ack = False
        supported = check_tool.no_eoi_check(self.bench.primary, self.journal.record)
        before = len(self.backend.events)
        self.assertFalse(check_tool.large_write_check(self.bench.primary, self.journal.record, supported))
        self.assertEqual(len(self.backend.events), before)
        unconfirmed = [e for e in self.backend.events if e[0] == 'write' and not e[4]]
        self.assertEqual(len(unconfirmed), 1)
        self.assertFalse(self.bench.primary.controller.faulted)

    def test_large_writes_require_every_chunk_ack_and_final_eoi_only(self):
        self.connect()
        self.assertTrue(check_tool.no_eoi_check(self.bench.primary, self.journal.record))
        self.assertTrue(check_tool.large_write_check(self.bench.primary, self.journal.record, True))
        chunks = [(len(e[3]), e[4]) for e in self.backend.events
                  if e[0] == 'write' and (len(e[3]) >= 65535 or e[3] == b'*IDN?\n')]
        self.assertIn([(65535, False), (6, True)], [chunks[i:i+2] for i in range(len(chunks))])
        self.assertIn([(65535, False), (65535, False), (6, True)],
                      [chunks[i:i+3] for i in range(len(chunks))])

    def test_partial_large_write_faults_bus_and_never_sends_the_next_chunk(self):
        self.connect()
        self.backend.short_large_write = True
        with self.assertRaises(gpib.ProtocolError):
            check_tool.large_write_check(self.bench.primary, self.journal.record, True)
        large = [e for e in self.backend.events if e[0] == 'write' and len(e[3]) >= 65535]
        self.assertEqual(len(large), 1)
        self.assertTrue(self.bench.primary.controller.faulted)

    def test_prepared_plan_and_blocked_features_are_not_completed_acceptance(self):
        self.assertFalse(self.journal.data['success'])
        self.assertEqual(self.journal.data['state'], 'prepared')
        self.journal.data['blocked'].append('No real write acknowledgement')
        self.journal.finish()
        self.assertFalse(self.journal.data['success'])
        self.assertEqual(self.journal.data['state'], 'partial')

    def test_plan_mode_never_constructs_native_backend_or_opens_usb(self):
        output = Path(self.folder.name) / 'prepared'
        argv = ['bench_acceptance', '--resource', 'GPIB0::24::INSTR', '--physical', 'usb', 'power',
                '--functional', '--acquire-seconds', '3600', '--plan', '--output', str(output)]
        with patch.object(sys, 'argv', argv), patch.object(bench_tool, 'NativeBackend',
                side_effect=AssertionError('Plan mode must not touch USB')):
            self.assertEqual(bench_tool.main(), 0)
        import json
        report = json.loads((output / 'report.json').read_text())
        self.assertEqual(report['state'], 'prepared')
        self.assertFalse(report['success'])
        self.assertEqual(report['checks'], [])

    def test_visible_but_unreadable_adapter_is_not_reported_as_absent(self):
        self.bench.serial = 'EXPECTED'
        self.backend.list_adapters = lambda: [dict(index=0, serial='', accessible=False)]
        with self.assertRaisesRegex(ValueError, 'identity is unreadable'):
            self.bench.discover()
        self.assertFalse(self.steps)

    def run_main(self, name, extra, operator=None):
        output = Path(self.folder.name) / name
        argv = ['bench_acceptance', '--resource', 'GPIB0::24::INSTR', '--resource', 'GPIB0::8::INSTR',
                '--bus-seconds', '0', '--bus-count', '5', '--count', '1', '--output', str(output)] + extra
        manager_class = gpib.ResourceManager
        with patch.object(sys, 'argv', argv), \
                patch.object(bench_tool, 'NativeBackend', return_value=self.backend), \
                patch.object(bench_tool.gpib, 'ResourceManager', side_effect=lambda: manager_class(_backend=self.backend)), \
                patch.object(bench_tool, 'console_operator', side_effect=operator or self.operator), \
                patch.object(bench_tool.time, 'monotonic', self.clock.now), \
                patch.object(bench_tool.time, 'sleep', self.clock.sleep), \
                patch.object(sys, 'path', [str(ROOT / 'tools')] + sys.path):
            code = bench_tool.main()
        return code, json.loads((output / 'report.json').read_text()), output

    def test_live_entrypoint_runs_usb_power_and_shared_queries_on_one_manager_at_a_time(self):
        code, report, _ = self.run_main('physical-cli', ['--physical', 'usb', 'power'])
        self.assertEqual(code, 0)
        self.assertEqual(report['state'], 'complete')
        self.assertIsNone(report['waiting'])
        self.assertEqual(self.steps, ['usb_unplug', 'usb_replug', 'power_off', 'power_on'])
        self.assertEqual(self.backend.handles, [0, 1])

    def test_full_functional_entrypoint_reports_unconfirmed_writes_as_partial(self):
        self.backend.no_eoi_ack = False
        code, report, _ = self.run_main('functional-cli', ['--functional'])
        self.assertEqual(code, 1)
        self.assertEqual(report['state'], 'partial')
        self.assertTrue(any('No-EOI' in item for item in report['blocked']))
        self.assertFalse(any(e[0] == 'write' and len(e[3]) >= 65535 for e in self.backend.events))

    def test_live_entrypoint_cancellation_is_saved_before_any_device_open(self):
        self.backend.connected = False
        code, report, _ = self.run_main('cancelled-cli', [], operator=lambda *args: False)
        self.assertEqual(code, 1)
        self.assertEqual(report['state'], 'cancelled')
        self.assertFalse(self.backend.handles)

    def test_failed_acquisition_stops_the_entire_suite_and_saves_unknown_output_state(self):
        calls = []
        def failed_acquisition(*args):
            calls.append('acquire')
            raise gpib.GpibTimeoutError('Failed batch must not replay')
        def unknown_shutdown(inst):
            calls.append('shutdown')
            return dict(output_off_confirmed=False, errors=['link lost'], manual_output_check_required=True)
        fake_module = SimpleNamespace(acquire=failed_acquisition, shutdown=unknown_shutdown)
        with patch.dict(sys.modules, {'keithley_2400_acquire': fake_module}):
            code, report, output = self.run_main('failed-acquire-cli', ['--functional', '--acquire-seconds', '3600'])
        self.assertEqual(code, 1)
        self.assertEqual(report['state'], 'failed')
        self.assertTrue(report['manual_output_check_required'])
        self.assertEqual(calls, ['acquire', 'shutdown'])
        pilot = json.loads((output / 'pilot.json').read_text())
        self.assertFalse(pilot['success'])
        self.assertTrue(pilot['cleanup']['manual_output_check_required'])
        self.assertFalse((output / 'large_ascii.json').exists())


if __name__ == '__main__':
    unittest.main()
