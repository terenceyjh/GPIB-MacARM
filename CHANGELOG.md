# Changelog

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
