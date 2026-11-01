"""2400 binary transfer and explicit fault/recovery acceptance (output stays off).

--recovery deliberately causes communication faults and sends IFC/SDC. --binary
reads existing buffer data and temporarily changes its transfer format. --no-eoi
tests an unvalidated write mode and reports missing acknowledgement as failure.
Use only on an idle adapter and a confirmed 2400; logs/identifiers stay local.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import time

import gpib_macarm as gpib


def decode_sreal(raw, count, order):
    if order not in ('NORM', 'SWAP'):
        raise ValueError('Unsupported byte order')
    if raw[:2] != b'#0' or raw[-1:] != b'\n' or len(raw) != 3 + count * 4:
        raise ValueError('Invalid 2400 #0 binary header, payload length or terminator')
    return struct.unpack(('>' if order == 'NORM' else '<') + str(count) + 'f', raw[2:-1])


def binary_check(inst, record, directory):
    if int(inst.query(':TRAC:POIN:ACT?')) < 1:
        raise ValueError('No stored readings; populate the buffer with an authorized acquisition first')
    saved = {k: inst.query(k + '?') for k in (':FORM:DATA', ':FORM:BORD')}
    record('binary_saved_settings', settings=saved)
    chunk_size = inst.chunk_size
    try:
        inst.write(':FORM:DATA ASC')
        reference = [float(v) for v in inst.query(':TRAC:DATA?').split(',')]
        chunks = [1, 2, 3, 7, 15, 30, 31, 64, 4096, 65535] if len(reference) < 1000 else [7, 15, 31, 4096, 65535]
        for fmt in ('SREAL', 'REAL,32'):
            for order in ('NORM', 'SWAP'):
                inst.write(':FORM:BORD ' + order)
                inst.write(':FORM:DATA ' + fmt)
                baseline = None
                for chunk in chunks:
                    inst.chunk_size = chunk
                    inst.write(':TRAC:DATA?')
                    raw = inst.read_raw()
                    values = decode_sreal(raw, len(reference), order)
                    if not all(math.isclose(a, b, rel_tol=2e-6, abs_tol=1e-12) for a, b in zip(values, reference)):
                        raise ValueError('Binary readings disagree with the same stored ASCII data')
                    if baseline is None:
                        baseline = raw
                        (directory / f'{fmt.replace(",", "-")}-{order}.bin').write_bytes(raw)
                    if raw != baseline:
                        raise ValueError('Binary bytes changed with read chunk size')
                    record('binary', format=fmt, order=order, chunk=chunk, bytes=len(raw),
                           sha256=hashlib.sha256(raw).hexdigest(), nul=raw.count(b'\0'),
                           cr=raw.count(b'\r'), lf=raw.count(b'\n'))
                inst.write(':TRAC:DATA?')
                if inst.read_bytes(2) + inst.read_bytes(len(baseline) - 2) != baseline:
                    raise ValueError('Separate binary header/payload reads changed message boundaries')
                record('binary_header_split', format=fmt, order=order, bytes=len(baseline))
    finally:
        inst.chunk_size = chunk_size
        # Recovery is explicit, logged, and never resumes the failed check.
        # Leave a faulted session untouched for the caller to inspect/recover.
        if not inst.controller.faulted:
            for key, value in saved.items():
                inst.write(key + ' ' + value)


def recovery_check(inst, record, count):
    identity = inst.query('*IDN?')
    keys = (':SOUR:FUNC?', ':SOUR:CURR?', ':SOUR:VOLT?', ':SENS:FUNC?', ':SENS:VOLT:PROT?',
            ':SYST:RSEN?', ':FORM:DATA?', ':FORM:ELEM?', ':TRIG:COUN?', ':OUTP?')
    before = {q: inst.query(q) for q in keys}
    timeout = inst.timeout

    def verify(name):
        begin = time.monotonic()
        inst.recover()
        for _ in range(5):
            if inst.query('*IDN?') != identity or inst.query(':OUTP?') != '0':
                raise ValueError('Identity/output state mismatch after recovery')
        if {q: inst.query(q) for q in keys} != before:
            raise ValueError('Instrument settings changed during recovery')
        record(name, seconds=time.monotonic() - begin, recovery=inst.controller.last_recovery)

    for iteration in range(count):
        inst.timeout = 100
        try:
            inst.read()
        except gpib.GpibTimeoutError as original:
            fault = original
        else:
            raise ValueError('Expected an unanswered read to time out')
        begin = time.monotonic()
        try:
            inst.query('*IDN?')
        except gpib.SessionFaultedError as exc:
            if exc.__cause__ is not fault or time.monotonic() - begin > .1:
                raise ValueError('Fault lockout lost the original error or did not stop immediately')
        else:
            raise ValueError('Faulted controller allowed ordinary I/O')
        inst.timeout = timeout
        verify(f'read_timeout_{iteration + 1}')
    inst.write('*IDN?')
    if inst.read_bytes(1) != identity[:1].encode('ascii'):
        raise ValueError('Unexpected partial reply')
    verify('partial_reply')
    limit = inst.max_read_bytes
    inst.max_read_bytes = 1
    try:
        inst.query('*IDN?')
    except gpib.MessageTooLongError:
        pass
    else:
        raise ValueError('Over-limit reply did not fault the controller')
    finally:
        inst.max_read_bytes = limit
    verify('over_limit_reply')


def no_eoi_check(inst, record):
    """Require a real write completion, never emulate a missing acknowledgement."""
    identity = inst.query('*IDN?')
    if inst.query(':OUTP?') != '0':
        raise ValueError('Output must be off before no-EOI checks')
    timeout, send_end = inst.timeout, inst.send_end
    supported = True
    write_completed = False
    try:
        inst.send_end = False
        inst.timeout = 1000
        inst.write('*IDN?')
        write_completed = True
        if inst.read() != identity:
            raise ValueError('No-EOI identity/reply boundary mismatch')
        record('no_eoi', supported=True, write_call_completed=True)
    except gpib.GpibTimeoutError as exc:
        supported = False
        record('no_eoi', supported=False, write_call_completed=write_completed,
               timeout_stage='read' if write_completed else 'write',
               error=f'{type(exc).__name__}: {exc}',
               note='The command may have arrived. No retry or success acknowledgement is inferred.')
    finally:
        inst.timeout, inst.send_end = timeout, send_end
    if inst.controller.faulted:
        inst.recover()
        if inst.query('*IDN?') != identity or inst.query(':OUTP?') != '0':
            raise ValueError('Identity/output mismatch after no-EOI failure recovery')
        record('no_eoi_recovery', recovery=inst.controller.last_recovery)
    return supported


def large_write_check(inst, record, no_eoi_acknowledged):
    """Harmless short SCPI lines cross native write boundaries; EOI is last only.

    The 2400 input buffer cannot accept one enormous SCPI command. Each *WAI
    line is five bytes; the final identity reply verifies the new message's
    boundary. The native write must acknowledge EVERY chunk, without replay.
    """
    if not no_eoi_acknowledged:
        record('large_write', status='blocked', reason='No-EOI write completion is unconfirmed')
        return False
    identity = inst.query('*IDN?')
    if inst.query(':OUTP?') != '0':
        raise ValueError('Output must be off before large writes')
    timeout, send_end = inst.timeout, inst.send_end
    try:
        inst.timeout, inst.send_end = max(timeout, 60000), True
        for chunks in (1, 2):
            # 65535 is divisible by len(b'*WAI\n'), so each native intermediate
            # block ends at a complete command and the last block is *IDN?.
            payload = b'*WAI\n' * (65535 * chunks // 5) + b'*IDN?\n'
            if inst.write_raw(payload) != len(payload):
                raise ValueError('Large write returned a short count')
            if inst.read() != identity:
                raise ValueError('Large write reply boundary mismatch')
            error = inst.query(':SYST:ERR?')
            if not error.startswith('0,'):
                raise ValueError('Instrument rejected a large write: ' + error)
            if inst.query(':OUTP?') != '0':
                raise ValueError('Output changed during large write checks')
            record('large_write', status='passed', bytes=len(payload),
                   intermediate_chunks=chunks, final_chunk_bytes=6, final_eoi_only=True)
    finally:
        inst.timeout, inst.send_end = timeout, send_end
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--resource', required=True)
    p.add_argument('--binary', action='store_true')
    p.add_argument('--recovery', action='store_true')
    p.add_argument('--no-eoi', action='store_true')
    p.add_argument('--large-write', action='store_true', help='First require acknowledged no-EOI writes')
    p.add_argument('--count', type=int, default=3)
    p.add_argument('--output', type=Path, required=True, help='New local report directory')
    args = p.parse_args()
    if not 1 <= args.count <= 100:
        p.error('count must be 1..100')
    if args.output.exists():
        p.error('Output directory already exists')
    args.output.mkdir(parents=True)
    report = {'success': False, 'checks': [], 'unsupported': []}

    def save():
        temporary = args.output / 'report.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(args.output / 'report.json')

    def record(name, **details):
        report['checks'].append(dict(name=name, **details))
        save()
        print(name, details, flush=True)

    try:
        with gpib.ResourceManager() as rm:
            inst = rm.open_resource(args.resource, timeout=10000)
            identity = inst.query('*IDN?')
            if len(identity.split(',')) < 2 or identity.split(',')[1].strip().upper() != 'MODEL 2400':
                raise ValueError('Selected instrument is not a Model 2400')
            if inst.query(':OUTP?') != '0':
                raise ValueError('Output must be off for transport fault tests')
            report['identity'] = identity
            if args.binary:
                binary_check(inst, record, args.output)
            if args.recovery:
                recovery_check(inst, record, args.count)
            if args.no_eoi or args.large_write:
                supported = no_eoi_check(inst, record)
                if not supported:
                    report['unsupported'].append('No-EOI write acknowledgement / large multi-chunk writes')
                if args.large_write:
                    large_write_check(inst, record, supported)
            if inst.query(':OUTP?') != '0':
                raise ValueError('Output changed during transport checks')
            record('final_output', state='off')
            report['success'] = not report['unsupported']
    except BaseException as exc:
        report.update(error=f'{type(exc).__name__}: {exc}', success=False)
    finally:
        save()
    print('success:', report['success'], flush=True)
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
