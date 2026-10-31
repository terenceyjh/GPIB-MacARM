"""Explicit SR830 fault/recovery check; never resets or enables instrument output.

Opening sends REN/IFC. recover() discards failed replies and sends device clear.
Use only a confirmed SR830 address, with no acquisition using this adapter.
"""
import argparse
import json
import math
from pathlib import Path
import time

import gpib_macarm as gpib


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--address', type=int, required=True)
    p.add_argument('--index', type=int, default=0)
    p.add_argument('--serial')
    p.add_argument('--count', type=int, default=5)
    p.add_argument('--partial', action='store_true')
    p.add_argument('--no-eoi', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if not 1 <= args.count <= 100:
        p.error('count must be 1..100')
    if args.output.exists():
        raise FileExistsError(args.output)
    report = {'resource': f'GPIB{args.index}::{args.address}::INSTR', 'events': [],
              'success': False, 'version': gpib.__version__}

    def save():
        temporary = args.output.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2), encoding='utf-8')
        temporary.replace(args.output)

    def record(name, operation):
        start = time.monotonic()
        event = {'name': name}
        try:
            value = operation()
            event['value'] = value
            return value
        except BaseException as exc:
            event['error'] = f'{type(exc).__name__}: {exc}'
            raise
        finally:
            event['seconds'] = time.monotonic()-start
            report['events'].append(event)
            save()
            print(event, flush=True)

    rm = gpib.ResourceManager()
    try:
        inst = rm.open_resource(report['resource'], serial=args.serial, timeout=1000, query_delay=.02)
        inst.write('OUTX 1')
        identity = record('initial_identity', lambda: inst.query('*IDN?'))
        if len(identity.split(',')) < 2 or identity.split(',')[1].strip().upper() != 'SR830':
            raise ValueError('This check is only for an SR830')
        keys = ('ISRC', 'ICPL', 'SENS', 'RMOD', 'OFLT', 'OFSL', 'FREQ', 'SLVL', 'DDEF? 1', 'DDEF? 2')

        def settings():
            return {k: inst.query(k if '?' in k else k+'?') for k in keys}

        before = record('settings_before', settings)

        def verify():
            for _ in range(5):
                actual_identity = inst.query('*IDN?')
                if actual_identity != identity:
                    raise AssertionError(f'Reply boundary mismatch: {actual_identity!r}')
                if inst.query('FREQ?') != before['FREQ']:
                    raise AssertionError('Frequency reply mismatch')
                values = [float(x) for x in inst.query('SNAP? 1,2,3,4,9').split(',')]
                if len(values) != 5 or not all(math.isfinite(v) for v in values):
                    raise AssertionError('Invalid SNAP data after recovery')
            if settings() != before:
                raise AssertionError('Instrument settings changed during recovery')
            return 'identity, typed replies, SNAP and settings match'

        def recover_and_verify(name):
            record(name+'_recover', inst.recover)
            record(name+'_discard', lambda: inst.controller.last_recovery)
            return record(name+'_verify', verify)

        for n in range(args.count):
            inst.timeout = 100
            try:
                record(f'timeout_{n}', inst.read)
            except gpib.GpibTimeoutError:
                pass
            else:
                raise AssertionError('Expected unanswered read to time out')
            start = time.monotonic()
            try:
                inst.query('*IDN?')
            except gpib.SessionFaultedError:
                if time.monotonic()-start > .1:
                    raise AssertionError('Faulted session did not stop immediately')
            else:
                raise AssertionError('Faulted session allowed ordinary I/O')
            inst.timeout = 1000
            recover_and_verify(f'timeout_{n}')

        if args.partial:
            inst.write('FREQ?')
            first = inst.read_bytes(1)
            record('partial_reply_prefix', lambda: first.hex())
            recover_and_verify('partial_reply')

        if args.no_eoi:
            inst.send_end = False
            try:
                value = record('no_eoi_identity', lambda: inst.query('*IDN?'))
                if value != identity:
                    raise AssertionError('No-EOI identity mismatch')
                report['no_eoi_supported_here'] = True
            except gpib.GpibError:
                report['no_eoi_supported_here'] = False
            finally:
                inst.send_end = True
            if inst.controller.faulted:
                recover_and_verify('no_eoi')
        report['success'] = True
    except BaseException as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        rm.close()
        save()
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
