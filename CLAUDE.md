# GPIB-MacARM — 开发交接与可复用 prompts

这是开发交接文件。先阅读 README.md、docs/ARCHITECTURE.md、docs/VALIDATION.md 和本文件，再继续修改。不要将“代码存在”“测试被跳过”或“Linux 测试通过”写成“Mac/硬件已经通过”。

## 项目目标与命名

- 项目/仓库：GPIB-MacARM。
- Python distribution / CLI：gpib-macarm。
- Python import：gpib_macarm。
- 自定义原生库环境变量：GPIB_MACARM_LIBRARY。
- 目标：Apple Silicon Mac 上，用真品 NI GPIB-USB-HS 做基础 SCPI，供现有 Python 采集脚本使用；提供有限的 PyVISA 风格接口。
- 版本：0.1.0，早期开发。GPL-2.0-or-later；保留 KAME/linux-gpib 版权头、AUTHORS、COPYING、来源哈希和本地补丁。

## 已完成什么

2026-10-30，先审查了 ni-gpib-usb-hs 与 KAME，然后选择提取 KAME 用户态核心。当前仓库独立于原始工作目录，不需要原 KAME 仓库即可编译安装。

1. 提取 KAME 的 NI USB-GPIB C 驱动、POSIX/libusb 兼容层和必要头文件。没有引入 Qt、完整 KAME、STM、内存池、MCP 或其他后台服务。
2. 增加 native/driver.cpp C ABI、标准库 ctypes 绑定和 Controller/Instrument/ResourceManager。
3. 支持文本 write/read/query、原始字节、分块完整读取、EOI/EOS、超时、query_delay、整次 query 的共享控制器锁、串行轮询和总线控制。
4. 加固短/畸形读回包、错误状态、残余计数；把 USB 超时传到 libusb；保留超时/拔除错误身份；处理 interrupt 线程的取消与重复启动；异常时清除 EOS。
5. 提供 CLI、SCPI/CSV 示例、hardware_smoke.py、离线单元测试、sanitizer 测试、独立编译与源码压缩包工具。
6. 统一使用 gpib-macarm / gpib_macarm；README 有英文入口和中文说明，记录了 KAME/linux-gpib 来源。

上游固定来源：

- KAME：https://github.com/northriv/KAME ，提交 f451025dc4215c5d85f39b71303f9008ccee66bc。
- 子目录 modules/charinterface/usermode-linux-gpib。
- KAME 携带 linux-gpib 4.3.6 / git 9813ff8f。
- UPSTREAM.json 记录原始与本地文件哈希；vendor/local-fixes.patch 记录实际修复。

vendor/kame/NiGpibDriver.* 作为上游参考保留，不参与本包构建；本包实际包装位于 native/driver.cpp。vendor/kame/win_compat.h 也是保留的上游文件，不意味着当前支持 Windows 原生安装。

## 真实验证边界

已验证：Windows Python 3.14 的纯 Python 测试；WSL2 Linux x86_64 / Python 3.10.12 / GCC 11.4 的原生编译、加载、wheel/源码 zip 构建与项目内独立安装。Linux 30 项 unittest 全通过，包含 22 项 API、2 项交付/来源完整性、6 项原生解析器/C ABI 测试。ASan/UBSan 覆盖 20,000 个畸形/短回包，以及模拟 URB 的动态超时和错误映射。

### 本次 Mac 离线测试结果（2026-10-31）

- 环境：macOS 14.8.9（23J631）/ arm64 / Python 3.11.6 / Apple Clang 15.0.0 / Homebrew libusb 1.0.30，Python 与 libusb 架构一致。
- 构建与加载：在项目 `.venv` 中完成 editable 编译安装；ctypes 成功加载 arm64 原生库；`python -m gpib_macarm info` 与 `gpib-macarm info` 均成功，`pip check` 通过。无需修改构建脚本、协议或 vendor。
- 完整 unittest：30 项通过，0 失败、0 跳过；包括 22 项 Python API、2 项交付/来源完整性和 6 项实际运行的原生解析器/C ABI 测试。
- ASan/UBSan：`bash tools/test_native.sh` 的两个程序均通过；覆盖 20,000 个畸形/短回包，以及模拟 bulk URB 的 32000 ms 超时传递、USB timeout/no-device 错误映射和完成回调，未报告 sanitizer 错误。
- 本轮未运行 `list`、仪器查询或 hardware smoke，未打开实际适配器、未发送 REN/IFC。原生测试仅用不存在的设备 index 检查枚举错误路径。这些结果只证明本机编译、加载及离线行为通过。
- 本地证据：`build/validation/mac-build.log`、`mac-info.log`、`mac-unittest.log`、`mac-sanitizers.log`；完整记录见 [docs/VALIDATION.md](docs/VALIDATION.md)。日志和本机二进制不提交到 Git。

### 尚未验证

尚未验证：Intel Mac、其他 macOS/Python 组合、Mac 非 editable 安装、真实 NI 适配器/仪器、首次冷启动寻址、REN/IFC、终止符、长期采集和拔插/断电恢复。本轮 Mac 只做离线验收，未打开适配器或执行仪器查询。Linux USB 枚举为空，不能把它写成实物通信成功。

2026-10-30 重命名后已再次完成 Linux 原生构建、30 项测试、sanitizer 检查和新包名的源码 zip/wheel 独立安装；CLI 与导入名也已核对。最终事实以 docs/VALIDATION.md 和实际执行结果为准。

## 下一步：实际连接设备做通信测试

本机 Mac 构建与离线验收已完成。下一步需要实际连接 NI GPIB-USB-HS 转接线和一台已知仪器，验证 USB → GPIB → 仪器的真实通信；在取得实物回包前，不得将项目标记为已通过硬件验收。

1. 先确认用户选择的仪器型号、真实 GPIB 主地址、转接线序列号（可选），并按仪器手册确定查询命令、终止符与超时；不要把示例地址 22 当成实际地址。
2. 插入适配器并连接仪器，先运行 `python -m gpib_macarm list`，记录 VID/PID、型号和序列号，确认 USB 访问权限。枚举成功只证明发现设备。
3. 按 [docs/MAC_ACCEPTANCE.md](docs/MAC_ACCEPTANCE.md) 使用真实地址完成一次 `*IDN?` 身份查询；不支持该命令的仪器使用手册规定的只读查询。打开会话会发送 REN/IFC；不发送 `*RST`、不开启输出、不修改量程。
4. 身份查询成功后，运行 `tools/hardware_smoke.py`，使用同一只读查询做 100 次连续通信测试，保存本地 `hardware-smoke.json`，检查回复非空、身份一致、无超时，并记录环境及时延。
5. 再验证慢查询、完整长回复、超时及拔插/断电后的恢复；仅将实际完成的项目写入验证记录。硬件报告对外提交前先检查设备信息。
6. 基础通信稳定后接入用户实际采集脚本，只迁移通信接口，保持仪器命令和测量流程不变，再考虑固定版本和增加 macOS/Linux CI。

在其他 Mac 上复现或修改原生代码后，仍需先检查系统、Python、Homebrew、libusb 架构，重建并运行 `info`、完整离线测试和 `tools/test_native.sh`，确认原生测试实际执行而非跳过。

不要默认刷新 vendor 到 upstream HEAD。不要为修复构建而关闭系统安全机制、安装 NI 内核驱动，或引入新的常驻服务。USB-B 固件加载和初始 PID 761e 的 HS+ 初始化不属于当前包。

## 构建与测试命令

```bash
brew install python libusb pkg-config
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m gpib_macarm info
python -m unittest discover -s tests -v
bash tools/test_native.sh
```

修改 C/C++ 或兼容层后必须重建；若 editable 安装未更新原生库，可执行：

```bash
python -m pip install --no-cache-dir --force-reinstall --no-deps -e .
```

只有显式选择了实际仪器后才运行：

```bash
python -m gpib_macarm list
python -m gpib_macarm query --address 22 '*IDN?'
python tools/hardware_smoke.py --address 22 --count 100 --output hardware-smoke.json
```

22 仅为示例地址。打开 Controller/open_resource 会初始化适配器并发送 REN/IFC；不会自动发 *RST。写入不能盲目自动重试，失败时仪器可能已经执行过命令。

## 修改代码时的重要约束

- 一个适配器共用一个 Controller/ResourceManager；锁住完整 query，不只锁 USB 单次传输。
- 原生 C ABI 不允许 C++ 异常跨边界；ctypes argtypes/restype 与 C 签名必须一致。
- C 文件以 GNU C11 编译，C++ 文件以 GNU C++17 编译。保留二进制 NUL、末尾换行和 END/EOS，不要用 strip() 处理 raw 数据。
- 超过 max_read_bytes 必须报错，不能静默截断。硬件超时是离散档位，不能宣称它是整个 query 的精确截止时间。
- 不要将此项目宣传成完整 VISA 后端；没有二级地址、VISA events 或二进制块便利 API。
- 原生库仅支持 macOS/Linux 构建。不要把本机 .so/.dylib/.o、venv、build、wheel、日志、采集数据或凭据提交到 Git。
- vendor 文件的原始字节由 .gitattributes 保留，以便跨平台校验来源哈希。修改 vendor 后更新 UPSTREAM.json 的本地哈希与补丁；原始哈希不变。
- tools/vendor_patch.py 是维护工具，会从指定的固定 KAME checkout 重新复制并应用补丁；不是安装步骤。普通构建不得依赖工作目录外的原始源码或私人路径。
- 每次修复记录实际测试环境和剩余限制。硬件报告默认留在本地，需要对外提交时先检查其中的设备信息。

## 可直接使用的 prompts

### 1. Mac 首次构建和诊断

> 请先阅读 CLAUDE.md、README.md、docs/VALIDATION.md 和 docs/MAC_ACCEPTANCE.md。检查本机 macOS、CPU、Python、Homebrew 和 libusb 的架构，编译安装 gpib-macarm 并运行离线测试与 info。先不访问仪器。若构建失败，围绕实际日志做最小修复，不更新 vendor，不引入 Qt/NI 驱动/MCP。记录哪些测试实际通过、哪些跳过，并更新验证文档。

### 2. NI GPIB-USB-HS 实物验收

> 请先读取项目交接文档。仪器型号为【填写】，GPIB 主地址为【填写】，转接线序列号为【填写或留空】。先运行 list 确认设备，再按照仪器手册进行身份查询和 100 次连续只读查询，保存环境及时延报告。允许正常初始化 REN/IFC，不发送 *RST，不开启输出、不修改量程。若失败，区分 USB 打开/占用、初始化、寻址、终止符和读回解析，依据日志修复并验证恢复，不盲目重试有副作用的写入。

### 3. 迁移现有 PyVISA 采集脚本

> 请把我提供的【脚本路径】从 PyVISA 的 GPIB 通信接口迁移到 gpib_macarm。保持原仪器命令、测量顺序、数据格式和时序意图，核对 ResourceManager、地址、终止符、毫秒超时和资源关闭。明确列出本包不支持的 VISA 功能；先用离线替身验证调用流程，实物运行按我给出的仪器范围执行。

### 4. 修复并持续验证

> 请检查【具体失败日志/问题】，先增加能复现问题的必要测试，再做最小修复。涉及消息边界、异常清理、ctypes、线程锁或 vendor 时，补相应测试和来源记录；重建原生库并运行相关检查。更新 CHANGELOG.md 和 docs/VALIDATION.md，清楚区分 Linux、Mac 和实物证据。不要将未测能力标成已支持。

### 5. 准备后续版本

> 请在 Mac/实际仪器验收后整理下一个版本：核对版本号、CLI、包名、README、GPL/上游声明、来源哈希与源码包完整性。构建 wheel 和 source archive，在干净环境安装验证，排除本机二进制、缓存、凭据和采集数据。先完成具体可审查的发布产物；只有我明确要求时才发布到 PyPI 或创建 GitHub Release。
