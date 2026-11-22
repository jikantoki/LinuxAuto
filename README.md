# Linux Auto

**Google DHU (Desktop Head Unit) を使用した Ubuntu / Kubuntu 向け Android Auto 接続サポート GUI**

[![Developer](https://img.shields.io/badge/Developer-ENOKI%20ELECTRONICS-blue)](https://enoki.xyz)
[![Platform](https://img.shields.io/badge/Platform-Ubuntu%20%7C%20Kubuntu-E95420)](https://ubuntu.com)
[![Dependency](<https://img.shields.io/badge/Dependencies-Zero%20(Standard%20Library%20Only)-brightgreen>)]()

---

## 概要

**Linux Auto** は、毎回ターミナルから複雑なコマンドや設定ファイルを扱わなければ使えなかった Ubuntu 系列 OS での Android Auto (Google DHU) 接続を、直感的な Web GUI からワンクリックで管理・実行できるようにするツールです。

- **サービス常駐 + 画面はアイコンから**: サーバーは systemd ユーザーサービスとしてログイン時に自動起動。デスクトップアイコンは画面を開くだけなので、いつ開いても・閉じても接続は維持されます。
- **USB / Wi-Fi 接続の切り替え**: USB（`desktop-head-unit --usb`）に加え、スマホのテザリングに接続した Wi-Fi 接続に対応。Wi-Fi は「方法1: ヘッドユニットサーバーへ直接接続（既定）」「方法2: ADB＋ポートフォワーディング」から選べ、スマホの IP はテザリングのゲートウェイから自動検出します。
- **10秒自動復帰機能**: ドライブ中やテスト中に不意にUSBケーブルが抜けてプロセスが落ちても、**切断後10秒間は自動的に再接続待機・復帰**を試みます（Wi-Fi 切断時も同様）。DHU のウィンドウを自分で閉じた場合は、それを判別して自動復帰しません（手動停止ボタンを押した場合を除く）。
- **GUI設定エディタ**: `~/.android/headunit.ini` の各パラメータ（解像度、フレームレート、DPI、タッチパネル許可など）を画面から簡単に調整・保存できます。
- **長期保守性（Zero-Dependency）**: `pip` や外部ライブラリを一切使わず、Ubuntu標準の Python 3 標準ライブラリのみで動作。OSのメジャーアップデートやPythonのバージョン変更による依存関係破壊・保守地獄を回避します。

---

## 開発者情報

- **開発者**: エノキ電気 ENOKI ELECTRONICS
- **ホームページ**: [https://enoki.xyz](https://enoki.xyz)
- **GitHub**: [https://github.com/jikantoki/LinuxAuto](https://github.com/jikantoki/LinuxAuto)
- **プロジェクト名**: Linux Auto

---

## 動作環境・前提条件

### 対象OS

- Ubuntu 20.04 LTS / 22.04 LTS / 24.04 LTS 以降
- Kubuntu 20.04 以降（KDE Plasma環境）
- その他 Debian/Ubuntu 系列の Linux ディストリビューション

### 事前準備 (Linux側) - Android SDK と DHU の導入

Linux Auto を動かすには、Google 公式の `desktop-head-unit`（DHU）バイナリが必要です。DHU は Android SDK のパッケージ `extras;google;auto` として配布されているため、まず Android SDK を導入します。
いちばん簡単なのは **自動セットアップ**（`setup-sdk.py`）です。手動で行う場合は **方法A（ターミナル）** か **方法B（Android Studio）** のどちらか一方を行ってください。アプリ内の「導入ガイド」ページにも同じ手順をコピーボタン付きで掲載しています。

#### かんたん: 自動セットアップ（いちばんおすすめ）

`setup-sdk.py` が、次の作業をまとめて自動で行います。**画面からでもコマンドラインからでも実行できます**（中身は同じ処理です）。

1. Java 17 以降があるか確認し、無ければ自動でインストール（sdkmanager の実行に必要）
2. 最新版の Android SDK Command-line Tools のファイル名を `repository2-1.xml` から取得（方法A の手順2と同じ）
3. ZIP をダウンロードし、チェックサム（SHA-1）を確認して `~/Android/Sdk/cmdline-tools/latest/` に配置
4. `sdkmanager` で `extras;google;auto`（DHU）と `platform-tools`（adb）をインストール
5. `desktop-head-unit` に実行権限を付与し、DHU の実行に必要なライブラリ（`libc++` など）が無ければ自動でインストール
6. Linux Auto の設定（`~/.config/linux-auto/config.json`）に DHU のパスを保存し、`~/.android/headunit.ini` を書き込む（既存の値は引き継ぎます）

Python 3 の標準ライブラリだけで動作するため、`wget` や `unzip` は不要です。インストール済みの部分は省略されるため、何度実行しても問題ありません。

**画面から実行する場合**: Linux Auto の画面を開いたときに `desktop-head-unit` のパスが正しくない（ファイルが無い / 実行権限が無い）と、メイン画面が「Android SDK のセットアップが必要です」という案内に切り替わります。「全自動セットアップを実行」を押し、**約 500MB のダウンロードと Google の利用規約（Android SDK ライセンス契約）への同意**を確認するダイアログで「はい」を選ぶと実行されます。完了してパスが正しくなると、自動で通常のメイン画面に戻ります。SDK が標準の場所（`~/Android/Sdk` 等）に既にある場合は「このパスを使う」ボタンで設定だけ直せます。

導入ガイドの「自動セットアップ」からも、オプションを選んで実行できます。導入ガイドの「自動セットアップ」で、ライセンスへの同意にチェックを入れて「自動セットアップを実行」を押します。進捗はその下のログに表示され、完了すると設定画面の DHU のパスが自動で更新されます（設定画面の「自動セットアップを開く」ボタンからも移動できます）。足りないパッケージがある場合は、デスクトップにパスワード入力のダイアログ（PolicyKit / `pkexec`）が表示されるので、ログインに使うパスワードを入力してください。

**コマンドラインから実行する場合**:

```bash
cd ~/LinuxAuto
python3 setup-sdk.py --yes
```

| オプション | 内容 |
| :--- | :--- |
| `--yes`, `-y` | Android SDK のライセンスに自動で同意する（付けない場合は sdkmanager が表示するライセンスを確認して `y` を入力） |
| `--no-install-deps` | Java 17 以降や DHU に必要なライブラリ（`libc++1` / `libc++abi1` など）が足りなくても自動でインストールしない（必要なコマンドを表示するだけ） |
| `--no-platform-tools` | platform-tools（adb）をインストールしない |
| `--reinstall` | インストール済みでも Command-line Tools を最新版でダウンロードし直す |
| `--reset-ini` | `headunit.ini` を既定値で上書きする |
| `--sdk-root <パス>` | Android SDK のインストール先（既定: `$ANDROID_HOME` → `~/Android/Sdk`） |

> **足りないパッケージの自動インストールについて**: Java（`openjdk-21-jdk-headless` または `openjdk-17-jdk-headless`）や DHU に必要なライブラリ（Ubuntu の標準状態では `libc++1` / `libc++abi1` が入っていないことが多い）は、`apt` で自動インストールします。管理者権限が必要なため、次の方法で実行します。
>
> - ターミナルから実行: `sudo`（パスワードをターミナルで入力）
> - 画面から実行: パスワード不要の `sudo` が使えればそれを、使えなければ `pkexec`（デスクトップにパスワード入力のダイアログを表示）
>
> ダイアログを閉じた場合や表示できない環境では、ログに表示されるコマンド（例: `sudo apt update && sudo apt install -y libc++1 libc++abi1`）をターミナルで実行してから、もう一度実行してください。

#### 方法A: ターミナルから手動で導入（Android Studio 不要）

巨大な Android Studio を入れずに、公式のコマンドラインツール（cmdline-tools）だけでインストールする手順です。

1. **Java と解凍ツールをインストールします**（`sdkmanager` の実行に Java 17 以降が必要です）：

   ```bash
   sudo apt update && sudo apt install -y openjdk-17-jdk-headless unzip wget
   ```

2. **最新版のコマンドラインツール（Android SDK Command-line Tools）のファイル名を調べます**：

   コマンドラインツールの ZIP はバージョンごとにファイル名（`commandlinetools-linux-<ビルド番号>_latest.zip`）が変わります。最新版のファイル名は、Google が公開している SDK のパッケージ一覧 [`repository2-1.xml`](https://dl.google.com/android/repository/repository2-1.xml) から取得できます。

   ```bash
   CMDLINE_ZIP=$(wget -qO- https://dl.google.com/android/repository/repository2-1.xml \
     | sed -n '/<remotePackage path="cmdline-tools;latest">/,/<\/remotePackage>/p' \
     | grep -o 'commandlinetools-linux-[0-9]*_latest\.zip' | head -n 1)
   echo "$CMDLINE_ZIP"
   ```

   このコマンドは次の処理をしています。

   1. `repository2-1.xml` を取得する
   2. その中から、最新版を表す `<remotePackage path="cmdline-tools;latest">`（表示名「Android SDK Command-line Tools (latest)」）の部分だけを取り出す
   3. その中の Linux 用ファイル名 `commandlinetools-linux-XXXXXXXX_latest.zip` を取り出す

   `commandlinetools-linux-16111833_latest.zip` のように表示されれば成功です（数字は最新版に合わせて変わります）。何も表示されない場合は、ネットワーク接続を確認してください。

   > XML をブラウザ等で開いて手動で確認する場合は、`cmdline-tools;latest` のブロック内にある `<host-os>linux</host-os>` の `<url>` の値がファイル名です。

3. **SDK ディレクトリを作成し、コマンドラインツールをダウンロード・配置します**：

   手順2で取得したファイル名を `https://dl.google.com/android/repository/` の後ろにつなげた URL からダウンロードします（手順2と同じターミナルで続けて実行してください）。

   ```bash
   mkdir -p ~/Android/Sdk/cmdline-tools
   cd ~/Android/Sdk/cmdline-tools
   wget "https://dl.google.com/android/repository/${CMDLINE_ZIP}" -O cmdline-tools.zip
   unzip cmdline-tools.zip && mv cmdline-tools latest && rm cmdline-tools.zip
   ```

   > **注意**: 展開したフォルダは必ず `~/Android/Sdk/cmdline-tools/latest/` という構成にしてください（`mv cmdline-tools latest` の部分）。この構成になっていないと、`sdkmanager` が「Could not determine SDK root」等のエラーで動きません。

4. **DHU（`extras;google;auto`）をインストールします**：

   ```bash
   yes | ~/Android/Sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=$HOME/Android/Sdk "extras;google;auto"
   ```

   先頭の `yes |` は、ライセンスへの同意を自動で回答するためのものです。

5. **（Wi-Fi 接続の方法2 や `adb devices` を使う場合）adb（platform-tools）もインストールします**：

   ```bash
   ~/Android/Sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=$HOME/Android/Sdk "platform-tools"
   ```

   USB 接続と Wi-Fi 接続の方法1 だけなら不要ですが、トラブルシューティングで役立つため入れておくのがおすすめです。Linux Auto は SDK 内の `platform-tools` を自動で探すため、PATH の設定は不要です。

6. **実行権限を付与します**：

   ```bash
   chmod +x ~/Android/Sdk/extras/google/auto/desktop-head-unit
   ```

7. **インストールを確認します**：

   ```bash
   ls -l ~/Android/Sdk/extras/google/auto/desktop-head-unit
   ```

   ファイルが表示され、権限に `x` が含まれていれば完了です。

#### 方法B: Android Studio (GUI) から導入する場合

すでに Android Studio を使っている場合はこちらが簡単です。

1. Android Studio を起動し、スタート画面の **「More Actions」→「SDK Manager」**（プロジェクトを開いている場合は「Settings」→「Languages & Frameworks」→「Android SDK」）を開きます。
2. 上部のタブで **「SDK Tools」** を選択します。
3. 一覧の中にある **「Android Auto Desktop Head Unit emulator」** にチェックを入れます（adb を使う場合は「Android SDK Platform-Tools」も）。
4. 右下の **「Apply」** をクリックしてダウンロード・インストールを完了させます。
5. インストール後、実行権限を付与します：

   ```bash
   chmod +x ~/Android/Sdk/extras/google/auto/desktop-head-unit
   ```

#### SDK を標準以外の場所にインストールした場合

Linux Auto（設定画面の「標準パス自動探索」）は、次の場所から `extras/google/auto/desktop-head-unit` を順に探します。

1. 環境変数 `ANDROID_HOME` / `ANDROID_SDK_ROOT` が指す場所
2. `~/Android/Sdk`（Android Studio の既定）
3. `~/AndroidSdk`、`~/.android-sdk`
4. `/usr/lib/android-sdk`、`/opt/android-sdk`

これ以外の場所に入れた場合は、設定画面の「DHU 実行ファイルのパス」にフルパスを直接入力して保存してください。

#### DHU のアップデート

```bash
~/Android/Sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=$HOME/Android/Sdk --update
```

アップデート後は、念のため方法Aの手順6の `chmod +x` を再実行してください。

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
3. メイン画面の「接続先スマホ」に **スマホの IP アドレス** が表示されていることを確認

> 画面は、普段使う最低限の項目（接続先スマホ・接続モード）だけを表示します。以下に出てくる「ネットワーク状態」「手動入力」「ADB 接続ポート」「① / ② のボタン」「ペアリング」「疎通確認」「接続経路」は、Wi-Fi接続の **「詳細設定を表示」** を押すと表示されます（開閉状態はブラウザに記憶されます）。

### 方法1: ヘッドユニットサーバーへ直接接続（おすすめ・追加機材なし）

ADB を使わず、スマホのヘッドユニットサーバー（TCP 5277）へ DHU から直接接続します。
DHU 公式の `--adb=<[ホスト:]ポート>` オプション（接続先のホスト・ポートを上書き）を利用しています。

```bash
./desktop-head-unit --adb=<スマホIP>:5277
```

- つながらない場合は、画面の **「ヘッドユニットサーバーの疎通確認」** でポートに届くかを確認できます。疎通確認はヘッドユニットサーバーへの接続を1回使うため、確認後はスマホでヘッドユニットサーバーを停止→起動し直してから「接続開始」してください（同じ理由で、接続開始時の自動疎通確認は行いません）。
- DHU 起動から約20秒たってもスマホから応答（`Phone reported protocol version`）がない場合、「Waiting for phone...」で止まっていると判断して画面とログに対処方法を表示します。
- DHU から直接つながらない場合は、接続経路を **「内蔵リレー経由」** に切り替えます。`socat TCP-LISTEN:5277,fork TCP:<スマホIP>:5277` と同じ中継を Linux Auto 自身（Python 標準ライブラリ）が行うため、socat のインストールは不要です。
- 疎通確認で「接続を拒否しました」となる場合は、ヘッドユニットサーバーが起動していないか、お使いの端末・Android Auto のバージョンでは Wi-Fi 側からの接続を受け付けていない可能性があります。その場合は方法2を使ってください。

### 方法2: ADB（Wi-Fiデバッグ）＋ポートフォワーディング（開発・テスト向け）

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

### KDE Plasma でのウィンドウルール自動登録（タッチ対策）

KDE Plasma 6（Wayland）では、DHU のような X11 アプリは XWayland 経由で表示されます。Linux Auto のサービスから起動した DHU のウィンドウは「ユーザー操作で開いたウィンドウ」ではないため、KWin のフォーカス奪取防止の対象になり、**見た目はアクティブでもクリックが届かない状態**で開くことがあります（「既知の不具合」の 1）。

Linux Auto は KDE を検出すると、DHU のウィンドウ専用の **KWin ウィンドウルール** を自動で登録します。システム設定 →「ウィンドウ管理」→「ウィンドウルール」に表示されるものと同じで、次の 2 項目を「強制」します。

| 項目                   | 値   |
| :--------------------- | :--- |
| フォーカス奪取防止     | なし |
| フォーカスを受け付ける | はい |

- **対象の指定**: ウィンドウタイトルの部分一致で指定します（初回は `Desktop Head Unit`、DHU のウィンドウが開いた後は実際のタイトル `Android Auto - Desktop Head Unit`）。実機では WM_CLASS で指定すると効かなかったため、タイトルで指定しています。DHU のウィンドウのタイトルと WM_CLASS は読み取り専用で確認し（ウィンドウの移動・リサイズ・フォーカス操作は一切しません）、ログに `[KDE] DHU のウィンドウを確認: …` と表示して `~/.config/linux-auto/dhu-window.json` に保存します。
- **開いた直後の再適用**: DHU のウィンドウが開いたことを確認したら、**毎回 KWin にウィンドウルールを再読み込みさせます**（ログ: `[KDE] 開いた DHU のウィンドウに、KWin のウィンドウルールを再適用させました`）。実機では、この再読み込みが起きた接続だけ最初からタッチが反応したためです。
- **登録方法**: KDE 公式の `kwriteconfig6` / `kreadconfig6` で `~/.config/kwinrulesrc` に `linux-auto-dhu` という名前で追加し、D-Bus で KWin に再読み込みさせます。**既存の他のウィンドウルールには一切触れません。**
- **無効化**: `config.json` で `"kde_focus_rule": false` にすると、次回の接続時にこのルールを削除します。システム設定のウィンドウルール画面から手動で削除・編集しても構いません。
- KDE 以外のデスクトップ（GNOME 等）では何もしません。

### 設定の保存先

接続方式は `~/.config/linux-auto/config.json` に保存され、サービス再起動後も引き継がれます。

```jsonc
{
  "connection_type": "wifi", // "usb" | "wifi"
  "wifi_mode": "direct", // "direct" (方法1・既定) | "adb" (方法2)
  "phone_ip_auto": true, // true: テザリング親機を自動検出
  "phone_ip": "", // 手動指定時のスマホ IP
  "adb_port": 5555, // 方法2: adb connect のポート
  "hu_port": 5277, // ヘッドユニットサーバーのポート
  "direct_transport": "adb_flag", // 方法1: "adb_flag" (--adb=IP:5277) | "relay" (内蔵リレー)
  "kde_focus_rule": true, // KDE で DHU 用のウィンドウルール (フォーカス設定) を自動登録
  "stop_on_window_close": true, // DHU のウィンドウを自分で閉じた場合は自動復帰しない
}
```

---

## 自動復帰と終了の判定

DHU は「ウィンドウを自分で閉じた」場合も「通信が切れた」場合も**終了コード 0** で終わり、終了時の出力にも区別できる情報が出ないことがあります（実機ログで確認）。そこで Linux Auto は、DHU が終了した直後に**実際の接続状態を確認**して終了理由を判定します。

| 判定                   | 条件                                                                                                                              | 動作                                                                                         |
| :--------------------- | :-------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------- |
| 強制切断               | 終了コードが 0 以外（異常終了）                                                                                                   | 10 秒後に自動復帰                                                                            |
| 強制切断               | 終了直前に通信エラー（`[E]: Failed to read from transport - disconnect.` 等）が出た                                               | 10 秒後に自動復帰                                                                            |
| 強制切断               | スマホとの接続確立（`Phone reported protocol version`）前に終了した                                                               | 10 秒後に自動復帰                                                                            |
| **USB** ケーブル抜け   | スマホ（DHU のログに出るシリアル番号で識別）が `/sys/bus/usb/devices` から消えた（AOA モード解除後の再認識を最大 5 秒待って確認） | 10 秒後に自動復帰                                                                            |
| **Wi-Fi** 切断         | スマホ（テザリング親機）への経路がなくなった / 方法2 で Wi-Fi ADB の接続がなくなった                                              | 10 秒後に自動復帰                                                                            |
| **ウィンドウを閉じた** | 上記のどれにも当てはまらない（スマホは USB に接続されたまま / Wi-Fi の経路も残っている）                                          | **自動復帰せず停止**し、画面に「DHU のウィンドウが閉じられたため、接続を終了しました」と表示 |

- 判定結果はログに `[判定] …` として理由とともに表示されます。
- 判定に迷う場合（スマホの情報が取れない等）は、従来どおり**自動復帰する側**に倒します。
- スマホ側でヘッドユニットサーバーを停止した場合など、通信エラーが出ずに終わるケースは「ウィンドウを閉じた」と判定されることがあります。
- 閉じても常に自動復帰させたい場合は、`config.json` で `"stop_on_window_close": false` にします。
- 画面のログでは、DHU が起動のたびに大量に出す音声デバイスの警告（`ALSA lib …`）を 1 行の件数表示に省略しています。全文は `journalctl --user -u linux-auto` で確認できます。

## 既知の不具合 (Known Issues)

1. **Wi-Fi 接続時、DHU の画面をクリック（タッチ）しても反応しない**（KDE Plasma 6 / Kubuntu 26.04 LTS で確認）
   - **現象**: Wi-Fi 接続（方法1 / 方法2）で DHU のウィンドウが開いた直後、画面をクリックしても Android Auto が反応しない。タスクバーなど**別のものを一度触ってから DHU に戻ると**反応するようになる（ウィンドウの最大化を解除しても直る）。切断→再接続すると再発する。USB 接続では発生しない。
   - **推定原因**: DHU は XWayland 経由の X11 アプリで、Linux Auto のサービスから起動されるため、KDE（KWin）のフォーカス奪取防止の対象になり、見た目はアクティブでも入力が届かない状態で開いていると考えられる。別のものを触ってから戻ると正規のフォーカス切り替えが起きるため直る。なお、XWayland のアプリが「マウスがウィンドウに入った」通知を受け取らないとクリックを無視する問題も KDE で報告されており、そちらが原因の可能性も残る（DHU は非公開のバイナリのため未確定）。
   - **対策状況**: KDE のウィンドウルールで DHU のウィンドウだけ「フォーカス奪取防止: なし / フォーカスを受け付ける: はい」を自動設定し、さらに DHU のウィンドウが開いた直後に毎回 KWin にルールを再適用させる対策を実装したが、**実機では改善せず、未解決（調査保留中）**（対策の内容は下記「KDE Plasma でのウィンドウルール自動登録」）。
     - 検証の経緯: ウィンドウルールを WM_CLASS で指定していた版では、「ウィンドウが開いた直後にルールを書き換えて KWin を再読み込みした接続」だけ最初からタッチが反応し、再読み込みが起きない 2 回目以降は反応しなかった。このため現在はタイトルで指定し、開いた直後の再読み込みを毎回行っている。
     - 以前試した「接続後にウィンドウを最大化し直す」補正は効果がなかったため削除済み。
   - **回避策**: DHU のウィンドウが開いたら、タスクバーなど別のものを一度クリックしてから DHU の画面に戻ってください。

2. **DHU の画面でダブルタップが認識されず、ピンチイン / ピンチアウトもできない**
   - **現象**: DHU 上の Google マップ等で、ダブルタップによるズームが反応せず、タッチパネルでの 2 本指のピンチイン / ピンチアウトもできない。OS 側のタッチパネルは正常で、Linux 上の Chrome で開いた Google マップではピンチ操作ができる。
   - **推定原因**:
     - **ピンチ**: DHU はタッチパネルの入力を直接受け取らず、**マウスのクリックをタッチとして扱う**仕様（公式ドキュメント: "The DHU emulates touch with the mouse"）。DHU は XWayland 経由で動作するため、タッチパネルの操作は 1 本のマウス操作に変換されて届き、2 本指の情報が失われる。Chrome はタッチパネルを Wayland で直接扱うためピンチが効く。Linux Auto 側の不具合ではなく DHU の仕様による制約。
     - **ダブルタップ**: 原因未特定。DHU の公式ドキュメントにダブルタップの記載はなく、コンソールコマンドも単発のタップ（`tap x y`）のみ。タッチ→マウス変換（XWayland / KDE）の問題か、DHU / Android Auto 側の問題か、Wi-Fi の遅延で 2 回のタップの間隔が崩れているかは未切り分け。
   - **切り分け方法**: (1) マウスの右クリックによるマルチタッチエミュレーション（下記の回避策）でズームできるか、(2) **マウス**のダブルクリックでズームできるかを確認する。マウスでは効きタッチパネルでは効かない場合はタッチ→マウス変換の問題、マウスでも効かない場合は DHU / Android Auto 側の問題。
   - **回避策（ピンチ）**: DHU 標準のマルチタッチエミュレーションを使う。1 本目の指の位置で**右クリック**し、2 本目の指の位置で**右ボタンを押したまま**マウスを動かすと、2 本指の中心を固定したままピンチイン / アウト・回転ができる。
   - **対策案（未着手）**: タッチパネルの 2 本指の動きを Linux Auto が直接読み取り（`/dev/input`）、上記の右クリック方式の操作に変換して DHU に送り込む「タッチブリッジ」。ただし `/dev/input` を読むためにユーザーを `input` グループに入れる必要がある（キー入力も読める権限のためセキュリティ面の判断が必要）こと、XWayland 上の DHU への入力注入が KDE Plasma 6 で可能かが未検証であること、元のタッチ入力との競合を避ける調整が必要なことが課題。

## PWA (Progressive Web App) 対応

Google Chrome, Chromium, Microsoft Edge などで `http://127.0.0.1:8855` を開くと、アドレスバー右端またはサイドバーの「アプリ化」ボタンから **PWAアプリとしてインストール** できます。

- アドレスバーやタブのない独立したネイティブアプリ風ウィンドウで起動します。
- 車載タッチスクリーンや全画面表示に最適です。

---

## 画面構成と機能

### 1. メインページ (Main)

- **Android SDK（DHU）の確認**: 画面を開いたとき（メイン画面に戻ったとき・設定を保存したときも）に `desktop-head-unit` のパスを確認し、正しくなければメイン画面を「Android SDK のセットアップが必要です」の案内に差し替えます。案内からは、確認ダイアログ（約 500MB のダウンロード + Google の利用規約への同意）で「はい」を選ぶと全自動セットアップを実行できます。
- **接続方式の切り替え**: 「USB接続」「Wi-Fi接続」のタブで切り替えます。Wi-Fi 接続では以下を操作できます（接続中は変更不可）。
  - **基本表示**: 接続先スマホの IP（自動検出 / 手動入力の結果）と、接続モード（方法1: 直接接続〈既定〉 / 方法2: ADB 経由）の選択のみ
  - **詳細設定**（「詳細設定を表示」ボタンで開閉）:
    - **ネットワーク状態**: 接続中の Wi-Fi（SSID）、インターフェース、この PC の IP、スマホの IP（ゲートウェイ）
    - **接続先スマホの IP**: 自動（テザリング親機を検出）/ 手動入力
    - **方法1**: ヘッドユニットサーバーのポート、接続経路（DHU から直接 / 内蔵リレー経由）、疎通確認
    - **方法2**: ADB 接続ポート、「USB経由で TCP/IP モードを有効化」「Wi-Fi で接続テスト」、ワイヤレスデバッグのペアリング、adb 端末一覧
- **接続開始 (DHU起動)**: 選択中の接続方式で DHU を起動します。
- **切断 / 停止**: 接続を終了します。
- **ステータスリング & インジケーター**: 現在の接続状態（待機中 / 実行中 / 再接続待機中 / エラー）を視覚的に表示。
- **10秒自動復帰プログレスバー**: USB抜け・Wi-Fi切断等で不意にプロセスが終了した際、10秒間のカウントダウンを表示しながらケーブル再挿入を待機します。
- **リアルタイムログ**: DHUプロセスの標準出力・エラー出力をリアルタイムに確認できます。

### 2. 設定ページ (Settings)

- **DHU 実行ファイルのパス**: `desktop-head-unit` のフルパスを設定可能。「標準パス自動探索」ボタンで典型的なパスを自動検出します。未インストールの場合は「自動セットアップを開く」ボタンから導入ガイドの自動セットアップへ移動できます。
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

- **自動セットアップ**: ボタン 1 つで `setup-sdk.py` を実行し、Android SDK / DHU のインストール、DHU のパスの保存、`headunit.ini` の書き込みまでを行います。進捗をリアルタイムのログで表示し、途中で中止もできます。
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
├── setup-sdk.py                # Android SDK / DHU 自動セットアップ (画面・コマンドライン共通)
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
   - 導入ガイドの「自動セットアップ」（または `python3 setup-sdk.py --yes`）を実行すると、インストールとパスの設定をまとめて行えます。
   - Android Studio の SDK Manager で `Extras` → `Android Auto Desktop Head Unit emulator` にチェックが入っているか確認してください。
   - パスは正しいのに DHU が起動しない（ログに `libc++.so.1: cannot open shared object file` 等）場合は、`sudo apt install -y libc++1 libc++abi1` を実行してください。
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
   - Linux 端末がスマホのテザリングに Wi-Fi で接続されているか確認してください（画面の「詳細設定を表示」→「ネットワーク状態」→「再取得」）。
   - 有線 LAN など他の経路が優先されている場合は、それを外すか「手動入力」でスマホの IP を指定してください。
7. **DHU が「Waiting for phone...」のまま進まない場合（ログに `connected.` は出ている）**:
   - スマホのロックを解除し、Android Auto の確認画面が出ていれば許可してください。
   - スマホでヘッドユニットサーバーを一度停止→起動し直してから、もう一度「接続開始」してください。
   - 方法1 で改善しない場合は、方法2（ADB）を使用してください。方法2 はスマホ側から見て公式の ADB トンネル経由（localhost）の接続になります。
   - ログに大量に出る `ALSA lib ... Unknown PCM ...` は音声デバイス設定の警告で、接続の成否とは無関係です。
   - **Wi-Fi 接続でタッチ（クリック）が反応しない場合**: 「既知の不具合」の 1 を参照してください。ログの `[KDE]` の行に、ウィンドウルールの登録状況と DHU のウィンドウ情報（タイトル / WM_CLASS）が表示されます。
8. **方法1 の疎通確認で「接続を拒否しました」「タイムアウト」と出る場合**:
   - スマホで「ヘッドユニットサーバーを起動」しているか（通知が出ているか）確認してください。
   - 改善しない場合は、端末側が Wi-Fi からの接続を受け付けていない可能性があるため、方法2（ADB）を使用してください。
9. **方法2 で「adb connect に失敗しました」と出る場合**:
   - スマホを USB 接続して「① USB経由で TCP/IP モードを有効化」を実行したか確認してください（スマホ再起動後は再実行が必要）。
   - スマホの画面に「USB デバッグを許可しますか？」が出ていたら「許可」をタップしてください。
10. **コードを更新したのに動作が変わらない場合**:

- サービスは更新前のコードで動き続けています。`systemctl --user restart linux-auto` で再起動してください。

---

## ライセンス

GPL License
Copyright (c) 2026 エノキ電気 ENOKI ELECTRONICS
