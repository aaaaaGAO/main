> 对应验收清单 §6 · 工程根目录：python/release_02_1/

# 模块 6：串口通讯矩阵解析及中间文件生成

## 本模块要培训的内容（讲师 checklist）

- [ ] **仅中央域**编排里有 UART 步；左右后 / DTC **不会**跑 UART
- [ ] 产物是**一个**文本文件：`Uart.txt`（默认名，可在 FixedConfig 改）
- [ ] 文件最多三段：`[UARTRS232]`、`[IVIToMCU]`、`[MCUToIVI]`
- [ ] 输入两类：**串口参数**（界面弹窗 → `uart_comm_*`）+ **UART 矩阵 Excel**（`uart_excel`）
- [ ] 降级：有 RS232 无矩阵 → 只写 RS232 段；**两者皆无** → 失败
- [ ] 矩阵 Sheet 名固定：`IVIToMCU`、`MCUToIVI`；表头 7 列必填
- [ ] 日志：`generate_uart_from_config.log` + 解析表 `Uart_Matrix.log`
- [ ] 客户常问：为什么中央 Tab 有串口弹窗别的域没有？

---

## 代码位置总览（本模块「小地图」）

| 层级 | 路径 | 职责（一句话） |
|------|------|----------------|
| **入口** | `generators/capl_uart/entrypoint.py` | `UARTEntrypointWorkflowUtility.run_generation` |
| **主编排** | `generators/capl_uart/service.py` | `UARTGeneratorService.run_pipeline` |
| **矩阵/文本** | `generators/capl_uart/runtime_io.py` | `UARTExcelParser`、`generate_uart_content`、RS232 读配置 |
| **编排调用** | `services/task_service.py` | `run_uart()`（domain 固定 CENTRAL） |
| **编排** | `services/task_orchestrator.py` | **仅** `[CENTRAL]` 且 `run_uart=True` 时执行 |
| **解析日志** | `core/parse_table_loggers.py` | `get_uart_matrix_logger` → `Uart_Matrix.log` |
| **界面→INI** | `services/state_config_service.py` | `c_uart`、`uart_comm_*` 同步到 `[CENTRAL]` |

**产出**：`{output_dir}/Configuration/Uart.txt` + `generate_uart_from_config.log`

---

## 先用大白话讲清楚：UART 模块干什么

中央域台架有时要通过 **RS232 串口** 与 IVI/MCU 交互。工具不做实时通讯，而是：

1. 把您在界面填的 **COM 口、波特率、帧类型** 写进 `[UARTRS232]`
2. 把 **UART 通信矩阵 Excel** 里两个 Sheet 的消息/信号，转成 `[IVIToMCU]` / `[MCUToIVI]` 文本段
3. 整体保存为 `{output_dir}/Configuration/Uart.txt`，给下游 CAPL/配置加载

**培训话术**：

> 「UART 跟 CAN 不一样——它不生成 `.can`，只生成一份 **`Uart.txt` 配置**。而且**只有中央域**会跑这一步；左右后/DTC 编排里没有 UART。」

---

## 谁触发 UART

```
中央 Tab「开始运行」/ POST /api/generate_central
  → TaskOrchestrator（CENTRAL 顺序：uart → soa → can → xml）
  → TaskService.run_uart()          # 注意：domain 写死 CENTRAL
  → UARTEntrypointWorkflowUtility.run_generation()
  → UARTGeneratorService.run_pipeline()
```

| 入口 | 说明 |
|------|------|
| `TaskService.run_uart()` | 编排唯一生产入口；捕获异常 → `TaskResult` |
| `generators/capl_uart/entrypoint.py` | 薄入口，转调 `UARTGeneratorService` |
| 命令行 `python -m generators.capl_uart.entrypoint` | 调试/单独跑 UART |

---

## 逐文件讲解

### 1. `generators/capl_uart/entrypoint.py`

| 方法 | 口语解释 |
|------|----------|
| `UARTEntrypointWorkflowUtility.run_generation()` | 构造 `UARTGeneratorService()` 并 `run_pipeline` |

---

### 2. `generators/capl_uart/service.py` — `UARTGeneratorService.run_pipeline`

**主编排**，步骤与控制台 print 一一对应，培训可边跑边看：

| 阶段 | 做什么 |
|------|--------|
| 解析路径 | `resolve_runtime_paths()` → 工程根 + `Configuration.ini` |
| 日志 | `setup_logging` → `generate_uart_from_config.log`；`get_parse_logger` → `Uart_Matrix.log` |
| stdout Tee | 控制台输出同步进 log（从 `FrameTypeIs8676` 触发后开始抓） |
| 读 RS232 | `read_uart_rs232_config()` 读 `[CENTRAL]` 的 `uart_comm_*` |
| 读 FrameType | 优先 RS232 里的 `frameTypeIs8676`，否则 `[PATHS]` 候选键 |
| 解析 IO 路径 | `resolve_io_paths()` → 矩阵 Excel + `Configuration/Uart.txt` |
| 读矩阵 | 打开 Excel，分别读 `IVIToMCU`、`MCUToIVI` |
| 降级处理 | 矩阵文件不存在但有 RS232 → 警告后继续，只写 RS232 |
| 失败条件 | 两个 Sheet 都空 **且** 无 RS232 → `ValueError` |
| 写文件 | `generate_uart_content` → `write_text_safe`（utf-8，失败回退 gb18030） |

---

### 3. `generators/capl_uart/runtime_io.py` — 解析与拼装

#### `UARTExcelParser` — 矩阵读取

| 方法 | 口语解释 |
|------|----------|
| `read_uart_excel_data(excel, sheet_name, workbook=...)` | 读指定 Sheet，按 **Msg ID** 聚合多行信号 |
| `normalize_header_text()` | 表头去换行、压空白 |

**必填列（缺则该 Sheet 返回空列表并打 error 日志）**：

| 内部键 | Excel 表头识别规则 |
|--------|-------------------|
| `msg_id` | 含 `Msg ID` 且含 `Hex` |
| `message_name` | `Message Name` 或 `消息名称` |
| `dlc` | `DLC` + `Byte` |
| `signal_name` | `Signal Name` 或 `信号名称` |
| `array` | 列名 `Array` |
| `length` | `Length` + `Bits` |
| `value_type` | `Value Type` |

**行语义**：有 Msg ID 的行开新消息；后续无 Msg ID 的行把信号 append 到当前消息。

#### `UARTRuntimeIOUtility` — 配置与文本

| 方法 | 口语解释 |
|------|----------|
| `read_uart_rs232_config()` | 读 7 个 `uart_comm_*`；全无则 `None` |
| `read_frame_type_value()` | `[PATHS]` 里找 `FrameTypeIs8676` 或值为 0/1 的项 |
| `resolve_io_paths()` | `uart_excel` 缺省可回退 `input/MCU_CDCU_CommunicationMatrix.xlsx` |
| `generate_uart_content()` | 拼三段文本 |
| `write_text_safe()` | 落盘 |

**`[UARTRS232]` 格式示例**：

```
[UARTRS232]
port=3//端口号
baudrate=115200//波特率
frameTypeIs8676=0
```

`COM3` → `port=3`；非标准口名会尝试提取数字。

**`[IVIToMCU]` / `[MCUToIVI]` 格式**：

```
Msg:0x{msg_id} {message_name} {dlc}
{signal_name} {array} {length} {value_type}
```

---

## 配置键

| 键 | 节 | 说明 |
|----|-----|------|
| `uart_excel` | `[CENTRAL]` | UART 矩阵 Excel |
| `uart_comm_port` / `baudrate` / `frameTypeIs8676` 等 | `[CENTRAL]` | 串口弹窗写入（前端活跃键见 `ACTIVE_UART_COMM_CFG_KEYS`） |
| `output_dir` | `[CENTRAL]` | 输出根 → `{output_dir}/Configuration/` |
| `uart_output_filename` | `FixedConfig.ini` | 默认 `Uart.txt` |
| `FrameTypeIs8676` | `[PATHS]`（兼容） | 无 RS232 帧类型时的兜底 |

**界面**：中央 Tab `c_uart` 选矩阵；`c_uart_comm` 打开串口参数弹窗 → POST 保存到 `[CENTRAL]`。

---

## 完整处理流程

```
run_pipeline
  → load_config_with_repair（重复 option 自动清理）
  → uart_rs232_config = read_uart_rs232_config
  → input_excel, output_path = resolve_io_paths
  → open_workbook (可选 cache)
  → IVIToMCU = read_uart_excel_data(..., "IVIToMCU")
  → MCUToIVI = read_uart_excel_data(..., "MCUToIVI")
  → 校验：至少 RS232 或 矩阵有数据
  → content = generate_uart_content(frame_type, ivi, mcu, rs232)
  → write_text_safe(output_path)
```

---

## 客户常问

| 问题 | 怎么答 |
|------|--------|
| 「DTC 为什么没有 UART？」 | 产品域划分：UART 只服务中央台架；编排里 LR/DTC 不含 `run_uart` |
| 「只配了 COM 口没选 Excel」 | 允许；生成仅含 `[UARTRS232]` 的 `Uart.txt` |
| 「Excel 选了但 Sheet 报错」 | 看 `Uart_Matrix.log` 缺哪一列；表头必须在第 1 行 |
| 「IVIToMCU 有数据 MCUToIVI 没有」 | 可以；文件里只会有有数据的段 |
| 「输出乱码？」 | 优先 utf-8；失败会试 gb18030 |

---

## 演示建议

1. 中央 Tab：点串口配置 → 选 COM、波特率 → 保存（观察 INI `[CENTRAL]` `uart_comm_*`）
2. 选择 UART 矩阵 Excel（含 IVIToMCU / MCUToIVI）
3. 一键运行中央域，或脚本 `POST /api/generate_central` 且 `run_uart: true`
4. 打开 `{output_dir}/Configuration/Uart.txt`，逐段对照 Excel
5. 演示降级：去掉 `uart_excel` 仅留 RS232，确认仍生成
6. 演示失败：RS232 和 Excel 都清空 → 弹窗失败 + log 明细

**预计时长**：1h

---

**上一册**：[05-SOA通信矩阵模块.md](./05-SOA通信矩阵模块.md) · **下一册**：[07-CAN文件生成模块.md](./07-CAN文件生成模块.md)
