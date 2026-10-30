"""Explicit opt-in SCPI smoke test. Opening initializes REN/IFC; no *RST is sent."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import platform
import statistics
import sys
import time

from gpib_macarm import Controller, __version__, list_adapters


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--address",type=int,required=True)
    p.add_argument("--index",type=int,default=0)
    p.add_argument("--serial")
    p.add_argument("--timeout",type=int,default=5000)
    p.add_argument("--count",type=int,default=100)
    p.add_argument("--command",default="*IDN?",help="Use a query with no side effects")
    p.add_argument("--read-term",choices=["none","lf","cr","crlf"],default="lf")
    p.add_argument("--write-term",choices=["none","lf","cr","crlf"],default="lf")
    p.add_argument("--output",type=Path,default=Path("hardware-smoke.json"))
    args=p.parse_args()
    if not 1<=args.count<=100000:
        p.error("count must be 1..100000")
    report=dict(version=__version__,python=sys.version,platform=platform.platform(),
                machine=platform.machine(),adapters=[asdict(a) for a in list_adapters()],
                settings={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},results=[])
    terms={"none":None,"lf":"\n","cr":"\r","crlf":"\r\n"}
    exit_code=0
    try:
        with Controller(args.index,serial=args.serial,timeout=args.timeout) as bus:
            inst=bus.open_instrument(args.address,timeout=args.timeout,
                read_termination=terms[args.read_term],write_termination=terms[args.write_term])
            for i in range(args.count):
                start=time.perf_counter()
                reply=inst.query(args.command)
                elapsed=time.perf_counter()-start
                if not reply:
                    raise RuntimeError("Empty reply")
                report["results"].append(dict(iteration=i+1,reply=reply,seconds=elapsed))
                print(f"{i+1}/{args.count} {elapsed*1000:.1f} ms {reply}")
    except Exception as exc:
        exit_code=1
        report["error"]=f"{type(exc).__name__}: {exc}"
        print(report["error"],file=sys.stderr)
    values=[r["seconds"] for r in report["results"]]
    report["success"]=(exit_code==0 and len(values)==args.count)
    if values:
        report["timing_seconds"]={"min":min(values),"mean":statistics.mean(values),"max":max(values)}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return exit_code


if __name__=="__main__":
    raise SystemExit(main())
