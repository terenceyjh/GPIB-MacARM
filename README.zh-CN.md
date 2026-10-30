# GPIB-MacARM

[English](README.md) · [开发交接与 prompts](CLAUDE.md)

从 [KAME](https://github.com/northriv/KAME) 提取的独立 NI USB-GPIB 用户态驱动，面向 Python 基础 SCPI 数据采集。

Python → 标准库 ctypes → 本包的 C ABI → [KAME](https://github.com/northriv/KAME)/[linux-gpib](https://linux-gpib.sourceforge.io/) C 驱动 → libusb → NI 转接线 → 仪器。

不需要 NI-488.2、NI-VISA、Qt、完整 [KAME](https://github.com/northriv/KAME)、内核模块或 MCP 服务。Python 接口接近常用 PyVISA 写法，但本包不是 PyVISA 后端，也不承诺完整 VISA API。

**验证记录**

| 日期 | 环境 | 实际结果 |
| --- | --- | --- |
| 2026-10-30 | Windows / Python 3.14 | Python API 离线测试通过；原生测试按平台跳过。 |
| 2026-10-30 | WSL2 Linux x86_64 / Python 3.10.12 / GCC 11.4 | 原生编译与加载、30 项离线测试、ASan/UBSan，以及 wheel/源码压缩包的干净安装均通过。 |
| 2026-10-31 | macOS 14.8.9 arm64 / Python 3.11.6 / Apple Clang 15.0.0 / libusb 1.0.30 | editable 编译安装、原生加载、模块与 CLI 的 `info`、30 项离线测试（0 跳过）及 ASan/UBSan 均通过。 |

本次 Mac 测试包括 22 项 Python API、2 项交付/来源完整性和 6 项实际原生解析器/C ABI 测试。Linux 与 Mac 的 sanitizer 检查均覆盖 20,000 个畸形/短回包，以及模拟 USB 超时传递、错误映射和完成回调。

**实物验收仍待完成。** 本轮 Mac 未打开适配器，未发送 REN/IFC 或仪器查询；USB/GPIB 通信、长期采集、拔插/断电恢复，以及 Intel Mac 和 Mac 非 editable 干净安装尚未验证。完整环境、命令与边界见 [验证记录](docs/VALIDATION.md)，后续按 [Mac 验收清单](docs/MAC_ACCEPTANCE.md) 使用明确选择的转接线和仪器继续测试。

**Mac 编译安装**

要求 macOS、同架构的 Python 3.10+、Xcode Command Line Tools、libusb 和 pkg-config。

```bash
xcode-select --install  # 已安装则跳过
brew install python libusb pkg-config
cd GPIB-MacARM
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
python -m gpib_macarm info
python -m gpib_macarm list
```

把这个文件夹完整复制到 Mac 即可，构建不需要原始 [KAME](https://github.com/northriv/KAME) 仓库。也可以安装交付的源代码压缩包：

```bash
python -m pip install ./gpib-macarm-0.1.0-source.zip
```

Apple Silicon 使用 arm64 Python 和 `/opt/homebrew` 的 libusb；Intel 使用对应 x86_64 环境。不要混用 Rosetta 下的 Python 和 arm64 Homebrew。构建器也识别 MacPorts `/opt/local`。其他路径可指定：

```bash
LIBUSB_INCLUDE_DIR=/your/prefix/include \
LIBUSB_LIBRARY_DIR=/your/prefix/lib \
python -m pip install --no-cache-dir .
```

编译时 C 文件使用 GNU C11，C++ 文件使用 GNU C++17；这很重要，因为上游头文件含有 C 语言专用标识符。原生库通过 ctypes 加载，不需要 pybind11 或 Python C API。构建出来的 wheel 是本机平台产物，Linux wheel 不能放到 Mac 使用。

**最小示例与 PyVISA 迁移**

```python
import gpib_macarm as visa

with visa.ResourceManager() as rm:
    with rm.open_resource("GPIB0::22::INSTR") as meter:
        meter.timeout = 5000          # 毫秒
        meter.write_termination = "\n"
        meter.read_termination = "\n"
        print(meter.query("*IDN?"))
        # 按你的仪器手册使用：
        # meter.write("CONF:VOLT:DC 10")
        # value = float(meter.query("READ?"))
```

常见脚本只需把 `import pyvisa` 改为 `import gpib_macarm as pyvisa`，保留 ResourceManager/open_resource/write/read/query 这部分写法。访问 USB/TCPIP、VISA events、二级地址或二进制块便利函数的脚本需要另行适配，不能直接替换所有 PyVISA 使用。

`GPIB0` 是 USB 枚举中的适配器编号；`22` 是仪器面板上设置的 GPIB 主地址。`list_resources()` 只返回已枚举适配器的 `GPIB0::INTFC` 等名称，不会自动探测仪器地址。多个适配器可以指定序列号，避免 USB 枚举顺序改变：

```python
with visa.ResourceManager() as rm:
    meter = rm.open_resource("GPIB0::22::INSTR", serial="YOUR_ADAPTER_SERIAL")
    print(meter.query("*IDN?"))
```

也可以直接操作共享控制器：

```python
from gpib_macarm import Controller

with Controller(serial="YOUR_ADAPTER_SERIAL") as bus:
    meter = bus.open_instrument(22, timeout=10000)
    source = bus.open_instrument(5)
    print(meter.query("*IDN?"))
    print(source.query("*IDN?"))
```

同一适配器应共用一个 Controller 或 ResourceManager。本包用控制器级 RLock 串行化完整 query，包括 query_delay；ctypes 会在原生调用期间释放 GIL。不能靠两个独立进程/两个独立 manager 的 Python 锁协调同一总线。

**接口与消息边界**

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

超时是底层每次传输的超时，不是整个 query 的绝对截止时间；USB 等待还包含协议余量。较长回复的多个分块、清理命令和 query_delay 可能让总时长超过 timeout。传输失败不自动重发写命令，避免有副作用的 SCPI 被执行两次。超时后仪器可能仍在测量/发送数据，按手册调用 clear()、interface_clear() 或关闭重开，并在应用层决定是否重试。

**诊断与测试**

```bash
python -m gpib_macarm info
python -m gpib_macarm list
python -m gpib_macarm query --address 22 '*IDN?'
python -m unittest discover -s tests -v
python tools/hardware_smoke.py --address 22 --count 100
```

`info` 只检查原生库加载；`list` 只枚举 USB。query、Controller/open_resource 及 hardware_smoke 会打开适配器，启用 REN 并发送 IFC，可能影响同一总线上的其他会话；不会自行发送 *RST。硬件 smoke 默认只反复查询 *IDN?，可指定符合仪器手册的无副作用查询。

源码测试不需要仪器；原生测试需要先成功构建本包。具体实现、改动和验收步骤见 [架构与移植说明](docs/ARCHITECTURE.md)、[Mac 验收](docs/MAC_ACCEPTANCE.md) 和 [验证记录](docs/VALIDATION.md)。

**支持范围和限制**

主要目标为真品 NI GPIB-USB-HS（3923:709b）。继承的驱动还识别 HS+、USB-B、KUSB-488A、MC USB-488，但本包未逐型号实测。USB-B 的固件加载、初始 PID 为 761e 的 HS+ 初始化不包含在本包内。廉价仿制线不保证兼容。Linux 上应保证没有内核驱动/其他进程占用设备，并配置 USB 访问权限；本包不会修改系统驱动配置。

macOS 无 NI 驱动占用时一般无需 sudo；如提示 BUSY/ACCESS，检查 NI-488.2、其他进程和 USB 配件授权设置。不要用关闭系统安全机制替代定位问题。诊断信息会报告原生库路径；遇到 incompatible architecture 或 Library not loaded，应检查 Python/libusb 架构并重新编译。

这是提取和加固后的 0.1.0 初版，非 NI 官方驱动。已完成的离线测试及剩余实物验收边界见上方验证记录与 [详细记录](docs/VALIDATION.md)。

**来源与许可**

[KAME](https://github.com/northriv/KAME) 源码固定于 f451025dc4215c5d85f39b71303f9008ccee66bc。[linux-gpib](https://linux-gpib.sourceforge.io/) 基础为 [KAME](https://github.com/northriv/KAME) 携带的 4.3.6/git 9813ff8f。许可证 GPL-2.0-or-later，原始版权头、COPYING、AUTHORS 均保留；具体见 [THIRD_PARTY.md](THIRD_PARTY.md)。UPSTREAM.json 记录来源及文件哈希，vendor/local-fixes.patch 记录本包的上游文件修复。
