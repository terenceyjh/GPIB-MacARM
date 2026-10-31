# Test summary / 测试概览

Evidence reviewed: 2026-11-01. Hardware checks performed: 2026-10-31.

记录核对日期：2026-11-01；以下实物测试于 2026-10-31 完成。这里只保留简要结论，详细日志、设备标识及测量数据留在本地，不随仓库或 release 分发。

## Hardware / 实物

Tested environment: macOS 14.8.9 / arm64, libusb 1.0.30; Python 3.11.6 for 2400 tests and 3.13.9 for SR830 tests.

| Adapter / 转接线 | Instrument / 仪器 | Passed / 已通过 | Limits / 边界 |
| --- | --- | --- | --- |
| NI GPIB-USB-HS (`3923:709b`) | Keithley 2400 | SCPI writes/readback, repeated identity queries, fragmented/raw reads, finite four-wire current sweeps and long text replies / SCPI 读写、连续身份查询、分块与原始读取、四线有限电流扫描及长文本回复 | Measurement accuracy unvalidated; new recovery implementation not retested here / 测量准确度未验收，新恢复实现尚未在此组合复验 |
| NI GPIB-USB-HS (`3923:709b`) | SRS SR830 | Repeated queries, 42-minute noise scan, explicit recovery after read timeout, partial reply and failed no-EOI write / 连续查询、42 分钟噪声扫描，以及读取超时、部分回复、无 EOI 写失败后的显式恢复 | Recovery passed; the no-EOI write itself still failed / 恢复通过，无 EOI 写入本身仍失败 |

**Default LF + EOI works on these combinations. Keep `send_end=True`.** 2450, other adapter models/firmware, Intel Macs, unplug/power-loss recovery, binary measurements, large multi-chunk writes and multiple instruments sharing a bus remain unvalidated.

**上述组合保留默认 LF + EOI。** 2450、其他线缆/固件、Intel Mac、拔插/断电恢复、二进制测量、大数据分块写入和多仪器共线仍待验证。通信成功不证明测量准确或源输出已经关闭。

## Software / 软件

- Release checks on 2026-11-01: **57 offline tests passed, zero skipped**, including exclusion of private files from the source ZIP.
- Both release archives installed with pip into fresh arm64 environments: source ZIP on Python 3.11.6 and sdist on Python 3.13.9. Native loading outside the source folder, pip check and all 57 tests passed in each environment.
- Native ASan/UBSan checks passed in the preceding development round. No new instrument tests were performed during release preparation.
- Earlier Linux x86_64 build/install and offline checks passed on an earlier revision; Windows checks covered Python only. Neither establishes current-revision hardware support there.

2026-11-01 打包验证：**57 项离线测试通过、零跳过**。ZIP 与 tar.gz 分别在新的 arm64 Python 3.11.6 / 3.13.9 环境完成 pip 安装，原生库加载、pip check 及全套测试通过；检查确认不夹带本机记录和二进制产物。上一轮原生 sanitizer 检查通过，本轮未重跑仪器测试。Linux/Windows 的历史结果不代表当前版本已完成这些平台的实物验收。

## Remaining work / 待办

No-EOI writes and final-chunk EOI handling; broader fault recovery; binary/longer/multi-instrument acquisition; cross-machine installation and macOS CI. See [README](../README.md) / [中文说明](../README.zh-CN.md) and [CLAUDE.md](../CLAUDE.md).
