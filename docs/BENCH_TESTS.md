# Guided bench acceptance / 现场配合测试

These tools are for the **unreleased development tree**. A prepared plan or a
simulated test does not establish hardware support. Read [CLAUDE.md](../CLAUDE.md)
and the current [test summary](VALIDATION.md) first. Use one idle adapter and
confirmed instrument addresses; the first instrument must be a Keithley **2400**.
Keep detailed reports, identities and measurement files in ignored local storage.

本流程面向未发布开发代码。先读 CLAUDE.md 与测试概览；关闭占用转接线的其他程序，确认型号和真实地址。第一个资源必须是 2400。准备计划和离线模拟均不算实物通过。

## Prepare without touching hardware / 先准备，不访问设备

```bash
# Address 24 is an example: use the confirmed address. Choose a NEW directory.
python tools/bench_acceptance.py \
  --resource GPIB0::24::INSTR \
  --physical usb power --functional \
  --acquire-seconds 3600 --current 2.5e-6 --compliance 21 \
  --plan --output build/validation/bench-plan
```

`--plan` writes a `prepared` report without loading the native backend,
enumerating USB or opening an instrument. It does not execute a test. Run the
live test later with the same chosen options, **without `--plan` and with a new
output directory**. Confirm the sample can tolerate the chosen current and
voltage protection first; the example values are not universal sample limits.

`--plan` 只生成计划，不枚举 USB、不打开仪器。正式运行时去掉 `--plan`，并换一个新输出目录。带 `--acquire-seconds` 会复位、配置并通电测量；先确认样品允许的激励与保护参数。省略该选项时不会安排采集。

## Physical steps / 人工操作

The program stops at each physical step and saves its instruction in the report's
`waiting` field. Complete the stated action and then enter `done`. An agent can
run the program and relay these prompts; the operator need only perform the
physical action and report completion. Empty input, EOF or any other response
cancels; elapsed time is never treated as confirmation.

程序会逐步停下来提示。按当条提示操作，完成后输入 `done`；由 agent 操作时，只需告诉 agent“已完成”，让它继续。不要提前执行后面的步骤。

1. If the adapter is absent, verify the 2400 front panel shows **OUTPUT off**,
   unplug only the adapter's **USB end**, wait at least five seconds and reconnect.
   Leave the sample's four wires and GPIB connector in place.
2. For the USB fault test, unplug the USB end and **leave it disconnected**. The
   program verifies the missing adapter, I/O failure and shared-controller lockout.
   Reconnect only when prompted. The program identifies the same adapter by
   serial, keeps old sessions faulted, then opens a new controller and checks
   identities, settings and output-off. A changed USB enumeration index is allowed.
3. Before the power test, existing buffer data are saved locally and their
   transfer format restored. Then switch off the 2400 with its output off and leave USB
   connected. Wait for the next prompt before switching it on. Confirm boot has
   finished, the panel is ready and **OUTPUT is off**. The program explicitly
   recovers communication and reports any changed settings; it does not restore
   them blindly or resume a failed measurement.

需要配合的操作通常是：先恢复 USB 连接，再做一次有意的 USB 拔插，以及一次 2400 关机/开机。故障检测期间不要提前插回或开机；样品接线保持不动。身份变化、输出未关闭或异常恢复失败都会停止后续测试。

## Automatic checks / 自动测试

With `--functional`, the suite checks existing-buffer binary transfers, read
timeouts, partial/over-limit replies and explicit recovery. Binary checks cover
both byte orders, SREAL/REAL,32, multiple requested chunk sizes and separate
header/payload reads. Native requests remain bounded to 4096 bytes.

With `--acquire-seconds`, the suite first performs a three-point pilot and a
2500-point batch, then binary/recovery checks, then the selected duration of
finite ten-point batches. Instrument-side TCO automatic output-off is checked
after every batch. Raw replies and CSV are saved; a failed batch stops the suite
without replay. If output-off cannot be verified, the child report explicitly
requires a physical output check. The old instrument buffer is saved locally
before a requested reset.

No-EOI is checked **last**. The program distinguishes a write-call timeout from
a later read timeout. It never emulates the missing write acknowledgement. Only
if the short no-EOI transaction completes does it attempt 65541- and 131076-byte
writes, using short harmless `*WAI` lines and a final identity query. Every native
chunk must acknowledge completion; EOI is enabled only for the final chunk. A
missing completion blocks those large writes and leaves the report `partial`.

自动阶段无需反复人工操作。无 EOI 测试放在最后；缺少写完成确认时不会发送大消息，也不会把 USB 已发送解释成命令执行成功。一小时采集和整体实物通过均须以实际报告为准。

## Additional instruments / 多仪器共线

Repeat `--resource` for each **confirmed, distinct address on the same adapter**.
The 2400 stays first. Default concurrent queries are `*IDN?`, at least 100 per
instrument and at least 60 seconds. Optional `--query` values can supply one
common query or one per resource; `--numeric` checks finite numeric replies and
field counts. Measurement queries require their own authorized settings/output.

All instruments share one manager/controller, including shared-fault checks.
Two sessions pointing to the same physical address do not count as two
instruments and are rejected. Do not guess or scan the second address. If more
than one adapter is connected, supply its known `--serial`.

第二台仪器的型号、地址及查询范围确认后，再追加对应资源。只有一台 2400 时，不把软件模拟或同地址双会话记为多仪器实测。

## Reports / 结果含义

| State | Meaning |
| --- | --- |
| `prepared` | Plan only; no hardware tests ran |
| `running` + `waiting` | Awaiting the stated operator action |
| `complete` | All checks selected in this run passed; this does not cover unselected roadmap items |
| `partial` | Requested checks remain blocked, such as unconfirmed no-EOI writes |
| `failed` | An unexpected check failed; remaining phases stopped |
| `cancelled` | The operator declined, input ended or execution was interrupted |

Each run must use a new directory. Reports are written after phase transitions;
do not reuse a failed directory to make an earlier failure look successful.
