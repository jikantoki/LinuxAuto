#!/usr/bin/env bash

# =============================================================================
# Linux Auto - コマンドライン直接接続ツール (connect.sh)
# 開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
# GitHub: https://github.com/jikantoki/LinuxAuto
#
# 【概要】
# GUI経由ではなく、ターミナルから直接 desktop-head-unit --usb を実行する暫定CLIツールです。
# 端末環境（完全なTTY・オーディオ・環境変数）で動作するため、GUIショートカットで
# 発生する即時切断問題を回避し、確実に Android Auto 接続を行うことができます。
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "  Linux Auto - CLI Direct Connect Tool"
echo "  開発者: エノキ電気 ENOKI ELECTRONICS"
echo "=========================================================="

# 1. DHU 実行バイナリの探索
CONFIG_FILE="$HOME/.config/linux-auto/config.json"
DHU_PATH=""

if [ -f "$CONFIG_FILE" ]; then
    # jq が入っていなくても Python 経由で config.json から dhu_path を取得
    DHU_PATH=$(python3 -c "import json, sys; conf=json.load(open('$CONFIG_FILE')); print(conf.get('dhu_path', ''))" 2>/dev/null || true)
fi

# 設定ファイルにない場合は標準パスを探索
if [ -z "$DHU_PATH" ] || [ ! -x "$DHU_PATH" ]; then
    CANDIDATES=(
        "$HOME/Android/Sdk/extras/google/auto/desktop-head-unit"
        "$HOME/AndroidSdk/extras/google/auto/desktop-head-unit"
        "$HOME/.android-sdk/extras/google/auto/desktop-head-unit"
        "/usr/lib/android-sdk/extras/google/auto/desktop-head-unit"
    )
    for c in "${CANDIDATES[@]}"; do
        if [ -x "$c" ]; then
            DHU_PATH="$c"
            break
        fi
    done
fi

if [ -z "$DHU_PATH" ] || [ ! -x "$DHU_PATH" ]; then
    echo "[エラー] desktop-head-unit 実行ファイルが見つかりません。"
    echo "Linux Auto の WebUI (設定画面) でパスを設定するか、Android SDK を確認してください。"
    exit 1
fi

echo "[情報] 使用する DHU パス: $DHU_PATH"
echo "[情報] 設定ファイル: ~/.android/headunit.ini"
echo "[情報] 停止するには Ctrl+C を押してください。"
echo "----------------------------------------------------------"

# DHU の親ディレクトリに移動して実行
DHU_DIR="$(dirname "$DHU_PATH")"
cd "$DHU_DIR"

# 2. 自動再接続ループ（Ctrl+C で安全に終了）
trap 'echo -e "\n[停止] 終了シグナルを受信しました。終了します。"; exit 0' SIGINT SIGTERM

while true; do
    echo "[起動] $(date +%H:%M:%S) desktop-head-unit --usb を実行します..."
    
    # ターミナル直結でフォアグラウンド実行（TTYが完全に維持されるため即時終了しません）
    set +e
    "$DHU_PATH" --usb
    EXIT_CODE=$?
    set -e

    echo "[終了] $(date +%H:%M:%S) DHU が終了しました (終了コード: $EXIT_CODE)"
    echo "[待機] USB切断の可能性があるため、10秒後に自動再試行します..."
    echo "[ヒント] 終了するには Ctrl+C を押してください。"

    for i in {10..1}; do
        echo -ne "再接続まで: $i 秒 \r"
        sleep 1
    done
    echo ""
done
