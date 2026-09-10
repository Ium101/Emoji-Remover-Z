#!/bin/bash
# Emoji Remover Z - Setup Script (Linux / macOS)
# Runs the app straight from emoji-remover-z.py — no compiled executable is
# built here. Only the icon and desktop shortcuts are generated.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_PY="$SCRIPT_DIR/emoji-remover-z.py"

echo "===================================================="
echo "  Emoji Remover Z - Setup Script"
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

echo "[2/5] Removing old compiled build (if any)..."
# Earlier versions of this script produced a PyInstaller executable here.
# Delete any leftovers so nothing stale is left for an old shortcut, taskbar
# pin, or file-manager entry to still be pointing at.
rm -f "$SCRIPT_DIR/Emoji_Remover_Z"
rm -rf "$SCRIPT_DIR/build"
rm -f "$SCRIPT_DIR"/*.spec
echo

echo "[3/5] Checking for tkinter..."
if ! $PY -c "import tkinter" &>/dev/null; then
    echo "  WARNING: tkinter isn't available for $PY — the app won't run without it."
    echo "    Debian/Ubuntu/BigLinux: sudo apt install python3-tk"
    echo "    Fedora:                 sudo dnf install python3-tkinter"
    echo "    Arch:                   sudo pacman -S tk"
else
    echo "  tkinter OK"
fi
echo

echo "[4/5] Generating icon..."
# Pillow is only needed to render the icon once; it's installed into a
# throwaway venv so nothing extra is left behind for the app itself, since
# the app only needs the Python standard library to run.
$PY -m venv .iconenv
source .iconenv/bin/activate
pip install --quiet Pillow
python "$APP_PY" --generate-icon --png-only
deactivate
rm -rf .iconenv

if [[ ! -f "$SCRIPT_DIR/emoji_remover_z.png" ]]; then
    echo "ERROR: Icon file was not created."
    exit 1
fi
echo "  Icon generated: emoji_remover_z.png"
echo

# Make the script directly runnable (shebang + exec bit): shortcuts and a
# terminal can both launch it as "./emoji-remover-z.py" from here on.
chmod +x "$APP_PY"

# Copy icon for the Linux app menu, then remove the loose source PNG.
ICON_HICOLOR="$HOME/.local/share/icons/hicolor/256x256/apps"
mkdir -p "$ICON_HICOLOR"
cp "$SCRIPT_DIR/emoji_remover_z.png" "$ICON_HICOLOR/emoji-remover-z.png"
rm -f "$SCRIPT_DIR/emoji_remover_z.png"

echo "[5/5] Installing shortcuts and app entry..."
echo

# ── Linux only ──────────────────────────────────────────────────────────────
if [[ "$OSTYPE" == "linux-gnu"* ]]; then

    DESKTOP_DIR="$HOME/.local/share/applications"

    # $HOME/Desktop is only correct on an English locale. On BigLinux and
    # most other pt-BR (or any non-English) systems, the folder your file
    # manager actually watches is named differently — e.g. "Área de
    # Trabalho" — and is recorded in ~/.config/user-dirs.dirs. Ask the
    # system for the real path instead of assuming; writing to the wrong
    # folder means the shortcut is created successfully but never appears
    # anywhere you'd see it.
    if command -v xdg-user-dir &>/dev/null; then
        XDG_DESKTOP="$(xdg-user-dir DESKTOP 2>/dev/null)"
    fi
    if [[ -z "$XDG_DESKTOP" || "$XDG_DESKTOP" == "$HOME" ]]; then
        # xdg-user-dir missing or desktop dir disabled/unset — fall back,
        # but this is the less reliable path.
        XDG_DESKTOP="$HOME/Desktop"
    fi
    DESKTOP_SHORTCUT="$XDG_DESKTOP/emoji-remover-z.desktop"
    mkdir -p "$DESKTOP_DIR" "$XDG_DESKTOP"

    # Broad search-and-destroy pass: an older revision of this script may
    # have used a different filename (spaces, different case, etc.) for the
    # shortcut, written Exec= pointing at the old compiled binary, or (like
    # the Desktop-folder bug this fixes) landed in the wrong folder
    # entirely. Clean up BOTH the real desktop folder and the plain
    # "$HOME/Desktop" fallback some earlier run may have created, so no
    # stale copy is left behind in either place.
    echo "  Scanning for old/stale shortcuts to remove..."
    for dir in "$DESKTOP_DIR" "$XDG_DESKTOP" "$HOME/Desktop"; do
        [[ -d "$dir" ]] || continue
        while IFS= read -r -d '' f; do
            if grep -qiE 'emoji[_ -]?remover[_ -]?z' "$f" 2>/dev/null; then
                echo "    Removing: $f"
                rm -f "$f"
            fi
        done < <(find "$dir" -maxdepth 1 -iname "*.desktop" -print0 2>/dev/null)
    done

    # Write .desktop file for app menu — Exec points straight at the .py
    # file (executable via its shebang), not at a compiled binary. The path
    # is quoted in case it contains spaces.
    cat > "$DESKTOP_DIR/emoji-remover-z.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Emoji Remover Z
GenericName=Filename Cleaner
Comment=Remove emojis and styled text from filenames and folders
Exec="$APP_PY"
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
Exec="$APP_PY"
Icon=emoji-remover-z
Terminal=false
Categories=Utility;FileTools;
Keywords=emoji;rename;filename;unicode;cleaner;
StartupNotify=true
StartupWMClass=Emoji_Remover_Z
EOF

    chmod +x "$DESKTOP_SHORTCUT"

    # Verify what actually got written, so it's obvious in the terminal
    # output whether the fix took — rather than trusting it silently.
    echo
    echo "  Verifying Exec lines actually point at the .py file:"
    grep -H '^Exec=' "$DESKTOP_DIR/emoji-remover-z.desktop" "$DESKTOP_SHORTCUT" | sed 's/^/    /'

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
    if command -v kbuildsycoca6 &>/dev/null; then
        kbuildsycoca6 --noincremental 2>/dev/null || true
    elif command -v kbuildsycoca5 &>/dev/null; then
        kbuildsycoca5 --noincremental 2>/dev/null || true
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
    echo "  Icon:             $ICON_HICOLOR/emoji-remover-z.png"
    echo
    echo "No executable was built — both shortcuts run emoji-remover-z.py directly."
    echo "The app will appear in your application menu under Utilities."
    echo "To pin to the GNOME sidebar: right-click the app in the launcher -> Add to Favorites."
    echo "To pin to the KDE taskbar:   right-click the app in the menu -> Add to Panel."
    echo "(You may need to log out and back in for the icon to appear.)"
    echo
    echo "IMPORTANT — if an icon already pinned to your sidebar/taskbar still"
    echo "gives a 'could not find the program' error after this: that pin is"
    echo "a leftover from before and won't update itself. Right-click it,"
    echo "choose Unpin/Remove, then re-pin it fresh from the application menu"
    echo "(the entry rebuilt above, verified to point at the .py file)."

else
    echo "[5/5] Skipping .desktop install (macOS detected)."
fi

echo
echo "Done!"
echo
echo "Run it any time with:"
echo "  $APP_PY"
echo "or:"
echo "  $PY \"$APP_PY\""
echo
