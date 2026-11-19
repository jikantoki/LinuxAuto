#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================================================
プロジェクト名: Linux Auto
開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
GitHub: https://github.com/jikantoki

【概要】
Ubuntu/Kubuntu環境において、Google Desktop Head Unit (DHU) を使用した
Android Auto有線接続をGUIから簡単に管理・実行するためのローカルWebサーバーです。

【技術的特長（外部依存ゼロ・Zero-Dependency）】
pip等によるサードパーティ製ライブラリを一切使わず、Python 3.6以降の標準ライブラリ
（http.server, subprocess, configparser, json, threading 等）のみで実装しています。
これにより、UbuntuのバージョンアップやPythonの環境更新による依存関係破壊・
バージョン管理地獄を回避し、年単位で安定して動作し続ける設計としています。

【Webエンジニア（Node.js / PHP / Spring Boot）向けの補足注釈】
コード内の各所に、JavaScript(Node.js/Express)やPHP、Java(Spring Boot)での
同等概念との比較コメントを記載しています。
=============================================================================
"""

import os
import sys
import json
import time
import shutil
import signal
import argparse
import threading
import subprocess
import configparser
import webbrowser
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# =============================================================================
# 定数・パス定義
# =============================================================================
PORT = 8855
HOST = "127.0.0.1"

# ユーザーのホームディレクトリの取得（Node.jsの os.homedir() や PHPの $_SERVER['HOME'] に相当）
HOME_DIR = Path.home()

# Google DHUの設定ファイルパス (~/.android/headunit.ini)
HEADUNIT_INI_PATH = HOME_DIR / ".android" / "headunit.ini"

# Linux Auto 独自の設定ファイルパス (~/.config/linux-auto/config.json)
APP_CONFIG_DIR = HOME_DIR / ".config" / "linux-auto"
APP_CONFIG_PATH = APP_CONFIG_DIR / "config.json"

# 静的ファイル（HTML/CSS/JS）が配置されるディレクトリ
STATIC_DIR = Path(__file__).resolve().parent / "static"


# =============================================================================
# 設定管理クラス (Configuration Manager)
# =============================================================================
class ConfigManager:
    """
    ~/.android/headunit.ini および アプリ設定 (config.json) を安全に読み書きするクラス。
    Spring Bootの @Configuration や Service クラスに相当する役割です。
    """

    DEFAULT_INI = {
        "general": {
            "touch": "true",
            "touchpad": "false",
            "resolution": "1920x1080",
            "dpi": "280",
            "framerate": "30",
        }
    }

    @staticmethod
    def find_default_dhu_path():
        """
        Linux環境における desktop-head-unit 実行ファイルの標準パスを自動探索します。
        """
        # 1. PATHが通っているか確認 (which desktop-head-unit に相当)
        which_path = shutil.which("desktop-head-unit")
        if which_path:
            return which_path

        # 2. Android SDKの標準的なインストール場所を順にチェック
        sdk_candidates = [
            HOME_DIR / "Android" / "Sdk",
            HOME_DIR / "AndroidSdk",
            HOME_DIR / ".android-sdk",
            Path("/usr/lib/android-sdk"),
            Path("/opt/android-sdk"),
        ]

        # 環境変数 ANDROID_HOME や ANDROID_SDK_ROOT も確認
        for env_var in ["ANDROID_HOME", "ANDROID_SDK_ROOT"]:
            if env_var in os.environ and os.environ[env_var]:
                sdk_candidates.insert(0, Path(os.environ[env_var]))

        for sdk in sdk_candidates:
            dhu = sdk / "extras" / "google" / "auto" / "desktop-head-unit"
            if dhu.is_file() and os.access(str(dhu), os.X_OK):
                return str(dhu)

        # 見つからなかった場合の推奨デフォルトパス
        return str(HOME_DIR / "Android" / "Sdk" / "extras" / "google" / "auto" / "desktop-head-unit")

    @classmethod
    def load_app_config(cls):
        """
        Linux Auto自体の設定 (config.json) を読み込みます。
        """
        default_config = {
            "dhu_path": cls.find_default_dhu_path(),
            "auto_retry": True,
            "retry_seconds": 10,
        }

        if not APP_CONFIG_PATH.exists():
            return default_config

        try:
            with open(APP_CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                default_config.update(saved)
                return default_config
        except Exception as e:
            print(f"[WARN] Failed to load app config: {e}", file=sys.stderr)
            return default_config

    @classmethod
    def save_app_config(cls, data):
        """
        Linux Auto自体の設定 (config.json) を保存します。
        """
        APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        current = cls.load_app_config()
        current.update(data)
        with open(APP_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
        return current

    @classmethod
    def load_headunit_ini(cls):
        """
        ~/.android/headunit.ini を読み込み、辞書型(JSON互換)で返します。
        大文字[General]・小文字[general]の両方に対応します。
        """
        config = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
        
        # ファイルが存在しない場合はデフォルト値を生成して保存
        if not HEADUNIT_INI_PATH.exists():
            cls.save_headunit_ini(cls.DEFAULT_INI["general"])
            return cls.DEFAULT_INI["general"]

        try:
            config.read(str(HEADUNIT_INI_PATH), encoding="utf-8")
            target_sec = None
            if "general" in config:
                target_sec = "general"
            elif "General" in config:
                target_sec = "General"

            if target_sec:
                general = {}
                for k, v in config[target_sec].items():
                    # 行末コメントや余計な空白を徹底的に除去
                    cleaned_val = v.split("#")[0].split(";")[0].strip()
                    general[k] = cleaned_val
                return general
            else:
                return cls.DEFAULT_INI["general"]
        except Exception as e:
            print(f"[WARN] Failed to read headunit.ini: {e}", file=sys.stderr)
            return cls.DEFAULT_INI["general"]

    @classmethod
    def save_headunit_ini(cls, general_data):
        """
        ~/.android/headunit.ini に設定を保存します。
        Google DHUの公式仕様に準拠し、小文字 [general] かつコメントなしで書き出します。
        """
        HEADUNIT_INI_PATH.parent.mkdir(parents=True, exist_ok=True)

        touch = "true" if str(general_data.get("touch", "true")).lower() in ["true", "1"] else "false"
        touchpad = "true" if str(general_data.get("touchpad", "false")).lower() in ["true", "1"] else "false"
        resolution = str(general_data.get("resolution", "1920x1080")).strip()
        dpi = str(general_data.get("dpi", "280")).strip()
        framerate = str(general_data.get("framerate", "30")).strip()

        # Google DHU公式仕様: [general]（小文字）でコメントなし
        content = (
            "[general]\n"
            f"touch = {touch}\n"
            f"touchpad = {touchpad}\n"
            f"resolution = {resolution}\n"
            f"dpi = {dpi}\n"
            f"framerate = {framerate}\n"
        )

        with open(HEADUNIT_INI_PATH, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "touch": touch,
            "touchpad": touchpad,
            "resolution": resolution,
            "dpi": dpi,
            "framerate": framerate,
        }


# =============================================================================
# DHUプロセス＆再接続監視コントローラー (Process Manager)
# =============================================================================
class DHUManager:
    """
    desktop-head-unit のプロセス起動、停止、死活監視、
    およびUSB切断時の『10秒間自動復帰ループ』を管理するシングルトン風クラス。
    
    【Node.jsとの比較】
    Node.jsの child_process.spawn() + setInterval によるプロセス監視に相当しますが、
    Pythonでは threading.Thread による独立したワーカースレッドで安全に監視ループを回します。
    """

    def __init__(self):
        self._lock = threading.Lock() # スレッドセーフのためのミューテックス（Javaの synchronized に相当）
        self.process = None           # 起動中の subprocess.Popen オブジェクト
        self.status = "IDLE"          # "IDLE" | "RUNNING" | "RECONNECTING" | "ERROR"
        self.user_stopped = False     # ユーザーの明示的な停止操作かどうかを識別するフラグ
        self.last_error = ""
        self.logs = []                # 最新のログ行を保持（リングバッファ）
        self.max_logs = 100
        self.retry_countdown = 0      # 再接続カウントダウン（残り秒数）
        self.monitor_thread = None

    def add_log(self, message):
        """タイムスタンプ付きでメモリ上のログ配列に追加します。"""
        timestamp = time.strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        with self._lock:
            self.logs.append(log_line)
            if len(self.logs) > self.max_logs:
                self.logs.pop(0)

    def get_status(self):
        """現在の接続状態をフロントエンドに返すための辞書を作成します。"""
        with self._lock:
            is_alive = False
            if self.process is not None:
                is_alive = (self.process.poll() is None)

            return {
                "status": self.status,
                "is_alive": is_alive,
                "pid": self.process.pid if is_alive else None,
                "retry_countdown": self.retry_countdown,
                "last_error": self.last_error,
                "logs": list(self.logs),
            }

    def start(self):
        """
        Android Auto (desktop-head-unit --usb) を起動します。
        すでに起動している場合は無視します。
        """
        with self._lock:
            if self.process is not None and self.process.poll() is None:
                return True, "すでに実行中です。"

            self.user_stopped = False
            self.status = "STARTING"
            self.retry_countdown = 0

        # アプリ設定から実行パスを取得
        config = ConfigManager.load_app_config()
        dhu_path = config.get("dhu_path", "").strip()

        if not dhu_path or not os.path.isfile(dhu_path):
            self.status = "ERROR"
            self.last_error = f"desktop-head-unitが見つかりません: {dhu_path}"
            self.add_log(f"[エラー] {self.last_error}")
            return False, self.last_error

        if not os.access(dhu_path, os.X_OK):
            self.status = "ERROR"
            self.last_error = f"desktop-head-unitに実行権限がありません: {dhu_path}"
            self.add_log(f"[エラー] {self.last_error}")
            return False, self.last_error

        # バックグラウンドの監視スレッドを起動
        self.monitor_thread = threading.Thread(
            target=self._run_and_monitor_loop,
            args=(dhu_path,),
            daemon=True
        )
        self.monitor_thread.start()
        return True, "起動を開始しました。"

    def stop(self):
        """
        ユーザーによる明示的な切断・終了処理。
        この場合、USB切断時の10秒自動復帰ループは発動させません。
        """
        self.add_log("[操作] 停止ボタンが押されました。")
        with self._lock:
            self.user_stopped = True
            self.retry_countdown = 0
            proc = self.process

        if proc is not None and proc.poll() is None:
            try:
                # 穏やかにSIGINT(Ctrl+C相当)を送信し、少し待って終了しなければSIGTERM/KILL
                proc.send_signal(signal.SIGINT)
                for _ in range(10):
                    if proc.poll() is not None:
                        break
                    time.sleep(0.2)
                if proc.poll() is None:
                    proc.terminate()
            except Exception as e:
                self.add_log(f"[警告] プロセス終了処理中の例外: {e}")

        with self._lock:
            self.process = None
            self.status = "IDLE"
        self.add_log("[状態] 停止しました。")
        return True, "停止しました。"

    def _run_and_monitor_loop(self, dhu_path):
        """
        【重要ロジック】
        DHUプロセスの実行と、USBケーブル抜け時の『10秒自動復帰』を制御する監視ループ。
        """
        while not self.user_stopped:
            cmd = [dhu_path, "--usb"]
            self.add_log(f"[実行] コマンド呼び出し: {' '.join(cmd)}")

            try:
                # subprocess.Popen で非同期にDHUを起動
                # 標準出力・エラー出力をパイプで受け取り、リアルタイムにログ化します
                # (Node.jsの spawn(cmd, ['--usb'], { stdio: 'pipe' }) と同等)
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1
                )
                with self._lock:
                    self.status = "RUNNING"
                    self.last_error = ""

                self.add_log(f"[接続] desktop-head-unit を起動しました (PID: {self.process.pid})")

                # 出力ログの読み取りループ
                if self.process.stdout:
                    for line in self.process.stdout:
                        clean_line = line.strip()
                        if clean_line:
                            self.add_log(f"[DHU] {clean_line}")

                self.process.wait()
                exit_code = self.process.returncode
                self.add_log(f"[終了] プロセスが終了しました (終了コード: {exit_code})")

            except Exception as e:
                self.add_log(f"[例外] DHU起動失敗: {e}")
                with self._lock:
                    self.status = "ERROR"
                    self.last_error = str(e)
                break

            # ユーザーが明示的に停止した場合はループを抜けて終了
            if self.user_stopped:
                break

            # =================================================================
            # 【要件】切断後10秒は再接続時に自動復帰を試みる
            # =================================================================
            self.add_log("[検知] 接続切断（USB抜け等の可能性）。10秒後に自動再接続を試みます...")
            with self._lock:
                self.status = "RECONNECTING"

            # 10秒カウントダウン（1秒ごとにユーザーキャンセルがないか確認）
            countdown_seconds = 10
            for sec in range(countdown_seconds, 0, -1):
                if self.user_stopped:
                    self.add_log("[中止] カウントダウン中に停止要求を受信しました。")
                    break
                with self._lock:
                    self.retry_countdown = sec
                time.sleep(1)

            with self._lock:
                self.retry_countdown = 0

            if self.user_stopped:
                break

            self.add_log("[再接続] 自動復帰を試行します...")

        with self._lock:
            self.status = "IDLE"
            self.process = None
            self.retry_countdown = 0


# グローバルなDHU管理インスタンス
dhu_manager = DHUManager()


# =============================================================================
# HTTPリクエストハンドラー (REST API + 静的Web配信)
# =============================================================================
class LinuxAutoHTTPHandler(SimpleHTTPRequestHandler):
    """
    Python標準の SimpleHTTPRequestHandler を拡張し、
    静的ファイル配信とREST APIエンドポイントを1つのクラスで処理します。
    
    【Node.js(Express)との対比】
    app.use(express.static('static'))
    app.get('/api/status', (req, res) => ...)
    app.post('/api/start', (req, res) => ...)
    と同じルーティングを do_GET() / do_POST() で実装しています。
    """

    # PWAに必要なMIMEタイプの補正
    extensions_map = SimpleHTTPRequestHandler.extensions_map.copy()
    extensions_map.update({
        ".webmanifest": "application/manifest+json",
        ".json": "application/json",
        ".js": "application/javascript",
        ".svg": "image/svg+xml",
    })

    def __init__(self, *args, **kwargs):
        # 静的ファイルのルートディレクトリを static/ に指定
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
        # Service Worker (sw.js) の更新をスムーズにするため、sw.jsのキャッシュを防止
        if self.path.endswith("sw.js"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Service-Worker-Allowed", "/")
        super().end_headers()

    def _send_json(self, status_code, data):
        """JSONレスポンスをクライアントに返却するヘルパー関数"""
        response_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        # ローカルツールのためキャッシュは無効化
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(response_bytes)

    def _read_json_body(self):
        """リクエストボディのJSONをパースするヘルパー関数"""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return {}
        raw_body = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        """GETリクエストのルーティング"""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        # API: 現在の状態取得
        if path == "/api/status":
            status_data = dhu_manager.get_status()
            self._send_json(200, status_data)
            return

        # API: 設定情報の取得 (headunit.ini + app_config)
        if path == "/api/config":
            ini_data = ConfigManager.load_headunit_ini()
            app_config = ConfigManager.load_app_config()
            self._send_json(200, {
                "headunit_ini": ini_data,
                "app_config": app_config,
                "ini_path": str(HEADUNIT_INI_PATH),
            })
            return

        # 静的ファイル（index.html, CSS, JS）の通常配信
        return super().do_GET()

    def do_POST(self):
        """POSTリクエストのルーティング"""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        # API: 接続開始
        if path == "/api/start":
            success, msg = dhu_manager.start()
            self._send_json(200 if success else 400, {
                "success": success,
                "message": msg,
                "status": dhu_manager.get_status(),
            })
            return

        # API: 接続停止
        if path == "/api/stop":
            success, msg = dhu_manager.stop()
            self._send_json(200, {
                "success": success,
                "message": msg,
                "status": dhu_manager.get_status(),
            })
            return

        # API: 設定の保存
        if path == "/api/config":
            payload = self._read_json_body()
            
            # headunit.ini の保存
            saved_ini = {}
            if "headunit_ini" in payload:
                saved_ini = ConfigManager.save_headunit_ini(payload["headunit_ini"])

            # app_config.json の保存
            saved_app = {}
            if "app_config" in payload:
                saved_app = ConfigManager.save_app_config(payload["app_config"])

            self._send_json(200, {
                "success": True,
                "message": "設定を保存しました。",
                "headunit_ini": saved_ini,
                "app_config": saved_app,
            })
            return

        # API: DHU実行ファイルの存在チェック
        if path == "/api/check-dhu":
            payload = self._read_json_body()
            target_path = payload.get("path", "").strip()
            exists = os.path.isfile(target_path)
            executable = os.access(target_path, os.X_OK) if exists else False
            self._send_json(200, {
                "exists": exists,
                "executable": executable,
                "valid": exists and executable,
            })
            return

        self._send_json(404, {"error": "Not Found"})


# =============================================================================
# サーバー起動メイン関数
# =============================================================================
def main():
    """
    アプリケーションのエントリーポイント。
    コマンドライン引数を解析し、HTTPサーバーを立ち上げます。
    """
    parser = argparse.ArgumentParser(
        description="Linux Auto - Android Auto Headunit Support GUI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--no-browser", "-n",
        action="store_true",
        help="自動起動時などにブラウザを自動で開かないようにする"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=PORT,
        help="WebUIの待ち受けポート番号"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=HOST,
        help="WebUIの待ち受けホストIP"
    )

    args = parser.parse_args()

    # 静的ファイル用ディレクトリの存在確認
    if not STATIC_DIR.exists():
        STATIC_DIR.mkdir(parents=True, exist_ok=True)

    server_address = (args.host, args.port)
    httpd = ThreadingHTTPServer(server_address, LinuxAutoHTTPHandler)

    url = f"http://{args.host}:{args.port}"
    print("=" * 60)
    print("   Linux Auto - Android Auto Headunit Support")
    print("   エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)")
    print("=" * 60)
    print(f" WebUIサーバー起動完了: {url}")
    if args.no_browser:
        print(" [情報] --no-browser オプション指定のため、ブラウザ自動起動をスキップしました。")
    print(" 終了するには Ctrl+C を押してください。")
    print("=" * 60)

    # ブラウザ自動オープン（--no-browser が指定されていない場合のみ）
    if not args.no_browser:
        def open_browser():
            time.sleep(0.8)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=open_browser, daemon=True).start()

    # シグナルハンドラ（Ctrl+Cでの正常終了処理）
    def shutdown_signal(signum, frame):
        print("\n[終了] シャットダウンシグナルを受信しました。終了します...")
        dhu_manager.stop()
        httpd.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_signal)
    signal.signal(signal.SIGTERM, shutdown_signal)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        dhu_manager.stop()
        httpd.server_close()
        print("[完了] サーバーを停止しました。")


if __name__ == "__main__":
    main()
