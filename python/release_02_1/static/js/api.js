/**
 * api.js - 所有与后端的 fetch 请求封装
 * 供 config_handler.js 与 ui_controls.js 调用
 */
(function (global) {
    'use strict';

    const API = {
        selectFile: function (fileType) {
            return fetch('/api/select_file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_type: fileType })
            }).then(function (res) { return res.json(); });
        },

        parseFileStructure: function (path) {
            return fetch('/api/parse_file_structure', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path })
            }).then(function (res) { return res.json(); });
        },

        autoSaveConfig: function (data) {
            return fetch('/api/auto_save_config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ data: data })
            });
        },

        getFilterOptions: function () {
            return fetch('/api/get_filter_options').then(function (res) { return res.json(); });
        },

        loadConfig: function () {
            return fetch('/api/load_config').then(function (res) { return res.json(); });
        },

        generate: function (payload) {
            return fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(function (res) {
                return res.json().catch(function () { return {}; }).then(function (data) {
                    return { ok: res.ok, status: res.status, data: data };
                });
            });
        },

        generateCentral: function (payload) {
            return fetch('/api/generate_central', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(function (res) {
                return res.json().catch(function () { return {}; }).then(function (data) {
                    return { ok: res.ok, status: res.status, data: data };
                });
            });
        },

        /** 中央域：从 Service_Interface 生成 SOA_StartSetserver.cin */
        soaSetserverCin: function (payload) {
            return fetch('/api/central/soa_setserver_cin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(function (res) {
                return res.json().catch(function () { return {}; }).then(function (data) {
                    return { ok: res.ok, status: res.status, data: data };
                });
            });
        },

        generateDTC: function (payload) {
            return fetch('/api/generate_dtc', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(function (res) {
                return res.json().catch(function () { return {}; }).then(function (data) {
                    return { ok: res.ok, status: res.status, data: data };
                });
            });
        },

        savePreset: function (data, currentTab) {
            return fetch('/api/save_preset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ data: data, current_tab: currentTab })
            }).then(function (res) { return res.json(); });
        },

        importPreset: function (currentTab) {
            return fetch('/api/import_preset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ current_tab: currentTab })
            }).then(function (res) {
                var ct = (res.headers.get('Content-Type') || '').toLowerCase();
                if (ct.indexOf('application/json') !== -1) {
                    return res.json();
                }
                return res.text().then(function (text) {
                    if (res.ok) {
                        try { return JSON.parse(text); } catch (e) {
                            return { success: false, message: '服务器返回了非 JSON 内容' };
                        }
                    }
                    return { success: false, message: '导入失败（' + res.status + '）：请确认后端服务正常并已注册 /api/import_preset' };
                });
            });
        },

        getSerialPorts: function () {
            return fetch('/api/get_serial_ports').then(function (res) { return res.json(); });
        },

        heartbeat: function () {
            // 心跳：用于检测后端是否仍存活。失败时通知前端进行“后端已关闭”处理。
            return fetch('/api/heartbeat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
                keepalive: true
            }).then(function (res) {
                if (!res.ok) {
                    throw new Error('心跳返回非 200 状态: ' + res.status);
                }
                return res;
            }).catch(function (err) {
                console.log('心跳请求失败，可能后端已关闭: ', err && err.message ? err.message : err);
                if (typeof global.handleBackendDown === 'function') {
                    try { global.handleBackendDown(); } catch (e) { console.error(e); }
                }
            });
        }
    };

    global.API = API;
})(typeof window !== 'undefined' ? window : this);
