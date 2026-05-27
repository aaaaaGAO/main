> 对应验收清单 §8 · 工程根目录：python/release_02_1/

# 模块 8：基于 CAN 生成 XML 文件

## 本模块要培训的内容（讲师 checklist）

- [ ] XML **不读已生成的 .can 文件**，**独立读 Excel**（与 CAN 同源表结构即可）
- [ ] **不做步骤翻译**：没有 StepParser、没有关键字映射表
- [ ] 只生成 **测试模块索引**：`capltestcase` 空标签，供 CANoe 测试管理器加载
- [ ] 中文用例名 → **拼音**（pypinyin）作为 XML `name` 属性
- [ ] 配置：`xml_input_excel`（LR 优先）与 `input_excel` 回退；输出 `Generated_Testcase.xml`（FixedConfig 可改）
- [ ] 过滤链与 CAN **相同**（等级→平台→车型→Target Version→用例类型）
- [ ] 编排：**CAN 之后**执行；与 CAN **共享 workbook_cache**（同一次运行少开一次 Excel）
- [ ] 客户常问：「为什么叫 from CAN 却不读 .can？」「XML 里为什么没有步骤？」

---

## 代码位置总览（本模块「小地图」）

| 层级 | 路径 | 职责（一句话） |
|------|------|----------------|
| **入口** | `generators/capl_xml/entrypoint.py` | `XMLEntrypointWorkflowUtility.run_generation` |
| **主编排** | `generators/capl_xml/service.py` | `XMLGeneratorService.run_pipeline` |
| **配置/日志** | `generators/capl_xml/runtime.py` | 按域解析输入路径、初始化 log |
| **解析/写 XML** | `generators/capl_xml/runtime_io.py` | `XMLGenerationUtility`：读 Excel 元数据、拼音、拼 XML |
| **共用过滤** | `core/case_filter.py` | 与 CAN 相同等级/平台/车型过滤 |
| **表头** | `infra/excel/header.py` | `TestCaseHeaderResolver` |
| **编排** | `services/task_service.py` | `run_xml(domain, workbook_cache)`（CAN 之后） |

**产出**：`{output_dir}/TESTmode/Generated_Testcase.xml`（文件名见 FixedConfig）+ `TestCases.log`

**不做**：不读 `.can`、不用 StepParser、不翻译测试步骤。

---

## 先用大白话讲清楚：XML = 「用例目录」，不是「用例正文」

> 「CAN 模块把 Excel 里的**每一步**翻译成 CAPL 代码，写在 `.can` 里。  
> XML 模块只做**电话簿**：告诉 CANoe 有哪些 testcase、叫什么名字、挂在哪个 Sheet 分组下。  
> 所以它会**再读一遍 Excel**（或同一次运行里复用已打开的 Workbook），**只读用例 ID、名称、筛选列**，**不读测试步骤列的内容去翻译**。」

**和模块 7 对比（培训必投屏）**：

| | CAN（模块 7） | XML（模块 8） |
|--|---------------|---------------|
| 读测试步骤？ | ✅ 翻译为 CAPL | ❌ 不翻译 |
| 读 .can 文件？ | ❌ 读 Excel | ❌ 也读 Excel |
| 输出 | 多个 `.can` + Master | **一个** `.xml` |
| 用例名处理 | testcase 名清洗 | XML `name` 转拼音 |
| 共用 | CaseFilter、表头解析、workbook_cache | 同上 |

**培训话术**：

> 「验收清单里写『基于 CAN 生成 XML』，指的是**与 CAN 同源的用例 Excel、同一套过滤规则**，不是去读磁盘上的 `.can` 文件。」

---

## 谁触发 XML

```
TaskOrchestrator 步 xml（在 can 之后）
  ↓
TaskService.run_xml(domain, workbook_cache=...)
  ↓
XMLEntrypointWorkflowUtility.run_generation(...)
  ↓
XMLGeneratorService.run_pipeline(...)
  ↓
{output_dir}/TESTmode/{xml_output_filename}
```

| 域 | 编排顺序片段 |
|----|--------------|
| LR / DTC | … → can → **xml** |
| CENTRAL | … → can → **xml** |

---

## 逐文件讲解（`generators/capl_xml/`）

### 1. `entrypoint.py` — 薄入口

| 类/方法 | 口语解释 |
|---------|----------|
| `XMLEntrypointWorkflowUtility.run_generation(...)` | TaskService 与命令行统一入口；参数：`config_path`、`base_dir`、`domain`、`workbook_cache` |
| `__main__` | `python -m generators.capl_xml.entrypoint` 可单独调试 |

**注意**：打包 `--noconsole` 时 stdout 可能为 None，入口里做了 devnull 防护。

---

### 2. `service.py` — `XMLGeneratorService.run_pipeline`

**主编排**（培训对着代码走一遍）：

| 阶段 | 做什么 |
|------|--------|
| `load_runtime_config` | 解析输入 Excel 路径、输出路径、过滤条件、域 |
| `init_runtime_logging` | `generate_xml_from_can.log` + stdout Tee |
| `find_excel_files` | 单文件或目录递归找 `.xlsx/.xls` |
| 循环每个 Excel | `parse_testcases_from_excel` → 得到 `{sheet: [testcase dict]}` |
| `group_testcases_by_sheet_and_group` | 按 Sheet 分组（当前实现：一 Sheet 一组，不按功能模块再拆） |
| `generate_xml_content` | 拼 XML 字符串 |
| 写文件 | UTF-8，CRLF 规范化 |

| 方法 | 口语解释 |
|------|----------|
| `build_ungenerated_reason(stats)` | 若 0 条用例，拼人类可读原因（过滤太严、表头错等） |

---

### 3. `runtime.py` — 配置加载与日志

| 职责 | 说明 |
|------|------|
| `XMLRuntimeUtility.load_runtime_config` | 按域读 `xml_input_excel` / `input_excel`、`output_dir`、过滤键 |
| 域差异 | **CENTRAL**：先 `xml_input_excel` 再 `input_excel`；**DTC**：主要 `input_excel`；**LR**：`xml_input_excel` 或回退 |
| `init_runtime_logging` | 挂 GeneratorLogger |
| `XMLRuntimeAPI` | 对 `runtime_io` 的薄封装，供 service 调用 |

**CENTRAL skip 行为**：未配 XML 输入路径时，TaskService 可 **success + 跳过提示**（与 CAN 类似），不是硬失败。

---

### 4. `runtime_io.py` — `XMLGenerationUtility`（核心解析）

#### Excel 发现与表头

| 方法 | 口语解释 |
|------|----------|
| `find_excel_files(input_path)` | 文件或目录；排除 `~$` 临时文件 |
| `is_history_sheet_name` | 跳过 Rev.Hist / 变更历史 Sheet |
| `parse_testcases_from_excel(...)` | 主解析：表头 + 过滤 + 去重 |

**表头**：与 CAN 共用 `TestCaseHeaderResolver`（扫描前 50 行）。

| 列 | 必填？ | 用途 |
|----|--------|------|
| 用例ID | ✅ 必填 | 去重、统计 |
| 用例名称 | 可选 | `capltestcase` 显示名来源 |
| 等级/平台/车型/Target Version/用例类型 | 可选 | `CaseFilter` 过滤 |

**必填列只有「用例ID」**——与 CAN 不同（CAN 还要步骤列）。

#### 过滤与去重

- 使用 `CaseFilter`：与 CAN 相同顺序过滤  
- `selected_sheets`：只处理界面勾选的 `文件|Sheet`  
- **跨 Sheet 去重** `seen_case_ids`：同一 ID 只在第一个 Sheet 保留  

#### 拼音名

| 方法 | 口语解释 |
|------|----------|
| `case_name_to_xml_attr(name)` | 中文 → `lazy_pinyin` 拼接；无 pypinyin 则告警并回退 |
| `_RE_HAS_CHINESE` | 检测是否含汉字 |

#### XML 生成

| 方法 | 口语解释 |
|------|----------|
| `escape_xml(text)` | 转义 `& < > " '` |
| `generate_xml_content(grouped_data, excel_basename)` | 输出完整 XML 文档 |

**XML 层级结构**：

```xml
<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<testmodule title="Test Module" version="1.0">
  <description>Generated from .can test cases</description>
  <testgroup title="{Excel文件名}">
    <testgroup title="{Sheet名}">
      <capltestcase name="{拼音或用例名}"></capltestcase>
    </testgroup>
  </testgroup>
</testmodule>
```

多个 Excel 时：外层再包一层 testgroup，或合并策略见 service 循环逻辑（培训时打开一次生成物对照）。

#### 日志

- `get_testcases_parse_logger` → `TestCases.log`（与 CAN 共用解析表 logger 体系）

---

## 配置键、输入输出

### 配置键

| 键 | 节 | 说明 |
|----|-----|------|
| `xml_input_excel` / `Xml_Input_Excel` | 域节 | LR 主输入 |
| `input_excel` / `Input_Excel` | 域节 | 回退 / CENTRAL / DTC |
| `output_dir` / `Output_Dir_Xml` 等 | 域节 | 输出根 |
| `case_levels` 等 | 域节 | 与 CAN 相同过滤 |
| `selected_sheets` | 域节 | 界面用例树勾选 |
| `xml_output_filename` | FixedConfig | 默认 `Generated_Testcase.xml` |

### 输入 / 输出

| 类型 | 内容 |
|------|------|
| 输入 | 测试用例 Excel（结构同 CAN 用例表，但不要求填步骤也可出 XML） |
| 输出 | `{output_dir}/TESTmode/{xml_output_filename}` |
| 日志 | `generate_xml_from_can.log`、`TestCases.log` |

编码：UTF-8（**无 BOM**），换行 CRLF。

---

## 完整处理流程

```
run_pipeline(domain, workbook_cache)
  ① load_runtime_config → input_path, output_path, filters
  ② init logging
  ③ find_excel_files(input_path)
  ④ for each excel:
       parse_testcases_from_excel (CaseFilter + selected_sheets)
       group_testcases_by_sheet_and_group
  ⑤ generate_xml_content → 单文件写入 TESTmode/
  ⑥ print 目录模式汇总（若输入是文件夹）
```

---

## 客户常问问题（备答）

| 问题 | 建议回答 |
|------|----------|
| 为什么不读 .can？ | 历史命名；实现上**只读 Excel 元数据**，与 CAN 并行、同源 |
| XML 里没有步骤内容？ | 设计如此；步骤在 `.can` 的 testcase 里 |
| 用例名乱码/拼音不对？ | 看是否安装 pypinyin；中文名会转拼音作 `name` 属性 |
| 为什么 CAN 生成了 XML 没有某条？ | 可能 ID 重复被跨 Sheet 去重，或过滤条件更严；看 `TestCases.log` |
| 和 CAN 用同一个 Excel 吗？ | 可以；通常 `input_excel` 指向同一路径 |
| 中央域没配 xml_input_excel？ | 可回退 `input_excel`；都空则 skip |

---

## 演示建议

1. 同一 Excel 同时跑 CAN + XML（全链路一键运行）  
2. 打开 `.can` 里 testcase 名 vs XML 里 `capltestcase name`（拼音）  
3. 改等级筛选，只跑 XML，看条目数变化  
4. 打开 `TestCases.log` 对照表头 warning  
5. 故意重复用例 ID 跨 Sheet，演示去重  

**预计时长**：约 1h

---

**上一册**：[07-CAN文件生成模块.md](./07-CAN文件生成模块.md) · **下一册**：[09-CIN文件生成模块.md](./09-CIN文件生成模块.md)
