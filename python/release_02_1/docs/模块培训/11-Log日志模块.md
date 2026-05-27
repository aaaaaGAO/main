> 对应验收清单 §11 · 工程根目录：python/release_02_1/

# 模块 11：Log 日志模块

## 本模块要培训的内容（讲师 checklist）

- [ ] 每次点「运行」新建 **`log/log_YYYYMMDD_HHMMSS/`**，不是追加同一个文件
- [ ] 两个子文件夹：**生成文件日志/**、**解析表格日志/**
- [ ] 同一次编排里 CAN、XML、DID… **共用同一时间戳目录**（环境变量传递）
- [ ] 各模块典型 log 文件名（generate_can_from_excel.log、IO_Mapping.log…）
- [ ] **PROGRESS 级别**：进度类消息始终可见，不受 `log_level_min` 限制
- [ ] `log_level_min` 在 **当前域** 配置节（LR/CENTRAL/DTC）
- [ ] **TeeToLogger**：旧代码 `print()` 也会进 log
- [ ] **caseid 去重**：同进程重复 ID 消息只写一次
- [ ] 如何用 log 排错：表头、IO、关键字、用例 ID
- [ ] 客户常问：「log 在哪？」「为什么第二次运行是新文件夹？」

---

## 代码位置总览（本模块「小地图」）

| 层级 | 路径 | 职责（一句话） |
|------|------|----------------|
| **运行目录** | `core/log_run_context.py` | `RunLogContext`：时间戳目录、env 共享、域标记 |
| **生成器日志** | `core/generator_logging.py` | `GeneratorLogger`：RotatingFileHandler、PROGRESS 双写 |
| **解析表日志** | `core/parse_table_loggers.py` | TestCases / IO / UART / Clib / caseid 专用 logger |
| **去重** | `core/caseid_log_dedup.py` | `DedupOnceFilter` 同进程消息去重 |
| **基础** | `utils/logger.py` | TeeToLogger、级别、PROGRESS_LEVEL、读 `log_level_min` |
| **stdout 劫持** | `core/run_context.py` | `tee_stdout_stderr` / `restore_stdout_stderr` |
| **编排触发** | `services/task_orchestrator.py` | 每次运行开头 `RunLogContext.reset()` |
| **打包导出** | `infra/logger/api.py` | re-export，供 PyInstaller hidden-import |

**目录结构**：`log/log_YYYYMMDD_HHMMSS/生成文件日志/` + `解析表格日志/`

---

## 先用大白话讲清楚：log = 「黑匣子」

> 「生成过程中控制台刷很快，客户看不清。工具把每次点击『开始运行』的所有过程记到 **`log/log_时间戳/`** 里：  
> - **生成文件日志**：各模块主流程（写 CAN、写 DID…）  
> - **解析表格日志**：读 Excel 表头、IO 表、用例表时的明细  
> 第二次再点运行，会 **新开一个时间戳文件夹**，不会盖掉上次的，方便对比。」

---

## 目录结构（培训打开磁盘对照）

```
{工程根}/log/log_20260525_143022/
├── 生成文件日志/
│   ├── generate_can_from_excel.log
│   ├── generate_xml_from_can.log
│   ├── generate_did_config.log
│   ├── generate_resetdid_from_excel.log
│   ├── generate_soa_startsetserver.log
│   ├── generate_uart_from_config.log
│   └── generate_cin_from_excel.log
└── 解析表格日志/
    ├── IO_Mapping.log
    ├── TestCases.log
    ├── Uart_Matrix.log
    ├── DIDConfiguration_Matrix.log
    ├── ResetDID_Matrix.log
    ├── Clib_Matrix.log
    └── caseid_clean_dup.log
```

---

## 逐文件讲解

### 1. `core/log_run_context.py` — 一次运行的「log 房间号」

| 类/方法 | 口语解释 |
|---------|----------|
| `RunLogDirs` | dataclass：root / gen_dir / parse_dir |
| `RunLogContext.reset()` | **每次编排开始**清空 env + 去重过滤器 |
| `RunLogContext.set_domain(domain)` | 记录 LR_REAR/CENTRAL/DTC，供读 log_level |
| `RunLogContext.ensure_dirs(base_dir)` | 创建或复用当前进程的时间戳目录 |
| 环境变量 | `RUN_LOG_ROOT`、`RUN_LOG_GEN_DIR`、`RUN_LOG_PARSE_DIR`、`RUN_LOG_DOMAIN` |

**谁调用 reset？** `TaskOrchestrator.run_generic_bundle` 开头。

---

### 2. `core/generator_logging.py` — `GeneratorLogger`

| 能力 | 口语解释 |
|------|----------|
| `GeneratorLogger.setup()` | 按 spec 创建 RotatingFileHandler（5MB×20） |
| 双 Handler | 主 log 排除 PROGRESS；同一文件另挂 PROGRESS-only Handler |
| `log_mgr.clear()` | 运行结束移除 handler，防泄漏 |
| `LogSpecConfig` | 可配子目录、basename、过滤规则 |

各 `generators/*/runtime*.py` 在入口 `setup()` 一次。

---

### 3. `core/parse_table_loggers.py` — 解析表专用

| 函数 | 文件 | 何时写 |
|------|------|--------|
| `get_testcases_parse_logger` | TestCases.log | CAN/XML 读用例 Excel |
| `get_uart_matrix_logger` | Uart_Matrix.log | UART 矩阵表头 |
| `get_clib_matrix_logger` | Clib_Matrix.log | Clib 表 |
| `get_caseid_clean_dup_logger` | caseid_clean_dup.log | 用例 ID 清洗/重复 |

`get_parse_file_logger`：若时间戳目录变了，**重建** handler。

---

### 4. `core/caseid_log_dedup.py`

| 符号 | 口语解释 |
|------|----------|
| `LogDedupManager.reset()` | 随 `RunLogContext.reset()` |
| `DedupOnceFilter` | 相同消息文本只记录一次（CAN+XML 双写时防刷屏） |

---

### 5. `utils/logger.py` — 基础能力

| 符号 | 口语解释 |
|------|----------|
| `PROGRESS_LEVEL = 25` | 自定义级别；「解析 Excel 文件: xxx」永远可见 |
| `ProgressOnlyFilter` / `ExcludeProgressFilter` | 拆分进度与普通 log |
| `TeeToLogger` | 把 stdout/stderr 写入 logger；防双 timestamp |
| `get_log_level_from_config(base_dir, section)` | 读域节 `log_level_min` |
| `log_progress_or_info` | 进度行路由 |

`core/run_context.py` 的 `tee_stdout_stderr` / `restore_stdout_stderr` 与生成器 finally 配对。

---

### 6. `infra/logger/api.py`

薄 re-export，供 `build_exe.py` hidden-import，避免打包缺模块。

---

## 完整生命周期（一次点击「运行」）

```
TaskOrchestrator 开始
  RunLogContext.reset()
  RunLogContext.set_domain("LR_REAR"|...)
  ↓
子任务 CAN:
  GeneratorLogger.setup() → ensure_dirs（复用同目录）
  tee_stdout_stderr
  excel_repo → TestCases.log
  io_mapping → IO_Mapping.log
  finally clear + restore
  ↓
子任务 XML / DID / …（同样复用 RUN_LOG_*）
  ↓
编排结束；用户打开 log/log_时间戳/ 查问题
```

---

## 配置与界面

| 配置键 | 节 | 界面 |
|--------|-----|------|
| `log_level_min` | `[LR_REAR]` / `[CENTRAL]` / `[DTC]` | 各 Tab 日志级别下拉 |

级别越高越安静；**PROGRESS 不受影响**。

---

## 排错指南（培训表格）

| 现象 | 先看哪个 log |
|------|--------------|
| 用例少了 | TestCases.log（过滤/表头） |
| 步骤 IO 没替换 | IO_Mapping.log |
| 用例 ID 变了 | caseid_clean_dup.log |
| DID 某 Sheet 没有 | DIDConfiguration_Matrix.log |
| UART 段为空 | Uart_Matrix.log |
| 关键字报错 | generate_can_from_excel.log + CAN sheet 子 log |

---

## 客户常问问题（备答）

| 问题 | 建议回答 |
|------|----------|
| log 在 EXE 哪？ | EXE **同级** `log/` 目录（config 也不打进包） |
| 能否关闭 log？ | 不能关目录；可调 `log_level_min` 减少细节 |
| 两次运行 log 混在一起？ | 不会；每次 reset 新时间戳（同一次编排内共用） |
| 控制台和文件不一致？ | 控制台可能过滤 PROGRESS；以文件为准 |

---

## 演示建议

1. 连续点两次「运行」→ 对比两个 `log/log_*` 文件夹  
2. 故意错表头 → 打开 TestCases.log  
3. 改 log_level 为 warning → 对比 log 体积  
4. 全链路跑完 → 带学员浏览两个子目录文件名  

**预计时长**：约 1h

---

**上一册**：[10-工程配置保存导入模块.md](./10-工程配置保存导入模块.md) · **下一册**：[12-打包模块.md](./12-打包模块.md)
