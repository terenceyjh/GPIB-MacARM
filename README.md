# GPIB-MacARM

**Python GPIB communication for Apple Silicon Macs.**

[中文说明](README.zh-CN.md) · [Mac acceptance checklist](docs/MAC_ACCEPTANCE.md) · [Development handoff and prompts](CLAUDE.md)

GPIB-MacARM is a standalone, userspace transport for controlling GPIB instruments from Python through an NI GPIB-USB-HS adapter. It extracts the NI USB-GPIB core from **KAME**, whose userspace port is based on **linux-gpib**, and adds a small native C ABI and a VISA-like Python interface.

```text
Python → ctypes → GPIB-MacARM C ABI → KAME/linux-gpib driver → libusb → NI adapter → instrument
```

No NI-488.2, NI-VISA, Qt, complete KAME installation, kernel module, or background server is required. The package name is `gpib-macarm`; the import name is `gpib_macarm`.

## Status

**Early development, version 0.1.0. A local Apple Silicon source build and offline tests have passed on macOS 14.8.9 / Python 3.11.6. Real-instrument communication remains unvalidated.**

The shared POSIX implementation has been compiled and installed on Linux x86_64 and macOS arm64 (editable install). The completed checks are recorded below; full environments, commands and remaining limits are in the [validation record](docs/VALIDATION.md).

## Validation record

| Date | Environment | Verified results |
| --- | --- | --- |
| 2026-10-30 | Windows / Python 3.14 | Python API offline tests passed; native tests were skipped on this platform. |
| 2026-10-30 | WSL2 Linux x86_64 / Python 3.10.12 / GCC 11.4 | Native build/load, all 30 offline tests, ASan/UBSan checks, and clean wheel/source-archive installation passed. |
| 2026-10-31 | macOS 14.8.9 arm64 / Python 3.11.6 / Apple Clang 15.0.0 / libusb 1.0.30 | Editable build/install, native loading, both `info` entry points, all 30 offline tests with zero skips, and ASan/UBSan checks passed. |

The Mac test run includes 22 Python API tests, 2 distribution/provenance tests and 6 native parser/C ABI tests. The sanitizer programs exercised 20,000 malformed/short packets and verified simulated USB timeout propagation, error mapping and completion callbacks on both Linux and Mac.

**Hardware acceptance is still pending.** The Mac run did not open an adapter or send REN/IFC or instrument queries. USB/GPIB communication, long-term acquisition and recovery after unplugging or power loss remain untested, as do Intel Mac builds and clean non-editable Mac installations. Continue with the [Mac acceptance checklist](docs/MAC_ACCEPTANCE.md) for a specific adapter and instrument.

## What it provides

- `ResourceManager`, `open_resource`, `write`, `read`, and `query` for familiar SCPI scripts.
- Binary-safe `write_raw`, `read_raw`, and `read_bytes`.
- EOI/EOS handling, configurable text terminators, and reads that continue until message completion.
- Per-resource timeouts, a complete-query lock shared by instruments on one controller, and context-managed sessions.
- Selected device clear, serial poll/status-byte reads, IFC, REN, and SRQ-line checks.
- USB enumeration, a diagnostic CLI, examples, and a hardware smoke-test script.

This is a **limited VISA-like API**, not a PyVISA backend or a replacement for every VISA feature. TCP/IP and USBTMC resources, secondary GPIB addressing, VISA events, controller handover, and firmware loading are outside its current scope.

## Install from source on a Mac

Use Python 3.10+ and a matching-architecture libusb installation. On Apple Silicon, use arm64 Python and the arm64 Homebrew prefix, normally `/opt/homebrew`; avoid mixing Rosetta Python with arm64 libraries.

```bash
xcode-select --install  # skip if Command Line Tools are installed
brew install python libusb pkg-config

git clone https://github.com/terenceyjh/GPIB-MacARM.git
cd GPIB-MacARM
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .

python -m gpib_macarm info
python -m gpib_macarm list
```

The native library is built locally from the bundled C/C++ sources. It uses GNU C11 and GNU C++17, links libusb/pthread, and is loaded with Python's standard-library `ctypes`. No pybind11 or Python C API binding is needed. Building does not fetch KAME/linux-gpib; pip may fetch its Python build dependencies. The package has **not been published to PyPI**.

MacPorts `/opt/local` is also recognized. For another prefix:

```bash
LIBUSB_INCLUDE_DIR=/your/prefix/include \
LIBUSB_LIBRARY_DIR=/your/prefix/lib \
python -m pip install --no-cache-dir .
```

Linux development builds use the same POSIX path and require a C/C++ toolchain and libusb development files. Windows native builds are not currently supported.

## Quick start

```python
import gpib_macarm as visa

with visa.ResourceManager() as rm:
    with rm.open_resource("GPIB0::22::INSTR", timeout=5000) as meter:
        print(meter.query("*IDN?"))
        # Use commands from your instrument manual:
        # meter.write("CONF:VOLT:DC 10")
        # value = float(meter.query("READ?"))
```

`GPIB0` selects the enumerated adapter; `22` is the instrument's primary GPIB address, configured on its front panel. `list_resources()` returns adapter interface names such as `GPIB0::INTFC`; it does not scan instrument addresses.

For several instruments, share one `Controller` or `ResourceManager` per adapter. A serial number is preferable when USB enumeration order can change:

```python
from gpib_macarm import Controller

with Controller(serial="YOUR_ADAPTER_SERIAL") as bus:
    meter = bus.open_instrument(22, timeout=10000)
    source = bus.open_instrument(5)
    print(meter.query("*IDN?"))
    print(source.query("*IDN?"))
```

Opening a controller initializes the adapter, asserts REN, and sends IFC, which affects the bus. The package does not automatically send SCPI `*RST`. `Instrument.close()` closes the logical session; closing its controller/manager releases the adapter and invalidates its borrowed resources.

## Migrating a PyVISA script

For scripts that only use the supported GPIB methods, start by replacing:

```python
import pyvisa
```

with:

```python
import gpib_macarm as pyvisa
```

Keep `ResourceManager()` without a VISA backend argument. Configure the instrument address, terminators, and timeout explicitly. Scripts that use unsupported VISA features require further adaptation.

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

## Diagnostics and development

```bash
python -m gpib_macarm info
python -m gpib_macarm list
python -m gpib_macarm query --address 22 '*IDN?'
python -m unittest discover -s tests -v
bash tools/test_native.sh  # offline ASan/UBSan tests; compiler/libusb headers required
python tools/hardware_smoke.py --address 22 --count 100 --output hardware-smoke.json
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

- [KAME](https://github.com/northriv/KAME), developed by Kentaro Kitagawa and contributors at the Kitagawa Laboratory, ISSP, University of Tokyo. This project extracts `modules/charinterface/usermode-linux-gpib` from commit [`f451025dc4215c5d85f39b71303f9008ccee66bc`](https://github.com/northriv/KAME/tree/f451025dc4215c5d85f39b71303f9008ccee66bc/modules/charinterface/usermode-linux-gpib). The standalone lifecycle/transport binding derives from KAME's `NiGpibDriver` approach.
- [linux-gpib](https://linux-gpib.sourceforge.io/), by Frank Mori Hess, C. Schroeter, and contributors. KAME's bundled driver is based on linux-gpib 4.3.6 / git `9813ff8f`.
- [libusb](https://libusb.info/) is an external library dependency and is not bundled as a binary in this source repository.

[UPSTREAM.json](UPSTREAM.json) records provenance and file hashes; [vendor/local-fixes.patch](vendor/local-fixes.patch) records local changes. GPIB-MacARM is an independent derivative project, not an NI product or an official KAME/linux-gpib release.
