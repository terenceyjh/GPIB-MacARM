# GPIB-MacARM

**让 Apple Silicon（ARM）Mac 通过 GPIB 转 USB 线缆，用 Python 控制实验仪器。**

[English](README.md) · [测试概览](docs/VALIDATION.md) · [Agent 使用指南与 prompts](CLAUDE.md)

本项目为 **ARM 架构的 Mac 提供用户态 GPIB 驱动和 Python 接口**，通过 **NI GPIB-USB-HS** 转接线与实验仪器通信。核心驱动改编自 **[KAME](https://github.com/northriv/KAME) / [linux-gpib](https://linux-gpib.sourceforge.io/)**；本项目在其基础上提供独立构建、C ABI、Python 封装和命令行工具。

无需安装 NI-488.2、NI-VISA、内核扩展或后台服务。安装包名为 `gpib-macarm`，Python 导入名为 `gpib_macarm`。

希望能帮到和我一样抱着 Mac 在实验室里折腾的博士生：论文已经够难了，别让驱动再给自己加一门选修课。愿你少熬几个调驱动的夜，多喝几杯不用续命的咖啡。☕

## 测试过的线缆与仪器

| USB–GPIB 转接线 | 仪器 | 已验证用途 |
| --- | --- | --- |
| NI GPIB-USB-HS（`3923:709b`） | Keithley **2400** 源表 | SCPI 读写、连续身份查询、四线有限电流扫描及长文本回复 |
| NI GPIB-USB-HS（`3923:709b`） | Stanford Research Systems **SR830** 锁相放大器 | 连续查询、连续噪声扫描，以及已测试通信故障后的显式恢复 |

当前为 **0.1.0 早期开发版**。上述组合在 macOS 14.8.9 / arm64 上完成实测。**2450、其他转接线和 Intel Mac 尚未验证。** 通信通过不等于测量准确度验收通过，简要范围见[测试概览](docs/VALIDATION.md)。

本项目针对 **ARM Mac**。Intel Mac 用户也可以参考已有的 PyVISA + NI-488.2/NI-VISA 方案，但须核对具体 macOS、驱动版本和线缆的兼容性：[NI 的 Intel Mac 说明](https://knowledge.ni.com/KnowledgeArticleDetails?id=kA0VU00000055n30AA&l=en-US)。驱动并非越新越适合 GPIB，另见 [NI 兼容性表](https://www.ni.com/en/support/documentation/compatibility/17/ni-visa-features-and-operating-system-compatibility.html)。

## 安装

需要 **Python 3.10+，以 arm64 运行**，并使用同架构的 libusb。如未安装，请先准备 [Homebrew](https://brew.sh/)，然后执行：

```bash
xcode-select --install  # 已安装 Command Line Tools 时跳过
brew install python libusb pkg-config
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

**使用 release：** 下载 **`gpib-macarm-0.1.0-release.zip`**，解压并进入 `GPIB-MacARM-0.1.0`。其中放有安装包、release 专用中英文 README，以及**同文件夹下可直接交给 agent 的 `CLAUDE.md`**。按包内 README 操作，或安装旁边的源码包：

```bash
python -m pip install ./gpib_macarm-0.1.0.tar.gz
```

里面的 tar.gz 不用手动解压；外层安装文件夹不是源码目录，请使用上面的命令，不要在外层执行 `pip install .`。

**使用 Git 仓库：**

```bash
git clone https://github.com/terenceyjh/GPIB-MacARM.git
cd GPIB-MacARM
python -m pip install .
```

pip 会在你的 Mac 上编译原生驱动，release 提供源码，不附带预编译驱动；运行时也需要保留 Homebrew libusb。**项目尚未发布到 PyPI**，请使用下载的压缩包或源码目录安装，不要直接运行 `pip install gpib-macarm`。

```bash
python -m gpib_macarm info
python -m pip check
```

`info` 检查原生库能否加载，不打开仪器。新开终端后需重新激活同一环境。加载失败时，用 `python -c 'import platform; print(platform.machine())'` 检查是否为 `arm64`，并确认 Python/libusb 架构一致。

## 使用

连接线缆、打开仪器，关闭占用同一转接线的其他程序，并在仪器面板确认 GPIB 主地址。

```bash
python -m gpib_macarm list
# 把 24 换成仪器的真实地址：
python -m gpib_macarm query --address 24 --timeout 10000 '*IDN?'
```

`list` 只枚举 USB 转接线，不扫描仪器地址。打开控制器会发送 REN/IFC，影响同一总线；上面的身份查询不会复位仪器或开启源输出。

```python
import gpib_macarm as visa

with visa.ResourceManager() as rm:
    with rm.open_resource(
        "GPIB0::24::INSTR",  # 转接线索引 0，仪器地址 24
        timeout=10000,      # 毫秒
        write_termination="\n",
        read_termination="\n",
        send_end=True,
    ) as instrument:
        print(instrument.query("*IDN?"))
        # instrument.write("...")  # 使用仪器支持的命令
        # reply = instrument.read()
```

同一转接线共用一个 manager/controller。如需按转接线序列号选择，可给 `open_resource()` 传入 `serial="YOUR_ADAPTER_SERIAL"`。不同仪器使用各自支持的命令。

| 常用接口 | 用途 |
| --- | --- |
| `write()`、`read()`、`query()` | 文本命令与回复 |
| `query_ascii_values()` | 将分隔的数值回复解析为列表 |
| `write_raw()`、`read_raw()`、`read_bytes(n)` | 保留原始字节；实物验证范围仍有限 |
| `timeout`、`query_delay` | 每次传输超时，单位毫秒；查询写入到读取的等待，单位秒 |
| `read_stb()`、`clear()` | 串行轮询、选定设备清除 |
| `recover()` | 显式通信恢复；已在本次 SR830 组合验证 |

请保留 **`send_end=True`**：关闭 EOI、仅用 LF 结尾的写入目前会失败。长测量应增加超时；超时针对底层传输，并非整个 query 的严格截止时间。通信错误后，同一控制器上的普通操作会锁止；应停止失败批次，按需显式恢复，并核对身份与设置后开始新的采集。失败命令不会自动重发，恢复成功也不代表源输出已经关闭。

迁移简单的 PyVISA 风格脚本时，可把 `import pyvisa` 改为 `import gpib_macarm as pyvisa`，并使用**不带 `"@py"` 的 `ResourceManager()`**。本项目只提供有限的 VISA 风格接口，不是注册到 PyVISA 的后端；不包含 TCP/IP、USBTMC、VISA events 或二进制块便利解析接口。

## 下一步开发方向

- 定位并修复**无 EOI 写入**，再验证“中间块不发 EOI、末块发送 EOI”的大数据写入。
- 在 2400、USB 拔插、仪器断电及更多设备/固件上验证异常恢复。
- 验证二进制传输、更长时间采集及多仪器共线。
- 扩展 macOS/Python 组合、跨机器安装验证，并补充 macOS CI。

需要 agent 协助安装、迁移脚本或继续开发时，可以直接把 **[CLAUDE.md](CLAUDE.md)** 交给它；其中有可复制的 prompts、重建方法和上述开发重点。实现说明见[架构文档](docs/ARCHITECTURE.md)。

## 致谢与许可

**核心驱动 credit to [KAME](https://github.com/northriv/KAME) / [linux-gpib](https://linux-gpib.sourceforge.io/)。** 本项目基于它们的工作提取、适配并封装上述使用流程，非 NI 官方驱动。

许可证为 GPL-2.0-or-later，保留原始版权及许可文件。详见 [THIRD_PARTY.md](THIRD_PARTY.md)、[UPSTREAM.json](UPSTREAM.json) 和 [vendor/local-fixes.patch](vendor/local-fixes.patch)。
