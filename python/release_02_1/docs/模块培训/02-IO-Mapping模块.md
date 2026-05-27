> 对应验收清单 §2 · 工程根目录：python/release_02_1/

# 模块 2：IO Mapping 解析及中间文件生成

## 本模块要培训的内容（讲师 checklist）

- [ ] IO Mapping 到底干什么：用例步骤里写的 `J_xxx` 怎么变成 CAPL 里的 Path 和具体数值
- [ ] **它不单独生成 .txt/.can 文件**，只在 CAN/CIN 生成时「在内存里翻译一步」
- [ ] 配置写在哪儿：`[LR_REAR]` 或 `[DTC]` 的 `io_inputs`，管道格式 `Excel路径 | Sheet列表` 或 `路径 | *`
- [ ] Excel 表头三列：**Name / Path / Values**（缺列会跳过该 Sheet 并写 log）
- [ ] 加载流程：读配置 → 开 Excel → 建两张表 `name_to_path`、`name_to_values` → 写 `IO_Mapping.log`
- [ ] 翻译入口：`IOMappingContext.transform_args()`；`StepParser` 在翻译关键字步骤时调用
- [ ] 特殊规则：**J_DI*LS**（分号分组、0/1 取反、二值枚举反转）
- [ ] **中央域 CAN/CIN 不用 IO Mapping**（`load_mapping_context` 对 CENTRAL 直接返回 None）
- [ ] `MappingContext.from_config()` 同时加载 IO Mapping 与 Config Enum（模块 3 会交叉提到 enum）
- [ ] 常见失败：表头错、Name 找不到、Values 对不上 → CAN 里出现注释行或整步报错
- [ ] 客户常问：「界面上选了 IO Excel，为什么没多出文件？」

---

## 代码位置总览（本模块「小地图」）

| 层级 | 路径 | 职责（一句话） |
|------|------|----------------|
| **核心实现** | `core/translator/io_mapping.py` | 读 IO Excel、`IOMappingContext.transform_args` 翻译步骤参数 |
| **统一加载** | `core/mapping_context.py` | `MappingContext.from_config()` 一次加载 IO + Config Enum |
| **CAN 侧加载** | `generators/capl_can/runtime_io.py` | `load_mapping_context()`；中央域返回 None |
| **CIN 侧加载** | `generators/capl_cin/runtime_io.py` | CIN 生成前同样加载 MappingContext |
| **步骤解析** | `core/parser/step_parser.py` | 解析关键字步骤时调用 `transform_args` |
| **CAN 翻译** | `generators/capl_can/translator.py` | `CANStepTranslator` 包装 StepParser + IO 错误处理 |
| **配置读取** | `infra/config/`、`GeneratorConfig` | 域内 `io_inputs` 管道格式 |
| **界面保存** | `services/config_manager.py` | `io_excel` / `d_io_excel` → 写入 `io_inputs` |

**产出**：无独立交付文件；`log/.../解析表格日志/IO_Mapping.log` + 嵌入 `.can`/`.cin` 步骤行。

---

## 先用大白话讲清楚：IO Mapping 是「翻译字典」，不是「生成器」

培训时先讲这句话：

> 「IO Mapping 就像一本**对照表**：左边是用例里写的信号名（Name），中间换成台架/仿真要用的路径（Path），右边把『开/关』这类中文或英文枚举翻成数字（Values）。  
> 它**不会**单独吐出一个交付文件；您在一键运行里看到的 DIDConfig.txt、.can 都不是它产的。它只在生成 CAN/CIN 时，**读一遍 Excel 放进内存**，逐步骤替换参数。」

和 DID Config / Reset-DID 的对比（客户容易混）：

| 对比项 | IO Mapping | DID Config / Reset-DID |
|--------|------------|-------------------------|
| 有没有独立产物 | **没有**（只有 log） | 有 `DIDConfig.txt` / `DIDInfo.txt` |
| 配置键 | `io_inputs` | `didconfig_input_excel` / `resetdid_inputs` |
| 何时跑 | 嵌在 CAN/CIN 步骤里 | 编排里独立一步 `did_config` / `did_info` |
| 谁用 | `StepParser` + `transform_args` | 诊断配置工具链 |

**哪些域会用 IO Mapping？**

| 域 | 是否加载 IO Mapping | 原因 |
|----|---------------------|------|
| 左右后 `[LR_REAR]` | ✅ | CAN/CIN 步骤含 `J_*` 信号 |
| DTC `[DTC]` | ✅ | 同上 |
| 中央 `[CENTRAL]` | ❌ | 中央 CAN 编排刻意不加载（无 IO 步骤翻译需求） |

---

## 整体分工（给客户讲：读表 → 字典 → 逐步替换）

```
Configuration.ini 里 io_inputs
    ↓
IOMappingUtility.load_context_from_config()
    ↓ 打开 IO_mapping Excel，扫描 Name/Path/Values
IOMappingContext（内存：name_to_path + name_to_values）
    ↓
CAN/CIN 生成时 MappingContext.from_config() 一并加载
    ↓
StepParser 遇到 J_ 开头参数 → transform_args()
    ↓
CAPL 行里已是 Path + 翻译后的数值
```

**日志落盘**：`log/log_时间戳/解析表格日志/IO_Mapping.log`（解析过程专用，不是交付物）

---

## 逐文件讲解（培训时可按此顺序打开源码）

### 1. `core/translator/io_mapping.py` — 核心：读 Excel + 翻译参数

**干什么**：本模块的**全部业务逻辑**几乎都在这一文件。分两块：**IOMappingUtility**（读表、解析 Values）和 **IOMappingContext**（对步骤参数做替换）。

#### 异常与常量

| 名称 | 口语解释 |
|------|----------|
| `IOMappingParseError` | 翻译失败时抛出；上层可能变成 CAPL 注释行或报错信息 |
| `PROGRESS_LEVEL` | 进度日志级别；「正在处理哪个 Excel/Sheet」始终可见 |
| `LS_INVERT_WARNED_NAMES` | J_DI*LS 枚举超过 2 个值时，同一 Name 只告警一次 |

#### `IOMappingUtility` — 工具方法表

| 方法 | 口语解释 |
|------|----------|
| `setup_logging()` | 初始化 `IO_Mapping.log`（按大小轮转），挂控制台 Handler |
| `emit_log_message()` | 有 logger 写 log，否则 fallback 到 print |
| `normalize_header_text()` | 表头规范化：去空白、去空格、转小写 |
| `find_header_row_and_indices()` | 在前 30 行找 **Name / Path / Values** 三列；缺列返回 missing 列表 |
| `find_colon()` | 在 Values 字符串里找半角/全角冒号 |
| `is_numeric_value()` | 判断是否十进制或 `0x` 十六进制 |
| `normalize_name_key()` | Name/Path 键：strip + casefold |
| `normalize_enum_key()` | 枚举 key：去不可见字符、合并空白、casefold |
| `has_expression_chars()` | 是否含 `><=()` — 有则**不做**枚举翻译，原样透传 |
| `parse_values_cell()` | 把 Values 单元格解析成 `{枚举标签 → 翻译后值}` 字典 |
| `get_io_mapping_inputs_text()` | 从当前域配置节读 `io_inputs`（支持历史别名键） |
| `load_context_from_config()` | **主入口**：读配置 → 开 Excel → 返回 `IOMappingContext`；无配置返回 `None` |

**`load_context_from_config` 内部要点（对着代码讲）**：

1. 按域读 `io_inputs`；空则直接 `return None`（不是报错）
2. 相对路径相对 **config 目录**（`Configuration.ini` 所在文件夹）解析
3. 校验 `.xlsx/.xlsm`、ZIP 文件头，损坏文件给明确中文提示
4. `路径 | *` 表示该 Excel **所有 Sheet**；`路径 | Sheet1,Sheet2` 指定 Sheet
5. 同表内 Name 对应多个 Path：**告警，保留第一次**；Values 枚举冲突同理
6. Name/Path/Values 用**当前行单元格原始值**，不做向下填充（合并单元格不影响「读到的行」逻辑）

#### `IOMappingContext` — 翻译方法表

| 方法 | 口语解释 |
|------|----------|
| `maybe_invert_ls_enum()` | J_DI*LS 且 Values 恰好 2 个枚举时，取「另一个」枚举 key |
| `is_j_di_ls()` | Name 是否 `J_DI` 开头且 `LS` 结尾 |
| `process_inverted_token()` | J_DI*LS 单 token：0↔1、枚举反转后查 Values、表达式透传 |
| `transform_args()` | **对外核心**：`args[0]` 从 Name 换 Path；后续 token 做 Values 翻译 |

**`transform_args` 规则摘要（培训必讲）**：

1. 首参不是 `J_` 开头 → **原样返回**，不翻译
2. Name 必须在 `name_to_path` 或 `name_to_values` 里能找到，且 Path 不能为空
3. 纯数字或带 `><=()` 的表达式 → **不翻枚举**，原样往后传
4. 普通 Name：从最长短语开始匹配 Values（支持多词枚举，如 `Not Active`）
5. **J_DI*LS**：支持 `;` / `；` 分组；组内可能是 `条件 枚举值` 两段式；0/1 数字互换

**Values 单元格格式示例（白板写给客户看）**：

```
1:Closed
0:Open
```

或一行多个：`1:关 0:开` — 解析器按冒号切分，**冒号左边是翻译后的值，右边是用户写的枚举标签**（大小写不敏感）。

---

### 2. `core/mapping_context.py` — 一次性加载 IO + Config Enum

**干什么**：薄薄一层「打包器」。CAN/CIN 生成器不想分别调两次 loader，就调 **`MappingContext.from_config()`**。

| 类/方法 | 口语解释 |
|---------|----------|
| `MappingContext` | dataclass，两个字段：`io_mapping`、`config_enum`（都可能为 None） |
| `MappingContext.from_config()` | 传入已读的 `ConfigParser` + 域 + 路径 → 同时加载 IO Mapping 与 Config Enum |

**为什么要单独一个文件？**  
IO Mapping 和 Config Enum 是两种不同 Excel/配置，但**都在翻译步骤时用**。统一入口避免 CAN、CIN 各写一遍「先 load io 再 load enum」。

---

### 3. 谁调用 IO Mapping（关联文件，培训点到为止）

| 路径 | 调用方式 |
|------|----------|
| `generators/capl_can/runtime_io.py` | `load_mapping_context()` → `MappingContext.from_config()`；**CENTRAL 域返回 (None, None)** |
| `generators/capl_can/service.py` | CAN 主编排里加载 mapping，传给翻译器 |
| `generators/capl_cin/runtime.py` | CIN 侧同样 `MappingContext.from_config()` |
| `core/parser/step_parser.py` | 关键字步骤解析时，对 `J_*` 或能在 IO 表找到的 Name 调 `transform_args()` |

**StepParser 里典型分支（口语）**：

- 关键字只有一个参数且以 `J_` 开头 → 尝试 IO 翻译，失败抛 `IOMappingParseError`
- 多参数步骤 → 整包 `args` 交给 `transform_args`，首元素变 Path，其余变翻译值

---

## 完整处理流程

### 流程 A：加载（每次 CAN/CIN 生成开始时）

```
MappingContext.from_config(config, domain=LR_REAR|DTC)
  → IOMappingUtility.get_io_mapping_inputs_text()
  → 空？→ io_mapping = None，后面步骤不翻译 IO
  → 非空：
       setup_logging → IO_Mapping.log
       对每个「excel | sheets」：
         打开 Workbook
         每个 Sheet：find_header_row_and_indices
         逐行读 Name/Path/Values → 填入 name_to_path / name_to_values
       返回 IOMappingContext
```

### 流程 B：翻译（每个测试步骤）

```
StepParser 解析出一行步骤的参数 args
  → args[0] 是 J_ 开头？
  → io_mapping_ctx 为 None？→ 不翻译（中央域或没配 io_inputs）
  → 调 transform_args(args)
       Name → Path（args[0] 替换）
       后续 token → Values 查表 / J_DI*LS 特殊处理
  → 拼进 CAPL 函数调用字符串
```

### 流程 C：失败时客户看到什么

| 情况 | 现象 |
|------|------|
| Excel 路径错 / 文件损坏 | 加载阶段抛错，CAN 生成失败；看 `IO_Mapping.log` |
| Sheet 缺 Name/Path/Values | 跳过该 Sheet，warning 写 log |
| 步骤里 Name 不在表里 | `IOMappingParseError: Name 未找到` |
| Values 写错枚举文案 | `Values 未匹配` 或 J_DI*LS 专用报错 |

---

## 配置键、输入输出

### 配置键

| 键 | 配置节 | 界面 state 键（参考） | 格式示例 |
|----|--------|----------------------|----------|
| `io_inputs` | `[LR_REAR]` 或 `[DTC]` | `io_excel` / `d_io_excel` | `input/IO_mapping.xlsx \| *` |
| | | | `input/io.xlsx \| Sheet1,Sheet2` |
| `log_level_min` | 同上（控制 log 详细度） | — | 与模块 11 共用 |

> **已不再使用**独立 `[IOMAPPING]` 节；必须写在当前域节内，**禁止**从别的 Tab 偷 `io_inputs`。

### 输入

| 输入 | 说明 |
|------|------|
| IO_mapping Excel | 表头 **Name / Path / Values**；可多文件、多 Sheet（配置多行 `io_inputs`） |
| `Configuration.ini` | 提供路径与 Sheet 列表 |

### 输出

| 输出 | 路径 | 是否交付物 |
|------|------|------------|
| `IO_Mapping.log` | `log/log_*/解析表格日志/` | 排错用 |
| 内存 `IOMappingContext` | 无文件 | 供 CAN/CIN 翻译 |
| 翻译后的 CAPL 行 | 写在 `.can` / `.cin` 里 | **间接**交付 |

---

## 谁调用它

| 调用方 | 何时 |
|--------|------|
| `TaskOrchestrator` | **不**单独编排 IO 步；随 `can` / `cin` 子任务间接执行 |
| `generators/capl_can/*` | LR/DTC 域 CAN 生成前 `load_mapping_context` |
| `generators/capl_cin/*` | CIN 生成前同样加载 |
| `core/parser/step_parser.py` | 逐步骤 `transform_args` |

界面路径保存：`ConfigManager` 把 `io_excel` 写入 `[LR_REAR].io_inputs`（DTC 域写 `[DTC]`，键名 `d_io_excel` → 同节 `io_inputs`）。

---

## 客户常问问题（备答）

| 问题 | 建议回答 |
|------|----------|
| 为什么选了 IO Excel 却没有新文件？ | IO Mapping **只写 log、不产 txt**；结果体现在 .can 步骤行里 |
| 中央域为什么没有 IO 配置项？ | 中央 CAN 设计为**不加载** IO Mapping；左右后/DTC 才需要 |
| Values 里冒号左右哪边是数字？ | **左边**是翻译后写入 CAPL 的值，**右边**是用例里写的枚举文本 |
| 合并单元格 Name 会向下填充吗？ | **不会**；只读当前行三列，空行跳过 |
| 同一个 Name 两行 Path 不一样？ | 保留**第一次**，后面的 warning 写 `IO_Mapping.log` |
| J_DI*LS 是什么？ | 一类特殊 DI 信号：步骤里可能要**逻辑取反**；支持 0/1 互换或二值枚举反转 |
| io_inputs 和用例 Excel 是一回事吗？ | **不是**；用例 Excel 是测试步骤，IO Excel 是信号/枚举对照表 |

---

## 演示建议

1. 打开 IO_mapping 样例 Excel，指给学员看 **Name / Path / Values** 三列  
2. 打开 `Configuration.ini`，找 `[LR_REAR] io_inputs = ... | *`  
3. 找一条用例步骤含 `J_xxx ... Open`，运行 CAN 生成  
4. 打开生成的 `.can`，对比 Path 和枚举值是否已替换  
5. 打开 `log/log_时间戳/解析表格日志/IO_Mapping.log`，看处理了哪些 Sheet  
6. （对比演示）中央 Tab 运行 CAN，说明没有 IO 翻译环节  
7. （可选）故意写错 Values 枚举，看重跑后 StepParser 报错或注释行  

**预计时长**：1～1.5h（含 J_DI*LS 答疑）

---

**上一册**：[01-前端GUI模块.md](./01-前端GUI模块.md) · **下一册**：[03-DID-Config模块.md](./03-DID-Config模块.md)
