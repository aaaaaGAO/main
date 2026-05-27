> 对应验收清单 §3 · 工程根目录：python/release_02_1/

# 模块 3：DID Config 解析及中间文件生成

## 本模块要培训的内容（讲师 checklist）

- [ ] DID Config 产出什么：**`DIDConfig.txt`**，描述 DID 各字段的 Byte/Bit/长度（诊断配置结构）
- [ ] 和 Reset-DID（`DIDInfo.txt`）的区别：Config 是**字段布局**，Reset 是**各车型复位值**
- [ ] 配置键：`didconfig_input_excel`、`output_dir`；文件名在 **FixedConfig** 的 `didconfig_output_filename`
- [ ] Excel 规则：**每个 Sheet 名 = 一个 DID**（可带或不带 `0x` 前缀）
- [ ] 表头列：name / byte / bit（支持多种英文别名，见代码）
- [ ] 编排步名 **`did_config`**，在 `did_info`（Reset-DID）**之前**
- [ ] 未配置 Excel → **静默 skip**；配了但路径错/表头错 → **报错或 warning 跳过 Sheet**
- [ ] 与 **Config Enum** 的关系：同一 DID Excel 也可能被 `config_enum.py` 读，供 `Set_Config` 步骤翻译（模块 7 交叉讲）
- [ ] 日志：`DIDConfiguration_Matrix.log` + `generate_did_config.log`
- [ ] 客户常问：「DIDConfig 和 DIDInfo 两个 txt 都要吗？」

---

## 代码位置总览（本模块「小地图」）

| 层级 | 路径 | 职责（一句话） |
|------|------|----------------|
| **包出口** | `generators/capl_didconfig/__init__.py` | 导出 `DIDConfigGeneratorService` |
| **入口** | `generators/capl_didconfig/entrypoint.py` | `DIDConfigEntrypointWorkflowUtility.run_generation` |
| **核心业务** | `generators/capl_didconfig/service.py` | `DIDConfigGeneratorService.run_pipeline` 读 Excel 写 txt |
| **路径/日志** | `generators/capl_didconfig/runtime_io.py` | 工程根、双日志初始化、GeneratorConfig |
| **转发** | `generators/capl_didconfig/runtime.py` | re-export `DIDConfigRuntimeIOUtility` |
| **编排调用** | `services/task_service.py` | `run_did_config(domain)` |
| **编排顺序** | `services/task_orchestrator.py` | 步名 `did_config`（在 `did_info` 之前） |

**产出**：`{output_dir}/Configuration/DIDConfig.txt` + `DIDConfiguration_Matrix.log` / `generate_did_config.log`

---

## 先用大白话讲清楚：DID Config = 「这个 DID 长什么样」

> 「可以把 DID 想成一个**数据包**。DID Config 这份 Excel 告诉工具：这个包有多长（DIDLength）、里面每个字段占哪几个 Byte、哪几个 Bit、叫什么名字。  
> 生成出来的 **`DIDConfig.txt`** 就是给下游诊断/仿真配置用的**结构说明书**。  
> 它**不包含**各车型具体填什么值——那是模块 4 Reset-DID（`DIDInfo.txt`）的事。」

**和 IO Mapping 再对比一句**：IO Mapping 不产文件；DID Config **一定产** `DIDConfig.txt`（只要配了 Excel 且跑过编排）。

---

## 整体分工

```
TaskOrchestrator 步 did_config
    ↓
TaskService.run_did_config(domain)
    ↓
DIDConfigEntrypointWorkflowUtility.run_generation()
    ↓
DIDConfigGeneratorService.run_pipeline()
    ↓ 读 Excel 每个 Sheet
{output_dir}/Configuration/DIDConfig.txt
```

---

## 逐文件讲解（`generators/capl_didconfig/`）

### 1. `__init__.py` — 包出口

| 导出 | 口语解释 |
|------|----------|
| `DIDConfigGeneratorService` | 外部（TaskService）唯一推荐 import 的类 |

---

### 2. `entrypoint.py` — 命令行 / 编排入口

**干什么**：薄入口；`python -m generators.capl_didconfig.entrypoint` 或 TaskService 都走这里。

| 类/方法 | 口语解释 |
|---------|----------|
| `DIDConfigEntrypointWorkflowUtility` | 入口编排工具类 |
| `run_generation(domain=None)` | `domain='DTC'` 读 `[DTC]`；否则读 `[LR_REAR]`；委托 Service |

---

### 3. `runtime.py` — 转发层

**干什么**：一行 re-export，让 `service.py` import `runtime.DIDConfigRuntimeIOUtility` 而不是直接绑 `runtime_io`（结构统一）。

| 导出 | 指向 |
|------|------|
| `DIDConfigRuntimeIOUtility` | `runtime_io.py` 里的实现 |

---

### 4. `runtime_io.py` — 路径、配置、日志

| 方法 | 口语解释 |
|------|----------|
| `resolve_base_dir()` | 从当前文件位置反推工程根目录 |
| `load_runtime(base_dir)` | `GeneratorConfig(base_dir).load()`；找不到 Configuration.ini 则 print 错误并 return None |
| `setup_generator_logger()` | 双日志 spec：解析表 `DIDConfiguration_Matrix.log` + 生成 `generate_did_config.log` |
| `init_logging()` | setup logger + `tee_stdout_stderr`（控制台输出也进 log） |
| `get_progress_level()` | 返回 PROGRESS 级别常量 |

---

### 5. `service.py` — **核心业务** `DIDConfigGeneratorService`

| 方法 | 口语解释 |
|------|----------|
| `run_pipeline(domain=None)` | 完整流程：读配置 → 校验 → 开 Excel → 逐 Sheet 解析 → 写 txt |

**`run_pipeline` 分域读配置（必讲）**：

| 域 | Excel 键 | 输出目录键 | 输出文件名 |
|----|----------|------------|------------|
| DTC | `[DTC].didconfig_input_excel` | `[DTC].output_dir`（或别名） | FixedConfig `didconfig_output_filename`，默认 `DIDConfig.txt` |
| LR_REAR | `[LR_REAR].didconfig_input_excel` | `[LR_REAR].output_dir` | 同上 |

**输出路径规则**：  
`{output_dir}/Configuration/{didconfig_output_filename}`  
注意：在 `output_dir` 下**寻找已有 Configuration 子目录**，不会自动乱建（`anchor_level="self"`）。

**Excel 解析规则（逐 Sheet）**：

1. 表头在前 30 行内，列名匹配（不区分大小写/空格）：
   - **name**：`name` / `field_subdataname` / `subdataname`
   - **byte**：`byte` / `field_byteposition` / `byteposition`
   - **bit**：`bit` / `field_bitposition` / `bitposition`
2. 缺表头 → **warning，跳过该 Sheet**（不中断整个任务）
3. 数据行：Name/Byte/Bit 不能为空；Byte 须能 parse 成整数
4. **Bit 列语义**：
   - `all` → bit 位置 0，长度 8 bit
   - 单个数字 `3` → 1 bit
   - 范围 `2-5` → 起始 2，长度 4 bit
5. Sheet 输出块格式：
   ```
   [0xSheetName]
   DIDLength:{max_byte+1};//DID数据长度BYTE
   Field_subDataName:...;//字段名称
   Field_BytePosition:...;//字段起始byte
   Field_bitPosition:...;//字段起始bit;
   Field_FieldLength:...;//字段长度，单位bit;
   Field_SortOrder:0;//排序方式0是motorola,1是intel
   Field_Data:0x01;//字段数据
   ```
6. `Field_Data` 在 DID Config 里**固定写 `0x01` 占位**（不是车型实际值）

---

## 完整处理流程

```
run_pipeline(domain)
  ① resolve_base_dir + load_runtime（GeneratorConfig）
  ② init_logging（双 log + Tee）
  ③ 按域读 didconfig_input_excel、output_dir、输出文件名
  ④ 缺 Excel 路径 → raise ValueError（TaskService 捕获后可能 skip）
  ⑤ resolve 绝对路径，打开 Workbook
  ⑥ for sheet_name in wb.sheetnames:
       找表头 → 逐行读 name/byte/bit（合并单元格用 merged_cell_value）
       算 DIDLength = max(byte)+1
       拼 Field_* 行块
  ⑦ write UTF-8 到 .../Configuration/DIDConfig.txt
  ⑧ finally：恢复 stdout/stderr，clear log handler
```

---

## 配置键、输入输出

### 配置键

| 键 | 节 | 界面 state 键 | 说明 |
|----|-----|---------------|------|
| `didconfig_input_excel` | `[LR_REAR]` / `[DTC]` | `didconfig_excel` / `d_didconfig_excel` | 单个 Excel 路径（非管道） |
| `output_dir` | 同上 | `out_root` 等 | 输出根；其下找 `Configuration/` |
| `didconfig_output_filename` | `[FixedConfig.ini]` | — | 默认 `DIDConfig.txt` |

### 输入

| 输入 | 说明 |
|------|------|
| DID 配置 Excel | 多 Sheet；Sheet 名 = DID ID |
| `Configuration.ini` + `FixedConfig.ini` | 路径与文件名 |

### 输出

| 输出 | 典型路径 |
|------|----------|
| `DIDConfig.txt` | `{output_dir}/Configuration/DIDConfig.txt` |
| `DIDConfiguration_Matrix.log` | `log/log_*/解析表格日志/` |
| `generate_did_config.log` | `log/log_*/生成文件日志/` |

---

## 谁调用它

| 调用链 | 说明 |
|--------|------|
| 界面「开始运行」 | `GenerationRouteService` → `TaskOrchestrator` → **`did_config` 步** |
| `TaskService.run_did_config(domain)` | 捕获「未配置」类错误 → **success + 跳过提示** |
| 命令行 | `python generators/capl_didconfig/entrypoint.py` |
| `run_validator.py` | 运行前校验是否配置了 `didconfig_input_excel` |

编排顺序（左右后 / DTC）：**did_config → did_info → cin → soa → can → xml**

---

## 客户常问问题（备答）

| 问题 | 建议回答 |
|------|----------|
| DIDConfig.txt 和 DIDInfo.txt 都要生成吗？ | 业务上常两个都要：Config 管**结构**，Info 管**各车型复位数据**；界面填了哪个 Excel 就跑哪个 |
| Sheet 名必须 0x 开头吗？ | 不必须；代码会自动补 `0x` 前缀 |
| 为什么 Field_Data 全是 0x01？ | DID Config 只描述**位域布局**；具体数据值在 Reset-DID 模块 |
| 没配 DID Excel 算失败吗？ | **不算**；编排 skip，提示「未配置 DID_Config 配置表」 |
| 某个 Sheet 表头错了会怎样？ | **跳过该 Sheet** 并 warning；其他 Sheet 照常 |
| 和 Config Enum 什么关系？ | 可能共用同一份 DID Excel；Enum 给 **Set_Config 关键字**翻译用，本模块只写 DIDConfig.txt |

---

## 演示建议

1. 界面「DID_Config 配置表」选 Excel → 看 INI 里 `didconfig_input_excel` 变化  
2. 只勾 DID 相关生成（或全量运行）→ 打开 `Configuration/DIDConfig.txt`  
3. 对照 Excel 某一个 Sheet：字段名、Byte、Bit 与 txt 里 Field_* 是否一致  
4. 打开 `DIDConfiguration_Matrix.log` 看每个 Sheet 解析进度  
5. 故意删掉表头一列，演示该 Sheet 被 skip 的 warning  
6. 与模块 4 对比：同一 DID 在 DIDConfig.txt 只有结构，DIDInfo.txt 才有 `{LDCU}`、`[车型]`、`Field_Data:0x..`  

**预计时长**：约 1h

---

**上一册**：[02-IO-Mapping模块.md](./02-IO-Mapping模块.md) · **下一册**：[04-Reset-DID模块.md](./04-Reset-DID模块.md)
