# Linux Auto

**Google DHU (Desktop Head Unit) を使用した Ubuntu / Kubuntu 向け Android Auto 接続サポート GUI**

[![Developer](https://img.shields.io/badge/Developer-ENOKI%20ELECTRONICS-blue)](https://enoki.xyz)
[![Platform](https://img.shields.io/badge/Platform-Ubuntu%20%7C%20Kubuntu-E95420)](https://ubuntu.com)
[![Dependency](<https://img.shields.io/badge/Dependencies-Zero%20(Standard%20Library%20Only)-brightgreen>)]()

---

## 概要

**Linux Auto** は、毎回ターミナルから複雑なコマンドや設定ファイルを扱わなければ使えなかった Ubuntu 系列 OS での Android Auto (Google DHU) 接続を、直感的な Web GUI からワンクリックで管理・実行できるようにするツールです。

- **サービス常駐 + 画面はアイコンから**: サーバーは systemd ユーザーサービスとしてログイン時に自動起動。デスクトップアイコンは画面を開くだけなので、いつ開いても・閉じても接続は維持されます。
- **USB / Wi-Fi 接続の切り替え**: USB（`desktop-head-unit --usb`）に加え、スマホのテザリングに接続した Wi-Fi 接続に対応。Wi-Fi は「方法1: ADB＋ポートフォワーディング」「方法2: ヘッドユニットサーバーへ直接接続」から選べ、スマホの IP はテザリングのゲートウェイから自動検出します。
- **10秒自動復帰機能**: ドライブ中やテスト中に不意にUSBケーブルが抜けてプロセスが落ちても、**切断後10秒間は自動的に再接続待機・復帰**を試みます（Wi-Fi 切断時も同様）（手動停止ボタンを押した場合を除く）。
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

Linux Auto は **「サーバー（常駐）」** と **「画面（WebUI）」** を分けて使う構成です。

| 役割                    | 担当                                                           | 起動タイミング                                           |
| :---------------------- | :------------------------------------------------------------- | :------------------------------------------------------- |
| サーバー本体 (`app.py`) | systemd ユーザーサービス `linux-auto.service`                  | PC にログインしたとき自動（`--boot` 指定時は電源投入時） |
| 画面 (WebUI)            | デスクトップ / メニューの「Linux Auto」アイコン (`open-ui.sh`) | 操作したいときだけ                                       |

画面（ブラウザ / PWA）を閉じても、サーバーと Android Auto 接続は止まりません。

### 手順1: サーバーをサービスとして登録する（初回のみ・おすすめ）

```bash
cd ~/LinuxAuto
chmod +x install-service.sh
./install-service.sh
```

これだけで以下が行われます（`sudo` 不要）。

- `~/.config/systemd/user/linux-auto.service` の作成
- ログイン時の自動起動の有効化（`systemctl --user enable`）と即時起動
- 旧方式の自動起動設定 `~/.config/autostart/linux-auto.desktop` が残っていれば、二重起動防止のため `linux-auto.desktop.disabled` にリネームして無効化

> **注意**: `./start.sh` で手動起動したサーバーが動いている場合は、先にそのターミナルで Ctrl+C を押して終了してから登録してください。

#### 電源投入直後（ログイン前）からサーバーを起動したい場合（任意）

```bash
./install-service.sh --boot
```

`loginctl enable-linger` を設定し、ログイン前からユーザーサービスを起動します。
ただし Android Auto の画面（DHU のウィンドウ）はデスクトップに表示されるため、実際の接続はログイン後になります。車載PCなどでは自動ログインと組み合わせるのがおすすめです。

#### なぜ「ユーザーサービス」なのか

DHU はログイン中ユーザーのデスクトップにウィンドウを出し、ユーザーのサウンドサーバーに音声を出力します。root で動くシステムサービス（`/etc/systemd/system`）からはこれらにアクセスできないため、ユーザー単位の systemd サービスとして登録しています。
また、サーバーは DHU を起動する直前に `systemctl --user show-environment` から最新の `DISPLAY` / `WAYLAND_DISPLAY` などを取得するため、ログイン前に起動していても、ログアウト→再ログインしても正しく画面を表示できます。

#### サービスの操作コマンド

```bash
systemctl --user status linux-auto      # 状態確認
journalctl --user -u linux-auto -f      # ログをリアルタイム表示
systemctl --user restart linux-auto     # 再起動（git pull 等でコードを更新した後は必ず実行）
systemctl --user stop linux-auto        # 停止
systemctl --user start linux-auto       # 起動
./install-service.sh --uninstall        # 登録解除（自動起動をやめる）
loginctl disable-linger $USER           # --boot を元に戻す
```

### 手順2: 起動アイコン（画面を開くだけ）を登録する

```bash
chmod +x install-desktop-shortcut.sh
./install-desktop-shortcut.sh
```

アプリケーションメニューとデスクトップに「Linux Auto」アイコンが追加されます（以前のバージョンで登録済みの場合も再実行してください）。
アイコンは `open-ui.sh` を呼び出し、次のように動作します。

1. サーバーが応答していれば、そのままブラウザで `http://127.0.0.1:8855` を開く
2. サービスが停止していれば `systemctl --user start linux-auto` で起動してから開く
3. サービス未登録の場合のみ、サーバーを一時的にバックグラウンド起動してから開く（ログ: `~/.cache/linux-auto/server.log`）

ターミナルから `./open-ui.sh` を実行しても同じ動作になります。

### 参考: 手動（フォアグラウンド）起動

デバッグ時など、ターミナルでログを見ながらサーバーを動かしたい場合：

```bash
./start.sh               # サーバー起動 + ブラウザを開く
./start.sh --no-browser  # ブラウザを開かずにサーバーだけ起動
```

サービスがすでに動いている状態で実行した場合は、二重起動せずに画面だけを開いて終了します。

### 参考: CLI直接接続ツール (connect.sh)

WebUI を使わず、ターミナルから直接 DHU をフォアグラウンド実行するツールです（USB 接続専用）。設定画面で保存した `desktop-head-unit` のパスや `~/.android/headunit.ini` の内容がそのまま適用され、USB切断時の10秒自動復帰ループも行われます。

```bash
chmod +x connect.sh
./connect.sh
```

---

## Wi-Fi（テザリング）接続

メイン画面の **「Wi-Fi接続」** を選ぶと、USB ケーブルなしで Android Auto を使えます。
**Linux 端末をスマホのテザリング（Wi-Fi アクセスポイント）に接続する運用**を前提に設計しています。

### スマホの IP アドレスの自動検出

テザリング中は Linux 端末の **デフォルトゲートウェイ＝スマホ本体** です。Linux Auto は接続のたびに `/proc/net/route` から Wi-Fi インターフェースのゲートウェイを読み取り、スマホの IP として使います（`ip` / `nmcli` 等の外部コマンドは不要）。

- Android 11 以降はテザリングのアドレスが接続ごとに変わることがあるため、`192.168.43.1` のような固定値は使いません。
- 再接続（10秒自動復帰）のたびに検出し直すため、テザリングを入れ直してアドレスが変わっても追従します。
- 自宅ルーター等の同一 LAN で使う場合は、画面で「手動入力」を選んでスマホの IP を入力します。

### 共通の準備

1. スマホのテザリングを ON にし、Linux 端末をそのアクセスポイントに Wi-Fi 接続する
2. スマホの Android Auto 設定 →「︙」→ **「ヘッドユニットサーバーを起動」**
3. メイン画面の「ネットワーク状態」に **スマホのIP（ゲートウェイ）** が表示されていることを確認

### 方法1: ADB（Wi-Fiデバッグ）＋ポートフォワーディング（開発・テスト向け）

「接続開始」を押すと、Linux Auto が以下を自動で実行します。

```bash
adb connect <スマホIP>:<ADBポート>     # 既に接続済みならスキップ
adb -s <スマホIP>:<ADBポート> forward tcp:5277 tcp:5277
./desktop-head-unit                      # 引数なし = localhost:5277 へ接続
```

事前に adb（platform-tools）が必要です：`~/Android/Sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=$HOME/Android/Sdk "platform-tools"`

| 方式                         | 手順                                                                                                                                                        | 向いている環境                                 |
| :--------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------- |
| **A: adb tcpip**（おすすめ） | USB デバッグを ON → 一度だけ USB 接続して画面の「① USB経由で TCP/IP モードを有効化」（= `adb tcpip 5555`）→ ケーブルを外す                                  | テザリング運用（スマホ再起動後は再実行が必要） |
| **B: ワイヤレスデバッグ**    | 開発者向けオプション →「ワイヤレスデバッグ」→ 画面の「ペアリング」欄にペア設定ポートとコードを入力 → 「IP アドレスとポート」のポートを ADB 接続ポートに入力 | Android 11 以降・同一 Wi-Fi ルーター環境       |

> テザリングの親機になっているスマホでは、機種によってワイヤレスデバッグを ON にできません。その場合は A を使ってください。

### 方法2: ヘッドユニットサーバーへ直接接続（おすすめ・追加機材なし）

ADB を使わず、スマホのヘッドユニットサーバー（TCP 5277）へ DHU から直接接続します。
DHU 公式の `--adb=<[ホスト:]ポート>` オプション（接続先のホスト・ポートを上書き）を利用しています。

```bash
./desktop-head-unit --adb=<スマホIP>:5277
```

- 「接続開始」の前に、画面の **「ヘッドユニットサーバーの疎通確認」** で接続できるかを確認できます（接続開始時にも自動で確認します）。
- DHU から直接つながらない場合は、接続経路を **「内蔵リレー経由」** に切り替えます。`socat TCP-LISTEN:5277,fork TCP:<スマホIP>:5277` と同じ中継を Linux Auto 自身（Python 標準ライブラリ）が行うため、socat のインストールは不要です。
- 疎通確認で「接続を拒否しました」となる場合は、ヘッドユニットサーバーが起動していないか、お使いの端末・Android Auto のバージョンでは Wi-Fi 側からの接続を受け付けていない可能性があります。その場合は方法1を使ってください。

### 設定の保存先

接続方式は `~/.config/linux-auto/config.json` に保存され、サービス再起動後も引き継がれます。

```jsonc
{
  "connection_type": "wifi", // "usb" | "wifi"
  "wifi_mode": "direct", // "adb" (方法1) | "direct" (方法2)
  "phone_ip_auto": true, // true: テザリング親機を自動検出
  "phone_ip": "", // 手動指定時のスマホ IP
  "adb_port": 5555, // 方法1: adb connect のポート
  "hu_port": 5277, // ヘッドユニットサーバーのポート
  "direct_transport": "adb_flag", // 方法2: "adb_flag" (--adb=IP:5277) | "relay" (内蔵リレー)
}
```

---

## 既知の不具合 (Known Issues)

今のところなし

## PWA (Progressive Web App) 対応

Google Chrome, Chromium, Microsoft Edge などで `http://127.0.0.1:8855` を開くと、アドレスバー右端またはサイドバーの「アプリ化」ボタンから **PWAアプリとしてインストール** できます。

- アドレスバーやタブのない独立したネイティブアプリ風ウィンドウで起動します。
- 車載タッチスクリーンや全画面表示に最適です。

---

## 画面構成と機能

### 1. メインページ (Main)

- **接続方式の切り替え**: 「USB接続」「Wi-Fi接続」のタブで切り替えます。Wi-Fi 接続では以下を操作できます（接続中は変更不可）。
  - **ネットワーク状態**: 接続中の Wi-Fi（SSID）、インターフェース、この PC の IP、スマホの IP（ゲートウェイ）
  - **接続先スマホの IP**: 自動（テザリング親機を検出）/ 手動入力
  - **接続モード**: 方法1（ADB＋ポートフォワーディング）/ 方法2（ヘッドユニットサーバーへ直接）
  - **方法1**: ADB 接続ポート、「USB経由で TCP/IP モードを有効化」「Wi-Fi で接続テスト」、ワイヤレスデバッグのペアリング、adb 端末一覧
  - **方法2**: ヘッドユニットサーバーのポート、接続経路（DHU から直接 / 内蔵リレー経由）、疎通確認
- **接続開始 (DHU起動)**: 選択中の接続方式で DHU を起動します。
- **切断 / 停止**: 接続を終了します。
- **ステータスリング & インジケーター**: 現在の接続状態（待機中 / 実行中 / 再接続待機中 / エラー）を視覚的に表示。
- **10秒自動復帰プログレスバー**: USB抜け・Wi-Fi切断等で不意にプロセスが終了した際、10秒間のカウントダウンを表示しながらケーブル再挿入を待機します。
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
[general]
touch = true
touchpad = false
resolution = 1920x1080
dpi = 280
framerate = 30
```

### 3. 導入ガイドページ (Guide)

- Android SDK / DHU の導入、スマートフォン側の設定、**Wi-Fi（テザリング）接続の準備（方法1 / 方法2）**、**サービス登録 (`install-service.sh`)**、**起動アイコン登録 (`install-desktop-shortcut.sh`)** の手順をコピーボタン付きで掲載。
- 現在のサーバー起動方式（サービス常駐 / 手動起動）を表示します。

### 4. Aboutページ

- 開発者（エノキ電気）、ホームページリンク、GitHubリンク、バージョン情報を表示。

---

## プロジェクト構造とソースコード解説

Node.js, PHP, Spring Boot の開発経験をお持ちの方向けに、プロジェクト構造と対応関係を記載しています。

```
LinuxAuto/
├── app.py                      # バックエンド (Python 3 標準ライブラリのみ)
├── install-service.sh          # systemd ユーザーサービス登録 / 解除スクリプト
├── open-ui.sh                  # 画面を開くだけのランチャー (アイコンの起動先)
├── start.sh                    # 手動 (フォアグラウンド) 起動シェル
├── connect.sh                  # ターミナル直結CLI起動ツール
├── install-desktop-shortcut.sh # デスクトップショートカット自動インストーラー
├── linux-auto.desktop          # XDG デスクトップエントリ定義 (テンプレート)
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
4. **アイコンを押しても画面が開かない / 「サーバーを起動できませんでした」と出る場合**:
   - `systemctl --user status linux-auto` でサービスの状態を、`journalctl --user -u linux-auto -n 50` でエラー内容を確認してください。
   - サービス未登録の場合は `~/.cache/linux-auto/server.log` を確認してください。
   - 別のプログラムがポート `8855` を使っていないか `ss -ltnp | grep 8855` で確認してください。
5. **サービス起動中に「デスクトップセッション (DISPLAY / WAYLAND_DISPLAY) が見つかりません」と出る場合**:
   - デスクトップにログインしてから接続してください。ログイン済みでも出る場合は、次を実行してから再接続してください：
     ```bash
     systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS
     ```
6. **Wi-Fi 接続で「スマホの IP アドレスを自動検出できません」と出る場合**:
   - Linux 端末がスマホのテザリングに Wi-Fi で接続されているか確認してください（画面の「ネットワーク状態」→「再取得」）。
   - 有線 LAN など他の経路が優先されている場合は、それを外すか「手動入力」でスマホの IP を指定してください。
7. **方法2 の疎通確認で「接続を拒否しました」「タイムアウト」と出る場合**:
   - スマホで「ヘッドユニットサーバーを起動」しているか（通知が出ているか）確認してください。
   - 改善しない場合は、端末側が Wi-Fi からの接続を受け付けていない可能性があるため、方法1（ADB）を使用してください。
8. **方法1 で「adb connect に失敗しました」と出る場合**:
   - スマホを USB 接続して「① USB経由で TCP/IP モードを有効化」を実行したか確認してください（スマホ再起動後は再実行が必要）。
   - スマホの画面に「USB デバッグを許可しますか？」が出ていたら「許可」をタップしてください。
9. **コードを更新したのに動作が変わらない場合**:
   - サービスは更新前のコードで動き続けています。`systemctl --user restart linux-auto` で再起動してください。

---

## ライセンス

GPL License
Copyright (c) 2026 エノキ電気 ENOKI ELECTRONICS
