# GPIB-MacARM

**Python GPIB communication for Apple Silicon Macs.**

[中文说明](README.zh-CN.md) · [Mac acceptance checklist](docs/MAC_ACCEPTANCE.md) · [Development handoff and prompts](CLAUDE.md)

GPIB-MacARM is a standalone, userspace transport for controlling GPIB instruments from Python through an NI GPIB-USB-HS adapter. It extracts the NI USB-GPIB core from **[KAME](https://github.com/northriv/KAME)**, whose userspace port is based on **[linux-gpib](https://linux-gpib.sourceforge.io/)**, and adds a small native C ABI and a VISA-like Python interface.

Python → ctypes → GPIB-MacARM C ABI → [KAME](https://github.com/northriv/KAME)/[linux-gpib](https://linux-gpib.sourceforge.io/) driver → libusb → NI adapter → instrument

No NI-488.2, NI-VISA, Qt, complete [KAME](https://github.com/northriv/KAME) installation, kernel module, or background server is required. The package name is `gpib-macarm`; the import name is `gpib_macarm`.

## Status

**SCPI communication with a Keithley 2400 SourceMeter has passed real-hardware testing.** On macOS 14.8.9 arm64 / Python 3.11.6, the connected GPIB-USB-HS (`3923:709b`) successfully sent configuration commands, read their settings back, completed 100 consecutive identity queries, and acquired four-wire current sweeps including replies larger than 4096 bytes. Version 0.1.0 remains early development; reliable recovery after a communication timeout is unfinished.

The shared POSIX implementation has been compiled and installed on Linux x86_64 and macOS arm64 (editable install). The completed checks are recorded below; full environments, commands and remaining limits are in the [validation record](docs/VALIDATION.md).

## Validation record

| Date | Environment | Verified results |
| --- | --- | --- |
| 2026-10-30 | Windows / Python 3.14 | Python API offline tests passed; native tests were skipped on this platform. |
| 2026-10-30 | WSL2 Linux x86_64 / Python 3.10.12 / GCC 11.4 | Native build/load, all 30 offline tests, ASan/UBSan checks, and clean wheel/source-archive installation passed. |
| 2026-10-31 | macOS 14.8.9 arm64 / Python 3.11.6 / Apple Clang 15.0.0 / libusb 1.0.30 | Editable build/install, native loading, both `info` entry points, all 30 offline tests with zero skips, and ASan/UBSan checks passed. |
| 2026-10-31 | Same Mac, connected GPIB-USB-HS + Keithley 2400 at address 24 | 100 consecutive identical identity replies, fragmented text/raw reads and read-only SCPI queries passed after parser fixes; all 34 offline tests passed without skips. |
| 2026-10-31 | Same hardware, low-resistance copper plate | Four-wire ±1 mA / 21-point and ±10 mA / 101-point forward/reverse current sweeps, 5655-byte replies and output-off checks passed; all 39 offline tests passed. Resistance accuracy remains unvalidated. |
| 2026-10-31 | Same Mac, fresh Python 3.11.6 venv | Non-editable `pip install .`, import/native loading outside the source directory, CLI `info`, `pip check` and all 39 offline tests passed. |

The latest Mac test run includes 22 Python API tests, 2 distribution/provenance tests, 10 native parser/C ABI tests and 5 sweep-data/shutdown tests. Mac sanitizer checks also cover compact/full reply fixtures, truncations and 20,000 malformed packets. The earlier Linux results apply to the earlier revision; the hardware fixes have not been rerun on Linux.

**Hardware acceptance remains limited.** Keep `send_end=True`; the 10000 ms identity-query timeout is insufficient for longer sweeps. The 101-point NPLC 5 sweep took 35.7 s and used 60000 ms. LF-only writes without EOI and recovery after deliberately unanswered reads failed, including immediate reopen attempts. Finite current sweeps and 5655-byte replies passed, with output off confirmed after each run, but nonlinear/negative-slope copper curves do not validate resistance accuracy. TCR, voltage-source IV, larger/binary replies, long-term acquisition, unplug/power-loss recovery, Intel Mac and cross-machine deployment remain unvalidated. See the [validation record](docs/VALIDATION.md) and [Mac acceptance checklist](docs/MAC_ACCEPTANCE.md).

## What it provides

- `ResourceManager`, `open_resource`, `write`, `read`, and `query` for familiar SCPI scripts.
- Binary-safe `write_raw`, `read_raw`, and `read_bytes`.
- EOI/EOS handling, configurable text terminators, and reads that continue until message completion.
- Per-resource timeouts, a complete-query lock shared by instruments on one controller, and context-managed sessions.
- Selected device clear, serial poll/status-byte reads, IFC, REN, and SRQ-line checks.
- USB enumeration, a diagnostic CLI, examples, and a hardware smoke-test script.

This is a **limited VISA-like API**, not a PyVISA backend or a replacement for every VISA feature. TCP/IP and USBTMC resources, secondary GPIB addressing, VISA events, controller handover, and firmware loading are outside its current scope.

## Install from source on a Mac

### 1. Prepare the build tools

You need Python 3.10+, Xcode Command Line Tools, libusb, pkg-config and Git. With [Homebrew](https://brew.sh/) installed:

```bash
xcode-select --install  # skip if Command Line Tools are installed
brew install python libusb pkg-config
```

Use Python and libusb of the same architecture. On Apple Silicon these should be arm64, normally with Homebrew under `/opt/homebrew`; avoid a Rosetta x86_64 Python with arm64 libraries. Check before creating the environment:

```bash
uname -m
python3 -c "import platform, sys; print(platform.machine()); print(sys.executable)"
brew --prefix
pkg-config --modversion libusb-1.0
```

If `python3` resolves to a different architecture, select the matching Homebrew Python explicitly when creating the environment, for example `/opt/homebrew/bin/python3 -m venv .venv` on Apple Silicon. Intel Mac builds are not yet validated.

### 2. Clone and install

```bash
git clone https://github.com/terenceyjh/GPIB-MacARM.git
cd GPIB-MacARM
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
python -m gpib_macarm info
python -m pip check
```

`info` must load the native library and report version/platform/library path; it does not access an instrument. The equivalent CLI is `gpib-macarm info`. In a new terminal, return to the repository and run `source .venv/bin/activate` before using these commands, or call `.venv/bin/python` directly.

The native library is built locally from the bundled C/C++ sources. It uses GNU C11 and GNU C++17, links libusb/pthread, and is loaded with Python's standard-library `ctypes`. No pybind11 or Python C API binding is needed. Building does not fetch [KAME](https://github.com/northriv/KAME)/[linux-gpib](https://linux-gpib.sourceforge.io/); pip may fetch its Python build dependencies. The package has **not been published to PyPI**.

To develop in this checkout, use `python -m pip install -e .` instead. After changing C/C++ or vendor files, force a rebuild:

```bash
python -m pip install --no-cache-dir --force-reinstall --no-deps -e .
python -m gpib_macarm info
python -m unittest discover -s tests -v
```

When updating an ordinary non-editable installation, rerun `python -m pip install --no-cache-dir --force-reinstall --no-deps .` after pulling changes. Do not copy a built `.dylib` or an entire venv from another machine.

MacPorts `/opt/local` is also recognized. For another prefix:

```bash
LIBUSB_INCLUDE_DIR=/your/prefix/include \
LIBUSB_LIBRARY_DIR=/your/prefix/lib \
python -m pip install --no-cache-dir .
```

Linux development builds use the same POSIX path and require a C/C++ toolchain and libusb development files. Windows native builds are not currently supported.

## Quick start

### 1. Find the adapter, then confirm the instrument address

Connect the USB adapter and the GPIB cable, power on the SourceMeter, select its GPIB interface, and check the primary address on its front panel. Close other software using the same adapter. The tested 2400 was at address **24**; another instrument may differ.

```bash
python -m gpib_macarm list
```

Expect an adapter entry with an index, model, VID/PID, serial and `accessible` flag. An empty list means no recognized USB adapter was found; enumeration alone does not establish instrument communication. No NI kernel driver or `sudo` is part of the normal setup.

### 2. Run a read-only identity query

For the tested address 24 on adapter index 0:

```bash
python -m gpib_macarm query --index 0 --address 24 --timeout 10000 '*IDN?'
```

Success means a reply containing `KEITHLEY INSTRUMENTS INC.,MODEL 2400`. The reply also contains the instrument serial and firmware. To select an adapter by its reported serial, add `--serial YOUR_ADAPTER_SERIAL`. Query defaults append LF and assert EOI; keep the EOI default for this hardware combination. This command does not reset the SourceMeter or enable its source output.

Opening a controller initializes the adapter, asserts REN, and sends IFC, which affects other sessions on the bus. Run one controller application at a time.

### 3. Use the Python interface

```python
import gpib_macarm as visa

with visa.ResourceManager() as rm:
    with rm.open_resource(
        "GPIB0::24::INSTR",
        timeout=10000,             # milliseconds
        write_termination="\n",
        read_termination="\n",
        send_end=True,             # EOI on the final write byte
    ) as meter:
        print(meter.query("*IDN?"))
        print("Output enabled:", meter.query(":OUTP?"))
        print("Source function:", meter.query(":SOUR:FUNC?"))
        print("Error queue:", meter.query(":SYST:ERR?"))
```

These commands are appropriate for the 2400; other instruments need their own SCPI commands. `:SYST:ERR?` consumes the oldest error-queue entry. `GPIB0` selects adapter index 0; `24` is the instrument address. `list_resources()` returns adapter interface names such as `GPIB0::INTFC`; it does not discover or scan instrument addresses.

For several instruments, share one `Controller` or `ResourceManager` per adapter. A serial number is preferable when USB enumeration order can change:

```python
from gpib_macarm import Controller

with Controller(serial="YOUR_ADAPTER_SERIAL") as bus:
    meter = bus.open_instrument(24, timeout=10000)
    source = bus.open_instrument(5)
    print(meter.query("*IDN?"))
    print(source.query("*IDN?"))
```

Opening a controller initializes the adapter, asserts REN, and sends IFC, which affects the bus. The package does not automatically send SCPI `*RST`. `Instrument.close()` closes the logical session; closing its controller/manager releases the adapter and invalidates its borrowed resources.

### 4. Repeat the communication check

Run from the cloned repository; `tools/` and `examples/` are source-checkout scripts, not installed CLI subcommands:

```bash
mkdir -p build/validation
python tools/hardware_smoke.py --address 24 --timeout 10000 --count 100 \
  --output build/validation/hardware-smoke-2400.json
```

Check `success: true`, 100 nonempty results, identical identity strings and no error. The report includes serials and environment details; keep it local unless reviewed for sharing. This check does not enable source output.

### 5. Run a four-wire IV check on a confirmed passive low-resistance load

Connect the force and sense leads correctly before running this step. The following tool **resets the 2400, changes its configuration and enables output during a finite current sweep**; it is separate from the read-only checks above. Its bounded parameters were tested on a copper plate, and are not a general-purpose prescription for other samples.

```bash
python tools/keithley_2400_iv.py --resource GPIB0::24::INSTR \
  --max-current 0.001 --points 21 --nplc 1 --compliance 0.1 --timeout 60000 \
  --output build/validation/iv-check-1mA
```

After a suitable first result, the tested longer scan used `--max-current 0.01 --points 101 --nplc 5`, with a new output prefix. Add `--reverse` to scan from positive to negative current. Run `python tools/keithley_2400_iv.py --help` for all arguments. The tool currently restricts current to at most 10 mA, voltage compliance to at most 0.1 V, and points to 3..101.

Each run writes `.json` metadata, `.csv` data and a `.raw.txt` reply, and refuses to overwrite existing files. Check `success`, point count, instrument errors and `cleanup.output_off_confirmed`; fit-quality warnings must be evaluated separately. VOLT is measured; CURR is the programmed source current in this mode. The tool uses instrument-side auto output-off and finally cleanup. A lost connection can still prevent cleanup, so an unconfirmed output-off result requires checking the instrument front panel.

The library and test tool have no third-party Python runtime dependencies. Plotting is optional; the locally produced plots used matplotlib, which is not installed by this package. Successful acquisition does not by itself validate sample resistance or calibration.

## Migrating a PyVISA script

For scripts that only use the supported GPIB methods, start by replacing:

```python
import pyvisa
```

with:

```python
import gpib_macarm as pyvisa
```

Keep `ResourceManager()` without a VISA backend argument: change `ResourceManager("@py")` or a VISA library path to `ResourceManager()`. A GPIB resource does not use a serial `baud_rate`. Configure the instrument address, terminators, and timeout explicitly. Scripts that use unsupported VISA features require further adaptation.

This installs only the transport. Existing PyMeasure/Qt/temperature-control applications still need their own dependencies and control logic. They have not been migrated or validated end to end. In particular, the referenced 2400 acquisition script uses a fixed 10000 ms timeout and sends IV output-off only after successful reading/fitting; longer sweeps need a suitable timeout and exception cleanup before unattended use.

| Setting or method | Behavior |
| --- | --- |
| `timeout` | Milliseconds, default 3000; NI hardware rounds up to a supported discrete timeout |
| `write_termination` | LF by default; `None`/empty disables appending; CR/LF/CRLF supported |
| `read_termination` | LF by default; `None`/empty relies on EOI |
| `send_end` | True by default; EOI on the last write byte, independent of appended LF |
| `query_delay` | Seconds between write/read, default 0; adapter lock remains held |
| `chunk_size` | Native read chunk, default 4096, maximum 65535 |
| `max_read_bytes` | Complete-message limit, default 1 MiB; raises rather than silently truncating |
| `read_raw()` | Preserves every byte and ignores text EOS; requires EOI for message completion |
| `read_bytes(n)` | At most n bytes; can stop early on END/EOI |
| `clear()` | Selected device clear, distinct from SCPI `*CLS`/`*RST` |
| `read_stb()` / `stb` | Serial-poll status byte |

Timeout applies to native transfers, not a strict deadline for the entire query. Multiple chunks, cleanup, hardware timeout rounding, and `query_delay` can extend elapsed time. Failed writes are never automatically retried: the instrument may already have executed part or all of a command.

## Known issues and remaining work

| Area | Current status and remaining work |
| --- | --- |
| Basic SCPI / C ABI | Passed on the tested Mac/adapter/2400, including real measurements and long text replies. No ABI signature change is currently required for this working path. |
| Timeout recovery — priority | Deliberately unanswered reads led to further timeouts/protocol errors. Immediate reopen and STOP/drain trials were not reliable. Diagnose cancellation, pending adapter operations and response synchronization, then validate repeated fault/recovery cycles. Do not automatically retry writes or triggers. |
| EOI disabled | LF-only writes with `send_end=False` timed out on this combination. Keep EOI enabled. Large writes needing intermediate chunks without EOI are also not hardware-validated. |
| Application integration | Adjust batch timeouts; stop/mark failed acquisitions after communication errors; confirm output off. PyMeasure/TCR GUI and temperature-service integration remain untested. |
| Measurement accuracy | Copper curves show offset, nonlinear behavior and negative fitted slopes. Verify physical wiring, electrode geometry and accuracy against a known standard; voltage-source IV and real TCR remain unvalidated. |
| Reliability / compatibility | Long-duration acquisition, unplug/power-cycle recovery, multiple instruments, other adapter models/firmware, binary measurements, larger replies and Intel Mac remain unvalidated. Earlier Linux/Windows results do not certify the current hardware changes there. |
| Distribution | No PyPI release or macOS CI. Clean source-archive installation, cross-machine deployment and wider macOS/Python coverage still need validation. |

A timeout means communication failed, not that the instrument output is off. Stop the current run, confirm the output state and re-establish a known identity/settings state before resuming. `clear()`, IFC and reopen are available operations but are **not a guaranteed recovery procedure** on the tested hardware. The root cause of the failed recovery is not yet fully isolated. Normal communication success must not be presented as fault-tolerant unattended operation.

### Troubleshooting installation and connection

| Symptom | Check |
| --- | --- |
| `ModuleNotFoundError: gpib_macarm` | Activate the venv used for installation; check `python -m pip show gpib-macarm`. The distribution name uses a hyphen; the import uses an underscore. |
| Cannot load library / incompatible architecture | Check the library path from `info`, matching Python/libusb architecture, and `GPIB_MACARM_LIBRARY` if set. Rebuild in the intended environment; do not reuse another machine's binary. |
| libusb headers or pkg-config missing | Install `libusb pkg-config` with the matching Homebrew prefix, or use the include/library environment variables above. |
| `list` returns `[]` | Check the USB connection, accessory authorization and recognized VID/PID. This command does not probe GPIB addresses. |
| USB busy / access denied | Close other controller processes and check whether an NI driver owns the interface. Do not disable system security or install a kernel driver as a workaround. |
| Adapter listed but `*IDN?` fails | Check instrument power, GPIB interface selection, cable, primary address and default LF + EOI; use an instrument-supported query. An unanswered query can enter the known failed-recovery path. |
| Sweep times out / output state unknown | Allow for the entire batch, source delays, NPLC/auto-zero and transfers. Check the front panel and stop acquisition; do not blindly resend the query. |

## Diagnostics and development

```bash
python -m gpib_macarm info
python -m gpib_macarm list
python -m gpib_macarm query --address 24 --timeout 10000 '*IDN?'
python -m unittest discover -s tests -v
bash tools/test_native.sh  # offline ASan/UBSan tests; compiler/libusb headers required
python tools/hardware_smoke.py --address 24 --timeout 10000 --count 100 --output hardware-smoke.json
```

`info` loads the native library; `list` enumerates USB without issuing GPIB commands. The smoke test opens the adapter and repeats an explicitly chosen query, defaulting to `*IDN?`. Its JSON report records environment, adapter information, replies, timing, and failures.

For editable development, use `python -m pip install -e .`; rebuild after C/C++ changes. `GPIB_MACARM_LIBRARY` can select a custom native library during debugging. See [architecture](docs/ARCHITECTURE.md), [Mac acceptance](docs/MAC_ACCEPTANCE.md), and [CLAUDE.md](CLAUDE.md) before continuing development.

To create a portable source archive without host binaries or caches:

```bash
python tools/make_delivery.py
```

Output goes to `dist/`. The repository and source archive contain all native build inputs.

## Hardware scope

The primary target is a genuine **NI GPIB-USB-HS**, USB ID **3923:709b**. The inherited core also recognizes HS+, USB-B, KUSB-488A, and MC USB-488, but these combinations have not been tested in this project. USB-B firmware loading and initialization of an HS+ still enumerating as PID `761e` are not included. Clones are not guaranteed to work.

On Linux, USB permissions and competing kernel drivers may need attention. On macOS, another application or an installed NI driver can own the USB interface. This project does not change system driver configuration automatically.

## Acknowledgements and license

**GPL-2.0-or-later.** See [LICENSE](LICENSE) and [THIRD_PARTY.md](THIRD_PARTY.md). Original copyright and license notices are retained.

- [KAME](https://github.com/northriv/KAME), developed by Kentaro Kitagawa and contributors at the Kitagawa Laboratory, ISSP, University of Tokyo. This project extracts `modules/charinterface/usermode-linux-gpib` from commit [`f451025dc4215c5d85f39b71303f9008ccee66bc`](https://github.com/northriv/KAME/tree/f451025dc4215c5d85f39b71303f9008ccee66bc/modules/charinterface/usermode-linux-gpib). The standalone lifecycle/transport binding derives from [KAME](https://github.com/northriv/KAME)'s `NiGpibDriver` approach.
- [linux-gpib](https://linux-gpib.sourceforge.io/), by Frank Mori Hess, C. Schroeter, and contributors. [KAME](https://github.com/northriv/KAME)'s bundled driver is based on [linux-gpib](https://linux-gpib.sourceforge.io/) 4.3.6 / git `9813ff8f`.
- [libusb](https://libusb.info/) is an external library dependency and is not bundled as a binary in this source repository.

[UPSTREAM.json](UPSTREAM.json) records provenance and file hashes; [vendor/local-fixes.patch](vendor/local-fixes.patch) records local changes. GPIB-MacARM is an independent derivative project, not an NI product or an official [KAME](https://github.com/northriv/KAME)/[linux-gpib](https://linux-gpib.sourceforge.io/) release.
