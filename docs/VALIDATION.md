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

## 2026-10-31：Keithley 2400 基础实物通信

沿用上述 macOS 14.8.9 / arm64 / Python 3.11.6 / libusb 1.0.30 环境。USB 枚举发现一只 GPIB-USB-HS（VID:PID `3923:709b`），可访问；参照用户提供的 `measure_tcr_v6.py`，打开 `GPIB0::24::INSTR`，设置 10000 ms 超时，取得包含 `KEITHLEY INSTRUMENTS INC.,MODEL 2400` 的真实身份回复，固件为 C34 / B01。转接线与仪器序列号只保存在本地报告，不写入本文件；枚举型号不代表另行验证了硬件真伪。

实际修复与验证：

- 首次身份查询收到 112 字节真实 USB 回包，但原解析器仅接受含寄存器确认的 28 字节尾部，因实际只有 16 字节紧凑尾部而返回 `ProtocolError`。增加两种严格长度分支，保留状态、填充与 TERM 校验。
- 小块读取又发现紧凑回包的最后块长度字段不可靠，例如请求 7 字节时返回 `0x53`，而 IBRD 剩余计数为零、实际数据确为 7 字节。紧凑格式改用请求长度减剩余计数，拒绝剩余计数超出请求、数据块不足或结果未落在最后块的情况。28 字节尾部继续检查最后块长度及寄存器写状态。
- 已更新 `tools/vendor_patch.py`、`vendor/local-fixes.patch` 和 `UPSTREAM.json` 的本地哈希。固定上游提交及原始哈希不变；补丁反向还原并恢复原始 CRLF 后，与记录的上游哈希一致。
- 重建最终原生库后，完整 unittest 为 **34 项通过，0 失败、0 跳过**：22 项 Python API、2 项交付/来源完整性、10 项原生解析器/C ABI。ASan/UBSan 的两个程序通过，包括紧凑/完整尾部、逐字节截断、20,000 个畸形包以及模拟 USB 超时/错误映射。`info` 和 `pip check` 通过。此次改动未重新运行 Linux/Windows 测试。
- `tools/hardware_smoke.py` 连续执行 100 次 `*IDN?`，全部非空且内容一致，无超时；时延见本地 JSON 报告。
- `ResourceManager` / `open_resource` 实物检查通过：18 种 `chunk_size`（1、2、3、4、7、8、14、15、16、29、30、31、63、64、79、80、81、4096）各执行 3 次身份查询，均完整一致；80 字节原始回复保留末尾 LF；`read_bytes(11)` 分 8 次恢复完整回复。
- 只读 SCPI 查询 `:OUTP?`、`:SOUR:FUNC?`、`:SENS:FUNC?`、`:FORM:ELEM?`、`:TRIG:COUN?`、`:SYST:RSEN?`、`*OPC?` 正常；串行轮询返回 0，SRQ 未置位。EOI 配合无写终止符、LF、CRLF，以及读 LF / 仅靠 EOI 均通过；50 ms `query_delay` 也经过实测。
- 正常关闭再打开后，另完成 100 次一致身份查询。正常通信检查报告共有 38 项记录，`success=true`。最终错误队列为 `0,"No error"`，输出状态在测试前后均为 0。

全程没有发送 `*RST`、`:OUTP ON`，没有修改量程/源值，也没有发 `:READ?` 或 `:MEAS?` 触发新测量。使用过正常 REN/IFC 初始化、SDC 清理，以及下述异常恢复诊断。因此本轮证明基础通信和读取路径，不代表 IV、TCR 或真实 V/I 测量已通过。参考脚本本身未修改或启动 GUI。

**实际失败的扩展检查，不能标成通过：**

- `send_end=False`，仅 LF 的 `*IDN?` 写入发生 USB 等待超时；当前组合应保留默认 EOI。不能据此宣称该硬件支持无 EOI 写入或需要中间无 EOI 分块的大写入。
- 在没有待回复查询时故意调用读取，100 ms 和 1000 ms 超时设置均出现超时，实际等待包含 USB 与清理时间，明显长于所设数值。之后直接复用原会话、立即关闭重开均出现失败或残留状态错配。发送适配器 STOP 并排空 USB 的试验未可靠解决问题，相关试验代码已撤回；最终只保留经验证的解析修复。稍后的独立重开恢复了正常通信，但不能宣传为可靠自动恢复。
- 就绪状态仍报告 `buffer[6]=0x12`、`buffer[9]=0x02` 不在原上游预期值内；这些诊断没有阻止本轮正常通信，未通过放宽初始化检查或隐藏日志来消除警告。

本地证据位于 `build/validation/`，由 Git 忽略：`hardware-smoke-2400.json`、`hardware-2400-transport.json`、`mac-hardware-smoke.log`、`mac-hardware-transport.log`、`mac-hardware-unittest.log`、`mac-hardware-sanitizers.log`、`mac-hardware-build.log`、`mac-hardware-info.log`。失败证据另存为 `mac-hardware-initial-failure.log`、`mac-hardware-chunk-failure.log`、`mac-hardware-chunk-matrix.log`、`mac-hardware-no-eoi-failure.log`、`mac-hardware-same-session-timeout-failure.log`、`mac-hardware-immediate-reopen-failure.log` 等。不要把早期失败报告和最终正常通信报告混为一轮全功能验收。

正常身份查询复现（仅对本次已确认的地址）：

```bash
.venv/bin/python -m gpib_macarm query --address 24 --timeout 10000 '*IDN?'
.venv/bin/python tools/hardware_smoke.py --address 24 --timeout 10000 --count 100 --output build/validation/hardware-smoke-2400.json
```

命令及终止符参考 [Keithley 官方 2400 Series User's Manual](https://download.tek.com/manual/2400S-900-01_K-Sep2011_User.pdf)，身份查询见 16-3，程序消息终止与多查询见 14-12/14-13。仪器手册规定的功能不能替代本转接线的实测结果。

## 2026-10-31：铜板四线电流扫描 IV

用户明确要求做四线 IV，并说明当前连接的是低阻铜板。为避免电压扫描持续进入限流，选择与参考脚本 TCR 配置一致的 Source I / Measure V，开启四线 remote sense，测量前 `*RST` / `*CLS`。电压保护设为 0.1 V，固定最低电压测量挡（配置值 0.2 V，读回满量程 0.21 V），延时 0.05 s，自动调零开启；用 `:READ?` 一次取得有限点数扫描。CURR 字段是源电流设定值，未启用独立电流测量，不能把它称为第二通道实测电流。

| 扫描 | 点数 | NPLC | READ 耗时 | 回复字节（不含 LF） | 原始线性拟合斜率 | R² |
| --- | --- | --- | --- | --- | --- | --- |
| −1 → +1 mA 试扫 | 21 | 1 | 2.392 s | 1175 | −1.337 mΩ | 0.457 |
| −10 → +10 mA | 101 | 5 | 35.688 s | 5655 | −0.1262 mΩ | 0.330 |
| +10 → −10 mA | 101 | 5 | 35.688 s | 5655 | −0.1295 mΩ | 0.338 |

通信与采集检查通过：

- 三次扫描共 223 点完整读回，电流序列/点数/时间戳校验通过；101 点回复超过默认 `chunk_size=4096`，完成了真实测量长回复的跨块读取。
- 每点状态字均为 4230148，包含 Remote Sense、I-Source、V-Measure；未出现超量程、真实/量程保护、OVP 或接触检查失败标志。四线软件模式的确启用，但这不构成物理接线的独立验证。
- 测量前的配置读回与错误队列正常，测量后错误队列均为 `0,"No error"`，同一会话的身份查询正常，无超时或解析错误。
- 使用 `:SOUR:CLE:AUTO ON`、`:SOUR:CLE:AUTO:MODE TCO`，在仪器内部计数完成后自动关输出；每次均先读回 `:OUTP? = 0`，再执行程序 finally 中的关输出/停止/归零，并再次确认输出为 0。最终停在固定电流模式、源值 0 A、四线开启、0.1 V 电压保护。
- 新增可复用的 `tools/keithley_2400_iv.py`，限制本测试电流不超过 10 mA、保护电压不超过 0.1 V，拒绝覆盖已有报告。测量数据保留原始字符串、CSV、配置读回、状态和清理结果；脚本把采集成功与电阻拟合质量分开。
- 完整离线 unittest 现为 **39 项通过，无失败或跳过**，新增 5 项覆盖状态/数据有效性、热电偏置下拟合和通信丢失时不得误报输出已关闭。此轮未改变原生代码。

**测量质量尚未验收：** ±10 mA 时电压约 −13.6～−19.2 µV，约 −16 µV 偏置明显；正反扫原始曲线均非理想直线，残差 RMS 约 1.05 µV，拟合出现负斜率。相同电流处两次曲线相关系数约 0.876，形状有一定重复性，不能简单归结为纯随机通信噪声。可能涉及 Sense 极性、四独立电极的几何布局、接触热电势或仪器/接线偏置；当前信息不能确定原因，也不能把表中负斜率当成铜板实际电阻。测试只确认测量命令、真实电压数据、有限扫描、长回复和正常关输出流程跑通，不能证明电阻测量准确度或校准。

**对实际采集的影响：**

- 参考脚本 `measure_tcr_v6.py` 的 2400 配置固定设置 10000 ms 超时。本次 101 点、NPLC 5 的 READ 实测约 35.7 秒，必须按整批测量时间留余量，本轮设置 60000 ms；超时仍不是严格的整个 query 截止时间。单点 TCR 与整批扫描的等待需求不同。
- 原参考脚本的 IV 回调在成功读取/拟合后才发送 `:OUTP OFF`，异常分支没有 finally 关输出；若 READ 超时，电脑报错并不意味着源输出已停止。新测试脚本增加了仪器自动关输出和 finally 清理，但通信失效时仍须检查实际面板，不能保证关输出命令必然送达。
- 保持 `send_end=True` 的默认 EOI，短 SCPI 命令正常；本轮长回复也已通过。此前关闭 EOI 写入和异常超时恢复的失败没有在本轮解决。发生超时应停止当前采集、标记本批失败并确认输出关闭，不能盲目重发 READ/输出命令，或把后续残留回复写入新的测量记录。

本地数据：`build/validation/iv-copper-4wire-1mA.{json,csv,raw.txt}`、`iv-copper-4wire-10mA-forward.{json,csv,raw.txt}`、`iv-copper-4wire-10mA-reverse.{json,csv,raw.txt}`；曲线 `iv-copper-4wire.png`，汇总 `iv-copper-summary.json`，离线测试日志 `mac-iv-unittest.log`。曲线绘制仅在本机 venv 安装 matplotlib，核心包仍不依赖它。

同一被动低阻样品上复现：

```bash
.venv/bin/python tools/keithley_2400_iv.py --resource GPIB0::24::INSTR --max-current 0.001 --points 21 --nplc 1 --compliance 0.1 --timeout 60000 --output build/validation/iv-new-1mA
```

此脚本会复位仪器、改变源/感测设置并在扫描时开启输出。参考脚本本身仍未修改；不要直接把本次参数用于未确认的其他样品。

## 2026-10-31：安装步骤复核与干净 venv 安装

为复核 README 的普通安装流程，在 `build/validation/mac-clean-venv` 新建 Python 3.11.6 虚拟环境，用该环境执行 `python -m pip install --no-deps .`，非 editable 安装成功。从源码目录之外的 `/tmp` 导入时，确认实际加载的是新 venv 内 `site-packages/gpib_macarm` 和其中的 `_driver.dylib`，不是工作目录的 editable 库。新环境的 `gpib-macarm info`、`pip check` 成功；使用新安装包运行仓库完整 unittest，39 项通过，无失败、无跳过。此轮未开启仪器或重跑输出扫描。

因此本机 **从仓库安装到新 venv 的非 editable 安装已验证**；不等于 Mac 源码压缩包独立解包安装、其他机器部署或其他 Python/macOS 组合已通过。日志为本地 `build/validation/mac-clean-install.log`、`mac-clean-install-unittest.log`。

## 剩余验证边界

尚未完成，不能视作已通过：

- Intel Mac 的编译及原生加载，以及其他 macOS/Python 组合。
- macOS 源码压缩包独立解包的干净安装、跨机器部署和其他 Python/macOS 组合；本机从仓库到新 venv 的非 editable 安装已通过。
- 其他转接线、PID/型号、固件、仿制线和 USB hub；当前一组设备结果不能外推。
- 比本次 5655 字节更大的回复、二进制测量数据、电压源 IV、TCR 与长期采集；铜板真实电阻及测量准确度尚未确认。
- 传输中拔插、仪器断电；无 EOI 写入、超时后可靠恢复仍有上述已知失败。

本机 Apple Silicon 构建与离线测试，以及上述单组设备的基础实物通信已通过。当前仍是早期驱动，完整硬件验收尚未完成。

复现：

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
bash tools/test_native.sh
python -m gpib_macarm info
```

实机步骤见 MAC_ACCEPTANCE.md。mock 和构造包测试不代表硬件回归。
