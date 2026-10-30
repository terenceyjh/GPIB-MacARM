# 验证记录

2026-10-30，源码版本 0.1.0；KAME 固定提交见 UPSTREAM.json。

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

尚未完成，不能视作已通过：

- macOS Apple Silicon/Intel 的实际编译及原生加载。
- 实物 NI 转接线的 USB 通信、REN/IFC、寻址和 SCPI。
- 其他 PID/型号、固件、仿制线、USB hub、长消息及长期采集。
- 传输中拔插、仪器断电、总线超时后的实物恢复行为。

Linux 测试不能证明 Mac 的 IOKit/libusb 行为一致。当前是已完成独立封装、构建和离线加固、可在 Mac 编译验收的初版源代码驱动。

复现：

```bash
python -m unittest discover -s tests -v
bash tools/test_native.sh
python -m gpib_macarm info
python -m gpib_macarm list
```

实机步骤见 MAC_ACCEPTANCE.md。mock 和构造包测试不代表硬件回归。
