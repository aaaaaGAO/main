> 对应验收清单 §4 · 工程根目录：python/release_02_1/

# 模块 4：Reset-DID 解析及中间文件生成

## 本模块要培训的内容（讲师 checklist）

- [ ] 业务名：**ResetDid_Value 配置表** → 输出 **`DIDInfo.txt`**（默认名，可 FixedConfig 改）
- [ ] 和模块 3 的区别：Config = 字段**布局**；Reset-DID = 各 **Sheet（ECU）× 车型列** 的**实际 Field_Data**
- [ ] 实现包 **`generators/capl_resetdid`**（不是旧名 capl_didinfo）
- [ ] 配置：`resetdid_inputs`（**管道** `路径 | Sheet`）、`resetdid_variants`（车型 CSV）、`output_dir` / `output_dir_resetdid`
- [ ] 界面：`resetdid_excel` / `d_resetdid_excel` → 保存成 `resetdid_inputs`（单路径时会自动补 `| *`）
- [ ] Excel 表头：**Configure DID、Length (Bytes)、Byte、Bit** + 表头区**车型列**（如 ACOSe, MY26…）
- [ ] Sheet 语义：常见 **LDCU / RDCU**；未指定 Sheet 时有默认挑选规则
- [ ] 编排步名 **`did_info`**（不是 resetdid）；开关与界面是否填 Excel 联动 `run_did`
- [ ] 守卫逻辑：没配 inputs → **skip**；配了但全 Sheet 解析为空 → **不生成文件**
- [ ] 日志：`ResetDID_Matrix.log` + `generate_resetdid_from_excel.log`
- [ ] 特殊解析：Bit 空 → 当 ALL；Byte/Bit 的 `END` 行；同 DID 同 BytePosition 重复告警

---

## 代码位置总览（本模块「小地图」）

| 层级 | 路径 | 职责（一句话） |
|------|------|----------------|
| **包出口** | `generators/capl_resetdid/__init__.py` | 导出 `ResetDidGeneratorService` |
| **入口** | `generators/capl_resetdid/entrypoint.py` | `ResetDidEntrypointWorkflowUtility.run_generation` |
| **核心业务** | `generators/capl_resetdid/service.py` | `run_pipeline`：多 Excel×Sheet×车型 → 写 DIDInfo |
| **Excel 解析** | `generators/capl_resetdid/runtime_io.py` | 表头/车型列、`generate_from_sheet` 文本块 |
| **配置/日志** | `generators/capl_resetdid/runtime.py` | `load_runtime_config`、`resetdid_inputs` 管道、Tee 日志 |
| **编排调用** | `services/task_service.py` | `run_did_info(domain)` |
| **编排顺序** | `services/task_orchestrator.py` | 步名 `did_info`（在 `did_config` 之后） |
| **常量/界面** | `services/config_constants.py` | `resetdid_inputs`、UI 键与 INI 映射 |

**产出**：`{output_dir}/Configuration/DIDInfo.txt` + `ResetDID_Matrix.log` / `generate_resetdid_from_excel.log`

---

## 先用大白话讲清楚：Reset-DID = 「每个车型复位填什么数」

> 「模块 3 告诉您 DID 里有哪些字段、占哪几位。Reset-DID 这份大 Excel 则在每个 **ECU Sheet**（比如 LDCU）里，按 **Configure DID** 分段，并在 **MY26、ID4 PA** 这些列里填每个字段的 **十六进制值**。  
> 工具把这些读出来，写成 **`DIDInfo.txt`**：先 `{Sheet名}`，再 `[车型名]`，再 `[0xDID]`，下面一串 `Field_Data:0x..`。」

**一张表帮客户记牢（培训必投屏）**：

| | DID Config（模块 3） | Reset-DID（模块 4） |
|--|---------------------|---------------------|
| 界面名称 | DID_Config 配置表 | ResetDid_Value 配置表 |
| 配置键 | `didconfig_input_excel` | `resetdid_inputs` |
| 编排步 | `did_config` | `did_info` |
| 输出文件 | `DIDConfig.txt` | `DIDInfo.txt` |
| Field_Data | 固定占位 `0x01` | **读 Excel 车型列真实值** |
| 多车型 | 无 | 有 `[ACOSe]`、`[MY26]` 等块 |

---

## 整体分工

```
TaskOrchestrator 步 did_info
    ↓
TaskService.run_did_info(domain)
    ↓
ResetDidEntrypointWorkflowUtility.run_generation()
    ↓
ResetDidGeneratorService.run_pipeline()
    ↓
{output_dir}/Configuration/DIDInfo.txt
```

---

## 逐文件讲解（`generators/capl_resetdid/`）

### 1. `__init__.py` — 包出口

| 导出 | 口语解释 |
|------|----------|
| `ResetDidGeneratorService` | TaskService 调用的服务类 |

---

### 2. `entrypoint.py` — 入口

| 类/方法 | 口语解释 |
|---------|----------|
| `ResetDidEntrypointWorkflowUtility` | 与 DID Config 对称的入口类 |
| `run_generation(domain=None)` | DTC 只读 `[DTC]`；默认 LR 只读 `[LR_REAR]`（**不跨节偷 PATHS**） |

---

### 3. `runtime.py` — 配置加载、日志、转发解析

**干什么**：比 DID Config 的 runtime 更「厚」——包含 **读 INI**、**Tee 日志**、以及把 Excel 解析委托给 `runtime_io`。

| 函数/类 | 口语解释 |
|---------|----------|
| `resolve_base_dir()` | 工程根目录 |
| `split_csv_values()` | `ACOSe,MY26` → 列表 |
| `iter_input_specs()` | 解析 `resetdid_inputs` 管道为 `(excel, sheets)` |
| `coalesce_resetdid_whitelisted_options()` | **仅白名单键**允许同节别名合并（防 get_first 式乱兜底） |
| `load_runtime_config()` | 返回 `(config_path, output_path, variant_names, inputs)` |
| `init_runtime()` | 双 log + TeeToLogger（带 `[resetdid]` 前缀清洗） |
| `clear_run_logger()` | 运行结束清理 |
| `get_progress_level()` | PROGRESS 级别 |
| `pick_sheet_name()` 等 | 转发到 `ResetDidRuntimeIOUtility` |

**`load_runtime_config` 要点**：

| 配置项 | 读取方式 | 默认 |
|--------|----------|------|
| 输出目录 | `output_dir_resetdid` 或 `output_dir` | 必填 |
| 输出文件名 | FixedConfig `resetdid_output_filename` | `DIDInfo.txt` |
| 车型列 | FixedConfig `resetdid_variants` 或节内 `resetdid_variants` | `ACOSe,MY26,ID4 PA,CMP21A` |
| 输入 | `resetdid_inputs` 管道 | DTC/LR 各自节内，缺则 **RuntimeError**（service 层可能 skip） |

**`iter_input_specs` 管道语义**：

| 配置写法 | 含义 |
|----------|------|
| `matrix.xlsx` | 只有路径 → 用 `pick_sheet_name` 默认 Sheet |
| `matrix.xlsx \| *` | 该 Excel **所有 Sheet** |
| `matrix.xlsx \| LDCU,RDCU` | 指定 Sheet 列表 |

---

### 4. `runtime_io.py` — Excel 表头 + 单 Sheet 生成

| 类/方法 | 口语解释 |
|---------|----------|
| `Field` | dataclass：字段名、byte/bit 范围（内部结构） |
| `find_header_row_and_cols()` | 前 50 行找 **Configure DID / Length (Bytes) / Byte / Bit** |
| `find_variant_cols()` | 在表头行及上方找车型列（大小写不敏感） |
| `pick_sheet_name()` | 优先参数 → 否则 LDCU/RDCU → 否则第一个 Sheet |
| `merged_cell_value()` | 合并单元格取左上角 |
| `parse_int_or_range()` | Byte：`3` 或 `2-5` / `2~5` |
| `parse_bit()` | Bit：`all`→整字节；`3`；`2-5`；`END`→停止 |
| `normalize_did()` | `1234` / `0x1234` → `0x1234` 大写 |
| `normalize_field_data()` | 空→`0x00`；保留 `0x` 前缀；去空格 |
| `compute_positions_and_length()` | 算 Field_BytePosition / bit / length（Motorola 风格） |
| `flush_did_header()` | 写 `{sheet}`、`[variant]`、`[0xDID]`、`DIDLength` 段头；**去重**避免重复头 |
| `generate_from_sheet()` | **单 Sheet + 单车型列** 生成一整段文本 |

**`generate_from_sheet` 行级逻辑（口语）**：

1. 遇到 **Configure DID** 列有合法 DID → 更新当前 DID + **Length (Bytes)** → 写段头  
2. 后续行读 Byte/Bit + **车型列单元格** → 拼 `Field_subDataName`（自动生成 `DID0x.._Byte.._Bit..` 标签）  
3. Bit 为空但 Byte 有 → **INFO**：按 ALL 处理  
4. Byte 为空 → ERROR 跳过  
5. 同一 DID+Length 下 **BytePosition 重复** → ERROR 告警  
6. `Field_Data` 来自**车型列**，不是固定 0x01  

**输出文本层次示例**：

```
{LDCU}
[MY26]
[0xCF00]
DIDLength:8;//DID数据长度BYTE
Field_subDataName:DID0xCF00_Byte0_BitALL;//字段名称
Field_BytePosition:0;//字段起始byte
...
Field_Data:0x12;//字段数据
```

---

### 5. `service.py` — `ResetDidGeneratorService.run_pipeline`

| 方法 | 口语解释 |
|------|----------|
| `run_pipeline(domain=None)` | 加载配置 → 循环 Excel/Sheet/variant → 写 DIDInfo.txt |

**双守卫（培训必讲）**：

1. **`inputs` 为空** → print「未配置…跳过」，**不生成文件**，正常 return  
2. **所有 Sheet 解析结果为空** → print「未解析到有效 DID…不生成文件」  

与 DID Config 不同：Reset-DID 在 LR 域 **缺 inputs 会 raise**（TaskService 对「未配置 ResetDid_Value 配置表」做 skip）；DTC 域同理。

---

## 完整处理流程

```
run_pipeline(domain)
  ① init_runtime（ResetDID_Matrix.log + generate_resetdid_from_excel.log）
  ② load_runtime_config → output_path, variant_names, inputs
  ③ inputs 空？→ 守卫 1 skip
  ④ for (excel, sheets) in inputs:
       打开 Workbook（rich_text=True）
       确定 target_sheets（* / 列表 / 默认 pick）
       for sheet_name:
         find_header_row_and_cols + find_variant_cols
         for variant_name in variant_names:
           generate_from_sheet(...) → 拼文本
  ⑤ all_parts 空？→ 守卫 2 不写文件
  ⑥ mkdir + write_text(output_path)
  ⑦ finally clear_run_logger
```

---

## 配置键、输入输出

### 配置键

| 键 | 节 | 界面 state 键 | 说明 |
|----|-----|---------------|------|
| `resetdid_inputs` | `[LR_REAR]` / `[DTC]` | `resetdid_excel` / `d_resetdid_excel` | 管道：`path \| *` 或多 Sheet |
| `resetdid_variants` | 同上（或 FixedConfig） | — | 逗号分隔车型列名 |
| `output_dir` / `output_dir_resetdid` | 同上 | `out_root` | 输出根 |
| `resetdid_output_filename` | `[FixedConfig.ini]` | — | 默认 `DIDInfo.txt` |
| `resetdid_variants` | `[FixedConfig.ini]` | — | 可覆盖节内车型列表 |

历史别名（同节白名单 coalesce）：`Resetdid_Inputs`、`Resetdid_Variants`、`Output_Dir_Resetdid` 等——**仅同节**，不跨 Tab 偷值。

### 输入

| 输入 | 说明 |
|------|------|
| ResetDid_Value Excel | 多 Sheet；表头含 DID/Length/Byte/Bit + 车型列 |
| `Configuration.ini` + `FixedConfig.ini` | 路径、车型、文件名 |

### 输出

| 输出 | 典型路径 |
|------|----------|
| `DIDInfo.txt` | `{output_dir}/Configuration/DIDInfo.txt` |
| `ResetDID_Matrix.log` | `log/log_*/解析表格日志/` |
| `generate_resetdid_from_excel.log` | `log/log_*/生成文件日志/` |

---

## 谁调用它

| 调用方 | 行为 |
|--------|------|
| `TaskOrchestrator` | **`did_info` 步**（在 `did_config` 之后） |
| `TaskService.run_did_info()` | 未配置表 → skip；其它异常 → 失败 |
| `ConfigManager` / `config_constants` | UI `resetdid_excel` ↔ `resetdid_inputs` |
| 命令行 | `python generators/capl_resetdid/entrypoint.py` |

---

## 客户常问问题（备答）

| 问题 | 建议回答 |
|------|----------|
| 为什么编排里叫 did_info 不叫 resetdid？ | 历史步名与验收清单一致；代码包名是 `capl_resetdid` |
| 只配了 DID Config 没配 Reset Excel？ | 只出 DIDConfig.txt；Reset 步 skip，**不算失败** |
| resetdid_inputs 和 didconfig_input_excel 能写同一个文件吗？ | **格式不同**；通常两份表，不建议混为一个 Excel |
| 车型列找不到？ | 检查 `resetdid_variants` 是否与 Excel 表头行车型名一致（大小写不敏感） |
| 为什么没生成 DIDInfo.txt？ | 看控制台/`ResetDID_Matrix.log`：可能 inputs 空、Excel 路径错、或所有 Sheet 被 skip |
| Sheet 没写 \| 后缀？ | 只写路径时默认挑 LDCU/RDCU/第一个 Sheet；多 Sheet 建议写 `path \| *` |
| Field_subDataName 为什么自动生成？ | Reset 模块用 `DID0x.._Byte.._Bit..` 规则，与 DID Config 里 Excel 的 name 列不同 |

---

## 演示建议

1. 界面选 **ResetDid_Value 配置表** → 看 INI `[LR_REAR] resetdid_inputs = ... \| *`  
2. 打开 Excel：指 **Configure DID、Length、Byte、Bit** 和 **MY26 等列**  
3. 运行生成 → 打开 `DIDInfo.txt`，找 `{LDCU}`、`[MY26]`、`[0x....]` 三层结构  
4. **并排对比** `DIDConfig.txt`（结构、Field_Data=0x01）与 `DIDInfo.txt`（真实 Field_Data）  
5. 打开 `ResetDID_Matrix.log`，看每个 Sheet×车型 的解析记录  
6. 清空 resetdid_inputs 再运行，演示 **skip 不报错**  
7. （可选）改错一个 variant 列名，演示 ERROR skip sheet  

**预计时长**：约 1h

---

**上一册**：[03-DID-Config模块.md](./03-DID-Config模块.md) · **下一册**：[05-SOA通信矩阵模块.md](./05-SOA通信矩阵模块.md)
