# Test summary / 测试概览

Evidence reviewed: 2026-11-02. Hardware checks performed: 2026-10-31 through 2026-11-02.

记录核对日期：2026-11-02；初始实物测试于 2026-10-31 完成，后续开发实测见下面的独立条目。这里只保留简要结论，详细日志、设备标识及测量数据留在本地，不随仓库或 release 分发。

## Released v0.1.0 hardware coverage / 已发布版本实物范围

Tested environment: macOS 14.8.9 / arm64, libusb 1.0.30; Python 3.11.6 for 2400 tests and 3.13.9 for SR830 tests.

| Adapter / 转接线 | Instrument / 仪器 | Passed / 已通过 | Limits / 边界 |
| --- | --- | --- | --- |
| NI GPIB-USB-HS (`3923:709b`) | Keithley 2400 | SCPI writes/readback, repeated identity queries, fragmented/raw reads, finite four-wire current sweeps and long text replies / SCPI 读写、连续身份查询、分块与原始读取、四线有限电流扫描及长文本回复 | Measurement accuracy unvalidated; new recovery implementation not retested here / 测量准确度未验收，新恢复实现尚未在此组合复验 |
| NI GPIB-USB-HS (`3923:709b`) | SRS SR830 | Repeated queries, 42-minute noise scan, explicit recovery after read timeout, partial reply and failed no-EOI write / 连续查询、42 分钟噪声扫描，以及读取超时、部分回复、无 EOI 写失败后的显式恢复 | Recovery passed; the no-EOI write itself still failed / 恢复通过，无 EOI 写入本身仍失败 |

**Default LF + EOI works on these combinations. Keep `send_end=True`.** 2450, other adapter models/firmware, Intel Macs, unplug/power-loss recovery, binary measurements, large multi-chunk writes and multiple instruments sharing a bus remain unvalidated.

**上述组合保留默认 LF + EOI。** 2450、其他线缆/固件、Intel Mac、拔插/断电恢复、二进制测量、大数据分块写入和多仪器共线仍待验证。通信成功不证明测量准确或源输出已经关闭。

## Software / 软件

- Release checks on 2026-11-01: **57 offline tests passed, zero skipped**, including exclusion of private files from the source ZIP.
- Both release archives installed with pip into fresh arm64 environments: source ZIP on Python 3.11.6 and sdist on Python 3.13.9. Native loading outside the source folder, pip check and all 57 tests passed in each environment.
- Native ASan/UBSan checks passed in the preceding development round. No new instrument tests were performed during release preparation.
- Earlier Linux x86_64 build/install and offline checks passed on an earlier revision; Windows checks covered Python only. Neither establishes current-revision hardware support there.

2026-11-01 打包验证：**57 项离线测试通过、零跳过**。ZIP 与 tar.gz 分别在新的 arm64 Python 3.11.6 / 3.13.9 环境完成 pip 安装，原生库加载、pip check 及全套测试通过；检查确认不夹带本机记录和二进制产物。上一轮原生 sanitizer 检查通过，本轮未重跑仪器测试。Linux/Windows 的历史结果不代表当前版本已完成这些平台的实物验收。

Installation-bundle update: 58 project offline checks passed. The ZIP pairs the same validated 0.1.0 sdist with dedicated install/agent guides and internal checksums; it introduces no driver changes.

安装 ZIP 调整：58 项项目离线检查通过；内含原已验证的 0.1.0 源码包、专用说明和校验文件，不改变驱动代码。

## Remaining work / 待办

Possible follow-up work: reliable no-EOI completion and dependent large writes when needed; communication/recovery on more instruments and adapter firmware; real multi-instrument shared-bus tests; broader Apple Silicon Mac installation coverage. Default-EOI use does not depend on resolving the no-EOI limitation. See [README](../README.md) / [中文说明](../README.zh-CN.md) and [CLAUDE.md](../CLAUDE.md).

## Unreleased development — 2026-11-01–02 / 未发布开发验证

The v0.1.0 installation ZIP's outer guides were updated on 2026-11-02; its inner
driver source archive remains the original v0.1.0. The results below apply to
later development revisions on the same arm64 Mac / HS / **2400**, not to that
installer. The subsequent completion-frame validation has its own status below.

- **91 offline tests passed, zero skipped.** Native ASan/UBSan checks passed for
  the USB shim, parser (including 20000 malformed frames), actual C++ transfer /
  close methods and recovery fault injection. Simulated multi-instrument checks
  do not establish real shared-bus support.
- **Physical USB unplug/replug passed:** unplug faults and locks the old session;
  recovery while absent fails without replacing the original error. After
  serial-pinned re-enumeration, a new manager verifies identity/settings/output.
  **2400 power-off/on recovery passed:** identity and output-off verified, changed
  power-cycle settings recorded rather than blindly restored. The prior buffer
  was backed up before power-off.
- **Three unanswered-read timeout/recovery rounds, partial-reply recovery and
  over-limit-reply protection/recovery passed**, with identity, settings and
  output-off checks. Explicit recovery after no-EOI write failure also passed.
  No failed command or measurement was automatically replayed.
- Three serial-poll checks passed: MAV was clear before an identity query,
  set while its reply was pending, and clear after the correct reply was read.
- A three-point pilot and **2500-point four-wire Source-I / Measure-V batch**
  passed. The latter returned **140000 ASCII bytes** with valid count/status
  and confirmed automatic output-off.
- A **40003-byte binary reply** passed **20 format/order/chunk cases**: SREAL and
  REAL,32; NORM and SWAP; requested chunks 7/15/31/4096/65535 bytes. Four separate
  header/payload cases passed, preserving embedded NUL/CR/LF. Binary values
  agree with ASCII after accounting for their documented timestamp origins.
- The earlier 65535-byte native IBRD request wedged the adapter. After physical
  replug, the **4096-byte native request cap**, continuous talker addressing and
  failure-cleanup fixes passed the above rerun. A 65535-byte *caller* request
  now completes through bounded native reads without truncation.
- **3600.55 seconds / 10040 points / 1004 finite batches passed**, using 2.5 µA,
  21 V protection, four-wire sensing and NPLC 5. Raw replies and CSV agree
  point-for-point; counts, timestamps, statuses, programmed current and voltage
  limits passed independent checks. Instrument-side output-off was verified
  after every batch, and final cleanup verified output off and set current to
  zero. The CURR field is the programmed source current, not an independent
  current measurement. This is transport acceptance, not accuracy certification.
- **No-EOI writes remain unsupported.** A command may reach the instrument while
  its real USB write completion is missing. Repeated traced failures show no
  completion on the normal or alternate receive endpoint; generic status data
  are not a substitute for an operation acknowledgement. A longer timeout
  (22 seconds actual wait) and 10 ms address-to-write delay did not restore
  completion. Identity/settings/output-off checks passed after each recovery.
  Dependent large writes
  with EOI only on the last chunk are blocked. The coordinator correctly ends
  with a partial report, despite successful acquisition and recovery checks.
- **Only one 2400 was available.** Real multi-instrument shared-bus tests and
  other adapters/firmware remain unvalidated. Distribution/CI work was deferred.

现场已完成 USB 拔插、2400 断电恢复、读取超时/部分回复/超长回复恢复，以及
2500 点 ASCII、两格式两字节序的大二进制和一小时 10040 点采集。原始回复与
CSV 逐点一致，自动及最终关输出均核验通过；测量准确度不在本次验收范围。
原大读取请求导致的卡死在限长修复后未复现。无 EOI 写入仍缺真实完成确认，
不能通过伪造确认记作成功，相关大写入被阻止。现场没有第二台仪器，实际共线
及其他固件仍待验证，因此路线图 1–3 尚不能全部标记完成。

Reproducible tools: `tools/bench_acceptance.py`,
`tools/keithley_2400_check.py`, `tools/keithley_2400_acquire.py` and
`tools/bus_smoke.py`. The coordinator supports serial-pinned physical steps,
explicit operator confirmation, buffer backup and phase-level journals;
`--plan` does not construct a native backend. See [guided bench instructions](BENCH_TESTS.md).
Detailed logs, identifiers and sample data remain local and excluded from
source/release archives.

### Minimal EOI check — 2026-11-02 / 最小 EOI 对照

Three identity-query writes, source output kept off, no resets or measurement
configuration changes: LF+EOI and EOI-only both received a real write completion
and the correct reply. LF-only with EOI disabled timed out waiting for write
completion; a diagnostic read consumed the original correct reply without
resending the query. USB observation confirmed that the outgoing EOI flag was
enabled/disabled as requested. Explicit recovery passed; all recorded settings
were unchanged, output remained off and the instrument error queue was clear.
This confirms delivery of this particular no-EOI query, not generic no-EOI
write support. The C/Python split and addressing behavior were left unchanged.
Two focused regressions cover EOI disabled on every write block and stopping
before the final EOI block when an intermediate completion fails. All **93
offline tests passed, zero skipped**. No native driver change was retained in
this check, so the existing sanitizer results were not represented as a new run.

GPIB permits transfers without EOI; the 2400 explicitly accepts LF, EOI or
LF+EOI as command terminators. EOI marks a message boundary, while DAV/NRFD/NDAC
perform byte handshakes. Our observed failure is the missing NI USB completion,
not a protocol prohibition. The driver uses the same EOI flag and real-completion
approach as linux-gpib; the inspected upstream has no workaround for this missing
response. The same adapter has not been tested under linux-gpib or official
NI-488.2 for comparison, and a firmware defect has not been established.
References: [NI manual, chapters 1 and 7](https://download.ni.com/support/manuals/370904a.pdf),
[2400 manual, §14](https://download.tek.com/manual/2400S-900-01_K-Sep2011_User.pdf),
[inspected linux-gpib source](https://sourceforge.net/p/linux-gpib/git/ci/e077ed19e2714678edf87c2662041dc9ea741ea5/tree/linux-gpib-kernel/drivers/gpib/ni_usb/ni_usb_gpib.c).

无 EOI 传输属于 GPIB 支持的情况，2400 也明确接受仅 LF 的命令终止方式。
本次异常是转接线缺少预期的 USB 写完成回包；linux-gpib 的同类代码也等待真实
完成状态，没有为这一现象提供绕过。尚未在同一转接线上完成 Linux/NI 官方驱动
对照，不能断言固件是根因。日常保留默认 LF+EOI 即可；无 EOI 和相关大写入仍
作为已知兼容限制记录，按实际需求继续研究。

### No-EOI completion research — 2026-11-02

Compared the official linux-gpib source and Linux mainline NI USB driver with
the EmbeddedCI user-space implementation and Gersoft's firmware workarounds.
Their standard write request uses the same EOI flag and twelve-byte completion
shape. Gersoft's missing-ACK workaround emulates success; this project does not
adopt that behavior.

Single-query experiments disabling interrupt monitoring, changing to the other
library's address order, splitting an identity query before its terminator, and
sending a USB zero-length packet did not produce a real no-EOI completion.
Read-only TNT register inspection did not yield usable transfer counters/chip
identification, so register-based success detection was rejected. A standalone
USB protocol termination-block experiment also failed and prevented subsequent
adapter initialization; STOP/drain and USB reset did not restore it. That
candidate was rejected. No source output was enabled or measurement settings
changed. Physical USB replug is required before further hardware checks.

The retained driver change only strengthens completion-frame validation:
status tag, requested-count bounds and the full termination block must all be
valid. The pinned upstream hashes and reproducible vendor patch are maintained.
**93 offline tests and native ASan/UBSan checks passed**, including missing,
truncated, corrupt and unrelated completions. The rebuilt driver's hardware
check is pending reconnection. Reliable no-EOI support remains unresolved.

### Documentation and installation ZIP — 2026-11-02 / 文档与安装包检查

- All **93 project offline tests passed, zero skipped**, after the documentation
  update. Native sources and the built development library still match the
  previously sanitizer-tested checkpoint; no new hardware checks were run.
- The revised default-Python commands passed on arm64 Python 3.11.6: update pip,
  setuptools and wheel in a fresh user package directory, then install the
  adjacent tar.gz using those tools (`--no-build-isolation`). Native loading,
  `pip check` and the installed import location passed outside the source tree.
  A temporary user-package prefix kept this check separate from existing user
  packages; no activation step was used.
- The ZIP contains exactly the installer, three guides, two license/credit
  files and internal checksums. Guide copies, checksums, Python example syntax,
  local document links and excluded-file checks passed. The inner installer is
  byte-for-byte identical to the original v0.1.0 archive; no development driver
  changes were added to that release.

本次 93 项离线测试全部通过；新的默认 Python 用户级安装命令、原生库加载和
依赖检查通过。安装 ZIP 的文档、校验及文件范围已核对，内层驱动安装包保持
原 v0.1.0。本次没有新增实物测试，也不将此前的硬件结果推广到新完成回包校验。
