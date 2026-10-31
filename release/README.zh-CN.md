# GPIB-MacARM 0.1.0 — 安装与使用

**为 Apple Silicon（ARM）Mac 提供用户态 GPIB 驱动和 Python 接口**，通过 NI GPIB-USB-HS 转接线控制实验仪器。核心驱动 credit to **[KAME](https://github.com/northriv/KAME) / [linux-gpib](https://linux-gpib.sourceforge.io/)**。

[English](README.md)

## 先看这里

当前文件夹中已经放好：

- `gpib_macarm-0.1.0.tar.gz`：交给 pip 安装的源码包，**里面这一层 tar.gz 不用手动解压**。
- `README.md` / `README.zh-CN.md`：中英文安装与基本用法。
- **[`CLAUDE.md`](CLAUDE.md)**：详细安装、接口用法、已知问题与处理办法。**它就在同一文件夹下，可以直接交给 agent 看，让 agent 帮你安装、排错或迁移脚本。**
- `LICENSE`、`THIRD_PARTY.md`、`SHA256SUMS.txt`：许可证、来源说明和校验文件。

## 安装

需要 ARM Mac、以 arm64 运行的 Python 3.10+、Xcode Command Line Tools 和 arm64 libusb。先准备 [Homebrew](https://brew.sh/)，然后执行：

```bash
xcode-select --install  # 已安装则跳过；请先完成弹出的安装流程
brew install python libusb pkg-config
```

在终端进入**这个解压后的文件夹**，确保能看到 tar.gz 和本 README。可以先输入 `cd `，将这个文件夹拖进终端，再回车。

```bash
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ./gpib_macarm-0.1.0.tar.gz
python -m gpib_macarm info
python -m pip check
```

`info` 应显示版本 `0.1.0`、架构 `arm64` 和原生库路径；它不打开仪器。pip 会在你的 Mac 上编译驱动，运行时仍需保留 libusb。项目**尚未发布到 PyPI**。**不要在这个外层文件夹运行 `pip install .`**：这里存放的是安装包，而非已展开的源码。

之后每次新开终端，先回到这个文件夹运行 `source .venv/bin/activate`，再使用 Python。

## 使用

关闭占用同一转接线的其他程序，连接仪器，并在仪器面板确认 GPIB 地址。

```bash
python -m gpib_macarm list
# 将 24 改成仪器真实的 GPIB 地址：
python -m gpib_macarm query --address 24 --timeout 10000 '*IDN?'
```

`list` 只枚举 USB 转接线，不扫描仪器地址。打开控制器会发送 REN/IFC，影响共享总线；身份查询不会复位仪器或开启源输出。

```python
import gpib_macarm as visa

with visa.ResourceManager() as rm:
    with rm.open_resource(
        "GPIB0::24::INSTR",  # 转接线索引 0；将地址 24 换成实际值
        timeout=10000,      # 毫秒
        send_end=True,
    ) as instrument:
        print(instrument.query("*IDN?"))
```

通过 `write()`、`read()`、`query()` 使用各仪器支持的命令；同一转接线共用一个 manager。迁移基础 PyVISA 脚本可使用 `import gpib_macarm as pyvisa`，并将 `ResourceManager("@py")` 改为无参数的 `ResourceManager()`。

## 已知边界与下一步

已实测 ARM macOS 上的 NI GPIB-USB-HS + **Keithley 2400**、NI GPIB-USB-HS + **SRS SR830**。**请保留 `send_end=True`：无 EOI 写入目前会失败。** 显式恢复只在本次 SR830 组合验证。通信故障后停止失败批次，核对身份、设置及真实输出状态，再开始新批次；具体处理办法见同文件夹的 **[CLAUDE.md](CLAUDE.md)**。

下一步重点是无 EOI 与大数据分块写入、更多故障恢复、二进制与长期/多仪器采集、跨机器安装和 macOS CI。2450、Intel Mac 尚未验证；通信成功不等于测量准确度通过。

GPL-2.0-or-later，非 NI 官方驱动。愿和我一样用 Mac 做实验的博士生，少熬几个调驱动的夜，多喝几杯不用续命的咖啡。☕
