"""Finite or timed four-wire Source-I / Measure-V transport acceptance.

Resets/configures the confirmed 2400 and applies the requested current. Confirm
the sample's limits first. Each finite READ? uses instrument-side automatic
output-off; communication failure stops the run and never replays a measurement.
Detailed data and identifiers belong in ignored local storage.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

from gpib_macarm import ResourceManager

BAD_STATUS = (1 << 0) | (1 << 3) | (1 << 4) | (1 << 16) | (1 << 18)
REQUIRED_STATUS = (1 << 22) | (1 << 15) | (1 << 11)


def parse_readings(reply, points, current, compliance):
    values = [float(v) for v in reply.split(',')]
    if len(values) != points * 4:
        raise ValueError(f'Expected {points * 4} fields, received {len(values)}')
    rows = []
    for start in range(0, len(values), 4):
        voltage, source, timestamp, status = values[start:start + 4]
        if not all(math.isfinite(v) and abs(v) < 1e30 for v in (voltage, source, timestamp, status)):
            raise ValueError('Nonfinite, overflow or unavailable reading')
        if status != int(status) or int(status) & BAD_STATUS or int(status) & REQUIRED_STATUS != REQUIRED_STATUS:
            raise ValueError(f'Invalid four-wire/source-I/measure-V status: {status}')
        if not math.isclose(source, current, rel_tol=1e-5, abs_tol=1e-12):
            raise ValueError('Programmed source-current readback mismatch')
        if abs(voltage) >= .95 * compliance:
            raise ValueError('Voltage is near compliance; stop and review the sample/setup')
        if rows and timestamp < rows[-1]['instrument_time_s']:
            raise ValueError('Instrument timestamps moved backwards')
        rows.append(dict(measured_voltage_v=voltage, programmed_current_a=source,
                         instrument_time_s=timestamp, status=int(status)))
    return rows


def shutdown(inst):
    result = {'output_off_confirmed': False, 'errors': []}
    for command in (':OUTP OFF', ':ABOR', ':SOUR:CURR:LEV 0'):
        try:
            inst.write(command)
        except Exception as exc:
            result['errors'].append(f'{command}: {type(exc).__name__}: {exc}')
    try:
        result['output_off_confirmed'] = inst.query(':OUTP?') == '0'
    except Exception as exc:
        result['errors'].append(f'Output verification: {type(exc).__name__}: {exc}')
    result['manual_output_check_required'] = not result['output_off_confirmed']
    return result


def acquire(inst, args, report, save):
    identity = inst.query('*IDN?')
    if len(identity.split(',')) < 2 or identity.split(',')[1].strip().upper() != 'MODEL 2400':
        raise ValueError('This tool requires a confirmed Model 2400')
    if inst.query(':OUTP?') != '0':
        raise ValueError('Output must be off before starting this acceptance test')
    report['identity'] = identity
    # Preserve existing buffer data before the explicitly requested reset.
    count = int(inst.query(':TRAC:POIN:ACT?'))
    if count:
        previous_format = inst.query(':FORM:DATA?')
        inst.write(':FORM:DATA ASC')
        try:
            previous = inst.query(':TRAC:DATA?')
            args.output.with_suffix('.previous-buffer.txt').write_text(previous + '\n')
        finally:
            inst.write(':FORM:DATA ' + previous_format)
    inst.write('*RST')
    inst.write('*CLS')
    time.sleep(.5)
    commands = [':SOUR:FUNC CURR', ':SOUR:CURR:MODE FIX',
                f':SOUR:CURR:RANG {abs(args.current):.12g}', f':SOUR:CURR:LEV {args.current:.12g}',
                ':SENS:FUNC:CONC OFF', ':SENS:FUNC "VOLT"',
                f':SENS:VOLT:PROT {args.compliance:.12g}', ':SENS:VOLT:RANG:AUTO ON',
                f':SENS:VOLT:NPLC {args.nplc:.12g}', ':SYST:RSEN ON', ':SYST:AZER:STAT ON',
                ':SENS:AVER:STAT OFF', ':FORM:DATA ASC', ':FORM:ELEM VOLT,CURR,TIME,STAT',
                ':ARM:SOUR IMM', ':ARM:COUN 1', ':TRIG:SOUR IMM', f':TRIG:COUN {args.points}',
                f':SOUR:DEL {args.delay:.12g}', ':TRAC:FEED:CONT NEV', ':TRAC:CLE',
                ':TRAC:POIN 2500', ':TRAC:FEED SENS', ':TRAC:FEED:CONT NEXT',
                ':SOUR:CLE:AUTO:MODE TCO', ':SOUR:CLE:AUTO ON']
    for command in commands:
        inst.write(command)
    keys = (':SOUR:FUNC?', ':SOUR:CURR?', ':SENS:FUNC?', ':SENS:VOLT:PROT?', ':SYST:RSEN?',
            ':SOUR:CLE:AUTO?', ':SOUR:CLE:AUTO:MODE?', ':TRIG:COUN?', ':OUTP?')
    config = {key: inst.query(key) for key in keys}
    report['configuration'] = config
    if (config[':SOUR:FUNC?'] != 'CURR' or 'VOLT' not in config[':SENS:FUNC?']
            or config[':SYST:RSEN?'] != '1' or config[':OUTP?'] != '0'
            or config[':SOUR:CLE:AUTO?'] != '1' or not config[':SOUR:CLE:AUTO:MODE?'].startswith('TCO')
            or not math.isclose(float(config[':SOUR:CURR?']), args.current, rel_tol=1e-5)
            or not math.isclose(float(config[':SENS:VOLT:PROT?']), args.compliance, rel_tol=1e-5)
            or int(config[':TRIG:COUN?']) != args.points):
        raise ValueError('Configuration or automatic output-off verification failed')
    error = inst.query(':SYST:ERR?')
    if not error.startswith('0,'):
        raise ValueError('SCPI configuration error: ' + error)
    report.update(samples=0, batches=0, max_reply_bytes=0, elapsed_seconds=0)
    start = time.monotonic()
    last_timestamp = None
    with args.output.with_suffix('.csv').open('x', newline='') as csv_file, \
            args.output.with_suffix('.raw.txt').open('x') as raw_file:
        writer = csv.DictWriter(csv_file, fieldnames=['sample', 'measured_voltage_v',
                                'programmed_current_a', 'instrument_time_s', 'status'])
        writer.writeheader()
        while True:
            # Automatic source clear enables output only for this finite batch.
            reply = inst.query(':READ?')
            raw_file.write(reply + '\n'); raw_file.flush()
            if inst.query(':OUTP?') != '0':
                raise ValueError('Instrument did not turn output off after the batch')
            rows = parse_readings(reply, args.points, args.current, args.compliance)
            if last_timestamp is not None and rows[0]['instrument_time_s'] < last_timestamp:
                raise ValueError('Instrument timestamp moved backwards between batches')
            last_timestamp = rows[-1]['instrument_time_s']
            for row in rows:
                report['samples'] += 1
                writer.writerow(dict(sample=report['samples'], **row))
            csv_file.flush()
            report['batches'] += 1
            report['max_reply_bytes'] = max(report['max_reply_bytes'], len(reply.encode('ascii')) + 1)
            report['elapsed_seconds'] = time.monotonic() - start
            if inst.query('*IDN?') != identity:
                raise ValueError('Identity/reply boundary changed during acquisition')
            if report['batches'] == 1 or report['batches'] % 100 == 0:
                print(f"{report['samples']} samples, {report['elapsed_seconds']:.1f} s; output off", flush=True)
            save()
            if report['elapsed_seconds'] >= args.seconds:
                break
    if not inst.query(':SYST:ERR?').startswith('0,'):
        raise ValueError('Instrument reported a measurement error')
    report['buffer_points'] = int(inst.query(':TRAC:POIN:ACT?'))
    report['success'] = True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--resource', required=True)
    p.add_argument('--current', type=float, default=2.5e-6, help='A; confirm sample limits')
    p.add_argument('--compliance', type=float, default=21, help='V; confirm sample limits')
    p.add_argument('--nplc', type=float, default=5)
    p.add_argument('--delay', type=float, default=.05)
    p.add_argument('--points', type=int, default=1, help='Finite readings per batch, 1..2500')
    p.add_argument('--seconds', type=float, default=0, help='Repeat complete batches for this duration')
    p.add_argument('--timeout', type=int, default=60000, help='Per-transfer milliseconds')
    p.add_argument('--output', type=Path, required=True, help='New local output prefix')
    args = p.parse_args()
    if (not all(math.isfinite(v) for v in (args.current, args.compliance, args.nplc, args.delay, args.seconds))
            or not 0 < abs(args.current) <= .01 or not 0 < args.compliance <= 21
            or not .01 <= args.nplc <= 10 or not 0 <= args.delay <= 10
            or not 1 <= args.points <= 2500 or not 0 <= args.seconds <= 86400
            or not 10000 <= args.timeout <= 1000000):
        p.error('Invalid current/compliance, timing, point count or timeout')
    suffixes = ('.json', '.csv', '.raw.txt', '.previous-buffer.txt')
    if any(args.output.with_suffix(s).exists() for s in suffixes):
        p.error('Output prefix already exists')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(success=False, started_utc=datetime.now(timezone.utc).isoformat(),
                  parameters={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()})

    def save():
        temporary = args.output.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(args.output.with_suffix('.json'))

    try:
        with ResourceManager() as rm:
            inst = rm.open_resource(args.resource, timeout=args.timeout)
            # Model and output preflight happen before any cleanup/configuration.
            identity = inst.query('*IDN?')
            if len(identity.split(',')) < 2 or identity.split(',')[1].strip().upper() != 'MODEL 2400':
                raise ValueError('Selected instrument is not a Model 2400')
            if inst.query(':OUTP?') != '0':
                raise ValueError('Output must be off before this test')
            try:
                acquire(inst, args, report, save)
            finally:
                report['cleanup'] = shutdown(inst)
                if not report['cleanup']['output_off_confirmed'] or report['cleanup']['errors']:
                    report['success'] = False
    except BaseException as exc:
        report.update(success=False, error=f'{type(exc).__name__}: {exc}')
    finally:
        save()
    print(json.dumps({k: report[k] for k in ('success', 'samples', 'elapsed_seconds', 'cleanup', 'error') if k in report}, indent=2))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
