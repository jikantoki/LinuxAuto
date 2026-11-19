# Linux Auto

**Google DHU (Desktop Head Unit) を使用した Ubuntu / Kubuntu 向け Android Auto 接続サポート GUI**

[![Developer](https://img.shields.io/badge/Developer-ENOKI%20ELECTRONICS-blue)](https://enoki.xyz)
[![Platform](https://img.shields.io/badge/Platform-Ubuntu%20%7C%20Kubuntu-E95420)](https://ubuntu.com)
[![Dependency](<https://img.shields.io/badge/Dependencies-Zero%20(Standard%20Library%20Only)-brightgreen>)]()

---

## 概要

**Linux Auto** は、毎回ターミナルから複雑なコマンドや設定ファイルを扱わなければ使えなかった Ubuntu 系列 OS での Android Auto (Google DHU) 接続を、直感的な Web GUI からワンクリックで管理・実行できるようにするツールです。

- **ワンクリック有線接続**: `desktop-head-unit --usb` をボタンひとつでバックグラウンド実行。
- **10秒自動復帰機能**: ドライブ中やテスト中に不意にUSBケーブルが抜けてプロセスが落ちても、**切断後10秒間は自動的に再接続待機・復帰**を試みます（手動停止ボタンを押した場合を除く）。
- **GUI設定エディタ**: `~/.android/headunit.ini` の各パラメータ（解像度、フレームレート、DPI、タッチパネル許可など）を画面から簡単に調整・保存できます。
- **長期保守性（Zero-Dependency）**: `pip` や外部ライブラリを一切使わず、Ubuntu標準の Python 3 標準ライブラリのみで動作。OSのメジャーアップデートやPythonのバージョン変更による依存関係破壊・保守地獄を回避します。

---

## 開発者情報

- **開発者**: エノキ電気 ENOKI ELECTRONICS
- **ホームページ**: [https://enoki.xyz](https://enoki.xyz)
- **GitHub**: [https://github.com/jikantoki](https://github.com/jikantoki)
- **プロジェクト名**: Linux Auto

---

## 動作環境・前提条件

### 対象OS

- Ubuntu 20.04 LTS / 22.04 LTS / 24.04 LTS 以降
- Kubuntu 20.04 以降（KDE Plasma環境）
- その他 Debian/Ubuntu 系列の Linux ディストリビューション

### 事前準備 (Linux側)

1. **Android SDK & DHU のインストール**:
   `Android-sdk` の `extras;google;auto` がインストールされている必要があります。

   ```bash
   # sdkmanager コマンドの例
   sdkmanager "extras;google;auto"
   ```

   インストール後、通常以下のパスに実行ファイルが生成されます：
   `~/Android/Sdk/extras/google/auto/desktop-head-unit`

2. **実行権限の確認**:
   ```bash
   chmod +x ~/Android/Sdk/extras/google/auto/desktop-head-unit
   ```

### 事前準備 (スマートフォン側 - Android Auto 開発者モード)

1. スマートフォンの「設定」→「Android Auto」を開きます。
2. 画面一番下の「バージョン」を10回連続でタップし、開発者モードを有効にします。
3. 右上のメニュー（︙）から **「ヘッドユニットサーバーを起動」** をタップします。
4. PCとスマートフォンをUSBケーブルで接続します。

---

## 使い方・起動方法

### 方法1: スクリプトから一発起動（おすすめ）

ターミナルを開き、以下のコマンドを実行します：

```bash
chmod +x start.sh
./start.sh
```

自動的に軽量サーバーが立ち上がり、デフォルトブラウザで `http://127.0.0.1:8855` が開きます。

### 方法2: デスクトップ / アプリメニューに登録して起動

```bash
chmod +x install-desktop-shortcut.sh
./install-desktop-shortcut.sh
```

Ubuntu / Kubuntu のアプリケーションランチャーやデスクトップに「Linux Auto」アイコンが追加され、ダブルクリックで起動できるようになります。

### 方法3: PC起動時の自動起動（ブラウザを開かないヘッドレス起動）

車載PCやLinux起動時に自動で立ち上げる場合、ブラウザが勝手に立ち上がらないようにする `--no-browser` オプションが利用可能です：

```bash
./start.sh --no-browser
```

#### Ubuntu / Kubuntu の自動起動 (Autostart) への一括登録コマンド:

```bash
mkdir -p ~/.config/autostart
cat <<EOF > ~/.config/autostart/linux-auto.desktop
[Desktop Entry]
Type=Application
Name=Linux Auto
Exec=$(pwd)/start.sh --no-browser
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Comment=Linux Auto Background Service
EOF
```

---

## PWA (Progressive Web App) 対応

Google Chrome, Chromium, Microsoft Edge などで `http://127.0.0.1:8855` を開くと、アドレスバー右端またはサイドバーの「アプリ化」ボタンから **PWAアプリとしてインストール** できます。

- アドレスバーやタブのない独立したネイティブアプリ風ウィンドウで起動します。
- 車載タッチスクリーンや全画面表示に最適です。

---

## 画面構成と機能

### 1. メインページ (Main)

- **接続開始 (DHU起動)**: ワンクリックで `desktop-head-unit --usb` を起動します。
- **切断 / 停止**: 接続を終了します。
- **ステータスリング & インジケーター**: 現在の接続状態（待機中 / 実行中 / 再接続待機中 / エラー）を視覚的に表示。
- **10秒自動復帰プログレスバー**: USB抜け等で不意にプロセスが終了した際、10秒間のカウントダウンを表示しながらケーブル再挿入を待機します。
- **リアルタイムログ**: DHUプロセスの標準出力・エラー出力をリアルタイムに確認できます。

### 2. 設定ページ (Settings)

- **DHU 実行ファイルのパス**: `desktop-head-unit` のフルパスを設定可能。「標準パス自動探索」ボタンで典型的なパスを自動検出します。
- **headunit.ini のパラメータ設定**:
  - `touch`: タッチパネルの許可 (`true` / `false`)
  - `touchpad`: タッチパッド (`true` / `false`、基本は `false`)
  - `resolution`: 画面解像度（1920x1080 FHD, 1280x720 HD, 800x480, 2560x1440 2K, カスタム入力）
  - `dpi`: 画面密度（スライダー＆数値入力、120〜480）
  - `framerate`: 最大フレームレート（30 fps / 60 fps）
  - ※ Google DHU の構文仕様に準拠し、コメント（`#` や `;`）を含まないクリーンな形式で `~/.android/headunit.ini` に保存されます。

```ini
[General]
touch = true
touchpad = false
resolution = 1920x1080
dpi = 280
framerate = 30
```

### 3. Aboutページ

- 開発者（エノキ電気）、ホームページリンク、GitHubリンク、バージョン情報を表示。

---

## プロジェクト構造とソースコード解説

Node.js, PHP, Spring Boot の開発経験をお持ちの方向けに、プロジェクト構造と対応関係を記載しています。

```
LinuxAuto/
├── app.py                      # バックエンド (Python 3 標準ライブラリのみ)
├── start.sh                    # Linux用ワンタッチ起動シェル
├── install-desktop-shortcut.sh # デスクトップショートカット自動インストーラー
├── linux-auto.desktop          # XDG デスクトップエントリ定義
├── static/                     # フロントエンド静的ファイル
│   ├── index.html              # SPA構成のメインHTML
│   ├── icon.svg                # アイコン用ベクター画像
│   ├── css/
│   │   └── style.css           # 車載インフォテインメント調ダークテーマ
│   └── js/
│       └── app.js              # フロントエンドロジック (Fetch API & ポーリング)
└── README.md                   # 本ドキュメント
```

### バックエンドの概念対比表

| 機能               | Linux Auto (app.py)                | Node.js (Express)         | Java (Spring Boot)            | PHP                               |
| :----------------- | :--------------------------------- | :------------------------ | :---------------------------- | :-------------------------------- |
| **Webサーバー**    | `http.server.ThreadingHTTPServer`  | `express()`               | Embedded Tomcat               | `php -S` / Apache                 |
| **ルーティング**   | `do_GET()`, `do_POST()`            | `app.get()`, `app.post()` | `@GetMapping`, `@PostMapping` | `switch($_SERVER['REQUEST_URI'])` |
| **プロセス起動**   | `subprocess.Popen([dhu, '--usb'])` | `child_process.spawn()`   | `ProcessBuilder`              | `proc_open()`                     |
| **設定ファイル**   | `configparser.ConfigParser()`      | `ini` パッケージ          | `@ConfigurationProperties`    | `parse_ini_file()`                |
| **非同期スレッド** | `threading.Thread(target=...)`     | Event Loop / Promise      | `@Async` / `Thread`           | CLI 常駐ワーカー                  |

---

## トラブルシューティング

1. **「desktop-head-unit が見つかりません」と表示される場合**:
   - 設定画面で `desktop-head-unit` のパスが正しいか確認してください。
   - Android Studio の SDK Manager で `Extras` → `Android Auto Desktop Head Unit emulator` にチェックが入っているか確認してください。
2. **「実行権限がありません」と表示される場合**:
   - `chmod +x /path/to/desktop-head-unit` を実行してバイナリに実行権限を付与してください。
3. **USB接続しても画面が表示されない場合**:
   - スマートフォン側で Android Auto の「ヘッドユニットサーバーを起動」がオンになっているか確認してください。
   - `adb devices` コマンドで端末がPCから認識されているか確認してください。

---

## ライセンス

MIT License
Copyright (c) 2026 エノキ電気 ENOKI ELECTRONICS
