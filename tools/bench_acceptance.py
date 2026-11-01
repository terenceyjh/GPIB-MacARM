"""Guided bench acceptance, with explicit pauses for USB and 2400 power changes.

--plan prepares a report without loading the native backend or touching USB.
Live runs require an idle bus, a confirmed 2400 first, and explicit operator
completion at each physical step. Optional acquisition resets/configures the
2400 and applies current; confirm sample limits. Failed batches are never replayed.
"""
import argparse
import json
import math
from pathlib import Path
import platform
import re
import time
from types import SimpleNamespace

import gpib_macarm as gpib
from gpib_macarm._backend import NativeBackend

SETTINGS = (':SOUR:FUNC?', ':SOUR:CURR?', ':SOUR:VOLT?', ':SENS:FUNC?',
            ':SENS:VOLT:PROT?', ':SYST:RSEN?', ':FORM:DATA?', ':FORM:ELEM?', ':TRIG:COUN?')


class OperatorCancelled(RuntimeError):
    pass


class Journal:
    def __init__(self, directory, plan):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.data = dict(schema_version=1, state='prepared', success=False,
                         plan=plan, checks=[], blocked=[], waiting=None)
        self.save()

    def save(self):
        temporary = self.directory / 'report.tmp'
        temporary.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + '\n')
        temporary.replace(self.directory / 'report.json')

    def record(self, phase, **details):
        self.data['checks'].append(dict(phase=phase, **details))
        self.save()
        print(phase, details.get('status', 'recorded'), flush=True)

    def finish(self):
        self.data['success'] = not self.data['blocked']
        self.data['state'] = 'complete' if self.data['success'] else 'partial'
        self.save()


def console_operator(phase, instruction):
    print(f'\n[{phase}] {instruction}', flush=True)
    try:
        return input('完成上述操作后输入 done；输入其他内容取消：').strip().lower() == 'done'
    except EOFError:
        return False


class PhysicalBench:
    def __init__(self, resources, backend, journal, operator=None,
                 manager_factory=None, serial=None,
                 clock=None, pause=None, wait_seconds=60):
        parsed = [re.fullmatch(r'GPIB(\d+)::(\d+)::INSTR', r, re.I) for r in resources]
        if (not parsed or not all(parsed) or len({int(p[1]) for p in parsed}) != 1
                or any(not 1 <= int(p[2]) <= 30 for p in parsed)
                or len({int(p[2]) for p in parsed}) != len(parsed)):
            raise ValueError('Use distinct confirmed addresses on one adapter; put the 2400 first')
        if not math.isfinite(wait_seconds) or wait_seconds <= 0:
            raise ValueError('Invalid adapter wait')
        self.addresses = [int(p[2]) for p in parsed]
        self.index, self.serial = int(parsed[0][1]), serial
        self.backend, self.journal = backend, journal
        self.operator = console_operator if operator is None else operator
        self.manager_factory = gpib.ResourceManager if manager_factory is None else manager_factory
        self.clock = time.monotonic if clock is None else clock
        self.pause = time.sleep if pause is None else pause
        self.wait_seconds = wait_seconds
        self.manager, self.instruments, self.identities = None, [], None

    @property
    def primary(self):
        return self.instruments[0]

    def operator_step(self, phase, instruction):
        self.journal.data['waiting'] = dict(phase=phase, instruction=instruction)
        self.journal.save()
        if self.operator(phase, instruction) is not True:
            raise OperatorCancelled('Operator did not confirm: ' + phase)
        self.journal.data['waiting'] = None
        self.journal.record(phase, status='operator_confirmed')

    def adapter(self):
        items = self.backend.list_adapters()
        if self.serial:
            matches = [a for a in items if a.get('serial') == self.serial]
            if not matches and any(not a.get('serial') and a.get('accessible') is False for a in items):
                raise ValueError('An adapter is visible but its identity is unreadable; check other programs/USB access')
        else:
            if len(items) > 1:
                raise ValueError('Specify --serial when multiple adapters are connected')
            matches = [a for a in items if a['index'] == self.index]
        if len(matches) > 1:
            raise ValueError('Adapter serial is ambiguous')
        return matches[0] if matches else None

    def wait_adapter(self, present):
        deadline = self.clock() + self.wait_seconds
        while True:
            item = self.adapter()
            if (item is not None) == present:
                return item
            if self.clock() >= deadline:
                raise TimeoutError('Expected USB adapter presence: ' + str(present))
            self.pause(.25)

    def discover(self):
        item = self.adapter()
        if item is None:
            self.operator_step('initial_usb_replug',
                '确认 2400 面板 OUTPUT 已关闭。将转接线的 USB 端拔下，等待至少 5 秒后插回；样品四线和 GPIB 端保持连接。')
            item = self.wait_adapter(True)
        if not item.get('serial'):
            raise ValueError('A readable adapter serial is required to identify the same adapter after replug')
        self.serial, self.index = item['serial'], item['index']
        self.journal.data['adapter'] = item
        self.journal.save()

    def connect(self):
        item = self.wait_adapter(True)
        self.index = item['index']
        self.manager = self.manager_factory()
        try:
            self.instruments = [self.manager.open_resource(f'GPIB{self.index}::{a}::INSTR',
                                serial=self.serial, timeout=10000) for a in self.addresses]
            identities = [s.query('*IDN?') for s in self.instruments]
            fields = identities[0].split(',')
            if len(fields) < 2 or fields[1].strip().upper() != 'MODEL 2400':
                raise ValueError('First resource is not a confirmed Model 2400')
            if self.identities is not None and identities != self.identities:
                raise ValueError('Identity changed after reconnect; no further commands were sent')
            self.identities = identities
            self.require_output_off()
            self.journal.record('connected', status='passed', identities=identities,
                                resources=[s.resource_name for s in self.instruments])
        except BaseException:
            self.close()
            raise

    def require_output_off(self):
        if self.primary.query(':OUTP?') != '0':
            raise ValueError('2400 output is not off; stop and check its front panel')

    def settings(self):
        return {q: self.primary.query(q) for q in SETTINGS}

    def verify(self):
        for _ in range(3):
            for inst, identity in zip(self.instruments, self.identities):
                if inst.query('*IDN?') != identity:
                    raise ValueError('Identity or reply boundary mismatch')
        self.require_output_off()

    def verify_lockout(self, original):
        for inst in self.instruments:
            try:
                inst.query('*IDN?')
            except gpib.SessionFaultedError as exc:
                if exc.__cause__ is not original:
                    raise ValueError('Fault lockout lost the original cause')
            else:
                raise ValueError('An ordinary query was allowed on a faulted controller')

    def provoke_fault(self, unanswered_read=False):
        inst = self.primary
        timeout = inst.timeout
        inst.timeout = 100
        try:
            try:
                inst.read() if unanswered_read else inst.query('*IDN?')
            except gpib.GpibError as exc:
                original = exc
            else:
                raise ValueError('Expected an I/O failure; physical fault was not observed')
        finally:
            inst.timeout = timeout
        self.verify_lockout(original)
        return original

    def shared_recovery(self):
        self.require_output_off()
        before = self.settings()
        self.provoke_fault(unanswered_read=True)
        self.primary.recover()
        self.verify()
        if self.settings() != before:
            raise ValueError('Settings changed during shared-controller recovery')
        self.journal.record('shared_recovery', status='passed',
                            instruments=len(self.instruments), recovery=self.primary.controller.last_recovery)

    def backup_buffer(self):
        count = int(self.primary.query(':TRAC:POIN:ACT?'))
        if not count:
            self.journal.record('pre_power_buffer', status='saved', points=0)
            return
        target = self.journal.directory / 'pre-power-buffer.txt'
        if target.exists():
            raise FileExistsError(target)
        fmt = self.primary.query(':FORM:DATA?')
        self.primary.write(':FORM:DATA ASC')
        try:
            reply = self.primary.query(':TRAC:DATA?')
            with target.open('x') as output:
                output.write(reply + '\n')
        finally:
            if not self.primary.controller.faulted:
                self.primary.write(':FORM:DATA ' + fmt)
        self.journal.record('pre_power_buffer', status='saved', points=count, file=target.name)

    def usb_cycle(self):
        self.require_output_off()
        before = self.settings()
        self.operator_step('usb_unplug',
            '现在只拔下转接线的 USB 端，保持拔下，等下一条提示再插回；不要动样品四线或 GPIB 端。')
        off_at = self.clock()
        self.wait_adapter(False)
        original = self.provoke_fault()
        try:
            self.primary.recover()
        except gpib.GpibError:
            self.verify_lockout(original)
        else:
            raise ValueError('Recovery unexpectedly succeeded while the adapter was absent')
        self.journal.record('usb_absent_fault', status='passed', error=str(original))
        self.pause(max(0, 5 - (self.clock() - off_at)))
        self.operator_step('usb_replug', '现在将转接线 USB 端插回原来的接口，插好后确认。')
        self.wait_adapter(True)
        self.verify_lockout(original)  # re-enumeration must not silently revive old sessions
        self.close()
        self.connect()
        self.verify()
        if self.settings() != before:
            raise ValueError('2400 settings changed across USB-only replug')
        self.journal.record('usb_replug_new_session', status='passed')

    def power_cycle(self):
        self.require_output_off()
        self.backup_buffer()
        before = self.settings()
        self.operator_step('power_off',
            '确认 2400 的 OUTPUT 关闭后，用电源开关关闭 2400，保持关机；USB 和样品接线保持不动。')
        off_at = self.clock()
        original = self.provoke_fault()
        self.journal.record('power_absent_fault', status='passed', error=str(original))
        self.pause(max(0, 5 - (self.clock() - off_at)))
        self.operator_step('power_on',
            '现在开启 2400，等开机完成、面板正常，并确认 OUTPUT 仍关闭后再确认。')
        # Power cycling may reset instrument settings; do not restore them or
        # resume a failed measurement. Recover communication and report changes.
        self.primary.recover()
        self.verify()
        after = self.settings()
        changed = {q: dict(before=before[q], after=after[q]) for q in before if before[q] != after[q]}
        self.journal.record('power_recovery', status='passed', changed_settings=changed,
                            recovery=self.primary.controller.last_recovery)

    def close(self):
        if self.manager is not None:
            self.manager.close()
        self.manager, self.instruments = None, []


def run_acquisition(bench, seconds, points, nplc, delay, args, name):
    # Script-local imports work for a source checkout or unpacked source archive.
    from keithley_2400_acquire import acquire, shutdown
    prefix = bench.journal.directory / name
    options = SimpleNamespace(output=prefix, current=args.current, compliance=args.compliance,
                              nplc=nplc, delay=delay, points=points, seconds=seconds)
    child = dict(success=False, parameters=vars(options).copy())
    child['parameters']['output'] = str(prefix)

    def save():
        temporary = prefix.with_suffix('.tmp')
        temporary.write_text(json.dumps(child, indent=2) + '\n')
        temporary.replace(prefix.with_suffix('.json'))

    inst = bench.primary
    timeout = inst.timeout
    inst.timeout = 60000
    try:
        acquire(inst, options, child, save)
    except BaseException as exc:
        child.update(success=False, error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        child['cleanup'] = shutdown(inst)
        inst.timeout = timeout
        if not child['cleanup']['output_off_confirmed'] or child['cleanup']['errors']:
            child['success'] = False
        save()
        cleanup = child['cleanup']
        bench.journal.record(name + '_cleanup',
                             status='passed' if cleanup['output_off_confirmed'] and not cleanup['errors'] else 'failed',
                             report=prefix.with_suffix('.json').name, cleanup=cleanup)
        if not cleanup['output_off_confirmed']:
            bench.journal.data['manual_output_check_required'] = True
            bench.journal.save()
            print('无法确认 2400 输出已关闭：请在仪器面板关闭 OUTPUT 并核对实际状态。测试已停止。', flush=True)
    if not child['success']:
        raise ValueError('Acquisition/cleanup failed; check actual output and the saved report')
    bench.journal.record(name, status='passed', samples=child['samples'],
                         seconds=child['elapsed_seconds'], max_reply_bytes=child['max_reply_bytes'])


def run_automatic(bench, args):
    from bus_smoke import run_queries
    from keithley_2400_check import binary_check, recovery_check, no_eoi_check, large_write_check
    record = bench.journal.record
    if len(bench.instruments) > 1:
        results = run_queries(bench.instruments, args.query, args.bus_count, args.bus_seconds, args.numeric)
        record('concurrent_bus_queries', status='passed', results=results)
        if args.functional:
            bench.shared_recovery()
    if args.acquire_seconds is not None:
        run_acquisition(bench, 0, 3, 5, .05, args, 'pilot')
        run_acquisition(bench, 0, 2500, .01, .001, args, 'large_ascii')
    if args.functional:
        if int(bench.primary.query(':TRAC:POIN:ACT?')):
            binary_check(bench.primary, record, bench.journal.directory)
        else:
            bench.journal.data['blocked'].append('Binary buffer empty; an authorized acquisition is required')
            record('binary', status='blocked')
        recovery_check(bench.primary, record, args.count)
        record('2400_recovery_matrix', status='passed')
    if args.acquire_seconds is not None and args.acquire_seconds > 0:
        run_acquisition(bench, args.acquire_seconds, 10, 5, .05, args, 'sustained_acquisition')
    if args.functional:
        supported = no_eoi_check(bench.primary, record)
        if not large_write_check(bench.primary, record, supported):
            bench.journal.data['blocked'].append('No-EOI acknowledgement and large final-EOI-only writes')
    bench.verify()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--resource', action='append', required=True, help='2400 first; repeat for confirmed shared instruments')
    p.add_argument('--serial', help='Adapter serial; required if multiple adapters are connected')
    p.add_argument('--physical', nargs='*', choices=('usb', 'power'), default=[])
    p.add_argument('--functional', action='store_true', help='Binary, recovery, no-EOI and gated large-write checks')
    p.add_argument('--acquire-seconds', type=float, help='Also run pilot/2500 points, then timed acquisition; enables output')
    p.add_argument('--current', type=float, default=2.5e-6)
    p.add_argument('--compliance', type=float, default=21)
    p.add_argument('--query', action='append', help='Shared-bus query, one common or one per resource; default *IDN?')
    p.add_argument('--numeric', action='store_true')
    p.add_argument('--count', type=int, default=3)
    p.add_argument('--bus-count', type=int, default=100)
    p.add_argument('--bus-seconds', type=float, default=60)
    p.add_argument('--plan', action='store_true', help='Prepare only; no USB enumeration or instrument access')
    p.add_argument('--output', type=Path, required=True, help='New local report directory')
    args = p.parse_args()
    if (not all(math.isfinite(v) for v in (args.current, args.compliance))
            or not 0 < abs(args.current) <= .01 or not 0 < args.compliance <= 21
            or not 1 <= args.count <= 100
            or not 1 <= args.bus_count <= 100000 or not math.isfinite(args.bus_seconds)
            or not 0 <= args.bus_seconds <= 86400
            or (args.acquire_seconds is not None and
                (not math.isfinite(args.acquire_seconds) or not 0 <= args.acquire_seconds <= 86400))):
        p.error('Invalid current, compliance, count or acquisition duration')
    args.query = args.query or ['*IDN?']
    if len(args.query) == 1:
        args.query *= len(args.resource)
    if (len(args.query) != len(args.resource) or
            any(not q.endswith('?') or any(c in q for c in ';\r\n') for q in args.query)):
        p.error('Specify one non-compound query per instrument, or one common query')
    if len(set(args.physical)) != len(args.physical):
        p.error('Do not repeat physical phases')
    # Validate resource spelling before creating files or accessing native code.
    try:
        PhysicalBench(args.resource, None, None, serial=args.serial)
    except ValueError as exc:
        p.error(str(exc))
    if args.output.exists():
        p.error('Output directory already exists; choose a new run')
    plan = dict(resources=args.resource, physical=args.physical, functional=args.functional,
                acquire_seconds=args.acquire_seconds, current_a=args.current, compliance_v=args.compliance,
                adapter_serial=args.serial, queries=args.query, numeric=args.numeric,
                recovery_count=args.count, bus_count=args.bus_count, bus_seconds=args.bus_seconds,
                operator_steps=['initial USB restore if absent'] +
                [step for phase in args.physical for step in (('USB out', 'USB in') if phase == 'usb' else ('2400 off', '2400 on/ready/output off'))])
    journal = Journal(args.output, plan)
    if args.plan:
        print('Prepared only. No hardware checks have run.', flush=True)
        return 0
    bench = None
    try:
        journal.data['state'] = 'running'
        journal.save()
        backend = NativeBackend()
        journal.data['runtime'] = dict(python=platform.python_version(), machine=platform.machine(),
                                      platform=platform.platform(), package_version=gpib.__version__,
                                      native_library=str(backend.path) if hasattr(backend, 'path') else None)
        journal.save()
        bench = PhysicalBench(args.resource, backend, journal, serial=args.serial)
        bench.discover()
        bench.connect()
        for phase in args.physical:
            bench.usb_cycle() if phase == 'usb' else bench.power_cycle()
        run_automatic(bench, args)
        journal.finish()
    except BaseException as exc:
        journal.data.update(state='cancelled' if isinstance(exc, (OperatorCancelled, KeyboardInterrupt)) else 'failed',
                            success=False, error=f'{type(exc).__name__}: {exc}')
        journal.save()
        print(journal.data['error'], flush=True)
    finally:
        if bench is not None:
            bench.close()
    print('Run state:', journal.data['state'], flush=True)
    return 0 if journal.data['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
