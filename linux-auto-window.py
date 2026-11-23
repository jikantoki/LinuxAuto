#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================================================
Linux Auto - 専用ウィンドウ ランチャー (linux-auto-window.py)
開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
GitHub: https://github.com/jikantoki/LinuxAuto

【役割】
ブラウザを使わずに、Linux Auto の画面 (WebUI) を独立したアプリのウィンドウで開きます。
deb パッケージでは /usr/bin/linux-auto (アプリメニューの「Linux Auto」) から呼ばれます。

  1. サーバー (app.py) が応答しているか確認し、止まっていれば
     linux-auto.service (systemd ユーザーサービス) を起動する
     (サービスが無い環境では、バックグラウンドで一時起動する)
  2. 画面を専用ウィンドウで開く。使える部品を次の順で探す
       PyQt6 + Qt WebEngine (apt: python3-pyqt6.qtwebengine)  ← KDE Plasma と相性が良い
       PyQt5 + Qt WebEngine (apt: python3-pyqt5.qtwebengine)
       WebKitGTK            (apt: python3-gi gir1.2-webkit2-4.1)
     どれも無ければ、これまで通りブラウザで開く
  3. すでにウィンドウが開いている場合は、新しく開かずに既存のウィンドウを前面に出す

ウィンドウを閉じても、サーバーと Android Auto の接続は止まりません (サービスが動き続けます)。
サーバーが再起動した場合 (deb の更新など) は、復帰を待って自動で画面を読み込み直します。
app.py と同じく pip のライブラリは使いません (Qt / GTK は apt のパッケージを利用)。

【ショートカットキー】
  F11              全画面の切り替え (状態は次回も引き継ぐ)
  F5 / Ctrl+R      再読み込み
  Ctrl + + / - / 0 拡大 / 縮小 / 100% に戻す (倍率は次回も引き継ぐ)
  Ctrl+Q           ウィンドウを閉じる (サーバーは止まりません)

【オプション】
  --fullscreen / --windowed  全画面 / ウィンドウで開く (前回の状態より優先)
  --browser                  専用ウィンドウを使わずブラウザで開く
  --toolkit qt6|qt5|gtk      使う部品を指定する (環境変数 LINUX_AUTO_TOOLKIT でも可)
  --disable-gpu              画面が真っ黒・ちらつく環境向けに GPU 描画を無効化する
  --migrate                  旧方式 (install-service.sh / install-desktop-shortcut.sh) の
                             登録を無効化して deb 版に切り替える
=============================================================================
"""

import os
import sys
import json
import time
import shutil
import argparse
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

# =============================================================================
# 定数・パス定義
# =============================================================================
APP_DIR = Path(__file__).resolve().parent
APP_PY = APP_DIR / "app.py"
ICON_PATH = APP_DIR / "static" / "icon.svg"

# deb パッケージとしてインストールされているか (旧方式の登録チェックはこの場合のみ行う)
PACKAGED_DIR = Path("/usr/lib/linux-auto")
IS_PACKAGED = APP_DIR == PACKAGED_DIR

try:
    PORT = int(os.environ.get("LINUX_AUTO_PORT", "8855"))
except ValueError:
    PORT = 8855
HOST = "127.0.0.1"
BASE_URL = f"http://{HOST}:{PORT}/"

SERVICE_NAME = "linux-auto.service"
APP_ID = "linux-auto"              # .desktop ファイル名 / WM_CLASS / Wayland の app_id
GTK_APP_ID = "xyz.enoki.LinuxAuto"  # GTK 版の二重起動防止に使う ID
WINDOW_TITLE = "Linux Auto"

HOME_DIR = Path.home()
LOG_DIR = HOME_DIR / ".cache" / "linux-auto"
WINDOW_STATE_PATH = HOME_DIR / ".config" / "linux-auto" / "window.json"
LEGACY_UNIT_PATH = HOME_DIR / ".config" / "systemd" / "user" / SERVICE_NAME
LEGACY_MENU_ENTRY = HOME_DIR / ".local" / "share" / "applications" / "linux-auto.desktop"
PACKAGED_DESKTOP_FILE = Path("/usr/share/applications/linux-auto.desktop")

DEFAULT_WIDTH, DEFAULT_HEIGHT = 1280, 800
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 0.5, 3.0, 0.1
# サーバーの応答を待つ秒数 (これを過ぎると待機画面にヒントを表示)
SERVER_WAIT_SEC = 20

# 環境変数 http_proxy が設定されていても 127.0.0.1 へは直接つなぐ (プロキシを使わない opener)
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


# =============================================================================
# 共通ヘルパー
# =============================================================================
def log(message):
    print(f"[Linux Auto] {message}", flush=True)


def notify(message):
    """デスクトップ通知 (notify-send があれば) + 標準出力"""
    log(message)
    if shutil.which("notify-send"):
        try:
            subprocess.Popen(
                ["notify-send", "-a", "Linux Auto", "-i", str(ICON_PATH), "Linux Auto", message],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass


def server_is_up(timeout=1.0):
    """サーバー (app.py) が応答しているか確認します。"""
    try:
        with _DIRECT_OPENER.open(BASE_URL + "api/status", timeout=timeout) as res:
            return res.status == 200
    except Exception:
        return False


def server_instance_id(timeout=1.0):
    """サーバーの起動ごとに変わる ID を返します (応答なし / 旧バージョンのサーバーは None)。"""
    try:
        with _DIRECT_OPENER.open(BASE_URL + "api/status", timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8")).get("server_id")
    except Exception:
        return None


class RestartWatcher:
    """サーバーの再起動 (deb の更新・サービスの再起動) を検知して、画面の読み込み直しを指示します。
    数秒おきに check() を呼び、True が返ったら画面を読み込み直します。"""

    INTERVAL_MS = 3000

    def __init__(self):
        self.known_id = None

    def reset(self):
        self.known_id = server_instance_id(timeout=0.5)

    def check(self):
        current = server_instance_id(timeout=0.5)
        if current is None:
            return False  # 停止中・再起動中 (応答が戻るまで待つ)
        if self.known_id is None:
            self.known_id = current
            return False
        if current != self.known_id:
            self.known_id = current
            log("サーバーの再起動を検知したため、画面を読み込み直します")
            return True
        return False


def wait_for_server(limit_sec):
    deadline = time.time() + limit_sec
    while time.time() < deadline:
        if server_is_up(timeout=0.5):
            return True
        time.sleep(0.25)
    return server_is_up(timeout=0.5)


def is_internal_url(url):
    """Linux Auto 自身の画面の URL か (それ以外のリンクは普段のブラウザで開く)"""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme in ("about", "data", "blob"):
        return True
    return parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost") and parsed.port == PORT


def open_external(url):
    """外部リンク (GitHub やホームページ) は普段使いのブラウザで開く"""
    try:
        if shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        else:
            import webbrowser
            webbrowser.open(url)
    except Exception as e:
        log(f"リンクを開けませんでした: {url} ({e})")


def run_quiet(cmd, timeout=15):
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, universal_newlines=True)
    except (OSError, subprocess.SubprocessError):
        return None


def service_is_registered():
    if not shutil.which("systemctl"):
        return False
    res = run_quiet(["systemctl", "--user", "cat", SERVICE_NAME])
    return res is not None and res.returncode == 0


def start_server_if_needed():
    """サーバーが止まっていれば起動します (起動完了は待たない。画面側で待機・再試行する)。"""
    if server_is_up():
        return
    if service_is_registered():
        log(f"サーバーが停止しているため {SERVICE_NAME} を起動します...")
        res = run_quiet(["systemctl", "--user", "start", SERVICE_NAME])
        if res is not None and res.returncode == 0:
            return
        log("サービスを起動できなかったため、サーバーを一時的にバックグラウンド起動します...")
    else:
        log("サービス未登録のため、サーバーを一時的にバックグラウンド起動します...")
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / "server.log", "ab") as log_file:
            subprocess.Popen(
                [sys.executable, str(APP_PY), "--no-browser", "--port", str(PORT)],
                stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT,
                cwd=str(APP_DIR), start_new_session=True,
            )
    except OSError as e:
        notify(f"サーバーを起動できませんでした: {e}")


def open_in_browser():
    if not wait_for_server(15):
        notify(f"サーバーを起動できませんでした。'systemctl --user status {SERVICE_NAME}' "
               f"または {LOG_DIR / 'server.log'} を確認してください。")
        return 1
    open_external(BASE_URL)
    return 0


# -----------------------------------------------------------------------------
# ウィンドウの状態 (位置・サイズ・倍率・全画面) の保存
# -----------------------------------------------------------------------------
def load_window_state():
    try:
        with open(WINDOW_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_window_state(state):
    try:
        WINDOW_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = WINDOW_STATE_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, WINDOW_STATE_PATH)
    except OSError as e:
        log(f"ウィンドウの状態を保存できませんでした: {e}")


def clamp_zoom(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 1.0
    return round(max(ZOOM_MIN, min(ZOOM_MAX, value)), 2)


def waiting_page_html(elapsed_sec):
    """サーバーの起動・再起動を待っている間に表示するページ"""
    hint = ""
    if elapsed_sec >= SERVER_WAIT_SEC:
        hint = (
            "<p class='hint'>サーバーに接続できません。ターミナルで次のコマンドを実行して状態を確認してください。<br>"
            f"<code>systemctl --user status {SERVICE_NAME}</code><br>"
            f"<code>journalctl --user -u {SERVICE_NAME} -e</code></p>"
        )
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><title>{WINDOW_TITLE}</title>
<style>
  html, body {{ height: 100%; margin: 0; background: #0f141c; color: #d8e0ea;
    font-family: "Noto Sans CJK JP", "Noto Sans JP", sans-serif; }}
  body {{ display: flex; align-items: center; justify-content: center; text-align: center; }}
  .spinner {{ width: 48px; height: 48px; margin: 0 auto 24px; border-radius: 50%;
    border: 4px solid #2a3646; border-top-color: #4fa3ff; animation: spin 1s linear infinite; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  h1 {{ font-size: 20px; font-weight: 600; margin: 0 0 8px; }}
  p {{ margin: 4px 0; color: #8a98aa; }}
  .hint {{ margin-top: 24px; color: #e8b04f; line-height: 1.8; }}
  code {{ background: #18202c; padding: 2px 8px; border-radius: 4px; color: #d8e0ea; }}
</style></head>
<body><div>
  <div class="spinner"></div>
  <h1>Linux Auto サーバーの起動を待っています…</h1>
  <p>起動すると自動で画面が表示されます</p>
  {hint}
</div></body></html>"""


# =============================================================================
# 旧方式 (git のフォルダから install-service.sh 等で登録) の検出と移行
# =============================================================================
def desktop_dir():
    """デスクトップフォルダ (日本語環境では ~/デスクトップ の場合がある)"""
    if shutil.which("xdg-user-dir"):
        res = run_quiet(["xdg-user-dir", "DESKTOP"], timeout=5)
        if res is not None and res.returncode == 0 and res.stdout.strip():
            return Path(res.stdout.strip())
    return HOME_DIR / "Desktop"


def is_legacy_entry(path):
    """install-desktop-shortcut.sh が作った (open-ui.sh を起動する) .desktop か"""
    try:
        return path.is_file() and "open-ui.sh" in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def find_legacy_items():
    items = []
    if LEGACY_UNIT_PATH.is_file():
        items.append(LEGACY_UNIT_PATH)
    for path in (LEGACY_MENU_ENTRY, desktop_dir() / "linux-auto.desktop"):
        if is_legacy_entry(path):
            items.append(path)
    return items


def warn_legacy():
    items = find_legacy_items()
    if not items:
        return
    log("旧方式 (git のフォルダから登録) の設定が残っています:")
    for path in items:
        log(f"  - {path}")
    if LEGACY_UNIT_PATH in items:
        notify("旧方式で登録したサービスが残っているため、古い Linux Auto が動いています。"
               "ターミナルで「linux-auto --migrate」を実行して deb 版に切り替えてください。")
    else:
        log("ターミナルで「linux-auto --migrate」を実行すると整理できます。")


def backup_path(path, suffix):
    target = path.with_name(path.name + suffix)
    if target.exists():
        target = path.with_name(f"{path.name}{suffix}.{time.strftime('%Y%m%d%H%M%S')}")
    return target


def migrate_legacy():
    """旧方式の登録を無効化して、deb 版のサービスとアイコンに切り替えます。"""
    if not IS_PACKAGED:
        log(f"--migrate は deb パッケージ版 ({PACKAGED_DIR}) から実行してください。")
        return 1
    changed = False

    # 1. ~/.config/systemd/user/linux-auto.service (旧サービス) を退避
    #    これが残っていると、deb 版 (/usr/lib/systemd/user/) より優先されて古いコードが動き続ける
    if LEGACY_UNIT_PATH.is_file():
        log("旧サービスを停止・無効化します...")
        run_quiet(["systemctl", "--user", "disable", "--now", SERVICE_NAME], timeout=30)
        target = backup_path(LEGACY_UNIT_PATH, ".removed")
        LEGACY_UNIT_PATH.rename(target)
        log(f"  旧サービスの定義を退避しました: {target}")
        run_quiet(["systemctl", "--user", "daemon-reload"])
        changed = True

    # 2. アプリメニューの旧アイコン (open-ui.sh = ブラウザで開く) を退避
    #    同じファイル名の deb 版 (/usr/share/applications/) より優先されてしまうため
    if is_legacy_entry(LEGACY_MENU_ENTRY):
        target = backup_path(LEGACY_MENU_ENTRY, ".disabled")
        LEGACY_MENU_ENTRY.rename(target)
        log(f"  アプリメニューの旧アイコンを退避しました: {target}")
        changed = True

    # 3. デスクトップの旧アイコンは、deb 版 (専用ウィンドウで開く) の内容に置き換える
    desktop_entry = desktop_dir() / "linux-auto.desktop"
    if is_legacy_entry(desktop_entry) and PACKAGED_DESKTOP_FILE.is_file():
        shutil.copyfile(str(PACKAGED_DESKTOP_FILE), str(desktop_entry))
        desktop_entry.chmod(0o755)
        if shutil.which("gio"):
            run_quiet(["gio", "set", str(desktop_entry), "metadata::trusted", "true"], timeout=5)
        log(f"  デスクトップのアイコンを deb 版に置き換えました: {desktop_entry}")
        changed = True

    if shutil.which("update-desktop-database"):
        run_quiet(["update-desktop-database", str(LEGACY_MENU_ENTRY.parent)], timeout=15)

    # 4. deb 版のサービスを起動
    if shutil.which("systemctl"):
        run_quiet(["systemctl", "--user", "daemon-reload"])
        res = run_quiet(["systemctl", "--user", "start", SERVICE_NAME], timeout=30)
        if res is not None and res.returncode == 0:
            log(f"deb 版のサービスを起動しました ({SERVICE_NAME})")
        else:
            log(f"サービスを起動できませんでした: systemctl --user status {SERVICE_NAME} を確認してください")

    if changed:
        log("移行が完了しました。git のフォルダ (例: ~/LinuxAuto) は不要なら削除してかまいません。")
        log("設定 (~/.config/linux-auto/ と ~/.android/headunit.ini) はそのまま引き継がれます。")
    else:
        log("旧方式の登録は見つかりませんでした。移行の必要はありません。")
    return 0


# =============================================================================
# 専用ウィンドウ (1): Qt WebEngine (PyQt6 / PyQt5)
# =============================================================================
def import_qt(major):
    """PyQt6 / PyQt5 の必要なクラスをまとめて読み込みます (無ければ ImportError)。"""
    from types import SimpleNamespace
    if major == 6:
        from PyQt6.QtCore import Qt, QUrl, QByteArray, QCoreApplication, QTimer
        from PyQt6.QtGui import QIcon, QDesktopServices, QKeySequence, QShortcut
        from PyQt6.QtWidgets import QApplication, QMainWindow
        from PyQt6.QtNetwork import QLocalServer, QLocalSocket
        from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        no_cache = QWebEngineProfile.HttpCacheType.NoCache
        share_gl = Qt.ApplicationAttribute.AA_ShareOpenGLContexts
    else:
        from PyQt5.QtCore import Qt, QUrl, QByteArray, QCoreApplication, QTimer
        from PyQt5.QtGui import QIcon, QDesktopServices, QKeySequence
        from PyQt5.QtWidgets import QApplication, QMainWindow, QShortcut
        from PyQt5.QtNetwork import QLocalServer, QLocalSocket
        from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineProfile
        no_cache = QWebEngineProfile.NoCache
        share_gl = Qt.AA_ShareOpenGLContexts
    return SimpleNamespace(**locals())


def run_qt(qt, args):
    # QtWebEngine は QApplication より前に設定が必要
    qt.QCoreApplication.setAttribute(qt.share_gl)
    qt.QCoreApplication.setApplicationName(APP_ID)
    app = qt.QApplication([APP_ID])  # argv[0] が X11 の WM_CLASS になる (.desktop の StartupWMClass と一致させる)
    app.setDesktopFileName(APP_ID)
    icon = qt.QIcon.fromTheme(APP_ID, qt.QIcon(str(ICON_PATH)))
    app.setWindowIcon(icon)

    # --- 二重起動の防止: すでにウィンドウがあれば前面に出してもらって終了 ---
    instance_name = f"linux-auto-window-{os.getuid()}"
    probe = qt.QLocalSocket()
    probe.connectToServer(instance_name)
    if probe.waitForConnected(500):
        probe.write(b"raise")
        probe.flush()
        probe.waitForBytesWritten(500)
        probe.disconnectFromServer()
        log("すでに開いているウィンドウを前面に表示しました。")
        return 0
    qt.QLocalServer.removeServer(instance_name)  # 異常終了で残ったソケットを掃除
    instance_server = qt.QLocalServer()
    instance_server.listen(instance_name)

    # --- 画面の保存先 (localStorage 等) を持つプロファイル ---
    # ※ Qt6 の既定プロファイルは「保存しない (シークレット)」なので名前付きプロファイルを作る
    profile = qt.QWebEngineProfile("linux-auto", app)
    # 更新 (deb の入れ替え) 後に古い画面が残らないよう HTTP キャッシュは使わない (localhost なので速度差なし)
    profile.setHttpCacheType(qt.no_cache)

    class Page(qt.QWebEnginePage):
        """外部リンクは普段のブラウザで、Linux Auto 自身の画面はこのウィンドウで開く"""

        def __init__(self, profile, parent=None):
            super().__init__(profile, parent)
            self._popups = []

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            text = url.toString()
            if is_internal_url(text):
                return True
            open_external(text)
            return False

        def createWindow(self, window_type):
            # target="_blank" や window.open(): 仮のページで URL だけ受け取って振り分ける
            popup = qt.QWebEnginePage(self.profile(), self)
            self._popups.append(popup)

            def on_url_changed(u):
                text = u.toString()
                if not text or text == "about:blank":
                    return
                if is_internal_url(text):
                    self.setUrl(u)
                else:
                    open_external(text)
                self._popups.remove(popup)
                popup.deleteLater()

            popup.urlChanged.connect(on_url_changed)
            return popup

        def javaScriptConsoleMessage(self, level, message, line, source):
            if os.environ.get("LINUX_AUTO_DEBUG"):
                log(f"[JS] {source}:{line} {message}")

    class MainWindow(qt.QMainWindow):
        def __init__(self):
            super().__init__()
            self.state = load_window_state()
            self.setWindowTitle(WINDOW_TITLE)
            self.setWindowIcon(icon)
            self.setMinimumSize(480, 360)

            self.view = qt.QWebEngineView(self)
            self.page = Page(profile, self.view)
            self.view.setPage(self.page)
            self.view.setZoomFactor(clamp_zoom(self.state.get("zoom", 1.0)))
            self.setCentralWidget(self.view)

            geometry = self.state.get("qt_geometry")
            restored = False
            if isinstance(geometry, str) and geometry:
                try:
                    restored = self.restoreGeometry(qt.QByteArray.fromHex(geometry.encode("ascii")))
                except Exception:
                    restored = False
            if not restored:
                self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)

            for keys, handler in (
                ("F11", self.toggle_fullscreen),
                ("F5", self.reload_page),
                ("Ctrl+R", self.reload_page),
                ("Ctrl++", lambda: self.change_zoom(ZOOM_STEP)),
                ("Ctrl+=", lambda: self.change_zoom(ZOOM_STEP)),
                ("Ctrl+-", lambda: self.change_zoom(-ZOOM_STEP)),
                ("Ctrl+0", lambda: self.change_zoom(None)),
                ("Ctrl+Q", self.close),
            ):
                shortcut = qt.QShortcut(qt.QKeySequence(keys), self)
                shortcut.activated.connect(handler)

            # サーバーの起動・再起動待ち
            self.waiting = False
            self.wait_started = time.time()
            self.retry_timer = qt.QTimer(self)
            self.retry_timer.setInterval(1000)
            self.retry_timer.timeout.connect(self.try_load)
            self.page.loadFinished.connect(self.on_load_finished)

            # サーバーの再起動 (deb の更新など) を検知したら新しい画面を読み込み直す
            self.watcher = RestartWatcher()
            self.watch_timer = qt.QTimer(self)
            self.watch_timer.setInterval(RestartWatcher.INTERVAL_MS)
            self.watch_timer.timeout.connect(self.check_restart)
            self.watch_timer.start()
            self.try_load()

        # --- 読み込み・再試行 ---
        def check_restart(self):
            if not self.waiting and self.watcher.check():
                self.view.setUrl(qt.QUrl(BASE_URL))

        def try_load(self):
            if server_is_up(timeout=0.5):
                self.retry_timer.stop()
                self.waiting = False
                self.watcher.reset()
                self.view.setUrl(qt.QUrl(BASE_URL))
                return
            if not self.waiting:
                self.waiting = True
                self.wait_started = time.time()
            self.page.setHtml(waiting_page_html(time.time() - self.wait_started))
            if not self.retry_timer.isActive():
                self.retry_timer.start()

        def on_load_finished(self, ok):
            # 読み込みに失敗し、かつサーバーが落ちている場合だけ待機画面に切り替える
            if not ok and not self.waiting and not server_is_up(timeout=0.5):
                self.try_load()

        def reload_page(self):
            if self.waiting:
                self.try_load()
            else:
                self.view.reload()

        # --- 表示 ---
        def change_zoom(self, delta):
            zoom = 1.0 if delta is None else clamp_zoom(self.view.zoomFactor() + delta)
            self.view.setZoomFactor(zoom)

        def toggle_fullscreen(self):
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()

        def bring_to_front(self):
            if self.isMinimized():
                self.showNormal()
            self.show()
            self.raise_()
            self.activateWindow()

        def closeEvent(self, event):
            state = load_window_state()
            state["zoom"] = clamp_zoom(self.view.zoomFactor())
            state["fullscreen"] = self.isFullScreen()
            if not self.isFullScreen():
                state["qt_geometry"] = bytes(self.saveGeometry().toHex()).decode("ascii")
            save_window_state(state)
            super().closeEvent(event)

    window = MainWindow()
    holder = {"window": window}

    def on_new_instance():
        conn = instance_server.nextPendingConnection()
        if conn is not None:
            conn.disconnected.connect(conn.deleteLater)
        if holder.get("window") is not None:
            holder["window"].bring_to_front()

    instance_server.newConnection.connect(on_new_instance)

    # ログアウト時 (SIGTERM) や Ctrl+C でも、ウィンドウの状態を保存してから終了する
    # (Qt のイベントループ中も Python のシグナル処理が動くよう、定期的に制御を戻す)
    import signal

    def on_signal(*_):
        if holder.get("window") is not None:
            holder["window"].close()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    signal_pump = qt.QTimer()
    signal_pump.timeout.connect(lambda: None)
    signal_pump.start(500)

    fullscreen = window.state.get("fullscreen", False)
    if args.fullscreen:
        fullscreen = True
    elif args.windowed:
        fullscreen = False
    if fullscreen:
        window.showFullScreen()
    else:
        window.show()

    exec_fn = getattr(app, "exec", None) or getattr(app, "exec_")
    code = exec_fn()
    instance_server.close()
    # ページ → プロファイルの順に破棄する (逆順だと Qt が "Release of profile requested..." と警告する)
    holder.clear()
    del window
    import gc
    gc.collect()
    return code


# =============================================================================
# 専用ウィンドウ (2): WebKitGTK (Qt が無い GNOME 環境向け)
# =============================================================================
def import_gtk():
    import gi
    gi.require_version("Gtk", "3.0")
    for version in ("4.1", "4.0"):
        try:
            gi.require_version("WebKit2", version)
            break
        except ValueError:
            continue
    else:
        raise ImportError("WebKit2 (gir1.2-webkit2-4.1) が見つかりません")
    from gi.repository import Gtk, Gdk, Gio, GLib, WebKit2
    from types import SimpleNamespace
    return SimpleNamespace(Gtk=Gtk, Gdk=Gdk, Gio=Gio, GLib=GLib, WebKit2=WebKit2)


def run_gtk(g, args):
    Gtk, Gdk, Gio, GLib, WebKit2 = g.Gtk, g.Gdk, g.Gio, g.GLib, g.WebKit2
    GLib.set_prgname(APP_ID)
    GLib.set_application_name(WINDOW_TITLE)
    # Gtk.Application が同じ ID の起動を検出し、既存ウィンドウを前面に出す (二重起動の防止)
    app = Gtk.Application(application_id=GTK_APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)

    def on_activate(application):
        windows = application.get_windows()
        if windows:
            windows[0].present()
            return

        state = load_window_state()
        win = Gtk.ApplicationWindow(application=application, title=WINDOW_TITLE)
        try:
            win.set_icon_from_file(str(ICON_PATH))
        except Exception:
            pass
        size = state.get("gtk_size") or [DEFAULT_WIDTH, DEFAULT_HEIGHT]
        try:
            win.set_default_size(int(size[0]), int(size[1]))
        except (TypeError, ValueError, IndexError):
            win.set_default_size(DEFAULT_WIDTH, DEFAULT_HEIGHT)
        if state.get("gtk_maximized"):
            win.maximize()

        context = WebKit2.WebContext.get_default()
        # 更新後に古い画面が残らないようキャッシュを最小にする
        context.set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)
        view = WebKit2.WebView()
        view.set_zoom_level(clamp_zoom(state.get("zoom", 1.0)))
        win.add(view)

        status = {"waiting": False, "since": time.time(), "timer": None, "fullscreen": False}
        watcher = RestartWatcher()

        def on_watch():
            # サーバーの再起動 (deb の更新など) を検知したら新しい画面を読み込み直す
            if not status["waiting"] and watcher.check():
                view.load_uri(BASE_URL)
            return True

        GLib.timeout_add(RestartWatcher.INTERVAL_MS, on_watch)

        def try_load(from_timer=False):
            if server_is_up(timeout=0.5):
                status["waiting"] = False
                watcher.reset()
                if status["timer"] is not None:
                    if not from_timer:  # タイマー内から呼ばれた場合は False を返して終了させる
                        GLib.source_remove(status["timer"])
                    status["timer"] = None
                view.load_uri(BASE_URL)
                return False
            if not status["waiting"]:
                status["waiting"] = True
                status["since"] = time.time()
            view.load_html(waiting_page_html(time.time() - status["since"]), None)
            if status["timer"] is None:
                status["timer"] = GLib.timeout_add(1000, on_tick)
            return False

        def on_tick():
            try_load(from_timer=True)
            return status["timer"] is not None  # 読み込めたらタイマー終了

        def on_load_failed(_view, _event, uri, _error):
            if not status["waiting"] and not server_is_up(timeout=0.5):
                GLib.idle_add(try_load)
                return True  # 標準のエラーページは出さない
            return False

        def on_decide_policy(_view, decision, decision_type):
            if decision_type not in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION,
                                     WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
                return False
            uri = decision.get_navigation_action().get_request().get_uri() or ""
            if is_internal_url(uri):
                if decision_type == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION:
                    view.load_uri(uri)
                    decision.ignore()
                    return True
                return False
            open_external(uri)
            decision.ignore()
            return True

        def on_key_press(_widget, event):
            ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
            key = event.keyval
            if key == Gdk.KEY_F11:
                if status["fullscreen"]:
                    win.unfullscreen()
                else:
                    win.fullscreen()
            elif key == Gdk.KEY_F5 or (ctrl and key in (Gdk.KEY_r, Gdk.KEY_R)):
                if status["waiting"]:
                    try_load()
                else:
                    view.reload()
            elif ctrl and key in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
                view.set_zoom_level(clamp_zoom(view.get_zoom_level() + ZOOM_STEP))
            elif ctrl and key in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
                view.set_zoom_level(clamp_zoom(view.get_zoom_level() - ZOOM_STEP))
            elif ctrl and key in (Gdk.KEY_0, Gdk.KEY_KP_0):
                view.set_zoom_level(1.0)
            elif ctrl and key in (Gdk.KEY_q, Gdk.KEY_Q):
                win.close()
            else:
                return False
            return True

        def on_window_state(_widget, event):
            status["fullscreen"] = bool(event.new_window_state & Gdk.WindowState.FULLSCREEN)
            return False

        def on_delete(_widget, _event):
            saved = load_window_state()
            saved["zoom"] = clamp_zoom(view.get_zoom_level())
            saved["fullscreen"] = status["fullscreen"]
            saved["gtk_maximized"] = win.is_maximized()
            if not status["fullscreen"] and not win.is_maximized():
                width, height = win.get_size()
                saved["gtk_size"] = [width, height]
            save_window_state(saved)
            return False

        view.connect("load-failed", on_load_failed)
        view.connect("decide-policy", on_decide_policy)
        win.connect("key-press-event", on_key_press)
        win.connect("window-state-event", on_window_state)
        win.connect("delete-event", on_delete)

        fullscreen = state.get("fullscreen", False)
        if args.fullscreen:
            fullscreen = True
        elif args.windowed:
            fullscreen = False
        win.show_all()
        if fullscreen:
            win.fullscreen()
        try_load()

    app.connect("activate", on_activate)
    return app.run([sys.argv[0]])


# =============================================================================
# メイン
# =============================================================================
TOOLKITS = {
    "qt6": (lambda: import_qt(6), run_qt, "PyQt6 + Qt WebEngine"),
    "qt5": (lambda: import_qt(5), run_qt, "PyQt5 + Qt WebEngine"),
    "gtk": (import_gtk, run_gtk, "WebKitGTK"),
}


def parse_args():
    parser = argparse.ArgumentParser(
        prog="linux-auto",
        description="Linux Auto の画面を専用ウィンドウで開きます (サーバーが止まっていれば起動します)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fullscreen", "-f", action="store_true", help="全画面で開く")
    mode.add_argument("--windowed", "-w", action="store_true", help="ウィンドウで開く (全画面にしない)")
    parser.add_argument("--browser", "-b", action="store_true", help="専用ウィンドウを使わずブラウザで開く")
    parser.add_argument("--toolkit", choices=sorted(TOOLKITS),
                        default=os.environ.get("LINUX_AUTO_TOOLKIT") or None,
                        help="使う部品を指定する (既定: qt6 → qt5 → gtk の順に自動選択)")
    parser.add_argument("--disable-gpu", action="store_true",
                        help="画面が真っ黒・ちらつく場合に GPU 描画を無効化する")
    parser.add_argument("--migrate", action="store_true",
                        help="旧方式 (install-service.sh 等) の登録を無効化して deb 版に切り替える")
    args = parser.parse_args()
    if args.toolkit and args.toolkit not in TOOLKITS:
        parser.error(f"--toolkit は {', '.join(sorted(TOOLKITS))} のいずれかを指定してください")
    return args


def main():
    args = parse_args()

    if args.migrate:
        return migrate_legacy()

    if IS_PACKAGED:
        warn_legacy()

    start_server_if_needed()

    if args.browser:
        return open_in_browser()

    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        log("デスクトップの画面 (DISPLAY / WAYLAND_DISPLAY) が見つかりません。デスクトップにログインした状態で実行してください。")
        return 1

    if args.disable_gpu:
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (flags + " --disable-gpu").strip()
        os.environ["WEBKIT_DISABLE_COMPOSITING_MODE"] = "1"

    order = [args.toolkit] if args.toolkit else ["qt6", "qt5", "gtk"]
    for name in order:
        importer, runner, label = TOOLKITS[name]
        try:
            toolkit = importer()
        except Exception as e:  # ImportError / ValueError (gi のバージョン違い) など
            log(f"{label} は使えません ({e.__class__.__name__}: {e})")
            continue
        log(f"{label} で画面を開きます")
        return runner(toolkit, args)

    notify("専用ウィンドウ用の部品が見つからないため、ブラウザで開きます。"
           "「sudo apt install python3-pyqt6.qtwebengine」で専用ウィンドウが使えるようになります。")
    return open_in_browser()


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        sys.exit(130)
