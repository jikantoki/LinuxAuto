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

document.addEventListener('DOMContentLoaded', () => {
  // 状態管理
  const state = {
    status: 'IDLE',
    isAlive: false,
    retryCountdown: 0,
    logs: [],
    config: null,
  }

  // DOM要素の参照
  const elements = {
    // ナビゲーション
    navItems: document.querySelectorAll('.nav-item'),
    tabPanes: document.querySelectorAll('.tab-pane'),
    sidebarBadge: document.getElementById('sidebar-badge'),

    // メインコントロール
    btnStart: document.getElementById('btn-start'),
    btnStop: document.getElementById('btn-stop'),
    btnGotoSettings: document.getElementById('btn-goto-settings'),
    statusRing: document.getElementById('status-ring'),
    statusIcon: document.getElementById('status-icon'),
    mainStatusTitle: document.getElementById('main-status-title'),
    mainStatusDesc: document.getElementById('main-status-desc'),
    reconnectBanner: document.getElementById('reconnect-banner'),
    countdownTimer: document.getElementById('countdown-timer'),
    countdownProgress: document.getElementById('countdown-progress'),

    // サマリー
    summaryResolution: document.getElementById('summary-resolution'),
    summaryFramerate: document.getElementById('summary-framerate'),
    summaryDpi: document.getElementById('summary-dpi'),
    summaryTouch: document.getElementById('summary-touch'),
    summaryDhuStatus: document.getElementById('summary-dhu-status'),

    // ログ
    logConsole: document.getElementById('log-console'),
    chkAutoscroll: document.getElementById('chk-autoscroll'),
    btnClearLogs: document.getElementById('btn-clear-logs'),

    // 設定フォーム
    settingsForm: document.getElementById('settings-form'),
    inputDhuPath: document.getElementById('input-dhu-path'),
    btnAutoDetect: document.getElementById('btn-auto-detect'),
    dhuPathValidation: document.getElementById('dhu-path-validation'),
    inputTouch: document.getElementById('input-touch'),
    inputTouchpad: document.getElementById('input-touchpad'),
    selectResolution: document.getElementById('select-resolution'),
    inputResolution: document.getElementById('input-resolution'),
    rangeDpi: document.getElementById('range-dpi'),
    inputDpi: document.getElementById('input-dpi'),
    iniPreview: document.getElementById('ini-preview'),
    saveStatusMsg: document.getElementById('save-status-msg'),

    // PWA & トースト
    pwaBanner: document.getElementById('pwa-banner'),
    btnInstallPwa: document.getElementById('btn-install-pwa'),
    toast: document.getElementById('toast'),
  }

  // =========================================================================
  // 1. タブナビゲーション処理
  // =========================================================================
  function switchTab(targetTabId) {
    elements.navItems.forEach((item) => {
      if (item.dataset.tab === targetTabId) {
        item.classList.add('active')
      } else {
        item.classList.remove('active')
      }
    })

    elements.tabPanes.forEach((pane) => {
      if (pane.id === targetTabId) {
        pane.classList.add('active')
      } else {
        pane.classList.remove('active')
      }
    })
  }

  elements.navItems.forEach((item) => {
    item.addEventListener('click', () => switchTab(item.dataset.tab))
  })

  if (elements.btnGotoSettings) {
    elements.btnGotoSettings.addEventListener('click', () =>
      switchTab('tab-settings'),
    )
  }

  // =========================================================================
  // 2. トースト通知表示
  // =========================================================================
  let toastTimeout = null
  function showToast(message, duration = 3000) {
    if (toastTimeout) clearTimeout(toastTimeout)
    elements.toast.textContent = message
    elements.toast.classList.add('show')
    toastTimeout = setTimeout(() => {
      elements.toast.classList.remove('show')
    }, duration)
  }

  // =========================================================================
  // 3. API通信ヘルパー (Fetch Wrapper)
  // =========================================================================
  async function apiRequest(endpoint, method = 'GET', body = null) {
    const options = {
      method,
      headers: { 'Content-Type': 'application/json' },
    }
    if (body) {
      options.body = JSON.stringify(body)
    }
    try {
      const res = await fetch(endpoint, options)
      return await res.json()
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err)
      return { error: err.message }
    }
  }

  // =========================================================================
  // 4. 定期ステータスポーリング (/api/status)
  // =========================================================================
  async function updateStatus() {
    const data = await apiRequest('/api/status')
    if (!data || data.error) return

    state.status = data.status
    state.isAlive = data.is_alive
    state.retryCountdown = data.retry_countdown || 0
    state.logs = data.logs || []

    // UIへの反映
    renderStatusUI(data)
    renderLogs(data.logs)
    renderRunMode(data.run_mode)
  }

  // サーバーの起動方式 (サービス / 手動) を導入ガイドに表示
  function renderRunMode(runMode) {
    const label = document.getElementById('run-mode-label')
    if (!label) return
    if (runMode === 'service') {
      label.textContent = 'サービス (systemd) で常駐中 ✔ 設定済みです'
    } else if (runMode === 'manual') {
      label.textContent =
        '手動起動 (start.sh など) — 下の手順でサービス登録できます'
    } else {
      label.textContent = '不明 (サーバーを更新後に再起動してください)'
    }
  }

  function renderStatusUI(data) {
    setConnectionLocked(
      ['RUNNING', 'RECONNECTING', 'STARTING'].includes(data.status),
    )
    const activeConn = data.connection || {}
    const isWifi = activeConn.type
      ? activeConn.type === 'wifi'
      : conn.type === 'wifi'
    const reconnectSub = document.getElementById('reconnect-sub')
    if (reconnectSub) {
      reconnectSub.textContent = isWifi
        ? 'テザリング (Wi-Fi) 接続とスマホのヘッドユニットサーバーを確認してください。自動的に再接続します。'
        : 'USBケーブルを挿し直してください。自動的にDHUを再起動します。'
    }
    const badge = elements.sidebarBadge
    const ring = elements.statusRing
    const badgeLabel = badge.querySelector('.status-label')

    // クラスのリセット
    badge.className = 'connection-badge'
    ring.className = 'status-ring'

    switch (data.status) {
      case 'RUNNING':
        badge.classList.add('running')
        ring.classList.add('running')
        badgeLabel.textContent = `接続中 (PID: ${data.pid})`
        elements.mainStatusTitle.textContent = 'Android Auto 接続中'
        elements.mainStatusDesc.textContent = activeConn.warning
          ? `⚠️ ${activeConn.warning}`
          : activeConn.label
            ? `${activeConn.label}${activeConn.target ? ' / ' + activeConn.target : ''} で実行中 (PID: ${data.pid})`
            : `desktop-head-unit が正常に実行されています (PID: ${data.pid})`
        if (activeConn.warning) {
          ring.classList.add('reconnecting')
          badgeLabel.textContent = 'スマホの応答待ち'
        }
        elements.btnStart.disabled = true
        elements.btnStop.disabled = false
        elements.reconnectBanner.style.display = 'none'
        break

      case 'RECONNECTING':
        badge.classList.add('reconnecting')
        ring.classList.add('reconnecting')
        badgeLabel.textContent = `再接続待機中 (${data.retry_countdown}s)`
        elements.mainStatusTitle.textContent = '接続が切断されました'
        elements.mainStatusDesc.textContent = data.last_error
          ? data.last_error
          : isWifi
            ? 'Wi-Fi 接続を確認してください。自動的に復帰を試みます。'
            : 'USBケーブルの接続を確認してください。自動的に復帰を試みます。'
        elements.btnStart.disabled = true
        elements.btnStop.disabled = false // カウントダウン中断のための切断ボタン

        // 10秒カウントダウンバー
        elements.reconnectBanner.style.display = 'block'
        elements.countdownTimer.textContent = `${data.retry_countdown}秒`
        const progressPercent = Math.max(
          0,
          Math.min(100, (data.retry_countdown / 10) * 100),
        )
        elements.countdownProgress.style.width = `${progressPercent}%`
        break

      case 'ERROR':
        badge.classList.add('error')
        ring.classList.add('error')
        badgeLabel.textContent = 'エラー'
        elements.mainStatusTitle.textContent = '起動エラー'
        elements.mainStatusDesc.textContent =
          data.last_error || 'DHUの起動に失敗しました。設定を確認してください。'
        elements.btnStart.disabled = false
        elements.btnStop.disabled = true
        elements.reconnectBanner.style.display = 'none'
        break

      case 'STARTING':
        badgeLabel.textContent = '起動処理中...'
        elements.mainStatusTitle.textContent = 'DHU起動処理中...'
        elements.btnStart.disabled = true
        elements.btnStop.disabled = true
        elements.reconnectBanner.style.display = 'none'
        break

      case 'IDLE':
      default:
        badgeLabel.textContent = '停止中'
        elements.mainStatusTitle.textContent = '待機中 (停止)'
        elements.mainStatusDesc.textContent = idleDescription()
        elements.btnStart.disabled = false
        elements.btnStop.disabled = true
        elements.reconnectBanner.style.display = 'none'
        break
    }
  }

  let lastLogCount = 0
  function renderLogs(logs) {
    if (!logs) return
    if (logs.length === lastLogCount && elements.logConsole.children.length > 1)
      return
    lastLogCount = logs.length

    elements.logConsole.innerHTML = ''
    if (logs.length === 0) {
      elements.logConsole.innerHTML =
        '<div class="log-line text-muted">[待機中] ログはありません。</div>'
      return
    }

    logs.forEach((line) => {
      const div = document.createElement('div')
      div.className = 'log-line'
      div.textContent = line
      if (line.includes('[エラー]') || line.includes('[例外]')) {
        div.style.color = '#f87171'
      } else if (
        line.includes('[検知]') ||
        line.includes('[再接続]') ||
        line.includes('[警告]')
      ) {
        div.style.color = '#fbbf24'
      } else if (
        line.includes('[Wi-Fi]') ||
        line.includes('[ADB]') ||
        line.includes('[リレー]') ||
        line.includes('[疎通確認]')
      ) {
        div.style.color = '#93c5fd'
      } else if (line.includes('[接続]')) {
        div.style.color = '#4ade80'
      }
      elements.logConsole.appendChild(div)
    })

    if (elements.chkAutoscroll.checked) {
      elements.logConsole.scrollTop = elements.logConsole.scrollHeight
    }
  }

  elements.btnClearLogs.addEventListener('click', () => {
    elements.logConsole.innerHTML =
      '<div class="log-line text-muted">[クリア] 表示ログを消去しました。</div>'
    lastLogCount = 0
  })

  // =========================================================================
  // 4.5 接続方式 (USB接続 / Wi-Fi接続 [方法1: ADB / 方法2: 直接])
  // =========================================================================
  const conn = {
    card: document.getElementById('conn-card'),
    tabs: document.querySelectorAll('.conn-tab'),
    panels: {
      usb: document.getElementById('panel-usb'),
      wifi: document.getElementById('panel-wifi'),
    },
    lockNote: document.getElementById('conn-lock-note'),
    inputPhoneIp: document.getElementById('input-phone-ip'),
    inputAdbPort: document.getElementById('input-adb-port'),
    inputHuPort: document.getElementById('input-hu-port'),
    inputPairPort: document.getElementById('input-pair-port'),
    inputPairCode: document.getElementById('input-pair-code'),
    detailAdb: document.getElementById('detail-adb'),
    detailDirect: document.getElementById('detail-direct'),
    result: document.getElementById('wifi-action-result'),
    deviceList: document.getElementById('adb-device-list'),
    net: {
      ssid: document.getElementById('net-ssid'),
      iface: document.getElementById('net-iface'),
      localIp: document.getElementById('net-local-ip'),
      gateway: document.getElementById('net-gateway'),
      hint: document.getElementById('net-hint'),
    },
    type: 'usb',
    locked: false,
    lastNetwork: null,
  }

  const radioValue = (name, fallback) => {
    const el = document.querySelector(`input[name="${name}"]:checked`)
    return el ? el.value : fallback
  }
  const setRadio = (name, value) => {
    const el = document.querySelector(`input[name="${name}"][value="${value}"]`)
    if (el) el.checked = true
  }

  // 画面の入力内容 → サーバーに送る接続設定
  function getConnectionForm() {
    return {
      connection_type: conn.type,
      wifi_mode: radioValue('wifi-mode', 'direct'),
      phone_ip_auto: radioValue('phone-ip-mode', 'auto') === 'auto',
      phone_ip: conn.inputPhoneIp.value.trim(),
      adb_port: parseInt(conn.inputAdbPort.value, 10) || 5555,
      hu_port: parseInt(conn.inputHuPort.value, 10) || 5277,
      direct_transport: radioValue('direct-transport', 'adb_flag'),
    }
  }

  // サーバーの設定値 → 画面
  function applyConnectionConfig(app) {
    conn.type = app.connection_type === 'wifi' ? 'wifi' : 'usb'
    setRadio('wifi-mode', app.wifi_mode === 'adb' ? 'adb' : 'direct')
    setRadio('phone-ip-mode', app.phone_ip_auto === false ? 'manual' : 'auto')
    conn.inputPhoneIp.value = app.phone_ip || ''
    conn.inputAdbPort.value = app.adb_port || 5555
    conn.inputHuPort.value = app.hu_port || 5277
    setRadio(
      'direct-transport',
      app.direct_transport === 'relay' ? 'relay' : 'adb_flag',
    )
    renderConnectionUI()
  }

  function phoneIpLabel() {
    const f = getConnectionForm()
    if (!f.phone_ip_auto) return f.phone_ip || '(未入力)'
    const gw = conn.lastNetwork && conn.lastNetwork.resolved_phone_ip
    return gw ? `${gw}（自動）` : '自動検出（未検出）'
  }

  function connectionSummary() {
    const f = getConnectionForm()
    if (f.connection_type === 'usb')
      return { label: 'USB（AOA）', target: 'USB ケーブル' }
    if (f.wifi_mode === 'adb') {
      return {
        label: 'Wi-Fi 方法1（ADB）',
        target: `${phoneIpLabel()} : ${f.adb_port}`,
      }
    }
    const via = f.direct_transport === 'relay' ? '（内蔵リレー）' : ''
    return {
      label: `Wi-Fi 方法2（直接）${via}`,
      target: `${phoneIpLabel()} : ${f.hu_port}`,
    }
  }

  function renderConnectionUI() {
    const f = getConnectionForm()
    conn.tabs.forEach((t) =>
      t.classList.toggle('active', t.dataset.conn === conn.type),
    )
    Object.entries(conn.panels).forEach(([k, el]) =>
      el.classList.toggle('active', k === conn.type),
    )
    conn.inputPhoneIp.style.display = f.phone_ip_auto ? 'none' : 'block'
    conn.detailAdb.classList.toggle('active', f.wifi_mode === 'adb')
    conn.detailDirect.classList.toggle('active', f.wifi_mode === 'direct')

    const s = connectionSummary()
    const sumConn = document.getElementById('summary-connection')
    const sumTarget = document.getElementById('summary-target')
    if (sumConn) sumConn.textContent = s.label
    if (sumTarget) sumTarget.textContent = s.target
    if (state.status === 'IDLE' || state.status === 'ERROR') {
      elements.mainStatusDesc.textContent = idleDescription()
    }
  }

  function idleDescription() {
    if (conn.type === 'usb')
      return 'スマートフォンを USB で接続し、「接続開始」を押してください。'
    const f = getConnectionForm()
    const method =
      f.wifi_mode === 'adb'
        ? '方法1（ADB）'
        : '方法2（ヘッドユニットサーバーへ直接）'
    return `Wi-Fi ${method} で接続します。スマホで「ヘッドユニットサーバーを起動」してから「接続開始」を押してください。`
  }

  // 設定の自動保存 (入力が落ち着いてから 0.6 秒後)
  let saveTimer = null
  function saveConnectionSoon() {
    renderConnectionUI()
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      apiRequest('/api/config', 'POST', { app_config: getConnectionForm() })
    }, 600)
  }

  conn.tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      if (conn.locked) return
      conn.type = tab.dataset.conn
      saveConnectionSoon()
      if (conn.type === 'wifi') refreshNetwork()
    })
  })

  document
    .querySelectorAll(
      'input[name="wifi-mode"], input[name="phone-ip-mode"], input[name="direct-transport"]',
    )
    .forEach((el) => el.addEventListener('change', saveConnectionSoon))
  document.querySelectorAll('input[name="wifi-mode"]').forEach((el) =>
    el.addEventListener('change', () => {
      if (el.checked && el.value === 'adb') refreshDevices()
    }),
  )
  ;[conn.inputPhoneIp, conn.inputAdbPort, conn.inputHuPort].forEach((el) =>
    el.addEventListener('input', saveConnectionSoon),
  )

  // 接続中は接続方式を変更できないようにロック
  function setConnectionLocked(locked) {
    if (conn.locked === locked) return
    conn.locked = locked
    conn.card.classList.toggle('locked', locked)
    conn.lockNote.style.display = locked ? 'block' : 'none'
    conn.card.querySelectorAll('input, .conn-tab').forEach((el) => {
      el.disabled = locked
    })
  }

  // ---- 結果表示 ----
  function showResult(ok, message) {
    conn.result.className = `wifi-result show ${ok ? 'ok' : 'ng'}`
    conn.result.textContent = `${ok ? '✓' : '✕'} ${message}`
  }

  // ---- ネットワーク情報 (テザリング親機の自動検出) ----
  async function refreshNetwork() {
    const data = await apiRequest('/api/network')
    if (!data || data.error) return
    conn.lastNetwork = data
    conn.net.ssid.textContent =
      data.ssid || (data.wireless ? '(取得不可)' : '--')
    conn.net.iface.textContent = data.iface
      ? `${data.iface}${data.wireless ? '（Wi-Fi）' : '（有線/その他）'}`
      : '--'
    conn.net.localIp.textContent = data.local_ip || '--'
    conn.net.gateway.textContent = data.gateway || '--'

    if (!data.detected) {
      conn.net.hint.textContent =
        '⚠️ デフォルトゲートウェイが見つかりません。Linux 端末をスマホのテザリング (Wi-Fi アクセスポイント) に接続してください。'
    } else if (!data.wireless) {
      conn.net.hint.textContent = `⚠️ 現在の経路は Wi-Fi ではありません (${data.iface})。テザリング運用では Wi-Fi でスマホに接続し、必要なら有線LANを外してください。`
    } else {
      conn.net.hint.textContent = `テザリング接続中であれば、ゲートウェイ ${data.gateway} がスマホ本体の IP アドレスです（「自動」を選ぶとこの値を使います）。`
    }
    renderConnectionUI()
  }

  document
    .getElementById('btn-net-refresh')
    .addEventListener('click', refreshNetwork)

  // ---- 方法1: ADB 操作 ----
  function renderDevices(devices) {
    if (!devices || devices.length === 0) {
      conn.deviceList.innerHTML =
        '<div class="text-muted">adb で認識されている端末はありません。</div>'
      return
    }
    conn.deviceList.innerHTML = ''
    devices.forEach((d) => {
      const row = document.createElement('div')
      row.className = 'adb-device'
      const stateClass = d.state === 'device' ? 'badge-success' : 'badge-danger'
      row.innerHTML = `<span class="badge badge-info"></span>
                             <code></code><span class="adb-model"></span><span class="badge ${stateClass}"></span>`
      const [t, serial, model, st] = row.children
      t.textContent = d.transport === 'wifi' ? 'Wi-Fi' : 'USB'
      serial.textContent = d.serial
      model.textContent = d.model || ''
      st.textContent = d.state === 'device' ? '接続OK' : d.state
      conn.deviceList.appendChild(row)
    })
  }

  async function refreshDevices() {
    const data = await apiRequest('/api/adb/devices')
    if (!data || data.error) return
    if (!data.adb_found) {
      conn.deviceList.innerHTML =
        '<div class="text-muted">⚠️ adb が見つかりません。Android SDK の platform-tools をインストールしてください。</div>'
      return
    }
    renderDevices(data.devices)
  }

  async function adbAction(endpoint, body, button) {
    button.disabled = true
    const original = button.textContent
    button.textContent = '実行中...'
    const res = await apiRequest(endpoint, 'POST', body)
    button.textContent = original
    button.disabled = conn.locked
    showResult(!!res.success, res.message || res.error || '応答がありません')
    if (res.devices) renderDevices(res.devices)
  }

  document
    .getElementById('btn-adb-tcpip')
    .addEventListener('click', (e) =>
      adbAction(
        '/api/adb/tcpip',
        { port: getConnectionForm().adb_port },
        e.currentTarget,
      ),
    )

  document.getElementById('btn-adb-connect').addEventListener('click', (e) => {
    const f = getConnectionForm()
    adbAction(
      '/api/adb/connect',
      { host: f.phone_ip_auto ? '' : f.phone_ip, port: f.adb_port },
      e.currentTarget,
    )
  })

  document.getElementById('btn-adb-pair').addEventListener('click', (e) => {
    const f = getConnectionForm()
    adbAction(
      '/api/adb/pair',
      {
        host: f.phone_ip_auto ? '' : f.phone_ip,
        port: parseInt(conn.inputPairPort.value, 10) || 0,
        code: conn.inputPairCode.value.trim(),
      },
      e.currentTarget,
    )
  })

  document
    .getElementById('btn-adb-devices')
    .addEventListener('click', refreshDevices)

  // ---- 方法2: ヘッドユニットサーバー疎通確認 ----
  document.getElementById('btn-probe').addEventListener('click', async (e) => {
    const btn = e.currentTarget
    const f = getConnectionForm()
    btn.disabled = true
    const res = await apiRequest('/api/probe', 'POST', {
      host: f.phone_ip_auto ? '' : f.phone_ip,
      port: f.hu_port,
    })
    btn.disabled = conn.locked
    showResult(
      !!res.ok,
      res.ok
        ? `${res.message}。ヘッドユニットサーバーが待ち受けています。※ この確認で接続を1回使うため、「接続開始」後に Waiting for phone... のまま進まない場合は、スマホでヘッドユニットサーバーを停止→起動し直してから接続してください。`
        : `${res.message || res.error}。スマホで「ヘッドユニットサーバーを起動」しているか確認してください。`,
    )
  })

  // Wi-Fi 選択中は 15 秒ごとにネットワーク状態を更新 (テザリングの接続・切断に追従)
  setInterval(() => {
    if (conn.type === 'wifi' && !document.hidden) refreshNetwork()
  }, 15000)

  // =========================================================================
  // 5. コントロールボタン操作 (接続開始 / 切断)
  // =========================================================================
  elements.btnStart.addEventListener('click', async () => {
    elements.btnStart.disabled = true
    // 画面で選択中の接続方式を一緒に送る (サーバー側で保存してから起動)
    const res = await apiRequest('/api/start', 'POST', {
      connection: getConnectionForm(),
    })
    if (res.success) {
      showToast('Android Auto (DHU) を起動しました')
    } else {
      showToast(`起動失敗: ${res.message || 'エラー'}`, 4000)
    }
    updateStatus()
  })

  elements.btnStop.addEventListener('click', async () => {
    elements.btnStop.disabled = true
    const res = await apiRequest('/api/stop', 'POST')
    showToast(res.message || '停止しました')
    updateStatus()
  })

  // =========================================================================
  // 6. 設定の読み込みとUI反映
  // =========================================================================
  async function loadConfig() {
    const data = await apiRequest('/api/config')
    if (!data || data.error) return

    state.config = data
    const ini = data.headunit_ini || {}
    const app = data.app_config || {}

    // 接続方式 (USB / Wi-Fi)
    applyConnectionConfig(app)
    if (conn.type === 'wifi') {
      refreshNetwork()
      refreshDevices()
    }

    // アプリ設定 (DHUパス)
    elements.inputDhuPath.value = app.dhu_path || ''
    checkDhuPath(elements.inputDhuPath.value)

    // headunit.ini 設定
    elements.inputTouch.checked = ini.touch === 'true' || ini.touch === true
    elements.inputTouchpad.checked =
      ini.touchpad === 'true' || ini.touchpad === true

    // 解像度
    const res = ini.resolution || '1920x1080'
    const options = Array.from(elements.selectResolution.options).map(
      (o) => o.value,
    )
    if (options.includes(res)) {
      elements.selectResolution.value = res
      elements.inputResolution.style.display = 'none'
    } else {
      elements.selectResolution.value = 'custom'
      elements.inputResolution.value = res
      elements.inputResolution.style.display = 'block'
    }

    // DPI
    const dpi = parseInt(ini.dpi || '280', 10)
    elements.rangeDpi.value = dpi
    elements.inputDpi.value = dpi

    // 最大フレームレート
    const fps = ini.framerate || '30'
    const radio = document.querySelector(
      `input[name="framerate"][value="${fps}"]`,
    )
    if (radio) radio.checked = true

    // サマリーの更新
    updateSummaryUI(ini)
    updateIniPreview()
  }

  function updateSummaryUI(ini) {
    elements.summaryResolution.textContent = ini.resolution || '1920x1080'
    elements.summaryFramerate.textContent = `${ini.framerate || '30'} fps`
    elements.summaryDpi.textContent = ini.dpi || '280'
    elements.summaryTouch.textContent =
      ini.touch === 'true' || ini.touch === true
        ? '有効 (true)'
        : '無効 (false)'
  }

  // =========================================================================
  // 7. 設定フォームのインタラクション
  // =========================================================================
  // 解像度セレクタ変更時
  elements.selectResolution.addEventListener('change', () => {
    if (elements.selectResolution.value === 'custom') {
      elements.inputResolution.style.display = 'block'
      elements.inputResolution.focus()
    } else {
      elements.inputResolution.style.display = 'none'
    }
    updateIniPreview()
  })

  // DPIスライダーと数値入力の双方向連動
  elements.rangeDpi.addEventListener('input', () => {
    elements.inputDpi.value = elements.rangeDpi.value
    updateIniPreview()
  })

  elements.inputDpi.addEventListener('input', () => {
    elements.rangeDpi.value = elements.inputDpi.value
    updateIniPreview()
  })

  // 各入力変更時にリアルタイムプレビュー更新
  ;[
    elements.inputTouch,
    elements.inputTouchpad,
    elements.inputResolution,
  ].forEach((el) => {
    el.addEventListener('change', updateIniPreview)
    el.addEventListener('input', updateIniPreview)
  })

  document.querySelectorAll('input[name="framerate"]').forEach((el) => {
    el.addEventListener('change', updateIniPreview)
  })

  // iniプレビュー生成
  function getCurrentFormData() {
    const resolution =
      elements.selectResolution.value === 'custom'
        ? elements.inputResolution.value.trim() || '1920x1080'
        : elements.selectResolution.value

    const framerateRadio = document.querySelector(
      'input[name="framerate"]:checked',
    )
    const framerate = framerateRadio ? framerateRadio.value : '30'

    return {
      touch: elements.inputTouch.checked ? 'true' : 'false',
      touchpad: elements.inputTouchpad.checked ? 'true' : 'false',
      resolution: resolution,
      dpi: String(elements.inputDpi.value || '280'),
      framerate: framerate,
    }
  }

  function updateIniPreview() {
    const data = getCurrentFormData()
    const content = `[general]
touch = ${data.touch}
touchpad = ${data.touchpad}
resolution = ${data.resolution}
dpi = ${data.dpi}
framerate = ${data.framerate}`

    elements.iniPreview.textContent = content
  }

  // DHUパスの検証
  async function checkDhuPath(path) {
    if (!path || path.trim() === '') {
      elements.dhuPathValidation.innerHTML =
        '<span class="badge badge-danger">パスが入力されていません</span>'
      elements.summaryDhuStatus.className = 'value status-badge invalid'
      elements.summaryDhuStatus.textContent = '未指定'
      return
    }

    const res = await apiRequest('/api/check-dhu', 'POST', {
      path: path.trim(),
    })
    if (res.valid) {
      elements.dhuPathValidation.innerHTML =
        '<span class="badge badge-success">✓ 実行可能ファイルが確認されました</span>'
      elements.summaryDhuStatus.className = 'value status-badge valid'
      elements.summaryDhuStatus.textContent = '有効 (OK)'
    } else if (res.exists) {
      elements.dhuPathValidation.innerHTML =
        '<span class="badge badge-danger">⚠️ ファイルは存在しますが実行権限がありません (chmod +x が必要)</span>'
      elements.summaryDhuStatus.className = 'value status-badge invalid'
      elements.summaryDhuStatus.textContent = '実行権限なし'
    } else {
      elements.dhuPathValidation.innerHTML =
        '<span class="badge badge-danger">✕ ファイルが見つかりません</span>'
      elements.summaryDhuStatus.className = 'value status-badge invalid'
      elements.summaryDhuStatus.textContent = '見つかりません'
    }
  }

  elements.inputDhuPath.addEventListener('input', () => {
    checkDhuPath(elements.inputDhuPath.value)
  })

  // 標準パス自動探索ボタン
  elements.btnAutoDetect.addEventListener('click', async () => {
    const data = await apiRequest('/api/config')
    if (data && data.app_config && data.app_config.dhu_path) {
      elements.inputDhuPath.value = data.app_config.dhu_path
      checkDhuPath(data.app_config.dhu_path)
      showToast('標準パスを再検索・設定しました')
    }
  })

  // 設定保存
  elements.settingsForm.addEventListener('submit', async (e) => {
    e.preventDefault()
    const iniData = getCurrentFormData()
    const appConfigData = {
      dhu_path: elements.inputDhuPath.value.trim(),
    }

    const res = await apiRequest('/api/config', 'POST', {
      headunit_ini: iniData,
      app_config: appConfigData,
    })

    if (res.success) {
      showToast('設定を保存しました (~/.android/headunit.ini)')
      elements.saveStatusMsg.textContent = '✓ 保存完了'
      setTimeout(() => {
        elements.saveStatusMsg.textContent = ''
      }, 3000)
      updateSummaryUI(iniData)
    } else {
      showToast('設定の保存に失敗しました', 4000)
    }
  })

  // =========================================================================
  // 8. ガイド内コードブロックのコピー機能
  // =========================================================================
  document.querySelectorAll('.btn-copy').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const textToCopy = btn.getAttribute('data-copy')
      if (!textToCopy) return

      try {
        await navigator.clipboard.writeText(textToCopy)
        const originalText = btn.textContent
        btn.textContent = 'コピー完了!'
        btn.style.backgroundColor = 'var(--success)'
        showToast('コマンドをクリップボードにコピーしました')
        setTimeout(() => {
          btn.textContent = originalText
          btn.style.backgroundColor = ''
        }, 2000)
      } catch (err) {
        console.error('Copy failed:', err)
        showToast(
          'コピーに失敗しました (手動で選択してコピーしてください)',
          3000,
        )
      }
    })
  })

  // =========================================================================
  // 9. PWA (Progressive Web App) 対応
  // =========================================================================
  let deferredPrompt = null

  // Service Worker の登録
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('sw.js')
        .then((reg) => console.log('Service Worker registered:', reg.scope))
        .catch((err) =>
          console.error('Service Worker registration failed:', err),
        )
    })
  }

  // PWAインストールプロンプトイベント
  window.addEventListener('beforeinstallprompt', (e) => {
    // デフォルトのブラウザプロンプトを抑止
    e.preventDefault()
    deferredPrompt = e
    // サイドバーのPWAインストールバナーを表示
    if (elements.pwaBanner) {
      elements.pwaBanner.classList.add('show')
    }
  })

  if (elements.btnInstallPwa) {
    elements.btnInstallPwa.addEventListener('click', async () => {
      if (!deferredPrompt) return
      deferredPrompt.prompt()
      const { outcome } = await deferredPrompt.userChoice
      console.log('PWA install choice:', outcome)
      deferredPrompt = null
      elements.pwaBanner.classList.remove('show')
    })
  }

  window.addEventListener('appinstalled', () => {
    showToast('Linux Auto がアプリとしてインストールされました！')
    if (elements.pwaBanner) {
      elements.pwaBanner.classList.remove('show')
    }
  })

  // =========================================================================
  // 10. 初期化と定期ポーリング開始
  // =========================================================================
  loadConfig()
  updateStatus()

  // 1秒ごとにステータスとログを更新
  setInterval(updateStatus, 1000)
})
