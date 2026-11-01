# Changelog

## Unreleased

- Validate the complete NI USB write-completion frame, including its termination block; reject corrupt, unrelated or out-of-range acknowledgements. Missing no-EOI completions still fail explicitly and are not emulated.
- Add a guided bench coordinator with explicit physical-action pauses, serial-pinned re-enumeration, buffer backup, shared-session checks and plan-only operation without hardware access. Gate large writes on actual no-EOI completion; incomplete features remain reported as blocked.
- Keep the instrument addressed across count-limited reads, and block other-address reads or REN changes while a reply is unfinished.
- Bound native read requests to 4096 bytes after a large IBRD request wedged the tested HS; assemble complete messages without truncation. The full 40003-byte binary rerun passed, including 65535-byte caller requests.
- Cancel local transfers before detaching a failed controller, including failed initialization, without appending normal shutdown register requests.
- Add native C++ transfer/close/recovery fault-injection checks and reproducible 2400 acquisition/binary/recovery and shared-bus query tools.
- Validate 2500-point / 140000-byte ASCII acquisition, both binary formats/orders, physical USB unplug and instrument power-cycle recovery, timeout/partial/over-limit recovery, and a 3600.55-second / 10040-point acquisition with exact raw/CSV agreement and confirmed output-off. No-EOI acknowledgement and dependent large writes remain unsupported; real multi-instrument and other-firmware checks remain open. These driver changes are not in the v0.1.0 installer.

## Documentation and installation-guide update — 2026-11-02

- Present the project as a GPIB driver for Apple Silicon Macs, currently exposing Python bindings and a CLI.
- Explain the no-EOI compatibility limit: the 2400 accepts the query but the USB write-completion response is missing. Keep default LF+EOI; no-EOI is permitted by GPIB and remains unresolved here.
- Document installation into the default arm64 Python's user package directory, with executable Python/CLI examples. Outline optional EOI, more-device and real shared-bus follow-up work.
- Refresh the v0.1.0 ZIP's outer English/Chinese READMEs and agent guide with checksums. Preserve its original driver source archive and tag; distinguish released tests from later development results.

## Packaging update — 2026-11-01

- Deliver one installation ZIP containing the validated 0.1.0 source archive, dedicated English/Chinese installation READMEs, a detailed agent troubleshooting guide, licenses and internal checksums.
- Keep the existing driver source archive and release tag; replace the standalone download assets with the installation bundle.

## 0.1.0 — release preparation, 2026-11-01

- Package a standalone userspace GPIB driver and Python/CLI interface for Apple Silicon Macs, derived from KAME / linux-gpib.
- Fix compact NI USB reply parsing and preserve checked message boundaries, raw bytes and source provenance.
- Add shared-controller fault lockout and explicit recovery without replaying failed commands.
- Provide concise English/Chinese installation and usage guides, a public agent guide with prompts, and a brief hardware test summary.
- Curate release contents; keep private handoffs, detailed test evidence and local artifacts out of distributions.

Tested hardware: NI GPIB-USB-HS with Keithley 2400 and SRS SR830. No-EOI writes remain unsupported on the tested setups; recovery coverage is limited to the tested SR830 combination. See [test summary](docs/VALIDATION.md).

## Initial development — 2026-10-30

- Extract the KAME userspace NI USB-GPIB core with its linux-gpib sources and licenses.
- Add native C ABI, ctypes bindings, shared-controller Python sessions, command-line tools, examples and offline checks.
