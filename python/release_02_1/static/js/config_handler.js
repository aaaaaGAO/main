/**
 * config_handler.js - 配置恢复、自动保存、预设导入导出
 * 依赖: api.js (window.API)
 * 被 ui_controls.js 依赖: initFromConfig, applyImportedState 会调用 autoParseAndRender
 */
(function (global) {
    'use strict';

    var selection = {};
    var configLoaded = false;

    var uartCommConfig = {
        port: '',
        baudrate: '115200',
        dataBits: '8',
        stopBits: '1',
        kHANDSHAKE_DISABLED: '0',
        parity: '0',
        frameTypeIs8676: '0'
    };
    var powerConfig = {
        port: '',
        baudrate: '115200',
        dataBits: '8',
        stopBits: '1',
        kHANDSHAKE_DISABLED: '0',
        parity: '0',
        channel: '1'
    };
    var relayConfigs = [];
    var relayCounter = 1;
    var relayCoilModes = {};
    /** UI 已隐藏的继电器字段：写入主配置/API 前剥离（保留 relayID，便于后端判断与后续扩展） */
    var RELAY_KEYS_STRIPPED_FOR_SAVE = ['dataBits', 'stopBits', 'kHANDSHAKE_DISABLED', 'parity'];

    function relayFromPersisted(r) {
        var o = {};
        if (!r || typeof r !== 'object') return o;
        Object.keys(r).forEach(function (k) {
            if (RELAY_KEYS_STRIPPED_FOR_SAVE.indexOf(k) === -1) o[k] = r[k];
        });
        return o;
    }

    function relayConfigsForSave(list) {
        if (!Array.isArray(list)) return list;
        return list.map(function (r) { return relayFromPersisted(r); });
    }
    // IG / PW / 点火循环不再带默认值，避免在用户未配置时写入当前主配置文件
    var igConfig = { equipmentType: '', channelNumber: '', initStatus: '', eqPosition: '' };
    var pwConfig = { equipmentType: '', channelNumber: '', initStatus: '', eqPosition: '' };
    var ignConfig = { waitTime: '', current: '' };
    var loginConfig = { username: '', password: '' };

    function getChecks(id) {
        var inputs = Array.from(document.querySelectorAll('#${id} input'.replace('${id}', id)));
        var isRadioGroup = id.indexOf('platform') !== -1 || id.indexOf('model') !== -1;
        var checked = inputs.filter(function (i) { return i.checked; }).map(function (i) { return i.value; });
        if (isRadioGroup) {
            return checked.length > 0 ? checked[0] : '';
        }
        // 仅「未勾选任何项」表示不过滤（与后端 parse_* 中 ALL/空 一致）。
        // 若「全选」也发 ALL，后端会当做不过滤，表中多出筛选项（如等级 F）仍会生成。
        return checked.length === 0 ? 'ALL' : checked.join(',');
    }

    function getSelectedSheets(containerId) {
        var container = document.getElementById(containerId);
        if (!container) return '';
        var inputs = container.querySelectorAll('input.sheet-checkbox:checked');
        var parts = [];
        inputs.forEach(function (inp) {
            var table = inp.getAttribute('data-table') || '';
            var sheet = inp.value || inp.getAttribute('data-sheet') || '';
            if (table && sheet) parts.push(table + '|' + sheet);
        });
        return parts.join(',');
    }

    function collectCurrentState() {
        var state = {
            can_input: selection.can_input || '',
            can_input_type: selection.can_input_type || 'file',
            selected_sheets: getSelectedSheets('can_select_cases_group'),
            io_excel: selection.io_excel || '',
            didconfig_excel: selection.didconfig_excel || '',
            didinfo_excel: selection.didinfo_excel || '',
            cin_excel: selection.cin_excel || '',
            srv_excel: selection.srv_excel || '',
            out_root: document.getElementById('out_root') ? document.getElementById('out_root').value || '' : '',
            levels: getChecks('level_group'),
            platforms: getChecks('platform_group'),
            models: getChecks('model_group'),
            target_versions: getChecks('target_version_group'),
            uds_ecu_qualifier: document.getElementById('uds_ecu_qualifier') ? document.getElementById('uds_ecu_qualifier').value : '',
            log_level: document.getElementById('log_level') ? document.getElementById('log_level').value : 'info',
            c_input: selection.c_input || '',
            c_input_type: selection.c_input_type || 'file',
            c_selected_sheets: getSelectedSheets('c_select_cases_group'),
            c_uart: selection.c_uart || '',
            c_uart_comm: uartCommConfig,
            c_srv: selection.c_srv || '',
            c_pwr: powerConfig,
            c_rly: relayConfigsForSave(relayConfigs),
            c_ig: igConfig,
            c_pw: pwConfig,
            c_out_root: document.getElementById('c_out_root') ? document.getElementById('c_out_root').value || '' : '',
            c_ign_waitTime: ignConfig.waitTime || '',
            c_ign_current: ignConfig.current || '',
            c_login_username: loginConfig.username || '',
            c_login_password: loginConfig.password || '',
            c_levels: getChecks('c_level_group'),
            c_platforms: getChecks('c_platform_group'),
            c_models: getChecks('c_model_group'),
            c_target_versions: getChecks('c_target_version_group'),
            c_uds_ecu_qualifier: document.getElementById('c_uds_ecu_qualifier') ? document.getElementById('c_uds_ecu_qualifier').value : '',
            c_log_level: document.getElementById('c_log_level') ? document.getElementById('c_log_level').value : 'info',
            d_input: selection.d_input || '',
            d_input_type: selection.d_input_type || 'file',
            d_selected_sheets: getSelectedSheets('d_select_cases_group'),
            d_log_level: document.getElementById('d_log_level') ? document.getElementById('d_log_level').value : 'info',
            d_io_excel: selection.d_io_excel || '',
            d_io_selected_sheets: getDtcIoSelectedSheets(),
            d_didconfig_excel: selection.d_didconfig_excel || '',
            d_didinfo_excel: selection.d_didinfo_excel || '',
            d_cin_excel: selection.d_cin_excel || '',
            d_srv_excel: selection.d_srv_excel || '',
            d_out_root: document.getElementById('d_out_root') ? document.getElementById('d_out_root').value || '' : '',
            d_levels: getChecks('d_level_group'),
            d_platforms: getChecks('d_platform_group'),
            d_models: getChecks('d_model_group'),
            d_target_versions: getChecks('d_target_version_group'),
            d_uds_ecu_qualifier: document.getElementById('d_uds_ecu_qualifier') ? document.getElementById('d_uds_ecu_qualifier').value : ''
        };
        return state;
    }

    function getDtcIoSelectedSheets() {
        var container = document.getElementById('d_io_sheets_container');
        if (!container) return '';
        // 复用用例树的结构，这里直接按 sheet-checkbox 收集
        var inputs = container.querySelectorAll('input.sheet-checkbox:checked');
        if (!inputs || inputs.length === 0) return '';
        var sheets = [];
        inputs.forEach(function (inp) {
            var name = inp.value || inp.getAttribute('data-sheet') || '';
            if (name) sheets.push(name);
        });
        return sheets.join(',');
    }

    function restoreChecks(id, vals) {
        if (!vals) return;
        var inputs = document.querySelectorAll('#' + id + ' input');
        var isRadioGroup = id.indexOf('platform') !== -1 || id.indexOf('model') !== -1;
        var values = Array.isArray(vals) ? vals : (typeof vals === 'string' ? vals.split(',').map(function (v) { return v.trim(); }).filter(function (v) { return v; }) : []);
        if ((id.indexOf('platform') !== -1 || id.indexOf('model') !== -1) && values.length > 0) {
            values = values.filter(function (v) { return v !== 'ALL' && v.trim().toUpperCase() !== 'ALL'; });
            if (values.length === 0) values = null;
        }
        if (!values || values.length === 0 || values.indexOf('ALL') !== -1) {
            if (isRadioGroup) {
                inputs.forEach(function (i) { i.checked = false; });
            } else {
                inputs.forEach(function (i) { i.checked = true; });
            }
        } else {
            if (isRadioGroup) {
                var firstMatch = Array.from(inputs).find(function (i) { return values.indexOf(i.value) !== -1; });
                if (firstMatch) {
                    firstMatch.checked = true;
                    if (global.handleRadioChange) global.handleRadioChange(firstMatch);
                }
            } else {
                inputs.forEach(function (i) { i.checked = values.indexOf(i.value) !== -1; });
            }
        }
    }

    function restoreCaseCheckboxes(containerId, selectedStr) {
        if (!selectedStr || typeof selectedStr !== 'string') return;
        var normalizedSelected = selectedStr.normalize('NFC');
        var set = new Set(normalizedSelected.split(',').map(function (s) { return s.trim(); }).filter(Boolean));
        var container = document.getElementById(containerId);
        if (!container) return;
        var basename = function (p) {
            var s = String(p).replace(/\\/g, '/');
            var i = s.lastIndexOf('/');
            return i >= 0 ? s.slice(i + 1) : s;
        };
        container.querySelectorAll('input.sheet-checkbox').forEach(function (inp) {
            var rawTable = inp.getAttribute('data-table') || '';
            var rawSheet = inp.value || inp.getAttribute('data-sheet') || '';
            var table = rawTable.normalize('NFC');
            var sheet = rawSheet.normalize('NFC');
            if (!table || !sheet) return;
            var key = (table + '|' + sheet).trim();
            var keyBase = (basename(table) + '|' + sheet).trim();
            inp.checked = set.has(key) || set.has(keyBase);
        });
    }

    function renderFilters(groupId, list) {
        var container = document.getElementById(groupId);
        if (!container) return;
        var isRadioGroup = groupId.indexOf('platform') !== -1 || groupId.indexOf('model') !== -1;
        var inputType = isRadioGroup ? 'radio' : 'checkbox';
        var groupName = isRadioGroup ? groupId : '';
        container.innerHTML = list.map(function (item) {
            return '<label class="check-item" title="' + item + '">' +
                '<input type="' + inputType + '" value="' + item + '" name="' + groupName + '" ' + (isRadioGroup ? 'onchange="handleRadioChange(this)"' : 'onchange="autoSaveConfig()"') + '> ' + item +
                '</label>';
        }).join('');
    }

    function renderUdsSelect(selectId, list, selectedVal) {
        var sel = document.getElementById(selectId);
        if (!sel) return;
        var opts = (list || []).map(function (item) {
            return '<option value="' + item + '" ' + (selectedVal === item ? 'selected' : '') + '>' + item + '</option>';
        }).join('');
        sel.innerHTML = opts || '<option value="">—</option>';
    }

    function updateDisplay(dispId, path) {
        var el = document.getElementById(dispId);
        if (el) {
            el.innerText = '√ ' + path.split(/[/\\]/).pop();
            el.classList.add('selected');
        }
    }

    function autoSaveConfig() {
        if (!configLoaded) return;
        try {
            var state = collectCurrentState();
            global.API.autoSaveConfig(state);
        } catch (e) {
            console.error('自动保存配置失败:', e);
        }
    }

    async function initFromConfig() {
        try {
            var filterRes = await global.API.getFilterOptions();
            var fData = filterRes;
            var tabPrefixes = ['', 'c_', 'd_'];
            tabPrefixes.forEach(function (pre) {
                renderFilters(pre + 'level_group', fData.levels);
                renderFilters(pre + 'platform_group', fData.platforms);
                renderFilters(pre + 'model_group', fData.models);
                renderFilters(pre + 'target_version_group', fData.target_versions || []);
            });
            var res = await global.API.loadConfig();
            var result = res;
            if (!result.success) {
                configLoaded = true;
                return;
            }
            var cfg = result.data || {};
            var setPath = function (key, path, dispId) {
                if (!path) return;
                selection[key] = path;
                var el = document.getElementById(dispId);
                if (el) {
                    el.innerText = '√ ' + path.split(/[/\\]/).pop();
                    el.classList.add('selected');
                }
            };
            // 先填充中央域等内存状态（relayConfigs/powerConfig 等），再更新 DOM，避免 restoreChecks/input 触发 change 时 autoSaveConfig 用空 c_rly 覆盖已保存配置
            if (cfg.c_uart_comm && typeof cfg.c_uart_comm === 'object') {
                Object.keys(cfg.c_uart_comm).forEach(function (k) { uartCommConfig[k] = cfg.c_uart_comm[k]; });
            }
            if (cfg.c_pwr && typeof cfg.c_pwr === 'object') {
                Object.keys(cfg.c_pwr).forEach(function (k) { powerConfig[k] = cfg.c_pwr[k]; });
            }
            if (cfg.c_rly && Array.isArray(cfg.c_rly)) {
                relayConfigs.length = 0;
                cfg.c_rly.forEach(function (r, idx) {
                    var o = relayFromPersisted(r);
                    o.id = idx + 1;
                    relayConfigs.push(o);
                });
                relayCounter = relayConfigs.length + 1;
                global.relayCounter = relayCounter;
                relayConfigs.forEach(function (r) { relayCoilModes[r.id] = 'open'; });
            }
            if ((cfg.c_ign_waitTime !== undefined && cfg.c_ign_waitTime !== null) || (cfg.c_ign_current !== undefined && cfg.c_ign_current !== null)) {
                if (cfg.c_ign_waitTime !== undefined && cfg.c_ign_waitTime !== null) ignConfig.waitTime = String(cfg.c_ign_waitTime);
                if (cfg.c_ign_current !== undefined && cfg.c_ign_current !== null) ignConfig.current = String(cfg.c_ign_current);
            }
            if (cfg.c_ig && typeof cfg.c_ig === 'object') {
                Object.keys(cfg.c_ig).forEach(function (k) { igConfig[k] = cfg.c_ig[k]; });
            }
            if (cfg.c_pw && typeof cfg.c_pw === 'object') {
                Object.keys(cfg.c_pw).forEach(function (k) { pwConfig[k] = cfg.c_pw[k]; });
            }
            if (cfg.out_root) {
                var outRootEl = document.getElementById('out_root');
                if (outRootEl) outRootEl.value = cfg.out_root;
            }
            setPath('can_input', cfg.can_input, 'can_disp');
            setPath('io_excel', cfg.io_excel, 'io_disp');
            setPath('didconfig_excel', cfg.didconfig_excel, 'didconfig_disp');
            setPath('didinfo_excel', cfg.didinfo_excel, 'didinfo_disp');
            setPath('cin_excel', cfg.cin_excel, 'cin_disp');
            setPath('srv_excel', cfg.srv_excel, 'srv_disp');
            restoreChecks('level_group', cfg.levels);
            restoreChecks('platform_group', cfg.platforms);
            restoreChecks('model_group', cfg.models);
            restoreChecks('target_version_group', cfg.target_versions);
            renderUdsSelect('uds_ecu_qualifier', fData.uds_ecu_qualifier, cfg.uds_ecu_qualifier);
            var logVal = function (v) {
                return (v && ['info', 'warning', 'error'].indexOf(String(v).toLowerCase()) !== -1) ? String(v).toLowerCase() : 'info';
            };
            var logLevelEl = document.getElementById('log_level');
            if (logLevelEl) logLevelEl.value = logVal(cfg.log_level);
            var cLogLevelEl = document.getElementById('c_log_level');
            if (cLogLevelEl) cLogLevelEl.value = logVal(cfg.c_log_level || cfg.log_level);
            var dLogLevelEl = document.getElementById('d_log_level');
            if (dLogLevelEl) dLogLevelEl.value = logVal(cfg.d_log_level || cfg.log_level);
            if (cfg.c_out_root) {
                var cOutEl = document.getElementById('c_out_root');
                if (cOutEl) cOutEl.value = cfg.c_out_root;
            }
            if ((cfg.c_ign_waitTime !== undefined && cfg.c_ign_waitTime !== null) || (cfg.c_ign_current !== undefined && cfg.c_ign_current !== null)) {
                ignConfig.waitTime = (cfg.c_ign_waitTime !== undefined && cfg.c_ign_waitTime !== null) ? String(cfg.c_ign_waitTime) : ignConfig.waitTime;
                ignConfig.current = (cfg.c_ign_current !== undefined && cfg.c_ign_current !== null) ? String(cfg.c_ign_current) : ignConfig.current;
                var ignDisp = document.getElementById('c_ignition_disp');
                if (ignDisp) {
                    ignDisp.innerText = '√ 已配置';
                    ignDisp.classList.add('selected');
                }
            }
            if (cfg.c_login_username !== undefined || cfg.c_login_password !== undefined) {
                if (cfg.c_login_username !== undefined) loginConfig.username = String(cfg.c_login_username || '');
                if (cfg.c_login_password !== undefined) loginConfig.password = String(cfg.c_login_password || '');
                var loginDisp = document.getElementById('c_login_disp');
                if (loginDisp) {
                    loginDisp.innerText = (loginConfig.username || loginConfig.password) ? '√ 已配置' : '未配置';
                    if (loginConfig.username || loginConfig.password) loginDisp.classList.add('selected'); else loginDisp.classList.remove('selected');
                }
            }
            setPath('c_input', cfg.c_input, 'c_disp');
            setPath('c_uart', cfg.c_uart, 'c_uart_disp');
            if (cfg.c_uart_config && typeof cfg.c_uart_config === 'object') {
                Object.keys(cfg.c_uart_config).forEach(function (k) { uartCommConfig[k] = cfg.c_uart_config[k]; });
                if (uartCommConfig.port) {
                    var uartDisp = document.getElementById('c_uart_config_disp');
                    if (uartDisp) { uartDisp.innerText = '√ 已配置'; uartDisp.classList.add('selected'); }
                }
            }
            if (cfg.c_uart_comm && typeof cfg.c_uart_comm === 'object') {
                Object.keys(cfg.c_uart_comm).forEach(function (k) { uartCommConfig[k] = cfg.c_uart_comm[k]; });
                if (uartCommConfig.port) {
                    var uartCommDisp = document.getElementById('c_uart_comm_disp');
                    if (uartCommDisp) { uartCommDisp.innerText = '√ 已配置'; uartCommDisp.classList.add('selected'); }
                }
            }
            setPath('c_srv', cfg.c_srv, 'c_srv_disp');
            if (cfg.c_pwr && typeof cfg.c_pwr === 'object') {
                Object.keys(cfg.c_pwr).forEach(function (k) { powerConfig[k] = cfg.c_pwr[k]; });
                if (powerConfig.port) {
                    var pwrDisp = document.getElementById('c_pwr_disp');
                    if (pwrDisp) { pwrDisp.innerText = '√ 已配置'; pwrDisp.classList.add('selected'); }
                }
            } else if (cfg.c_pwr) {
                setPath('c_pwr', cfg.c_pwr, 'c_pwr_disp');
            }
            if (cfg.c_rly && Array.isArray(cfg.c_rly)) {
                relayConfigs = cfg.c_rly.map(function (r, idx) {
                    var o = relayFromPersisted(r);
                    o.id = idx + 1;
                    return o;
                });
                relayCounter = relayConfigs.length + 1;
                global.relayCounter = relayCounter;
                relayConfigs.forEach(function (r) { relayCoilModes[r.id] = 'open'; });
                if (relayConfigs.length > 0) {
                    var rlyDisp = document.getElementById('c_rly_disp');
                    if (rlyDisp) { rlyDisp.innerText = '√ 已配置 ' + relayConfigs.length + ' 个继电器'; rlyDisp.classList.add('selected'); }
                }
            } else if (cfg.c_rly) {
                setPath('c_rly', cfg.c_rly, 'c_rly_disp');
            }
            if (cfg.c_ig && typeof cfg.c_ig === 'object') {
                Object.keys(cfg.c_ig).forEach(function (k) { igConfig[k] = cfg.c_ig[k]; });
                if (igConfig.equipmentType) {
                    var igDisp = document.getElementById('c_ig_disp');
                    if (igDisp) { igDisp.innerText = '√ 已配置'; igDisp.classList.add('selected'); }
                }
            }
            if (cfg.c_pw && typeof cfg.c_pw === 'object') {
                Object.keys(cfg.c_pw).forEach(function (k) { pwConfig[k] = cfg.c_pw[k]; });
                if (pwConfig.equipmentType) {
                    var pwDisp = document.getElementById('c_pw_disp');
                    if (pwDisp) { pwDisp.innerText = '√ 已配置'; pwDisp.classList.add('selected'); }
                }
            }
            restoreChecks('c_level_group', cfg.c_levels);
            restoreChecks('c_platform_group', cfg.c_platforms);
            restoreChecks('c_model_group', cfg.c_models);
            restoreChecks('c_target_version_group', cfg.c_target_versions);
            renderUdsSelect('c_uds_ecu_qualifier', fData.uds_ecu_qualifier, cfg.c_uds_ecu_qualifier);
            if (cfg.d_out_root) {
                var dOutEl = document.getElementById('d_out_root');
                if (dOutEl) dOutEl.value = cfg.d_out_root;
            }
            setPath('d_input', cfg.d_input, 'd_disp');
            setPath('d_io_excel', cfg.d_io_excel, 'd_io_disp');
            setPath('d_didconfig_excel', cfg.d_didconfig_excel, 'd_didconfig_disp');
            setPath('d_didinfo_excel', cfg.d_didinfo_excel, 'd_didinfo_disp');
            setPath('d_cin_excel', cfg.d_cin_excel, 'd_cin_disp');
            setPath('d_srv_excel', cfg.d_srv_excel, 'd_srv_disp');
            restoreChecks('d_level_group', cfg.d_levels);
            restoreChecks('d_platform_group', cfg.d_platforms);
            restoreChecks('d_model_group', cfg.d_models);
            restoreChecks('d_target_version_group', cfg.d_target_versions);
            renderUdsSelect('d_uds_ecu_qualifier', fData.uds_ecu_qualifier, cfg.d_uds_ecu_qualifier);
            if (cfg.d_io_excel && global.autoParseDtcIoSheets) {
                await global.autoParseDtcIoSheets(cfg.d_io_selected_sheets);
            }
            if (cfg.can_input && global.autoParseAndRender) {
                await global.autoParseAndRender('can_input', 'can_select_cases_group', cfg.selected_sheets);
            }
            if (cfg.c_input && global.autoParseAndRender) {
                await global.autoParseAndRender('c_input', 'c_select_cases_group', cfg.c_selected_sheets);
            }
            if (cfg.d_input && global.autoParseAndRender) {
                await global.autoParseAndRender('d_input', 'd_select_cases_group', cfg.d_selected_sheets);
            }
            configLoaded = true;
        } catch (e) {
            console.error('初始化失败:', e);
            configLoaded = true;
        }
    }

    async function applyImportedState(data) {
        if (data.can_input) {
            selection.can_input = data.can_input;
            selection.can_input_type = data.can_input_type || 'file';
            updateDisplay('can_disp', data.can_input);
        }
        if (data.io_excel) {
            selection.io_excel = data.io_excel;
            updateDisplay('io_disp', data.io_excel);
        }
        if (data.didconfig_excel) {
            selection.didconfig_excel = data.didconfig_excel;
            updateDisplay('didconfig_disp', data.didconfig_excel);
        }
        if (data.didinfo_excel) {
            selection.didinfo_excel = data.didinfo_excel;
            updateDisplay('didinfo_disp', data.didinfo_excel);
        }
        if (data.cin_excel) {
            selection.cin_excel = data.cin_excel;
            updateDisplay('cin_disp', data.cin_excel);
        }
        if (data.srv_excel) {
            selection.srv_excel = data.srv_excel;
            updateDisplay('srv_disp', data.srv_excel);
        }
        if (data.out_root) {
            var outRootEl = document.getElementById('out_root');
            if (outRootEl) outRootEl.value = data.out_root;
        }
        restoreChecks('level_group', data.levels);
        restoreChecks('platform_group', data.platforms);
        restoreChecks('model_group', data.models);
        restoreChecks('target_version_group', data.target_versions);
        if (data.log_level) {
            var logLevelEl = document.getElementById('log_level');
            if (logLevelEl) logLevelEl.value = data.log_level;
        }
        if (data.uds_ecu_qualifier) {
            var udsEl = document.getElementById('uds_ecu_qualifier');
            if (udsEl) udsEl.value = data.uds_ecu_qualifier;
        }
        if (data.can_input && global.autoParseAndRender) {
            await global.autoParseAndRender('can_input', 'can_select_cases_group', data.selected_sheets);
        }
        if (data.c_input) {
            selection.c_input = data.c_input;
            selection.c_input_type = data.c_input_type || 'file';
            updateDisplay('c_disp', data.c_input);
            await global.autoParseAndRender('c_input', 'c_select_cases_group', data.c_selected_sheets);
        }
        if (data.c_uart) {
            selection.c_uart = data.c_uart;
            updateDisplay('c_uart_disp', data.c_uart);
        }
        if (data.c_srv) {
            selection.c_srv = data.c_srv;
            updateDisplay('c_srv_disp', data.c_srv);
        }
        if (data.c_pwr) {
            if (typeof data.c_pwr === 'object') {
                Object.keys(data.c_pwr).forEach(function (k) { powerConfig[k] = data.c_pwr[k]; });
                if (powerConfig.port) {
                    var pwrDisp = document.getElementById('c_pwr_disp');
                    if (pwrDisp) { pwrDisp.innerText = '√ 已配置'; pwrDisp.classList.add('selected'); }
                }
            } else {
                selection.c_pwr = data.c_pwr;
                updateDisplay('c_pwr_disp', data.c_pwr);
            }
        }
        if (data.c_rly) {
            if (Array.isArray(data.c_rly)) {
                relayConfigs = data.c_rly.map(function (r, idx) {
                    var o = relayFromPersisted(r);
                    o.id = idx + 1;
                    return o;
                });
                relayCounter = relayConfigs.length + 1;
                global.relayCounter = relayCounter;
                relayConfigs.forEach(function (r) { relayCoilModes[r.id] = 'open'; });
                if (relayConfigs.length > 0) {
                    var rlyDisp = document.getElementById('c_rly_disp');
                    if (rlyDisp) { rlyDisp.innerText = '√ 已配置 ' + relayConfigs.length + ' 个继电器'; rlyDisp.classList.add('selected'); }
                }
            } else {
                selection.c_rly = data.c_rly;
                updateDisplay('c_rly_disp', data.c_rly);
            }
        }
        if (data.c_ig && typeof data.c_ig === 'object') {
            Object.keys(data.c_ig).forEach(function (k) { igConfig[k] = data.c_ig[k]; });
            if (igConfig.equipmentType) {
                var igDisp = document.getElementById('c_ig_disp');
                if (igDisp) { igDisp.innerText = '√ 已配置'; igDisp.classList.add('selected'); }
            }
        }
        if (data.c_pw && typeof data.c_pw === 'object') {
            Object.keys(data.c_pw).forEach(function (k) { pwConfig[k] = data.c_pw[k]; });
            if (pwConfig.equipmentType) {
                var pwDisp = document.getElementById('c_pw_disp');
                if (pwDisp) { pwDisp.innerText = '√ 已配置'; pwDisp.classList.add('selected'); }
            }
        }
        if (data.c_out_root) {
            var cOutEl = document.getElementById('c_out_root');
            if (cOutEl) cOutEl.value = data.c_out_root;
        }
        if (data.c_ign_waitTime !== undefined && data.c_ign_waitTime !== null) ignConfig.waitTime = String(data.c_ign_waitTime);
        if (data.c_ign_current !== undefined && data.c_ign_current !== null) ignConfig.current = String(data.c_ign_current);
        if (ignConfig.waitTime || ignConfig.current) {
            var ignDisp = document.getElementById('c_ignition_disp');
            if (ignDisp) { ignDisp.innerText = '√ 已配置'; ignDisp.classList.add('selected'); }
        }
        if (data.c_login_username !== undefined) loginConfig.username = String(data.c_login_username || '');
        if (data.c_login_password !== undefined) loginConfig.password = String(data.c_login_password || '');
        var loginDisp = document.getElementById('c_login_disp');
        if (loginDisp) {
            loginDisp.innerText = (loginConfig.username || loginConfig.password) ? '√ 已配置' : '未配置';
            if (loginConfig.username || loginConfig.password) loginDisp.classList.add('selected'); else loginDisp.classList.remove('selected');
        }
        restoreChecks('c_level_group', data.c_levels);
        restoreChecks('c_platform_group', data.c_platforms);
        restoreChecks('c_model_group', data.c_models);
        restoreChecks('c_target_version_group', data.c_target_versions);
        if (data.c_uds_ecu_qualifier) {
            var cUdsEl = document.getElementById('c_uds_ecu_qualifier');
            if (cUdsEl) cUdsEl.value = data.c_uds_ecu_qualifier;
        }
        var cLog = data.c_log_level || data.log_level;
        if (cLog) {
            var cLogEl = document.getElementById('c_log_level');
            if (cLogEl) cLogEl.value = cLog;
        }
        var dIn = data.d_input || data.can_input;
        if (dIn) {
            selection.d_input = dIn;
            selection.d_input_type = data.d_input_type || data.can_input_type || 'file';
            updateDisplay('d_disp', dIn);
            await global.autoParseAndRender('d_input', 'd_select_cases_group', data.d_selected_sheets || data.selected_sheets);
        }
        var dOut = data.d_out_root || data.out_root;
        if (dOut) {
            var dOutEl = document.getElementById('d_out_root');
            if (dOutEl) dOutEl.value = dOut;
        }
        var dIo = data.d_io_excel || data.io_excel;
        if (dIo) {
            selection.d_io_excel = dIo;
            updateDisplay('d_io_disp', dIo);
            // 导入预设时同步还原 DTC IO_Mapping 的 Sheet 勾选状态：
            // - 路径：d_io_excel / io_excel
            // - Sheet 勾选：d_io_selected_sheets（如 "LZCU_CEA1.0,RZCU_CEA1.0"）
            //   传入 autoParseDtcIoSheets 作为 initialSelectedSheets，内部会根据文件名拼成 table|sheet 形式并做还原
            if (global.autoParseDtcIoSheets) {
                await global.autoParseDtcIoSheets(data.d_io_selected_sheets || '');
            }
        }
        var dDidCfg = data.d_didconfig_excel || data.didconfig_excel;
        if (dDidCfg) {
            selection.d_didconfig_excel = dDidCfg;
            updateDisplay('d_didconfig_disp', dDidCfg);
        }
        var dDidInfo = data.d_didinfo_excel || data.didinfo_excel;
        if (dDidInfo) {
            selection.d_didinfo_excel = dDidInfo;
            updateDisplay('d_didinfo_disp', dDidInfo);
        }
        var dCin = data.d_cin_excel || data.cin_excel;
        if (dCin) {
            selection.d_cin_excel = dCin;
            updateDisplay('d_cin_disp', dCin);
        }
        var dSrv = data.d_srv_excel || data.srv_excel;
        if (dSrv) {
            selection.d_srv_excel = dSrv;
            updateDisplay('d_srv_disp', dSrv);
        }
        restoreChecks('d_level_group', data.d_levels || data.levels);
        restoreChecks('d_platform_group', data.d_platforms || data.platforms);
        restoreChecks('d_model_group', data.d_models || data.models);
        restoreChecks('d_target_version_group', data.d_target_versions || data.target_versions);
        if (data.d_uds_ecu_qualifier) {
            var dUdsEl = document.getElementById('d_uds_ecu_qualifier');
            if (dUdsEl) dUdsEl.value = data.d_uds_ecu_qualifier;
        }
        var dLog = data.d_log_level || data.log_level;
        if (dLog) {
            var dLogEl = document.getElementById('d_log_level');
            if (dLogEl) dLogEl.value = dLog;
        }
    }

    async function saveConfigPreset() {
        var state = collectCurrentState();
        var activeTab = document.querySelector('.tab-content.active');
        var currentTab = activeTab ? activeTab.id : '';
        try {
            var result = await global.API.savePreset(state, currentTab);
            if (result.success) {
                alert('✅ 配置保存成功！\n保存位置: ' + result.filepath);
            } else {
                if (result.message !== '用户取消了保存') {
                    alert('❌ 保存失败: ' + result.message);
                }
            }
        } catch (e) {
            alert('❌ 保存失败: ' + e.message);
        }
    }

    async function importConfigPreset() {
        var activeTab = document.querySelector('.tab-content.active');
        var currentTab = activeTab ? activeTab.id : '';
        try {
            var result = await global.API.importPreset(currentTab);
            if (!result.success) {
                if (result.message !== '用户取消了选择') {
                    alert('❌ 导入失败: ' + result.message);
                }
                return;
            }
            await applyImportedState(result.data);
            alert('✅ 配置导入成功！');
        } catch (e) {
            alert('❌ 导入失败: ' + e.message);
        }
    }

    global.selection = selection;
    Object.defineProperty(global, 'configLoaded', {
        get: function () { return configLoaded; },
        set: function (v) { configLoaded = v; },
        configurable: true
    });
    global.uartCommConfig = uartCommConfig;
    global.powerConfig = powerConfig;
    global.relayConfigs = relayConfigs;
    global.relayCounter = relayCounter;
    global.relayCoilModes = relayCoilModes;
    global.igConfig = igConfig;
    global.pwConfig = pwConfig;
    global.ignConfig = ignConfig;
    global.loginConfig = loginConfig;
    global.getChecks = getChecks;
    global.getSelectedSheets = getSelectedSheets;
    global.getDtcIoSelectedSheets = getDtcIoSelectedSheets;
    global.collectCurrentState = collectCurrentState;
    global.relayConfigsForSave = relayConfigsForSave;
    global.restoreChecks = restoreChecks;
    global.restoreCaseCheckboxes = restoreCaseCheckboxes;
    global.renderFilters = renderFilters;
    global.renderUdsSelect = renderUdsSelect;
    global.updateDisplay = updateDisplay;
    global.autoSaveConfig = autoSaveConfig;
    global.initFromConfig = initFromConfig;
    global.applyImportedState = applyImportedState;
    global.saveConfigPreset = saveConfigPreset;
    global.importConfigPreset = importConfigPreset;
})(typeof window !== 'undefined' ? window : this);
