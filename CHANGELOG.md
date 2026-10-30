# Changelog

Unreleased — 2026-10-31

- Validate the local Apple Silicon editable build, native loading, both info entry points, all 30 offline tests without skips, and ASan/UBSan checks on macOS 14.8.9 / Python 3.11.6 / libusb 1.0.30.
- Update validation, setup status and development handoff documentation; Intel Mac and real-hardware acceptance remain pending. No driver or vendor changes were needed.

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
