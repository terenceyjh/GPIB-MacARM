# GPIB-MacARM 0.1.0 — agent installation & troubleshooting guide

# Agent 安装、使用与排错指南

This guide belongs to the **installation ZIP**, not an unpacked source checkout. It is beside `README.md`, `README.zh-CN.md` and **`gpib_macarm-0.1.0.tar.gz`**. Read the README first. You may give this file directly to an agent.

本文件与中英文 README、`gpib_macarm-0.1.0.tar.gz` 位于同一文件夹，可以直接交给 agent。这里是**安装包外层目录**，没有 `pyproject.toml`；安装时指定 tar.gz，不能在这里执行 `pip install .`。

## 1. Scope / 项目与版本

GPIB-MacARM brings **GPIB instrument communication to Apple Silicon Macs**, primarily through NI GPIB-USB-HS. The userspace C/C++ driver currently provides Python bindings and a CLI through a C ABI. **Core driver credit: [KAME](https://github.com/northriv/KAME) / [linux-gpib](https://linux-gpib.sourceforge.io/).** No NI-488.2, NI-VISA, kernel extension or background service is required.

- Distribution/CLI: `gpib-macarm`; Python import: `gpib_macarm`; version: `0.1.0`, early development.
- Requirements: Apple Silicon Mac, arm64 Python 3.10+, matching arm64 libusb, C/C++ build tools and pkg-config.
- Tested hardware: NI GPIB-USB-HS (`3923:709b`) with **Keithley 2400**, and with **SRS SR830**, on macOS 14.8.9 arm64.
- 2450, Intel Mac, other adapters/firmware and all VISA functionality are not validated by these tests. Successful transport does not certify measurement accuracy.

本包针对 ARM Mac；型号为 **2400，不是 2450**。提供有限的 VISA 风格 API，并非注册到 PyVISA 的后端。安装成功或离线测试通过不等于已完成用户仪器的实测。

## 2. Install / 详细安装

Install into the default arm64 Python's user package directory, using the same interpreter for installation and execution. If the user explicitly selects another interpreter, respect that choice. First prepare the build tools:

```bash
xcode-select --install  # skip if installed; complete the installer before continuing
brew install python libusb pkg-config
python3 -c 'import platform, sys; print(platform.machine()); print(sys.executable)'
```

Expected architecture is `arm64`, Python 3.10+. A Rosetta x86_64 Python cannot use arm64 libusb. 用户默认使用 ARM Python 的用户包目录；先按 Homebrew 官网准备好 Homebrew，再检查 Python 与 libusb 架构一致。

In Terminal, enter the extracted installation folder and verify these files exist:

```bash
pwd
ls README.md README.zh-CN.md CLAUDE.md gpib_macarm-0.1.0.tar.gz
```

Then install **the adjacent archive**, without extracting it:

```bash
python3 -m pip install --user --break-system-packages --upgrade pip setuptools wheel
python3 -m pip install --user --break-system-packages --no-build-isolation ./gpib_macarm-0.1.0.tar.gz
python3 -m gpib_macarm info
python3 -m pip check
python3 -m pip show gpib-macarm
```

Expected: version `0.1.0`, `arm64`, an existing native-library path and no broken requirements. `info` loads the driver but does not open an instrument. Keep libusb installed at runtime. The package is not on PyPI. pip may download build dependencies; the archive already contains the driver source, so no separate KAME checkout is needed.

预期结果：版本 `0.1.0`、架构 `arm64`、可加载的原生库、无损坏依赖。项目不在 PyPI，不要用 `pip install gpib-macarm` 替代安装本地 tar.gz，也不要复制别人的 `.dylib`。

`--user --break-system-packages` permits user-directory installation with Homebrew Python; do not use sudo or change global pip configuration. Use the same `python3` in new terminals and your IDE. Check integrity with `shasum -a 256 -c SHA256SUMS.txt` in this folder. See [pip options](https://pip.pypa.io/en/stable/cli/pip_install/).

无需额外激活步骤；运行脚本和 IDE 都使用上述 `python3`。通过 `python3 -m pip` 安装，避免解释器与安装目标不一致。

## 3. First communication / 首次连接

Before instrument access, confirm the model, actual primary address and intended commands. Close other acquisition programs using the adapter. Installation permission does not itself authorize resets, configuration changes or source output. `list` only enumerates USB adapters:

```bash
python3 -m gpib_macarm list
```

With the actual address confirmed, perform a supported read-only identity query:

```bash
# 24 is an example, not an address scan / 24 只是示例，请使用真实地址
python3 -m gpib_macarm query --address 24 --timeout 10000 '*IDN?'
```

Opening a controller sends **REN/IFC**, affecting the shared bus. The identity command does not reset instruments or enable outputs. `list_resources()` lists adapter interfaces, not instrument addresses. Keep **LF + EOI** defaults and **`send_end=True`**.

确认仪器型号、面板 GPIB 地址与操作范围后再连接；打开控制器会影响共享总线。身份查询不应改量程、复位或开输出。不要扫描地址来代替核对面板。

## 4. Python usage / Python 用法

```python
import gpib_macarm as visa

with visa.ResourceManager() as rm:
    with rm.open_resource(
        "GPIB0::24::INSTR",    # index 0, address 24; use the actual values
        timeout=10000,         # milliseconds
        write_termination="\n",
        read_termination="\n",
        send_end=True,
    ) as instrument:
        print(instrument.query("*IDN?"))
        # Equivalent split write/read / 等价的分步写入、读取：
        instrument.write("*IDN?")
        print(instrument.read())
```

Share one manager/controller per adapter; open several resources through it. If enumeration order varies, pass `serial="YOUR_ADAPTER_SERIAL"` to `open_resource()`. `with` closes sessions and releases the adapter; it does not promise to turn off an instrument output.

| API / 参数 | Meaning / 含义 |
| --- | --- |
| `write(str)`, `read()`, `query(str)` | Text commands/replies; ASCII by default / 默认 ASCII 文本通信 |
| `query_ascii_values(command)` | Delimited numeric reply as a list / 将数值回复解析为列表 |
| `write_raw(bytes)`, `read_raw()`, `read_bytes(n)` | Preserve binary bytes; coverage is limited / 保留原始字节，实物验证有限 |
| `timeout` | Milliseconds per transfer; allow enough time for the measurement / 每次传输超时，单位毫秒 |
| `query_delay` | Seconds between writing a query and reading / 查询写入后到读取的等待，单位秒 |
| `send_end` | Keep `True`; EOI on the last byte / 保持 True，末字节发送 EOI |
| `chunk_size`, `max_read_bytes` | Read chunk size (4096 default), reply limit (1 MiB default) / 读取分块和整条回复上限 |
| `read_stb()`, `clear()` | Serial poll; selected device clear, not SCPI reset / 串行轮询；设备清除，不是 SCPI 复位 |
| `recover(timeout=20000)` | Explicit shared-controller recovery; see limits below / 显式恢复共享控制器，限制见下文 |

For basic PyVISA scripts use `import gpib_macarm as pyvisa` and **`ResourceManager()` without `"@py"`**. Remove serial-port-only settings. Preserve instrument commands/order/data format and adjust timeouts for full measurement batches. TCP/IP, USBTMC, VISA events, secondary addresses and binary-block convenience parsers are outside this API.

迁移时只替换通信接口，不顺手更改仪器流程；量程、触发、输出和异常清理按仪器手册及用户授权处理。raw API 保留字节，不代表二进制测量或大写入已通过实物验证。

## 5. Known issues and workarounds / 已知问题及处理办法

| Symptom / 问题 | Current response / 当前处理办法 |
| --- | --- |
| Writes time out with EOI disabled / 关闭 EOI 写入超时 | **Keep `send_end=True` and normal LF termination.** No-EOI writes remain unfixed. Large writes over 65535 bytes need intermediate no-EOI chunks and are not hardware-validated. / 保持默认 EOI；这不是已修复的功能，大数据分块写入也不能宣称可用。 |
| `SessionFaultedError` after a timeout / 超时后会话锁止 | Stop the failed batch. Do not immediately reuse/reopen/retry commands. Explicit recovery is tested on the current SR830 combination only; verify identity/settings afterward. / 停止批次，按下方流程显式恢复，不直接重发。 |
| A new write/poll/clear is refused after `read_bytes()` / 部分读取后拒绝新操作 | The earlier reply has not ended. Finish reading it, or deliberately discard it via explicit recovery before new commands. / 先读完旧回复，或显式恢复丢弃；不要把残留回复当成新数据。 |
| Slow measurement times out / 长测量超时 | Increase `timeout` for the instrument's full batch duration. It is per transfer, not an exact whole-query deadline. / 按整批时长设置，不照搬身份查询的超时。 |
| Source output state is unknown / 输出状态不明 | Stop acquisition and check the actual instrument state. Closing, clearing or recovering communication does not prove output is off. / 核对真实输出；恢复通信不等于关输出。 |
| `ModuleNotFoundError` / 无法导入 | Inspect `sys.executable` and `python3 -m pip show gpib-macarm`; use the interpreter that installed the package. / 核对解释器和安装目标。 |
| Native architecture/library error / 架构不兼容或找不到库 | Use arm64 Python + arm64 Homebrew libusb; check any `GPIB_MACARM_LIBRARY` override. Reinstall in the intended environment. / 统一架构并重新安装，不手动复制原生库。 |
| libusb headers/compiler missing / 缺头文件或编译器 | Finish Command Line Tools installation; install `libusb pkg-config`; check `pkg-config --modversion libusb-1.0`. / 补齐构建工具。 |
| Native driver older than Python API / 原生库与 Python API 不匹配 | Restart processes and reinstall this archive with `python3 -m pip install --user --break-system-packages --no-build-isolation --no-cache-dir --force-reinstall --no-deps ./gpib_macarm-0.1.0.tar.gz`. / 重装并重启已加载旧库的进程。 |
| `list` is empty / 找不到转接线 | Check USB connection, macOS accessory permission and adapter model. / 检查线缆与访问权限；不代表支持任意 USB 转接线。 |
| USB busy/access denied / 设备被占用或拒绝访问 | Close other users of the adapter and check competing drivers/accessory permission. / 排查其他控制程序或驱动，不通过关闭系统安全机制解决。 |
| Adapter appears but no identity reply / 找到线缆但无回复 | Check power, GPIB interface, actual address, instrument-supported query and LF + EOI. Stop on failure; do not repeatedly send queries. / 核对仪器配置与终止方式，失败后停止。 |

### What the EOI issue means / EOI 问题的含义

GPIB permits data transfers without EOI: byte acceptance uses DAV/NRFD/NDAC handshakes, while EOI marks a message boundary. The 2400 also accepts LF alone to end a command. Our LF+EOI and EOI-only identity queries passed; with LF-only/no EOI, the instrument produced the original correct reply, but the expected USB write-completion response was missing and the driver timed out. The cause remains unresolved; do not call it a GPIB restriction or a proven adapter firmware defect. See [NI's handshake/termination explanation](https://download.ni.com/support/manuals/370904a.pdf) and [2400 manual, §14](https://download.tek.com/manual/2400S-900-01_K-Sep2011_User.pdf).

无 EOI 是协议支持的正常操作。当前兼容问题位于可靠写完成确认：收到某条查询的回复只能证明该次命令送达，不能代替所有写操作的完成确认。与 linux-gpib 一样，驱动设置 EOI 标志并等待真实 USB 完成状态；缺少回包不当作成功，不自动重发。默认 LF+EOI 可正常使用；超过 65535 字节的大写入依赖无 EOI 中间块，仍未支持。大读取与大写入要分别看待。

### Explicit recovery / 显式恢复细节

A failed I/O faults every resource on the shared controller and preserves the original error. Do not replay failed writes/triggers/measurements: the instrument might already have executed them. Stop acquisition first and keep the original manager/resource open if attempting explicit recovery.

在**仍打开的原会话作用域内**，停止失败批次后，可按当前仪器的已验证范围显式调用：

```python
instrument.recover(timeout=20000)
print(instrument.query("*IDN?"))
# Recheck settings/output before a NEW run; never resume the old failed batch.
```

`timeout=20000` bounds the first late-completion receive, not the total recovery duration. Recovery discards queued replies, sends bus/device clear operations and checks cached identity when available. Default MAV bit 4 assumes IEEE-488.2 status. Failure keeps the controller faulted. Known SR830 faults recovered in testing; 2400 retests, unplug/power loss and nonstandard status bytes remain unfinished. No-EOI write failure recovery does **not** fix no-EOI writing.

恢复可能等待较久并清除旧回复，影响仪器操作；默认 MAV 语义不能随意推广到所有仪器。尚未在当前仪器验证时，不声称恢复保证成功。没有缓存身份时，应按仪器支持的方式自行核对身份/状态。不要自动恢复后继续旧批次。

## 6. Test scope and further work / 测试范围与未来方向

This ZIP's guides were updated on 2026-11-02; its inner driver source archive and v0.1.0 tag are unchanged. Released-version tests cover repeated 2400/SR830 communication, finite 2400 acquisition, and a 42-minute SR830 scan with tested fault recovery. Single-2400 USB/power recovery, large binary reads and a one-hour / 10040-point run passed on later development revisions, **not this installer's driver**. The latest development completion-frame validation passed 93 offline tests and native ASan/UBSan, but its hardware recheck is pending. Detailed version-specific results are in the [public test record](https://github.com/terenceyjh/GPIB-MacARM/blob/main/docs/VALIDATION.md).

本安装包沿用原 v0.1.0 驱动；后续开发结果不自动归属于它。测量准确度、无 EOI、依赖无 EOI 的大写入、更多设备/固件及真实多仪器共线尚未验收。

Possible future work, selected according to actual need:

1. **No-EOI completion:** compare the same adapter with official NI-488.2, identify a reliable completion mechanism, then test final-chunk-only EOI writes. Normal default-EOI use need not wait for this.
2. **More hardware:** test additional instruments and adapter models/firmware, including appropriate error recovery.
3. **Multiple instruments:** verify complete interleaved queries, reply isolation and shared-controller fault/recovery using at least two real devices with distinct confirmed addresses.
4. **More ARM Macs:** broaden macOS/Python and installation coverage when requested; Intel Mac is outside the current target.

未来可继续测试 EOI、更多仪器/转接线和真实多设备共线；保留已正常工作的 C/Python 分层与分块方式，按实际问题做针对性修改。

For development, obtain the repository/source checkout rather than editing this outer installation folder. Install its source into the selected interpreter and run:

```bash
python3 -m pip install --user --break-system-packages --no-build-isolation --no-cache-dir --force-reinstall --no-deps -e .
python3 -m unittest discover -s tests -v
bash tools/test_native.sh
```

Read the source tree's own `CLAUDE.md` and architecture/test summary before edits. Rebuild after native changes and restart processes. Keep ABI declarations aligned, preserve raw bytes and message limits, lock complete queries and never auto-replay failed writes. Vendor edits require provenance hashes/patch updates. Preserve existing commits. Public summaries should be brief; private logs, hardware identifiers, measurements and credentials stay local.

源码安装自带另一份开发向 `CLAUDE.md`；修改前阅读。无 EOI 功能须有实物证据，不能以 fake backend 或跳过测试代替；维护上游版权、许可与来源。

## 7. Prompt to give an agent / 可直接交给 agent 的 prompt

> Read this CLAUDE.md and the adjacent README. Install the adjacent gpib_macarm-0.1.0.tar.gz into the default arm64 Python's user package directory, verify architecture, native info and pip check. Report the interpreter and result. Do not access instruments yet. For later communication, confirm the model/address and command scope; preserve default EOI and apply the known-issue workarounds above.
>
> 请阅读本文件及同文件夹的 README，在默认 arm64 Python 的用户包目录安装旁边的 gpib_macarm-0.1.0.tar.gz，核对架构、native info 和 pip check，报告解释器与结果。先不访问仪器。后续连接前确认型号、地址与操作范围，保留默认 EOI，按上面的已知问题处理办法操作。
