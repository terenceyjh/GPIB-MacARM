# GPIB-MacARM

**A GPIB driver for Apple Silicon (ARM) Macs.**

[中文说明](README.zh-CN.md) · [Test summary](docs/VALIDATION.md) · [Agent guide & prompts](CLAUDE.md)

GPIB-MacARM brings **GPIB instrument communication to Apple Silicon Macs**, currently through an **NI GPIB-USB-HS** adapter. It runs in userspace and currently provides **Python bindings and a command-line tool**, backed by a native C/C++ driver and C ABI. The driver core is adapted from **[KAME](https://github.com/northriv/KAME) / [linux-gpib](https://linux-gpib.sourceforge.io/)**.

No NI-488.2, NI-VISA, kernel extension or background service is required. Install the package as `gpib-macarm`, then import `gpib_macarm`.

Built for fellow PhD students with a Mac, a bench full of instruments, and a thesis that really doesn't need another driver side quest. Hope this saves you a few late nights. ☕

## Tested hardware

| USB–GPIB adapter | Instrument | Verified use |
| --- | --- | --- |
| NI GPIB-USB-HS (`3923:709b`) | Keithley **2400** SourceMeter | SCPI read/write, repeated identity queries, finite four-wire current sweeps and long text replies |
| NI GPIB-USB-HS (`3923:709b`) | Stanford Research Systems **SR830** lock-in amplifier | Repeated queries, a continuous noise scan and explicit recovery from tested communication faults |

Early development: **0.1.0**. These combinations were tested on macOS 14.8.9 / arm64. Subsequent 2400 development checks passed USB/power recovery, large binary reads and a one-hour / 10040-point acquisition; these changes are not in the v0.1.0 installer. **Other instrument models, other adapter models/firmware and real multi-instrument operation remain unvalidated.** Successful transport does not certify measurement accuracy. See [test results](docs/VALIDATION.md) for version-specific coverage.

This project targets **ARM Macs**. Intel Mac users can also investigate established PyVISA + NI-488.2/NI-VISA setups, checking the exact macOS, driver and adapter combination: [NI's Intel Mac guidance](https://knowledge.ni.com/KnowledgeArticleDetails?id=kA0VU00000055n30AA&l=en-US). Newer driver versions do not necessarily retain GPIB support; see [NI's compatibility table](https://www.ni.com/en/support/documentation/compatibility/17/ni-visa-features-and-operating-system-compatibility.html).

## Install

Use **Python 3.10+ running as arm64**, with matching arm64 libusb. Install [Homebrew](https://brew.sh/) first if needed, then:

```bash
xcode-select --install  # skip if Command Line Tools are already installed
brew install python libusb pkg-config
python3 -c 'import platform, sys; print(platform.machine()); print(sys.executable)'
python3 -m pip install --user --break-system-packages --upgrade pip setuptools wheel
```

**From a release:** download **`gpib-macarm-0.1.0-release.zip`**, extract it and enter `GPIB-MacARM-0.1.0`. The folder contains the installer archive, dedicated English/Chinese READMEs and **`CLAUDE.md`, which you can give directly to your agent**. Follow that folder's README, or install its adjacent archive:

```bash
python3 -m pip install --user --break-system-packages --no-build-isolation ./gpib_macarm-0.1.0.tar.gz
```

No need to extract the inner tar.gz. The outer installation folder is not a source checkout; use the command above rather than `pip install .` there.

**From this repository:**

```bash
git clone https://github.com/terenceyjh/GPIB-MacARM.git
cd GPIB-MacARM
python3 -m pip install --user --break-system-packages --no-build-isolation .
```

The first pip command prepares the installation/build tools; the package command uses those tools. These commands install into the default arm64 `python3` interpreter's user package directory. `--user --break-system-packages` allows that installation with Homebrew Python's package-management policy; no `sudo` is needed. See [pip's installation options](https://pip.pypa.io/en/stable/cli/pip_install/).

The native driver compiles on your Mac during installation; the release contains source, not a prebuilt driver. Keep Homebrew libusb installed at runtime. **This project is not published to PyPI**; use a downloaded archive or the source folder rather than `pip install gpib-macarm`.

```bash
python3 -m gpib_macarm info
python3 -m pip check
```

`info` checks native loading without opening an instrument. Use the same `python3` to run your scripts, including in your IDE. The architecture check above must report `arm64`; Python 3.10+ and libusb must have matching architectures.

## Use

Connect the adapter and instrument, close other programs using the adapter, and check the instrument's GPIB primary address on its front panel.

```bash
python3 -m gpib_macarm list
# Replace 24 with your instrument's actual address:
python3 -m gpib_macarm query --address 24 --timeout 10000 '*IDN?'
```

`list` enumerates USB adapters; it does not discover instrument addresses. Opening a controller sends REN/IFC and affects the shared bus. The identity example does not reset the instrument or enable a source output.

```python
import gpib_macarm as visa

with visa.ResourceManager() as rm:
    with rm.open_resource(
        "GPIB0::24::INSTR",  # adapter index 0, instrument address 24
        timeout=10000,      # milliseconds
        write_termination="\n",
        read_termination="\n",
        send_end=True,
    ) as instrument:
        print(instrument.query("*IDN?"))
        # instrument.write("...")  # instrument-specific command
        # reply = instrument.read()
```

Share one manager/controller per adapter. To select an adapter by serial number, pass `serial="YOUR_ADAPTER_SERIAL"` to `open_resource()`. Use commands supported by your instrument.

Save the example as `example.py` and run `python3 example.py`. `query()` writes a command and reads its reply; use `write()` for commands without a reply. The default text settings add LF on writes and remove LF from text replies. Raw methods preserve bytes.

| Common interface | Purpose |
| --- | --- |
| `write()`, `read()`, `query()` | Text commands and replies |
| `query_ascii_values()` | Parse a delimited numeric reply into a list |
| `write_raw()`, `read_raw()`, `read_bytes(n)` | Preserve raw bytes; hardware coverage remains limited |
| `timeout`, `query_delay` | Milliseconds per transfer; seconds between query write/read |
| `read_stb()`, `clear()` | Serial poll and selected device clear |
| `recover()` | Explicit communication recovery; verified on the tested SR830 combination |

Long measurements need a longer timeout than identity queries; timeouts are per transfer, not a strict deadline for the whole query. A communication error stops ordinary operations on the shared controller. Stop the failed acquisition, explicitly recover if appropriate, and verify identity/settings before starting a new run; failed commands are not replayed. Recovery does not confirm that a source output is off.

For basic PyVISA-style scripts, replace `import pyvisa` with `import gpib_macarm as pyvisa` and use **`ResourceManager()` without `"@py"`**. This is a limited VISA-like API, not a registered PyVISA backend. TCP/IP, USBTMC, VISA events and binary-block convenience methods are outside its scope.

## Known limitation: writes without EOI

**Keep the default `send_end=True` and LF termination.** Default LF+EOI works on the tested setups; EOI-only identity queries also passed on the 2400. GPIB supports transfers without EOI, and the 2400 explicitly accepts LF alone as a command terminator. However, with EOI disabled, our LF-terminated query reached the 2400 and produced the correct reply while the adapter's USB write-completion response was missing, so the driver timed out. This is an unresolved compatibility issue in the current combination, not a protocol prohibition. [2400 manual, §14](https://download.tek.com/manual/2400S-900-01_K-Sep2011_User.pdf)

The driver follows linux-gpib's EOI flag and real write-completion approach; missing confirmation is an error, and failed commands are not automatically retried. Writes over 65535 bytes need intermediate no-EOI chunks and remain unsupported on the tested setup, even with `send_end=True`. Large **reads** are a separate path and passed the documented development checks.

## Possible further development

- Investigate no-EOI completion when that use case is needed, using the same adapter with an official-driver comparison; validate large writes afterward.
- Test more instruments and adapter firmware, including recovery on each combination.
- Test multiple real instruments sharing one GPIB bus, with interleaved queries and shared-controller recovery.
- Broaden Apple Silicon Mac, macOS and Python installation coverage.

For agent-assisted installation, script migration or development, give your agent **[CLAUDE.md](CLAUDE.md)**. It includes ready-to-use prompts, rebuild instructions and the same development priorities. Implementation details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Credits & license

**Core driver credit goes to [KAME](https://github.com/northriv/KAME) and [linux-gpib](https://linux-gpib.sourceforge.io/).** This project extracts, adapts and packages their work for the use case above. It is not an official NI driver.

GPL-2.0-or-later. Original notices and license files are preserved; see [THIRD_PARTY.md](THIRD_PARTY.md), [UPSTREAM.json](UPSTREAM.json) and [vendor/local-fixes.patch](vendor/local-fixes.patch).
