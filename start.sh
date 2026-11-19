#!/usr/bin/env bash

# =============================================================================
# Linux Auto - 起動スクリプト
# 開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
# GitHub: https://github.com/jikantoki
# =============================================================================

set -e

# スクリプト自身のディレクトリを取得
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "  Linux Auto - Android Auto Headunit Support"
echo "  開発者: エノキ電気 ENOKI ELECTRONICS"
echo "=========================================================="

# 1. Python3 の存在チェック (Ubuntu/Kubuntuには標準搭載)
if ! command -v python3 >/dev/null 2>&1; then
    echo "[エラー] python3 が見つかりません。以下のコマンドでインストールしてください:"
    echo "  sudo apt update && sudo apt install -y python3"
    exit 1
fi

echo "[起動] Linux Auto サーバーを起動しています..."
if [[ "$*" != *"--no-browser"* ]] && [[ "$*" != *"-n"* ]]; then
    echo "[情報] ブラウザが自動的に開きます (http://127.0.0.1:8855)"
else
    echo "[情報] 自動起動モード (--no-browser): ブラウザの自動起動をスキップします"
fi
echo "[ヒント] 停止するには、この端末で Ctrl+C を押してください。"
echo "----------------------------------------------------------"

# 2. 外部依存なしのPythonサーバーを直接実行（渡された引数をそのまま引き継ぎます）
exec python3 "$SCRIPT_DIR/app.py" "$@"
