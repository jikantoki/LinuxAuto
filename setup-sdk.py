#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================================================
Linux Auto - Android SDK / DHU 自動セットアップスクリプト
開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)

【やること】
  1. Java (sdkmanager の実行に必要・17 以降) の確認 (無ければ apt で自動インストール)
  2. 最新版 Android SDK Command-line Tools のファイル名を
     https://dl.google.com/android/repository/repository2-1.xml から取得
  3. https://dl.google.com/android/repository/<ファイル名> をダウンロードし、
     <SDK>/cmdline-tools/latest/ に配置 (SHA-1 チェックサムも検証)
  4. sdkmanager で "extras;google;auto" (DHU) と "platform-tools" (adb) をインストール
  5. desktop-head-unit に実行権限を付与し、必要なライブラリ (libc++ 等) が無ければ apt で自動インストール
  6. Linux Auto の設定 (~/.config/linux-auto/config.json) に DHU のパスを保存し、
     ~/.android/headunit.ini を書き込む

【使い方】
  python3 setup-sdk.py            # ライセンスは sdkmanager の画面で確認して y を入力
  python3 setup-sdk.py --yes      # ライセンスに自動で同意して、すべて自動で実行
  python3 setup-sdk.py --yes --no-install-deps
                                  # 足りないパッケージを自動でインストールしない
  python3 setup-sdk.py --help     # オプション一覧

Linux Auto の画面 (導入ガイド →「自動セットアップ」) からも同じスクリプトが実行されます。
足りないパッケージのインストールには root 権限が必要なため、ターミナルからは sudo、
画面からは pkexec (デスクトップにパスワード入力のダイアログが出る) を使います。
app.py と同じく、Python 3 の標準ライブラリだけで動作します (wget / unzip も不要)。
=============================================================================
"""

import os
import re
import sys
import glob
import shutil
import signal
import hashlib
import argparse
import tempfile
import zipfile
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_BASE_URL = "https://dl.google.com/android/repository/"
REPO_XML_URL = REPO_BASE_URL + "repository2-1.xml"
CMDLINE_TOOLS_PACKAGE = "cmdline-tools;latest"
DHU_PACKAGE = "extras;google;auto"
PLATFORM_TOOLS_PACKAGE = "platform-tools"
MIN_JAVA_VERSION = 17
# Java が無いときに apt でインストールを試みるパッケージ (先に見つかったものを使う)
JAVA_APT_PACKAGES = ["openjdk-21-jdk-headless", "openjdk-17-jdk-headless"]
# DHU が必要とする共有ライブラリ → apt のパッケージ名の候補 (先に見つかったものを使う)
LIB_APT_PACKAGES = {
    "libc++.so.1": ["libc++1"],
    "libc++abi.so.1": ["libc++abi1"],
    "libasound.so.2": ["libasound2t64", "libasound2"],
    "libusb-1.0.so.0": ["libusb-1.0-0"],
}

SCRIPT_DIR = Path(__file__).resolve().parent
TOTAL_STEPS = 6
# 最後にまとめて表示する注意事項
SUMMARY = {"warnings": []}


# =============================================================================
# 出力ヘルパー (画面のログにもそのまま表示される)
# =============================================================================
def say(message=""):
    print(message, flush=True)


def step(no, title):
    say("")
    say(f"[{no}/{TOTAL_STEPS}] {title}")


def fail(message, hint=None, code=1):
    say(f"[エラー] {message}")
    if hint:
        for line in hint.splitlines():
            say(f"         {line}")
    sys.exit(code)


def is_interactive():
    return sys.stdin is not None and sys.stdin.isatty()


# =============================================================================
# 1. Java
# =============================================================================
def java_major_version(java_bin):
    """`java -version` の出力から メジャーバージョン (17, 21 など) を取り出す。"""
    try:
        proc = subprocess.run(
            [java_bin, "-version"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r'version "(\d+)(?:\.(\d+))?', proc.stdout)
    if not m:
        return None
    major = int(m.group(1))
    if major == 1 and m.group(2):  # 1.8.0 形式 → 8
        major = int(m.group(2))
    return major


def find_java():
    """
    17 以降の Java を探す。見つかれば (java のパス, バージョン, JAVA_HOME or None) を返す。
    PATH の java が古くても、/usr/lib/jvm に新しい JDK があればそちらを使う。
    """
    candidates = []
    if os.environ.get("JAVA_HOME"):
        candidates.append((str(Path(os.environ["JAVA_HOME"]) / "bin" / "java"), os.environ["JAVA_HOME"]))
    which_java = shutil.which("java")
    if which_java:
        candidates.append((which_java, None))
    for home in sorted(glob.glob("/usr/lib/jvm/*/"), reverse=True):
        candidates.append((os.path.join(home, "bin", "java"), home.rstrip("/")))

    best = None
    for java_bin, java_home in candidates:
        if not (os.path.isfile(java_bin) and os.access(java_bin, os.X_OK)):
            continue
        ver = java_major_version(java_bin)
        if ver is None:
            continue
        if ver >= MIN_JAVA_VERSION:
            return java_bin, ver, java_home
        if best is None:
            best = (java_bin, ver, java_home)
    return best  # 古い Java しかない場合はそれを返す (呼び出し側で判定)


def apt_pick(candidates):
    """apt で入手できるパッケージ名を候補から選ぶ (Ubuntu のバージョンで名前が違うものがあるため)。"""
    for pkg in candidates:
        try:
            r = subprocess.run(["apt-cache", "show", pkg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            break
        if r.returncode == 0:
            return pkg
    return candidates[-1]


APT_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")


def root_command_prefix():
    """
    root 権限でコマンドを実行する方法を選ぶ。
      - ターミナルから実行      : sudo (パスワードはターミナルで入力)
      - パスワード不要の sudo   : sudo -n
      - 画面 (サービス) から実行: pkexec (デスクトップにパスワード入力のダイアログが出る)
    返り値: (コマンドの先頭部分 or None, 方法の説明)
    """
    if os.geteuid() == 0:
        return [], "root"
    if shutil.which("sudo"):
        if is_interactive():
            return ["sudo"], "sudo"
        try:
            ok = subprocess.run(["sudo", "-n", "true"], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        if ok:
            return ["sudo", "-n"], "sudo (パスワード不要)"
    if shutil.which("pkexec"):
        return ["pkexec"], "pkexec"
    return None, "sudo / pkexec が使えません"


def apt_install(packages, what):
    """
    足りないパッケージを apt でインストールする。成功したら True。
    apt-get update と install を 1 回の権限昇格でまとめて実行する (パスワード入力を 1 回で済ませるため)。
    """
    packages = [p for p in packages if APT_PACKAGE_RE.match(p)]
    if not packages:
        return False
    if not shutil.which("apt-get"):
        say("  apt-get が見つからないため、自動インストールできません。")
        return False

    prefix, method = root_command_prefix()
    if prefix is None:
        say(f"  root 権限で実行する方法がないため、自動インストールできません ({method})。")
        return False

    script = ("apt-get update || true; "
              "DEBIAN_FRONTEND=noninteractive apt-get install -y " + " ".join(packages))
    say(f"  {what}を自動でインストールします: " + " ".join(packages))
    if method == "sudo":
        say("  ※ sudo のパスワードを求められたら入力してください。")
    elif method == "pkexec":
        say("  ※ デスクトップにパスワード入力のダイアログが表示されます。ログインに使うパスワードを入力してください。")
    say(f"  $ {' '.join(prefix) + ' ' if prefix else ''}sh -c \"{script}\"")

    try:
        code = subprocess.call(prefix + ["/bin/sh", "-c", script],
                               stdin=None if is_interactive() else subprocess.DEVNULL)
    except OSError as e:
        say(f"  インストールを実行できませんでした: {e}")
        return False

    if code == 0:
        say(f"  OK: {what}をインストールしました")
        return True
    if method == "pkexec" and code in (126, 127):
        say("  パスワード入力がキャンセルされたか、認証できませんでした"
            " (パスワード入力のダイアログを表示できない環境の場合もあります)。")
    else:
        say(f"  インストールに失敗しました (終了コード {code})。"
            "他のソフトの更新 (apt) が動いている場合は、終わってからもう一度実行してください。")
    return False


def ensure_java(args):
    step(1, "Java の確認 (sdkmanager の実行に Java 17 以降が必要です)")
    found = find_java()
    if found and found[1] >= MIN_JAVA_VERSION:
        java_bin, ver, java_home = found
        say(f"  OK: Java {ver} ({java_bin})")
        return java_home

    if found:
        say(f"  見つかった Java は {found[1]} です (17 以降が必要)。")
    else:
        say("  Java が見つかりません。")

    java_pkg = apt_pick(JAVA_APT_PACKAGES)
    hint = "ターミナルで次を実行してから、もう一度セットアップしてください:\n" \
           f"  sudo apt update && sudo apt install -y {java_pkg}"

    if args.no_install_deps:
        fail("Java 17 以降が必要です (--no-install-deps のため自動インストールしません)。", hint, code=2)

    if apt_install([java_pkg], "Java (JDK)"):
        found = find_java()
        if found and found[1] >= MIN_JAVA_VERSION:
            say(f"  OK: Java {found[1]} ({found[0]})")
            return found[2]
        fail("Java をインストールしましたが、Java 17 以降が見つかりません。", hint, code=2)

    fail("Java 17 以降をインストールできませんでした。", hint, code=2)


# =============================================================================
# 2. 最新版 Command-line Tools の情報を取得
# =============================================================================
def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "LinuxAuto-setup-sdk"})
    return urllib.request.urlopen(req, timeout=timeout)


def find_latest_cmdline_tools():
    """
    repository2-1.xml の <remotePackage path="cmdline-tools;latest"> から、
    Linux 用アーカイブのファイル名・サイズ・SHA-1 を取り出す。
    """
    step(2, "最新版 Android SDK Command-line Tools の確認")
    say(f"  取得: {REPO_XML_URL}")
    try:
        with http_get(REPO_XML_URL) as res:
            xml_bytes = res.read()
    except Exception as e:
        fail(f"パッケージ一覧を取得できませんでした: {e}", "ネットワーク接続を確認してください。")

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        fail(f"パッケージ一覧を解析できませんでした: {e}")

    for pkg in root.iter():
        if not pkg.tag.endswith("remotePackage") or pkg.get("path") != CMDLINE_TOOLS_PACKAGE:
            continue
        version = ".".join(
            (pkg.findtext("revision/" + k) or "") for k in ("major", "minor") if pkg.findtext("revision/" + k)
        )
        for archive in pkg.iter("archive"):
            if (archive.findtext("host-os") or "").strip() != "linux":
                continue
            url = (archive.findtext("complete/url") or "").strip()
            if not re.fullmatch(r"commandlinetools-linux-\d+_latest\.zip", url):
                continue
            info = {
                "file": url,
                "url": REPO_BASE_URL + url,
                "size": int(archive.findtext("complete/size") or 0),
                "sha1": (archive.findtext("complete/checksum") or "").strip().lower(),
                "version": version,
            }
            say(f"  最新版: {info['file']} (バージョン {version or '不明'})")
            return info

    fail(f"パッケージ一覧に {CMDLINE_TOOLS_PACKAGE} の Linux 用ファイルが見つかりませんでした。")


# =============================================================================
# 3. ダウンロードと配置
# =============================================================================
def download(info, dest):
    say(f"  ダウンロード: {info['url']}")
    sha1 = hashlib.sha1()
    done = 0
    last_step = -1
    try:
        with http_get(info["url"], timeout=120) as res, open(dest, "wb") as f:
            total = info["size"] or int(res.headers.get("Content-Length") or 0)
            while True:
                chunk = res.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                sha1.update(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    if pct // 10 != last_step:
                        last_step = pct // 10
                        say(f"  ... {pct}% ({done // (1024 * 1024)} / {total // (1024 * 1024)} MB)")
    except Exception as e:
        fail(f"ダウンロードに失敗しました: {e}", "ネットワーク接続を確認して、もう一度実行してください。")

    if info["sha1"] and sha1.hexdigest() != info["sha1"]:
        fail("ダウンロードしたファイルのチェックサムが一致しません (破損している可能性があります)。",
             "もう一度実行してください。")
    say("  OK: チェックサム (SHA-1) を確認しました")


def extract_zip(zip_path, dest_dir):
    """zip を展開する。実行権限 (bin/sdkmanager など) も復元する。"""
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            out = zf.extract(member, dest_dir)
            mode = (member.external_attr >> 16) & 0o777
            if mode and not member.is_dir():
                os.chmod(out, mode)


def ensure_cmdline_tools(sdk_root, args):
    latest_dir = sdk_root / "cmdline-tools" / "latest"
    sdkmanager = latest_dir / "bin" / "sdkmanager"

    if sdkmanager.is_file() and not args.reinstall:
        step(2, "最新版 Android SDK Command-line Tools の確認")
        say(f"  インストール済みのため、ダウンロードを省略します: {latest_dir}")
        say("  (入れ直す場合は --reinstall を付けて実行してください)")
        step(3, "Command-line Tools の配置")
        say("  省略しました")
        return sdkmanager

    info = find_latest_cmdline_tools()
    step(3, f"Command-line Tools のダウンロードと配置 ({latest_dir})")
    (sdk_root / "cmdline-tools").mkdir(parents=True, exist_ok=True)
    # 前回中断したときの作業フォルダが残っていれば片付ける
    for leftover in (sdk_root / "cmdline-tools").glob("linux-auto-sdk-*"):
        shutil.rmtree(str(leftover), ignore_errors=True)
    with tempfile.TemporaryDirectory(prefix="linux-auto-sdk-", dir=str(sdk_root / "cmdline-tools")) as tmp:
        zip_path = Path(tmp) / info["file"]
        download(info, zip_path)
        say("  展開しています...")
        extract_zip(zip_path, tmp)
        extracted = Path(tmp) / "cmdline-tools"
        if not (extracted / "bin" / "sdkmanager").is_file():
            fail("展開したファイルの中に cmdline-tools/bin/sdkmanager が見つかりません。")
        if latest_dir.exists():
            say(f"  既存の {latest_dir} を置き換えます")
            shutil.rmtree(str(latest_dir))
        shutil.move(str(extracted), str(latest_dir))
    say(f"  OK: {latest_dir}")
    return sdkmanager


# =============================================================================
# 4. sdkmanager でパッケージをインストール
# =============================================================================
PROGRESS_RE = re.compile(r"^\[[= ]*\]\s*(\d+)%\s*(.*)$")


def run_sdkmanager_auto_accept(cmd, env):
    """
    ライセンスへの同意 (y) を自動入力しながら sdkmanager を実行し、
    進捗バー (\\r で書き換わる行) やライセンス全文を間引いて表示する。
    """
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env)
    try:
        proc.stdin.write(b"y\n" * 200)
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass

    state = {"in_license": False, "progress": None}

    def emit(raw):
        line = raw.decode("utf-8", errors="replace").strip()
        # 空行と、Java が環境変数 (JAVA_TOOL_OPTIONS 等) を読んだときの通知は省く
        if not line or line.startswith("Picked up "):
            return
        if "Accept? (y/N)" in line:
            state["in_license"] = False
            say("  → ライセンスに同意しました (y)")
            line = line.split("Accept? (y/N):", 1)[-1].strip()
            if not line:
                return
        if state["in_license"]:
            return
        if line.startswith("License "):
            state["in_license"] = True
            say(f"  ライセンス: {line[len('License '):].rstrip(':')}")
            return
        m = PROGRESS_RE.match(line)
        if m:
            key = (int(m.group(1)) // 10, m.group(2))
            if key != state["progress"]:
                state["progress"] = key
                say(f"  ... {m.group(1)}% {m.group(2)}".rstrip())
            return
        say(f"  {line}")

    buf = b""
    while True:
        chunk = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(1)
        if not chunk:
            break
        buf += chunk
        parts = re.split(rb"[\r\n]", buf)
        buf = parts.pop()
        for part in parts:
            emit(part)
    if buf:
        emit(buf)
    return proc.wait()


def install_packages(sdkmanager, sdk_root, java_home, args):
    packages = [DHU_PACKAGE]
    if not args.no_platform_tools:
        packages.append(PLATFORM_TOOLS_PACKAGE)
    step(4, "sdkmanager でパッケージをインストール: " + ", ".join(packages))

    env = os.environ.copy()
    if java_home:
        env["JAVA_HOME"] = java_home
    cmd = [str(sdkmanager), f"--sdk_root={sdk_root}"] + packages
    say("  $ " + " ".join(cmd))

    if args.yes:
        code = run_sdkmanager_auto_accept(cmd, env)
    else:
        say("  ※ Android SDK のライセンスが表示されたら、内容を確認して y を入力してください。")
        say("    (自動で同意する場合は --yes を付けて実行します)")
        code = subprocess.call(cmd, env=env)

    if code != 0:
        fail(f"sdkmanager が失敗しました (終了コード {code})。",
             "ライセンスに同意しなかった場合や、ネットワークが切れた場合に発生します。もう一度実行してください。")
    say("  OK: インストールが完了しました")


# =============================================================================
# 5. 実行権限
# =============================================================================
def ensure_dhu_executable(sdk_root, args):
    step(5, "desktop-head-unit に実行権限を付与し、必要なライブラリを確認")
    dhu = sdk_root / "extras" / "google" / "auto" / "desktop-head-unit"
    if not dhu.is_file():
        fail(f"desktop-head-unit が見つかりません: {dhu}")
    os.chmod(str(dhu), dhu.stat().st_mode | 0o111)
    say(f"  OK: {dhu}")

    ensure_dhu_libraries(dhu, args)
    return dhu


def missing_libraries(dhu):
    if not shutil.which("ldd"):
        return []
    try:
        out = subprocess.run(["ldd", str(dhu)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted({line.split("=>")[0].strip() for line in out.splitlines() if "not found" in line})


def ensure_dhu_libraries(dhu, args):
    """DHU の起動に必要な共有ライブラリ (libc++ など) が足りなければ、自動でインストールする。"""
    missing = missing_libraries(dhu)
    if not missing:
        say("  OK: DHU の実行に必要なライブラリはそろっています")
        return

    say("  DHU の実行に必要なライブラリが見つかりません: " + ", ".join(missing))
    packages = sorted({apt_pick(LIB_APT_PACKAGES[lib]) for lib in missing if lib in LIB_APT_PACKAGES})
    unknown = [lib for lib in missing if lib not in LIB_APT_PACKAGES]
    command = "sudo apt update && sudo apt install -y " + " ".join(packages) if packages else ""

    if packages and not args.no_install_deps and apt_install(packages, "DHU に必要なライブラリ"):
        missing = missing_libraries(dhu)
        if not missing:
            say("  OK: DHU の実行に必要なライブラリはそろいました")
            return
        say("  まだ見つからないライブラリがあります: " + ", ".join(missing))
        unknown = [lib for lib in missing if lib not in LIB_APT_PACKAGES]
        packages = sorted({apt_pick(LIB_APT_PACKAGES[lib]) for lib in missing if lib in LIB_APT_PACKAGES})
        command = "sudo apt update && sudo apt install -y " + " ".join(packages) if packages else ""

    say("  [注意] このままでは DHU を起動できません。ターミナルで次を実行してください:")
    if command:
        say(f"         {command}")
    if unknown:
        say("         次のライブラリは apt で提供元のパッケージを探してインストールしてください: " + ", ".join(unknown))
    SUMMARY["warnings"].append(
        "DHU の実行に必要なライブラリが不足しています" + (f" → {command}" if command else ""))


# =============================================================================
# 6. Linux Auto の設定と headunit.ini
# =============================================================================
def load_config_manager():
    """app.py の ConfigManager を読み込む (設定ファイルの形式を画面と完全に揃えるため)。"""
    sys.path.insert(0, str(SCRIPT_DIR))
    sys.dont_write_bytecode = True  # app.py の __pycache__ を作らない
    try:
        import app as linux_auto_app  # noqa: E402
    except Exception as e:
        fail(f"app.py を読み込めませんでした: {e}", "setup-sdk.py は app.py と同じフォルダに置いて実行してください。")
    return linux_auto_app


def save_settings(dhu, args):
    step(6, "Linux Auto の設定と headunit.ini を保存")
    la = load_config_manager()
    cm = la.ConfigManager

    cm.save_app_config({"dhu_path": str(dhu)})
    say(f"  OK: DHU のパスを保存しました → {la.APP_CONFIG_PATH}")
    say(f"      dhu_path = {dhu}")

    ini_path = la.HEADUNIT_INI_PATH
    if ini_path.exists() and not args.reset_ini:
        values = cm.load_headunit_ini()
        note = "既存の値を引き継いで書き込みました"
    else:
        values = dict(cm.DEFAULT_INI["general"])
        note = "既定値で書き込みました" if not ini_path.exists() else "既定値で上書きしました (--reset-ini)"
    saved = cm.save_headunit_ini(values)
    say(f"  OK: {ini_path} を{note}")
    for key, value in saved.items():
        say(f"      {key} = {value}")


# =============================================================================
# メイン
# =============================================================================
def default_sdk_root():
    for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(env_var):
            return Path(os.environ[env_var]).expanduser()
    return Path.home() / "Android" / "Sdk"


def main():
    parser = argparse.ArgumentParser(
        description="Linux Auto: Android SDK と Desktop Head Unit (DHU) を自動でセットアップします。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Android SDK のライセンスに自動で同意する")
    parser.add_argument("--sdk-root", type=Path, default=default_sdk_root(),
                        help="Android SDK のインストール先")
    parser.add_argument("--no-platform-tools", action="store_true",
                        help="platform-tools (adb) をインストールしない")
    parser.add_argument("--reinstall", action="store_true",
                        help="インストール済みでも Command-line Tools を最新版でダウンロードし直す")
    parser.add_argument("--reset-ini", action="store_true",
                        help="headunit.ini を既定値で上書きする (既定では既存の値を引き継ぐ)")
    parser.add_argument("--no-install-deps", action="store_true",
                        help="Java 17 以降や DHU に必要なライブラリ (libc++ 等) が足りなくても、"
                             "自動でインストールしない (必要なコマンドを表示するだけ)")
    args = parser.parse_args()

    sdk_root = args.sdk_root.expanduser().resolve()

    say("=" * 60)
    say("  Linux Auto - Android SDK / DHU 自動セットアップ")
    say("=" * 60)
    say(f"  SDK のインストール先: {sdk_root}")

    java_home = ensure_java(args)
    sdkmanager = ensure_cmdline_tools(sdk_root, args)
    install_packages(sdkmanager, sdk_root, java_home, args)
    dhu = ensure_dhu_executable(sdk_root, args)
    save_settings(dhu, args)

    say("")
    if SUMMARY["warnings"]:
        say("[完了] セットアップは完了しましたが、次の対応が必要です:")
        for w in SUMMARY["warnings"]:
            say(f"  - {w}")
    else:
        say("[完了] セットアップが完了しました。Linux Auto の画面から「接続開始」できます。")


def _on_terminate(signum, frame):
    # 画面の「中止」ボタン (SIGTERM) でも、作業中の一時ファイルを片付けてから終了する
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _on_terminate)
    try:
        main()
    except KeyboardInterrupt:
        say("")
        say("[中断] セットアップを中断しました。")
        sys.exit(130)
