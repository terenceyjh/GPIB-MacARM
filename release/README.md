# GPIB-MacARM 0.1.0 — install & use

**A userspace GPIB driver and Python interface for Apple Silicon (ARM) Macs**, using an NI GPIB-USB-HS adapter. Core driver credit: **[KAME](https://github.com/northriv/KAME) / [linux-gpib](https://linux-gpib.sourceforge.io/)**.

[中文说明](README.zh-CN.md)

## Start here

This folder contains everything you need to start:

- `gpib_macarm-0.1.0.tar.gz` — the source package to install with pip. **Do not extract this inner archive.**
- `README.md` / `README.zh-CN.md` — installation and basic use.
- **[`CLAUDE.md`](CLAUDE.md)** — a detailed installation, usage and troubleshooting guide. **You can give this file directly to your agent. It is in the same folder.**
- `LICENSE`, `THIRD_PARTY.md`, `SHA256SUMS.txt` — license, credits and checksums.

## Install

Requirements: ARM Mac, arm64 Python 3.10+, Xcode Command Line Tools and arm64 libusb. With [Homebrew](https://brew.sh/) installed:

```bash
xcode-select --install  # skip if already installed; finish this installer first
brew install python libusb pkg-config
```

Open Terminal in **this extracted folder**, which contains the `.tar.gz` and this README. You can type `cd `, drag this folder into Terminal, then press Return.

```bash
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ./gpib_macarm-0.1.0.tar.gz
python -m gpib_macarm info
python -m pip check
```

`info` should show version `0.1.0`, machine `arm64` and a native library path. It does not open an instrument. pip compiles the driver locally; keep libusb installed at runtime. The package is **not on PyPI**. **Do not use `pip install .` in this outer folder**: it contains the installer archive, not an unpacked source tree.

For later use, return to this folder and run `source .venv/bin/activate` before running Python.

## Use

Close other software using the adapter, connect the instrument and check its GPIB address on the front panel.

```bash
python -m gpib_macarm list
# Replace 24 with the actual instrument address:
python -m gpib_macarm query --address 24 --timeout 10000 '*IDN?'
```

`list` lists USB adapters, not instrument addresses. Opening a controller sends REN/IFC and affects the shared bus; the identity query does not reset the instrument or enable a source output.

```python
import gpib_macarm as visa

with visa.ResourceManager() as rm:
    with rm.open_resource(
        "GPIB0::24::INSTR",  # adapter index 0; replace address 24
        timeout=10000,      # milliseconds
        send_end=True,
    ) as instrument:
        print(instrument.query("*IDN?"))
```

Use instrument-specific commands with `write()`, `read()` and `query()`. Share one manager per adapter. For basic PyVISA migration, use `import gpib_macarm as pyvisa` and `ResourceManager()` without `"@py"`.

## Current limits & next steps

Tested: NI GPIB-USB-HS with **Keithley 2400** and **SRS SR830**, on ARM macOS. **Keep `send_end=True`: writes without EOI currently fail.** Explicit recovery is verified on the tested SR830 setup only. After a communication error, stop the failed acquisition and verify identity/settings and actual output state before starting a new one. See **[CLAUDE.md](CLAUDE.md)** for specific workarounds and recovery details.

Next priorities: no-EOI and large chunked writes, broader fault recovery, binary/longer/multi-instrument acquisition, cross-machine installation and macOS CI. 2450 and Intel Macs are not validated. Successful communication does not certify measurement accuracy.

GPL-2.0-or-later; not an official NI driver. Hope this saves a fellow Mac-using PhD student a driver side quest or two. ☕
