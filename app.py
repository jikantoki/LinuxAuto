#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================================================
プロジェクト名: Linux Auto
開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
GitHub: https://github.com/jikantoki/LinuxAuto

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
import re
import sys
import errno
import json
import time
import shutil
import signal
import socket
import struct
import argparse
import threading
import subprocess
import configparser
import ctypes
import ctypes.util
import webbrowser
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# =============================================================================
# 定数・パス定義
# =============================================================================
PORT = 8855
HOST = "127.0.0.1"

# Android Auto ヘッドユニットサーバー (スマホ側) の標準ポート
HU_SERVER_PORT = 5277
# 方法2 (adb forward) で PC 側に開くポート。DHU は引数なしだと localhost:5277 に接続する
ADB_FORWARD_LOCAL_PORT = 5277
# 方法1 (内蔵リレー経由) で PC 側に開くポート
RELAY_LOCAL_PORT = 5277
# Wi-Fi 接続時、DHU 起動からスマホの応答 (ハンドシェイク) を待つ秒数
HANDSHAKE_TIMEOUT_SEC = 20
# タッチ補正: ハンドシェイク成功から最大化し直すまでの待ち時間 (映像の表示開始を待つ)
TOUCH_FIX_DELAY_SEC = 1.5
# DHU が出力する色付けエスケープシーケンス (例: \x1b[38;5;34m) を除去する正規表現
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[[0-9;]+m")

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
            # ---- 接続方式 ----
            "connection_type": "usb",        # "usb" | "wifi"
            "wifi_mode": "direct",           # "direct" (方法1・既定) | "adb" (方法2)
            "phone_ip_auto": True,           # True: テザリング親機 (デフォルトゲートウェイ) を自動検出
            "phone_ip": "",                  # 手動指定時のスマホ IP
            "adb_port": 5555,                # 方法2: adb connect 先のポート
            "hu_port": HU_SERVER_PORT,       # ヘッドユニットサーバーのポート
            "direct_transport": "adb_flag",  # 方法1: "adb_flag" (--adb=IP:5277) | "relay" (内蔵リレー)
            "wifi_touch_fix": True,          # Wi-Fi 接続確立後に DHU ウィンドウを最大化し直してタッチを有効化
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
        current.update(cls.sanitize_app_config(data or {}))
        with open(APP_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
        return current

    @staticmethod
    def sanitize_app_config(data):
        """
        画面から送られた設定値を検証・型変換します (未知のキーは捨てる)。
        Spring Boot の @Validated による入力チェックに相当します。
        """
        clean = {}

        def to_port(value, default):
            try:
                v = int(value)
                return v if 1 <= v <= 65535 else default
            except (TypeError, ValueError):
                return default

        def to_bool(value):
            return str(value).lower() in ("true", "1", "yes", "on")

        if "dhu_path" in data:
            clean["dhu_path"] = str(data["dhu_path"]).strip()
        if "connection_type" in data:
            clean["connection_type"] = "wifi" if data["connection_type"] == "wifi" else "usb"
        if "wifi_mode" in data:
            clean["wifi_mode"] = "adb" if data["wifi_mode"] == "adb" else "direct"
        if "phone_ip_auto" in data:
            clean["phone_ip_auto"] = to_bool(data["phone_ip_auto"])
        if "phone_ip" in data:
            # IP アドレス / ホスト名として使える文字だけを許可
            clean["phone_ip"] = "".join(c for c in str(data["phone_ip"]).strip() if c.isalnum() or c in ".-:")
        if "adb_port" in data:
            clean["adb_port"] = to_port(data["adb_port"], 5555)
        if "hu_port" in data:
            clean["hu_port"] = to_port(data["hu_port"], HU_SERVER_PORT)
        if "direct_transport" in data:
            clean["direct_transport"] = "relay" if data["direct_transport"] == "relay" else "adb_flag"
        for key in ("auto_retry", "wifi_touch_fix"):
            if key in data:
                clean[key] = to_bool(data[key])
        return clean

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
# 実行モード判定 & グラフィカルセッション環境変数の取得
# =============================================================================
# DHU がウィンドウ・音声を出すために必要なデスクトップセッション側の環境変数
SESSION_ENV_KEYS = [
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XAUTHORITY",
    "XDG_RUNTIME_DIR",
    "XDG_SESSION_TYPE",
    "XDG_CURRENT_DESKTOP",
    "DBUS_SESSION_BUS_ADDRESS",
    "PULSE_SERVER",
]


def is_running_as_service():
    """
    systemd のサービスとして起動されているかを判定します。
    systemd は起動したプロセスに INVOCATION_ID を必ず付与するため、それで判別します。
    """
    return bool(os.environ.get("INVOCATION_ID"))


def get_systemd_user_session_env():
    """
    `systemctl --user show-environment` から、ログイン中のデスクトップセッションが
    systemd ユーザーマネージャーに登録した環境変数 (DISPLAY 等) を取得します。

    【なぜ必要か】
    ユーザーサービスはデスクトップにログインする前に起動することがあるため、
    サーバー起動時点の os.environ には DISPLAY / WAYLAND_DISPLAY が含まれていません。
    GNOME / KDE Plasma はログイン時にこれらを systemd に登録するので、
    DHU を起動する「その瞬間」に最新の値を取り直すことで確実に画面を出せます。
    """
    result = {}
    try:
        out = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            timeout=3,
        ).stdout
    except Exception:
        return result

    for line in out.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in SESSION_ENV_KEYS:
            # systemd は値を $'...' 形式でエスケープする場合があるため簡易的に剥がす
            if value.startswith("$'") and value.endswith("'"):
                value = value[2:-1]
            result[key] = value
    return result


# =============================================================================
# 子プロセス (DHU / adb) 用の環境変数を組み立てる
# =============================================================================
def build_child_env(dhu_path=None):
    """
    DHU や adb を起動する際の環境変数を作成します。
    GUIショートカットや systemd から起動された場合は PATH が最小限しか通っていないため、
    Android SDK の platform-tools (adb) などを PATH に補完します。
    """
    env = os.environ.copy()
    path_list = env.get("PATH", "").split(os.pathsep)

    sdk_candidates = []
    if dhu_path:
        try:
            # .../<SDK>/extras/google/auto/desktop-head-unit → <SDK>
            sdk_candidates.append(Path(dhu_path).resolve().parent.parent.parent.parent)
        except Exception:
            pass
    for env_var in ["ANDROID_HOME", "ANDROID_SDK_ROOT"]:
        if os.environ.get(env_var):
            sdk_candidates.append(Path(os.environ[env_var]))
    sdk_candidates += [
        HOME_DIR / "Android" / "Sdk",
        HOME_DIR / "android-sdk",
        HOME_DIR / "AndroidSdk",
        HOME_DIR / ".android-sdk",
        Path("/usr/lib/android-sdk"),
    ]

    for sdk in sdk_candidates:
        for sub in [("platform-tools",), ("cmdline-tools", "latest", "bin")]:
            p = sdk.joinpath(*sub)
            if p.is_dir() and str(p) not in path_list:
                path_list.insert(0, str(p))

    env["PATH"] = os.pathsep.join(path_list)
    env["HOME"] = str(HOME_DIR)
    return env


# =============================================================================
# ネットワーク検出 (テザリング前提) ヘルパー
# =============================================================================
class NetworkHelper:
    """
    Linux 端末がスマホのテザリング (Wi-Fi アクセスポイント) に接続している前提で、
    スマホの IP アドレスを自動検出するためのヘルパーです。

    【テザリング時の考え方】
    スマホがアクセスポイント (親機) になる場合、Linux 側の「デフォルトゲートウェイ」が
    そのままスマホ自身の IP アドレスになります。
    Android 11 以降はテザリングのサブネットが接続のたびにランダム化されることがあるため
    (例: 192.168.43.1 固定ではない)、毎回ルーティングテーブルから取得し直します。
    外部コマンド (ip / nmcli) に頼らず /proc/net/route を直接読むため、最小構成の OS でも動作します。
    """

    @staticmethod
    def _is_wireless(iface):
        return os.path.isdir(f"/sys/class/net/{iface}/wireless")

    @classmethod
    def get_default_routes(cls):
        """/proc/net/route からデフォルトルート一覧 (iface, gateway, metric, wireless) を返します。"""
        routes = []
        try:
            with open("/proc/net/route", "r") as f:
                lines = f.readlines()[1:]
        except Exception:
            return routes

        for line in lines:
            cols = line.split()
            if len(cols) < 8:
                continue
            iface, dest, gw_hex, flags_hex, metric = cols[0], cols[1], cols[2], cols[3], cols[6]
            try:
                flags = int(flags_hex, 16)
            except ValueError:
                continue
            # 宛先 0.0.0.0 (デフォルトルート) かつ RTF_GATEWAY(0x2) が立っているもの
            if dest != "00000000" or not (flags & 0x2):
                continue
            try:
                gw = socket.inet_ntoa(struct.pack("<L", int(gw_hex, 16)))
            except Exception:
                continue
            routes.append({
                "iface": iface,
                "gateway": gw,
                "metric": int(metric) if metric.isdigit() else 0,
                "wireless": cls._is_wireless(iface),
            })

        # Wi-Fi インターフェースを優先し、その中でメトリックが小さい順
        routes.sort(key=lambda r: (0 if r["wireless"] else 1, r["metric"]))
        return routes

    @staticmethod
    def get_local_ip_for(target):
        """target へ通信する際に使われるこの端末側の IP アドレス (パケットは送信しません)。"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((target, 9))
                return s.getsockname()[0]
        except Exception:
            return ""

    @staticmethod
    def get_ssid(iface):
        """接続中の Wi-Fi の SSID (nmcli / iwgetid があれば)。取得できなければ空文字。"""
        commands = []
        if shutil.which("nmcli"):
            commands.append(["nmcli", "-t", "-f", "GENERAL.CONNECTION", "device", "show", iface])
        if shutil.which("iwgetid"):
            commands.append(["iwgetid", iface, "-r"])
        for cmd in commands:
            try:
                out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     universal_newlines=True, timeout=2).stdout.strip()
            except Exception:
                continue
            if out:
                return out.split(":", 1)[-1].strip() if cmd[0] == "nmcli" else out
        return ""

    @classmethod
    def info(cls):
        """画面表示用のネットワーク情報をまとめて返します。"""
        routes = cls.get_default_routes()
        primary = routes[0] if routes else None
        result = {
            "detected": primary is not None,
            "iface": primary["iface"] if primary else "",
            "wireless": primary["wireless"] if primary else False,
            "gateway": primary["gateway"] if primary else "",
            "local_ip": cls.get_local_ip_for(primary["gateway"]) if primary else "",
            "ssid": cls.get_ssid(primary["iface"]) if primary and primary["wireless"] else "",
            "routes": routes,
        }
        return result

    @classmethod
    def resolve_phone_ip(cls, config):
        """
        接続先スマホの IP を決定します。
        - phone_ip_auto が True (既定) : デフォルトゲートウェイ = テザリング親機のスマホ
        - False : 手動入力された phone_ip
        """
        if not config.get("phone_ip_auto", True):
            return str(config.get("phone_ip", "")).strip()
        routes = cls.get_default_routes()
        return routes[0]["gateway"] if routes else ""

    @staticmethod
    def probe_tcp(host, port, timeout=2.0):
        """host:port に TCP 接続できるか確認します。(成功, メッセージ) を返します。"""
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                return True, f"{host}:{port} に接続できました"
        except socket.timeout:
            return False, f"{host}:{port} への接続がタイムアウトしました"
        except ConnectionRefusedError:
            return False, f"{host}:{port} は接続を拒否しました (サーバー未起動の可能性)"
        except OSError as e:
            return False, f"{host}:{port} に接続できません ({e.strerror or e})"


# =============================================================================
# ADB 操作ヘルパー (方法2: Wi-Fi ADB + ポートフォワーディング)
# =============================================================================
class ADBHelper:
    """adb コマンドのラッパーです。PATH は build_child_env() で補完したものを使います。"""

    def __init__(self, env):
        self.env = env
        self.path = shutil.which("adb", path=env.get("PATH", ""))

    def run(self, args, timeout=15):
        if not self.path:
            return 127, "adb が見つかりません (Android SDK の platform-tools をインストールしてください)"
        try:
            p = subprocess.run([self.path] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, universal_newlines=True,
                               timeout=timeout, env=self.env)
            return p.returncode, p.stdout.strip()
        except subprocess.TimeoutExpired:
            return 124, f"adb {' '.join(args)} がタイムアウトしました"
        except Exception as e:
            return 1, str(e)

    def devices(self):
        """adb devices -l の結果を [{serial, state, model, transport}] で返します。"""
        rc, out = self.run(["devices", "-l"], timeout=10)
        result = []
        if rc != 0:
            return result
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices") or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            model = ""
            for p in parts[2:]:
                if p.startswith("model:"):
                    model = p.split(":", 1)[1]
            wireless = (":" in serial) or ("_adb-tls-connect" in serial)
            result.append({
                "serial": serial,
                "state": state,
                "model": model,
                "transport": "wifi" if wireless else "usb",
            })
        return result

    def connect(self, host, port):
        rc, out = self.run(["connect", f"{host}:{port}"], timeout=15)
        ok = ("connected to" in out) and ("cannot" not in out) and ("failed" not in out.lower())
        return ok, out

    def pair(self, host, port, code):
        rc, out = self.run(["pair", f"{host}:{port}", str(code)], timeout=30)
        ok = rc == 0 and "Successfully paired" in out
        return ok, out

    def tcpip(self, port):
        """USB 接続中の端末を TCP/IP (adb tcpip <port>) モードに切り替えます。"""
        usb_devices = [d for d in self.devices() if d["transport"] == "usb" and d["state"] == "device"]
        if not usb_devices:
            return False, "USB デバッグで接続された端末が見つかりません。USB ケーブルで接続し、スマホで「USB デバッグを許可」してください。"
        serial = usb_devices[0]["serial"]
        rc, out = self.run(["-s", serial, "tcpip", str(port)], timeout=15)
        return rc == 0, out or f"{serial} を TCP/IP モード (ポート {port}) に切り替えました"

    def forward(self, serial, local_port, remote_port):
        rc, out = self.run(["-s", serial, "forward", f"tcp:{local_port}", f"tcp:{remote_port}"], timeout=10)
        return rc == 0, out

    def remove_forward(self, local_port):
        if self.path:
            self.run(["forward", "--remove", f"tcp:{local_port}"], timeout=5)


# =============================================================================
# 内蔵 TCP リレー (方法1 の予備経路 / socat 相当)
# =============================================================================
class TCPRelay:
    """
    127.0.0.1:<listen_port> で待ち受け、届いた接続をスマホの <remote_host>:<remote_port> へ中継します。
    `socat TCP-LISTEN:5277,fork TCP:<スマホIP>:5277` と同じ働きを Python 標準ライブラリだけで実現し、
    socat のインストールを不要にしています。
    """

    def __init__(self, listen_port, remote_host, remote_port, logger):
        self.listen_port = int(listen_port)
        self.remote_host = remote_host
        self.remote_port = int(remote_port)
        self.log = logger
        self._server = None
        self._conns = []
        self._lock = threading.Lock()
        self._running = False

    def start(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", self.listen_port))
        srv.listen(4)
        self._server = srv
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        self.log(f"[リレー] 127.0.0.1:{self.listen_port} → {self.remote_host}:{self.remote_port} の中継を開始しました")

    def _accept_loop(self):
        while self._running:
            try:
                client, _ = self._server.accept()
            except OSError:
                break
            if not self._running:
                client.close()
                break
            try:
                remote = socket.create_connection((self.remote_host, self.remote_port), timeout=5)
                remote.settimeout(None)
            except OSError as e:
                self.log(f"[リレー] スマホ {self.remote_host}:{self.remote_port} へ接続できません: {e}")
                client.close()
                continue
            for s in (client, remote):
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with self._lock:
                self._conns += [client, remote]
            threading.Thread(target=self._pump, args=(client, remote), daemon=True).start()
            threading.Thread(target=self._pump, args=(remote, client), daemon=True).start()

    @staticmethod
    def _pump(src, dst):
        try:
            while True:
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)
        except OSError:
            pass
        finally:
            for s in (src, dst):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def stop(self):
        self._running = False
        if self._server:
            # ※ Linux では別スレッドが accept() で待機中のソケットを close() しただけでは
            #    待ち受けが解除されないため、先に shutdown() で accept() を起こしてから閉じる
            try:
                self._server.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._server.close()
            except OSError:
                pass
        with self._lock:
            for s in self._conns:
                try:
                    s.close()
                except OSError:
                    pass
            self._conns = []
        self.log("[リレー] 中継を停止しました")


# =============================================================================
# DHU ウィンドウ操作ヘルパー (Wi-Fi 接続時のタッチ不具合の自動回避)
# =============================================================================
class X11WindowHelper:
    """
    X11 (XWayland 含む) 上の DHU ウィンドウを、EWMH (_NET_WM_STATE) で最大化/解除します。
    wmctrl / xdotool 等の外部ツールに頼らず、Python 標準の ctypes から libX11 を直接呼び出します。

    【なぜ必要か】
    Wi-Fi 接続では DHU のウィンドウが「Waiting for phone...」の段階で開き、ウィンドウマネージャー
    (KDE 等) によって接続確立前に最大化されます。DHU はこの「接続確立前のサイズ変更」を
    タッチ座標の計算に反映しないため、最大化されたままだとクリック (タッチ) が反応しません。
    接続確立後に一度でもサイズが変わると正しく再計算されるため、手動で行っていた
    「最大化解除 → 再最大化」を接続確立の直後に自動で実行します。
    """

    CLIENT_MESSAGE = 33
    SUBSTRUCTURE_NOTIFY_MASK = 1 << 19
    SUBSTRUCTURE_REDIRECT_MASK = 1 << 20
    NET_WM_STATE_REMOVE = 0
    NET_WM_STATE_ADD = 1

    _error_handler_ref = None  # GC されないよう保持

    class _XClientMessageEvent(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_int),
            ("serial", ctypes.c_ulong),
            ("send_event", ctypes.c_int),
            ("display", ctypes.c_void_p),
            ("window", ctypes.c_ulong),
            ("message_type", ctypes.c_ulong),
            ("format", ctypes.c_int),
            ("data", ctypes.c_long * 5),
        ]

    class _XEvent(ctypes.Union):
        pass

    _XEvent._fields_ = [("xclient", _XClientMessageEvent), ("pad", ctypes.c_long * 24)]

    def __init__(self, display_name, xauthority=None):
        libname = ctypes.util.find_library("X11") or "libX11.so.6"
        x = ctypes.CDLL(libname)
        c_ulong_p = ctypes.POINTER(ctypes.c_ulong)

        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XDefaultRootWindow.restype = ctypes.c_ulong
        x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x.XInternAtom.restype = ctypes.c_ulong
        x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x.XGetWindowProperty.restype = ctypes.c_int
        x.XGetWindowProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long, ctypes.c_long,
            ctypes.c_int, ctypes.c_ulong, c_ulong_p, ctypes.POINTER(ctypes.c_int),
            c_ulong_p, c_ulong_p, ctypes.POINTER(ctypes.c_void_p),
        ]
        x.XFree.argtypes = [ctypes.c_void_p]
        x.XSendEvent.restype = ctypes.c_int
        x.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.c_void_p]
        x.XFlush.argtypes = [ctypes.c_void_p]
        x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XCloseDisplay.argtypes = [ctypes.c_void_p]

        # 既定の Xlib エラーハンドラーはエラー時にプロセスごと終了してしまうため、
        # 「操作中に DHU のウィンドウが閉じられた」等のエラーを無視するハンドラーに差し替える
        if X11WindowHelper._error_handler_ref is None:
            handler_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
            X11WindowHelper._error_handler_ref = handler_type(lambda dpy, err: 0)
            x.XSetErrorHandler.argtypes = [handler_type]
            x.XSetErrorHandler(X11WindowHelper._error_handler_ref)

        # サービス起動時はサーバー自身の環境変数に XAUTHORITY が無いため、セッションの値を使う
        if xauthority:
            os.environ["XAUTHORITY"] = xauthority

        dpy = x.XOpenDisplay(display_name.encode() if display_name else None)
        if not dpy:
            raise OSError(f"X ディスプレイ {display_name or '(未設定)'} に接続できません")
        self.x = x
        self.dpy = dpy
        self.root = x.XDefaultRootWindow(dpy)
        self._atoms = {}

    def close(self):
        if self.dpy:
            self.x.XCloseDisplay(self.dpy)
            self.dpy = None

    def atom(self, name):
        if name not in self._atoms:
            self._atoms[name] = self.x.XInternAtom(self.dpy, name.encode(), 0)
        return self._atoms[name]

    def _get_property(self, window, name):
        """プロパティを取得します。format=32 なら整数のリスト、8 ならバイト列を返します。"""
        actual_type = ctypes.c_ulong()
        actual_format = ctypes.c_int()
        nitems = ctypes.c_ulong()
        bytes_after = ctypes.c_ulong()
        prop = ctypes.c_void_p()
        status = self.x.XGetWindowProperty(
            self.dpy, window, self.atom(name), 0, 4096, 0, 0,  # 0 = AnyPropertyType
            ctypes.byref(actual_type), ctypes.byref(actual_format),
            ctypes.byref(nitems), ctypes.byref(bytes_after), ctypes.byref(prop),
        )
        if status != 0 or not prop.value:
            return None
        try:
            if actual_format.value == 32:
                arr = ctypes.cast(prop, ctypes.POINTER(ctypes.c_ulong))
                return [arr[i] for i in range(nitems.value)]
            if actual_format.value == 8:
                return ctypes.string_at(prop, nitems.value)
            return None
        finally:
            self.x.XFree(prop)

    def find_windows_by_pid(self, pid):
        """_NET_WM_PID が pid と一致するトップレベルウィンドウの一覧。"""
        clients = self._get_property(self.root, "_NET_CLIENT_LIST") or []
        result = []
        for w in clients:
            pids = self._get_property(w, "_NET_WM_PID")
            if pids and pids[0] == pid:
                result.append(w)
        return result

    def window_title(self, window):
        raw = self._get_property(window, "_NET_WM_NAME") or self._get_property(window, "WM_NAME") or b""
        return raw.decode("utf-8", "replace") if isinstance(raw, bytes) else ""

    def is_maximized(self, window):
        states = self._get_property(window, "_NET_WM_STATE") or []
        return (self.atom("_NET_WM_STATE_MAXIMIZED_VERT") in states
                and self.atom("_NET_WM_STATE_MAXIMIZED_HORZ") in states)

    def set_maximized(self, window, maximize):
        ev = X11WindowHelper._XEvent()
        ev.xclient.type = self.CLIENT_MESSAGE
        ev.xclient.send_event = 1
        ev.xclient.display = self.dpy
        ev.xclient.window = window
        ev.xclient.message_type = self.atom("_NET_WM_STATE")
        ev.xclient.format = 32
        ev.xclient.data[0] = self.NET_WM_STATE_ADD if maximize else self.NET_WM_STATE_REMOVE
        ev.xclient.data[1] = self.atom("_NET_WM_STATE_MAXIMIZED_VERT")
        ev.xclient.data[2] = self.atom("_NET_WM_STATE_MAXIMIZED_HORZ")
        ev.xclient.data[3] = 1  # 送信元: 通常のアプリケーション
        ev.xclient.data[4] = 0
        self.x.XSendEvent(self.dpy, self.root, 0,
                          self.SUBSTRUCTURE_REDIRECT_MASK | self.SUBSTRUCTURE_NOTIFY_MASK,
                          ctypes.byref(ev))
        self.x.XSync(self.dpy, 0)


# =============================================================================
# DHUプロセス＆再接続監視コントローラー (Process Manager)
# =============================================================================
class DHUManager:
    """
    desktop-head-unit のプロセス起動、停止、死活監視、
    およびUSB/Wi-Fi切断時の『10秒間自動復帰ループ』を管理するシングルトン風クラス。

    【接続方式】
    - USB             : desktop-head-unit --usb (AOA アクセサリモード)
    - Wi-Fi / 方法1   : desktop-head-unit --adb=<スマホIP>:5277 (ヘッドユニットサーバーへ直接 TCP 接続・既定)
    - Wi-Fi / 方法2   : adb connect <スマホIP>:<ADBポート> → adb forward tcp:5277 tcp:5277 → desktop-head-unit
                        ※ 予備として内蔵リレー (socat 相当) 経由も選択可能

    【Node.jsとの比較】
    Node.jsの child_process.spawn() + setInterval によるプロセス監視に相当しますが、
    Pythonでは threading.Thread による独立したワーカースレッドで安全に監視ループを回します。
    """

    def __init__(self):
        self._lock = threading.Lock() # スレッドセーフのためのミューテックス（Javaの synchronized に相当）
        self.process = None           # 起動中の subprocess.Popen オブジェクト
        self.status = "IDLE"          # "IDLE" | "STARTING" | "RUNNING" | "RECONNECTING" | "ERROR"
        self.user_stopped = False     # ユーザーの明示的な停止操作かどうかを識別するフラグ
        self.last_error = ""
        self.logs = []                # 最新のログ行を保持（リングバッファ）
        self.max_logs = 200
        self.retry_countdown = 0      # 再接続カウントダウン（残り秒数）
        self.monitor_thread = None
        self.relay = None             # 方法1 (リレー経由) 用の TCPRelay
        self.connection = {}          # 現在の接続方式 (画面表示用)

    def add_log(self, message):
        """タイムスタンプ付きでメモリ上のログ配列に追加します。"""
        timestamp = time.strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        print(log_line, flush=True)
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
                "run_mode": "service" if is_running_as_service() else "manual",
                "connection": dict(self.connection),
            }

    def is_busy(self):
        with self._lock:
            return self.status in ("STARTING", "RUNNING", "RECONNECTING")

    def start(self, options=None):
        """
        Android Auto (DHU) を起動します。options に接続方式が渡された場合は設定に保存してから使います。
        すでに起動している場合は無視します。
        """
        with self._lock:
            if self.status in ("STARTING", "RUNNING", "RECONNECTING"):
                return True, "すでに実行中です。"
            self.user_stopped = False
            self.status = "STARTING"
            self.retry_countdown = 0
            self.last_error = ""

        if options:
            config = ConfigManager.save_app_config(options)
        else:
            config = ConfigManager.load_app_config()
        dhu_path = config.get("dhu_path", "").strip()

        if not dhu_path or not os.path.isfile(dhu_path):
            return self._fail_start(f"desktop-head-unitが見つかりません: {dhu_path}")
        if not os.access(dhu_path, os.X_OK):
            return self._fail_start(f"desktop-head-unitに実行権限がありません: {dhu_path}")

        # バックグラウンドの監視スレッドを起動
        self.monitor_thread = threading.Thread(
            target=self._run_and_monitor_loop,
            args=(dhu_path, config),
            daemon=True
        )
        self.monitor_thread.start()
        return True, "起動を開始しました。"

    def _fail_start(self, message):
        with self._lock:
            self.status = "ERROR"
            self.last_error = message
        self.add_log(f"[エラー] {message}")
        return False, message

    def stop(self):
        """
        ユーザーによる明示的な切断・終了処理。
        この場合、切断時の10秒自動復帰ループは発動させません。
        """
        self.add_log("[操作] 停止ボタンが押されました。")
        with self._lock:
            self.user_stopped = True
            self.retry_countdown = 0
            proc = self.process

        if proc is not None and proc.poll() is None:
            try:
                # まず DHU の対話コンソールに 'quit' を送って正常終了を促す
                if proc.stdin is not None:
                    try:
                        proc.stdin.write("quit\n")
                        proc.stdin.flush()
                    except Exception:
                        pass
                    for _ in range(10):
                        if proc.poll() is not None:
                            break
                        time.sleep(0.2)

                # 終了しなければ SIGINT(Ctrl+C相当)、それでもだめなら SIGTERM
                if proc.poll() is None:
                    proc.send_signal(signal.SIGINT)
                for _ in range(10):
                    if proc.poll() is not None:
                        break
                    time.sleep(0.2)
                if proc.poll() is None:
                    proc.terminate()
            except Exception as e:
                self.add_log(f"[警告] プロセス終了処理中の例外: {e}")

        self._stop_relay()
        with self._lock:
            self.process = None
            self.status = "IDLE"
            self.connection = {}
        self.add_log("[状態] 停止しました。")
        return True, "停止しました。"

    def _stop_relay(self):
        if self.relay is not None:
            self.relay.stop()
            self.relay = None

    def _apply_session_env(self, env):
        """
        DHU に渡す環境変数へ、デスクトップセッションの DISPLAY 等を反映します。
        - サービス起動時: systemd に登録された最新のセッション値で上書き
          (ログアウト→再ログインで DISPLAY が変わっても追従するため)
        - 手動起動時   : 足りない値だけを補完 (ターミナルの値を優先)
        """
        session_env = get_systemd_user_session_env()
        as_service = is_running_as_service()
        for key, value in session_env.items():
            if as_service or not env.get(key):
                env[key] = value

        if not env.get("XDG_RUNTIME_DIR"):
            runtime_dir = f"/run/user/{os.getuid()}"
            if os.path.isdir(runtime_dir):
                env["XDG_RUNTIME_DIR"] = runtime_dir

        if not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
            self.add_log(
                "[警告] デスクトップセッション (DISPLAY / WAYLAND_DISPLAY) が見つかりません。"
                "デスクトップにログインしてから接続してください。"
            )

    def _fix_touch_by_remaximize(self, proc, env):
        """
        【Wi-Fi 接続時のタッチ不具合の自動回避】
        接続確立後、DHU のウィンドウが最大化されていれば「最大化解除 → 再最大化」を行い、
        DHU にウィンドウサイズを再計算させてタッチ (クリック) を有効にします。
        詳細は X11WindowHelper の説明を参照してください。
        """
        time.sleep(TOUCH_FIX_DELAY_SEC)
        display = env.get("DISPLAY")
        if not display:
            self.add_log("[タッチ補正] DISPLAY が無いため実行できません (X11 / XWayland 以外の環境)")
            return

        try:
            x11 = X11WindowHelper(display, env.get("XAUTHORITY"))
        except Exception as e:
            self.add_log(f"[タッチ補正] X11 に接続できないためスキップします: {e}")
            return

        try:
            windows = []
            for _ in range(20):  # ウィンドウが現れるまで最大 10 秒待つ
                if proc.poll() is not None or self.user_stopped:
                    return
                windows = x11.find_windows_by_pid(proc.pid)
                if windows:
                    break
                time.sleep(0.5)
            if not windows:
                self.add_log("[タッチ補正] DHU のウィンドウが見つからないためスキップします")
                return

            for w in windows:
                title = x11.window_title(w) or hex(w)
                if not x11.is_maximized(w):
                    self.add_log(f"[タッチ補正] 「{title}」は最大化されていないため補正不要です")
                    continue
                x11.set_maximized(w, False)
                time.sleep(0.4)
                x11.set_maximized(w, True)
                time.sleep(0.3)
                state = "最大化に復帰" if x11.is_maximized(w) else "最大化に戻せませんでした"
                self.add_log(f"[タッチ補正] 「{title}」の最大化を解除→再最大化しました ({state})")
        except Exception as e:
            self.add_log(f"[タッチ補正] 失敗しました: {e}")
        finally:
            x11.close()

    def _warn_no_handshake(self, proc, handshake, config):
        """DHU 起動後、スマホからの応答がないまま一定時間経過した場合の案内。"""
        if handshake["ok"] or proc.poll() is not None or self.user_stopped:
            return
        if config.get("wifi_mode") == "adb":
            msg = ("スマホから応答がありません (Waiting for phone...)。スマホのロックを解除し、Android Auto の確認画面が"
                   "出ていれば許可してください。改善しない場合は、スマホでヘッドユニットサーバーを一度停止→起動し直してください。")
        else:
            msg = ("スマホから応答がありません (Waiting for phone...)。TCP 接続はできていますが、ヘッドユニットサーバーが"
                   "応答していません。スマホのロック解除・確認画面の許可を行い、ヘッドユニットサーバーを停止→起動し直してください。"
                   "それでも進まない場合、この端末では Wi-Fi 直結が使えない可能性があるため、方法2 (ADB) をお試しください。")
        self.add_log(f"[警告] {msg}")
        with self._lock:
            self.connection["warning"] = msg

    # -------------------------------------------------------------------------
    # 接続方式ごとの準備 (毎回の接続試行の直前に実行)
    # -------------------------------------------------------------------------
    def _prepare_connection(self, dhu_path, config, env):
        """
        接続方式に応じた前準備を行い、実行する DHU コマンドを返します。
        戻り値: (cmd: list | None, error: str | None)
        """
        ctype = config.get("connection_type", "usb")

        if ctype != "wifi":
            with self._lock:
                self.connection = {"type": "usb", "label": "USB (AOA アクセサリモード)", "target": ""}
            return [dhu_path, "--usb"], None

        # ---- 以下 Wi-Fi 接続 ----
        wifi_mode = config.get("wifi_mode", "direct")
        hu_port = int(config.get("hu_port") or HU_SERVER_PORT)
        host = NetworkHelper.resolve_phone_ip(config)
        if not host:
            if config.get("phone_ip_auto", True):
                return None, ("スマホの IP アドレスを自動検出できません。Linux 端末がスマホのテザリング (Wi-Fi) に"
                              "接続されているか確認するか、IP アドレスを手動で入力してください。")
            return None, "スマホの IP アドレスが入力されていません。"

        how = "自動検出: テザリング親機" if config.get("phone_ip_auto", True) else "手動入力"
        self.add_log(f"[Wi-Fi] 接続先スマホ: {host} ({how})")

        if wifi_mode == "adb":
            return self._prepare_wifi_adb(dhu_path, config, env, host, hu_port)
        return self._prepare_wifi_direct(dhu_path, config, env, host, hu_port)

    def _prepare_wifi_adb(self, dhu_path, config, env, host, hu_port):
        """方法2: Wi-Fi ADB 接続 + adb forward tcp:5277 tcp:5277"""
        adb = ADBHelper(env)
        if not adb.path:
            return None, "adb が見つかりません。Android SDK の platform-tools をインストールしてください。"

        adb_port = int(config.get("adb_port") or 5555)
        target = f"{host}:{adb_port}"

        devices = adb.devices()
        online = [d for d in devices if d["state"] == "device"]
        serial = target if any(d["serial"] == target for d in online) else None

        if serial is None:
            self.add_log(f"[ADB] adb connect {target} を実行します...")
            ok, out = adb.connect(host, adb_port)
            self.add_log(f"[ADB] {out}")
            if ok:
                serial = target
            else:
                # ワイヤレスデバッグ (mDNS 自動接続) 等で別名のシリアルが既にある場合はそれを使う
                wireless = [d for d in online if d["transport"] == "wifi"]
                if wireless:
                    serial = wireless[0]["serial"]
                    self.add_log(f"[ADB] 接続済みの無線デバイス {serial} を使用します")
                else:
                    return None, (f"adb connect {target} に失敗しました。スマホで「USB デバッグ」が有効か、"
                                  f"一度 USB 接続して「TCP/IP モード有効化 (adb tcpip {adb_port})」を実行したか確認してください。")

        if any(d["serial"] == serial and d["state"] == "unauthorized" for d in adb.devices()):
            return None, "スマホ側で USB デバッグ (この PC) が許可されていません。スマホの画面で「許可」をタップしてください。"

        ok, out = adb.forward(serial, ADB_FORWARD_LOCAL_PORT, hu_port)
        if not ok:
            return None, f"adb forward に失敗しました: {out}"
        self.add_log(f"[ADB] adb -s {serial} forward tcp:{ADB_FORWARD_LOCAL_PORT} tcp:{hu_port} を設定しました")

        with self._lock:
            self.connection = {
                "type": "wifi", "wifi_mode": "adb",
                "label": "Wi-Fi 方法2 (ADB + ポートフォワード)",
                "target": f"{serial} → localhost:{ADB_FORWARD_LOCAL_PORT}",
            }
        # DHU の既定動作 (引数なし) は localhost:5277 への接続
        return [dhu_path], None

    def _prepare_wifi_direct(self, dhu_path, config, env, host, hu_port):
        """
        方法1: ヘッドユニットサーバー (スマホ:5277) へ直接接続

        ※ 接続直前の自動疎通確認 (TCP 接続して即切断) は行いません。
           ヘッドユニットサーバーは 1 本の接続を 1 セッションとして扱うため、確認用の接続が
           セッションを消費し、直後の DHU の接続に応答しなくなる (Waiting for phone... で停止する)
           可能性があるためです。接続できない場合は DHU 自体が終了し、10 秒後に自動で再試行します。
        """
        self.add_log(f"[Wi-Fi] ヘッドユニットサーバー {host}:{hu_port} へ直接接続します")

        transport = config.get("direct_transport", "adb_flag")
        if transport == "relay":
            # 以前の adb forward が同じポートを掴んでいると衝突するため解除しておく
            ADBHelper(env).remove_forward(RELAY_LOCAL_PORT)
            if self.relay is None or self.relay.remote_host != host or self.relay.remote_port != hu_port:
                self._stop_relay()
                relay = TCPRelay(RELAY_LOCAL_PORT, host, hu_port, self.add_log)
                try:
                    relay.start()
                except OSError as e:
                    return None, f"リレー用ポート 127.0.0.1:{RELAY_LOCAL_PORT} を開けません ({e.strerror or e})。adb forward 等が使用中でないか確認してください。"
                self.relay = relay
            with self._lock:
                self.connection = {
                    "type": "wifi", "wifi_mode": "direct",
                    "label": "Wi-Fi 方法1 (内蔵リレー経由)",
                    "target": f"localhost:{RELAY_LOCAL_PORT} → {host}:{hu_port}",
                }
            return [dhu_path], None

        with self._lock:
            self.connection = {
                "type": "wifi", "wifi_mode": "direct",
                "label": "Wi-Fi 方法1 (ヘッドユニットサーバーへ直接)",
                "target": f"{host}:{hu_port}",
            }
        return [dhu_path, f"--adb={host}:{hu_port}"], None

    # -------------------------------------------------------------------------
    # 監視ループ本体
    # -------------------------------------------------------------------------
    def _run_and_monitor_loop(self, dhu_path, config):
        """
        【重要ロジック】
        DHUプロセスの実行、起動直後のUSBモード切り替え瞬断の即時リカバリ、
        および切断時の『10秒自動復帰』を制御する監視ループ。
        """
        instant_retry_count = 0  # 起動直後の瞬断連続カウント (USB のみ)
        is_usb = config.get("connection_type", "usb") != "wifi"

        env = build_child_env(dhu_path)
        self._apply_session_env(env)
        dhu_work_dir = str(Path(dhu_path).resolve().parent)

        while not self.user_stopped:
            elapsed = 0.0
            cmd, prep_error = self._prepare_connection(dhu_path, config, env)

            if prep_error:
                # 準備段階の失敗 (スマホが見つからない等) は 10 秒後に再試行
                self.add_log(f"[エラー] {prep_error}")
                with self._lock:
                    self.last_error = prep_error
            else:
                self.add_log(f"[実行] コマンド呼び出し: {' '.join(cmd)}")
                start_time = time.time()
                last_dhu_output = ""

                try:
                    # =========================================================
                    # 【デスクトップ起動時の即時終了対策】
                    # DHU は標準入力を対話コンソール (day / night / quit 等) として読み続けます。
                    # .desktop (Terminal=false) や systemd から起動すると stdin が /dev/null になり、
                    # DHU は即座に EOF を受け取って「quit」と同様に exit 0 で終了してしまいます。
                    # そこで、何も書き込まずに開いたままのパイプを stdin として渡し、
                    # ターミナル起動時と同じ「入力待ち」状態を再現します。
                    # (このパイプは停止時に 'quit' コマンドを送る用途にも使います)
                    # =========================================================
                    proc = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        universal_newlines=True,
                        bufsize=1,
                        env=env,
                        cwd=dhu_work_dir
                    )
                    with self._lock:
                        self.process = proc
                        self.status = "RUNNING"
                        self.last_error = ""

                    self.add_log(f"[接続] desktop-head-unit を起動しました (PID: {proc.pid})")

                    # ---------------------------------------------------------
                    # 【ハンドシェイク監視】(Wi-Fi のみ)
                    # TCP 接続できてもスマホが応答しないと、DHU は「Waiting for phone...」のまま
                    # 終了もせず止まってしまいます。一定時間内に "Phone reported protocol version"
                    # (スマホからの応答) が出なければ、原因と対処をログと画面に表示します。
                    # ---------------------------------------------------------
                    handshake = {"ok": False}
                    watchdog = None
                    if not is_usb:
                        watchdog = threading.Timer(
                            HANDSHAKE_TIMEOUT_SEC, self._warn_no_handshake, args=(proc, handshake, config)
                        )
                        watchdog.daemon = True
                        watchdog.start()

                    # 出力ログのリアルタイム読み取り
                    if proc.stdout:
                        for line in proc.stdout:
                            clean_line = ANSI_ESCAPE_RE.sub("", line).strip()
                            if clean_line:
                                last_dhu_output = clean_line
                                self.add_log(f"[DHU] {clean_line}")
                                if "Phone reported protocol version" in clean_line and not handshake["ok"]:
                                    handshake["ok"] = True
                                    with self._lock:
                                        self.connection.pop("warning", None)
                                    if not is_usb:
                                        self.add_log("[接続] スマホとのハンドシェイクに成功しました")
                                        if config.get("wifi_touch_fix", True):
                                            threading.Thread(
                                                target=self._fix_touch_by_remaximize,
                                                args=(proc, env),
                                                daemon=True,
                                            ).start()

                    if watchdog is not None:
                        watchdog.cancel()

                    proc.wait()
                    if proc.stdin is not None:
                        try:
                            proc.stdin.close()
                        except Exception:
                            pass
                    exit_code = proc.returncode
                    elapsed = time.time() - start_time
                    self.add_log(f"[終了] プロセスが終了しました (終了コード: {exit_code}, 稼働時間: {elapsed:.1f}秒)")

                    if exit_code != 0:
                        if last_dhu_output:
                            self.add_log(f"[エラー詳細] DHU最終出力: {last_dhu_output}")
                        with self._lock:
                            self.last_error = f"DHU終了コード {exit_code}: {last_dhu_output or '異常終了'}"

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
            # 【スマート復帰判定】(USB のみ)
            # 起動直後 (約3.5秒以内) にプロセスが落ちる現象は、スマホが「通常USBモード(MTP等)」から
            # 「Android Open Accessory(AOA)モード」へ切り替わる際の一瞬のUSB再初期化によるものです。
            # この時は10秒待たずに約1.5秒後に即座に再起動することでシームレスに接続できます。
            # =================================================================
            if is_usb and not prep_error and elapsed < 3.5 and instant_retry_count < 3:
                instant_retry_count += 1
                self.add_log(f"[モード切替検知] AOAアクセサリ切り替えによる瞬断を検知 ({instant_retry_count}/3回目)。1.5秒後に即時再試行します...")
                with self._lock:
                    self.status = "RECONNECTING"
                    self.retry_countdown = 1

                for _ in range(15):
                    if self.user_stopped:
                        break
                    time.sleep(0.1)

                with self._lock:
                    self.retry_countdown = 0

                if self.user_stopped:
                    break
                continue

            # =================================================================
            # 【要件】通常稼働後の切断は、10秒カウントダウンしながら再接続待機
            # =================================================================
            instant_retry_count = 0
            if is_usb:
                self.add_log("[検知] 接続切断（USB抜け等の可能性）。10秒後に自動再接続を試みます...")
            else:
                self.add_log("[検知] Wi-Fi 接続が切断されたか、接続できませんでした。10秒後に自動再接続を試みます...")
            with self._lock:
                self.status = "RECONNECTING"

            for sec in range(10, 0, -1):
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

            # 再接続のたびに最新の接続方式設定を読み直す (自動検出 IP の変化にも追従)
            config = ConfigManager.load_app_config()
            self.add_log("[再接続] 自動復帰を試行します...")

        self._stop_relay()
        if not is_usb and config.get("wifi_mode") == "adb":
            # 方法2 で設定した adb forward を後片付け (他の方式でポートが衝突しないように)
            ADBHelper(env).remove_forward(ADB_FORWARD_LOCAL_PORT)
        with self._lock:
            if self.status != "ERROR":
                self.status = "IDLE"
            self.process = None
            self.retry_countdown = 0
            self.connection = {}


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

        # API: ネットワーク情報 (テザリング親機 = スマホ IP の自動検出結果)
        if path == "/api/network":
            info = NetworkHelper.info()
            app_config = ConfigManager.load_app_config()
            info["resolved_phone_ip"] = NetworkHelper.resolve_phone_ip(app_config)
            self._send_json(200, info)
            return

        # API: adb で認識されている端末一覧
        if path == "/api/adb/devices":
            adb = ADBHelper(build_child_env(ConfigManager.load_app_config().get("dhu_path")))
            self._send_json(200, {
                "adb_found": bool(adb.path),
                "adb_path": adb.path or "",
                "devices": adb.devices() if adb.path else [],
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
            # 画面で選択中の接続方式 (USB / Wi-Fi 方法1 / 方法2) を受け取り、保存してから起動
            payload = self._read_json_body()
            success, msg = dhu_manager.start(payload.get("connection") if payload else None)
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

        # API: スマホ (ヘッドユニットサーバー / ADB) への TCP 疎通確認
        if path == "/api/probe":
            payload = self._read_json_body()
            app_config = ConfigManager.load_app_config()
            host = str(payload.get("host") or NetworkHelper.resolve_phone_ip(app_config)).strip()
            port = payload.get("port") or app_config.get("hu_port") or HU_SERVER_PORT
            if not host:
                self._send_json(200, {"ok": False, "host": "", "port": port,
                                      "message": "スマホの IP アドレスが分かりません (テザリング未接続?)"})
                return
            ok, msg = NetworkHelper.probe_tcp(host, port)
            self._send_json(200, {"ok": ok, "host": host, "port": port, "message": msg})
            return

        # API: adb 操作 (方法2 の事前準備)
        if path in ("/api/adb/connect", "/api/adb/pair", "/api/adb/tcpip"):
            payload = self._read_json_body()
            app_config = ConfigManager.load_app_config()
            adb = ADBHelper(build_child_env(app_config.get("dhu_path")))
            if not adb.path:
                self._send_json(200, {"success": False, "message": "adb が見つかりません (platform-tools をインストールしてください)"})
                return

            host = str(payload.get("host") or NetworkHelper.resolve_phone_ip(app_config)).strip()
            try:
                port = int(payload.get("port") or app_config.get("adb_port") or 5555)
            except (TypeError, ValueError):
                port = 5555

            if path == "/api/adb/tcpip":
                ok, out = adb.tcpip(port)
            elif not host:
                ok, out = False, "スマホの IP アドレスが分かりません (テザリング未接続?)"
            elif path == "/api/adb/connect":
                ok, out = adb.connect(host, port)
            else:
                code = "".join(c for c in str(payload.get("code", "")) if c.isdigit())
                if not code:
                    ok, out = False, "ペアリングコード (6桁) を入力してください"
                else:
                    ok, out = adb.pair(host, port, code)

            dhu_manager.add_log(f"[ADB] {path.rsplit('/', 1)[-1]}: {out}")
            self._send_json(200, {"success": ok, "message": out, "devices": adb.devices()})
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
    url = f"http://{args.host}:{args.port}"

    try:
        httpd = ThreadingHTTPServer(server_address, LinuxAutoHTTPHandler)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            # すでにサービス等でサーバーが動いている場合は二重起動せず、画面だけ開いて終了する
            print(f"[情報] ポート {args.port} は既に使用中です。Linux Auto サーバーは起動済みと判断します。")
            if not args.no_browser:
                print(f"[情報] 画面を開きます: {url}")
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
            sys.exit(0)
        raise

    print("=" * 60)
    print("   Linux Auto - Android Auto Headunit Support")
    print("   エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)")
    print("=" * 60)
    print(f" WebUIサーバー起動完了: {url}")
    print(f" 起動モード: {'サービス (systemd)' if is_running_as_service() else '手動起動'}")
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
    # ※ httpd.shutdown() を serve_forever() と同じスレッド(シグナルハンドラ)から呼ぶと
    #    デッドロックして終了できないため、KeyboardInterrupt に変換して finally 節で後始末します。
    #    (systemctl --user stop は SIGTERM を送るので、この処理で DHU も正しく停止します)
    def shutdown_signal(signum, frame):
        print("\n[終了] シャットダウンシグナルを受信しました。終了します...")
        raise KeyboardInterrupt

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
