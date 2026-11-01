# GPIB-MacARM 0.1.0 — install & use

**A GPIB driver for Apple Silicon (ARM) Macs.** Communicate with laboratory instruments through an NI GPIB-USB-HS adapter; the current interface is primarily Python, with a small command-line tool. The native driver is adapted from **[KAME](https://github.com/northriv/KAME) / [linux-gpib](https://linux-gpib.sourceforge.io/)**. No NI-488.2, NI-VISA or kernel extension is required.

[中文说明](README.zh-CN.md)

## Start here

This folder contains:

- `gpib_macarm-0.1.0.tar.gz` — the source package to install with pip. **Do not extract this inner archive.**
- `README.md` / `README.zh-CN.md` — installation and basic use.
- **[`CLAUDE.md`](CLAUDE.md)** — detailed installation, usage and troubleshooting instructions you can give directly to an agent.
- `LICENSE`, `THIRD_PARTY.md`, `SHA256SUMS.txt` — license, credits and checksums.

## Install

Requirements: Apple Silicon Mac, arm64 Python 3.10+, Xcode Command Line Tools and arm64 libusb. With [Homebrew](https://brew.sh/) installed:

```bash
xcode-select --install  # skip if already installed; finish this installer first
brew install python libusb pkg-config
python3 -c 'import platform, sys; print(platform.machine()); print(sys.executable)'
```

The architecture must be `arm64`. Open Terminal in **this extracted folder**, which contains the `.tar.gz` and this README. You can type `cd `, drag this folder into Terminal, then press Return.

```bash
python3 -m pip install --user --break-system-packages --upgrade pip setuptools wheel
python3 -m pip install --user --break-system-packages --no-build-isolation ./gpib_macarm-0.1.0.tar.gz
python3 -m gpib_macarm info
python3 -m pip check
```

The first pip command prepares the installation/build tools; the second installs this package using those tools. This installs into the default `python3` interpreter's user package directory. `--user --break-system-packages` allows this user installation with Homebrew Python; no `sudo` is needed. See [pip's installation options](https://pip.pypa.io/en/stable/cli/pip_install/). Use this same `python3` for your scripts and select it in your IDE.

`info` should show version `0.1.0`, machine `arm64` and a native library path. It does not open an instrument. pip compiles the driver on your Mac; keep libusb installed at runtime. The package is **not on PyPI**. **Do not use `pip install .` in this outer folder**: install the adjacent tar.gz as shown above.

## Use

Close other software using the adapter, connect the instrument and check its GPIB address on the front panel.

```bash
python3 -m gpib_macarm list
# Replace 24 with the actual instrument address:
python3 -m gpib_macarm query --address 24 --timeout 10000 '*IDN?'
```

`list` lists USB adapters, not instrument addresses. `*IDN?` must be supported by your instrument. Opening a controller sends REN/IFC and affects the shared bus; this identity query does not reset the instrument or enable a source output.

Save the following as `example.py`, replace address 24, then run `python3 example.py`:

```python
import gpib_macarm as visa

with visa.ResourceManager() as rm:
    with rm.open_resource(
        "GPIB0::24::INSTR",  # adapter index 0; replace address 24
        timeout=10000,      # milliseconds
        write_termination="\n",
        read_termination="\n",
        send_end=True,
    ) as instrument:
        print(instrument.query("*IDN?"))
```

`query()` writes a command and reads its reply. Use `write()` for commands without replies, and `read()` to read a pending reply. The default text settings append LF on writes and remove LF from text replies. Commands and timeouts must match your instrument; a timeout is per transfer. Share one manager per adapter. For basic PyVISA migration, use `import gpib_macarm as pyvisa` and `ResourceManager()` without `"@py"`.

## Known limitation: writes without EOI

**Keep the default `send_end=True` and LF termination.** GPIB supports no-EOI transfers, and the 2400 accepts LF alone as a command terminator. On the tested combination, a no-EOI query reached the 2400 and produced a correct reply, but the adapter's USB write-completion response was missing; the driver reported a timeout. The cause is unresolved. Default LF+EOI works, and EOI-only 2400 identity queries also passed. [2400 manual, §14](https://download.tek.com/manual/2400S-900-01_K-Sep2011_User.pdf)

The driver follows linux-gpib's EOI flag and real write-completion approach. It does not assume success when confirmation is missing or automatically replay failed commands. Writes over 65535 bytes need intermediate no-EOI chunks and remain unsupported on the tested setup, even with `send_end=True`.

After communication errors, stop the failed acquisition and verify identity/settings and actual output state before a new run. Recovery does not prove output is off. See **[CLAUDE.md](CLAUDE.md)** for details.

## Test scope and future work

The v0.1.0 installer was tested with NI GPIB-USB-HS and **Keithley 2400 / SRS SR830** on ARM macOS, including repeated queries, 2400 finite acquisition and SR830 continuous acquisition/recovery. This ZIP updates the guides and retains the original v0.1.0 driver archive.

Later development passed single-2400 USB/power recovery, large binary reads and a one-hour / 10040-point run; those driver changes are **not included in this installer**. The [project test record](https://github.com/terenceyjh/GPIB-MacARM/blob/main/docs/VALIDATION.md) separates the versions. Measurement accuracy is not certified.

Possible next work: investigate no-EOI completion when needed, test more instruments/adapters, and test multiple real instruments sharing one bus. Other instrument models, other firmware and Intel Macs remain unvalidated.

GPL-2.0-or-later; not an official NI driver. Hope this saves a fellow Mac-using PhD student a driver side quest or two. ☕
