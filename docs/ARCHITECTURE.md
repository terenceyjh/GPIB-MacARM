# 架构、范围与本地改动

此包复用 KAME 的 C 核心，增加很薄的 C ABI 和 ctypes Python 层。基本 SCPI 不需要完整实验框架或 VISA 插件协议。ctypes 的 CDLL 在原生调用时释放 GIL；Python 层保护整个 query 的事务，原生层保护单个控制器调用。

| 路径 | 责任 |
| --- | --- |
| src/gpib_macarm/api.py | Controller/Instrument/ResourceManager；消息边界、文本终止符、共享锁、生命周期 |
| src/gpib_macarm/_backend.py | ctypes 类型声明、缓冲区和 Python 异常映射 |
| native/driver.cpp | 基于 KAME NiGpibDriver 流程的独立封装；USB 选择/占用/恢复、attach/detach、checked REN/IFC、原始读写和 END 标志 |
| vendor/kame/linux-gpib | KAME 携带的 linux-gpib C 驱动与头文件 |
| vendor/kame/osx_compat.h | POSIX/pthread/libusb 兼容层；macOS 与 Linux 共用 |
| vendor/kame/gpib_stubs.c | 必需的 gpib_common 符号替代；不是完整 gpib_common 实现 |
| vendor/kame/NiGpibDriver.* | 保留的上游参考实现，不参与本包编译 |
| vendor/kame/win_compat.h | 保留的上游文件；本包当前不支持 Windows 原生构建 |

每个 Controller 占用一个 libusb interface。多个仪器共用该控制器，按地址通信。ResourceManager 缓存控制器；Instrument.close 仅关闭逻辑会话，manager.close/controller.close 释放物理适配器。weakref.finalize 是遗漏显式关闭时的兜底，推荐使用 with。

KAME 的 GUI、测量框架、Qt、GSL、FFTW、脚本框架、STM、内存池和 MCP 均未引入。固件烧写和 NI 官方驱动配置也不在范围内。

本地修复：

- C 读取解析器增加真实 USB 长度参数，逐段检查数据块、读状态、辅助寄存器状态、长度和终止块；短包及计数不一致返回 EPROTO。
- 实物回包兼容：接受 16 字节紧凑尾部及 28 字节含寄存器写确认的尾部。已连接 HS 的紧凑格式在小块读取时最后块长度不可靠，改用请求长度减 IBRD 剩余计数，并检查结果确实落在最后一个已接收数据块内；保留状态标签、边界、填充和 TERM 校验。含寄存器确认的格式继续验证最后块长度及寄存器状态。
- 修复读取/写入/命令状态中“USB 短读但 retval=0”被当作成功的路径；校验命令/写状态标签和残余计数。
- POSIX URB 接收调用者的 timeout_ms，不再将所有 bulk 固定为 10 秒；保留 USB timeout/no-device/access/busy/pipe 错误身份。
- interrupt URB 的取消标志使用原子操作；在 pthread_create 前标记已启动，防止快速回调重入创建第二个线程；反复错误时退避，拔除后退出。
- 原有 gpib_interface 的 IFC/REN API 返回 void；本包增加 checked 变体，让 open 能检查初始化错误。
- 异常路径关闭 EOS；二进制数据不删 CR/LF。读取根据 END/EOS 持续进行，超过默认 1 MiB 上限会报错。写入按 65535 字节分块，仅最后一块发送 EOI。
- 读取跨块保留同一 Talker 的寻址，直到 END/EOS 后才 UNL/UNT；未读完时拒绝切换读取地址、写入、轮询、清除或改变 REN。2400 手册 18-48/49 要求二进制回复期间不要提前取消 Talker。
- 单次底层读取请求限制为已验证的 4096 字节，较大的 Python `chunk_size` 仍通过连续读取组装完整消息，不静默截断。原因是本次 HS 在 40003 字节二进制回复上，65535 字节 IBRD 请求导致超时及无法重开；物理重插后，两种二进制格式、两种字节序及五种上层请求大小的完整复验通过，包括 65535 字节上层请求。
- 所有写入均不自动重试，避免有副作用的命令被执行两次。

EOI 与写完成是两个概念：EOI 随最后一个数据字节表示 END；关闭 EOI 的写入仍应在指定字节完成握手后结束，不能等待未来的 EOI 才算写完。`send_end=True` 只在最后一块请求 EOI，`False` 则所有块都不请求 EOI。LF 是仪器解释的字节终止符，与总线 EOI 分开处理。参见 [NI 数据传输终止说明（第 7 章）](https://download.ni.com/support/manuals/370904a.pdf)。

本驱动通过 NI USB 请求中的 EOI 标志控制转接线，依赖其完成状态核对写入计数；USB 完成状态属于转接线协议，不能与 GPIB 的 EOI 信号等同。2026-11-02 的三项最小 2400 检查中，LF+EOI 和仅 EOI 均收到真实写确认及正确回复；仅 LF、不发 EOI 时，原查询仍有正确回复，但缺少 USB 写确认。跟踪确认 EOI 标志已正确切换。当前未发现需改动的 EOI 标志编码，可靠的无 EOI 完成确认仍未解决；不能据此宣称支持无 EOI，也不能把缺确认当作成功。

写完成状态必须是完整的 12 字节 NI USB 回包：`0x0d` 状态标签、有效剩余计数和 `04 00 00 00` 结尾块均需通过校验。错误状态继续按原来的异常映射处理；短写不能返回完整成功计数，缺失回包不能通过通用状态或“USB 已发送”替代。此校验不改变 Python 分块与原生寻址的分工。

范围：一个系统控制器、主地址 0..30、顺序 SCPI、串行轮询和 SRQ 线查询。不提供二级地址、并行轮询 API、VISA 事件回调、控制器轮换、内核级异步取消、固件加载或 IEEE 488.2 二进制块便利解析。原始字节 API 可供应用自行解析二进制块，但仍需硬件验证。

没有宣称完成整个驱动审计。构造包、Linux 编译和无设备测试不能替代具体 Mac、转接线及仪器实测。

故障恢复：共享控制器在 I/O/协议错误后进入 faulted 状态，保留原异常并拒绝普通操作。native 不在失败传输后追加普通清理命令，正常清理错误向上传递。显式 `recover()` 在同一控制器锁内处理迟到 USB 完成包、已知部分回复及总线恢复；Python 对已知地址执行清除、按 MAV 有界丢弃旧消息，并在已有身份缓存时核对身份边界。不重放失败测量或触发，恢复失败保持 faulted。调用方仍须核对设置与实际输出，实测范围见 [测试概览](VALIDATION.md)。

失败关闭：原生 C ABI 记录 I/O/协议失败；发生此类错误或回复尚未读完时，析构先执行本地 disconnect（取消 URB 并标记接口不可用），再 detach 释放状态，避免 vendor 的正常关机寄存器请求排在旧操作之后。初始化失败也采用这个顺序。成功恢复后恢复正常关闭流程。原生离线测试覆盖真实 C++ 传输、关闭顺序及恢复流程的 USB 故障注入；这些检查不代表实际拔插/断电验收。

维护 vendor 时准备固定 KAME 提交，运行：

```bash
python tools/vendor_patch.py --source ../KAME/modules/charinterface/usermode-linux-gpib
```

脚本会重新复制 vendor 并记录哈希/补丁，仅用于维护。普通安装不运行该脚本，不需要原 KAME 仓库或 git 网络连接。

接口参考：[libusb 同步 I/O](https://libusb.sourceforge.io/api-1.0/group__libusb__syncio.html)、[setuptools 原生构建](https://setuptools.pypa.io/en/latest/userguide/ext_modules.html)、[Python ctypes](https://docs.python.org/3/library/ctypes.html)。
