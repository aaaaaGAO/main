> 对应验收清单 §7 · 工程根目录：python/release_02_1/

# 模块 7：关键字用例解析及 CAN 文件生成

## 本模块要培训的内容（讲师 checklist）

- [ ] CAN 是**核心模块**：用例 Excel → 关键字翻译 → `.can` + `Master.can`
- [ ] 流水线：**读表**（excel_repo）→ **翻译**（translator + StepParser）→ **渲染**（renderer）→ **聚合**（generated_from_cases_bundle）
- [ ] 关键字映射表：`FixedConfig` 的 `mapping_excel` + `mapping_sheets`
- [ ] `StepParser` **最长匹配**：先 `函数::关键字`，再 `::关键字`；支持 `Step` 前缀
- [ ] 用例表必填列：用例ID、用例名称、测试步骤、预期结果
- [ ] 过滤链：等级 → 平台 → 车型 → Target Version → 用例类型（与 XML 一致）
- [ ] 用例 ID 清洗 / 同 Sheet 去重：`caseid_clean_dup.log`
- [ ] IO Mapping、Config Enum、Clib 白名单在翻译中的分工
- [ ] 输出：`TESTmode/Testcases/generated_from_cases_{excel}_{sheet}.can` + `TESTmode/Master.can`（或 FixedConfig 名）
- [ ] **CIN 必须在 CAN 之前**（Master `#include` Clib `.cin`）
- [ ] 中央域特殊：不加载 IO Mapping；SOA_CONNECT/CLOSE；SecOC `#include`
- [ ] 双日志：主 log + 每 Sheet 子 log + `TestCases.log` / `IO_Mapping.log`

---

## 代码位置总览（本模块「小地图」）

| 层级 | 路径 | 职责（一句话） |
|------|------|----------------|
| **入口** | `generators/capl_can/entrypoint.py` | `CANEntrypointWorkflowUtility.run_generation` |
| **主编排** | `generators/capl_can/service.py` | `CANGeneratorService.run_pipeline` |
| **读 Excel** | `generators/capl_can/excel_repo.py` | `CANExcelRepository.load_cases`、过滤、ID 清洗 |
| **步骤翻译** | `generators/capl_can/translator.py` | `CANStepTranslator` → StepParser |
| **渲染 .can** | `generators/capl_can/renderer.py` | `CANFileRenderer`、SOA 重排、中央 SOA 包壳 |
| **批处理/Master** | `generators/capl_can/generated_from_cases_bundle.py` | 每 Sheet 一个 can + Master 汇总 |
| **运行上下文** | `generators/capl_can/generated_cases_context.py` | 过滤器、keyword specs、translator 构建 |
| **路径/日志** | `generators/capl_can/runtime.py`、`runtime_io.py` | 输入输出路径、mapping、Clib 白名单 |
| **模型** | `generators/capl_can/models.py` | `CANTestCase`、`CANRawStep` 等 |
| **步骤内核** | `core/parser/step_parser.py` | 关键字最长匹配、IO/Enum/Clib |
| **映射表** | `core/translator/keyword_mapping.py` | 读关键字-CAPL 映射 Excel |
| **IO/Enum** | `core/translator/io_mapping.py`、`config_enum.py` | 参数替换（LR/DTC；中央 CAN 跳过 IO） |
| **编排** | `services/task_service.py` | `run_can(domain, workbook_cache)` |

**产出**：`TESTmode/Testcases/generated_from_cases_*.can` + `TESTmode/Master.can` + 多份 log

---

## 先用大白话讲清楚：CAN 模块在整条链路里的位置

```
Excel 里人写的测试步骤（中文/英文关键字）
    ↓ CANExcelRepository 读行、过滤
    ↓ CANStepTranslator → StepParser 查映射表
    ↓ 必要时 IO_mapping / configuration 替参数
    ↓ CANFileRenderer 包成 testcase { ... }
    ↓ 每个 Sheet 一个 .can + 最后 Master.can 统一 #include
```

**和 XML 的区别（开场点一句）**：CAN **翻译步骤**；XML（模块 8）只读元数据建索引，**不**走 StepParser。

**培训话术**：

> 「客户给的用例 Excel，每一行步骤都要查『关键字-CAPL函数映射表』，变成 CAPL 函数调用。  
> 翻译错了不会 silently 跳过——会生成 `teststepfail`，并在 log 里标模块名和 Excel 行号。」

---

## 谁触发 CAN

| 域 | 编排位置 |
|----|----------|
| LR/DTC | … → cin → soa → **can** → xml |
| CENTRAL | uart → soa → **can** → xml |

入口：`CANEntrypointWorkflowUtility.run_generation()` ← `TaskService.run_can(domain)`。

---

## 共用内核：`core/parser` 与 `core/translator`

### `core/parser/step_parser.py` — `StepParser`

**CAN 与 CIN 共用**的步骤解析器。

| 能力 | 说明 |
|------|------|
| `parse_line(line, keyword_specs, mode="can", ...)` | 单行入口；返回 `ParseResult(code_lines, ...)` |
| 特殊指令 | `SetRepeatKeyword`、`AutoIncreaseInVal`、`Clib`、`Keep*WithTime` |
| 关键字匹配 | 从 tokens **尾部向前**尝试最长 `func::keyword`；再试 `::keyword`（最多 4 词） |
| IO 替换 | 普通关键字：首参 `J_*` 或能在 IO 表找到的 Name → `io_mapping_ctx.transform_args` |
| Config 枚举 | 映射表里 func/keyword/capl 含 `set_config` → `config_enum_ctx.translate_args` |
| CIN 兼容 | `mode=cin` 时自动尝试补 `Step` 前缀再匹配 |

**最长匹配示例（口述）**：

> 步骤 `Step TC_xxx SubKey arg1`  
> 会先查 `tc_xxx::subkey`，再查 `tc_xxx`，再查 `::step tc xxx subkey`…  
> **更长的 keyword 优先**，避免「短关键字抢匹配」。

| 异常 | 含义 |
|------|------|
| `KeywordMatchError` | 映射表里没有 |
| `ClibMatchError` | Clib 名不在 Clib Excel |
| `IOMappingParseError` | IO 名找不到或 Values 翻译失败 |
| `ConfigEnumParseError` | Set_Config 的 Name/Values 问题 |
| `StepSyntaxError` | 特殊指令参数不够 |

---

### `core/translator/keyword_mapping.py`

| 符号 | 口语解释 |
|------|----------|
| `KeywordSpec` | 一条映射：func_name、keyword、capl_func、remark |
| `load_keyword_specs_from_excel()` | 读映射表多 Sheet → `dict[full_key.lower()]` |

表头列：函数 / 关键字 / CAPL函数 / 备注（中英文别名均可）。

---

### `core/translator/io_mapping.py`

| 符号 | 口语解释 |
|------|----------|
| `load_io_mapping_from_config()` | 读域内 `io_inputs`（`path \| sheets`）→ 打开 IO_mapping Excel |
| `IOMappingContext` | `name_to_path`、`name_to_values`；`transform_args()` 做 Path 替换 + Values 枚举 |
| `IOMappingParseError` | 翻译失败时抛出 |

**域规则**：LR/DTC 加载；**CENTRAL 在 CAN 入口直接返回 None**（中央不用 IO Mapping 翻译步骤）。

日志：`IO_Mapping.log`（解析表格目录）。

---

### `core/translator/config_enum.py`

| 符号 | 口语解释 |
|------|----------|
| `load_config_enum_from_config()` | 读 `didconfig_input_excel` → configuration.xlsx |
| `ConfigEnumContext.translate_args()` | 专供 **Set_Config** 类关键字：把 value 文本翻成 Values 左侧数值 |

与 IO Mapping 分工：**IO 管 Name→Path + 通用 Values**；**Config Enum 只管 Set_Config 且只翻 value**。

---

## 逐文件讲解（`generators/capl_can/`）

### 1. `entrypoint.py` — `CANEntrypointWorkflowUtility.run_generation`

| 步骤 | 做什么 |
|------|--------|
| `CANRuntimeContextStore.reset()` | 清运行时上下文 |
| `load_generator_config` | 读 INI |
| `setup_generator_logger` | `generate_can_from_excel.log` + stdout Tee |
| `load_mapping_context` | IO + ConfigEnum（中央跳过） |
| `load_clib_context` | 读 Clib Excel Name 列 → 白名单 set |
| `CANGeneratorService.run_pipeline` | 主编排 |

---

### 2. `service.py` — `CANGeneratorService.run_pipeline`

生产路径**真正干活**的方法（`extract/transform/load` 是 BaseTask 骨架/CLI 用）。

| 阶段 | 调用 |
|------|------|
| 构建上下文 | `build_generated_cases_run_context` → translator、renderer、过滤集合 |
| 遍历输入 | `runtime_paths["excel_files"]`（单文件或目录） |
| 每 Excel | `GeneratedCasesBundleUtility.process_excel_for_generated_case_cans` |
| 汇总 | `write_master_can_aggregate_file` → Master.can |

---

### 3. `excel_repo.py` — `CANExcelRepository`

| 方法 | 口语解释 |
|------|----------|
| `load_cases(excel, workbook_cache=...)` | 遍历 Sheet（跳过 Rev.Hist）；尊重 `selected_sheets` 勾选 |
| `load_sheet_cases(ws, ...)` | 定位表头 → 校验必填列 → 逐行走读 |
| 多行用例 | 同一用例 ID 首行带 ID，后续行只追加步骤/预期 |
| `sanitize_case_id` | 非法字符清洗、中文转拼音；写 `caseid_clean_dup.log` |
| 同 Sheet 重复 ID | 自动后缀 `_1`、`_2`… |
| `CaseFilter.is_filtered` | 等级→平台→车型→Target Version→用例类型 |

**必填列**：用例ID、用例名称、测试步骤、预期结果。  
**可选列**缺了：默认 ALL/自动，并在 `TestCases.log` 打 warning。

---

### 4. `translator.py` — `CANStepTranslator`

| 方法 | 口语解释 |
|------|----------|
| `translate(raw_step)` | 调 `StepParser.parse_line(..., mode="can")` |
| 注释后缀 | 每行 CAPL 追加 `// 测试步骤 xxx` 或 `// 预期结果 xxx` |
| `build_error_result` | 失败时：`teststep` + `teststepfail` + 注释原因 |

---

### 5. `renderer.py` — `CANFileRenderer`

| 方法 | 口语解释 |
|------|----------|
| `render_sheet_file(cases)` | 一个 Sheet 所有用例 → 一个 `.can` 文件 |
| `render_testcase(case)` | `testcase Name()` + TestDescription + 步骤行 |
| `apply_soa_prepare_reorder` | SOA CHECK/CHECKREQ 预期行生成 `_Prepare` 副本，插到对应测试步骤前/后 |
| 中央域 | `central_sheet_soa_wrapper_enabled`：首 case 前 `SOA_CONNECT`，末 case 后 `SOA_CLOSE` |

SOA 规则要点：按「节点」（相邻测试步骤之间）处理；wait/sleep 类步骤则 Prepare 插在步骤**下方**。

---

### 6. `generated_from_cases_bundle.py` — 批处理与 Master

| 方法 | 口语解释 |
|------|----------|
| `process_excel_for_generated_case_cans` | 单 Excel：load → translate → render → 写 per-sheet `.can` |
| `per_sheet_can_filename` | `generated_from_cases_{excel}_{sheet}.can` |
| `write_sheet_can_log` | 每 Sheet 一份子 log 到 `log/.../can/` |
| `build_master_can_lines` | TestMoudleControl + 可选 SecOC + 可选 Clib `.cin` + 各 Testcases `#include` |
| `write_master_can_aggregate_file` | 写 Master.can（覆盖写，不删历史其它 can） |

---

### 7. `runtime_io.py` / `runtime.py` — 路径与配置

| 能力 | 说明 |
|------|------|
| `CANEntrypointSupport.build_runtime_paths` | 解析 `input_excel`、`output_dir`、testcases 目录、master 路径、secoc_qualifier |
| `load_keyword_specs` | 包装 `load_keyword_specs_from_excel` |
| `create_clib_validator` | 步骤里 `Clib xxx` 必须在 Clib Excel Name 列存在 |

---

## 配置键（摘要）

| 类别 | 键 |
|------|-----|
| 域节 | `input_excel`、`output_dir`、`case_level` / `case_platform` / `case_model` / `case_type` / `case_target_version`、`selected_sheets`、`cin_input_excel`、`io_inputs`、`uds_ecu_qualifier` |
| FixedConfig | `mapping_excel`、`mapping_sheets`、`output_filename`（Master.can）、`cin_output_filename` |

---

## 完整处理流程（建议画在白板上）

```
run_generation(domain)
  ├─ 加载 mapping_excel → keyword_specs
  ├─ 加载 io_inputs / didconfig（非 CENTRAL）
  ├─ 加载 cin_input_excel → clib_names_set
  └─ run_pipeline
        for each excel in input_excel:
          CANExcelRepository.load_cases
            for each sheet:
              translate_sheet_cases_in_place (StepParser)
              renderer.render_sheet_file → TESTmode/Testcases/*.can
              write_sheet_can_log
        write_master_can_aggregate_file → TESTmode/Master.can
```

---

## 客户常问

| 问题 | 怎么答 |
|------|--------|
| 「关键字明明有为什么匹配失败？」 | 查映射表 **func::keyword** 是否一致、大小写、是否被更长短语抢走；看 log 错误模块 |
| 「IO 替换了 Name 但 Values 没翻？」 | Values 要在 IO 表该 Name 行配置；纯数字/表达式不翻 |
| 「Set_Config 报错？」 | 走 configuration.xlsx，不是 IO_mapping；Name 必须在 DID Config 表 |
| 「Clib 说表里没有？」 | 先跑 CIN 或确认 `cin_input_excel`；CAN 只校验 Name 白名单 |
| 「Master.can 没 include 我的 sheet？」 | 该 Sheet 过滤后 0 条用例不会生成子 can；看 CAN 汇总 log |
| 「中央为什么没有 IO？」 | 设计：中央域 `load_mapping_context` 直接返回 None |
| 「SOA 步骤顺序怪？」 | `_Prepare` 重排是 renderer 规则，不是 Excel 顺序 bug |

---

## 演示建议

1. 准备**小**用例 Excel（1 个 Sheet、3～5 条用例）+ 映射表 +（LR 域）IO_mapping
2. 界面勾选 Sheet → 只跑 CAN（或全链路）
3. 打开 `generated_from_cases_*.can`：对照某行步骤与 CAPL 注释里的 `// 测试步骤`
4. 打开 `Master.can`：看 `#include` 链（Clib、SecOC、Testcases）
5. 打开 `log/.../TestCases.log`、`caseid_clean_dup.log`、某个 sheet 子 log
6. （中央）演示含 SOA_REQ / SOA_CHECK 的用例，指 `_Prepare` 插入位置
7. 故意写错关键字 → 演示 `teststepfail` 与错误模块名

**预计时长**：2.5～3h（建议拆「读表过滤」「StepParser」「渲染 SOA」三段讲）

---

**上一册**：[06-串口UART模块.md](./06-串口UART模块.md) · **下一册**：[08-XML文件生成模块.md](./08-XML文件生成模块.md)
