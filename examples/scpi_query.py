"""python examples/scpi_query.py --address 22 --command '*IDN?'"""
import argparse
import gpib_macarm as visa

p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--address",type=int,required=True)
p.add_argument("--index",type=int,default=0)
p.add_argument("--serial")
p.add_argument("--command",default="*IDN?")
args=p.parse_args()
with visa.ResourceManager() as rm:
    with rm.open_resource(f"GPIB{args.index}::{args.address}::INSTR",
                          serial=args.serial,timeout=5000) as inst:
        print(inst.query(args.command))
