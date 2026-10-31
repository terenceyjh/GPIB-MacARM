# GPIB-MacARM

[English](README.md) · [开发交接与 prompts](CLAUDE.md)

从 [KAME](https://github.com/northriv/KAME) 提取的独立 NI USB-GPIB 用户态驱动，面向 Python 基础 SCPI 数据采集。

Python → 标准库 ctypes → 本包的 C ABI → [KAME](https://github.com/northriv/KAME)/[linux-gpib](https://linux-gpib.sourceforge.io/) C 驱动 → libusb → NI 转接线 → 仪器。

不需要 NI-488.2、NI-VISA、Qt、完整 [KAME](https://github.com/northriv/KAME)、内核模块或 MCP 服务。Python 接口接近常用 PyVISA 写法，但本包不是 PyVISA 后端，也不承诺完整 VISA API。

**已在真实 Keithley 2400 源表上完成 SCPI 命令通信测试，结果通过。** 当前 Mac + GPIB-USB-HS 组合已验证配置命令写入、设置读回、100 次连续身份查询、四线电流扫描和超过 4096 字节的测量回复。正常通信路径目前没有必须修改 C ABI 签名的问题；通信超时后的可靠恢复仍未完成。

## 验证记录

| 日期 | 环境 | 实际结果 |
| --- | --- | --- |
| 2026-10-30 | Windows / Python 3.14 | Python API 离线测试通过；原生测试按平台跳过。 |
| 2026-10-30 | WSL2 Linux x86_64 / Python 3.10.12 / GCC 11.4 | 原生编译与加载、30 项离线测试、ASan/UBSan，以及 wheel/源码压缩包的干净安装均通过。 |
| 2026-10-31 | macOS 14.8.9 arm64 / Python 3.11.6 / Apple Clang 15.0.0 / libusb 1.0.30 | editable 编译安装、原生加载、模块与 CLI 的 `info`、30 项离线测试（0 跳过）及 ASan/UBSan 均通过。 |
| 2026-10-31 | 同一 Mac，连接 GPIB-USB-HS（3923:709b）与地址 24 的 Keithley 2400 | 修复解析器后，100 次连续身份查询、分块文本/原始读取和只读 SCPI 通过；34 项离线测试全部通过，无跳过。 |
| 2026-10-31 | 同一硬件，低阻铜板 | 四线 ±1 mA / 21 点及 ±10 mA / 101 点正反向电流扫描、5655 字节回复和关输出检查通过；39 项离线测试通过。铜板电阻准确度尚未确认。 |
| 2026-10-31 | 同一 Mac，新建 Python 3.11.6 venv | 非 editable 的 pip install .、源码目录外的导入与原生加载、CLI info、pip check 和 39 项离线测试全部通过。 |

最新 Mac 测试包括 22 项 Python API、2 项交付/来源完整性、10 项原生解析器/C ABI 和 5 项扫描数据/异常关输出测试。Mac sanitizer 还覆盖两种尾部格式、逐字节截断与 20,000 个畸形包；此前 Linux 结果对应较早版本，本次硬件修复尚未在 Linux 重跑。

**已通过基础通信与有限电流扫描，完整验收仍有边界。** 保留 `send_end=True`；身份查询使用的 10000 ms 超时不能直接用于长扫描，本次 101 点 NPLC 5 实测 35.7 秒，设置 60000 ms。关闭 EOI 的写入会超时，无回复读取超时后原会话复用及立即重开也未通过。铜板扫描与 5655 字节长回复通过，每次结束输出确认为关闭，但曲线非线性且拟合斜率为负，不能宣称电阻准确度通过。TCR、电压源 IV、更大的/二进制回复、长期采集、拔插/断电恢复、Intel Mac 和跨机器部署尚未验证。详情见 [验证记录](docs/VALIDATION.md) 和 [Mac 验收清单](docs/MAC_ACCEPTANCE.md)。

## Mac 编译安装

### 1. 准备编译环境

需要 Python 3.10+、Xcode Command Line Tools、libusb、pkg-config 和 Git。已安装 [Homebrew](https://brew.sh/) 后运行：

```bash
xcode-select --install  # 已安装则跳过
brew install python libusb pkg-config
```

Apple Silicon 应使用 arm64 Python 和 arm64 libusb，Homebrew 前缀通常为 `/opt/homebrew`；不要把 Rosetta x86_64 Python 与 arm64 库混用。创建环境前核对：

```bash
uname -m
python3 -c "import platform, sys; print(platform.machine()); print(sys.executable)"
brew --prefix
pkg-config --modversion libusb-1.0
```

如果 `python3` 指向其他架构，应显式选择匹配的 Python，例如 Apple Silicon 上使用 `/opt/homebrew/bin/python3 -m venv .venv`。Intel Mac 尚未验证。

### 2. 获取源码并安装

```bash
git clone https://github.com/terenceyjh/GPIB-MacARM.git
cd GPIB-MacARM
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
python -m gpib_macarm info
python -m pip check
```

`info` 应成功加载原生库，显示版本、架构和库路径；此步骤不访问仪器。也可运行等价的 `gpib-macarm info`。每次打开新终端，先进入项目并执行 `source .venv/bin/activate`，或直接使用 `.venv/bin/python`。

构建只使用本仓库内的 C/C++ 与 vendor 源码，不需要原始 [KAME](https://github.com/northriv/KAME) 工作目录。pip 可能联网获取 setuptools/wheel 构建依赖。**目前未发布到 PyPI**，不要假设直接执行 `pip install gpib-macarm` 就能安装本项目。也可以安装已经生成的源码包：

```bash
python -m pip install ./gpib-macarm-0.1.0-source.zip
```

### 3. 开发安装、更新与重建

需要修改源码时，把普通安装命令换成 `python -m pip install -e .`。修改 C/C++、vendor 或兼容层后，即使使用 editable 安装也需要重建：

```bash
python -m pip install --no-cache-dir --force-reinstall --no-deps -e .
python -m gpib_macarm info
python -m unittest discover -s tests -v
```

普通非 editable 安装在 `git pull` 更新源码后应重新执行 `python -m pip install --no-cache-dir --force-reinstall --no-deps .`。不要从别的电脑复制 `.dylib` 或整个虚拟环境来替代本机编译。

构建器也识别 MacPorts `/opt/local`。其他 libusb 路径可指定：

```bash
LIBUSB_INCLUDE_DIR=/your/prefix/include \
LIBUSB_LIBRARY_DIR=/your/prefix/lib \
python -m pip install --no-cache-dir .
```

编译时 C 文件使用 GNU C11，C++ 文件使用 GNU C++17；这很重要，因为上游头文件含有 C 语言专用标识符。原生库通过 ctypes 加载，不需要 pybind11 或 Python C API。构建出来的 wheel 是本机平台产物，Linux wheel 不能放到 Mac 使用。

## 连接源表并完成只读通信测试

### 1. 发现 USB 转接线

连接 USB 和 GPIB 线，打开源表电源，在仪器面板选择 GPIB 接口并确认主地址，关闭其他占用同一转接线的程序。本次实测 2400 地址为 **24**，其他仪器应按实际面板设置填写。

```bash
python -m gpib_macarm list
```

正常时返回包含 index、型号、VID/PID、serial 和 accessible 的 JSON。空列表表示没有发现支持的 USB 设备。USB 枚举成功只证明发现转接线，还没有证明源表通信成功；此命令不会扫描 GPIB 主地址。正常安装流程不需要 NI 内核驱动或 sudo。

### 2. 查询身份

下面命令对应适配器 index 0、源表地址 24：

```bash
python -m gpib_macarm query --index 0 --address 24 --timeout 10000 '*IDN?'
```

成功时返回包含 `KEITHLEY INSTRUMENTS INC.,MODEL 2400` 的字符串，另含仪器序列号和固件信息。需要固定选择某只转接线时，可加 `--serial YOUR_ADAPTER_SERIAL`，使用 `list` 中的实际值。

默认追加 LF 并在最后字节发送 EOI；本次硬件组合应保留这个默认值。身份查询不会复位源表或开启源输出。打开控制器会初始化适配器、启用 REN 并发送 IFC，会影响同一总线上的其他会话，因此同一时间只运行一个控制程序。

### 3. 在 Python 中使用

```python
import gpib_macarm as visa

with visa.ResourceManager() as rm:
    with rm.open_resource(
        "GPIB0::24::INSTR",
        timeout=10000,               # 毫秒
        write_termination="\n",
        read_termination="\n",
        send_end=True,               # 最后一个字节发送 EOI
    ) as meter:
        print(meter.query("*IDN?"))
        print("Output enabled:", meter.query(":OUTP?"))
        print("Source function:", meter.query(":SOUR:FUNC?"))
        print("Error queue:", meter.query(":SYST:ERR?"))
```

这里的 SCPI 命令适用于 2400，其他型号需按各自手册使用。`:SYST:ERR?` 会读取并移除最早的一条错误队列记录。

`GPIB0` 是 USB 枚举中的适配器编号；`24` 是仪器面板上的主地址。`list_resources()` 只返回已枚举适配器的 `GPIB0::INTFC` 等名称，不会自动探测仪器地址。多个适配器可以指定序列号，避免 USB 枚举顺序改变：

```python
with visa.ResourceManager() as rm:
    meter = rm.open_resource("GPIB0::24::INSTR", serial="YOUR_ADAPTER_SERIAL", timeout=10000)
    print(meter.query("*IDN?"))
```

也可以直接操作共享控制器：

```python
from gpib_macarm import Controller

with Controller(serial="YOUR_ADAPTER_SERIAL") as bus:
    meter = bus.open_instrument(24, timeout=10000)
    source = bus.open_instrument(5)
    print(meter.query("*IDN?"))
    print(source.query("*IDN?"))
```

同一适配器应共用一个 Controller 或 ResourceManager。本包用控制器级 RLock 串行化完整 query，包括 query_delay；ctypes 会在原生调用期间释放 GIL。不能靠两个独立进程/两个独立 manager 的 Python 锁协调同一总线。

### 4. 连续 100 次通信检查

在克隆的源码目录下运行；`tools/`、`examples/` 是源码脚本，不是 pip 安装后的 CLI 子命令：

```bash
mkdir -p build/validation
python tools/hardware_smoke.py --address 24 --timeout 10000 --count 100 \
  --output build/validation/hardware-smoke-2400.json
```

检查 JSON 中 `success` 为 true、100 条回复非空且身份一致、没有 error。报告包含设备序列号和环境信息，分享前应检查。此测试不启用源输出。

## 四线 IV 测试：被动低阻负载

先确认 Force/Sense 四根线已正确接到合适的被动低阻负载。下面脚本**会复位 2400、修改源/感测配置，并在有限扫描期间开启输出**，与前面的只读测试不同。参数在铜板上实测过，不能直接套用到未确认的其他样品。

```bash
python tools/keithley_2400_iv.py --resource GPIB0::24::INSTR \
  --max-current 0.001 --points 21 --nplc 1 --compliance 0.1 --timeout 60000 \
  --output build/validation/iv-check-1mA
```

先评估 ±1 mA 试扫；本次进一步测试用 `--max-current 0.01 --points 101 --nplc 5`，并换用新的 output 前缀。加 `--reverse` 从正电流扫到负电流。完整参数可运行 `python tools/keithley_2400_iv.py --help`。当前工具限制最大电流不超过 10 mA、电压保护不超过 0.1 V、点数 3..101。

每次生成 `.json` 配置/结果、`.csv` 数据和 `.raw.txt` 原始回复，拒绝覆盖已有文件。重点检查 success、完整点数、错误队列和 `cleanup.output_off_confirmed`；拟合质量警告需单独判断。VOLT 为实测电压，CURR 在本模式下为源电流设定值。工具启用仪器内部自动关输出，并在 finally 中清理；通信失效仍可能阻止清理命令送达，未确认关输出时应检查实际面板。

核心库和扫描脚本只依赖 Python 标准库，不需要 PyVISA、numpy 或 matplotlib。画图是可选步骤，本次本地曲线使用 matplotlib；本项目不会自动安装绘图库。成功采集不等于样品电阻或仪器校准已通过验收。

## 迁移 PyVISA 采集脚本

仅使用本包支持的 GPIB 方法时，可以把 `import pyvisa` 改为 `import gpib_macarm as pyvisa`，继续使用 ResourceManager/open_resource/write/read/query。**同时把 `ResourceManager("@py")` 或 VISA 库路径改为无参数的 `ResourceManager()`**；GPIB 不使用串口 baud_rate。按真实仪器设置地址、毫秒超时、LF 和 EOI。

访问 TCP/IP、USBTMC、VISA events、二级地址或二进制块便利函数的代码需要另行适配。已有 PyMeasure/Qt/温控 GUI 的其他依赖与控制逻辑也需要单独安装、迁移和验证，本包只提供传输层。

当前参考的 2400 采集脚本固定 10000 ms 超时，IV 回调只在成功读取/拟合后关输出；原脚本尚未修改。长扫描应按整批时长设置足够超时，并补齐异常清理后再考虑无人值守采集。单点 TCR 的超时需求不能直接用于整批 IV。

## 接口与消息边界

| API/属性 | 行为 |
| --- | --- |
| `write(str)` / `read()` / `query(str)` | 文本通信，默认 ASCII |
| `write_raw(bytes)` / `read_raw()` | 二进制安全，保留 NUL 和末尾 CR/LF；raw read 不使用文本 EOS |
| `read_bytes(count, break_on_termchar=False)` | 最多读取 count 字节；遇到 EOI/END 可提前结束 |
| `query_ascii_values(command)` | 逗号分隔数值，返回 list；可提供 converter/separator |
| `timeout` | 1..1000000 毫秒；底层按 NI 硬件支持的离散档位向上取整 |
| `query_delay` | 写入到读取间的等待秒数，默认 0 |
| `write_termination` | 默认 LF；None/空串不追加；支持 CR/LF/CRLF |
| `read_termination` | 默认 LF；None/空串只依靠 EOI；CRLF 用 LF 做硬件 EOS，文本层移除完整 CRLF |
| `send_end` | 默认 True，在最后一个写入字节上断言 EOI；与追加 LF 相互独立 |
| `chunk_size` | 每次原生读取大小，默认 4096，最大 65535 |
| `max_read_bytes` | 完整消息的保护上限，默认 1 MiB；到达上限仍无 END/EOS 会抛错 |
| `clear()` | 对此仪器发 SDC；不同于 SCPI *CLS 或 *RST |
| `read_stb()` / `stb` | 串行轮询状态字 |
| `Controller.interface_clear()` | 对整个总线发送 IFC |
| `Controller.enable_remote(bool)` | 控制整个总线的 REN |
| `Controller.check_srq()` | 检查 SRQ 线；不提供异步事件订阅 |

长回复会持续读取到 END/EOS；达到保护上限不会返回被悄悄截断的数据。`read()` 只去掉配置的末尾终止符，不会 strip 数值前后的空格。按仪器手册设置终止符：只靠 EOI 的仪器可将 read_termination 设为 None；使用 LF 而不发 EOI 的仪器应使用文本 read/query。

超时是底层每次传输的超时，不是整个 query 的绝对截止时间；USB 等待还包含协议余量。较长回复的多个分块、清理命令和 query_delay 可能让总时长超过 timeout。传输失败不自动重发写命令，避免有副作用的 SCPI 被执行两次。超时后仪器可能仍在测量/发送数据；clear()、IFC 和关闭重开虽有接口，但在本次硬件上不能保证恢复，不应直接自动重试。

## 诊断与测试

```bash
python -m gpib_macarm info
python -m gpib_macarm list
python -m gpib_macarm query --address 24 --timeout 10000 '*IDN?'
python -m unittest discover -s tests -v
bash tools/test_native.sh
python tools/hardware_smoke.py --address 24 --timeout 10000 --count 100
```

`info` 只检查原生库加载；`list` 只枚举 USB。query、Controller/open_resource 及 hardware_smoke 会打开适配器，启用 REN 并发送 IFC，可能影响同一总线上的其他会话；不会自行发送 *RST。硬件 smoke 默认只反复查询 *IDN?，可指定符合仪器手册的无副作用查询。

源码测试不需要仪器；原生测试需要先成功构建本包。具体实现、改动和验收步骤见 [架构与移植说明](docs/ARCHITECTURE.md)、[Mac 验收](docs/MAC_ACCEPTANCE.md) 和 [验证记录](docs/VALIDATION.md)。

## 已知问题与仍缺少的工作

| 项目 | 当前结论与待办 |
| --- | --- |
| 基础 SCPI / C ABI | 本机 Mac、转接线及 2400 的正常命令通信、测量和长文本回复通过；目前无需为这条已工作的路径修改 ABI 签名。 |
| 异常恢复（优先） | 无回复读取超时后，后续命令会继续超时或发生协议错误；立即重开及 STOP/排空试验不可靠。需定位取消、适配器未结束操作和回包同步，再做重复故障/恢复验证。不得盲目重发写入或触发命令。 |
| 关闭 EOI | 本组合 `send_end=False` 的仅 LF 写入失败；保留默认 EOI。需要中间无 EOI 分块的大写入也未实测通过。 |
| 实际采集脚本 | 调整整批超时、完善异常关输出与失败批次处理；PyMeasure/TCR GUI、温度服务尚未完成端到端迁移和验证。 |
| 测量准确度 | 铜板曲线有偏置、非线性及负拟合斜率；应核对接线/电极布局并用已知标准负载验收准确度。电压源 IV 和正式 TCR 未验证。 |
| 长期稳定与兼容性 | 长期采集、拔插/断电恢复、多仪器共线、其他型号/固件、二进制测量、更大回复、Intel Mac 未验证；此前 Linux/Windows 结果不代表本轮硬件修复在那里已回归。 |
| 分发与自动验证 | 未发布 PyPI，未建立 macOS CI；源码压缩包干净安装、跨机器部署和更多 macOS/Python 组合仍需验证。 |

超时表示通信失败，不表示输出已关闭。应停止本批采集、确认实际输出状态，并重新建立可信的身份/设置状态后再继续。故障恢复根因尚未完全定位；基础 SCPI 成功不能等同于具备无人值守容错能力。

## 常见安装与连接问题

| 现象 | 排查方法 |
| --- | --- |
| `ModuleNotFoundError: gpib_macarm` | 激活安装时的 venv，执行 `python -m pip show gpib-macarm`；distribution 用连字符，import 用下划线。 |
| Cannot load / incompatible architecture | 核对 info 中的库路径、Python/libusb 架构及已设置的 GPIB_MACARM_LIBRARY，在目标环境重新编译。 |
| 缺少 libusb 头文件或 pkg-config | 在对应架构的 Homebrew 安装 libusb/pkg-config，或设置上文的 include/library 路径。 |
| list 为 `[]` | 检查 USB 接线、配件授权和识别的 VID/PID；该命令不扫描源表地址。 |
| USB busy / access denied | 关闭其他控制进程，检查 NI 驱动是否占用接口；不要关闭系统安全机制来规避。 |
| 找到转接线但 IDN 失败 | 检查仪器电源、GPIB 接口选择、线缆、真实地址及默认 LF + EOI；确认查询受该仪器支持。无回复查询可能触发已知恢复问题。 |
| 扫描超时、输出状态不明 | 计入整批点数、源延时、NPLC/自动调零及传输时间；确认仪器面板输出状态并停止采集，不能盲目重发。 |

## 支持范围和限制

主要目标为真品 NI GPIB-USB-HS（3923:709b）。继承的驱动还识别 HS+、USB-B、KUSB-488A、MC USB-488，但本包未逐型号实测。USB-B 的固件加载、初始 PID 为 761e 的 HS+ 初始化不包含在本包内。廉价仿制线不保证兼容。Linux 上应保证没有内核驱动/其他进程占用设备，并配置 USB 访问权限；本包不会修改系统驱动配置。

macOS 无 NI 驱动占用时一般无需 sudo；如提示 BUSY/ACCESS，检查 NI-488.2、其他进程和 USB 配件授权设置。不要用关闭系统安全机制替代定位问题。诊断信息会报告原生库路径；遇到 incompatible architecture 或 Library not loaded，应检查 Python/libusb 架构并重新编译。

这是提取和加固后的 0.1.0 初版，非 NI 官方驱动。已完成的离线测试及剩余实物验收边界见上方验证记录与 [详细记录](docs/VALIDATION.md)。

## 来源与许可

[KAME](https://github.com/northriv/KAME) 源码固定于 f451025dc4215c5d85f39b71303f9008ccee66bc。[linux-gpib](https://linux-gpib.sourceforge.io/) 基础为 [KAME](https://github.com/northriv/KAME) 携带的 4.3.6/git 9813ff8f。许可证 GPL-2.0-or-later，原始版权头、COPYING、AUTHORS 均保留；具体见 [THIRD_PARTY.md](THIRD_PARTY.md)。UPSTREAM.json 记录来源及文件哈希，vendor/local-fixes.patch 记录本包的上游文件修复。
