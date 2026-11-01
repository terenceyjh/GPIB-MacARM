"""Concurrent queries to confirmed, distinct instruments on one GPIB adapter.

Defaults to *IDN? only. Measurement queries require separate authorization for
their instrument settings/output; this tool does not configure them. One shared
manager holds each complete query transaction. Any failure stops all workers.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import re
import threading
import time

from gpib_macarm import ResourceManager


def run_queries(instances, queries, count=100, seconds=0, numeric=False, results=None):
    """Use existing sessions so the coordinator retains ONE physical controller."""
    if len(instances) != len(queries) or not instances:
        raise ValueError('Each instrument needs one query')
    if count < 1 or not math.isfinite(seconds) or seconds < 0:
        raise ValueError('Invalid query count or duration')
    results = [] if results is None else results
    stop = threading.Event()
    sessions = []
    for inst, query in zip(instances, queries):
        resource = inst.resource_name
        identity = inst.query('*IDN?')
        baseline = inst.query(query)
        fields = len(baseline.split(','))
        if numeric and not all(math.isfinite(float(v)) for v in baseline.split(',')):
            raise ValueError('Initial numeric reply is invalid')
        entry = dict(resource=resource, identity=identity, query=query, queries=0,
                     expected_fields=fields, seconds=0)
        results.append(entry)
        sessions.append((inst, baseline, entry))

    def worker(session):
        inst, baseline, entry = session
        start = time.monotonic()
        try:
            while not stop.is_set():
                reply = inst.query(entry['query'])
                if numeric:
                    values = [float(v) for v in reply.split(',')]
                    if len(values) != entry['expected_fields'] or not all(map(math.isfinite, values)):
                        raise ValueError('Numeric reply shape/value mismatch')
                elif reply != baseline:
                    raise ValueError('Reply changed or crossed instrument boundaries')
                entry['queries'] += 1
                entry['seconds'] = time.monotonic() - start
                if entry['queries'] >= count and entry['seconds'] >= seconds:
                    break
            if not stop.is_set() and inst.query('*IDN?') != entry['identity']:
                raise ValueError('Final identity mismatch')
        except BaseException:
            stop.set()
            raise

    with ThreadPoolExecutor(max_workers=len(sessions)) as pool:
        for future in [pool.submit(worker, s) for s in sessions]:
            future.result()
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--resource', action='append', required=True, help='Repeat for each confirmed instrument')
    p.add_argument('--query', action='append', help='One common query, or one per resource; default *IDN?')
    p.add_argument('--numeric', action='store_true', help='Require finite numeric replies with a stable field count')
    p.add_argument('--count', type=int, default=100)
    p.add_argument('--seconds', type=float, default=0)
    p.add_argument('--timeout', type=int, default=10000)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    addresses = []
    for resource in args.resource:
        match = re.fullmatch(r'GPIB(\d+)::(\d+)::INSTR', resource, re.I)
        if not match or not 1 <= int(match[2]) <= 30:
            p.error('Use confirmed GPIB<adapter>::<address 1..30>::INSTR resources')
        addresses.append(tuple(map(int, match.groups())))
    if len(addresses) < 2 or len(set(addresses)) != len(addresses) or len({a[0] for a in addresses}) != 1:
        p.error('At least two distinct instrument addresses on the same adapter are required')
    queries = args.query or ['*IDN?']
    if len(queries) == 1:
        queries = queries * len(addresses)
    if len(queries) != len(addresses) or any(not q.endswith('?') or any(c in q for c in ';\r\n') for q in queries):
        p.error('Supply one query or one per resource; compound messages are not supported here')
    if (not 1 <= args.count <= 100000 or not math.isfinite(args.seconds)
            or not 0 <= args.seconds <= 86400 or not 100 <= args.timeout <= 1000000):
        p.error('Invalid count, duration or timeout')
    if args.output.exists():
        p.error('Output file already exists')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'success': False, 'instruments': []}
    try:
        with ResourceManager() as rm:
            instances = [rm.open_resource(resource, timeout=args.timeout, query_delay=.005)
                         for resource in args.resource]
            run_queries(instances, queries, args.count, args.seconds, args.numeric,
                        report['instruments'])
            report['success'] = True
    except BaseException as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'success': report['success'], 'queries': [r['queries'] for r in report['instruments']],
                      'error': report.get('error')}, indent=2))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
