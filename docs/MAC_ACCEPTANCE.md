# Mac 编译与实机验收

交付环境没有 Mac 或实际 USB-GPIB 仪器。下面用于在你的 Mac 上完成余下验收。

1. 解压源码包进入 gpib-macarm。按 README 安装 Xcode Command Line Tools、Python 3.10+、libusb、pkg-config，创建 venv 并 pip install .。
2. 运行 uname -m、`python -c 'import platform; print(platform.machine())'`、brew --prefix，确认 Python 和 libusb 同架构。Apple Silicon 建议 arm64 加 /opt/homebrew；Intel 使用 x86_64 环境。
3. `python -m gpib_macarm info` 必须成功加载原生库。
4. `python -m unittest discover -s tests -v` 验证 Python/API 和原生解析器。若原生测试跳过，检查是否误导入了尚未编译的 src 目录，不要将跳过解释为通过。
5. 可选执行 `LIBUSB_INCLUDE_DIR="$(brew --prefix)/include" LIBUSB_LIBRARY_DIR="$(brew --prefix)/lib" bash tools/test_native.sh`，运行离线 sanitizer 测试。
6. 插入转接线，`python -m gpib_macarm list` 记录 index、型号、序列号。此命令不扫描 GPIB 地址、不发送 GPIB 命令。确认没有 NI-488.2 或其他进程占用 interface；按正常系统流程允许 USB 配件访问。
7. 在仪器面板确认主地址、接好总线并关闭其他控制程序。后续打开会话会初始化适配器，发送 REN/IFC。
8. `python -m gpib_macarm query --address 22 '*IDN?'`，用真实地址替换 22。不支持 *IDN? 的仪器使用手册规定的查询。按需设置 --read-term/--write-term 为 none、lf、cr、crlf。
9. `python tools/hardware_smoke.py --address 22 --count 100 --output hardware-smoke.json`。预期每次回复非空、身份一致且没有超时。脚本只执行你指定的查询，默认 *IDN?，不发送 *RST、不配置量程、不打开输出。
10. 在采集脚本中测试一条实际配置命令、一条慢测量查询。根据仪器手册设置 timeout/query_delay；NI 硬件超时档位向上取整，USB 等待还包含余量。
11. 测试超过 chunk_size 的已知回复并核对长度。没有此类查询时先使用短文本，不宣称长消息已实测。
12. 仪器完全断电重开、USB 拔插后重新建立 manager，各执行 smoke。旧会话不会自动重连。
13. 在受控条件下验证错误地址和超时后的恢复。写入失败不自动重发；按仪器手册选择 SDC、IFC 或关闭重开，确认下次查询没有残留数据。

可回传 info/list 输出、编译日志和 hardware-smoke.json，并说明 Mac/macOS/Python 架构、转接线 PID、仪器型号。USB 能枚举不代表 GPIB 通信已经通过。
