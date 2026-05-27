> 对应验收清单 §9 · 工程根目录：python/release_02_1/

# 模块 9：Clib 关键字集合解析及 CIN 文件生成

## 本模块要培训的内容（讲师 checklist）

- [ ] Clib Excel：**Name** 列 + **Step** 列；每个 Name → 一个 `export void g_HIL_Clib_Swc_Clib_*()` 函数
- [ ] 与 CAN **共用** `StepParser`（`mode="cin"`）和**关键字-CAPL 映射表**
- [ ] 输出 **单个** `.cin`（默认 `generated_from_keyword.cin`）
- [ ] **编排在 CAN 之前**（LR/DTC）；Master.can 会 `#include` 该文件
- [ ] CAN 侧 **Clib 白名单**：读同一 Excel 的 Name 列校验 `Clib xxx` 步骤
- [ ] `run_cin` 默认 **false**；界面填了 `cin_excel` 才 true；缺 Clib Excel → **硬失败**
- [ ] CIN **各域**可加载 IO Mapping（含 CENTRAL）；与 CAN 中央域不同
- [ ] 客户常问：「CIN 和 CAN 有什么区别？」「为什么要先跑 CIN？」

---

## 代码位置总览（本模块「小地图」）

| 层级 | 路径 | 职责（一句话） |
|------|------|----------------|
| **入口** | `generators/capl_cin/entrypoint.py` | `CINEntrypointWorkflowUtility.run_generation` |
| **主编排** | `generators/capl_cin/service.py` | `CINGeneratorService.run_pipeline` |
| **配置** | `generators/capl_cin/runtime.py` | `CINEntrypointSupport.load_runtime_config` |
| **读 Clib/翻译/写 cin** | `generators/capl_cin/runtime_io.py` | `read_clib_steps`、`render_step_lines`、`generate_content` |
| **常量** | `generators/capl_cin/constants.py` | 运行时键名、log 过滤模式 |
| **步骤内核** | `core/parser/step_parser.py` | `mode="cin"` + 默认参数加引号 |
| **映射表** | `core/translator/keyword_mapping.py` | 与 CAN 共用关键字 Excel |
| **IO/Enum** | `core/mapping_context.py` | 各域均可加载（含 CENTRAL） |
| **编排** | `services/task_service.py` | `run_cin(domain)`（**CAN 之前**） |

**产出**：`{output_dir}/TESTmode/generated_from_keyword.cin`（默认名）+ `generate_cin_from_excel.log`

---

## 先用大白话讲清楚：CIN = 「关键字函数库」，CAN = 「用例脚本」

> 「**Clib 矩阵 Excel** 里每一行 Name 是一个**可复用的步骤包**（Step 列里多行关键字步骤）。  
> CIN 生成器把这些步骤翻译成 CAPL，打包成 **一个 `.cin` 库文件**，每个 Name 一个 export 函数。  
> **CAN** 生成器写测试用例时，步骤里可以写 `Clib 某Name`，CAN 会检查 Name 是否在 Clib 表里，并且 Master.can 会 `#include` 刚生成的 `.cin`。」

**顺序为什么 CIN 在前？**

```
编排：… → cin → soa → can → …
原因：CAN 的 Master.can 要 #include "generated_from_keyword.cin"
      若 CAN 先跑，include 的文件可能还不存在或是旧的
```

| | CIN（本模块） | CAN（模块 7） |
|--|---------------|---------------|
| 读什么 Excel | Clib 矩阵（Name/Step） | 用例表（步骤/预期） |
| 输出 | **1 个** `.cin` | 多 `.can` + Master |
| StepParser mode | `cin` | `can` |
| IO Mapping（中央） | ✅ 加载 | ❌ 不加载 |
| 默认是否跑 | run_cin=false | run_can=true |

---

## 谁触发 CIN

```
TaskOrchestrator 步 cin（在 can 之前，LR/DTC）
  ↓
TaskService.run_cin(domain)    # 不传 workbook_cache
  ↓
CINEntrypointWorkflowUtility.run_generation(domain)
  ↓
CINGeneratorService.run_pipeline(runtime)
  ↓
{output_dir}/TESTmode/{cin_output_filename}
```

---

## 逐文件讲解（`generators/capl_cin/`）

### 1. `entrypoint.py` — `CINEntrypointWorkflowUtility.run_generation`

| 步骤 | 口语解释 |
|------|----------|
| `reset_runtime_state()` | 清 CIN 模块级 ClassVar 缓存 |
| `resolve_base_dir()` | 工程根（默认 Configuration.ini 位置） |
| `setup_generator_logger` | `generate_cin_from_excel.log` |
| `tee_stdout_stderr` | print 进 log；带 `[cin]` 前缀过滤 |
| `load_runtime_config(base_dir, domain)` | 路径、Sheet、输出文件名 → runtime 字典 |
| `load_mapping_context` | IO + ConfigEnum（**含 CENTRAL**） |
| `CINGeneratorService.run_pipeline(runtime)` | 主逻辑 |
| `finally` | 恢复 stdout、clear logger |

**与 CAN 入口差异**：CIN **不**从 TaskService 接收 `config_path` / `workbook_cache`，始终 `GeneratorConfig(base_dir)` 解析配置。

---

### 2. `runtime.py` — `CINEntrypointSupport`

| 方法 | 口语解释 |
|------|----------|
| `resolve_base_dir()` | 工程根 |
| `load_runtime_config(base_dir, domain)` | 读域内 `cin_input_excel`、`cin_input_sheet`、`output_dir`；FixedConfig 读 mapping 表路径 |
| `detect_sheet_title(excel, sheet)` | 实际使用的 Sheet 名（日志展示） |

---

### 3. `runtime_io.py` — `CINRuntimeIOUtility`

#### 读 Clib Excel

| 方法 | 口语解释 |
|------|----------|
| `read_clib_steps(excel_path, clib_sheet)` | 找表头 **Name**、**Step**（可选 Project）；Step 单元格按 `\n` 拆多行 |
| 返回结构 | `(sheet_title, [(name, [(step_text, excel_row_num), ...]), ...])` |
| Sheet 选择 | 指定 `cin_input_sheet` 或 active sheet |

#### 关键字与翻译

| 方法 | 口语解释 |
|------|----------|
| `load_keyword_specs(...)` | 调 `load_keyword_specs_from_excel`（与 CAN 同表） |
| `render_step_lines(...)` | 对某 Clib 的每条 Step 调 `StepParser.parse_line(mode="cin", ...)` |
| `apply_default_param_parsing` | 非数字参数自动加引号（CIN 模式惯例） |
| 失败 | `format_step_error_lines` → teststep/teststepfail 占位 |
| 成功 | 追加 `//测试步骤 {原文} [idx/total]` |

#### 拼装 .cin

| 方法 | 口语解释 |
|------|----------|
| `generate_content(clib_groups, ...)` | `/*@!Encoding:65001*/` + includes/variables + 各 export 函数 |
| 函数名 | `export void g_HIL_Clib_Swc_Clib_{sanitize_clib_name(Name)}()` |
| `StringUtility.sanitize_clib_name` | 非法字符清洗 |

#### 其它

| 方法 | 口语解释 |
|------|----------|
| `load_mapping_context(cfg, base_dir, config_path, domain)` | `MappingContext.from_config` |
| `setup_generator_logger` | GeneratorLogger + 可选 SubstringFilter |
| `reset_runtime_state` | 清 io_mapping_context 等 ClassVar |

---

### 4. `service.py` — `CINGeneratorService`

| 方法 | 口语解释 |
|------|----------|
| `run_pipeline(runtime) → str | None` | 读 mapping → read_clib_steps → 逐 Name 渲染 → 写文件；无有效记录返回 None |
| `log_error_records()` | 从生成内容里解析 teststep/teststepfail 对，写 ERROR 日志 |

---

### 5. `constants.py`

默认 log 过滤模式、运行时字典键名常量（与 `config_constants` 对齐）。

---

## 配置键

| 键 | 节 / FixedConfig | 说明 |
|----|------------------|------|
| `cin_input_excel` | 域节 | Clib Excel（**必填**） |
| `cin_input_sheet` | 域节 | 目标 Sheet |
| `output_dir` | 域节 | 输出根 |
| `io_inputs` | 域节 | IO Mapping（管道） |
| `cin_mapping_excel` / `unified_mapping_excel` | FixedConfig | 关键字映射表 |
| `cin_mapping_sheet` / `mapping_sheets` | FixedConfig | 映射表 Sheet 列表 |
| `cin_output_filename` | FixedConfig | 默认 `generated_from_keyword.cin` |

界面：`cin_excel` / `d_cin_excel` → 保存为 `cin_input_excel`。

---

## 完整处理流程

```
run_generation(domain)
  ① 日志 + runtime 配置
  ② load_mapping_context（IO + ConfigEnum）
  ③ load_keyword_specs_from_excel
  ④ read_clib_steps → 按 Name 分组
  ⑤ for each Name:
       render_step_lines (StepParser mode=cin)
  ⑥ generate_content → write UTF-8 BOM + CRLF
  ⑦ 输出路径 TESTmode/{cin_output_filename}
```

---

## 与 CAN 的协作（培训必讲）

1. **CIN 先跑** → 写出 `.cin`  
2. **CAN 跑** → `load_clib_context` 读 Clib Excel Name 列 → `clib_validator`  
3. **Master.can** → 若配置了 `cin_input_excel`，添加 `#include "{cin_output_filename}"`  
4. 用例步骤写 `Clib MyName` → 必须在 Clib 表 Name 列存在  

---

## 客户常问问题（备答）

| 问题 | 建议回答 |
|------|----------|
| CIN 和 CAN 各读哪张表？ | CIN 读 **Clib 矩阵**；CAN 读 **用例 Excel** + 映射表 |
| 没勾 CIN 为什么 Master 还 include？ | 只要 INI 里 `cin_input_excel` 非空，Master 就会 include；是否**生成**新 cin 看 run_cin |
| Clib 步骤报错「不在表里」？ | 先确认 CIN 已生成且 Name 与 Excel 一致（大小写清洗规则） |
| 中央域要 IO 吗？ | CIN **会**加载 io_inputs；中央 CAN **不会** |
| 未生成 cin 文件？ | Name/Step 全空或 read 失败；看 `[cin] 未读取到任何有效` 提示 |

---

## 演示建议

1. 准备 Clib Excel（2～3 个 Name，每个 Name 多行 Step）  
2. 只开 run_cin（或全链路 LR）→ 打开 `generated_from_keyword.cin` 看 export 函数  
3. 再跑 CAN → 打开 Master.can 看 `#include`  
4. 用例里写 `Clib xxx`，故意写错名 → 看 teststepfail  
5. 对照 `generate_cin_from_excel.log`  

**预计时长**：约 1.5h

---

**上一册**：[08-XML文件生成模块.md](./08-XML文件生成模块.md) · **下一册**：[10-工程配置保存导入模块.md](./10-工程配置保存导入模块.md)
