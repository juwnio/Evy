#!/bin/bash
# Install the `evy` command so Evy can be launched from any directory.
#
# Symlinks scripts/evy into a directory on your PATH (default: ~/.local/bin).
set -e

REPO="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO/scripts/evy"
TARGET_DIR="${EVY_BIN_DIR:-$HOME/.local/bin}"
TARGET="$TARGET_DIR/evy"

if [ ! -f "$SRC" ]; then
    echo "Could not find $SRC" >&2
    exit 1
fi

chmod +x "$SRC"
mkdir -p "$TARGET_DIR"
ln -sf "$SRC" "$TARGET"

echo "Installed: $TARGET -> $SRC"

case ":$PATH:" in
    *":$TARGET_DIR:"*)
        echo "You can now run: evy"
        ;;
    *)
        echo
        echo "$TARGET_DIR is not on your PATH. Add this to your shell profile"
        echo "(~/.zshrc, ~/.bashrc, etc.), then restart your terminal:"
        echo
        echo "    export PATH=\"$TARGET_DIR:\$PATH\""
        ;;
esac
