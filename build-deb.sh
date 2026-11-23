#!/usr/bin/env bash

# =============================================================================
# Linux Auto - deb パッケージ作成スクリプト (build-deb.sh)
# 開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
# GitHub: https://github.com/jikantoki/LinuxAuto
#
# 使い方:
#   ./build-deb.sh            バージョンは static/index.html の「Version x.y.z」から自動取得
#   ./build-deb.sh 1.1.0      バージョンを指定して作成
#
# 出力: dist/linux-auto.deb (ファイル名は毎回同じ。バージョンはパッケージ情報に入る)
#       中のバージョンの確認: dpkg-deb -f dist/linux-auto.deb Version
# 必要なもの: dpkg-deb (Ubuntu / Debian 系なら標準で入っています)
#
# パッケージの中身 (インストール先):
#   /usr/lib/linux-auto/                 app.py, setup-sdk.py, linux-auto-window.py, connect.sh, static/
#   /usr/bin/linux-auto                  画面を専用ウィンドウで開く (アプリメニューの起動先)
#   /usr/bin/linux-auto-setup-sdk        Android SDK / DHU の自動セットアップ
#   /usr/lib/systemd/user/linux-auto.service   サーバーのユーザーサービス
#   /usr/share/applications/linux-auto.desktop アプリメニューのアイコン
#   /usr/share/icons/hicolor/scalable/apps/linux-auto.svg
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PKG_NAME="linux-auto"
PKG_SRC="$SCRIPT_DIR/packaging/deb"
OUT_DIR="$SCRIPT_DIR/dist"

if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "[エラー] dpkg-deb が見つかりません。Ubuntu / Debian 系の環境で実行してください。"
    exit 1
fi

# -----------------------------------------------------------------------------
# バージョンとメンテナー
# -----------------------------------------------------------------------------
VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    VERSION="$(tr -d '\r' < static/index.html | grep -oE 'Version [0-9]+(\.[0-9]+)+' | head -n 1 | awk '{print $2}' || true)"
fi
if ! [[ "$VERSION" =~ ^[0-9][0-9A-Za-z.+~-]*$ ]]; then
    echo "[エラー] バージョンを判定できませんでした。./build-deb.sh 1.0.0 のように指定してください。"
    exit 1
fi

# メンテナー: 環境変数 DEB_MAINTAINER → git の user.name / user.email → 既定値
MAINTAINER="${DEB_MAINTAINER:-}"
if [ -z "$MAINTAINER" ] && command -v git >/dev/null 2>&1; then
    GIT_NAME="$(git config user.name 2>/dev/null || true)"
    GIT_EMAIL="$(git config user.email 2>/dev/null || true)"
    if [ -n "$GIT_NAME" ] && [ -n "$GIT_EMAIL" ]; then
        MAINTAINER="$GIT_NAME <$GIT_EMAIL>"
    fi
fi
MAINTAINER="${MAINTAINER:-ENOKI ELECTRONICS <jikantoki@users.noreply.github.com>}"

echo "[作成] $PKG_NAME $VERSION の deb パッケージを作成します..."

# -----------------------------------------------------------------------------
# 作業フォルダ (Linux のファイルシステム上で組み立てる: 権限を正しく付けるため)
# -----------------------------------------------------------------------------
umask 022
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
ROOT="$WORK_DIR/${PKG_NAME}_${VERSION}_all"
LIB_DIR="$ROOT/usr/lib/linux-auto"

# テキストファイルは改行コードを LF に統一して配置する
# (Windows で git clone すると CRLF になり、シェルスクリプトや shebang が動かなくなるため)
install_file() {
    local src="$1" dest="$2" mode="$3"
    mkdir -p "$(dirname "$dest")"
    case "$src" in
        *.py|*.sh|*.html|*.css|*.js|*.json|*.svg|*.md|*.txt|*.service|*.desktop|\
        */control|*/postinst|*/prerm|*/postrm|*/copyright|*/linux-auto|*/linux-auto-setup-sdk)
            sed 's/\r$//' "$src" > "$dest" ;;
        *)
            cp "$src" "$dest" ;;
    esac
    chmod "$mode" "$dest"
}

# --- アプリ本体 ---
install_file app.py                "$LIB_DIR/app.py"                755
install_file setup-sdk.py          "$LIB_DIR/setup-sdk.py"          755
install_file linux-auto-window.py  "$LIB_DIR/linux-auto-window.py"  755
install_file connect.sh            "$LIB_DIR/connect.sh"            755

while IFS= read -r -d '' file; do
    install_file "$file" "$LIB_DIR/$file" 644
done < <(find static -type f ! -name '*.pyc' -print0)

# --- コマンド・サービス・メニュー・アイコン ---
install_file "$PKG_SRC/linux-auto"           "$ROOT/usr/bin/linux-auto"                               755
install_file "$PKG_SRC/linux-auto-setup-sdk" "$ROOT/usr/bin/linux-auto-setup-sdk"                     755
install_file "$PKG_SRC/linux-auto.service"   "$ROOT/usr/lib/systemd/user/linux-auto.service"          644
install_file "$PKG_SRC/linux-auto.desktop"   "$ROOT/usr/share/applications/linux-auto.desktop"        644
install_file static/icon.svg                 "$ROOT/usr/share/icons/hicolor/scalable/apps/linux-auto.svg" 644
install_file "$PKG_SRC/copyright"            "$ROOT/usr/share/doc/linux-auto/copyright"               644
install_file README.md                       "$ROOT/usr/share/doc/linux-auto/README.md"               644

# --- パッケージ情報 (DEBIAN/) ---
mkdir -p "$ROOT/DEBIAN"
for script in postinst prerm postrm; do
    install_file "$PKG_SRC/$script" "$ROOT/DEBIAN/$script" 755
done
INSTALLED_SIZE="$(du -sk "$ROOT/usr" | cut -f1)"
sed -e 's/\r$//' \
    -e "s|@VERSION@|$VERSION|" \
    -e "s|@MAINTAINER@|$MAINTAINER|" \
    -e "s|@INSTALLED_SIZE@|$INSTALLED_SIZE|" \
    "$PKG_SRC/control" > "$ROOT/DEBIAN/control"
chmod 644 "$ROOT/DEBIAN/control"

# ディレクトリの権限をそろえる
find "$ROOT" -type d -exec chmod 755 {} +

# -----------------------------------------------------------------------------
# パッケージ化 (所有者は root、圧縮は互換性の高い xz)
# -----------------------------------------------------------------------------
mkdir -p "$OUT_DIR"
# ファイル名にバージョンを含めず、毎回同じファイルを上書きする (配布リンクや手順を固定できる)
DEB_FILE="$OUT_DIR/${PKG_NAME}.deb"
dpkg-deb --root-owner-group -Zxz --build "$ROOT" "$DEB_FILE" >/dev/null

echo "[完了] $DEB_FILE (バージョン $VERSION)"
echo ""
echo "  インストール / 更新:  sudo apt install \"$DEB_FILE\""
echo "  中身の確認        :  dpkg-deb --contents \"$DEB_FILE\""
