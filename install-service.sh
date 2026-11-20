#!/usr/bin/env bash

# =============================================================================
# Linux Auto - サービス登録スクリプト (install-service.sh)
# 開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
# GitHub: https://github.com/jikantoki/LinuxAuto
#
# Linux Auto のサーバー (app.py) を systemd の「ユーザーサービス」として登録し、
# PC 起動 (ログイン) 時に自動でバックグラウンド起動させます。
#
# 【なぜシステムサービスではなくユーザーサービスなのか】
# DHU (Android Auto の画面) はログイン中ユーザーのデスクトップに
# ウィンドウを表示し、音声もユーザーのサウンドサーバーへ出力します。
# root で動くシステムサービスからはそれらにアクセスできないため、
# ユーザー単位の systemd サービス (~/.config/systemd/user/) として登録します。
#
# 使い方:
#   ./install-service.sh              サービスを登録して今すぐ起動 (ログイン時に自動起動)
#   ./install-service.sh --boot       上記 + PC の電源投入時 (ログイン前) からサーバーを起動
#   ./install-service.sh --uninstall  サービスを停止して登録を解除
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="linux-auto.service"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_FILE="$UNIT_DIR/$SERVICE_NAME"
OLD_AUTOSTART="$HOME/.config/autostart/linux-auto.desktop"
PORT=8855

MODE="install"
for arg in "$@"; do
    case "$arg" in
        --uninstall|-u) MODE="uninstall" ;;
        --boot|-b)      ENABLE_LINGER=1 ;;
        --help|-h)
            sed -n '17,20p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *)
            echo "[エラー] 不明なオプション: $arg  (--help で使い方を表示)"
            exit 1 ;;
    esac
done

if ! command -v systemctl >/dev/null 2>&1; then
    echo "[エラー] systemctl が見つかりません。systemd 環境 (Ubuntu / Kubuntu 等) で実行してください。"
    exit 1
fi

# -----------------------------------------------------------------------------
# アンインストール
# -----------------------------------------------------------------------------
if [ "$MODE" = "uninstall" ]; then
    echo "[解除] $SERVICE_NAME を停止・無効化します..."
    systemctl --user disable --now "$SERVICE_NAME" 2>/dev/null || true
    if [ -f "$UNIT_FILE" ]; then
        mv "$UNIT_FILE" "$UNIT_FILE.removed"
        echo "[解除] ユニットファイルを $UNIT_FILE.removed に退避しました (不要なら削除してください)。"
    fi
    systemctl --user daemon-reload
    echo "[完了] サービスの登録を解除しました。"
    echo "       ログイン前起動 (--boot) を元に戻す場合: loginctl disable-linger $USER"
    exit 0
fi

# -----------------------------------------------------------------------------
# インストール
# -----------------------------------------------------------------------------
PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "[エラー] python3 が見つかりません: sudo apt install -y python3"
    exit 1
fi

chmod +x "$SCRIPT_DIR/app.py" "$SCRIPT_DIR/start.sh" "$SCRIPT_DIR/open-ui.sh" 2>/dev/null || true
mkdir -p "$UNIT_DIR"

echo "[設定] $UNIT_FILE を作成します..."
cat <<EOF > "$UNIT_FILE"
[Unit]
Description=Linux Auto - Android Auto Headunit Support (WebUI server)
Documentation=https://github.com/jikantoki/LinuxAuto

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart="$PYTHON_BIN" "$SCRIPT_DIR/app.py" --no-browser
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=5
TimeoutStopSec=15

[Install]
WantedBy=default.target
EOF

# 旧方式 (~/.config/autostart) の自動起動が残っていると二重起動になるため無効化
if [ -f "$OLD_AUTOSTART" ]; then
    mv "$OLD_AUTOSTART" "$OLD_AUTOSTART.disabled"
    echo "[移行] 旧方式の自動起動設定を無効化しました: $OLD_AUTOSTART.disabled"
fi

# 手動起動 (./start.sh) のサーバーが動いているとサービスがポートを取れないため確認
if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/api/status', timeout=1)" >/dev/null 2>&1 \
   && ! systemctl --user is-active --quiet "$SERVICE_NAME"; then
    echo ""
    echo "[注意] すでに手動起動の Linux Auto サーバーがポート $PORT で動いています。"
    echo "       そのターミナルで Ctrl+C を押して終了してから、次を実行してください:"
    echo "         systemctl --user restart $SERVICE_NAME"
    echo ""
fi

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user restart "$SERVICE_NAME"

if [ "${ENABLE_LINGER:-0}" = "1" ]; then
    echo "[設定] ログイン前からサーバーを起動するため linger を有効化します (sudo パスワードを求められる場合があります)..."
    loginctl enable-linger "$USER" || sudo loginctl enable-linger "$USER"
fi

sleep 1
echo ""
systemctl --user --no-pager --lines=5 status "$SERVICE_NAME" || true
echo ""
echo "[完了] Linux Auto をサービスとして登録しました。"
echo "  - 次回から PC にログインすると、サーバーが自動でバックグラウンド起動します。"
echo "  - 画面を開く : デスクトップの「Linux Auto」アイコン、または ./open-ui.sh"
echo "  - 状態確認   : systemctl --user status $SERVICE_NAME"
echo "  - ログ確認   : journalctl --user -u $SERVICE_NAME -f"
echo "  - 再起動     : systemctl --user restart $SERVICE_NAME"
echo "  - 登録解除   : ./install-service.sh --uninstall"
