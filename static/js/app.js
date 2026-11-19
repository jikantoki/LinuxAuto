/**
 * =============================================================================
 * Linux Auto - Frontend Application Logic
 * 開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
 * GitHub: https://github.com/jikantoki
 * 
 * 【概要】
 * バックエンド（Python HTTP Server）との非同期通信(Fetch API)、
 * UIの状態更新、DHUプロセスの死活監視、設定画面の同期を管理します。
 * =============================================================================
 */

document.addEventListener("DOMContentLoaded", () => {
    // 状態管理
    const state = {
        status: "IDLE",
        isAlive: false,
        retryCountdown: 0,
        logs: [],
        config: null,
    };

    // DOM要素の参照
    const elements = {
        // ナビゲーション
        navItems: document.querySelectorAll(".nav-item"),
        tabPanes: document.querySelectorAll(".tab-pane"),
        sidebarBadge: document.getElementById("sidebar-badge"),

        // メインコントロール
        btnStart: document.getElementById("btn-start"),
        btnStop: document.getElementById("btn-stop"),
        btnGotoSettings: document.getElementById("btn-goto-settings"),
        statusRing: document.getElementById("status-ring"),
        statusIcon: document.getElementById("status-icon"),
        mainStatusTitle: document.getElementById("main-status-title"),
        mainStatusDesc: document.getElementById("main-status-desc"),
        reconnectBanner: document.getElementById("reconnect-banner"),
        countdownTimer: document.getElementById("countdown-timer"),
        countdownProgress: document.getElementById("countdown-progress"),

        // サマリー
        summaryResolution: document.getElementById("summary-resolution"),
        summaryFramerate: document.getElementById("summary-framerate"),
        summaryDpi: document.getElementById("summary-dpi"),
        summaryTouch: document.getElementById("summary-touch"),
        summaryDhuStatus: document.getElementById("summary-dhu-status"),

        // ログ
        logConsole: document.getElementById("log-console"),
        chkAutoscroll: document.getElementById("chk-autoscroll"),
        btnClearLogs: document.getElementById("btn-clear-logs"),

        // 設定フォーム
        settingsForm: document.getElementById("settings-form"),
        inputDhuPath: document.getElementById("input-dhu-path"),
        btnAutoDetect: document.getElementById("btn-auto-detect"),
        dhuPathValidation: document.getElementById("dhu-path-validation"),
        inputTouch: document.getElementById("input-touch"),
        inputTouchpad: document.getElementById("input-touchpad"),
        selectResolution: document.getElementById("select-resolution"),
        inputResolution: document.getElementById("input-resolution"),
        rangeDpi: document.getElementById("range-dpi"),
        inputDpi: document.getElementById("input-dpi"),
        iniPreview: document.getElementById("ini-preview"),
        saveStatusMsg: document.getElementById("save-status-msg"),

        // PWA & トースト
        pwaBanner: document.getElementById("pwa-banner"),
        btnInstallPwa: document.getElementById("btn-install-pwa"),
        toast: document.getElementById("toast"),
    };

    // =========================================================================
    // 1. タブナビゲーション処理
    // =========================================================================
    function switchTab(targetTabId) {
        elements.navItems.forEach(item => {
            if (item.dataset.tab === targetTabId) {
                item.classList.add("active");
            } else {
                item.classList.remove("active");
            }
        });

        elements.tabPanes.forEach(pane => {
            if (pane.id === targetTabId) {
                pane.classList.add("active");
            } else {
                pane.classList.remove("active");
            }
        });
    }

    elements.navItems.forEach(item => {
        item.addEventListener("click", () => switchTab(item.dataset.tab));
    });

    if (elements.btnGotoSettings) {
        elements.btnGotoSettings.addEventListener("click", () => switchTab("tab-settings"));
    }

    // =========================================================================
    // 2. トースト通知表示
    // =========================================================================
    let toastTimeout = null;
    function showToast(message, duration = 3000) {
        if (toastTimeout) clearTimeout(toastTimeout);
        elements.toast.textContent = message;
        elements.toast.classList.add("show");
        toastTimeout = setTimeout(() => {
            elements.toast.classList.remove("show");
        }, duration);
    }

    // =========================================================================
    // 3. API通信ヘルパー (Fetch Wrapper)
    // =========================================================================
    async function apiRequest(endpoint, method = "GET", body = null) {
        const options = {
            method,
            headers: { "Content-Type": "application/json" },
        };
        if (body) {
            options.body = JSON.stringify(body);
        }
        try {
            const res = await fetch(endpoint, options);
            return await res.json();
        } catch (err) {
            console.error(`API Error on ${endpoint}:`, err);
            return { error: err.message };
        }
    }

    // =========================================================================
    // 4. 定期ステータスポーリング (/api/status)
    // =========================================================================
    async function updateStatus() {
        const data = await apiRequest("/api/status");
        if (!data || data.error) return;

        state.status = data.status;
        state.isAlive = data.is_alive;
        state.retryCountdown = data.retry_countdown || 0;
        state.logs = data.logs || [];

        // UIへの反映
        renderStatusUI(data);
        renderLogs(data.logs);
    }

    function renderStatusUI(data) {
        const badge = elements.sidebarBadge;
        const ring = elements.statusRing;
        const badgeLabel = badge.querySelector(".status-label");

        // クラスのリセット
        badge.className = "connection-badge";
        ring.className = "status-ring";

        switch (data.status) {
            case "RUNNING":
                badge.classList.add("running");
                ring.classList.add("running");
                badgeLabel.textContent = `接続中 (PID: ${data.pid})`;
                elements.mainStatusTitle.textContent = "Android Auto 接続中";
                elements.mainStatusDesc.textContent = `desktop-head-unit が正常に実行されています (PID: ${data.pid})`;
                elements.btnStart.disabled = true;
                elements.btnStop.disabled = false;
                elements.reconnectBanner.style.display = "none";
                break;

            case "RECONNECTING":
                badge.classList.add("reconnecting");
                ring.classList.add("reconnecting");
                badgeLabel.textContent = `再接続待機中 (${data.retry_countdown}s)`;
                elements.mainStatusTitle.textContent = "接続が切断されました";
                elements.mainStatusDesc.textContent = "USBケーブルの接続を確認してください。自動的に復帰を試みます。";
                elements.btnStart.disabled = true;
                elements.btnStop.disabled = false; // カウントダウン中断のための切断ボタン

                // 10秒カウントダウンバー
                elements.reconnectBanner.style.display = "block";
                elements.countdownTimer.textContent = `${data.retry_countdown}秒`;
                const progressPercent = Math.max(0, Math.min(100, (data.retry_countdown / 10) * 100));
                elements.countdownProgress.style.width = `${progressPercent}%`;
                break;

            case "ERROR":
                badge.classList.add("error");
                ring.classList.add("error");
                badgeLabel.textContent = "エラー";
                elements.mainStatusTitle.textContent = "起動エラー";
                elements.mainStatusDesc.textContent = data.last_error || "DHUの起動に失敗しました。設定を確認してください。";
                elements.btnStart.disabled = false;
                elements.btnStop.disabled = true;
                elements.reconnectBanner.style.display = "none";
                break;

            case "STARTING":
                badgeLabel.textContent = "起動処理中...";
                elements.mainStatusTitle.textContent = "DHU起動処理中...";
                elements.btnStart.disabled = true;
                elements.btnStop.disabled = true;
                elements.reconnectBanner.style.display = "none";
                break;

            case "IDLE":
            default:
                badgeLabel.textContent = "停止中";
                elements.mainStatusTitle.textContent = "待機中 (停止)";
                elements.mainStatusDesc.textContent = "スマートフォンをUSBで接続し、「接続開始」を押してください。";
                elements.btnStart.disabled = false;
                elements.btnStop.disabled = true;
                elements.reconnectBanner.style.display = "none";
                break;
        }
    }

    let lastLogCount = 0;
    function renderLogs(logs) {
        if (!logs) return;
        if (logs.length === lastLogCount && elements.logConsole.children.length > 1) return;
        lastLogCount = logs.length;

        elements.logConsole.innerHTML = "";
        if (logs.length === 0) {
            elements.logConsole.innerHTML = '<div class="log-line text-muted">[待機中] ログはありません。</div>';
            return;
        }

        logs.forEach(line => {
            const div = document.createElement("div");
            div.className = "log-line";
            div.textContent = line;
            if (line.includes("[エラー]") || line.includes("[例外]")) {
                div.style.color = "#f87171";
            } else if (line.includes("[検知]") || line.includes("[再接続]")) {
                div.style.color = "#fbbf24";
            } else if (line.includes("[接続]")) {
                div.style.color = "#4ade80";
            }
            elements.logConsole.appendChild(div);
        });

        if (elements.chkAutoscroll.checked) {
            elements.logConsole.scrollTop = elements.logConsole.scrollHeight;
        }
    }

    elements.btnClearLogs.addEventListener("click", () => {
        elements.logConsole.innerHTML = '<div class="log-line text-muted">[クリア] 表示ログを消去しました。</div>';
        lastLogCount = 0;
    });

    // =========================================================================
    // 5. コントロールボタン操作 (接続開始 / 切断)
    // =========================================================================
    elements.btnStart.addEventListener("click", async () => {
        elements.btnStart.disabled = true;
        const res = await apiRequest("/api/start", "POST");
        if (res.success) {
            showToast("Android Auto (DHU) を起動しました");
        } else {
            showToast(`起動失敗: ${res.message || "エラー"}`, 4000);
        }
        updateStatus();
    });

    elements.btnStop.addEventListener("click", async () => {
        elements.btnStop.disabled = true;
        const res = await apiRequest("/api/stop", "POST");
        showToast(res.message || "停止しました");
        updateStatus();
    });

    // =========================================================================
    // 6. 設定の読み込みとUI反映
    // =========================================================================
    async function loadConfig() {
        const data = await apiRequest("/api/config");
        if (!data || data.error) return;

        state.config = data;
        const ini = data.headunit_ini || {};
        const app = data.app_config || {};

        // アプリ設定 (DHUパス)
        elements.inputDhuPath.value = app.dhu_path || "";
        checkDhuPath(elements.inputDhuPath.value);

        // headunit.ini 設定
        elements.inputTouch.checked = (ini.touch === "true" || ini.touch === true);
        elements.inputTouchpad.checked = (ini.touchpad === "true" || ini.touchpad === true);

        // 解像度
        const res = ini.resolution || "1920x1080";
        const options = Array.from(elements.selectResolution.options).map(o => o.value);
        if (options.includes(res)) {
            elements.selectResolution.value = res;
            elements.inputResolution.style.display = "none";
        } else {
            elements.selectResolution.value = "custom";
            elements.inputResolution.value = res;
            elements.inputResolution.style.display = "block";
        }

        // DPI
        const dpi = parseInt(ini.dpi || "280", 10);
        elements.rangeDpi.value = dpi;
        elements.inputDpi.value = dpi;

        // 最大フレームレート
        const fps = ini.framerate || "30";
        const radio = document.querySelector(`input[name="framerate"][value="${fps}"]`);
        if (radio) radio.checked = true;

        // サマリーの更新
        updateSummaryUI(ini);
        updateIniPreview();
    }

    function updateSummaryUI(ini) {
        elements.summaryResolution.textContent = ini.resolution || "1920x1080";
        elements.summaryFramerate.textContent = `${ini.framerate || "30"} fps`;
        elements.summaryDpi.textContent = ini.dpi || "280";
        elements.summaryTouch.textContent = (ini.touch === "true" || ini.touch === true) ? "有効 (true)" : "無効 (false)";
    }

    // =========================================================================
    // 7. 設定フォームのインタラクション
    // =========================================================================
    // 解像度セレクタ変更時
    elements.selectResolution.addEventListener("change", () => {
        if (elements.selectResolution.value === "custom") {
            elements.inputResolution.style.display = "block";
            elements.inputResolution.focus();
        } else {
            elements.inputResolution.style.display = "none";
        }
        updateIniPreview();
    });

    // DPIスライダーと数値入力の双方向連動
    elements.rangeDpi.addEventListener("input", () => {
        elements.inputDpi.value = elements.rangeDpi.value;
        updateIniPreview();
    });

    elements.inputDpi.addEventListener("input", () => {
        elements.rangeDpi.value = elements.inputDpi.value;
        updateIniPreview();
    });

    // 各入力変更時にリアルタイムプレビュー更新
    [elements.inputTouch, elements.inputTouchpad, elements.inputResolution].forEach(el => {
        el.addEventListener("change", updateIniPreview);
        el.addEventListener("input", updateIniPreview);
    });

    document.querySelectorAll('input[name="framerate"]').forEach(el => {
        el.addEventListener("change", updateIniPreview);
    });

    // iniプレビュー生成
    function getCurrentFormData() {
        const resolution = elements.selectResolution.value === "custom"
            ? (elements.inputResolution.value.trim() || "1920x1080")
            : elements.selectResolution.value;

        const framerateRadio = document.querySelector('input[name="framerate"]:checked');
        const framerate = framerateRadio ? framerateRadio.value : "30";

        return {
            touch: elements.inputTouch.checked ? "true" : "false",
            touchpad: elements.inputTouchpad.checked ? "true" : "false",
            resolution: resolution,
            dpi: String(elements.inputDpi.value || "280"),
            framerate: framerate,
        };
    }

    function updateIniPreview() {
        const data = getCurrentFormData();
        const content =
`[General]
touch = ${data.touch}
touchpad = ${data.touchpad}
resolution = ${data.resolution}
dpi = ${data.dpi}
framerate = ${data.framerate}`;

        elements.iniPreview.textContent = content;
    }

    // DHUパスの検証
    async function checkDhuPath(path) {
        if (!path || path.trim() === "") {
            elements.dhuPathValidation.innerHTML = '<span class="badge badge-danger">パスが入力されていません</span>';
            elements.summaryDhuStatus.className = "value status-badge invalid";
            elements.summaryDhuStatus.textContent = "未指定";
            return;
        }

        const res = await apiRequest("/api/check-dhu", "POST", { path: path.trim() });
        if (res.valid) {
            elements.dhuPathValidation.innerHTML = '<span class="badge badge-success">✓ 実行可能ファイルが確認されました</span>';
            elements.summaryDhuStatus.className = "value status-badge valid";
            elements.summaryDhuStatus.textContent = "有効 (OK)";
        } else if (res.exists) {
            elements.dhuPathValidation.innerHTML = '<span class="badge badge-danger">⚠️ ファイルは存在しますが実行権限がありません (chmod +x が必要)</span>';
            elements.summaryDhuStatus.className = "value status-badge invalid";
            elements.summaryDhuStatus.textContent = "実行権限なし";
        } else {
            elements.dhuPathValidation.innerHTML = '<span class="badge badge-danger">✕ ファイルが見つかりません</span>';
            elements.summaryDhuStatus.className = "value status-badge invalid";
            elements.summaryDhuStatus.textContent = "見つかりません";
        }
    }

    elements.inputDhuPath.addEventListener("input", () => {
        checkDhuPath(elements.inputDhuPath.value);
    });

    // 標準パス自動探索ボタン
    elements.btnAutoDetect.addEventListener("click", async () => {
        const data = await apiRequest("/api/config");
        if (data && data.app_config && data.app_config.dhu_path) {
            elements.inputDhuPath.value = data.app_config.dhu_path;
            checkDhuPath(data.app_config.dhu_path);
            showToast("標準パスを再検索・設定しました");
        }
    });

    // 設定保存
    elements.settingsForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const iniData = getCurrentFormData();
        const appConfigData = {
            dhu_path: elements.inputDhuPath.value.trim(),
        };

        const res = await apiRequest("/api/config", "POST", {
            headunit_ini: iniData,
            app_config: appConfigData,
        });

        if (res.success) {
            showToast("設定を保存しました (~/.android/headunit.ini)");
            elements.saveStatusMsg.textContent = "✓ 保存完了";
            setTimeout(() => { elements.saveStatusMsg.textContent = ""; }, 3000);
            updateSummaryUI(iniData);
        } else {
            showToast("設定の保存に失敗しました", 4000);
        }
    });

    // =========================================================================
    // 8. ガイド内コードブロックのコピー機能
    // =========================================================================
    document.querySelectorAll(".btn-copy").forEach(btn => {
        btn.addEventListener("click", async () => {
            const textToCopy = btn.getAttribute("data-copy");
            if (!textToCopy) return;

            try {
                await navigator.clipboard.writeText(textToCopy);
                const originalText = btn.textContent;
                btn.textContent = "コピー完了!";
                btn.style.backgroundColor = "var(--success)";
                showToast("コマンドをクリップボードにコピーしました");
                setTimeout(() => {
                    btn.textContent = originalText;
                    btn.style.backgroundColor = "";
                }, 2000);
            } catch (err) {
                console.error("Copy failed:", err);
                showToast("コピーに失敗しました (手動で選択してコピーしてください)", 3000);
            }
        });
    });

    // =========================================================================
    // 9. PWA (Progressive Web App) 対応
    // =========================================================================
    let deferredPrompt = null;

    // Service Worker の登録
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker.register("sw.js")
                .then(reg => console.log("Service Worker registered:", reg.scope))
                .catch(err => console.error("Service Worker registration failed:", err));
        });
    }

    // PWAインストールプロンプトイベント
    window.addEventListener("beforeinstallprompt", (e) => {
        // デフォルトのブラウザプロンプトを抑止
        e.preventDefault();
        deferredPrompt = e;
        // サイドバーのPWAインストールバナーを表示
        if (elements.pwaBanner) {
            elements.pwaBanner.classList.add("show");
        }
    });

    if (elements.btnInstallPwa) {
        elements.btnInstallPwa.addEventListener("click", async () => {
            if (!deferredPrompt) return;
            deferredPrompt.prompt();
            const { outcome } = await deferredPrompt.userChoice;
            console.log("PWA install choice:", outcome);
            deferredPrompt = null;
            elements.pwaBanner.classList.remove("show");
        });
    }

    window.addEventListener("appinstalled", () => {
        showToast("Linux Auto がアプリとしてインストールされました！");
        if (elements.pwaBanner) {
            elements.pwaBanner.classList.remove("show");
        }
    });

    // =========================================================================
    // 10. 初期化と定期ポーリング開始
    // =========================================================================
    loadConfig();
    updateStatus();

    // 1秒ごとにステータスとログを更新
    setInterval(updateStatus, 1000);
});
