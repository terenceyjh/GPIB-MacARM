# GPIB-MacARM: agent guide / Agent 使用指南

This is the **public, portable guide** shipped with the repository and release. Read [README.md](README.md) / [README.zh-CN.md](README.zh-CN.md), [test summary](docs/VALIDATION.md) and [architecture](docs/ARCHITECTURE.md) before changing the project. No private machine setup or credentials are needed.

本文件随仓库与 release 提供，可直接交给 agent。修改前先读中英文 README、测试概览和架构文档；这里不依赖开发者的本机环境或认证信息。

## Project / 项目定位

- Userspace GPIB driver + Python API for **Apple Silicon / ARM Macs**, primarily NI GPIB-USB-HS. Core driver credit: **KAME / linux-gpib**.
- Package/CLI: `gpib-macarm`; import: `gpib_macarm`; Python 3.10+. Early development, version 0.1.0.
- Tested instruments: **Keithley 2400 and SRS SR830**, not 2450. A successful build or skipped test is not hardware validation.
- `ResourceManager()` takes no `"@py"` backend argument. Keep default LF and **`send_end=True`**. No-EOI writes currently fail.
- 本项目针对 ARM Mac；通信测试不等于测量准确度通过，不要将离线测试或恢复成功写成所有硬件功能已通过。

## Install and verify / 安装与检查

Use arm64 Python and matching libusb. From the extracted source/repository directory:

```bash
xcode-select --install  # only if Command Line Tools are missing
brew install python libusb pkg-config
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
python -m gpib_macarm info
python -m pip check
```

A downloaded sdist can instead be installed with `python -m pip install ./gpib_macarm-0.1.0.tar.gz`. The package is not on PyPI. Source compilation needs the tools above; libusb is also needed at runtime. Use the selected interpreter's `python -m pip`, not an unrelated pip executable.

源码包可直接通过上述 pip 命令安装，不要假定 PyPI 上已有此包。先确认 Python 为 arm64；不要混用 Rosetta Python 与 ARM libusb，也不要复制其他机器的原生库或虚拟环境。

For development / 开发安装与检查:

```bash
python -m pip install --no-cache-dir --force-reinstall --no-deps -e .
python -m gpib_macarm info
python -m unittest discover -s tests -v
bash tools/test_native.sh
```

Rebuild after changing native C/C++, vendor code, build settings or the native ABI. Restart processes that loaded the old library. Native tests must actually run; report failures/skips honestly. `info` does not open an instrument; native offline tests enumerate an impossible adapter index without initializing actual hardware.

修改原生代码后必须重编译并重启已加载旧库的进程。修改 vendor 后同步维护本地哈希与补丁，保留固定上游版本、原始哈希和版权头，不自动更新到 upstream HEAD。

## Instrument use / 仪器操作

Confirm the model, actual primary address and intended commands before hardware work. `list` enumerates adapters; `list_resources()` lists interfaces, not instrument addresses. Opening a controller sends **REN/IFC**, affecting the shared bus; use one manager/controller per adapter. Do not infer permission to reset an instrument, change settings or enable output from permission to install software.

仪器操作前确认型号、真实地址和命令范围。软件安装本身不等于允许复位或开输出；按用户实际授权执行。只在没有其他采集占用转接线时进行硬件测试。

```bash
python -m gpib_macarm list
# Example only: replace 24 with the confirmed instrument address.
python -m gpib_macarm query --address 24 --timeout 10000 '*IDN?'
```

Timeout is in milliseconds per transfer, not a strict deadline for the complete query. Set it for the whole measurement's expected wait. Never automatically replay failed writes, triggers or measurements. I/O failures fault the shared controller; stop the failed batch. Explicit `recover(timeout=20000)` is verified only on the tested SR830 setup and can take longer than its first-stage wait. Reconfirm identity/settings and actual source output state before starting a new batch; clear/IFC/reopen are not universal recovery guarantees.

超时后停止失败批次，不自动重发命令。`recover()` 恢复通信不等于输出已关闭；恢复后核对身份、设置和实际状态，再开始新批次。`tools/keithley_2400_iv.py` 会复位、改设置并开启输出，故障复现脚本会故意制造超时，均不属于普通身份查询。

## Next development priorities / 下一步开发方向

1. **No-EOI writes:** isolate NI USB requests/completion status and GPIB handshakes; add a reproducer, fix the evidenced cause and verify on hardware. Then test large writes with EOI only on the last chunk. Do not call this supported merely because fake-backend tests pass.
2. **Recovery coverage:** retest the 2400, unplug/power loss, different firmware and status-byte behavior. Preserve the original failure and avoid stale replies or command replay.
3. **Transfer and acquisition coverage:** binary transfers, larger messages, longer runs and multiple instruments on one bus.
4. **Distribution:** cross-machine ARM Mac installs, more macOS/Python combinations and macOS CI.

对应重点：无 EOI 写入及分块写入 → 扩展异常恢复 → 二进制与长期/多仪器采集 → 安装兼容性和 CI。Intel Mac 不属于当前验收范围。

Keep C ABI signatures and ctypes declarations aligned; no C++ exceptions may cross the ABI. Preserve NUL/CR/LF in raw data; never silently truncate an over-limit reply. Hold the shared controller lock across complete queries. Changes to message boundaries, native parsing and fault handling need meaningful regression checks.

## Ready-to-use prompts / 可直接使用的 prompts

### Install / 安装

> Read CLAUDE.md and the README. Install GPIB-MacARM in a new arm64 Python environment using pip from the provided source archive/folder. Check Python/libusb architecture, native info and pip check. Report the interpreter and result. Do not access instruments yet.
>
> 请阅读 CLAUDE.md 和 README，用提供的源码包/目录，通过 pip 在新的 arm64 Python 环境安装；核对 Python/libusb 架构、native info 和 pip check，报告解释器与结果。先不访问仪器。

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

Ship portable source, licenses, concise docs and this guide. Do not publish local agent handoffs, authentication material, environments, build outputs, serial numbers, hardware reports or measurement data. Keep detailed development/test evidence in ignored local storage. Use `tools/make_delivery.py` for the curated source ZIP; inspect both ZIP and sdist contents before distribution. Publishing to a service is separate from building local release files.

公开版本保留通用使用说明和简要测试概览；本机 agent 交接、认证材料、详细测试记录及测量数据不进入仓库或 release。打包后检查实际文件清单。
