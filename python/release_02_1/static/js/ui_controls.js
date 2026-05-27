/**
 * ui_controls.js - Tab 切换、弹窗、用例树、运行按钮、心跳
 * 依赖: api.js (window.API), config_handler.js (selection, autoSaveConfig, getChecks, getSelectedSheets, collectCurrentState, 及各 config 对象)
 */
(function (global) {
    'use strict';

    var selection = global.selection;
    var uartCommConfig = global.uartCommConfig;
    var powerConfig = global.powerConfig;
    var relayConfigs = global.relayConfigs;
    var relayCoilModes = global.relayCoilModes;
    var igConfig = global.igConfig;
    var pwConfig = global.pwConfig;
    var ignConfig = global.ignConfig;
    var loginConfig = global.loginConfig || { username: '', password: '' };

    /** 一键生成失败时组装用户可读提示（避免弹窗直接展示 Python 堆栈）。 */
    function formatGenerationFailureAlert(result, httpStatus) {
        var lines = [];
        if (httpStatus) {
            lines.push('HTTP ' + httpStatus);
        }
        if (result && result.message) {
            lines.push(result.message);
        } else {
            lines.push('未知错误');
        }
        var detail = result && result.detail ? String(result.detail).trim() : '';
        if (detail) {
            var isTraceback = detail.indexOf('Traceback (most recent call last)') !== -1
                || detail.indexOf('File "') !== -1;
            if (isTraceback) {
                lines.push('\n技术详情已写入运行日志，请打开 log 目录下对应生成日志查看。');
            } else if (detail.length <= 800) {
                lines.push('\n' + detail);
            } else {
                lines.push('\n' + detail.substring(0, 800) + '\n…（详情过长已截断）');
            }
        }
        return lines.join('\n');
    }

    function toggleCheck(groupId) {
        var inputs = document.querySelectorAll('#' + groupId + ' input');
        var isRadioGroup = groupId.indexOf('platform') !== -1 || groupId.indexOf('model') !== -1;
        if (isRadioGroup) {
            var allUnchecked = Array.from(inputs).every(function (i) { return !i.checked; });
            if (allUnchecked && inputs.length > 0) {
                inputs[0].checked = true;
                global.handleRadioChange(inputs[0]);
            } else {
                inputs.forEach(function (i) { i.checked = false; });
            }
        } else {
            var allChecked = Array.from(inputs).every(function (i) { return i.checked; });
            inputs.forEach(function (i) { i.checked = !allChecked; });
        }
        global.autoSaveConfig();
    }

    async function selectPath(key, type, dispId) {
        try {
            var data = await global.API.selectFile(type);
            if (data.success) {
                var el = document.getElementById(dispId);
                if (el.tagName === 'INPUT') {
                    el.value = data.path;
                    selection[key] = data.path;
                } else {
                    selection[key] = data.path;
                    el.innerText = '√ ' + data.filename;
                    el.classList.add('selected');
                    if (key.indexOf('input') !== -1) selection[key + '_type'] = type;
                }
                global.autoSaveConfig();
                var keyToContainer = { can_input: 'can_select_cases_group', c_input: 'c_select_cases_group', d_input: 'd_select_cases_group' };
                if (keyToContainer[key]) {
                    autoParseAndRender(key, keyToContainer[key]);
                }
                if (key === 'd_io_excel' && global.autoParseDtcIoSheets) {
                    // 选择 IO_Mapping 后，显示下方的灰色勾选区域
                    var wrap = document.getElementById('d_io_sheets_wrapper');
                    if (wrap) wrap.style.display = 'block';
                    global.autoParseDtcIoSheets();
                }
            }
        } catch (e) { console.error(e); }
    }

    /**
     * 清除已选路径并同步到后端
     * @param {string} key - 对应 selection 中的键名 (如 'can_input', 'io_excel')
     * @param {string} dispId - 对应显示的 span 或 input ID (如 'can_disp')
     */
    function clearPath(key, dispId) {
        if (selection && Object.prototype.hasOwnProperty.call(selection, key)) {
            selection[key] = '';
        }
        if (selection && Object.prototype.hasOwnProperty.call(selection, key + '_type')) {
            selection[key + '_type'] = 'file';
        }
        var el = document.getElementById(dispId);
        if (el) {
            if (el.tagName === 'INPUT') {
                el.value = '';
            } else {
                el.innerText = '未选择';
                el.classList.remove('selected');
            }
        }
        // 对应的“勾选用例”区域不再显示提示文字，保持为空，由解析成功后再填充
        var keyToContainer = {
            can_input: 'can_select_cases_group',
            c_input: 'c_select_cases_group',
            d_input: 'd_select_cases_group'
        };
        if (keyToContainer[key]) {
            var container = document.getElementById(keyToContainer[key]);
            if (container) {
                container.innerHTML = '';
            }
        }
        // 清空 DTC IO_Mapping 时，同时清空并隐藏 Sheet 勾选区域（保持干净，不显示灰框）
        if (key === 'd_io_excel') {
            var ioWrapper = document.getElementById('d_io_sheets_wrapper');
            if (ioWrapper) ioWrapper.style.display = 'none';
            var ioContainer = document.getElementById('d_io_sheets_container');
            if (ioContainer) ioContainer.innerHTML = '';
        }
        if (global.autoSaveConfig) {
            global.autoSaveConfig();
        }
    }

    // 串口通信 / 电源 / 继电器 / IG / PW / 点火循环 / 登录配置的清空函数
    function clearUartCommConfig() {
        uartCommConfig.port = '';
        uartCommConfig.baudrate = '';
        uartCommConfig.dataBits = '';
        uartCommConfig.stopBits = '';
        uartCommConfig.kHANDSHAKE_DISABLED = '';
        uartCommConfig.parity = '';
        uartCommConfig.frameTypeIs8676 = '';
        var disp = document.getElementById('c_uart_comm_disp');
        if (disp) {
            disp.innerText = '未配置';
            disp.classList.remove('selected');
        }
        if (global.autoSaveConfig) global.autoSaveConfig();
    }

    function clearPowerConfig() {
        powerConfig.port = '';
        powerConfig.baudrate = '';
        powerConfig.dataBits = '';
        powerConfig.stopBits = '';
        powerConfig.kHANDSHAKE_DISABLED = '';
        powerConfig.parity = '';
        powerConfig.channel = '';
        var disp = document.getElementById('c_pwr_disp');
        if (disp) {
            disp.innerText = '未配置';
            disp.classList.remove('selected');
        }
        if (global.autoSaveConfig) global.autoSaveConfig();
    }

    function clearRelayConfigState() {
        relayConfigs.length = 0;
        for (var k in relayCoilModes) {
            if (Object.prototype.hasOwnProperty.call(relayCoilModes, k)) {
                delete relayCoilModes[k];
            }
        }
        var disp = document.getElementById('c_rly_disp');
        if (disp) {
            disp.innerText = '未配置';
            disp.classList.remove('selected');
        }
        var list = document.getElementById('relayList');
        if (list) {
            list.innerHTML = global.UIComponents.renderMessage('暂无继电器配置，点击"添加继电器"开始配置', 'center');
        }
        // 继电器这里直接显式发送最小 state，确保后端能收到 c_rly: []
        if (global.API && global.API.autoSaveConfig) {
            global.API.autoSaveConfig({ c_rly: [] });
        } else if (global.autoSaveConfig) {
            global.autoSaveConfig();
        }
    }

    function clearIGConfigState() {
        igConfig.equipmentType = '';
        igConfig.channelNumber = '';
        igConfig.initStatus = '';
        igConfig.eqPosition = '';
        var disp = document.getElementById('c_ig_disp');
        if (disp) {
            disp.innerText = '未配置';
            disp.classList.remove('selected');
        }
        if (global.autoSaveConfig) global.autoSaveConfig();
    }

    function clearPWConfigState() {
        pwConfig.equipmentType = '';
        pwConfig.channelNumber = '';
        pwConfig.initStatus = '';
        pwConfig.eqPosition = '';
        var disp = document.getElementById('c_pw_disp');
        if (disp) {
            disp.innerText = '未配置';
            disp.classList.remove('selected');
        }
        if (global.autoSaveConfig) global.autoSaveConfig();
    }

    function clearIgnitionConfigState() {
        ignConfig.waitTime = '';
        ignConfig.current = '';
        var disp = document.getElementById('c_ignition_disp');
        if (disp) {
            disp.innerText = '未配置';
            disp.classList.remove('selected');
        }
        if (global.autoSaveConfig) global.autoSaveConfig();
    }

    function clearLoginConfigState() {
        loginConfig.username = '';
        loginConfig.password = '';
        var disp = document.getElementById('c_login_disp');
        if (disp) {
            disp.innerText = '未配置';
            disp.classList.remove('selected');
        }
        if (global.autoSaveConfig) global.autoSaveConfig();
    }

    async function autoParseAndRender(key, containerId, initialSelectedSheets) {
        var path = selection[key];
        var container = document.getElementById(containerId);
        if (!container) return;
        if (!path) {
            // 未选择文件或文件夹时，不显示任何提示文案，保持区域为空
            container.innerHTML = '';
            return;
        }
        try {
            var data = await global.API.parseFileStructure(path);
            if (!data.success) {
                container.innerHTML = global.UIComponents.renderMessage('解析失败: ' + (data.message || '未知错误'), 'error');
                return;
            }
            container.innerHTML = global.UIComponents.renderCaseSelectCheckboxes(data.data, containerId);
            if (initialSelectedSheets && String(initialSelectedSheets).trim()) {
                global.restoreCaseCheckboxes(containerId, initialSelectedSheets);
            } else {
                container.querySelectorAll('input.sheet-checkbox').forEach(function (inp) { inp.checked = false; });
            }
            updateAllParentAndSelectAllState(containerId);
        } catch (e) {
            console.error(e);
            container.innerHTML = global.UIComponents.renderMessage('解析请求失败: ' + e.message, 'error');
        }
    }

    async function autoParseDtcIoSheets(initialSelectedSheets) {
        var path = selection.d_io_excel;
        var container = document.getElementById('d_io_sheets_container');
        if (!container) return;

        // 只要有有效路径并开始解析，就确保外层灰色区域可见（支持刷新后从配置还原的场景）
        var wrap = document.getElementById('d_io_sheets_wrapper');

        // 未选择 IO_Mapping 文件时，保持区域为空（不显示提示文字）
        if (!path) {
            if (wrap) wrap.style.display = 'none';
            container.innerHTML = '';
            return;
        }
        if (wrap) wrap.style.display = 'block';

        try {
            var data = await global.API.parseFileStructure(path);
            if (!data.success || !data.data || data.data.length === 0) {
                container.innerHTML = global.UIComponents.renderMessage('解析失败', 'error');
                return;
            }

            // 复用通用树形渲染逻辑，使样式/折叠行为与“勾选用例”一致
            container.innerHTML = global.UIComponents.renderCaseSelectCheckboxes(data.data, 'd_io_sheets_container');

            // 处理勾选状态还原：
            // - initialSelectedSheets 为空或为 "*"：默认全选
            // - 否则按 "Sheet1,Sheet2" 还原
            if (initialSelectedSheets && initialSelectedSheets !== '*') {
                var first = data.data[0] || {};
                var filename = first.relpath || first.filename || '';
                var formatted = String(initialSelectedSheets)
                    .split(',')
                    .map(function (s) { return s.trim(); })
                    .filter(Boolean)
                    .map(function (s) { return filename + '|' + s; })
                    .join(',');
                if (global.restoreCaseCheckboxes) {
                    global.restoreCaseCheckboxes('d_io_sheets_container', formatted);
                }
            } else {
                container.querySelectorAll('input.sheet-checkbox').forEach(function (inp) {
                    inp.checked = true;
                });
            }

            updateAllParentAndSelectAllState('d_io_sheets_container');
        } catch (e) {
            console.error(e);
            container.innerHTML = global.UIComponents.renderMessage('解析异常', 'error');
        }
    }

    function toggleTreeExpand(blockId) {
        var block = document.getElementById(blockId);
        if (!block) return;
        block.classList.toggle('expanded');
    }

    function onParentCheckboxChange(parentEl) {
        var blockId = parentEl.getAttribute('data-parent-block');
        var block = document.getElementById(blockId);
        if (!block) return;
        var sheetInputs = block.querySelectorAll('input.sheet-checkbox');
        var allChecked = sheetInputs.length > 0 && Array.from(sheetInputs).every(function (i) { return i.checked; });
        var newChecked = !allChecked;
        sheetInputs.forEach(function (inp) { inp.checked = newChecked; });
        parentEl.checked = newChecked;
        parentEl.indeterminate = false;
        global.autoSaveConfig();
    }

    function onSheetCheckboxChange(sheetEl) {
        var blockId = sheetEl.getAttribute('data-parent-block');
        updateParentCheckboxState(blockId);
        global.autoSaveConfig();
    }

    function updateParentCheckboxState(blockId) {
        var block = document.getElementById(blockId);
        if (!block) return;
        var parentCb = block.querySelector('input.parent-checkbox');
        var sheetInputs = block.querySelectorAll('input.sheet-checkbox');
        if (!parentCb || sheetInputs.length === 0) return;
        var n = sheetInputs.length;
        var checkedCount = Array.from(sheetInputs).filter(function (i) { return i.checked; }).length;
        parentCb.checked = checkedCount === n;
        parentCb.indeterminate = checkedCount > 0 && checkedCount < n;
    }

    function updateAllParentAndSelectAllState(containerId) {
        var container = document.getElementById(containerId);
        if (!container) return;
        container.querySelectorAll('.case-table-block.case-tree-parent').forEach(function (block) {
            updateParentCheckboxState(block.id);
        });
    }

    function toggleCaseSelection(containerId) {
        var container = document.getElementById(containerId);
        if (!container) return;
        var sheetInputs = Array.from(container.querySelectorAll('input.sheet-checkbox'));
        if (sheetInputs.length === 0) return;
        var allChecked = sheetInputs.every(function (inp) { return inp.checked; });
        var nextChecked = !allChecked;
        sheetInputs.forEach(function (inp) { inp.checked = nextChecked; });
        updateAllParentAndSelectAllState(containerId);
        global.autoSaveConfig();
    }

    async function parseFileStructure(key) {
        var path = selection[key];
        if (!path) {
            alert('请先选择文件或文件夹');
            return;
        }
        try {
            var data = await global.API.parseFileStructure(path);
            if (!data.success) {
                alert('解析失败: ' + (data.message || '未知错误'));
                return;
            }
            var container = document.getElementById('parseFileContent');
            if (container) container.innerHTML = global.UIComponents.renderParseResult(data.data);
            var modal = document.getElementById('parseFileModal');
            if (modal) modal.style.display = 'flex';
        } catch (e) {
            console.error(e);
            alert('解析请求失败: ' + e.message);
        }
    }

    function closeParseFileModal() {
        var modal = document.getElementById('parseFileModal');
        if (modal) modal.style.display = 'none';
    }

    function handleRadioChange(clickedInput) {
        var groupName = clickedInput.name;
        var allInputs = document.querySelectorAll('input[name="' + groupName + '"]');
        allInputs.forEach(function (input) {
            if (input !== clickedInput) input.checked = false;
        });
        global.autoSaveConfig();
    }

    function getChecksForRun(id) {
        var inputs = Array.from(document.querySelectorAll('#' + id + ' input'));
        var isRadioGroup = id.indexOf('platform') !== -1 || id.indexOf('model') !== -1;
        var checked = inputs.filter(function (i) { return i.checked; }).map(function (i) { return i.value; });
        if (isRadioGroup) {
            return checked.length > 0 ? checked[0] : '';
        }
        return checked.length === 0 ? 'ALL' : checked.join(',');
    }

    async function run() {
        var btn = document.getElementById('runBtn');
        var outPath = document.getElementById('out_root') ? document.getElementById('out_root').value : '';
        if (!outPath) { alert('请选择输出路径！'); return; }
        var payload = {
            can_input: selection.can_input,
            can_input_type: selection.can_input_type,
            out_root: outPath,
            can_is_dir: selection.can_input_type === 'folder',
            levels: global.getChecks('level_group'),
            platforms: global.getChecks('platform_group'),
            models: global.getChecks('model_group'),
            target_versions: global.getChecks('target_version_group'),
            uds_ecu_qualifier: document.getElementById('uds_ecu_qualifier') ? document.getElementById('uds_ecu_qualifier').value : '',
            selected_sheets: global.getSelectedSheets('can_select_cases_group'),
            log_level: document.getElementById('log_level') ? document.getElementById('log_level').value : 'info'
        };
        Object.keys(selection).forEach(function (k) { if (payload[k] === undefined) payload[k] = selection[k]; });
        btn.disabled = true;
        btn.innerText = '⏳ 执行中...';
        try {
            var out = await global.API.generate(payload);
            var result = out.data;
            if (!out.ok || !result.success) {
                alert('❌ 生成失败\n\n' + formatGenerationFailureAlert(result, out.status));
                return;
            }
            alert(result.message);
        } catch (e) {
            console.error('请求失败:', e);
            alert('❌ 请求失败: ' + e.message + '\n\n请检查浏览器控制台查看详细信息。');
        } finally {
            btn.disabled = false;
            btn.innerText = '⚡ 开始一键运行左右后域任务';
        }
    }

    async function runCentral() {
        var btn = document.getElementById('runCentralBtn');
        var outPath = document.getElementById('c_out_root') ? document.getElementById('c_out_root').value : '';
        if (!outPath) { alert('请选择输出路径！'); return; }
        var payload = {
            c_out_root: outPath,
            c_uart: selection.c_uart || '',
            c_srv: selection.c_srv || '',
            c_uart_comm: uartCommConfig,
            c_input: selection.c_input || '',
            c_input_type: selection.c_input_type || 'file',
            c_is_dir: selection.c_input_type === 'folder',
            c_selected_sheets: global.getSelectedSheets('c_select_cases_group'),
            c_levels: global.getChecks('c_level_group'),
            c_platforms: global.getChecks('c_platform_group'),
            c_models: global.getChecks('c_model_group'),
            c_target_versions: global.getChecks('c_target_version_group'),
            c_uds_ecu_qualifier: document.getElementById('c_uds_ecu_qualifier') ? document.getElementById('c_uds_ecu_qualifier').value : '',
            c_log_level: document.getElementById('c_log_level') ? document.getElementById('c_log_level').value : 'info',
            c_ign_waitTime: ignConfig.waitTime || '',
            c_ign_current: ignConfig.current || '',
            power_config: powerConfig,
            relay_configs: global.relayConfigsForSave ? global.relayConfigsForSave(relayConfigs) : relayConfigs,
            ig_config: igConfig,
            pw_config: pwConfig
        };
        btn.disabled = true;
        btn.innerText = '⏳ 执行中...';
        try {
            var out = await global.API.generateCentral(payload);
            var result = out.data;
            if (!out.ok || !result.success) {
                alert('❌ 生成失败\n\n' + formatGenerationFailureAlert(result, out.status));
                return;
            }
            alert(result.message);
        } catch (e) {
            console.error('请求失败:', e);
            alert('❌ 请求失败: ' + e.message + '\n\n请检查浏览器控制台查看详细信息。');
        } finally {
            btn.disabled = false;
            btn.innerText = '⚡ 开始一键运行中央域任务';
        }
    }

    async function runDTC() {
        var btn = document.getElementById('runDTCBtn');
        var outPath = document.getElementById('d_out_root') ? document.getElementById('d_out_root').value : '';
        if (!outPath) { alert('请选择输出路径！'); return; }
        var payload = {
            d_input: selection.d_input || '',
            d_input_type: selection.d_input_type || 'file',
            d_selected_sheets: global.getSelectedSheets('d_select_cases_group'),
            d_log_level: document.getElementById('d_log_level') ? document.getElementById('d_log_level').value : 'info',
            d_io_excel: selection.d_io_excel || '',
            d_io_selected_sheets: (global.getDtcIoSelectedSheets ? global.getDtcIoSelectedSheets() : ''),
            d_didconfig_excel: selection.d_didconfig_excel || '',
            d_resetdid_excel: selection.d_resetdid_excel || '',
            d_cin_excel: selection.d_cin_excel || '',
            d_srv_excel: selection.d_srv_excel || '',
            d_out_root: outPath,
            d_is_dir: selection.d_input_type === 'folder',
            d_levels: global.getChecks('d_level_group'),
            d_platforms: global.getChecks('d_platform_group'),
            d_models: global.getChecks('d_model_group'),
            d_target_versions: global.getChecks('d_target_version_group'),
            d_uds_ecu_qualifier: document.getElementById('d_uds_ecu_qualifier') ? document.getElementById('d_uds_ecu_qualifier').value : ''
        };
        btn.disabled = true;
        btn.innerText = '⏳ 执行中...';
        try {
            var out = await global.API.generateDTC(payload);
            var result = out.data;
            if (!out.ok || !result.success) {
                alert('❌ 生成失败\n\n' + formatGenerationFailureAlert(result, out.status));
                return;
            }
            alert(result.message);
        } catch (e) {
            console.error('请求失败:', e);
            alert('❌ 请求失败: ' + e.message + '\n\n请检查浏览器控制台查看详细信息。');
        } finally {
            btn.disabled = false;
            btn.innerText = '⚡ 开始一键运行DTC任务';
        }
    }

    // 通用：带“其他（自定义）”的下拉 + 输入框
    function setupSelectWithCustom(selectId, inputId, value, defaultValue) {
        var sel = document.getElementById(selectId);
        if (!sel) return;
        var input = inputId ? document.getElementById(inputId) : null;
        var v = (value || '').toString().trim();
        if (!v) v = (defaultValue || '').toString();
        var standardValues = Array.from(sel.options)
            .map(function (o) { return o.value; })
            .filter(function (val) { return val && val !== '__custom__'; });
        var isStandard = standardValues.indexOf(v) !== -1;
        if (isStandard) {
            sel.value = v;
            if (input) {
                input.style.display = 'none';
                input.value = '';
            }
        } else {
            if (sel.querySelector('option[value="__custom__"]')) {
                sel.value = '__custom__';
                if (input) {
                    input.style.display = v ? 'block' : 'none';
                    input.value = v;
                }
            } else {
                sel.value = v || (standardValues[0] || '');
                if (input) {
                    input.style.display = 'none';
                }
            }
        }
    }

    function getSelectWithCustomValue(selectId, inputId, defaultValue) {
        var sel = document.getElementById(selectId);
        if (!sel) return defaultValue || '';
        var val = sel.value;
        if (val === '__custom__') {
            var input = inputId ? document.getElementById(inputId) : null;
            var v = input ? (input.value || '').trim() : '';
            return v || (defaultValue || '');
        }
        return val || (defaultValue || '');
    }

    function onSelectWithCustomChange(selectId, inputId) {
        var sel = document.getElementById(selectId);
        var input = inputId ? document.getElementById(inputId) : null;
        if (!sel || !input) return;
        if (sel.value === '__custom__') {
            input.style.display = 'block';
            input.focus();
        } else {
            input.style.display = 'none';
        }
    }

    async function showUartCommConfig() {
        try {
            var data = await global.API.getSerialPorts();
            var portSelect = document.getElementById('uart_comm_port');
            if (portSelect) {
                portSelect.innerHTML = '';
                if (data.success && data.ports && data.ports.length > 0) {
                    data.ports.forEach(function (port) {
                        var option = document.createElement('option');
                        option.value = port.port;
                        option.textContent = port.port;
                        if (port.port === uartCommConfig.port) option.selected = true;
                        portSelect.appendChild(option);
                    });
                }
                if ((!data.ports || data.ports.length === 0) && uartCommConfig && uartCommConfig.port) {
                    var opt = document.createElement('option');
                    opt.value = uartCommConfig.port;
                    opt.textContent = uartCommConfig.port + ' (已配置)';
                    opt.selected = true;
                    portSelect.appendChild(opt);
                }
            }
        } catch (e) {
            console.error('获取串口列表失败:', e);
            if (uartCommConfig && uartCommConfig.port) {
                var portSelect = document.getElementById('uart_comm_port');
                if (portSelect) {
                    var opt = document.createElement('option');
                    opt.value = uartCommConfig.port;
                    opt.textContent = uartCommConfig.port + ' (已配置)';
                    opt.selected = true;
                    portSelect.appendChild(opt);
                }
            }
        }
        var ids = ['uart_comm_port', 'uart_comm_baudrate', 'uart_comm_databits', 'uart_comm_stopbits', 'uart_comm_handshake', 'uart_comm_parity', 'uart_comm_frameTypeIs8676'];
        var keys = ['port', 'baudrate', 'dataBits', 'stopBits', 'kHANDSHAKE_DISABLED', 'parity', 'frameTypeIs8676'];
        keys.forEach(function (k, i) {
            var el = document.getElementById(ids[i]);
            var val = uartCommConfig[k] || (k === 'baudrate' ? '115200' : k === 'dataBits' ? '8' : k === 'stopBits' ? '1' : '0');
            if (k === 'baudrate') {
                setupSelectWithCustom('uart_comm_baudrate', 'uart_comm_baudrate_custom', val, '115200');
            } else if (k === 'dataBits') {
                setupSelectWithCustom('uart_comm_databits', 'uart_comm_databits_custom', val, '8');
            } else if (k === 'stopBits') {
                setupSelectWithCustom('uart_comm_stopbits', 'uart_comm_stopbits_custom', val, '1');
            } else if (el) {
                el.value = val;
            }
        });
        var modal = document.getElementById('uartCommConfigModal');
        if (modal) modal.style.display = 'flex';
    }

    function closeUartCommConfig() {
        var modal = document.getElementById('uartCommConfigModal');
        if (modal) modal.style.display = 'none';
    }

    function saveUartCommConfig() {
        uartCommConfig.port = document.getElementById('uart_comm_port') ? document.getElementById('uart_comm_port').value : '';
        uartCommConfig.baudrate = document.getElementById('uart_comm_baudrate')
            ? getSelectWithCustomValue('uart_comm_baudrate', 'uart_comm_baudrate_custom', '115200')
            : '';
        uartCommConfig.dataBits = document.getElementById('uart_comm_databits')
            ? getSelectWithCustomValue('uart_comm_databits', 'uart_comm_databits_custom', '8')
            : '';
        uartCommConfig.stopBits = document.getElementById('uart_comm_stopbits')
            ? getSelectWithCustomValue('uart_comm_stopbits', 'uart_comm_stopbits_custom', '1')
            : '';
        var uhs = document.getElementById('uart_comm_handshake');
        uartCommConfig.kHANDSHAKE_DISABLED = uhs ? uhs.value : '';
        var upa = document.getElementById('uart_comm_parity');
        uartCommConfig.parity = upa ? upa.value : '';
        uartCommConfig.frameTypeIs8676 = document.getElementById('uart_comm_frameTypeIs8676') ? document.getElementById('uart_comm_frameTypeIs8676').value : '0';
        var disp = document.getElementById('c_uart_comm_disp');
        if (disp) {
            disp.innerText = uartCommConfig.port ? '√ 已配置' : '未配置';
            if (uartCommConfig.port) disp.classList.add('selected'); else disp.classList.remove('selected');
        }
        global.autoSaveConfig();
        closeUartCommConfig();
    }

    async function showPowerConfig() {
        try {
            var data = await global.API.getSerialPorts();
            var portSelect = document.getElementById('power_port');
            if (portSelect) {
                portSelect.innerHTML = '';
                if (data.success && data.ports) {
                    data.ports.forEach(function (port) {
                        var option = document.createElement('option');
                        option.value = port.port;
                        option.textContent = port.port;
                        if (port.port === powerConfig.port) option.selected = true;
                        portSelect.appendChild(option);
                    });
                }
            }
        } catch (e) { console.error('获取串口列表失败:', e); }
        var ids = ['power_port', 'power_baudrate', 'power_databits', 'power_stopbits', 'power_handshake', 'power_parity', 'power_channel'];
        var keys = ['port', 'baudrate', 'dataBits', 'stopBits', 'kHANDSHAKE_DISABLED', 'parity', 'channel'];
        keys.forEach(function (k, i) {
            var el = document.getElementById(ids[i]);
            var val = powerConfig[k] || (k === 'baudrate' ? '115200' : k === 'channel' ? '1' : k === 'dataBits' ? '8' : k === 'stopBits' ? '1' : '0');
            if (k === 'baudrate') {
                setupSelectWithCustom('power_baudrate', 'power_baudrate_custom', val, '115200');
            } else if (k === 'dataBits') {
                setupSelectWithCustom('power_databits', 'power_databits_custom', val, '8');
            } else if (k === 'stopBits') {
                setupSelectWithCustom('power_stopbits', 'power_stopbits_custom', val, '1');
            } else if (el) {
                el.value = val;
            }
        });
        var modal = document.getElementById('powerConfigModal');
        if (modal) modal.style.display = 'flex';
    }

    function closePowerConfig() {
        var modal = document.getElementById('powerConfigModal');
        if (modal) modal.style.display = 'none';
    }

    function savePowerConfig() {
        powerConfig.port = document.getElementById('power_port') ? document.getElementById('power_port').value : '';
        powerConfig.baudrate = document.getElementById('power_baudrate')
            ? getSelectWithCustomValue('power_baudrate', 'power_baudrate_custom', '115200')
            : '';
        powerConfig.dataBits = document.getElementById('power_databits')
            ? getSelectWithCustomValue('power_databits', 'power_databits_custom', '8')
            : '';
        powerConfig.stopBits = document.getElementById('power_stopbits')
            ? getSelectWithCustomValue('power_stopbits', 'power_stopbits_custom', '1')
            : '';
        var phs = document.getElementById('power_handshake');
        powerConfig.kHANDSHAKE_DISABLED = phs ? phs.value : '';
        var ppa = document.getElementById('power_parity');
        powerConfig.parity = ppa ? ppa.value : '';
        var pch = document.getElementById('power_channel');
        powerConfig.channel = pch ? pch.value : '';
        var disp = document.getElementById('c_pwr_disp');
        if (disp) {
            disp.innerText = powerConfig.port ? '√ 已配置' : '未配置';
            if (powerConfig.port) disp.classList.add('selected'); else disp.classList.remove('selected');
        }
        global.autoSaveConfig();
        closePowerConfig();
    }

    function showRelayConfig() {
        renderRelayList();
        loadSerialPortsForRelay();
        var modal = document.getElementById('relayConfigModal');
        if (modal) modal.style.display = 'flex';
    }

    function closeRelayConfig() {
        var modal = document.getElementById('relayConfigModal');
        if (modal) modal.style.display = 'none';
    }

    async function loadSerialPortsForRelay() {
        try {
            var data = await global.API.getSerialPorts();
            var portSelects = document.querySelectorAll('.relay-port-select');
            if (data.success && data.ports) {
                portSelects.forEach(function (select) {
                    var relayId = parseInt(select.getAttribute('data-relay-id'), 10);
                    var relay = relayConfigs.find(function (item) { return item.id === relayId; });
                    var currentValue = relay && relay.port ? String(relay.port) : '';
                    select.innerHTML = '';
                    var emptyOption = document.createElement('option');
                    emptyOption.value = '';
                    emptyOption.textContent = '';
                    emptyOption.selected = !currentValue;
                    select.appendChild(emptyOption);
                    data.ports.forEach(function (port) {
                        var option = document.createElement('option');
                        option.value = port.port;
                        option.textContent = port.port;
                        if (port.port === currentValue) option.selected = true;
                        select.appendChild(option);
                    });
                    if (currentValue && !data.ports.some(function (port) { return port.port === currentValue; })) {
                        var missingOption = document.createElement('option');
                        missingOption.value = currentValue;
                        missingOption.textContent = currentValue;
                        missingOption.selected = true;
                        select.appendChild(missingOption);
                    }
                });
            }
        } catch (e) { console.error('获取串口列表失败:', e); }
    }

    function addRelay() {
        var relayId = global.relayCounter++;
        relayConfigs.push({
            id: relayId,
            port: '',
            baudrate: '9600',
            // dataBits: '8',
            // stopBits: '1',
            // kHANDSHAKE_DISABLED: '0',
            // parity: '0',
            // relayID: '1',
            // 默认使用 8 路继电器
            relayType: 'RS232_8',
            coilStatuses: []
        });
        relayCoilModes[relayId] = 'open';
        renderRelayList();
        setTimeout(loadSerialPortsForRelay, 100);
    }

    function removeRelay(relayId) {
        var idx = relayConfigs.findIndex(function (r) { return r.id === relayId; });
        if (idx !== -1) relayConfigs.splice(idx, 1);
        renderRelayList();
    }

    function renderRelayList() {
        var container = document.getElementById('relayList');
        if (!container) return;
        relayConfigs.forEach(function (relay) {
            var typeParts = String(relay.relayType || 'RS232_8').split('_');
            var parsedCoilCount = parseInt(typeParts[typeParts.length - 1], 10);
            var coilCount = (!isNaN(parsedCoilCount) && parsedCoilCount > 0) ? parsedCoilCount : 8;
            if (relay.coilStatuses.length !== coilCount) {
                relay.coilStatuses = Array(coilCount).fill(18);
            }
        });
        container.innerHTML = global.UIComponents.renderRelayListHtml(relayConfigs, relayCoilModes);
        setTimeout(loadSerialPortsForRelay, 100);
    }

    function updateRelayConfig(relayId, key, value, index) {
        var relay = relayConfigs.find(function (r) { return r.id === relayId; });
        if (!relay) return;
        if (key === 'coilStatuses' && index !== undefined && index !== null) {
            relay.coilStatuses[index] = parseInt(value, 10);
        } else {
            relay[key] = value;
        }
    }

    function updateRelayType(relayId, relayType) {
        var relay = relayConfigs.find(function (r) { return r.id === relayId; });
        if (!relay) return;
        relay.relayType = relayType;
        // 同样根据 RelayType 末尾数字决定线圈数量
        var typeParts = String(relayType || 'RS232_8').split('_');
        var parsedCoilCount = parseInt(typeParts[typeParts.length - 1], 10);
        var coilCount = (!isNaN(parsedCoilCount) && parsedCoilCount > 0) ? parsedCoilCount : 8;
        if (relay.coilStatuses.length !== coilCount) {
            var oldStatuses = relay.coilStatuses.slice(0);
            relay.coilStatuses = Array(coilCount).fill(18);
            // 尽量保留原有前面部分线圈的配置
            for (var i = 0; i < Math.min(oldStatuses.length, coilCount); i++) {
                relay.coilStatuses[i] = oldStatuses[i];
            }
        }
        renderRelayList();
    }

    function setCoilMode(relayId, mode) {
        relayCoilModes[relayId] = mode;
        renderRelayList();
    }

    function handleRelaySelectChange(relayId, key, selectEl) {
        if (!selectEl) return;
        var value = selectEl.value;
        var customInputId = null;
        if (key === 'baudrate') customInputId = 'relay-baudrate-custom-' + relayId;
        if (key === 'dataBits') customInputId = 'relay-databits-custom-' + relayId;
        if (key === 'stopBits') customInputId = 'relay-stopbits-custom-' + relayId;
        var inputEl = customInputId ? document.getElementById(customInputId) : null;
        if (value === '__custom__') {
            if (inputEl) {
                var relay = relayConfigs.find(function (r) { return r.id === relayId; });
                if (relay && relay[key] && !inputEl.value) {
                    inputEl.value = relay[key];
                }
                inputEl.style.display = 'block';
                inputEl.focus();
            }
        } else {
            if (key === 'relayType') {
                updateRelayType(relayId, value);
            } else {
                updateRelayConfig(relayId, key, value);
            }
            if (inputEl) {
                inputEl.style.display = 'none';
            }
        }
    }

    function handleRelayCustomInputChange(relayId, key, rawValue) {
        var v = (rawValue || '').trim();
        if (!v) return;
        updateRelayConfig(relayId, key, v);
        if (key === 'relayType') {
            renderRelayList();
        }
    }

    function applyCoilStatus(relayId) {
        var relay = relayConfigs.find(function (r) { return r.id === relayId; });
        if (!relay) return;
        var input = document.getElementById('coil-input-' + relayId);
        var inputValue = (input ? input.value : '').trim().replace(/，/g, ',');
        var coilCount = relay.coilStatuses.length;
        var mode = relayCoilModes[relayId] || 'open';
        var selectedCoils = new Set();
        if (!inputValue) {
            relay.coilStatuses = mode === 'open' ? Array(coilCount).fill(17) : Array(coilCount).fill(18);
        } else {
            var parts = inputValue.split(',').map(function (p) { return p.trim(); }).filter(function (p) { return p; });
            parts.forEach(function (part) {
                if (part.indexOf('-') !== -1) {
                    var range = part.split('-');
                    if (range.length === 2) {
                        var start = parseInt(range[0].trim(), 10);
                        var end = parseInt(range[1].trim(), 10);
                        if (!isNaN(start) && !isNaN(end) && start > 0 && end > 0) {
                            var min = Math.min(start, end);
                            var max = Math.max(start, end);
                            for (var i = min; i <= max; i++) {
                                if (i <= coilCount) selectedCoils.add(i);
                            }
                        }
                    }
                } else {
                    var num = parseInt(part, 10);
                    if (!isNaN(num) && num > 0 && num <= coilCount) selectedCoils.add(num);
                }
            });
            if (mode === 'open') {
                relay.coilStatuses = Array(coilCount).fill(18);
                selectedCoils.forEach(function (coilNum) { relay.coilStatuses[coilNum - 1] = 17; });
            } else {
                relay.coilStatuses = Array(coilCount).fill(17);
                selectedCoils.forEach(function (coilNum) { relay.coilStatuses[coilNum - 1] = 18; });
            }
        }
        renderRelayList();
    }

    function saveRelayConfig() {
        var disp = document.getElementById('c_rly_disp');
        if (disp) {
            disp.innerText = relayConfigs.length > 0 ? '√ 已配置 ' + relayConfigs.length + ' 个继电器' : '未配置';
            if (relayConfigs.length > 0) disp.classList.add('selected'); else disp.classList.remove('selected');
        }
        // 显式把当前继电器列表带入 state 并请求保存，确保后端写入当前主配置文件
        var state = (global.collectCurrentState && global.collectCurrentState()) || {};
        state.c_rly = global.relayConfigsForSave
            ? global.relayConfigsForSave(Array.isArray(relayConfigs) ? relayConfigs.slice() : relayConfigs)
            : (Array.isArray(relayConfigs) ? relayConfigs.slice() : relayConfigs);
        if (global.API && global.API.autoSaveConfig) {
            global.API.autoSaveConfig(state);
        } else if (global.autoSaveConfig) {
            global.autoSaveConfig();
        }
        closeRelayConfig();
    }

    function showIGConfig() {
        updateIGConfig();
        var el = document.getElementById('ig_equipment_type');
        if (el) el.value = igConfig.equipmentType || 'Power';
        updateIGConfig();
        var ch = document.getElementById('ig_channel_number');
        if (ch) ch.value = igConfig.channelNumber || '1';
        var is = document.getElementById('ig_init_status');
        if (is) is.value = igConfig.initStatus || '1';
        var eq = document.getElementById('ig_eq_position');
        if (eq) eq.value = igConfig.eqPosition || '1';
        var modal = document.getElementById('igConfigModal');
        if (modal) modal.style.display = 'flex';
    }

    function closeIGConfig() {
        var modal = document.getElementById('igConfigModal');
        if (modal) modal.style.display = 'none';
    }

    function updateIGConfig() {
        var equipmentType = (document.getElementById('ig_equipment_type') && document.getElementById('ig_equipment_type').value) || 'Power';
        var channelSelect = document.getElementById('ig_channel_number');
        var initStatusSelect = document.getElementById('ig_init_status');
        var eqPositionSelect = document.getElementById('ig_eq_position');
        if (channelSelect) {
            channelSelect.innerHTML = '';
            var maxCh = equipmentType === 'Power' ? 3 : 16;
            for (var i = 1; i <= maxCh; i++) {
                var option = document.createElement('option');
                option.value = String(i);
                option.textContent = String(i);
                channelSelect.appendChild(option);
            }
        }
        if (initStatusSelect) {
            initStatusSelect.innerHTML = '';
            if (equipmentType === 'Power') {
                ['0', '1'].forEach(function (v) {
                    var o = document.createElement('option');
                    o.value = v;
                    o.textContent = v === '0' ? '0（下电）' : '1（上电）';
                    initStatusSelect.appendChild(o);
                });
            } else {
                ['17', '18'].forEach(function (v) {
                    var o = document.createElement('option');
                    o.value = v;
                    o.textContent = v === '17' ? '17（常开）' : '18（常关）';
                    initStatusSelect.appendChild(o);
                });
            }
        }
        if (eqPositionSelect) {
            eqPositionSelect.innerHTML = '';
            var count = equipmentType === 'Power' ? 1 : Math.max(1, relayConfigs.length);
            for (var j = 1; j <= count; j++) {
                var opt = document.createElement('option');
                opt.value = String(j);
                opt.textContent = String(j);
                eqPositionSelect.appendChild(opt);
            }
        }
    }

    function saveIGConfig() {
        var el = document.getElementById('ig_equipment_type');
        if (el) igConfig.equipmentType = el.value;
        var ch = document.getElementById('ig_channel_number');
        if (ch) igConfig.channelNumber = ch.value;
        var is = document.getElementById('ig_init_status');
        if (is) igConfig.initStatus = is.value;
        var eq = document.getElementById('ig_eq_position');
        if (eq) igConfig.eqPosition = eq.value;
        var disp = document.getElementById('c_ig_disp');
        if (disp) { disp.innerText = '√ 已配置'; disp.classList.add('selected'); }
        global.autoSaveConfig();
        closeIGConfig();
    }

    function showPWConfig() {
        updatePWConfig();
        var el = document.getElementById('pw_equipment_type');
        if (el) el.value = pwConfig.equipmentType || 'Relay';
        updatePWConfig();
        var ch = document.getElementById('pw_channel_number');
        if (ch) ch.value = pwConfig.channelNumber || '1';
        var is = document.getElementById('pw_init_status');
        if (is) is.value = pwConfig.initStatus || '17';
        var eq = document.getElementById('pw_eq_position');
        if (eq) eq.value = pwConfig.eqPosition || '1';
        var modal = document.getElementById('pwConfigModal');
        if (modal) modal.style.display = 'flex';
    }

    function closePWConfig() {
        var modal = document.getElementById('pwConfigModal');
        if (modal) modal.style.display = 'none';
    }

    function updatePWConfig() {
        var equipmentType = (document.getElementById('pw_equipment_type') && document.getElementById('pw_equipment_type').value) || 'Relay';
        var channelSelect = document.getElementById('pw_channel_number');
        var initStatusSelect = document.getElementById('pw_init_status');
        var eqPositionSelect = document.getElementById('pw_eq_position');
        if (channelSelect) {
            channelSelect.innerHTML = '';
            var maxCh = equipmentType === 'Power' ? 3 : 16;
            for (var i = 1; i <= maxCh; i++) {
                var option = document.createElement('option');
                option.value = String(i);
                option.textContent = String(i);
                channelSelect.appendChild(option);
            }
        }
        if (initStatusSelect) {
            initStatusSelect.innerHTML = '';
            if (equipmentType === 'Power') {
                ['0', '1'].forEach(function (v) {
                    var o = document.createElement('option');
                    o.value = v;
                    o.textContent = v === '0' ? '0（下电）' : '1（上电）';
                    initStatusSelect.appendChild(o);
                });
            } else {
                ['17', '18'].forEach(function (v) {
                    var o = document.createElement('option');
                    o.value = v;
                    o.textContent = v === '17' ? '17（常开）' : '18（常关）';
                    initStatusSelect.appendChild(o);
                });
            }
        }
        if (eqPositionSelect) {
            eqPositionSelect.innerHTML = '';
            var count = equipmentType === 'Power' ? 1 : Math.max(1, relayConfigs.length);
            for (var j = 1; j <= count; j++) {
                var opt = document.createElement('option');
                opt.value = String(j);
                opt.textContent = String(j);
                eqPositionSelect.appendChild(opt);
            }
        }
    }

    function savePWConfig() {
        var el = document.getElementById('pw_equipment_type');
        if (el) pwConfig.equipmentType = el.value;
        var ch = document.getElementById('pw_channel_number');
        if (ch) pwConfig.channelNumber = ch.value;
        var is = document.getElementById('pw_init_status');
        if (is) pwConfig.initStatus = is.value;
        var eq = document.getElementById('pw_eq_position');
        if (eq) pwConfig.eqPosition = eq.value;
        var disp = document.getElementById('c_pw_disp');
        if (disp) { disp.innerText = '√ 已配置'; disp.classList.add('selected'); }
        global.autoSaveConfig();
        closePWConfig();
    }

    function showIgnitionConfig() {
        var wt = document.getElementById('ignition_waitTime');
        if (wt) wt.value = ignConfig.waitTime || '';
        var cur = document.getElementById('ignition_current');
        if (cur) cur.value = ignConfig.current || '';
        var modal = document.getElementById('ignitionConfigModal');
        if (modal) modal.style.display = 'flex';
    }

    function closeIgnitionConfig() {
        var modal = document.getElementById('ignitionConfigModal');
        if (modal) modal.style.display = 'none';
    }

    function saveIgnitionConfig() {
        var wt = document.getElementById('ignition_waitTime');
        var cur = document.getElementById('ignition_current');
        var wtVal = wt ? (wt.value || '').trim() : '';
        var curVal = cur ? (cur.value || '').trim() : '';
        // 如果用户没有输入值，但点击了“确定”，则使用占位符作为默认选择值写入配置
        if (!wtVal && wt && wt.placeholder) {
            wtVal = wt.placeholder;
        }
        if (!curVal && cur && cur.placeholder) {
            curVal = cur.placeholder;
        }
        ignConfig.waitTime = wtVal;
        ignConfig.current = curVal;
        var disp = document.getElementById('c_ignition_disp');
        if (disp) {
            if (ignConfig.waitTime || ignConfig.current) {
                disp.innerText = '√ 已配置';
                disp.classList.add('selected');
            } else {
                disp.innerText = '未配置';
                disp.classList.remove('selected');
            }
        }
        global.autoSaveConfig();
        closeIgnitionConfig();
    }

    function toggleLoginPasswordVisible() {
        var input = document.getElementById('login_password');
        var btn = document.getElementById('login_password_toggle');
        if (!input || !btn) return;
        if (input.type === 'password') {
            input.type = 'text';
            btn.textContent = '隐藏';
            btn.title = '点击隐藏密码';
        } else {
            input.type = 'password';
            btn.textContent = '●';
            btn.title = '点击显示密码';
        }
    }

    function showLoginConfig() {
        var u = document.getElementById('login_username');
        if (u) u.value = loginConfig.username || '';
        var p = document.getElementById('login_password');
        if (p) {
            p.value = loginConfig.password || '';
            p.type = 'password';
        }
        var btn = document.getElementById('login_password_toggle');
        if (btn) { btn.textContent = '●'; btn.title = '点击显示密码'; }
        var modal = document.getElementById('loginConfigModal');
        if (modal) modal.style.display = 'flex';
    }

    function closeLoginConfig() {
        var modal = document.getElementById('loginConfigModal');
        if (modal) modal.style.display = 'none';
    }

    function saveLoginConfig() {
        var u = document.getElementById('login_username');
        loginConfig.username = u ? u.value.trim() || '' : '';
        var p = document.getElementById('login_password');
        loginConfig.password = p ? p.value.trim() || '' : '';
        var disp = document.getElementById('c_login_disp');
        if (disp) {
            disp.innerText = (loginConfig.username || loginConfig.password) ? '√ 已配置' : '未配置';
            if (loginConfig.username || loginConfig.password) disp.classList.add('selected'); else disp.classList.remove('selected');
        }
        global.autoSaveConfig();
        closeLoginConfig();
    }

    global.toggleCheck = toggleCheck;
    global.selectPath = selectPath;
    global.autoParseAndRender = autoParseAndRender;
    global.toggleTreeExpand = toggleTreeExpand;
    global.onParentCheckboxChange = onParentCheckboxChange;
    global.onSheetCheckboxChange = onSheetCheckboxChange;
    global.toggleCaseSelection = toggleCaseSelection;
    global.parseFileStructure = parseFileStructure;
    global.closeParseFileModal = closeParseFileModal;
    global.handleRadioChange = handleRadioChange;
    global.run = run;
    global.runCentral = runCentral;
    global.runDTC = runDTC;
    global.showUartCommConfig = showUartCommConfig;
    global.closeUartCommConfig = closeUartCommConfig;
    global.saveUartCommConfig = saveUartCommConfig;
    global.setupSelectWithCustom = setupSelectWithCustom;
    global.getSelectWithCustomValue = getSelectWithCustomValue;
    global.onSelectWithCustomChange = onSelectWithCustomChange;
    global.showPowerConfig = showPowerConfig;
    global.closePowerConfig = closePowerConfig;
    global.savePowerConfig = savePowerConfig;
    global.showRelayConfig = showRelayConfig;
    global.closeRelayConfig = closeRelayConfig;
    global.addRelay = addRelay;
    global.removeRelay = removeRelay;
    global.renderRelayList = renderRelayList;
    global.updateRelayConfig = updateRelayConfig;
    global.updateRelayType = updateRelayType;
    global.setCoilMode = setCoilMode;
    global.applyCoilStatus = applyCoilStatus;
    global.saveRelayConfig = saveRelayConfig;
    global.loadSerialPortsForRelay = loadSerialPortsForRelay;
    global.handleRelaySelectChange = handleRelaySelectChange;
    global.handleRelayCustomInputChange = handleRelayCustomInputChange;
    global.autoParseDtcIoSheets = autoParseDtcIoSheets;
    global.showIGConfig = showIGConfig;
    global.closeIGConfig = closeIGConfig;
    global.updateIGConfig = updateIGConfig;
    global.saveIGConfig = saveIGConfig;
    global.showPWConfig = showPWConfig;
    global.closePWConfig = closePWConfig;
    global.updatePWConfig = updatePWConfig;
    global.savePWConfig = savePWConfig;
    global.showIgnitionConfig = showIgnitionConfig;
    global.closeIgnitionConfig = closeIgnitionConfig;
    global.saveIgnitionConfig = saveIgnitionConfig;
    global.toggleLoginPasswordVisible = toggleLoginPasswordVisible;
    global.showLoginConfig = showLoginConfig;
    global.closeLoginConfig = closeLoginConfig;
    global.saveLoginConfig = saveLoginConfig;
    global.clearPath = clearPath;
    global.clearUartCommConfig = clearUartCommConfig;
    global.clearPowerConfig = clearPowerConfig;
    global.clearRelayConfigState = clearRelayConfigState;
    global.clearIGConfigState = clearIGConfigState;
    global.clearPWConfigState = clearPWConfigState;
    global.clearIgnitionConfigState = clearIgnitionConfigState;
    global.clearLoginConfigState = clearLoginConfigState;
})(typeof window !== 'undefined' ? window : this);
