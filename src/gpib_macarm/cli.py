import argparse
from dataclasses import asdict
import json
import platform
import sys

from . import Controller, GpibError, __version__, list_adapters
from ._backend import NativeBackend


def main(argv=None):
    p = argparse.ArgumentParser(prog="gpib-macarm", description="Standalone NI USB-GPIB diagnostics")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("info", help="Load native library and show architecture; no GPIB commands")
    sub.add_parser("list", help="List USB adapters as JSON; no GPIB address scan")
    q = sub.add_parser("query", help="Open adapter (REN/IFC), then send a SCPI query")
    q.add_argument("command", nargs="?", default="*IDN?")
    q.add_argument("--address", type=int, required=True)
    q.add_argument("--index", type=int, default=0)
    q.add_argument("--serial")
    q.add_argument("--timeout", type=int, default=3000, help="milliseconds")
    q.add_argument("--write-term", choices=["none", "lf", "cr", "crlf"], default="lf")
    q.add_argument("--read-term", choices=["none", "lf", "cr", "crlf"], default="lf")
    args = p.parse_args(argv)
    try:
        if args.action == "info":
            backend = NativeBackend()
            print(json.dumps(dict(version=__version__, platform=platform.platform(),
                machine=platform.machine(), python=sys.version, native_library=str(backend.path)), indent=2))
        elif args.action == "list":
            print(json.dumps([asdict(a) for a in list_adapters()], indent=2))
        else:
            terms = {"none":None, "lf":"\n", "cr":"\r", "crlf":"\r\n"}
            with Controller(args.index, serial=args.serial, timeout=args.timeout) as bus:
                with bus.open_instrument(args.address, timeout=args.timeout,
                        write_termination=terms[args.write_term], read_termination=terms[args.read_term]) as inst:
                    print(inst.query(args.command))
        return 0
    except (GpibError, ValueError, UnicodeError) as exc:
        print(f"gpib-macarm: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
