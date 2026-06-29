#!/bin/bash
# Emoji Remover Z - Build Script (Linux / macOS)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "===================================================="
echo "  Emoji Remover Z - Build Script"
echo "===================================================="
echo

# Prefer python3.14, fall back to python3.12, then python3
if command -v python3.14 &>/dev/null; then
    PY=python3.14
elif command -v python3.12 &>/dev/null; then
    PY=python3.12
elif command -v python3 &>/dev/null; then
    PY=python3
else
    echo "ERROR: Python 3 not found. Install it from https://python.org"
    exit 1
fi

echo "[1/5] Using $($PY --version)"
echo

echo "[2/5] Creating virtual environment and installing dependencies..."
$PY -m venv .venv
source .venv/bin/activate
pip install --quiet Pillow pyinstaller

echo "[3/5] Generating icon..."
python "$SCRIPT_DIR/emoji-remover-z.py" --generate-icon --png-only

if [[ ! -f "$SCRIPT_DIR/emoji_remover_z.png" ]]; then
    echo "ERROR: Icon file was not created."
    deactivate
    rm -rf .venv
    exit 1
fi
echo "  Icon generated: emoji_remover_z.png"
echo

echo "[4/5] Building executable..."

# Wipe any previous build/spec cache so PyInstaller can never reuse a
# stale .spec file that points at a since-deleted or relocated icon path.
rm -rf build

python -m PyInstaller --onefile --windowed --name "Emoji_Remover_Z" \
    --icon "$SCRIPT_DIR/emoji_remover_z.png" \
    --distpath . --workpath build --specpath build \
    --noconfirm \
    "emoji-remover-z.py"

deactivate

echo
echo "Cleaning up build files..."
rm -rf build .venv

# Copy icon for Linux app menu before deleting the source PNG
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    ICON_HICOLOR="$HOME/.local/share/icons/hicolor/256x256/apps"
    mkdir -p "$ICON_HICOLOR"
    cp "$SCRIPT_DIR/emoji_remover_z.png" "$ICON_HICOLOR/emoji-remover-z.png"
fi
rm -f "$SCRIPT_DIR/emoji_remover_z.png"

echo
echo "[5/5] Installing shortcuts and app entry..."
echo

# ── Linux only ──────────────────────────────────────────────────────────────
if [[ "$OSTYPE" == "linux-gnu"* ]]; then

    ICON_DIR="$ICON_HICOLOR"
    DESKTOP_DIR="$HOME/.local/share/applications"
    DESKTOP_SHORTCUT="$HOME/Desktop/emoji-remover-z.desktop"
    mkdir -p "$DESKTOP_DIR" "$HOME/Desktop"

    # Write .desktop file for app menu
    cat > "$DESKTOP_DIR/emoji-remover-z.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Emoji Remover Z
GenericName=Filename Cleaner
Comment=Remove emojis and styled text from filenames and folders
Exec=$SCRIPT_DIR/Emoji_Remover_Z
Icon=emoji-remover-z
Terminal=false
Categories=Utility;FileTools;
Keywords=emoji;rename;filename;unicode;cleaner;
StartupNotify=true
StartupWMClass=Emoji_Remover_Z
EOF

    chmod +x "$DESKTOP_DIR/emoji-remover-z.desktop"

    # Write Desktop shortcut directly (not a copy — independent file)
    cat > "$DESKTOP_SHORTCUT" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Emoji Remover Z
GenericName=Filename Cleaner
Comment=Remove emojis and styled text from filenames and folders
Exec=$SCRIPT_DIR/Emoji_Remover_Z
Icon=emoji-remover-z
Terminal=false
Categories=Utility;FileTools;
Keywords=emoji;rename;filename;unicode;cleaner;
StartupNotify=true
StartupWMClass=Emoji_Remover_Z
EOF

    chmod +x "$DESKTOP_SHORTCUT"

    # Mark trusted so GNOME/Nautilus shows it as a launcher, not a text file.
    # gio set with a quoted "true" string is required on GNOME 40+; bare `true`
    # is silently ignored. If gio is unavailable, fall back to setfattr.
    if command -v gio &>/dev/null; then
        gio set "$DESKTOP_SHORTCUT" metadata::trusted "true" 2>/dev/null || true
    elif command -v setfattr &>/dev/null; then
        setfattr -n "user.xdg.origin.url" -v "" "$DESKTOP_SHORTCUT" 2>/dev/null || true
    fi

    # Refresh caches (best-effort)
    if command -v gtk-update-icon-cache &>/dev/null; then
        gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    fi
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    fi

    # Try to pin to GNOME sidebar
    if command -v gsettings &>/dev/null; then
        CURRENT_FAVORITES=$(gsettings get org.gnome.shell favorite-apps 2>/dev/null || echo "[]")
        APP_ID="emoji-remover-z.desktop"
        if [[ "$CURRENT_FAVORITES" != *"$APP_ID"* ]]; then
            NEW_FAVORITES="$(echo "$CURRENT_FAVORITES" | sed "s/]/, '$APP_ID']/;s/\[\s*,/[/")"
            gsettings set org.gnome.shell favorite-apps "$NEW_FAVORITES" 2>/dev/null || true
        fi
    fi

    echo "  App menu entry:   $DESKTOP_DIR/emoji-remover-z.desktop"
    echo "  Desktop shortcut: $DESKTOP_SHORTCUT"
    echo "  Icon:             $ICON_DIR/emoji-remover-z.png"
    echo
    echo "The app will appear in your application menu under Utilities."
    echo "To pin to the GNOME sidebar: right-click the app in the launcher -> Add to Favorites."
    echo "To pin to the KDE taskbar:   right-click the app in the menu -> Add to Panel."
    echo "(You may need to log out and back in for the icon to appear.)"

else
    echo "[5/5] Skipping .desktop install (macOS detected)."
fi

echo
echo "Done!"
echo
echo "Your executable is at:  $SCRIPT_DIR/Emoji_Remover_Z"
echo
