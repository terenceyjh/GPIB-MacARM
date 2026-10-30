# Changelog

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
- Hardware and macOS/Apple Silicon validation remain pending; see docs/VALIDATION.md.
