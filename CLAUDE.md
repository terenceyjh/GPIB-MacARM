# GPIB-MacARM: agent guide / Agent 使用指南

This is the **public, portable guide** shipped with the repository and release. Read [README.md](README.md) / [README.zh-CN.md](README.zh-CN.md), [test summary](docs/VALIDATION.md) and [architecture](docs/ARCHITECTURE.md) before changing the project. The installation ZIP has its own end-user guide in `release/CLAUDE.md`, copied beside its installer archive. No private machine setup or credentials are needed.

本文件随仓库与 release 提供，可直接交给 agent。修改前先读中英文 README、测试概览和架构文档；这里不依赖开发者的本机环境或认证信息。

## Project / 项目定位

- **GPIB communication on Apple Silicon / ARM Macs** is the project goal. The userspace C/C++ driver currently exposes a C ABI, Python bindings and a CLI, primarily for NI GPIB-USB-HS. Core driver credit: **KAME / linux-gpib**.
- Package/CLI: `gpib-macarm`; import: `gpib_macarm`; Python 3.10+. Early development, version 0.1.0.
- Tested instruments: **Keithley 2400 and SRS SR830**, not 2450. A successful build or skipped test is not hardware validation.
- `ResourceManager()` takes no `"@py"` backend argument. Keep default LF and **`send_end=True`**. No-EOI writes currently fail.
- 本项目首先是 Apple Silicon Mac 上的 GPIB 驱动，目前主要提供 Python 接口；通信测试不等于测量准确度验收，不要将离线测试或恢复成功写成所有硬件功能已通过。

## Install and verify / 安装与检查

Use arm64 Python and matching libusb. From the extracted source/repository directory:

```bash
xcode-select --install  # only if Command Line Tools are missing
brew install python libusb pkg-config
python3 -c 'import platform, sys; print(platform.machine()); print(sys.executable)'
python3 -m pip install --user --break-system-packages --upgrade pip setuptools wheel
python3 -m pip install --user --break-system-packages --no-build-isolation .
python3 -m gpib_macarm info
python3 -m pip check
```

A downloaded sdist can instead be installed with `python3 -m pip install --user --break-system-packages --no-build-isolation ./gpib_macarm-0.1.0.tar.gz`. The package is not on PyPI. Source compilation needs the tools above; libusb is also needed at runtime. Install into the default arm64 Python's user package directory with `--user --break-system-packages`; do not use sudo. Use the same interpreter for pip and execution. See [pip options](https://pip.pypa.io/en/stable/cli/pip_install/).

源码包可直接通过上述 pip 命令安装，不要假定 PyPI 上已有此包。先确认 Python 为 arm64；不要混用 Rosetta Python 与 ARM libusb，也不要复制其他机器的原生库或虚拟环境。

For development / 开发安装与检查:

```bash
python3 -m pip install --user --break-system-packages --no-build-isolation --no-cache-dir --force-reinstall --no-deps -e .
python3 -m gpib_macarm info
python3 -m unittest discover -s tests -v
bash tools/test_native.sh
```

Rebuild after changing native C/C++, vendor code, build settings or the native ABI. Restart processes that loaded the old library. Native tests must actually run; report failures/skips honestly. `info` does not open an instrument; native offline tests enumerate an impossible adapter index without initializing actual hardware.

修改原生代码后必须重编译并重启已加载旧库的进程。修改 vendor 后同步维护本地哈希与补丁，保留固定上游版本、原始哈希和版权头，不自动更新到 upstream HEAD。

## Instrument use / 仪器操作

Confirm the model, actual primary address and intended commands before hardware work. `list` enumerates adapters; `list_resources()` lists interfaces, not instrument addresses. Opening a controller sends **REN/IFC**, affecting the shared bus; use one manager/controller per adapter. Do not infer permission to reset an instrument, change settings or enable output from permission to install software.

仪器操作前确认型号、真实地址和命令范围。软件安装本身不等于允许复位或开输出；按用户实际授权执行。只在没有其他采集占用转接线时进行硬件测试。

```bash
python3 -m gpib_macarm list
# Example only: replace 24 with the confirmed instrument address.
python3 -m gpib_macarm query --address 24 --timeout 10000 '*IDN?'
```

Timeout is in milliseconds per transfer, not a strict deadline for the complete query. Set it for the whole measurement's expected wait. Never automatically replay failed writes, triggers or measurements. I/O failures fault the shared controller; stop the failed batch. Explicit `recover(timeout=20000)` is verified on the tested SR830 setup and, in unreleased development, the 2400 setup; it can take longer than its first-stage wait. Reconfirm identity/settings and actual source output state before starting a new batch; clear/IFC/reopen are not universal recovery guarantees.

超时后停止失败批次，不自动重发命令。`recover()` 恢复通信不等于输出已关闭；恢复后核对身份、设置和实际状态，再开始新批次。`tools/keithley_2400_iv.py` 会复位、改设置并开启输出，故障复现脚本会故意制造超时，均不属于普通身份查询。

## EOI compatibility / EOI 兼容限制

Keep default LF + `send_end=True`. GPIB allows no-EOI transfers; the 2400 explicitly accepts LF-only command termination. On the tested combination, LF+EOI and EOI-only identity queries passed, but an LF-only/no-EOI query produced a correct instrument reply while its USB write-completion response was missing. The driver therefore reports a timeout. This does not establish a protocol restriction or a proven firmware defect.

默认 LF+EOI 已验证可用。无 EOI 是协议允许、2400 也支持的用法；当前问题是缺少转接线的可靠 USB 写完成确认，根因尚未确定。沿用 linux-gpib 的标志及真实完成回包处理，不伪造确认，不因 USB OUT 成功或一次查询有回复就认定通用写入成功，不自动重放命令。超过 65535 字节的写入因中间块不发 EOI 而仍不支持；大读取已经单独验证。

The completion-frame validation added on 2026-11-02 passed offline/native checks; its rebuilt hardware check remains pending. It does not fix missing completions. Preserve the working C/Python split, chunking and addressing unless a demonstrated failure requires a focused change. Protocol references: [NI termination guide, chapter 7](https://download.ni.com/support/manuals/370904a.pdf), [2400 manual, §14](https://download.tek.com/manual/2400S-900-01_K-Sep2011_User.pdf).

## Possible further work / 未来可继续开发与测试

These are candidate directions, not a requirement to expand every task. Default-EOI use need not wait for a no-EOI workaround.

1. **EOI:** when needed, compare the same adapter under official NI-488.2 with the current implementation, identify a reliable no-EOI completion mechanism, then validate final-chunk-only EOI large writes. Retain failures when confirmation is absent.
2. **More hardware:** test additional instruments and adapter models/firmware, including identity, text/raw transfers and appropriate recovery. The current tested instruments are 2400 and SR830; do not infer other-model compatibility.
3. **Multiple instruments:** use at least two real devices at distinct confirmed addresses on one bus; verify interleaved complete queries, partial-reply isolation and shared-controller failure/recovery. Two sessions to one device do not establish this coverage.
4. **Mac coverage:** test more Apple Silicon machines, macOS and Python combinations when requested. Intel Mac is outside the current target; CI/distribution expansion is optional future work.

未来方向为无 EOI 完成确认、更多仪器/固件、真实多仪器共线，以及更多 ARM Mac 环境。按实际需求选择，不为了补齐清单反复修改可用功能。

## Current evidence / 当前验证范围

The development tree passed single-2400 USB/power recovery, timeout/partial/over-limit recovery, large ASCII/binary reads and a one-hour / 10040-point acquisition. **93 offline tests and native ASan/UBSan checks passed.** No-EOI support, dependent large writes, real multi-instrument operation and measurement accuracy remain unvalidated. See [test results](docs/VALIDATION.md) and [bench instructions](docs/BENCH_TESTS.md) for the tested revisions and limits.

开发测试与已发布版本必须分开：v0.1.0 安装 ZIP 的外层文档已更新，内层驱动源码包沿用原版；后续驱动改动未进入该安装包。最新完成回包校验尚待实物复验，不能把此前的采集结果写成对这一改动的验证。

Keep C ABI signatures and ctypes declarations aligned; no C++ exceptions may cross the ABI. Preserve NUL/CR/LF in raw data; never silently truncate an over-limit reply. Hold the shared controller lock across complete queries. Changes to message boundaries, native parsing and fault handling need meaningful regression checks.

## Ready-to-use prompts / 可直接使用的 prompts

### Install / 安装

> Read CLAUDE.md and the README. Install GPIB-MacARM into the default arm64 Python's user package directory using pip from the provided source archive/folder. Check Python/libusb architecture, native info and pip check. Report the interpreter and result. Do not access instruments yet.
>
> 请阅读 CLAUDE.md 和 README，用提供的源码包/目录，通过 pip 安装到默认 arm64 Python 的用户包目录；核对 Python/libusb 架构、native info 和 pip check，报告解释器与结果。先不访问仪器。

### First communication / 首次通信

> My instrument is [model], GPIB address [address]. Confirm the adapter, then perform a supported read-only identity query with default EOI. Normal REN/IFC initialization is allowed; do not reset, configure measurements or enable output. Save hardware identifiers and detailed logs locally.
>
> 仪器是【型号】，GPIB 地址为【地址】。先确认转接线，再用默认 EOI 做仪器支持的只读身份查询；允许正常 REN/IFC 初始化，不复位、不配置测量、不开输出。硬件标识与详细日志留在本地。

### Migrate a script / 迁移脚本

> Migrate [script] from basic PyVISA GPIB calls to gpib_macarm. Preserve instrument commands, ordering and data format; replace ResourceManager("@py") with ResourceManager(). Check unsupported APIs, per-batch timeouts and failure cleanup. Verify offline first; hardware execution is limited to my stated scope.
>
> 将【脚本】中的基础 PyVISA GPIB 调用迁移为 gpib_macarm，保持仪器命令、顺序和数据格式，使用无参数 ResourceManager()；核对不支持的接口、批次超时和异常清理，先离线检查，实物运行限于我明确指定的范围。

### Continue development / 继续开发

> Investigate [issue] against the current test summary. Reproduce the failure, make a focused fix and rebuild if native code changes. Run relevant offline/native checks. State exactly which hardware checks ran and what remains unverified. Update public summaries briefly; keep detailed logs and device information local.
>
> 根据测试概览定位【问题】，先复现，再做针对性修复；涉及原生代码时重建。运行相关离线/原生检查，明确实测与未验证范围。公开文档只记简要结论，详细日志和设备信息留本地。

## Public vs local files / 公开与本地文件

Ship portable source, licenses, concise docs and this guide. Do not publish local agent handoffs, authentication material, environments, build outputs, serial numbers, hardware reports or measurement data. Keep detailed development/test evidence in ignored local storage. Use `tools/make_delivery.py` to bundle an existing `dist/gpib_macarm-0.1.0.tar.gz` with the guides in `release/`. The result is one installation ZIP; publish that ZIP rather than a standalone tar.gz. `--source` builds an optional developer source ZIP. Inspect outer ZIP and inner sdist contents before distribution. Publishing to a service is separate from building local release files.

公开版本保留通用使用说明和简要测试概览；本机 agent 交接、认证材料、详细测试记录及测量数据不进入仓库或 release。打包后检查实际文件清单。
