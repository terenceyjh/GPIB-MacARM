# GPIB-MacARM — 开发交接与可复用 prompts

这是开发交接文件。先阅读 README.md、docs/ARCHITECTURE.md、docs/VALIDATION.md 和本文件，再继续修改。不要将“代码存在”“测试被跳过”或“Linux 测试通过”写成“Mac/硬件已经通过”。

## 当前结论与继续开发入口（2026-10-31）

**本机 Mac + 已连接 GPIB-USB-HS + Keithley 2400 的基础 SCPI 命令通信测试已成功。** 已验证命令写入、设置读回、连续身份查询、真实四线电流扫描和 5655 字节测量回复。正常路径当前不需要修改 C ABI 签名；异常超时后的可靠恢复仍缺失。铜板数据的电阻准确度没有验收通过，不得把通信成功写成测量精度通过。

用户安装、环境检查、CLI/Python 用法、PyVISA 迁移及扫描命令，以 [README.md](README.md) / [README.zh-CN.md](README.zh-CN.md) 为入口；逐轮证据见 [docs/VALIDATION.md](docs/VALIDATION.md)。源码 `.venv` editable 与新建 venv 非 editable 安装都已在本机验证；39 项测试无失败、无跳过。原始数据、日志、设备序列号和本机二进制留在忽略的 `build/validation/` 中，不上传。

### 仍缺少什么，下一轮优先做什么

| 优先项 | 现状与下一步 |
| --- | --- |
| 1. 异常恢复 | 无回复读取超时后，后续命令及立即重开可能失败。根因尚未完全定位，STOP/排空试验无效且已撤回。定位取消/适配器未完成操作/残留回复同步，再验证重复故障与恢复、身份/数据边界及输出状态。保留原始错误，不盲目重发写命令。 |
| 2. 实际采集程序接入 | 参考脚本未修改、GUI 未端到端验证。迁移时把 `ResourceManager("@py")` 改为本包无参数 manager，删除串口专用设置；保留仪器流程，按批时长调整超时、补 finally 清理和失败批次处理。PyMeasure/Qt/温度服务依赖需单独管理。 |
| 3. 测量准确度 | 核对铜板 Sense 极性、四个落点、接触热电势/偏置，并用已知标准负载验证；正式 TCR、电压源 IV 尚未测试。 |
| 4. EOI 与其他数据路径 | `send_end=False` 的仅 LF 写入失败，应保留默认 EOI；需要中间无 EOI 分块的大写入、二进制测量、更大的回复未实测通过。不要将字节 API 的离线测试写成所有硬件传输均兼容。 |
| 5. 稳定性和适配范围 | 长期采集、拔插/断电恢复、多仪器共线、其他转接线/固件、Intel Mac、更多 macOS/Python 组合待验证；本轮修改未在 Linux/Windows 重跑。 |
| 6. 分发与持续验证 | 源码压缩包在 Mac 的干净安装、跨机器部署、macOS CI、发布流程待补齐；尚未发布 PyPI。本机新 venv 从仓库 `pip install .` 已通过，不再属于待验证项。 |

恢复能力若需新控制入口，先明确语义和硬件证据，再决定是否扩展 ABI；不要为普通 SCPI 路径无目的改签名。连接关闭、SDC、IFC 都不能宣称为已保证成功的恢复方案。超时不等于输出关闭，采集错误后须停止该批并确认实际状态。

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

### 本次基础实物通信结果（2026-10-31，后续轮次）

- 连接的转接线枚举为 GPIB-USB-HS（`3923:709b`），Keithley 2400 实际地址为 24，`GPIB0::24::INSTR`。沿用 `.venv`，10000 ms 超时，默认 LF + EOI。序列号仅保留在本地日志。
- 首次查询因紧凑回包尾部及小块计数字段而触发 `ProtocolError`。已修复 IBRD 解析器，保留边界、剩余计数、状态与 TERM 校验，并同步维护补丁、复现脚本和本地哈希；未更新上游提交。
- 100 次连续身份查询一致；18 种分块大小各查 3 次、原始字节/定长分段读取、终止符、只读配置查询、query_delay、串行轮询和 SRQ 通过。正常关闭重开再做 100 次一致身份查询。最终错误队列无错误，输出状态始终为 0。
- 最终代码重建后，34 项 unittest 全通过（22 API + 2 来源 + 10 native，零跳过），ASan/UBSan 通过。未开启源输出、未修改测量配置或触发新测量；参考 `measure_tcr_v6.py` 未修改，GUI 未运行。
- **已知失败：** 关闭 EOI 的写入超时；故意无回复读取超时后，原会话复用及立即重开不可靠。STOP/排空恢复试验无效，相关试验代码已撤回，不能声称自动恢复。就绪状态仍有两个上游预期值警告，日志未隐藏。
- 详细事实、复现命令及本地证据路径见 [docs/VALIDATION.md](docs/VALIDATION.md)。不要将基础通信通过写成测量或完整硬件验收通过。

### 铜板四线 IV 实测（2026-10-31）

- 用户随后授权四线 IV，负载为低阻铜板。已用 Source I / Measure V，0.1 V 电压保护、四线 remote sense，完成 ±1 mA / 21 点试扫及 ±10 mA / 101 点正反扫，共 223 点。
- 101 点 NPLC 5 的 READ 每次约 35.7 s，设置 60000 ms 超时；5655 字节回复跨过 4096 字节读取块，完整性、状态字、同会话后续通信均通过。每次仪器自动关输出及 finally 后的输出状态均为 0，无测量错误或保护触发。
- 原始 IV 有明显约 −16 µV 偏置及非线性，拟合为负斜率且 R² 仅约 0.33；不能宣称铜板电阻准确测出。应核对 Sense 极性、四个落点/电极几何、接触热电势及偏置。
- 新增 `tools/keithley_2400_iv.py`（运行会复位和开启输出，仅用于确认过的被动低阻样品），39 项离线测试通过，无跳过。参考 `measure_tcr_v6.py` 未修改：其 IV 的 10000 ms 固定超时及异常分支缺少 finally 关输出，实际运行需注意。
- 数据、图和精确边界见 [docs/VALIDATION.md](docs/VALIDATION.md)。此前无 EOI / 超时恢复的失败仍未解决。

### 尚未验证

尚未验证：Intel Mac、其他 macOS/Python 组合、Mac 源码压缩包的干净安装、跨机器部署、其他转接线/仪器、真正冷启动/断电和拔插恢复、更大的/二进制回复、电压源 IV、TCR 及长期采集。本机从仓库到新 venv 的非 editable 安装已通过。铜板测量准确度仍未确认。本次 Mac 实物结果仅适用于上述组合；Linux USB 枚举为空，不能把它写成 Linux 实物通信成功。无 EOI 和超时恢复还有已知失败。

2026-10-30 重命名后已再次完成 Linux 原生构建、30 项测试、sanitizer 检查和新包名的源码 zip/wheel 独立安装；CLI 与导入名也已核对。最终事实以 docs/VALIDATION.md 和实际执行结果为准。

## 下一步：测量流程与异常恢复

本机 Mac 基础通信与铜板有限电流扫描已完成。后续应核对物理接线与测量准确度，验证实际 TCR 流程并解决已知恢复问题；不得将现有结果标记为完整硬件验收。下面保留其他设备及后续验收流程，已完成项以验证记录为准。

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
