# Changelog

Unreleased — 2026-10-31

- Expand English/Chinese installation and usage guides, explicitly record successful real SCPI communication with the 2400, and prioritize unfinished work in the READMEs and CLAUDE.md. Verify ordinary non-editable installation in a fresh Mac venv, out-of-tree native loading, CLI diagnostics and all 39 offline tests.
- Add a bounded four-wire current-sweep tool with configuration/status validation, instrument auto output-off, finally cleanup, CSV/raw/JSON reports and explicit fit-quality warnings. On the connected copper plate, acquire 21-point ±1 mA and 101-point ±10 mA forward/reverse sweeps; verify 5655-byte replies and output off after each run. Raw curves are nonlinear with negative fitted slopes; sample resistance accuracy remains unvalidated. All 39 offline tests pass.
- Validate the local Apple Silicon editable build, native loading, both info entry points, all 30 offline tests without skips, and ASan/UBSan checks on macOS 14.8.9 / Python 3.11.6 / libusb 1.0.30.
- Validate basic read-only GPIB-USB-HS / Keithley 2400 communication at address 24: 100 consecutive identity queries, fragmented reads, raw bytes, terminators and status queries. Keep output off; actual source/measurement runs remain untested.
- Fix compact NI IBRD reply parsing: accept the observed shorter trailer and use checked residual counts when its last-block count is unreliable. Preserve full-trailer validation, update the reproducible vendor patch and local source hash, and add native regression/sanitizer fixtures. All 34 Mac offline tests pass without skips.
- Record hardware limits: no-EOI writes and recovery after deliberately unanswered reads did not pass; do not describe these as supported by the tested combination. Intel Mac and broader hardware acceptance remain pending.

0.1.0 — 2026-10-30

- Name the independent project GPIB-MacARM, distribution/CLI gpib-macarm, import gpib_macarm.
- Add English/Chinese documentation and CLAUDE.md development handoff prompts.

- Extract KAME's NI USB-GPIB usermode C core into a standalone installable package.
- Add ctypes C ABI, shared-controller VISA-like Python interface, CLI and examples.
- Preserve END/EOS, binary data and complete-message boundaries; chunk writes safely.
- Add bounds checking to the NI readback parser, short-packet errors and checked bus controls.
- Carry USB per-transfer timeouts and error identities through the POSIX shim.
- Serialize query transactions; clean up EOS on failures; never retry writes automatically.
- Include reproducible upstream manifest, patch, licensing, offline tests and Mac acceptance steps.
- At initial delivery, hardware and macOS/Apple Silicon validation were pending; see docs/VALIDATION.md for subsequent results.
