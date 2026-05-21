/**
 * app.js - 应用程序入口：页签切换、初始化、心跳
 */
(function (global) {
    'use strict';

    global.showTab = function (tabId) {
        document.querySelectorAll('.tab-content').forEach(function (t) { t.classList.remove('active'); });
        document.querySelectorAll('.nav-tab').forEach(function (t) { t.classList.remove('active'); });
        var tabEl = document.getElementById(tabId);
        if (tabEl) tabEl.classList.add('active');
        if (global.event && global.event.currentTarget) global.event.currentTarget.classList.add('active');
    };

    function sendHeartbeat() {
        if (global.API && global.API.heartbeat) global.API.heartbeat();
    }

    var workerCode = 'setInterval(function(){self.postMessage("ping");}, 5000);';
    var blob = new Blob([workerCode], { type: 'application/javascript' });
    var worker = new Worker(URL.createObjectURL(blob));
    worker.onmessage = function (e) {
        if (e.data === 'ping') sendHeartbeat();
    };
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') sendHeartbeat();
    });
    sendHeartbeat();
    var lastFired = Date.now();
    setInterval(function () {
        var now = Date.now();
        if (now - lastFired > 20000) sendHeartbeat();
        lastFired = now;
    }, 5000);

    var backendDownNotified = false;
    global.handleBackendDown = function () {
        if (backendDownNotified) return;
        backendDownNotified = true;
        try {
            alert('后端程序已关闭或异常退出，本页面将不再可用。\n\n请关闭本页面，并重新双击 EXE 启动工具后再使用。');
        } catch (e) {
            console.error(e);
        }
        try {
            window.close();
        } catch (e2) {
            console.error(e2);
        }
    };

    window.onload = function () {
        if (global.initFromConfig) global.initFromConfig();
    };
})(typeof window !== 'undefined' ? window : this);
