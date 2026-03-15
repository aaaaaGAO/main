4.1.1.1 关键字用例解析及CAN文件生成模块描述
本模块负责把Excel 测试用例表自动转换为测试环境所需的用例脚本文件（包括单用例脚本和总控脚本）。  它综合使用配置文件、IO-Mapping、枚举表和关键字映射表，将用例 Excel翻译成结构化的用例脚本文本，并在日志中记录生成过程与失败原因。  
4.1.1.1.1 软件架构

4.1.1.1.2 模块功能说明
1. 从 `Configuration.txt` / `FixedConfig.txt` 读取关键字用例生成相关配置（输入 Excel、输出目录等）；  
2. 初始化本次运行的日志目录和主日志文件；  
3. 加载 IO Mapping 与 Config Enum，使后续可以把信号名、枚举值翻译成真正的底层信号路径和数值；  
4. 从指定的 Excel（或目录）中读取测试用例和步骤，并按等级、平台、车型、目标版本等条件过滤；  
5. 结合关键字映射表，对每一行步骤做关键字匹配、参数翻译与合法性校验，将其翻译为用例脚本中的执行指令行；  
6. 针对每个 Excel/Sheet 生成对应的用例脚本文件；  
7. 汇总所有脚本文件，生成一个总控脚本，集中管理和调度本次生成的所有用例；  
8. 输出详细日志与统计信息，记录用例筛选、跳过原因、翻译错误等，便于定位哪些用例未生成及原因。
4.1.1.1.3 接口说明
1、`void CaseScript_Generate_From_Excel(char ar_P_ConfigPath[], char ar_P_BaseDir[], char ar_P_Domain[])`  
返回值类型：无；  
形参：ar_P_ConfigPath（char[]，配置文件路径，可为空）、ar_P_BaseDir（char[]，工程根目录，可为空）、ar_P_Domain（char[]，业务域，如 "LR_REAR"）；  
功能：作为用例脚本生成的统一入口，读取配置、准备环境，并串联执行完整的用例脚本生成流程（对应 `generate_can_from_excel.main()`）。  

2、`void CaseScript_Execute_Workflow(char ar_P_ConfigPath[], char ar_P_BaseDir[], char ar_P_Domain[])`  
返回值类型：无；  
形参：ar_P_ConfigPath（char[]）、ar_P_BaseDir（char[]）、ar_P_Domain（char[]）；  
功能：完成用例脚本生成的内部工作流（重置状态、读配置、初始化日志、加载映射、启动服务），对应 `generate_can_from_excel.execute_workflow()`。  

3、`void CaseScript_Service_Run(char ar_P_BaseDir[])`  
返回值类型：无；  
形参：ar_P_BaseDir（char[]，工程根目录）；  
功能：创建用例生成服务并按默认配置执行一轮生成任务，对应 `generators/capl_can/service.py` 中的 `main()`。  

4.1.1.2 Clib关键字集合解析及CIN文件生成模块描述
CIN 模块负责根据关键字集合 Excel，生成 关键字库脚本文件（.cin），用于集中存放关键字实现。  
4.1.1.2.1 软件架构
4.1.1.2.2 模块功能说明
1. 从 `Configuration.txt` / `FixedConfig.txt` 读取本模块相关配置（Clib/关键字 Excel 输入、CIN 输出文件名等）；  
2. 解析 Clib 矩阵或关键字集合 Excel 中的关键字名称、参数列表、说明等信息；  
3. 加载 IO Mapping 与 Config Enum，并结合关键字映射规则，将关键字定义中涉及的信号名、枚举值等翻译成具体路径和数值，生成对应的脚本实现内容；  
4. 将所有关键字实现按约定格式组织成一个 `.cin` 关键字库脚本文件，并写出到配置指定的位置；  
5. 在日志中记录关键字数量、生成文件路径以及解析/生成过程中的错误信息，便于排查配置或关键字表问题。  
4.1.1.2.3 接口说明
1、`void CIN_Generate(char ar_P_ConfigPath[], char ar_P_BaseDir[])`  
返回值类型：无；  
形参：ar_P_ConfigPath（char[]）、ar_P_BaseDir（char[]）；  
功能：根据配置生成 CIN 文件，对应 `generate_cin_from_excel.main()`。  

2、`void CIN_From_Excel(char ar_P_ExcelPath[], char ar_P_OutputPath[])`  
返回值类型：无；  
形参：ar_P_ExcelPath（char[]，Clib / 关键字 Excel 路径）、ar_P_OutputPath（char[]，输出 CIN 文件路径）；  
功能：直接从指定 Excel 解析关键字集合并生成 CIN 文件，由 `generators/capl_cin` 中服务实现。  

4.1.1.3 基于CAN生成XML文件模块描述  
本模块负责根据测试用例 Excel，生成 XML 格式的测试模块文件（.xml），供测试管理或执行平台等上层系统导入和使用。模块会对用例进行分组、整理和清洗，保证输出 XML 结构清晰、字段完整。  

4.1.1.3.1 软件架构  

4.1.1.3.2 模块功能说明  
1. 从 `Configuration.txt` / `FixedConfig.txt` 读取本模块相关配置（输入 Excel 路径、XML 输出目录、过滤条件等）；  
2. 打开测试用例 Excel，解析用例 ID、名称、等级、功能模块等基本信息以及与分组相关的字段；  
3. 根据配置中的过滤条件（等级、平台、车型等）对用例进行筛选，只保留需要导出的用例；  
4. 按约定的分组规则（按用例id、功能模块）将用例划分为多个测试模块；  
5. 为每个测试模块构建对应的 XML 结构，填充用例的基本信息和必要的附加属性；  
6. 将生成的 XML 文件写入配置指定的输出目录，并保证文件命名、层级符合约定；  
7. 在日志中记录每个 Excel/模块生成的 XML 文件数量、输出路径以及解析/生成过程中的错误信息，方便后续排查。  

4.1.1.3.3 接口说明  
1、`void XML_Generate(char ar_P_ConfigPath[], char ar_P_BaseDir[])`  
返回值类型：无；  
形参：ar_P_ConfigPath（char[]，配置文件路径，可为空）、ar_P_BaseDir（char[]，工程根目录，可为空）；  
功能：作为 XML 生成的统一入口，读取配置、准备环境，并串联执行完整的 XML 生成流程（对应 `generate_xml_from_can.main()`）。  

2、`void XML_From_Excel(char ar_P_ExcelPath[], char ar_P_OutputDir[])`  
返回值类型：无；  
形参：ar_P_ExcelPath（char[]，测试用例 Excel 路径）、ar_P_OutputDir（char[]，XML 输出目录）；  
功能：直接从指定 Excel 解析测试用例并生成 XML 文件，由 `generators/capl_xml` 中服务实现。  

4.1.1.4 reset-did解析及中间文件生成模块描述  
本模块负责根据项目配置的 DID 信息 Excel（含 ResetDid_Value 配置表），生成 DIDInfo.txt 文件，用于描述诊断 DID 的详细信息（长度、字节布局、适用车型等），为诊断配置和测试提供统一的数据来源。  

4.1.1.4.1 软件架构  

4.1.1.4.2 模块功能说明  
1. 从 `Configuration.txt` / `FixedConfig.txt` 读取本模块相关配置（DID 信息 Excel、ResetDid_Value 配置表路径、DIDInfo 输出文件名及目录等）；  
2. 打开 DID 信息 Excel 以及 ResetDid_Value 配置表，解析每条 DID 的静态信息：DID 编号、名称、总长度、各 Byte/Bit 的含义、适用车型/变体等；  
3. 按车型、Sheet 或配置中的分组规则，将 DID 信息进行归类，将同一 DID 在不同车型下的差异合并或并列展示；  
4. 基于解析结果为每个 DID 生成一条或多条“说明性记录”（如：DID 基本属性、字节布局、重置相关说明等），累积形成 DIDInfo 输出内容；  
5. 将组装好的 DIDInfo 文本写入配置指定的输出文件（如 DIDInfo.txt），并确保编码、换行符等格式符合约定，便于人工查看或后续工具消费；  
6. 在日志中记录解析到的 DID 数量、涉及的 Excel/Sheet、DIDInfo 输出路径以及解析/生成过程中的错误信息，便于排查 Excel 或配置问题。  

4.1.1.4.3 接口说明  
1、`void DIDInfo_Generate(char ar_P_ConfigPath[], char ar_P_BaseDir[])`  
返回值类型：无；  
形参：ar_P_ConfigPath（char[]，配置文件路径，可为空）、ar_P_BaseDir（char[]，工程根目录，可为空）；  
功能：根据配置启动 DIDInfo 生成流程，解析 DID 信息及 Reset-DID 配置表，输出 DIDInfo 文件（对应 `generate_didinfo_from_excel.main()`）。  

2、`void DIDInfo_From_Excel(char ar_P_ExcelPath[], char ar_P_OutputPath[])`  
返回值类型：无；  
形参：ar_P_ExcelPath（char[]，DID 信息 Excel 路径）、ar_P_OutputPath（char[]，输出 DIDInfo 文件路径）；  
功能：直接从指定 Excel 读取 DID 信息并生成 DIDInfo 文件，由 `generators/capl_didinfo` 中服务实现。  

4.1.1.5 did-config解析及中间文件生成模块描述  
本模块负责根据 DID 配置 Excel 生成 DIDConfig.txt（或配置指定名称）文件，描述各诊断 DID 的配置关系和参数，为诊断配置和测试环境提供统一的配置文件。  

4.1.1.5.1 软件架构  

4.1.1.5.2 模块功能说明  
1. 从 `Configuration.txt` / `FixedConfig.txt` 读取本模块相关配置（DID 配置 Excel 输入、DIDConfig 输出文件名及目录等）；  
2. 打开 DID 配置 Excel，解析表头，定位每条 DID 在诊断通信中的配置字段，例如功能类型、访问权限、会话/安全等级、上下限值、刷写相关标志等；  
3. 逐行读取 DID 配置信息，对必填字段、取值范围、一致性（如长度与 DIDInfo 中长度是否匹配）等进行检查，并对原始数据做必要的清洗和标准化；  
4. 根据既定的 DIDConfig 文件格式规范，将每条 DID 的配置转换为一条或多条配置行，包含该 DID 的所有诊断配置参数；  
5. 将所有配置行按约定顺序写入 DIDConfig 输出文件，确保分隔符、编码、换行符等细节符合既定规范，便于诊断栈或测试环境直接加载；  
6. 在日志中记录解析到的 DID 数量、DIDConfig 输出路径、发现的配置问题（如缺失字段、值非法等）以及生成过程中的错误信息。  

4.1.1.5.3 接口说明  
1、`void DIDConfig_Generate(char ar_P_ConfigPath[], char ar_P_BaseDir[])`  
返回值类型：无；  
形参：ar_P_ConfigPath（char[]，配置路径，可为空）、ar_P_BaseDir（char[]，工程根目录，可为空）；  
功能：启动 DID 配置生成流程，生成 DIDConfig 文件，对应 `generate_did_config.main()`。  

2、`void DIDConfig_From_Excel(char ar_P_ExcelPath[], char ar_P_OutputPath[])`  
返回值类型：无；  
形参：ar_P_ExcelPath（char[]，DID 配置 Excel 路径）、ar_P_OutputPath（char[]，输出 DIDConfig 文件路径）；  
功能：直接从指定 Excel 解析并生成 DIDConfig 文件，由 `generators/capl_didconfig` 中的服务实现。  

4.1.1.6 串口通讯矩阵解析及中间文件生成模块描述  
本模块负责读取串口通信矩阵 Excel（例如 IVI→MCU、MCU→IVI 等 Sheet），生成 Uart.txt 串口配置文件，描述每个串口消息的通道、方向、信号、周期等信息，为车载或台架串口通信提供统一配置。  

4.1.1.6.1 软件架构  

4.1.1.6.2 模块功能说明  
1. 从 `Configuration.txt` / `FixedConfig.txt` 读取本模块相关配置（UART 矩阵 Excel 输入、Uart.txt 输出路径、串口参数等）；  
2. 打开 UART 矩阵 Excel，解析表头，定位通道、方向、信号名称、周期等关键字段；  
3. 逐行读取 UART 矩阵，构建内部的串口消息/信号数据结构，并根据配置或规则进行必要的过滤与校验；  
4. 将内部数据结构转换为 Uart.txt 中约定格式的配置行，覆盖通道、方向、信号、周期等信息；  
5. 将所有配置行写入 Uart.txt 输出文件，并保证文件格式、编码和换行符符合约定；  
6. 在日志中记录解析到的消息/信号数量、Uart.txt 输出路径，以及解析/生成过程中的错误信息，方便排查配置或 Excel 问题。  

4.1.1.6.3 接口说明  
1、`void UART_Generate(char ar_P_ConfigPath[], char ar_P_BaseDir[])`  
返回值类型：无；  
形参：ar_P_ConfigPath（char[]，配置路径，可为空）、ar_P_BaseDir（char[]，工程根目录，可为空）；  
功能：根据配置文件生成 Uart.txt 串口配置，对应 `generate_uart_from_config.main()`。  

2、`void UART_From_Excel(char ar_P_ExcelPath[], char ar_P_OutputPath[])`  
返回值类型：无；  
形参：ar_P_ExcelPath（char[]，串口矩阵 Excel 路径）、ar_P_OutputPath（char[]，输出 Uart.txt 路径）；  
功能：直接从指定 Excel 解析 UART 矩阵并输出配置文件，由 `generators/capl_uart` 中服务实现。  

4.1.1.7 io-mapping解析及中间文件生成模块描述  
本模块负责解析 IO_mapping Excel，将信号名和枚举文本转换为内部统一的“信号名→路径”“枚举值→数值”等映射，为关键字用例、CIN、UART 等生成模块提供共享的中间数据（IOMappingContext）。  

4.1.1.7.1 软件架构  

4.1.1.7.2 模块功能说明  
1. 从 `Configuration.txt` / `FixedConfig.txt` 读取本模块相关配置（IO_mapping Excel 路径、Sheet 列表等）；  
2. 打开 IO_mapping Excel，解析表头，定位 Name、Path、Values 等关键列；  
3. 逐行读取 IO_mapping 数据，构建“信号名→路径”“枚举文本→数值”等映射字典，并进行基本校验（如 Name 重复、Path 为空等）；  
4. 将上述映射封装为 IOMappingContext，供关键字用例脚本生成、CIN 生成、UART 生成等模块统一使用；  
5. 在日志中记录成功加载的条目数量、遇到的表头错误或数据问题，以及对应的 Excel/Sheet 信息，便于排查配置或表结构问题。  

4.1.1.7.3 接口说明  
1、`void IOMapping_Load_From_Config(char ar_P_ConfigPath[], char ar_P_BaseDir[])`  
返回值类型：无；  
形参：ar_P_ConfigPath（char[]，配置路径，可为空）、ar_P_BaseDir（char[]，工程根目录，可为空）；  
功能：从配置中读取 IO_mapping Excel 的路径和 Sheet 信息，并完成 IO 映射加载，构建 IOMappingContext（对应 `core/translator/io_mapping.py` 的加载入口）。  

2、`void IOMapping_Transform(char ar_P_SignalName[], char ar_P_PathOut[], float* p_ValueOut)`  
返回值类型：无；  
形参：ar_P_SignalName（char[]，信号名或枚举文本）、ar_P_PathOut（char[]，输出路径）、p_ValueOut（float*，输出数值，可选）；  
功能：根据已加载的 IO 映射，将信号名或枚举文本转换为真实路径和数值，用于各生成模块在翻译步骤或生成脚本时调用。  

4.1.1.8 工程配置保存及导入模块描述  
本模块负责统一管理工程级配置：读取、写入 `Configuration.txt` / `FixedConfig.txt`，提供前端所需的路径、筛选项、域配置等数据，并支持保存当前配置、导入已有预设。  

4.1.1.8.1 软件架构  

4.1.1.8.2 模块功能说明  
1. 从 `Configuration.txt` / `FixedConfig.txt` 读取当前工程的全局配置（输入输出路径、域配置、筛选条件等）；  
2. 将底层 INI 配置转换为前端和服务层易于使用的结构化对象（如各域的 Excel 路径、输出路径、选项列表等）；  
3. 接收前端提交的配置变更（路径修改、筛选条件调整等），更新内存中的配置对象；  
4. 按约定规则将配置变更写回 `Configuration.txt`，并处理与 `FixedConfig.txt` 之间的覆盖关系（固定项不被误改）；  
5. 支持预设的保存和导入，将当前配置导出为预设文件，或从预设文件恢复配置状态；  
6. 在日志中记录配置加载、保存、导入的关键信息和错误（如写文件失败、配置项缺失等），以便排查环境或权限问题。  

4.1.1.8.3 接口说明  
1、`void Config_Load_All(char ar_P_BaseDir[])`  
返回值类型：无；  
形参：ar_P_BaseDir（char[]，工程根目录，可为空）；  
功能：读取 `Configuration.txt` / `FixedConfig.txt` 中的所有工程级配置，并填充到内存中的配置中心对象（对应 `services/config_manager.py` / `utils/config.py`）。  

2、`void Config_Save_All(char ar_P_BaseDir[])`  
返回值类型：无；  
形参：ar_P_BaseDir（char[]，工程根目录，可为空）；  
功能：将当前内存中的配置状态写回 `Configuration.txt` 等配置文件，实现“保存当前工程配置”（对应 `services/config_manager.py` 中的保存逻辑）。  

4.1.1.9 log日志模块描述  
本模块统一管理运行期日志：创建时间戳日志目录、组织生成文件日志和表格解析日志、将标准输出重定向到日志文件，并提供去重和分类能力，保证每次运行的日志清晰可追溯。  

4.1.1.9.1 软件架构  

4.1.1.9.2 模块功能说明  
1. 在工程根目录下创建按时间戳命名的日志根目录（如 `log/log_YYYYMMDD_HHMMSS/`），并在其下划分子目录（生成文件日志、解析表格日志等）；  
2. 提供 Tee 功能，将标准输出和标准错误重定向到主日志文件，同时保留在控制台输出；  
3. 为不同类型的表格解析（TestCases、IO_mapping、UART_Matrix 等）创建专用 Logger，分别输出到对应的解析日志文件；  
4. 提供一次性去重过滤器（如按用例 ID 去重日志），避免同一条信息在一次运行中重复打印；  
5. 在每次生成任务结束时，正确关闭和清理日志句柄，为下一次运行创建新的干净日志目录；  
6. 在日志中输出关键信息（开始/结束时间、错误详情、未生成原因等），方便问题定位与验收。  

4.1.1.9.3 接口说明  
1、`void Log_Init_RunContext(char ar_P_BaseDir[])`  
返回值类型：无；  
形参：ar_P_BaseDir（char[]，工程根目录，可为空）；  
功能：初始化本次运行的日志目录结构和主日志文件，将运行上下文中的日志目录信息准备好（对应 `core/log_run_context.py`、`core/generator_logging.py` 等）。  

2、`void Log_Tee_Stdout(void)`  
返回值类型：无；  
形参：无；  
功能：将标准输出/错误重定向到当前运行的主日志文件，同时保留控制台输出，便于统一收集所有打印信息（对应 `core/run_context.py`、`utils/logger.py` 相关逻辑）。  

4.1.1.10 打包模块描述  
本模块负责使用 PyInstaller 将整个 Python 工具打包为单文件 EXE，包含 Flask Web 服务、各生成入口脚本、核心逻辑及前端静态资源，使无 Python 环境的工位也能直接运行。  

4.1.1.10.1 软件架构  

4.1.1.10.2 模块功能说明  
1. 从 `build_exe.py` 中读取打包相关配置（入口脚本、额外依赖、资源文件、输出路径等）；  
2. 配置 PyInstaller 的入口为 `app.py` 或指定的主脚本，确保 Web 服务和各生成脚本被正确打包进 EXE；  
3. 将 `templates/`、`static/` 以及必需的配置文件等资源以 add-data 形式打包，与 EXE 保持正确相对路径；  
4. 执行 PyInstaller 打包流程，生成单文件 EXE；  
5. 在日志中记录打包过程的关键信息（使用的命令、输出路径、错误信息等），用于确认打包结果是否符合预期。  

4.1.1.10.3 接口说明  
1、`void Build_Exe_Run(char ar_P_BaseDir[])`  
返回值类型：无；  
形参：ar_P_BaseDir（char[]，工程根目录，可为空）；  
功能：执行打包流程，调用 PyInstaller 将当前工程打包为单文件 EXE（对应 `build_exe.py` 中的主流程）。  