"""Simple CSV logger. Check query syntax against your instrument manual first."""
import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import time

from gpib_macarm import ResourceManager

p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--resource",required=True,help="e.g. GPIB0::22::INSTR")
p.add_argument("--query",required=True,help="a read-only measurement query from the instrument manual")
p.add_argument("--count",type=int,default=100)
p.add_argument("--interval",type=float,default=1.0)
p.add_argument("--output",type=Path,default=Path("readings.csv"))
args=p.parse_args()
if args.count<1 or args.interval<0:
    p.error("count must be positive and interval nonnegative")
with ResourceManager() as rm, args.output.open("x",newline="",encoding="utf-8") as output:
    meter=rm.open_resource(args.resource,timeout=10000)
    writer=csv.writer(output)
    writer.writerow(["timestamp_utc","value"])
    for _ in range(args.count):
        value=meter.query(args.query)
        writer.writerow([datetime.now(timezone.utc).isoformat(),value])
        output.flush()
        time.sleep(args.interval)
