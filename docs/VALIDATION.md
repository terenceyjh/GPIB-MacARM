# 验证记录

源码版本 0.1.0；KAME 固定提交见 UPSTREAM.json。

## 2026-10-30：Windows / Linux

已实际完成：

- Windows Python 3.14：Python API 离线测试；原生测试按平台跳过。
- WSL2 Linux x86_64 / Python 3.10.12 / GCC 11.4：C11/C++17 编译、链接系统 libusb 运行库、ctypes 加载成功。
- Linux 共 30 项 unittest 全部通过：22 项 Python 行为测试、2 项交付/来源完整性测试、6 项原生解析器/C ABI 测试。覆盖整次 query 线程锁、长回复、二进制保留、EOI/EOS、消息上限、零进展、超时不重试、关闭和共享控制器、参数验证。
- 原生构造包覆盖正常 15/30 字节块、逐字节截断、错误读状态标签、辅助寄存器错误、非法长度和终止块。
- ASan + UBSan：20,000 个短/畸形回包通过实际 C 解析器，没有报告越界或未定义行为。
- ASan + UBSan：实际 POSIX URB shim 的模拟 bulk 测试验证 32000 ms 超时传递、USB timeout/no-device 错误身份和完成回调。
- Linux wheel 构建成功，安装到项目独立 target 目录，从安装目录运行 info/list 成功。USB 枚举返回空列表，符合本环境无转接线的情况。
- 交付的 source.zip 已在独立解包目录由 pip 从零构建 wheel、安装到另一个项目内 target，并成功执行 info/list；压缩包不包含本机 Linux 二进制或缓存。
- 更名为 GPIB-MacARM 后已重新执行上述 30 项测试、原生构建、sanitizer、源码 zip/wheel 构建及独立安装，核对 gpib_macarm 导入名和 gpib-macarm CLI。

构建使用现有系统 libusb-1.0.so.0 和官方 libusb v1.0.29 头文件。头文件位于 gpib-mac/build-tools，仅用于本机验证，不进入交付包。没有修改系统驱动。

## 2026-10-31：macOS Apple Silicon 离线验收

实际环境：macOS 14.8.9（23J631）、arm64；Homebrew 5.1.7，前缀 `/opt/homebrew`；Python 3.11.6（arm64）；Apple Clang 15.0.0，Command Line Tools / MacOSX14.sdk；pkg-config 0.29.2；libusb 1.0.30（Homebrew arm64 bottle）。

- 本机原先缺少 libusb，通过 Homebrew 安装；沿用已有 Python 和编译工具，在项目 `.venv` 中升级 pip 至 26.2.2，并执行 `python -m pip install -v -e .` 成功。
- 原生 C/C++ 分别按 GNU C11 / GNU C++17 编译，无需修改构建脚本、协议或 vendor。隔离构建依赖为 setuptools 84.2.1、wheel 0.48.0、packaging 26.3。
- `python -m gpib_macarm info` 与 `gpib-macarm info` 均成功，通过 ctypes 加载本地 `_driver.dylib` 并报告 0.1.0 / arm64。`file` 确认原生库为 Mach-O arm64；`otool -L` 确认链接 Homebrew libusb、libc++ 和 libSystem；`pip check` 通过。
- 完整 unittest：30 项通过，0 失败、0 跳过；包括 22 项 Python API、2 项交付/来源哈希、6 项实际加载原生库的解析器/C ABI 测试。
- `bash tools/test_native.sh` 实际运行两个 ASan/UBSan 程序，均通过：模拟 bulk URB 的 32000 ms 超时传递、timeout/no-device 错误映射及回调；20,000 个短/畸形回包的 C 解析器检查。没有 sanitizer 错误报告。
- 构建保留了上游 GNU 旧式字段初始化、符号位比较、未使用函数，以及 sanitizer 链接时重复 `-lusb-1.0` 的警告；没有为消除警告修改 vendor 或关闭检查。
- 本轮仅做离线验收，未运行 `list`、仪器查询或 hardware smoke，未打开适配器或发送 REN/IFC。原生测试使用不存在的设备 index 检查错误路径，仅枚举而不初始化设备。
- 本地日志保存在 `build/validation/mac-build.log`、`mac-info.log`、`mac-unittest.log`、`mac-sanitizers.log`；原生库、虚拟环境和日志均由 Git 忽略。

## 剩余验证边界

尚未完成，不能视作已通过：

- Intel Mac 的编译及原生加载，以及其他 macOS/Python 组合。
- macOS 非 editable wheel / 源码压缩包的干净环境安装和跨机器验证。
- 实物 NI 转接线的 USB 通信、REN/IFC、寻址和 SCPI。
- 其他 PID/型号、固件、仿制线、USB hub、长消息及长期采集。
- 传输中拔插、仪器断电、总线超时后的实物恢复行为。

本机 Apple Silicon 构建、加载和离线测试通过，仍不能证明真实设备上的 IOKit/libusb、总线初始化或 SCPI 行为。当前是完成 Linux 与本机 Mac 离线验收、等待实物验收的初版源代码驱动。

复现：

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
bash tools/test_native.sh
python -m gpib_macarm info
```

实机步骤见 MAC_ACCEPTANCE.md。mock 和构造包测试不代表硬件回归。
