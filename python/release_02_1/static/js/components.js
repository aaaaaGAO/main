/**
 * components.js - 纯 UI 渲染组件
 * 不包含业务逻辑，只负责返回 HTML 字符串
 */
(function (global) {
    'use strict';

    function esc(v) {
        return String(v).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    var UIComponents = {
        renderMessage: function (msg, type) {
            var cls = 'ui-message';
            if (type === 'error') cls += ' ui-message--error';
            else if (type === 'center') cls += ' ui-message--center ui-message--muted';
            else cls += ' ui-message--muted';
            return '<p class="' + cls + '">' + esc(msg) + '</p>';
        },

        renderCaseSelectCheckboxes: function (items, containerId) {
            if (!items || items.length === 0) {
                return UIComponents.renderMessage('未找到可解析的文件（支持 Excel、CAN、XML）', 'muted');
            }
            var filterRevHist = function (arr) {
                return (arr || []).filter(function (s) {
                    var name = String(s || '').trim().toLowerCase();
                    return !(name === 'rev.hist' || name === '变更记录' || name === '变更历史');
                });
            };
            var safeContainerId = esc(containerId);
            var html = '<div class="case-tree-list">';
            items.forEach(function (item, fileIdx) {
                var tableName = item.relpath ? item.relpath : item.filename;
                var tableLabel = (item.relpath && item.relpath !== item.filename) ? item.relpath : item.filename;
                var blockId = 'case_block_' + Date.now() + '_' + fileIdx;
                var hasChildren = !item.error && (
                    (item.type === 'excel' && item.sheets && item.sheets.length) ||
                    (item.type === 'can' && item.testcases && item.testcases.length) ||
                    (item.type === 'xml' && ((item.testgroups && item.testgroups.length) || (item.capltestcases && item.capltestcases.length)))
                );
                html += '<div class="case-table-block case-tree-parent' + (hasChildren ? '' : ' no-expand') + '" id="' + blockId + '" data-container-id="' + safeContainerId + '">';
                html += '<div class="case-parent-row">';
                html += '<span class="case-expand-btn" onclick="toggleTreeExpand(\'' + blockId + '\')" title="展开/收起">';
                html += '<span class="icon-collapsed">▶</span><span class="icon-expanded">▼</span></span>';
                html += '<label><input type="checkbox" class="parent-checkbox" data-parent-block="' + blockId + '" onchange="onParentCheckboxChange(this)"><span>📄 ' + esc(tableLabel) + '</span></label>';
                html += '</div>';
                if (item.error) {
                    html += '<div class="case-tree-children case-tree-children--error">' + esc(item.error) + '</div>';
                } else {
                    var sheets = [];
                    if (item.type === 'excel' && item.sheets && item.sheets.length) {
                        sheets = filterRevHist(item.sheets).map(function (s) { return { name: s, type: 'Sheet' }; });
                    } else if (item.type === 'can' && item.testcases && item.testcases.length) {
                        item.testcases.forEach(function (s) { sheets.push({ name: s, type: 'Testcase' }); });
                    } else if (item.type === 'xml') {
                        if (item.testgroups && item.testgroups.length) {
                            item.testgroups.forEach(function (s) { sheets.push({ name: s, type: 'Testgroup' }); });
                        }
                        if (item.capltestcases && item.capltestcases.length) {
                            item.capltestcases.forEach(function (s) { sheets.push({ name: s, type: 'Capltestcase' }); });
                        }
                    }
                    if (sheets.length > 0) {
                        html += '<div class="case-tree-children"><div class="case-sheet-grid">';
                        sheets.forEach(function (s) {
                            var safeName = esc(s.name);
                            var safeTable = esc(tableName);
                            html += '<label class="check-item" title="' + safeName + '"><input type="checkbox" class="sheet-checkbox" value="' + safeName + '" data-table="' + safeTable + '" data-sheet="' + safeName + '" data-parent-block="' + blockId + '" onchange="onSheetCheckboxChange(this)"> ' + esc(s.name) + '</label>';
                        });
                        html += '</div></div>';
                    } else {
                        html += '<div class="case-tree-children case-tree-children--empty">无解析结果</div>';
                    }
                }
                html += '</div>';
            });
            html += '</div>';
            return html;
        },

        renderParseResult: function (items) {
            if (!items || items.length === 0) {
                return UIComponents.renderMessage('未找到可解析的文件（支持 Excel、CAN、XML）', 'muted');
            }
            var html = '';
            items.forEach(function (item) {
                var rel = item.relpath ? ' <span class="parse-item__relpath">' + esc(item.relpath) + '</span>' : '';
                html += '<div class="parse-item">';
                html += '<div class="parse-item__title">📄 ' + esc(item.filename) + rel + '</div>';
                if (item.error) {
                    html += '<div class="parse-item__error">' + esc(item.error) + '</div>';
                } else if (item.type === 'excel' && item.sheets && item.sheets.length) {
                    html += '<div class="parse-item__label">Sheet 名 (' + item.sheets.length + ' 个):</div>';
                    html += '<div class="parse-item__tags">';
                    item.sheets.forEach(function (s) {
                        html += '<span class="parse-tag parse-tag--sheet">' + esc(s) + '</span>';
                    });
                    html += '</div>';
                } else if (item.type === 'can' && item.testcases && item.testcases.length) {
                    html += '<div class="parse-item__label">Testcase 名 (' + item.testcases.length + ' 个):</div>';
                    html += '<div class="parse-item__tags parse-item__tags--scroll">';
                    item.testcases.slice(0, 50).forEach(function (s) {
                        html += '<span class="parse-tag parse-tag--can">' + esc(s) + '</span>';
                    });
                    if (item.testcases.length > 50) {
                        html += '<span class="parse-item__more">... 共 ' + item.testcases.length + ' 个</span>';
                    }
                    html += '</div>';
                } else if (item.type === 'xml') {
                    if (item.testgroups && item.testgroups.length) {
                        html += '<div class="parse-item__label">Testgroup (' + item.testgroups.length + ' 个):</div>';
                        html += '<div class="parse-item__tags">';
                        item.testgroups.slice(0, 20).forEach(function (s) {
                            html += '<span class="parse-tag parse-tag--xml-group">' + esc(s) + '</span>';
                        });
                        if (item.testgroups.length > 20) html += '<span class="parse-item__more">... 共 ' + item.testgroups.length + ' 个</span>';
                        html += '</div>';
                    }
                    if (item.capltestcases && item.capltestcases.length) {
                        html += '<div class="parse-item__label" style="margin-top:8px;">Capltestcase (' + item.capltestcases.length + ' 个):</div>';
                        html += '<div class="parse-item__tags parse-item__tags--scroll-sm">';
                        item.capltestcases.slice(0, 30).forEach(function (s) {
                            html += '<span class="parse-tag parse-tag--xml-case">' + esc(s) + '</span>';
                        });
                        if (item.capltestcases.length > 30) html += '<span class="parse-item__more">... 共 ' + item.capltestcases.length + ' 个</span>';
                        html += '</div>';
                    }
                } else {
                    html += '<div class="parse-item__empty">无解析结果</div>';
                }
                html += '</div>';
            });
            return html;
        },

        renderRelayListHtml: function (relayConfigs, relayCoilModes) {
            if (!relayConfigs || relayConfigs.length === 0) {
                return UIComponents.renderMessage('暂无继电器配置，点击"添加继电器"开始配置', 'center');
            }
            var baudStandard = ['9600', '19200', '38400', '57600', '115200'];
            var typeStandard = ['RS232_8', 'RS232_16', 'RS232_24', 'RS232_32', 'RS232_64'];
            return relayConfigs.map(function (relay, index) {
                var relayNumber = index + 1;
                var coilMode = relayCoilModes[relay.id] || 'open';
                var baudIsStandard = baudStandard.indexOf(relay.baudrate) !== -1;
                var openBtnCls = coilMode === 'open' ? 'coil-mode-btn--open-active' : 'coil-mode-btn--open-inactive';
                var closeBtnCls = coilMode === 'close' ? 'coil-mode-btn--close-active' : 'coil-mode-btn--close-inactive';
                var customDisplay = (!baudIsStandard && relay.baudrate) ? 'block' : 'none';
                var html = '<div class="relay-card relay-item">';
                html += '<div class="relay-card__header">';
                html += '<h3 class="relay-card__title">继电器 ' + relayNumber + '</h3>';
                html += '<button class="btn relay-card__delete" onclick="removeRelay(' + relay.id + ')">删除</button></div>';
                html += '<div class="grid-2-col">';
                html += '<div><label class="form-label">端口号 (port):</label>';
                html += '<select class="relay-port-select form-control" data-relay-id="' + relay.id + '" onchange="updateRelayConfig(' + relay.id + ', \'port\', this.value)"></select></div>';
                html += '<div><label class="form-label">波特率 (baudrate):</label>';
                html += '<select id="relay-baudrate-' + relay.id + '" class="form-control" onchange="handleRelaySelectChange(' + relay.id + ', \'baudrate\', this)">';
                baudStandard.forEach(function (b) {
                    html += '<option value="' + b + '"' + (baudIsStandard && relay.baudrate === b ? ' selected' : '') + '>' + b + '</option>';
                });
                html += '<option value="__custom__"' + (!baudIsStandard && relay.baudrate ? ' selected' : '') + '>其他（自定义）</option>';
                html += '</select>';
                html += '<input type="number" id="relay-baudrate-custom-' + relay.id + '" class="form-control-custom" value="' + (!baudIsStandard ? (relay.baudrate || '') : '') + '" placeholder="自定义波特率" style="display:' + customDisplay + ';" onchange="handleRelayCustomInputChange(' + relay.id + ', \'baudrate\', this.value)"></div>';
                html += '<div><label class="form-label">继电器类型 (RelayType):</label>';
                html += '<select id="relay-type-' + relay.id + '" class="form-control" onchange="handleRelaySelectChange(' + relay.id + ', \'relayType\', this)">';
                typeStandard.forEach(function (t) {
                    html += '<option value="' + t + '"' + (relay.relayType === t ? ' selected' : '') + '>' + t + '</option>';
                });
                html += '</select></div></div>';
                html += '<div class="relay-coil-section"><label class="form-label">线圈状态配置 (RelayCoilStatus):</label>';
                html += '<div class="relay-coil-toolbar">';
                html += '<div class="relay-coil-mode-btns">';
                html += '<button id="coil-mode-open-' + relay.id + '" class="btn ' + openBtnCls + '" onclick="setCoilMode(' + relay.id + ', \'open\')">常开</button>';
                html += '<button id="coil-mode-close-' + relay.id + '" class="btn ' + closeBtnCls + '" onclick="setCoilMode(' + relay.id + ', \'close\')">常关</button></div>';
                html += '<input type="text" id="coil-input-' + relay.id + '" class="relay-coil-input" placeholder="输入线圈编号，如: 1,3,5 或 1-5">';
                html += '<button class="btn relay-coil-apply" onclick="applyCoilStatus(' + relay.id + ')">应用</button></div>';
                html += '<div class="relay-coil-grid">';
                relay.coilStatuses.forEach(function (status, idx) {
                    html += '<div class="relay-coil-item"><label>线圈' + (idx + 1) + '</label>';
                    html += '<select class="form-control" onchange="updateRelayConfig(' + relay.id + ', \'coilStatuses\', this.value, ' + idx + ')">';
                    html += '<option value="17"' + (status === 17 ? ' selected' : '') + '>常开(17)</option>';
                    html += '<option value="18"' + (status === 18 ? ' selected' : '') + '>常关(18)</option></select></div>';
                });
                html += '</div></div></div>';
                return html;
            }).join('');
        }
    };

    global.UIComponents = UIComponents;
})(typeof window !== 'undefined' ? window : this);
