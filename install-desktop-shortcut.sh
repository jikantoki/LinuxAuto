#!/usr/bin/env bash

# =============================================================================
# Linux Auto - デスクトップショートカット登録スクリプト
#
# 登録されるアイコンは「画面 (WebUI) を開くだけ」のランチャーです (open-ui.sh)。
# サーバー本体は install-service.sh でサービスとして常駐させてください。
# (サービス未登録でもアイコンから使えますが、その場合はサーバーを一時起動します)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$HOME/Desktop"
ICON_PATH="$SCRIPT_DIR/static/icon.svg"

echo "[設定] Linux Auto のショートカットをシステムに登録します..."

# 実行権限の付与
chmod +x "$SCRIPT_DIR/start.sh"
chmod +x "$SCRIPT_DIR/connect.sh"
chmod +x "$SCRIPT_DIR/app.py"
chmod +x "$SCRIPT_DIR/open-ui.sh"

mkdir -p "$APPS_DIR"

# アプリケーションメニュー登録用のデスクトップエントリを作成
DESKTOP_ENTRY_FILE="$APPS_DIR/linux-auto.desktop"

cat <<EOF > "$DESKTOP_ENTRY_FILE"
[Desktop Entry]
Version=1.0
Type=Application
Name=Linux Auto
GenericName=Android Auto Headunit Support
Comment=Google DHU を使用した Android Auto 接続 GUI ツール
Exec="$SCRIPT_DIR/open-ui.sh"
Path=$SCRIPT_DIR
Icon=$ICON_PATH
Terminal=false
Categories=Utility;AudioVideo;
StartupNotify=true
EOF

chmod +x "$DESKTOP_ENTRY_FILE"

# デスクトップフォルダが存在する場合はデスクトップにもコピー
if [ -d "$DESKTOP_DIR" ]; then
    cp "$DESKTOP_ENTRY_FILE" "$DESKTOP_DIR/linux-auto.desktop"
    chmod +x "$DESKTOP_DIR/linux-auto.desktop"
    # GNOME (Ubuntu) ではデスクトップ上のランチャーを「信頼済み」にしないと起動できないため設定
    if command -v gio >/dev/null 2>&1; then
        gio set "$DESKTOP_DIR/linux-auto.desktop" metadata::trusted true 2>/dev/null || true
    fi
    echo "[完了] デスクトップにショートカットを配置しました。"
fi

echo "[完了] アプリケーションメニューに 'Linux Auto' が登録されました！"
echo "アイコンをクリックすると Linux Auto の画面が開きます (サーバーは起動済みのものを利用します)。"
if ! systemctl --user is-enabled --quiet linux-auto.service 2>/dev/null; then
    echo ""
    echo "[ヒント] サーバーがまだサービス登録されていません。PC起動時に自動で常駐させるには:"
    echo "  ./install-service.sh"
fi
