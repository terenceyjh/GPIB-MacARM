"""Bounded four-wire current sweep for a passive, low-resistance test sample.

Uses the current-source / voltage-measure commands in measure_tcr_v6.py.
Resets the selected 2400 and enables its output during the finite sweep.
The returned CURR field is the programmed source current, not a second meter.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import time

from gpib_macarm import ResourceManager

BAD_STATUS = (1 << 0) | (1 << 3) | (1 << 4) | (1 << 16) | (1 << 18)
FOUR_WIRE = 1 << 22
REQUIRED_STATUS = FOUR_WIRE | (1 << 15) | (1 << 11)  # remote sense, source I, measure V


def parse_sweep(reply, start, stop, points, compliance):
    values = [float(item) for item in reply.strip().split(",")]
    if len(values) != points * 4:
        raise ValueError(f"Expected {points * 4} fields, received {len(values)}")
    rows = []
    for index in range(points):
        voltage, current, timestamp, status_value = values[index * 4:index * 4 + 4]
        if not all(math.isfinite(v) and abs(v) < 1e30 for v in (voltage, current, timestamp, status_value)):
            raise ValueError(f"Invalid/overflow reading at point {index + 1}")
        status = int(status_value)
        if status != status_value or status & BAD_STATUS or status & REQUIRED_STATUS != REQUIRED_STATUS:
            raise ValueError(f"Invalid measurement status at point {index + 1}: {status}")
        expected = start + (stop - start) * index / (points - 1)
        if not math.isclose(current, expected, rel_tol=1e-5, abs_tol=1e-10):
            raise ValueError(f"Source-current mismatch at point {index + 1}: {current} vs {expected}")
        if abs(voltage) >= 0.95 * compliance:
            raise ValueError(f"Voltage near compliance at point {index + 1}: {voltage} V")
        if rows and timestamp < rows[-1]["instrument_time_s"]:
            raise ValueError("Non-monotonic instrument timestamps")
        rows.append(dict(point=index + 1, source_current_a=current, measured_voltage_v=voltage,
                         instrument_time_s=timestamp, status=status))
    return rows


def fit_rows(rows):
    xs = [r["source_current_a"] for r in rows]
    ys = [r["measured_voltage_v"] for r in rows]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    offset = my - slope * mx
    residuals = [y - (slope * x + offset) for x, y in zip(xs, ys)]
    sse = sum(r * r for r in residuals)
    syy = sum((y - my) ** 2 for y in ys)
    return dict(resistance_ohm=slope, offset_v=offset,
                r_squared=1 - sse / syy if syy else None,
                residual_rms_v=math.sqrt(sse / len(rows)),
                slope_standard_error_ohm=math.sqrt(sse / (len(rows) - 2) / sxx),
                min_voltage_v=min(ys), max_voltage_v=max(ys))


def error_queue(inst):
    errors = []
    for _ in range(16):
        reply = inst.query(":SYST:ERR?")
        errors.append(reply)
        if int(reply.split(",")[0]) == 0:
            return errors
    raise RuntimeError("Instrument error queue did not empty")


def safe_shutdown(inst):
    errors = []
    output = None
    for command in (":OUTP OFF", ":ABOR", ":SOUR:CURR:MODE FIX", ":SOUR:CURR:LEV 0"):
        try:
            inst.write(command)
        except Exception as exc:
            errors.append(f"{command}: {type(exc).__name__}: {exc}")
    try:
        output = inst.query(":OUTP?")
    except Exception as exc:
        errors.append(f"output verification: {type(exc).__name__}: {exc}")
    return dict(output=output, errors=errors, output_off_confirmed=output == "0",
                manual_output_off_required=output != "0")


def acquire(inst, args, report):
    report["identity"] = inst.query("*IDN?")
    if "MODEL 2400," not in report["identity"]:
        raise RuntimeError("Selected instrument is not a Model 2400")
    report["initial_errors"] = error_queue(inst)
    inst.write(":OUTP OFF")
    inst.write("*RST")
    inst.write("*CLS")
    time.sleep(0.5)
    start, stop = (-args.max_current, args.max_current)
    if args.reverse:
        start, stop = stop, start
    step = (stop - start) / (args.points - 1)
    commands = [
        ":SOUR:FUNC CURR", ":SOUR:CURR:MODE FIX",
        f":SOUR:CURR:RANG {args.max_current:.12g}", ":SOUR:CURR:LEV 0",
        ":SENS:FUNC:CONC OFF", ':SENS:FUNC "VOLT"',
        ":SENS:VOLT:RANG:AUTO OFF", ":SENS:VOLT:RANG 0.2",
        f":SENS:VOLT:PROT {args.compliance:.12g}", f":SENS:VOLT:NPLC {args.nplc:.12g}",
        ":SYST:RSEN ON", ":SYST:AZER:STAT ON", ":SENS:AVER:STAT OFF",
        ":FORM:DATA ASC", ":FORM:ELEM VOLT,CURR,TIME,STAT",
        ":ARM:SOUR IMM", ":ARM:COUN 1", ":TRIG:SOUR IMM",
        f":TRIG:COUN {args.points}", f":SOUR:DEL {args.delay:.12g}",
        ":SOUR:SWE:SPAC LIN", ":SOUR:SWE:RANG FIX",
        f":SOUR:CURR:STAR {start:.12g}", f":SOUR:CURR:STOP {stop:.12g}",
        f":SOUR:CURR:STEP {step:.12g}", ":SOUR:CURR:MODE SWE",
        ":SOUR:CLE:AUTO:MODE TCO", ":SOUR:CLE:AUTO ON",
    ]
    report["configuration_commands"] = commands
    for command in commands:
        inst.write(command)
    report["configuration"] = {command: inst.query(command) for command in (
        ":SYST:RSEN?", ":SOUR:FUNC?", ":SOUR:CURR:MODE?", ":SOUR:CURR:RANG?",
        ":SENS:FUNC?", ":SENS:VOLT:RANG?", ":SENS:VOLT:PROT?", ":SENS:VOLT:NPLC?",
        ":TRIG:COUN?", ":SOUR:CURR:STAR?", ":SOUR:CURR:STOP?", ":SOUR:CURR:STEP?",
        ":SOUR:CLE:AUTO?", ":SOUR:CLE:AUTO:MODE?", ":OUTP?", ":SYST:LFR?")}
    errors = error_queue(inst)
    report["configuration_errors"] = errors
    if len(errors) != 1:
        raise RuntimeError(f"SCPI configuration failed: {errors}")
    if report["configuration"][":SYST:RSEN?"] != "1":
        raise RuntimeError("Four-wire sense was not enabled")
    config = report["configuration"]
    for query, expected in ((":SENS:VOLT:PROT?", args.compliance), (":TRIG:COUN?", args.points),
                            (":SOUR:CURR:STAR?", start), (":SOUR:CURR:STOP?", stop),
                            (":SOUR:CURR:STEP?", step)):
        if not math.isclose(float(config[query]), expected, rel_tol=1e-5, abs_tol=1e-12):
            raise RuntimeError(f"Configuration readback mismatch: {query} = {config[query]}")
    if config[":SOUR:CLE:AUTO?"] != "1" or not config[":SOUR:CLE:AUTO:MODE?"].startswith("TCO"):
        raise RuntimeError("Automatic output-off after trigger count was not enabled")
    if config[":OUTP?"] != "0":
        raise RuntimeError("Output unexpectedly enabled before the sweep")
    print(f"Starting {args.points}-point sweep, {start:g} to {stop:g} A, "
          f"V compliance {args.compliance:g} V, timeout {args.timeout} ms", flush=True)
    begin = time.perf_counter()
    reply = inst.query(":READ?")
    report["query_seconds"] = time.perf_counter() - begin
    report["reply_bytes_without_lf"] = len(reply.encode("ascii"))
    args.output.with_suffix(".raw.txt").write_text(reply + "\n")
    report["automatic_output_after_sweep"] = inst.query(":OUTP?")
    if report["automatic_output_after_sweep"] != "0":
        raise RuntimeError("Instrument auto output-off did not turn output off")
    rows = parse_sweep(reply, start, stop, args.points, args.compliance)
    with args.output.with_suffix(".csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report["points_received"] = len(rows)
    report["statuses"] = sorted({row["status"] for row in rows})
    report["fit"] = fit_rows(rows)
    fit = report["fit"]
    warnings = []
    if fit["r_squared"] is None or fit["r_squared"] < 0.99:
        warnings.append("Low linearity: do not interpret the slope as a validated sample resistance")
    if fit["resistance_ohm"] < 0:
        warnings.append("Negative slope: check sense polarity, electrode geometry and thermal drift")
    report["quality_warnings"] = warnings
    report["post_sweep_errors"] = error_queue(inst)
    if len(report["post_sweep_errors"]) != 1:
        raise RuntimeError(f"SCPI measurement errors: {report['post_sweep_errors']}")
    report["communication_after_sweep"] = inst.query("*IDN?") == report["identity"]
    if not report["communication_after_sweep"]:
        raise RuntimeError("Identity changed after the sweep")
    report["success"] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource", required=True)
    parser.add_argument("--max-current", type=float, default=0.001)
    parser.add_argument("--points", type=int, default=21)
    parser.add_argument("--nplc", type=float, default=1)
    parser.add_argument("--delay", type=float, default=0.05)
    parser.add_argument("--compliance", type=float, default=0.1)
    parser.add_argument("--timeout", type=int, default=60000)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--output", type=Path, required=True, help="New output prefix; writes JSON, CSV and raw reply")
    args = parser.parse_args()
    if not math.isfinite(args.max_current) or not 0 < args.max_current <= 0.01:
        parser.error("This low-current test requires max-current in (0, 0.01] A")
    if not math.isfinite(args.compliance) or not 0 < args.compliance <= 0.1:
        parser.error("This test requires compliance in (0, 0.1] V")
    if not 3 <= args.points <= 101 or not math.isfinite(args.nplc) or not 0.01 <= args.nplc <= 5:
        parser.error("points must be 3..101 and nplc 0.01..5")
    if not math.isfinite(args.delay) or not 0 <= args.delay <= 1 or args.timeout < 10000:
        parser.error("delay must be 0..1 seconds; timeout must be at least 10000 ms")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if any(args.output.with_suffix(suffix).exists() for suffix in (".json", ".csv", ".raw.txt")):
        parser.error("Output prefix already exists; choose a new prefix")
    report = dict(started_utc=datetime.now(timezone.utc).isoformat(), success=False,
                  settings={key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
                  current_field="programmed source current; voltage independently measured", cleanup=None)
    exit_code = 0
    try:
        with ResourceManager() as rm:
            inst = rm.open_resource(args.resource, timeout=args.timeout,
                                    write_termination="\n", read_termination="\n", send_end=True)
            try:
                acquire(inst, args, report)
            finally:
                report["cleanup"] = safe_shutdown(inst)
                if not report["cleanup"]["output_off_confirmed"] or report["cleanup"]["errors"]:
                    report["success"] = False
                    exit_code = 1
    except Exception as exc:
        report["success"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        exit_code = 1
    finally:
        args.output.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({key: report[key] for key in ("success", "cleanup", "fit", "quality_warnings", "query_seconds", "error") if key in report},
                     indent=2), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
