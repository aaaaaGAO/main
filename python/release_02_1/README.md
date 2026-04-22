# 测试用例生成工具

从 Excel 测试用例与配置表生成 CANoe 所需的 CAPL 脚本（.can）、关键字库（.cin）、XML 测试集、DIDInfo/DIDConfig、Uart.txt 等。支持左右后域、中央域、DTC 域分域配置与一键生成。

---

## 一、根目录需要放什么

### 1. 程序入口（已有）

| 文件/目录 | 说明 |
|-----------|------|
| `app.py` | 主程序入口，启动 Web 界面（保留在根目录） |
| `build_exe.py` | 打包脚本，生成单文件 EXE（保留在根目录） |

### 2. 配置文件目录（必需）

在根目录下建立 **`config`** 文件夹，并在其中放置：

| 文件 | 说明 |
|------|------|
| `config/Configuration.ini` / `config/Configuration.txt` | 主业务配置：输入/输出路径、IO 映射、各域参数、DID/CIN/UART 等 |
| `config/FixedConfig.ini` / `config/FixedConfig.txt` | 固定配置：部分输出文件名、路径等（可选，缺省用代码默认值） |
| `config/filter_options.ini` | 筛选项配置：等级、平台、车型、UDS_ECU 等下拉列表（可选，缺省下拉为空） |

程序会从 **工程根目录下的 config/** 中读取上述配置。主配置/固定配置当前规则为：优先已有 `*.ini`，同时支持已有 `*.txt`。开发时工程根目录 = 含主配置的目录；打包后 = EXE 所在目录。

### 3. 推荐目录（可选）

| 目录 | 说明 |
|------|------|
| `input/` | 存放输入 Excel（用例表、IO 映射、关键字表、DID/UART 矩阵等），在主配置文件中用相对路径引用 |
| `output/` | 生成结果输出目录（也可在配置中指定到其他路径） |
| `log/` | 运行日志根目录，程序按时间戳自动创建子目录 |

---

## 二、如何运行

### 方式一：开发环境（有 Python）

1. 确保根目录下存在 **config/Configuration.ini** 或 **config/Configuration.txt**（优先使用 `.ini`，同时支持历史 `.txt`）。
2. 在项目根目录执行：
   ```bash
   python app.py
   ```
3. 浏览器会自动打开工具界面（默认端口 5001，若被占用则顺延）。若未自动打开，请访问：`http://127.0.0.1:5001`。

### 方式二：打包后运行（无 Python 环境）

1. 在项目根目录执行打包：
   ```bash
   python build_exe.py
   ```
2. 打包完成后，根目录下会生成 **测试用例生成工具_2026.x.x.exe**（具体名称以 app.py 中 TOOL_DISPLAY_NAME 为准）。
3. 将 EXE 拷贝到目标机器后，在 **EXE 同级目录** 下建立 **config** 文件夹，并将 `Configuration.ini`/`Configuration.txt`、`FixedConfig.ini`/`FixedConfig.txt`、`filter_options.ini` 放入其中。
4. 双击 EXE 启动，浏览器会自动打开界面。

---

## 三、基本操作步骤

1. **打开界面**  
   运行 `app.py` 或双击 EXE，等待浏览器打开。

2. **配置路径与筛选项**  
   - 在「左右后域」「中央域」「DTC」Tab 中填写或通过「选择文件/文件夹」选择用例 Excel、输出目录等。  
   - 等级、平台、车型等筛选项若已配置 `config/filter_options.ini`，会出现在下拉框中。  
  - 可勾选要参与的 Sheet，配置会自动保存到当前主配置文件（优先 `config/Configuration.ini`，同时支持 `config/Configuration.txt`）。

3. **开始运行**  
   - 在对应 Tab 点击「开始运行」，执行该域的一键生成（DIDConfig → DIDInfo → CIN → UART → CAN → XML 等，按域组合）。  
   - 运行结束后界面会显示成功/失败及详情；日志落在 **log/log_YYYYMMDD_HHMMSS/** 下。

4. **查看结果**  
   - 生成文件位于配置中指定的输出目录（如 output/ 或各域 output_dir）。  
   - 运行日志在 **log/** 下按时间戳分目录，内含生成文件日志与解析表格日志。

---



