# GPIB-MacARM

**Use a GPIB-to-USB adapter with Python on an Apple Silicon (ARM) Mac.**

[中文说明](README.zh-CN.md) · [Test summary](docs/VALIDATION.md) · [Agent guide & prompts](CLAUDE.md)

GPIB-MacARM provides a **userspace GPIB driver and a Python interface** for controlling laboratory instruments through an **NI GPIB-USB-HS** adapter on ARM Macs. The native driver core is adapted from **[KAME](https://github.com/northriv/KAME) / [linux-gpib](https://linux-gpib.sourceforge.io/)**; this project packages it with a C ABI, Python bindings and a small command-line tool.

No NI-488.2, NI-VISA, kernel extension or background service is required. Install the package as `gpib-macarm`, then import `gpib_macarm`.

Built for fellow PhD students with a Mac, a bench full of instruments, and a thesis that really doesn't need another driver side quest. Hope this saves you a few late nights. ☕

## Tested hardware

| USB–GPIB adapter | Instrument | Verified use |
| --- | --- | --- |
| NI GPIB-USB-HS (`3923:709b`) | Keithley **2400** SourceMeter | SCPI read/write, repeated identity queries, finite four-wire current sweeps and long text replies |
| NI GPIB-USB-HS (`3923:709b`) | Stanford Research Systems **SR830** lock-in amplifier | Repeated queries, a continuous noise scan and explicit recovery from tested communication faults |

Early development: **0.1.0**. These combinations were tested on macOS 14.8.9 / arm64. **2450, other adapters and Intel Macs have not been validated.** Successful transport does not certify measurement accuracy. See the short [test summary](docs/VALIDATION.md) for coverage and limits.

This project targets **ARM Macs**. Intel Mac users can also investigate established PyVISA + NI-488.2/NI-VISA setups, checking the exact macOS, driver and adapter combination: [NI's Intel Mac guidance](https://knowledge.ni.com/KnowledgeArticleDetails?id=kA0VU00000055n30AA&l=en-US). Newer driver versions do not necessarily retain GPIB support; see [NI's compatibility table](https://www.ni.com/en/support/documentation/compatibility/17/ni-visa-features-and-operating-system-compatibility.html).

## Install

Use **Python 3.10+ running as arm64**, with matching arm64 libusb. Install [Homebrew](https://brew.sh/) first if needed, then:

```bash
xcode-select --install  # skip if Command Line Tools are already installed
brew install python libusb pkg-config
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

**From a release:** download and extract the source ZIP, enter its `GPIB-MacARM` folder, then install with pip:

```bash
python -m pip install .
```

Alternatively, install the downloaded source distribution directly, from the folder containing it:

```bash
python -m pip install ./gpib_macarm-0.1.0.tar.gz
```

**From this repository:**

```bash
git clone https://github.com/terenceyjh/GPIB-MacARM.git
cd GPIB-MacARM
python -m pip install .
```

The native driver compiles on your Mac during installation; the release contains source, not a prebuilt driver. Keep Homebrew libusb installed at runtime. **This project is not published to PyPI**; use a downloaded archive or the source folder rather than `pip install gpib-macarm`.

```bash
python -m gpib_macarm info
python -m pip check
```

`info` checks native loading without opening an instrument. In a new terminal, reactivate the same environment. If loading fails, check `python -c 'import platform; print(platform.machine())'` reports `arm64` and that Python/libusb architectures match.

## Use

Connect the adapter and instrument, close other programs using the adapter, and check the instrument's GPIB primary address on its front panel.

```bash
python -m gpib_macarm list
# Replace 24 with your instrument's actual address:
python -m gpib_macarm query --address 24 --timeout 10000 '*IDN?'
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

| Common interface | Purpose |
| --- | --- |
| `write()`, `read()`, `query()` | Text commands and replies |
| `query_ascii_values()` | Parse a delimited numeric reply into a list |
| `write_raw()`, `read_raw()`, `read_bytes(n)` | Preserve raw bytes; hardware coverage remains limited |
| `timeout`, `query_delay` | Milliseconds per transfer; seconds between query write/read |
| `read_stb()`, `clear()` | Serial poll and selected device clear |
| `recover()` | Explicit communication recovery; verified on the tested SR830 combination |

Keep **`send_end=True`**: LF-only writes with EOI disabled currently fail. Long measurements need a longer timeout than identity queries; timeouts are per transfer, not a strict deadline for the whole query. A communication error stops ordinary operations on the shared controller. Stop the failed acquisition, explicitly recover if appropriate, and verify identity/settings before starting a new run; failed commands are not replayed. Recovery does not confirm that a source output is off.

For basic PyVISA-style scripts, replace `import pyvisa` with `import gpib_macarm as pyvisa` and use **`ResourceManager()` without `"@py"`**. This is a limited VISA-like API, not a registered PyVISA backend. TCP/IP, USBTMC, VISA events and binary-block convenience methods are outside its scope.

## Next steps

- Diagnose and fix **writes without EOI**, then validate large writes with EOI only on the final chunk.
- Extend recovery testing to the 2400, USB unplug/power loss and additional firmware/devices.
- Validate binary transfers, longer acquisitions and multiple instruments on one bus.
- Add broader macOS/Python coverage, cross-machine installation checks and macOS CI.

For agent-assisted installation, script migration or development, give your agent **[CLAUDE.md](CLAUDE.md)**. It includes ready-to-use prompts, rebuild instructions and the same development priorities. Implementation details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Credits & license

**Core driver credit goes to [KAME](https://github.com/northriv/KAME) and [linux-gpib](https://linux-gpib.sourceforge.io/).** This project extracts, adapts and packages their work for the use case above. It is not an official NI driver.

GPL-2.0-or-later. Original notices and license files are preserved; see [THIRD_PARTY.md](THIRD_PARTY.md), [UPSTREAM.json](UPSTREAM.json) and [vendor/local-fixes.patch](vendor/local-fixes.patch).
