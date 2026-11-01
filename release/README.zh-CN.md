# GPIB-MacARM 0.1.0 — 安装与使用

**面向 Apple Silicon（ARM）Mac 的 GPIB 驱动。** 通过 NI GPIB-USB-HS 转接线与实验仪器通信，目前主要提供 Python 接口及命令行工具。原生驱动改编自 **[KAME](https://github.com/northriv/KAME) / [linux-gpib](https://linux-gpib.sourceforge.io/)**，无需安装 NI-488.2、NI-VISA 或内核扩展。

[English](README.md)

## 先看这里

当前文件夹中已经放好：

- `gpib_macarm-0.1.0.tar.gz`：交给 pip 安装的源码包，**里面这一层 tar.gz 不用手动解压**。
- `README.md` / `README.zh-CN.md`：中英文安装与基本用法。
- **[`CLAUDE.md`](CLAUDE.md)**：详细安装、接口用法与排错指南，可直接交给 agent。
- `LICENSE`、`THIRD_PARTY.md`、`SHA256SUMS.txt`：许可证、来源说明和校验文件。

## 安装

需要 Apple Silicon Mac、以 arm64 运行的 Python 3.10+、Xcode Command Line Tools 和 arm64 libusb。先准备 [Homebrew](https://brew.sh/)，然后执行：

```bash
xcode-select --install  # 已安装则跳过；请先完成弹出的安装流程
brew install python libusb pkg-config
python3 -c 'import platform, sys; print(platform.machine()); print(sys.executable)'
```

架构应显示 `arm64`。在终端进入**这个解压后的文件夹**，确保能看到 tar.gz 和本 README。可以先输入 `cd `，将这个文件夹拖进终端，再回车。

```bash
python3 -m pip install --user --break-system-packages --upgrade pip setuptools wheel
python3 -m pip install --user --break-system-packages --no-build-isolation ./gpib_macarm-0.1.0.tar.gz
python3 -m gpib_macarm info
python3 -m pip check
```

第一条 pip 命令更新安装/编译工具，第二条使用这些工具安装本包，直接装到默认 `python3` 的用户包目录。`--user --break-system-packages` 用于允许 Homebrew Python 执行该用户级安装，无需 `sudo`。参数说明见 [pip 官方文档](https://pip.pypa.io/en/stable/cli/pip_install/)。之后用同一个 `python3` 运行脚本，IDE 也选择对应解释器。

`info` 应显示版本 `0.1.0`、架构 `arm64` 和原生库路径；它不打开仪器。pip 会在你的 Mac 上编译驱动，运行时仍需保留 libusb。项目**尚未发布到 PyPI**。**不要在这个外层文件夹运行 `pip install .`**，按上面的命令安装旁边的 tar.gz 即可。

## 使用

关闭占用同一转接线的其他程序，连接仪器，并在仪器面板确认 GPIB 地址。

```bash
python3 -m gpib_macarm list
# 将 24 改成仪器真实的 GPIB 地址：
python3 -m gpib_macarm query --address 24 --timeout 10000 '*IDN?'
```

`list` 只枚举 USB 转接线，不扫描仪器地址；`*IDN?` 需由仪器支持。打开控制器会发送 REN/IFC，影响共享总线；这里的身份查询不会复位仪器或开启源输出。

将以下内容保存为 `example.py`，修改地址 24，再运行 `python3 example.py`：

```python
import gpib_macarm as visa

with visa.ResourceManager() as rm:
    with rm.open_resource(
        "GPIB0::24::INSTR",  # 转接线索引 0；将地址 24 换成实际值
        timeout=10000,      # 毫秒
        write_termination="\n",
        read_termination="\n",
        send_end=True,
    ) as instrument:
        print(instrument.query("*IDN?"))
```

`query()` 发送命令并读取回复；没有回复的命令使用 `write()`，读取已有回复使用 `read()`。默认文本写入添加 LF，文本读取去除末尾 LF。具体命令和超时按仪器手册设置，超时针对每次传输。同一转接线共用一个 manager。迁移基础 PyVISA 脚本可使用 `import gpib_macarm as pyvisa`，并将 `ResourceManager("@py")` 改为无参数的 `ResourceManager()`。

## 已知限制：无 EOI 写入

**日常使用请保留默认的 `send_end=True` 和 LF 换行终止符。** GPIB 支持无 EOI 传输，2400 也接受只用 LF 结束命令。但当前实测组合中，无 EOI 查询虽然送达 2400 并产生正确回复，转接线却没有返回预期的 USB 写完成确认，驱动因此超时，原因仍待定位。默认 LF+EOI 工作正常，仅 EOI 的 2400 身份查询也通过。参见 [2400 手册第 14 章](https://download.tek.com/manual/2400S-900-01_K-Sep2011_User.pdf)。

驱动沿用 linux-gpib 的 EOI 标志及真实写完成确认方式，不在缺少确认时假定成功，也不自动重发失败命令。超过 65535 字节的写入需要中间块不发 EOI，因此在当前实测组合上仍不支持，即使设置了 `send_end=True`。

通信故障后停止失败批次，核对身份、设置及真实输出状态，再开始新批次；恢复通信不等于关输出。详细处理办法见同文件夹的 **[CLAUDE.md](CLAUDE.md)**。

## 测试范围与未来方向

v0.1.0 安装包已在 ARM macOS 上通过 NI GPIB-USB-HS + **Keithley 2400 / SRS SR830** 测试，包括连续查询、2400 有限采集及 SR830 连续采集/恢复。本 ZIP 更新使用说明，内层驱动源码包沿用原 v0.1.0。

后续开发测试通过了单台 2400 的 USB 拔插/断电恢复、大二进制读取及一小时 10040 点采集；这些驱动改动**尚未进入本安装包**。版本范围见[项目测试记录](https://github.com/terenceyjh/GPIB-MacARM/blob/main/docs/VALIDATION.md)。测量准确度未验收。

未来可按需继续定位无 EOI 完成确认，扩展更多仪器/转接线，并测试多台真实仪器共享总线。其他仪器型号、其他固件和 Intel Mac 尚未验证。

GPL-2.0-or-later，非 NI 官方驱动。愿和我一样用 Mac 做实验的博士生，少熬几个调驱动的夜，多喝几杯不用续命的咖啡。☕
