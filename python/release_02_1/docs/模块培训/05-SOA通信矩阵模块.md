> 对应验收清单 §5 · 工程根目录：python/release_02_1/

# 模块 5：SOA 通信矩阵解析及中间文件生成

## 本模块要培训的内容（讲师 checklist）

- [ ] SOA 一次运行会产出**三件套**：Node `.can`、``SOA_StartSetserver.cin``、``SOA_DataTab.cin``
- [ ] 输入是**服务通信矩阵 Excel**（界面字段 `srv_excel`）；**三域**（左右后 / 中央 / DTC）都能配，但各自读**自己域**的配置节
- [ ] 必填：`srv_excel` + `output_dir`；缺任一项**硬失败**，不会静默跳过
- [ ] Excel 两个关键 Sheet：`Service_Deployment`（Node + DataTab 部署关系）、`Service_Interface`（Setserver + DataTab 接口细节）
- [ ] 输出目录**不是**随便写在 `output_dir` 根下，而是按规则拼到固定子路径
- [ ] 编排步名 `soa`，开关 `run_soa`；主界面「填了矩阵路径」会自动为 true
- [ ] **中央域 CAN** 里还有 SOA_CONNECT / SOA_CLOSE 包壳（模块 7 交叉讲）
- [ ] 同一次任务内**复用 workbook 缓存**，矩阵 Excel 只 open 一次
- [ ] 客户常问：为什么 Node 成功了 CIN 还失败？为什么左右后也要配 SOA？

---

## 代码位置总览（本模块「小地图」）

| 层级 | 路径 | 职责（一句话） |
|------|------|----------------|
| **Node 入口** | `generators/capl_soa/entrypoint.py` | `SOAGenerationUtility.run_generation` → Deployment → Jinja2 |
| **Node 模板** | `generators/capl_soa/templates/Node.template` | 每个 Provider 节点 `.can` 骨架 |
| **Setserver CIN** | `generators/capl_soa/soa_setserver_cin.py` | `SOASetServerCinGenerator` ← Service_Interface |
| **DataTab CIN** | `generators/capl_soa/soa_datatab_cin.py` | `SOADataTabCinGenerator` 大表 cin |
| **Excel 工具** | `generators/capl_soa/soa_excel_utils.py` | Workbook 缓存、单元格规范化、Consumer 勾选 |
| **总调度** | `services/task_service.py` | `run_soa(domain)` 三件套串联 + 缓存 |
| **编排** | `services/task_orchestrator.py` | 步名 `soa`；三域均可 |
| **脚本 API** | `web/routes/central.py` | `POST /api/central/soa_setserver_cin` 单独生成 Setserver |
| **脚本服务** | `services/central_programmatic_route_service.py` | setserver 路由业务 |

**产出**：`public/ILNode/SOANode/*.can` + `Public/.../SOA_Onder/SOA_StartSetserver.cin` + `SOA_DataTab.cin`

---

## 先用大白话讲清楚：SOA 在工具里干什么

SOA（服务导向架构）在本工具里，不是跑台架通讯，而是**把 Excel 里的服务矩阵「翻译」成 CAPL 中间文件**，供 CANoe 工程 include：

| 产物 | 给谁用 | 从哪张 Sheet 来 | 落到哪 |
|------|--------|-----------------|--------|
| **每个 ECU 一个 Node `.can`** | ILNode 仿真节点 | `Service_Deployment` | `{用户所选 output_dir 的上一级}/public/ILNode/SOANode/{NodeName}.can`（与是否在工具包内无关） |
| **`SOA_StartSetserver.cin`** | 启动 SetServer 调用体 | `Service_Interface` | `{output_dir 上一级}/Public/TESTmode/Bus/SOA/SOA_Onder/` |
| **`SOA_DataTab.cin`** | SOA 数据表（服务/事件/方法/信号） | `Service_Deployment` + `Service_Interface` | 同上 SOA_Onder 目录 |

**培训话术示例**：

> 「您配好服务矩阵 Excel 后点运行，Python 会先根据部署关系生成每个节点的 `.can`，再在同一份 Excel 里读接口表，写出两个 `.cin`。  
> 这三个文件是**成套**的；CIN 任一步失败，整次 SOA 任务算失败——但 Node 文件可能已经在磁盘上了，排查时别只看弹窗 success。」

---

## 谁触发 SOA：编排与入口

```
主界面 / 脚本 POST generate*
  → TaskOrchestrator 按域顺序调用子步
  → step="soa" → TaskService.run_soa(domain)
       ├─ SOAGenerationUtility.run_generation()      # Node
       ├─ SOASetServerCinGenerator.generate()        # StartSetserver
       └─ SOADataTabCinGenerator.generate()          # DataTab
```

| 域 | 编排顺序里 SOA 的位置 | 说明 |
|----|----------------------|------|
| 左右后 `[LR_REAR]` | did → did_info → **cin → soa** → can → xml | CIN 在 SOA 前，CAN 在 SOA 后 |
| 中央 `[CENTRAL]` | **uart → soa** → can → xml | 无 DID/CIN 步 |
| DTC `[DTC]` | 同左右后 | 含 IO Mapping |

**脚本接口**：`POST /api/central/soa_setserver_cin` 可**单独**生成 StartSetserver（主界面无按钮，但 `api.js` 预留了调用）。

---

## 逐文件讲解（培训时可按此顺序打开源码）

### 1. `services/task_service.py` — `run_soa(domain)` 总调度

**干什么**：把三件套串成**一次任务**，管日志、缓存、失败回滚语义。

| 方法/变量 | 口语解释 |
|-----------|----------|
| `run_soa(domain)` | SOA 子任务入口；默认 domain=`CENTRAL`，编排传入实际域 |
| `workbook_cache` | 同任务内缓存已打开的矩阵 Excel，Node 与两个 CIN 共用 |
| `SOAGenerationUtility.run_generation(...)` | 第一步：生成 Node `.can`，返回已加载的 `GeneratorConfig` |
| `SOASetServerCinGenerator(...).generate(...)` | 第二步：写 StartSetserver；传入 `uds_ecu_qualifier` 做服务过滤 |
| `SOADataTabCinGenerator(...).generate(...)` | 第三步：写 DataTab |
| `finally: workbook_cache.close()` | 任务结束统一关 Excel，防泄漏 |
| `GeneratorLogger` + `SOA_PARSE_LOG_BASENAME` | 解析表日志 + 生成日志分文件 |

**重要行为**：

- Node 成功后，CIN 任一步 `raise` → 整个 `run_soa` 返回 `success=False`，日志写「SOA 扩展生成物未完成（SOA Node 已成功）」
- **不会**因为 Node 已成功就把任务标成 success

---

### 2. `generators/capl_soa/entrypoint.py` — `SOAGenerationUtility`

**干什么**：读配置、解析 `Service_Deployment`、Jinja2 渲染 Node 文件。

| 方法 | 口语解释 |
|------|----------|
| `resolve_base_and_config()` | 找工程根 + 加载 `Configuration.ini` → `GeneratorConfig` |
| `load_paths(gconfig, base_dir, domain)` | 读 `srv_excel`（含候选键兜底，**同节多键**）、`output_dir`；拼 SOANode 输出目录 |
| `read_variables_list_from_excel()` | 扫 Deployment 表：Provider 列 + Consumer 勾选列（`x`/`X`/`×`） |
| `render_nodes_to_files()` | 每个节点名 → 一个 `{NodeName}.can` |
| `run_generation(...)` | 上述步骤串联；**只负责 Node**，不负责 CIN |

**Deployment 表列约定（写死在代码里，培训可对照 Excel）**：

| 列索引（0-based） | 含义 |
|-------------------|------|
| 0 | Provider 节点名 |
| 3–6 | ServiceId / InstanceId / Major / Minor |
| 7 | Port |
| 10 | Protocol（`TCP`→6，否则 17） |
| 12+ | Consumer 矩阵：第 2 行是 Consumer 节点名，数据行 `x` 表示消费关系 |

每个节点会先塞一条占位 `0x0000` 服务，再 append 真实服务；最后写 `ProvidedServiceListNum` / `ConsumedServiceListNum`。

---

### 3. `generators/capl_soa/templates/Node.template` — Node CAPL 骨架

**干什么**：Jinja2 模板，变量来自上一步的 `node_data` 字典。

生成内容要点：

- `#include "../SOALib/SOALib_Node.cin"`
- `SOA_NodeName`、`SOA_NodeProtocol`、`SOA_NodePort`
- 两个 struct 数组：`ProvidedServiceList`、`ConsumedServiceList`

**客户可能问**：「为什么每个节点长差不多？」—— 差异只在节点名、端口、服务列表数组。

---

### 4. `generators/capl_soa/soa_excel_utils.py` — 公共 Excel 工具

| 函数 | 口语解释 |
|------|----------|
| `normalize_cell_text()` | 单元格去空白（复用 `infra.excel.header` 权威实现） |
| `is_client_marker()` | 只认 `x` / `X` / `×` 为勾选；√、1、yes **不算** |
| `open_workbook_cached()` | 带缓存 open；`workbook_cache=None` 时调用方负责 close |

---

### 5. `generators/capl_soa/soa_setserver_cin.py` — StartSetserver CIN

**干什么**：从 `Service_Interface` 抽 Event / Method 调用行，渲染成 `.cin`。

| 类/方法 | 口语解释 |
|---------|----------|
| `SOASetServerCinUtility.collect_setserver_call_lines()` | **Event**：元组 ID **>** `0x8001` 且周期非空 |
| `collect_setserver_method_lines()` | **Method**：元组 ID **<** `0x8000` 且 Type=`RR-Out` |
| `should_skip_service_by_uds_qualifier()` | 按域 `uds_ecu_qualifier`（LDCU/RDCU/CDCU…）过滤服务 |
| `build_service_name_to_server_ecus_map()` | 结合 Deployment 表知道「谁提供这个服务」 |
| `render_cin_document()` | 拼 CAPL 文本 |
| `SOASetServerCinGenerator.generate()` | 对外入口：读表 → 过滤 → 写文件 |

**表头**：前 60 行内扫描，列名支持中英文别名（如 `Element ID` / `元组ID`、`Cycle Time (ms)` / `周期`）。

**输出路径**：`output_dir` 的**上一级** + `Public/TESTmode/Bus/SOA/SOA_Onder/`（**严格模式**，目录不存在则失败，不自动 mkdir）。

**输出文件名**：`FixedConfig.ini` → `soa_setserver_output_filename`（缺省由 `resolve_setserver_filename` 探测）。

---

### 6. `generators/capl_soa/soa_datatab_cin.py` — DataTab CIN

**干什么**：生成 SOA 运行时用的「大表」：节点信息、服务、事件、方法、信号结构。

| 函数/类 | 口语解释 |
|---------|----------|
| `SOA_NODEINFO_CIN_LINES` | **写死**的节点编号表（SOAEngine/RDCU/LDCU/TBOX/Tester） |
| `collect_service_entries()` | 从 Deployment + Client 勾选列收集服务条目 |
| `collect_event_entries()` / `collect_method_entries()` | 从 Interface 表收集 |
| `collect_signal_entries()` | 解析 PayloadParameterGrammar 字段 |
| `render_datatab_document()` | 输出完整 `.cin` 文本 |
| `SOADataTabCinGenerator.generate()` | 对外入口 |

**输出**：同 Setserver，在 `SOA_Onder` 目录；文件名来自 FixedConfig `soa_datatab_output_filename`。

---

## 配置键（讲师对照 INI 讲）

| 键 | 所在 | 说明 |
|----|------|------|
| `srv_excel` | 域节 `[LR_REAR]` / `[CENTRAL]` / `[DTC]` | 服务矩阵 Excel（**必填**） |
| `output_dir` | 同上 | 输出根；SOA 产物用其**上一级**作锚点 |
| `uds_ecu_qualifier` | 域节 | Setserver 过滤用 ECU 限定 |
| `soa_setserver_output_filename` | `FixedConfig.ini` | StartSetserver 文件名 |
| `soa_datatab_output_filename` | `FixedConfig.ini` | DataTab 文件名（**必填**，缺则抛错） |

**主界面映射**：`srv_excel` ↔ 三域各自路径框；中央无前缀、左右后无前缀、DTC 为 `d_srv_excel` 状态键。

**run_soa 怎么变成 true**：`StateConfigService` 里对应域 `srv_excel` 非空 → 一键生成时 `run_soa=True`。

---

## 完整处理流程（对着日志讲）

```
TaskService.run_soa(domain)
  1. 初始化 SOA 专用 Logger + 空 workbook_cache
  2. SOAGenerationUtility.run_generation
       → 校验 srv_excel 文件存在
       → 读 Service_Deployment
       → Jinja2 → public/ILNode/SOANode/*.can
  3. 复用 generator_config（不再 reload INI）
       → SOASetServerCinGenerator.generate(excel, uds_ecu_qualifier=...)
       → SOADataTabCinGenerator.generate(excel)
  4. 关 workbook_cache；log "任务完成"
  5. 返回 TaskResult(success=True/False)
```

---

## 客户常问

| 问题 | 怎么答 |
|------|--------|
| 「左右后为什么要 SOA？」 | 三域编排一致；若项目不用，**不填** `srv_excel` 即可（`run_soa` 为 false） |
| 「Consumer 勾了 √ 为什么没识别？」 | 工具只认 **x / X / ×**，请改矩阵或统一规范 |
| 「Node 有了，弹窗却说 SOA 失败？」 | CIN 步骤失败；看 `log/.../解析表格日志/` 与 `generate_soa_*.log` |
| 「SOA_Onder 目录不存在？」 | **设计如此**：须工程里预先建好目录，工具不自动创建 |
| 「和中央 CAN 的 SOA_CONNECT 什么关系？」 | CAN 用例里 SOA 步骤的运行时包壳；矩阵生成的是**节点/表/Setserver** 中间文件，两者配合使用（模块 7） |

---

## 演示建议

1. 三域任选其一，配置有效 `srv_excel` + `output_dir`（确认 SOANode、SOA_Onder 目录已存在）
2. 只勾 SOA 或一键运行，观察 `TaskOrchestrator` 日志里 `step=soa`
3. 打开 `{锚点}/public/ILNode/SOANode/`，数 `.can` 个数是否等于 Deployment 里节点数
4. 打开 `SOA_Onder` 下两个 `.cin`，对照 `Service_Interface` 里 Event/Method 行数
5. （进阶）故意删掉 Interface Sheet → 演示 CIN 失败但 Node 已落盘的现象

**预计时长**：1.5h（含 Excel 列约定与失败案例）

---

**上一册**：[04-Reset-DID模块.md](./04-Reset-DID模块.md) · **下一册**：[06-串口UART模块.md](./06-串口UART模块.md)
