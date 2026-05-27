> 对应验收清单 §1 · 工程根目录：python/release_02_1/

# 模块 1：前端 GUI 模块

## 本模块要培训的内容（讲师 checklist）

- [ ] 工具怎么启动、浏览器怎么自动打开
- [ ] 三域 Tab 各自干什么、页面上四块区域分别是什么
- [ ] 点「选择文件」为什么会弹出 Windows 文件夹窗口（Tk），选完怎么写进配置
- [ ] 用例树（Sheet 勾选）是怎么来的
- [ ] 筛选项：为什么「一个都不勾」等于「全部都要」
- [ ] 点「开始运行」之后，后台依次做了哪几步（保存 → 生成 → 弹窗）
- [ ] 自动保存、导出预设、导入预设
- [ ] 两套接口的区别：**人点按钮用的** vs **程序/脚本调用的**（见下节）
- [ ] 客户常问：为什么有浏览器又有弹窗？为什么改界面会自动写 INI？

---

## 代码位置总览（本模块「小地图」）

> 培训时**先投屏本表**：让学员知道「改界面 / 点运行会经过哪些文件」。细节见下文「逐文件讲解」。

| 层级 | 路径 | 职责（一句话） |
|------|------|----------------|
| **应用入口** | `app.py` | Flask 启动、端口探测、自动打开浏览器、心跳记录 |
| **Web 工厂** | `web/__init__.py` | `create_app()`，注册 4 个蓝图，设置 `BASE_DIR` |
| **通用 API** | `web/routes/common.py` | 主界面全部 `/api/*`：心跳、配置、选文件、筛选项、三域一键生成 |
| **域 API（脚本用）** | `web/routes/lr_rear.py` | `/api/lr/*`：左右后脚本/集成接口 |
| **域 API（脚本用）** | `web/routes/central.py` | `/api/central/*`：中央脚本接口 + 单独 SOA setserver |
| **域 API（脚本用）** | `web/routes/dtc.py` | `/api/dtc/*`：DTC 脚本接口 |
| **路由辅助** | `web/routes/route_helpers.py` | `get_base_dir`、JSON 响应封装、编排结果格式化 |
| **GUI 服务** | `services/gui_service.py` | Tk 选文件/文件夹、解析 Excel/CAN/XML 结构 |
| **UI 业务** | `services/common_ui_route_service.py` | 除一键生成外的界面操作（加载/保存/预设/串口列表） |
| **一键生成** | `services/generation_route_service.py` | 「开始运行」：存配置 → 算 flags → 调编排器 |
| **状态↔INI** | `services/state_config_service.py` | 界面 JSON 与 INI 互转、生成前保存、run_* 开关推导 |
| **编排（出本模块）** | `services/task_orchestrator.py` | 按域顺序调用 CAN/XML/DID…（GUI 只调到这里） |
| **页面** | `templates/index.html` | 三 Tab 布局、按钮、筛选区、运行按钮 |
| **样式** | `static/css/main.css` | 全局样式、Tab/弹窗外观 |
| **JS·API** | `static/js/api.js` | 封装所有 `fetch('/api/...')` |
| **JS·组件** | `static/js/components.js` | 用例树、解析结果 HTML 渲染 |
| **JS·配置** | `static/js/config_handler.js` | 状态收集、加载、自动保存、预设导入导出 |
| **JS·交互** | `static/js/ui_controls.js` | 选路径、运行按钮、中央域配置弹窗 |
| **JS·启动** | `static/js/app.js` | Tab 切换、心跳 Worker、页面初始化 |

**本模块不负责**：具体生成 `.can`/`.xml`/`.txt`（在 `generators/capl_*`，见模块 7～12）。

---

## 先用大白话讲清楚：界面有两套「后门」

日常培训时，**先把下面这张表讲明白**，客户就不容易懵：

| 说法 | 实际是什么 | 谁在用 | 举例 |
|------|-----------|--------|------|
| **主界面接口** | 地址以 `/api/...` 开头 | 浏览器里您点的每一个按钮 | 选文件、保存配置、一键运行 |
| **脚本/自动化接口** | 地址以 `/api/lr`、`/api/central`、`/api/dtc` 开头 | 测试脚本、别的系统、高级用户用 Postman 调 | 只跑 CAN、只写 LR 配置、单独生成 SOA 某个 cin |

**「脚本/集成用细粒度接口」是什么意思？**

- **脚本**：不用打开网页，用 Python/curl 发 HTTP 请求也能触发生成。
- **集成**：别的工具（如 CI、台架软件）可以对接这些地址，嵌入到自己的流程里。
- **细粒度**：主界面是「一键全跑」；这些接口可以**只跑其中一步**，例如「只生成 CAN、不要 XML」，或在 JSON 里写 `"run_uart": true` 单独开 UART。

**培训话术示例**：

> 「您平时双击 EXE、在网页里操作，走的是 `/api/generate` 这一套，会把界面上填的东西先存进配置文件，再按规则决定跑哪些生成步骤。  
> `/api/lr/generate/can` 这类地址是给写程序的人用的，网页主按钮**不会**去调它；配置也要事先写好，不会帮您从页面收数据。」

---

## 整体分工（给客户讲：浏览器管看，Python 管干）

```
您看到的网页（HTML + JS）
    ↕ 发请求（像打电话）
Flask 路由（只负责接电话、转接，不写生成逻辑）
    ↕
Service 服务层（真正办事：存配置、弹窗、安排生成任务）
    ↕
TaskOrchestrator（按顺序调用 CAN、XML、DID… 各生成器）
```

**重要**：网页里的 JavaScript **不会**读 Excel、**不会**写 .can 文件；它只把路径和选项打包成 JSON 发给 Python。

---

## 逐文件讲解（培训时可按此顺序打开源码）

### 1. `app.py` — 程序入口，相当于「总开关」

**干什么**：启动整个工具。您双击 EXE 或运行 `python app.py`，最终都是进这里。

| 函数/变量 | 口语解释 |
|-----------|----------|
| `TOOL_DISPLAY_NAME` | 窗口标题和 EXE 文件名（改一处两处一起变） |
| `get_app_path()` | 找「工程根目录」——配置文件夹 `config/` 在哪 |
| `get_resource_path()` | 找网页模板、CSS、JS；打包成 EXE 后从内置资源读 |
| `find_available_port()` | 从 5001 起找没被占用的端口，避免启动失败 |
| `make_app()` | 创建 Flask，挂上所有 API、首页 |
| `index()` | 有人访问 `/` 时，返回 `index.html` 页面 |
| `track_heartbeat()` | 前端每几秒 ping 一次；这里记录「后端还活着」 |
| `start_app()` | 开线程、找端口、**自动打开浏览器**、跑 Web 服务 |

**启动顺序（可对着代码讲）**：

1. `start_app()` 打印应用根目录  
2. 后台开一个「心跳监控」线程（默认**不会**因无心跳退出，`AUTO_EXIT_ON_NO_HEARTBEAT = False`）  
3. `find_available_port(5001)` → 例如 `http://127.0.0.1:5001`  
4. 另开线程 1.5 秒后 `webbrowser.open(url)` 打开浏览器  
5. `app.run(...)` 在本机监听，只接受本机访问  

**客户可能问**：「为什么有时端口不是 5001？」——因为 5001 被占用就会试 5002、5003…

---

### 2. `web/__init__.py` — 把四类 API「挂号」到 Flask

**干什么**：像医院分诊台，把不同业务的接口注册到不同 URL 前缀下。

| 函数 | 口语解释 |
|------|----------|
| `project_root()` | 再次确认工程根目录（含 `config/Configuration.ini` 的目录） |
| `create_app()` | 创建 Flask，设置 `BASE_DIR`，注册下面 4 个蓝图 |

**四个蓝图（培训必讲）**：

| 蓝图变量 | URL 前缀 | 给谁用 |
|----------|----------|--------|
| `common_bp` | `/api` | **网页主界面**（选文件、保存、一键运行） |
| `lr_rear_bp` | `/api/lr` | 脚本：左右后域 |
| `central_bp` | `/api/central` | 脚本：中央域 |
| `dtc_bp` | `/api/dtc` | 脚本：DTC 域 |

---

### 3. `web/routes/common.py` — 主界面用的所有 API（最重要）

**干什么**：网页里点的按钮，几乎都在这里「挂号」。**本文件本身不写业务**，每个接口只转给对应的 Service。

设计原则（可告诉客户）：路由文件要**薄**——只解析 HTTP 请求，复杂逻辑在 `services/` 里。

| 路由 | 方法 | 您界面上对应什么 | 转给谁 |
|------|------|------------------|--------|
| `/api/heartbeat` | POST | 后台悄悄 ping（用户无感） | 直接返回 alive |
| `/api/get_filter_options` | GET | 页面加载时等级/平台/车型下拉 | `CommonUiRouteService.filter_options_result` |
| `/api/load_config` | GET | 打开工具时恢复上次配置 | `load_config_result` → `ConfigManager.load_ui_data` |
| `/api/select_file` | POST | 点「选择文件/浏览」 | `select_file_result` → **Tk 弹窗** |
| `/api/parse_file_structure` | POST | 选完 Excel 后解析 Sheet 列表 | `parse_file_structure_result` |
| `/api/get_serial_ports` | GET | 中央域串口配置弹窗里的 COM 口列表 | `serial_ports_result` |
| `/api/auto_save_config` | POST | 改任意一项后自动保存 | `StateConfigService.persist_state_config` |
| `/api/generate` | POST | 左右后 Tab「开始运行」 | `GenerationRouteService` → 编排 |
| `/api/generate_central` | POST | 中央 Tab「开始运行」 | 同上 |
| `/api/generate_dtc` | POST | DTC Tab「开始运行」 | 同上 |
| `/api/save_preset` | POST | 右上角「保存预设」 | Tk 另存为 + 写 INI |
| `/api/import_preset` | POST | 右上角「导入预设」 | Tk 打开 INI + 读回界面 |

**一键生成公共函数** `execute_generation_route()`：三个 generate 路由共用，避免复制粘贴三份代码。

---

### 4. `web/routes/lr_rear.py` — 给程序用的「左右后专用接口」

**干什么**：网页**不用**这些地址；给自动化测试或二次开发。

| 路由 | 口语解释 |
|------|----------|
| `POST /api/lr/generate/can` | 触发左右后域生成；名字带 can 是历史原因，**默认仍会跑 XML**（除非调用方改参数） |
| `POST /api/lr/config` | 只把 JSON 里 LR 相关字段写入 `[LR_REAR]` 节，**不**走完整界面 state 合并 |

实现：`ProgrammaticDomainRouteService.run_lr_generate_can_bundle` / `save_lr_rear_section_tuple`

---

### 5. `web/routes/central.py` — 给程序用的「中央专用接口」

| 路由 | 口语解释 |
|------|----------|
| `POST /api/central/generate` | 中央域生成；要在 JSON 里**自己写** `run_can`、`run_uart`、`run_soa` 等 true/false |
| `POST /api/central/soa_setserver_cin` | **仅**生成 `SOA_StartSetserver.cin`；主界面没有单独按钮，但 `api.js` 里预留了调用 |

与 `/api/generate_central` 的区别：

- 主界面：先把**整个页面**的状态存进 INI，再**根据填了哪些 Excel 路径自动判断**跑哪些步骤  
- 本文件：假定 INI 已经配好，调用方**手动指定**跑哪几步  

---

### 6. `web/routes/dtc.py` — 给程序用的「DTC 专用接口」

| 路由 | 口语解释 |
|------|----------|
| `POST /api/dtc/generate` | DTC 域生成；同样要在 JSON 里显式传 `run_cin`、`run_did`、`run_soa` 等 |

与 `/api/generate_dtc` 的区别同上：主界面会帮推导开关，脚本接口不会。

---

### 7. `web/routes/route_helpers.py` — 路由小工具

| 函数 | 口语解释 |
|------|----------|
| `get_base_dir()` | 当前工程根目录从哪来（Flask 配置里的 `BASE_DIR`） |
| `jsonify_route_result` | 装饰器：Service 返回 `(字典, 状态码)`，这里统一转成 Flask 的 JSON 响应 |
| `jsonify_orchestrator_result()` | 把「生成任务结果」格式化成前端熟悉的 `{success, message, detail}` |

---

### 8. `services/gui_service.py` — 弹窗和「看文件里有什么」

**干什么**：浏览器**不能**直接打开 Windows 文件选择框，所以由 Python 用 **Tkinter** 弹系统对话框。

| 方法 | 口语解释 |
|------|----------|
| `select_path(file_type)` | 选单个 Excel 或选文件夹；`tk_lock` 保证同时只弹一个窗，防崩溃 |
| `ask_saveas_filename()` | 「另存为」——保存预设时用 |
| `ask_open_config_filename()` | 「打开」——导入预设时用 |
| `parse_excel_sheets()` | 读 Excel 有哪些 Sheet 名 |
| `parse_can_testcases()` | 读 .can 里有哪些 `testcase xxx(` |
| `parse_xml_structure()` | 读 XML 里 testgroup / capltestcase |
| `parse_file_structure()` | 对外总入口：传文件或文件夹，返回结构列表给前端画树 |

**客户可能问**：「为什么选文件会闪一下小窗口？」——那是 Tk 临时窗口，选完就关。

---

### 9. `services/common_ui_route_service.py` — 主界面「除一键生成外」的业务

**类**：`CommonUiRouteService(base_dir)`

每个 `*_result()` 方法对应 `common.py` 里一个路由：

| 方法 | 做什么 |
|------|--------|
| `filter_options_result` | 读 `filter_options.ini` 给下拉框 |
| `load_config_result` | 读主配置，转成前端 JSON |
| `serial_ports_result` | 枚举 COM 口（先 pyserial，不行再 PowerShell） |
| `select_file_result` | 调 GuiService 弹窗 |
| `parse_file_structure_result` | 解析 Excel/目录结构 |
| `auto_save_config_result` | 把前端 `data` 写进 Configuration.ini |
| `save_preset_result` | 另存为一份 INI |
| `import_preset_result` | 从选的 INI 读回 `load_ui_data` |

**设计点**：这里**不 import Flask**，方便单独测试；异常用 `@guard_service_route_tuple` 统一捕获。

---

### 10. `services/generation_route_service.py` — 「开始运行」真正干活的地方

**类**：`GenerationRouteService`

**核心方法** `execute_from_payload()` — 一键生成 5 步（培训必背）：

1. **合并**前端 JSON → `state` 对象  
2. **`prepare_generation_config`**：把 state **写进** Configuration.ini（生成前一定先存盘）  
3. **`get_lr_generation_flags` / `get_central_*` / `get_dtc_*`**：根据填了哪些路径，决定 `run_can`、`run_did`、`run_uart`… 是 true 还是 false  
4. **`run_lr_bundle` / `run_central_bundle` / `run_dtc_bundle`**：按顺序调用各生成器  
5. 成功/失败拼成 message，返回给前端 `alert`  

**三个工厂函数**（告诉客户：三个 Tab 各绑一个）：

- `generation_route_options_lr_rear()` → `/api/generate`  
- `generation_route_options_central()` → `/api/generate_central`（保存时**不覆盖** LR 节）  
- `generation_route_options_dtc()` → `/api/generate_dtc`  

---

### 11. `services/state_config_service.py` — 界面和 INI 的「翻译官」

（本模块培训点到为止，细节在模块 10 展开）

- `persist_state_config`：界面改一项 → 合并进 INI  
- `prepare_generation_config`：点运行前再存一次，并只更新当前域  
- `get_*_generation_flags`：看界面上有没有填 DID Excel、SOA Excel… 决定跑哪些子任务  

---

### 12. 前端文件（浏览器里跑的代码）

**加载顺序**（`index.html` 里 script 标签顺序不能乱）：

```
api.js → components.js → config_handler.js → ui_controls.js → app.js
```

#### `static/js/api.js` — 「打电话清单」

把所有 `fetch('/api/...')` 封装成 `API.xxx()`，别处只调 `API`，不写 URL 字符串。

| 方法 | 打哪个电话 |
|------|-----------|
| `selectFile` | POST `/api/select_file` |
| `loadConfig` | GET `/api/load_config` |
| `autoSaveConfig` | POST `/api/auto_save_config` |
| `generate` / `generateCentral` / `generateDTC` | 三个域的一键运行 |
| `heartbeat` | POST `/api/heartbeat`；失败则 `handleBackendDown()` 提示重开 EXE |

#### `static/js/config_handler.js` — 「记事本 + 自动同步」

| 变量/函数 | 口语解释 |
|-----------|----------|
| `selection` | 内存里存各路径（can_input、io_excel…） |
| `configLoaded` | 页面还没加载完时不自动保存，防止空数据覆盖 INI |
| `collectCurrentState()` | 把 DOM 上所有输入收成一个大 JSON（三 Tab 全包） |
| `autoSaveConfig()` | 调 `API.autoSaveConfig` 写后端 |
| `initFromConfig()` | 页面.onload：拉筛选项 → loadConfig → 回填界面 → 解析用例树 |
| `getChecks(id)` | 读勾选框；**一个都不勾** → 发 `'ALL'`（表示不过滤） |
| `getSelectedSheets()` | 用例树里勾选的 `文件\|Sheet` 列表 |

#### `static/js/ui_controls.js` — 「按钮点了干什么」

| 函数 | 口语解释 |
|------|----------|
| `selectPath(key, type, dispId)` | 选文件 → 更新显示 → 自动保存 → 若是用例 Excel 则 `autoParseAndRender` 画树 |
| `clearPath` | 清除路径并重置用例树 |
| `run()` / `runCentral()` / `runDTC()` | 校验输出目录 → `collectCurrentState` → 调对应 `API.generate*` → alert 结果 |
| 各种 `show*Config` | 中央域串口/电源/继电器等弹窗（保存回内存 + autoSaveConfig） |

#### `static/js/components.js` — 「画 HTML」

把后端返回的 Sheet/testcase 列表画成带 checkbox 的树形区域（`renderCaseSelectCheckboxes` 等）。

#### `static/js/app.js` — 「开机 + 心跳」

| 内容 | 口语解释 |
|------|----------|
| `showTab` | 切换左右后/中央/DTC 三个 Tab |
| Web Worker 每 5 秒 | 发心跳，检测后端是否还活着 |
| `window.onload` | 调用 `initFromConfig()` 恢复配置 |
| `handleBackendDown` | 后端挂了：alert 提示重新双击 EXE |

#### `templates/index.html` — 页面长什么样

三个 `#tab-lr-rear` / `#tab-central` / `#tab-dtc`，结构相同：Excel 区 → 配置表区 → 筛选用例区 → 输出目录 + 运行按钮。  
中央 Tab 多一串「配置」按钮（UART、电源…）。右上角保存/导入预设。

#### `static/css/main.css` — 样式

颜色、Tab 高亮、弹窗布局等，不影响业务逻辑。

---

## 三条主线流程（培训演示用）

### 流程 A：打开工具

```
双击 EXE → app.start_app → 浏览器打开 /
  → app.js onload → initFromConfig()
  → GET /api/get_filter_options（下拉选项）
  → GET /api/load_config（读 INI 填回界面）
  → 若之前存过 Excel 路径 → parseFileStructure 画用例树
  → 心跳开始每 5 秒 POST /api/heartbeat
```

### 流程 B：选一个 Excel

```
点「选择文件」→ ui_controls.selectPath
  → POST /api/select_file → GuiService Tk 弹窗
  → 返回 path → 界面显示 √ 文件名
  → autoSaveConfig → POST /api/auto_save_config → 写 Configuration.ini
  → POST /api/parse_file_structure → 返回 sheets 列表
  → components.js 渲染 Sheet 勾选树
```

### 流程 C：点「开始运行」（左右后为例）

```
run() → 检查 out_root 是否填写
  → collectCurrentState() 打包 JSON
  → POST /api/generate
  → GenerationRouteService：
       ① 合并 state
       ② prepare_generation_config 写 INI
       ③ get_lr_generation_flags（有 DID 路径就跑 DID…）
       ④ TaskOrchestrator.run_lr_bundle
       ⑤ 各 generators 写 .can / .xml / .txt…
  → 返回 success → alert「一键生成完成」
  → log/log_时间戳/ 下产生日志
```

---

## 客户常问问题（备答）

| 问题 | 建议回答 |
|------|----------|
| 为什么用浏览器而不是传统桌面窗体？ | 界面用 HTML 好改、好打包；文件选择仍用 Windows 原生对话框（Tk） |
| 改路径为什么要自动保存？ | 防止只改界面没点运行就关浏览器，下次打开配置丢失 |
| `/api/lr` 和 `/api/generate` 有什么区别？ | 前者给脚本精细控制；后者是网页一键跑，会收全页面状态 |
| 心跳干什么用？ | 检测 Python 后台是否还在；关了 EXE 会提示页面失效 |
| 生成逻辑在哪？ | **不在** static/js；在 `generators/` 和 `services/task_orchestrator.py` |

---

## 演示建议

1. 启动应用 → 指给学员看控制台 URL 和自动打开的浏览器  
2. 选一个 Excel → 同时打开 `Configuration.ini` 看键值变化  
3. 勾/不勾等级筛选 → 说明 `ALL` 的含义  
4. 点运行 → 指 `log/log_时间戳/` 目录  
5. （可选）用 Postman 调一次 `/api/lr/config` 对比主界面保存差异  

**预计时长（课堂）**：2～2.5h（含逐文件过一遍 + 演示）

---

**上一册**：[00-整体架构导读.md](./00-整体架构导读.md) · **下一册**：[02-IO-Mapping模块.md](./02-IO-Mapping模块.md)
