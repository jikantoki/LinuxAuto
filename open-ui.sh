#!/usr/bin/env bash

# =============================================================================
# Linux Auto - 画面 (WebUI) を開くだけのランチャー (open-ui.sh)
# 開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
# GitHub: https://github.com/jikantoki
#
# 【役割】
# デスクトップアイコン / アプリメニューから呼ばれるスクリプトです。
# サーバー本体はサービス (systemd ユーザーサービス) として常駐している前提で、
# このスクリプトは「画面を開く」ことだけを行います。
#
#   1. サーバーが応答していれば、そのままブラウザで画面を開く
#   2. 応答がなければ、linux-auto.service を起動してから画面を開く
#   3. サービス未登録の場合のみ、バックグラウンドでサーバーを一時起動する
#
# アイコンを閉じても (ブラウザを閉じても) サーバーと Android Auto 接続は止まりません。
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${LINUX_AUTO_PORT:-8855}"
URL="http://127.0.0.1:${PORT}"
SERVICE_NAME="linux-auto.service"
LOG_DIR="$HOME/.cache/linux-auto"

# デスクトップ通知 (notify-send があれば) + 標準出力
notify() {
    echo "[Linux Auto] $1"
    if command -v notify-send >/dev/null 2>&1; then
        notify-send -a "Linux Auto" -i "$SCRIPT_DIR/static/icon.svg" "Linux Auto" "$1" >/dev/null 2>&1 || true
    fi
}

# サーバーが応答しているか確認 (curl が無い環境でも動くよう python3 標準ライブラリで確認)
server_is_up() {
    python3 - "$URL/api/status" <<'EOF' >/dev/null 2>&1
import sys, urllib.request
urllib.request.urlopen(sys.argv[1], timeout=1)
EOF
}

# サーバーが立ち上がるまで最大 N 秒待機
wait_for_server() {
    local limit="$1"
    local i=0
    while [ "$i" -lt "$((limit * 4))" ]; do
        server_is_up && return 0
        sleep 0.25
        i=$((i + 1))
    done
    return 1
}

if ! server_is_up; then
    if systemctl --user cat "$SERVICE_NAME" >/dev/null 2>&1; then
        # サービス登録済み: サービスを起動 (停止していた場合の復旧)
        echo "[Linux Auto] サーバーが停止しているため $SERVICE_NAME を起動します..."
        systemctl --user start "$SERVICE_NAME" || true
    else
        # サービス未登録: その場限りでバックグラウンド起動
        echo "[Linux Auto] サービス未登録のため、サーバーを一時的にバックグラウンド起動します..."
        mkdir -p "$LOG_DIR"
        nohup python3 "$SCRIPT_DIR/app.py" --no-browser --port "$PORT" \
            </dev/null >>"$LOG_DIR/server.log" 2>&1 &
        disown || true
    fi

    if ! wait_for_server 15; then
        notify "サーバーを起動できませんでした。'systemctl --user status $SERVICE_NAME' または $LOG_DIR/server.log を確認してください。"
        exit 1
    fi
fi

# 画面を開く (xdg-open → Python webbrowser の順で試行)
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 &
else
    python3 -m webbrowser "$URL" >/dev/null 2>&1 &
fi

exit 0
