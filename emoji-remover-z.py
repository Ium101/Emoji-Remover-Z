#!/usr/bin/env python3
import sys

# ── Build-time icon generation ───────────────────────────────────────────────
# Handled first and before any tkinter import: the build scripts call this
# script with --generate-icon (no display / no tkinter needed) to produce
# the app icon prior to packaging. Normal app runs are unaffected.
if "--generate-icon" in sys.argv:
    def _make_face(size: int):
        from PIL import Image, ImageDraw

        # Render at 8x and downscale for clean anti-aliasing.
        SS = 8
        S = size * SS
        cx, cy = S / 2, S / 2
        r = S * 0.47
        dark = (40, 25, 10, 255)

        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        outline_w = max(1, round(S * 0.025))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 200, 0, 255),
                   outline=(170, 110, 0, 255), width=outline_w)

        # Eyes like "||" — taller than wide so they read as vertical bars
        # even at small icon sizes (16–32 px), not flat lines.
        eye_w  = r * 0.11   # narrow width
        eye_h  = r * 0.20   # tall height — clearly taller than wide
        eye_y  = cy - r * 0.20
        eye_dx = r * 0.30

        for ex in (cx - eye_dx, cx + eye_dx):
            d.rounded_rectangle(
                [ex - eye_w, eye_y - eye_h, ex + eye_w, eye_y + eye_h],
                radius=eye_w, fill=dark,
            )

        # Open mouth smile: a crescent gap (outer half-circle with a
        # smaller circle cut from the top), wide and with clear margin
        # from both the eyes above and the chin below.
        smile_w = r * 0.55
        smile_top_y = cy + r * 0.02
        outer_h = r * 0.34
        outer_bbox = [cx - smile_w, smile_top_y, cx + smile_w, smile_top_y + outer_h * 2]

        mouth_mask = Image.new("L", (S, S), 0)
        mmd = ImageDraw.Draw(mouth_mask)
        mmd.pieslice(outer_bbox, start=0, end=180, fill=255)

        inner_w = smile_w * 0.68
        inner_h = outer_h * 0.50
        inner_top = smile_top_y + outer_h * 0.55
        inner_bbox = [cx - inner_w, inner_top, cx + inner_w, inner_top + inner_h * 2]
        mmd.ellipse(inner_bbox, fill=0)

        mouth_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        mouth_layer.paste(dark, mask=mouth_mask)
        img = Image.alpha_composite(img, mouth_layer)

        return img.resize((size, size), Image.LANCZOS)

    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = {s: _make_face(s) for s in sizes}
    imgs[256].save("emoji_remover_z.png")
    if "--png-only" not in sys.argv:
        imgs[256].save(
            "emoji_remover_z.ico",
            format="ICO",
            sizes=[(s, s) for s in sizes],
        )
    print("Icon generated.")
    sys.exit(0)

import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import os
import re
import unicodedata
from pathlib import Path
import threading
import queue
import configparser

PLATFORM = sys.platform  # 'win32', 'darwin', 'linux'

# ── Settings file (per-OS, stored next to the script/executable) ──────────────
# Windows -> emoji-remover-z_windows.ini
# Linux   -> emoji-remover-z_linux.ini
# (macOS falls back to the linux-style name since it's not explicitly required)

def _app_dir() -> Path:
    """Directory the script or frozen executable lives in."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


_INI_SUFFIX = "_windows.ini" if PLATFORM == "win32" else "_linux.ini"
SETTINGS_PATH = _app_dir() / f"emoji-remover-z{_INI_SUFFIX}"

_DEFAULT_SETTINGS = {
    "language": "en",
    "theme": "dark",
    "last_folder": "",
    "recursive": "False",
    "rename_folders": "True",
}


class Settings:
    """Tiny wrapper around configparser for persisting user preferences."""

    SECTION = "settings"

    def __init__(self, path: Path):
        self.path = path
        self._cfg = configparser.ConfigParser()
        self._data = dict(_DEFAULT_SETTINGS)
        self.load()

    def load(self):
        try:
            if self.path.exists():
                self._cfg.read(self.path, encoding="utf-8")
                if self._cfg.has_section(self.SECTION):
                    for key in _DEFAULT_SETTINGS:
                        if self._cfg.has_option(self.SECTION, key):
                            self._data[key] = self._cfg.get(self.SECTION, key)
        except Exception:
            # Corrupt/unreadable ini -> fall back to defaults silently
            self._data = dict(_DEFAULT_SETTINGS)

    def save(self):
        self._cfg[self.SECTION] = self._data
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                self._cfg.write(f)
        except Exception:
            pass  # Best-effort persistence; never crash the app over this.

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self._data.get(key, str(default))
        return str(val).strip().lower() in ("1", "true", "yes", "on")

    def set(self, key: str, value):
        self._data[key] = str(value)
        self.save()


# ── Translations ────────────────────────────────────────────────────────────────

TRANSLATIONS = {
    "en": {
        "app_title": "Emoji Remover Z",
        "app_subtitle": "strip emojis & styled text from filenames and folders",
        "folder_label": "FOLDER",
        "browse": "Browse",
        "recursive": "Include subfolders",
        "rename_folders": "Also rename folders",
        "scan": "⟳  Scan",
        "cancel": "✕  Cancel",
        "rename_selected": "✦  Rename Selected",
        "rename_n": "✦  Rename {n} File{s}",
        "preview_default": "PREVIEW  —  files to be renamed",
        "preview_found": "PREVIEW  —  {n} file{s} found  (click row to toggle)",
        "table_hint": "Click a filename to open it  •  Right-click for more options  •  Only names are modified, not contents",
        "select_all": "Select All",
        "deselect_all": "Deselect All",
        "col_original": "ORIGINAL FILENAME  (click → open file)",
        "col_renamed": "CLEANED FILENAME",
        "col_ext": "EXT",
        "col_type": "TYPE",
        "ctx_open_location": "📂  Open file location",
        "ctx_open_file": "▶  Open file",
        "ctx_toggle": "☑  Toggle selection",
        "footer": "Made by User Ium101 from GitHub",
        "status_counting": "Counting files…",
        "status_counting_n": "Counting… {n} files found",
        "status_scanning_n": "Scanning {n} files…",
        "status_found_n": "Scanning… {n} found",
        "status_cancelling": "Cancelling…",
        "status_cancelled_none": "Cancelled — no files found",
        "status_none_found": "No files to rename found",
        "status_n_found": "{n} file{s} found{suffix}",
        "status_renaming_n": "Renaming… {done}/{total}",
        "status_done": "✓ {n} file{s} renamed successfully",
        "status_done_errors": "Done — {n} renamed, {e} error(s)",
        "status_scan_error": "Scan error",
        "no_folder_title": "No folder",
        "no_folder_msg": "Please select a valid folder first.",
        "confirm_rename_title": "Confirm rename",
        "confirm_rename_msg": "Rename {n} item{s}?\n\nOnly names will be changed.\nFile and folder contents are never read or modified.",
        "scan_error_title": "Scan error",
        "scan_error_msg": "An error occurred:\n{e}",
        "partial_title": "Partial success",
        "partial_msg": "Renamed {ok} file{s} successfully.\n\n{e} error{es}:\n{lines}",
        "done_title": "Done",
        "done_msg": "Successfully renamed {n} item{s}.\n\nFile and folder contents were not modified.",
        "open_location_warn_title": "Open location",
        "open_location_warn_msg": "Could not open folder:\n{e}",
        "open_file_warn_title": "Open file",
        "open_file_warn_msg": "Could not open file:\n{e}",
        "select_folder_title": "Select folder",
        "theme_toggle_dark": "🌙",
        "theme_toggle_light": "☀",
        "lang_name": "EN",
    },
    "pt": {
        "app_title": "Emoji Remover Z",
        "app_subtitle": "remove emojis e texto estilizado de arquivos e pastas",
        "folder_label": "PASTA",
        "browse": "Procurar",
        "recursive": "Incluir subpastas",
        "rename_folders": "Renomear pastas também",
        "scan": "⟳  Escanear",
        "cancel": "✕  Cancelar",
        "rename_selected": "✦  Renomear Selecionados",
        "rename_n": "✦  Renomear {n} Arquivo{s}",
        "preview_default": "PRÉVIA  —  arquivos a serem renomeados",
        "preview_found": "PRÉVIA  —  {n} arquivo{s} encontrado{s}  (clique na linha para alternar)",
        "table_hint": "Clique no nome para abrir  •  Clique com botão direito para mais opções  •  Somente os nomes são modificados, não o conteúdo",
        "select_all": "Selecionar Tudo",
        "deselect_all": "Desmarcar Tudo",
        "col_original": "NOME ORIGINAL  (clique → abrir arquivo)",
        "col_renamed": "NOME LIMPO",
        "col_ext": "EXT",
        "col_type": "TIPO",
        "ctx_open_location": "📂  Abrir local do arquivo",
        "ctx_open_file": "▶  Abrir arquivo",
        "ctx_toggle": "☑  Alternar seleção",
        "footer": "Feito pelo Usuário Ium101 do GitHub",
        "status_counting": "Contando arquivos…",
        "status_counting_n": "Contando… {n} arquivos encontrados",
        "status_scanning_n": "Escaneando {n} arquivos…",
        "status_found_n": "Escaneando… {n} encontrados",
        "status_cancelling": "Cancelando…",
        "status_cancelled_none": "Cancelado — nenhum arquivo encontrado",
        "status_none_found": "Nenhum arquivo para renomear encontrado",
        "status_n_found": "{n} arquivo{s} encontrado{s}{suffix}",
        "status_renaming_n": "Renomeando… {done}/{total}",
        "status_done": "✓ {n} arquivo{s} renomeado{s} com sucesso",
        "status_done_errors": "Concluído — {n} renomeado(s), {e} erro(s)",
        "status_scan_error": "Erro ao escanear",
        "no_folder_title": "Nenhuma pasta",
        "no_folder_msg": "Selecione uma pasta válida primeiro.",
        "confirm_rename_title": "Confirmar renomeação",
        "confirm_rename_msg": "Renomear {n} item{s}?\n\nApenas os nomes serão alterados.\nO conteúdo de arquivos e pastas nunca é lido ou modificado.",
        "scan_error_title": "Erro ao escanear",
        "scan_error_msg": "Ocorreu um erro:\n{e}",
        "partial_title": "Sucesso parcial",
        "partial_msg": "{ok} arquivo{s} renomeado{s} com sucesso.\n\n{e} erro{es}:\n{lines}",
        "done_title": "Concluído",
        "done_msg": "{n} item{s} renomeado{s} com sucesso.\n\nO conteúdo de arquivos e pastas não foi modificado.",
        "open_location_warn_title": "Abrir local",
        "open_location_warn_msg": "Não foi possível abrir a pasta:\n{e}",
        "open_file_warn_title": "Abrir arquivo",
        "open_file_warn_msg": "Não foi possível abrir o arquivo:\n{e}",
        "select_folder_title": "Selecionar pasta",
        "theme_toggle_dark": "🌙",
        "theme_toggle_light": "☀",
        "lang_name": "PT",
    },
}


# ── Themes ──────────────────────────────────────────────────────────────────────

THEMES = {
    "dark": {
        "BG":      "#0f0f13",
        "CARD":    "#18181f",
        "BORDER":  "#2a2a35",
        "ACCENT":  "#ff6b35",
        "ACCENT2": "#ff9f1c",
        "FG":      "#e8e8f0",
        "MUTED":   "#7a7a90",
        "GREEN":   "#3ddc84",
        "ENTRY_BG": "#0f0f13",
        "SEL_BG":   "#2a2a45",
        "DANGER_BG": "#3a2020",
        "DANGER_FG": "#ff6060",
        "DANGER_ACTIVE_BG": "#5a2020",
        "DANGER_ACTIVE_FG": "#ff9090",
        "HINT": "#4a4a60",
        "FOOTER": "#3a3a50",
        "DISABLED_FG": "#7a5040",
    },
    "light": {
        "BG":      "#f4f4f8",
        "CARD":    "#ffffff",
        "BORDER":  "#d8d8e2",
        "ACCENT":  "#e85d2a",
        "ACCENT2": "#ff9f1c",
        "FG":      "#1c1c24",
        "MUTED":   "#6a6a7e",
        "GREEN":   "#1f9d57",
        "ENTRY_BG": "#ffffff",
        "SEL_BG":   "#ffe2d2",
        "DANGER_BG": "#ffe0e0",
        "DANGER_FG": "#c43030",
        "DANGER_ACTIVE_BG": "#ffc9c9",
        "DANGER_ACTIVE_FG": "#a02020",
        "HINT": "#9090a0",
        "FOOTER": "#a0a0b0",
        "DISABLED_FG": "#d8a890",
    },
}

# All files are supported — no extension filter

# ── Styled-unicode → ASCII map ─────────────────────────────────────────────────
# Covers mathematical bold/italic/script/fraktur/sans/monospace/double-struck,
# fullwidth ASCII, and a selection of letterlike symbols.

_STYLED_TO_ASCII: dict[str, str] = {}

_MATH_BLOCKS = [
    (0x1D400, 'A', 26), (0x1D41A, 'a', 26),  # bold
    (0x1D434, 'A', 26), (0x1D44E, 'a', 26),  # italic
    (0x1D468, 'A', 26), (0x1D482, 'a', 26),  # bold italic
    (0x1D49C, 'A', 26), (0x1D4B6, 'a', 26),  # script
    (0x1D4D0, 'A', 26), (0x1D4EA, 'a', 26),  # bold script
    (0x1D504, 'A', 26), (0x1D51E, 'a', 26),  # fraktur
    (0x1D538, 'A', 26), (0x1D552, 'a', 26),  # double-struck
    (0x1D56C, 'A', 26), (0x1D586, 'a', 26),  # bold fraktur
    (0x1D5A0, 'A', 26), (0x1D5BA, 'a', 26),  # sans-serif
    (0x1D5D4, 'A', 26), (0x1D5EE, 'a', 26),  # sans-serif bold
    (0x1D608, 'A', 26), (0x1D622, 'a', 26),  # sans-serif italic
    (0x1D63C, 'A', 26), (0x1D656, 'a', 26),  # sans-serif bold italic
    (0x1D670, 'A', 26), (0x1D68A, 'a', 26),  # monospace
    (0x1D7CE, '0', 10),                       # bold digits
    (0x1D7D8, '0', 10),                       # double-struck digits
    (0x1D7E2, '0', 10),                       # sans-serif digits
    (0x1D7EC, '0', 10),                       # sans-serif bold digits
    (0x1D7F6, '0', 10),                       # monospace digits
]
for _start, _base, _count in _MATH_BLOCKS:
    for _i in range(_count):
        _STYLED_TO_ASCII[chr(_start + _i)] = chr(ord(_base) + _i)

# Fullwidth ASCII (！..～ → !..~) and fullwidth space
for _cp in range(0xFF01, 0xFF5F):
    _STYLED_TO_ASCII[chr(_cp)] = chr(_cp - 0xFF01 + 0x21)
_STYLED_TO_ASCII['\u3000'] = ' '

# Letterlike symbols
_STYLED_TO_ASCII.update({
    'ℂ':'C','ℊ':'g','ℋ':'H','ℌ':'H','ℍ':'H','ℎ':'h','ℏ':'h',
    'ℐ':'I','ℑ':'I','ℒ':'L','ℓ':'l','ℕ':'N','℘':'P','ℙ':'P',
    'ℚ':'Q','ℛ':'R','ℜ':'R','ℝ':'R','ℤ':'Z','ℨ':'Z','ℬ':'B',
    'ℭ':'C','ℯ':'e','ℰ':'E','ℱ':'F','ℳ':'M','ℴ':'o',
})


def normalize_styled(name: str) -> tuple[str, bool]:
    """Replace bold/italic/styled unicode chars with plain ASCII equivalents."""
    result = [_STYLED_TO_ASCII.get(c, c) for c in name]
    normalized = ''.join(result)
    return normalized, (normalized != name)


# ── Emoji detection ────────────────────────────────────────────────────────────

_EMOJI_RANGES = [
    (0x1F600, 0x1F64F), (0x1F300, 0x1F5FF), (0x1F680, 0x1F6FF),
    (0x1F700, 0x1F77F), (0x1F780, 0x1F7FF), (0x1F800, 0x1F8FF),
    (0x1F900, 0x1F9FF), (0x1FA00, 0x1FA6F), (0x1FA70, 0x1FAFF),
    (0x2300,  0x23FF),  (0x2600,  0x26FF),  (0x2700,  0x27BF),
    (0xFE00,  0xFE0F),  (0x1F1E0, 0x1F1FF), (0x200D,  0x200D),
    (0x20D0,  0x20FF),  (0xFE20,  0xFE2F),
]


def is_emoji(char: str) -> bool:
    cp = ord(char)
    for start, end in _EMOJI_RANGES:
        if start <= cp <= end:
            return True
    try:
        cat = unicodedata.category(char)
        if cat in ('So', 'Sm') and cp > 0x2000:
            return True
    except Exception:
        pass
    return False


def remove_emojis(name: str) -> tuple[str, bool]:
    """
    Remove emoji characters from name.
    Trims spaces that were only adjacent to removed emojis.
    Returns (cleaned_name, had_emojis).
    """
    flags = [is_emoji(c) for c in name]
    if not any(flags):
        return name, False
    result: list[str] = []
    i = 0
    while i < len(name):
        if flags[i]:
            # Remove trailing space that padded this emoji on the left
            while result and result[-1] == ' ':
                result.pop()
            i += 1
            # Skip one padding space after the emoji (if any)
            if i < len(name) and name[i] == ' ' and not flags[i]:
                if result:          # only skip if something precedes
                    result.append(' ')
                i += 1
        else:
            result.append(name[i])
            i += 1
    cleaned = ''.join(result).strip()
    return (cleaned if cleaned else 'file'), True


# Characters forbidden in Windows filenames (also scrubbed on all platforms for portability)
_WIN_FORBIDDEN = frozenset('\\/:*?"<>|')
# Additional Unicode punctuation/symbols that are problematic or visually noisy in filenames
# (bullet •, middle dot ·, section §, etc.) — Po/So chars outside normal text ranges
_EXTRA_STRIP_RANGES = [
    (0x2000, 0x206F),  # General Punctuation (bullets, dashes, quotes, etc.)
    (0x2190, 0x21FF),  # Arrows
    (0x2200, 0x22FF),  # Mathematical Operators
    (0x2300, 0x23FF),  # Miscellaneous Technical (already in emoji ranges)
    (0x2500, 0x257F),  # Box Drawing
    (0x2580, 0x259F),  # Block Elements
    (0x25A0, 0x25FF),  # Geometric Shapes
    (0x2900, 0x297F),  # Supplemental Arrows
    (0x2B00, 0x2BFF),  # Miscellaneous Symbols and Arrows
]

# Special decorative characters that need to be stripped
_SPECIAL_CHARS_TO_STRIP = frozenset([
    # Most problematic decorative marks from user examples
    '✩', '✧', '⋆', '☾', '✺', '❉', '✾',
    '♡', '♥', '💀',  # Hearts and skull
    '┌', '┐', '┘', '└', '╚', '╔', '╝', '║', '═', '╳',  # Box drawing
    '●', '○', '◟', '◞', '☑',  # Circles and checkboxes
])

def _is_extra_strip(char: str) -> bool:
    cp = ord(char)
    # Preserve CJK characters (Chinese, Japanese Kanji)
    if (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF) or (0xF900 <= cp <= 0xFAFF):
        return False
    for start, end in _EXTRA_STRIP_RANGES:
        if start <= cp <= end:
            return True
    return False


def sanitize_for_filesystem(name: str) -> tuple[str, bool]:
    """
    Remove characters that are forbidden or problematic in filenames.
    Only reports was_changed=True if a character was actually removed/replaced.
    Does NOT normalise whitespace unless a removal created adjacent spaces.
    Invisible characters are removed silently without marking as changed.
    """
    # Invisible characters that should be removed silently
    _INVISIBLE_CHARS = frozenset([
        '\ufe0e', '\ufe0f',  # text/emoji variation selectors
        '\u200d', '\u200c', '\u200b',  # ZWJ, ZWNJ, zero-width space
    ])
    
    # Whitelist for dash/hyphen variants and other characters we want to keep
    _DASH_WHITELIST = frozenset([
        '-',           # U+002D HYPHEN-MINUS (regular hyphen)
        '\u2010',      # HYPHEN
        '\u2011',      # NON-BREAKING HYPHEN
        '\u2012',      # FIGURE DASH
        '\u2013',      # EN DASH
        '\u2014',      # EM DASH
        '\u2026',      # HORIZONTAL ELLIPSIS (...)
    ])
    
    result = []
    actually_changed = False
    for c in name:
        # Remove invisible characters silently (don't mark as changed)
        if c in _INVISIBLE_CHARS:
            continue
        if c in _WIN_FORBIDDEN:
            result.append(' ')
            actually_changed = True
            continue
        cp = ord(c)
        if cp < 32:
            actually_changed = True
            continue
        if c in _DASH_WHITELIST:
            result.append(c)
            continue
        if c in _SPECIAL_CHARS_TO_STRIP:
            actually_changed = True
            continue
        if _is_extra_strip(c) and not c.isalnum() and c not in ' _-()[]{}.,!@#%^&+=~`\':‐‑‒–—':
            actually_changed = True
            continue
        result.append(c)

    if not actually_changed:
        return name, False

    # Only clean up spaces that were created by removals
    cleaned = re.sub(r' {2,}', ' ', ''.join(result)).strip()
    return (cleaned if cleaned else 'file'), True


def clean_name(name: str) -> tuple[str, bool]:
    """
    Apply all three transformations in order:
      1. Normalize styled unicode (bold/italic/fullwidth/…) → plain ASCII
      2. Remove emojis
      3. Strip filesystem-forbidden and problematic symbols
    Returns (final_name, was_changed).
    """
    step1, c1 = normalize_styled(name)
    step2, c2 = remove_emojis(step1)
    step3, c3 = sanitize_for_filesystem(step2)
    return step3, (c1 or c2 or c3)


# ── Safe rename ────────────────────────────────────────────────────────────────

def get_unique_path(directory: str, new_name: str, ext: str) -> str:
    base = os.path.join(directory, new_name + ext)
    if not os.path.exists(base):
        return base
    counter = 1
    while counter < 100_000:
        candidate = os.path.join(directory, f"{new_name}_{counter}{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1
    raise RuntimeError(f"Could not find a unique name for '{new_name}{ext}'")


def safe_rename(src_path: Path, new_stem: str, ext: str) -> str:
    if not src_path.exists():
        raise FileNotFoundError(f"Source no longer exists: {src_path}")
    if not src_path.is_file():
        raise ValueError(f"Source is not a regular file: {src_path}")
    dest = get_unique_path(str(src_path.parent), new_stem, ext)
    try:
        os.rename(str(src_path), dest)
    except FileExistsError:
        dest = get_unique_path(str(src_path.parent), new_stem + "_r", ext)
        os.rename(str(src_path), dest)
    return dest


# ── Folder scanner ─────────────────────────────────────────────────────────────

def scan_folder(folder: str, recursive: bool, rename_folders: bool,
                cancel_event: threading.Event,
                out_queue: queue.Queue) -> None:
    """
    Phase 1 — walk and collect all supported files and folders, emitting __count__ per item.
    Phase 2 — check each name, emitting __item__ (match) or __progress__ (no match).
    Ends with None sentinel.
    """
    root_path = Path(folder)
    all_items: list[tuple[Path, str]] = []  # (path, 'file' or 'folder')

    try:
        for dirpath, dirs, files in os.walk(str(root_path)):
            if cancel_event.is_set():
                out_queue.put(None)
                return
            # Collect folders first (if enabled)
            if rename_folders:
                for dname in dirs:
                    try:
                        p = Path(dirpath) / dname
                        all_items.append((p, 'folder'))
                        out_queue.put(("__count__", len(all_items)))
                    except (PermissionError, OSError):
                        continue
            # Then collect files
            for fname in files:
                try:
                    p = Path(dirpath) / fname
                    all_items.append((p, 'file'))
                    out_queue.put(("__count__", len(all_items)))
                except (PermissionError, OSError):
                    continue
            if not recursive:
                dirs.clear()
    except (PermissionError, OSError):
        pass

    total = len(all_items)
    out_queue.put(("__total__", total))

    for i, (p, item_type) in enumerate(all_items):
        if cancel_event.is_set():
            break
        try:
            if item_type == 'folder':
                cleaned, changed = clean_name(p.name)
            else:
                cleaned, changed = clean_name(p.stem)
                cleaned_with_ext = (cleaned, p.suffix)
            
            if changed:
                if item_type == 'folder':
                    out_queue.put(("__item__", (p, p.name, cleaned, '', item_type), i + 1, total))
                else:
                    out_queue.put(("__item__", (p, p.stem, cleaned, p.suffix, item_type), i + 1, total))
            else:
                out_queue.put(("__progress__", i + 1, total))
        except (PermissionError, OSError):
            out_queue.put(("__progress__", i + 1, total))

    out_queue.put(None)


# ── GUI constants ──────────────────────────────────────────────────────────────

CHECK_ON  = "☑"
CHECK_OFF = "☐"


# ── Application ────────────────────────────────────────────────────────────────

class App(tk.Tk):
    _BATCH_SIZE = 100
    _POLL_MS    = 50

    def __init__(self):
        super().__init__(className="Emoji_Remover_Z")

        self.settings = Settings(SETTINGS_PATH)
        self.lang  = self.settings.get("language", "en")
        if self.lang not in TRANSLATIONS:
            self.lang = "en"
        self.theme = self.settings.get("theme", "dark")
        if self.theme not in THEMES:
            self.theme = "dark"

        self.title("Emoji Remover Z")
        self.geometry("960x690")
        self.minsize(720, 500)
        self.resizable(True, True)

        self.folder_var    = tk.StringVar(value=self.settings.get("last_folder", ""))
        self.recursive_var = tk.BooleanVar(value=self.settings.get_bool("recursive", False))
        self.rename_folders_var = tk.BooleanVar(value=self.settings.get_bool("rename_folders", True))

        # Scan state — all parallel lists indexed by row
        self._preview_data: list[tuple] = []   # (Path, old_stem, new_stem, ext, item_type)
        self._row_ids:      list[str]   = []   # treeview iid
        self._checked:      list[bool]  = []   # True = will be renamed

        self._scan_queue   = queue.Queue()
        self._cancel_event = threading.Event()
        self._scan_active  = False
        self._found_total  = 0
        self._scan_total   = 0
        self._prog_visible = False

        self.configure(bg=self._c("BG"))
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Auto-scan on startup if a folder was restored from settings
        if self.folder_var.get().strip() and os.path.isdir(self.folder_var.get().strip()):
            self.after(150, self._scan)

    # ── i18n / theme helpers ─────────────────────────────────────────────────────

    def _t(self, key: str, **kwargs) -> str:
        text = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"]).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

    def _c(self, key: str) -> str:
        return THEMES.get(self.theme, THEMES["dark"])[key]

    def _on_close(self):
        self._cancel_event.set()
        self.settings.set("last_folder", self.folder_var.get().strip())
        self.destroy()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        BG, CARD, BORDER   = self._c("BG"), self._c("CARD"), self._c("BORDER")
        ACCENT, ACCENT2    = self._c("ACCENT"), self._c("ACCENT2")
        FG, MUTED, GREEN   = self._c("FG"), self._c("MUTED"), self._c("GREEN")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
                        background=CARD, foreground=FG,
                        fieldbackground=CARD, borderwidth=0,
                        rowheight=28, font=("Consolas", 9))
        style.configure("Treeview.Heading",
                        background=BORDER, foreground=MUTED,
                        font=("Consolas", 9, "bold"), relief="flat")
        style.map("Treeview",
                  background=[("selected", self._c("SEL_BG"))],
                  foreground=[("selected", FG)])
        style.configure("Vertical.TScrollbar",
                        background=BORDER, troughcolor=CARD,
                        arrowcolor=MUTED, borderwidth=0)
        style.configure("TCheckbutton",
                        background=BG, foreground=MUTED,
                        font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("TProgressbar",
                        troughcolor=BORDER, background=GREEN,
                        borderwidth=0, thickness=6)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=BG, pady=20)
        hdr.pack(fill="x", padx=28)
        tk.Label(hdr, text="✦ EMOJI REMOVER Z",
                 font=("Courier New", 18, "bold"),
                 bg=BG, fg=ACCENT).pack(side="left")
        self.subtitle_lbl = tk.Label(hdr, text=self._t("app_subtitle"),
                 font=("Segoe UI", 10), bg=BG, fg=MUTED)
        self.subtitle_lbl.pack(side="left", padx=14, pady=4)

        # Theme + language toggles, right-aligned in the header
        self.lang_btn = tk.Button(hdr,
                  text=TRANSLATIONS[self.lang]["lang_name"],
                  command=self._toggle_language,
                  font=("Segoe UI", 9, "bold"),
                  bg=BORDER, fg=FG, activebackground=ACCENT,
                  activeforeground="#fff", relief="flat",
                  padx=10, pady=4, cursor="hand2", bd=0, width=3)
        self.lang_btn.pack(side="right", padx=(8, 0))

        theme_icon = self._t("theme_toggle_light") if self.theme == "dark" else self._t("theme_toggle_dark")
        self.theme_btn = tk.Button(hdr, text=theme_icon,
                  command=self._toggle_theme,
                  font=("Segoe UI", 11),
                  bg=BORDER, fg=FG, activebackground=ACCENT,
                  activeforeground="#fff", relief="flat",
                  padx=10, pady=4, cursor="hand2", bd=0, width=3)
        self.theme_btn.pack(side="right")

        # ── Folder picker ─────────────────────────────────────────────────────
        picker = tk.Frame(self, bg=CARD, bd=0,
                          highlightthickness=1, highlightbackground=BORDER)
        picker.pack(fill="x", padx=28, pady=(0, 12))
        self.folder_label_lbl = tk.Label(picker, text=self._t("folder_label"), font=("Consolas", 8, "bold"),
                 bg=CARD, fg=MUTED)
        self.folder_label_lbl.pack(anchor="w", padx=14, pady=(10, 2))
        row = tk.Frame(picker, bg=CARD)
        row.pack(fill="x", padx=14, pady=(0, 12))
        self.path_entry = tk.Entry(row, textvariable=self.folder_var,
                                   font=("Consolas", 10), bg=self._c("ENTRY_BG"),
                                   fg=FG, insertbackground=ACCENT,
                                   relief="flat", bd=8,
                                   highlightthickness=1,
                                   highlightbackground=BORDER,
                                   highlightcolor=ACCENT)
        self.path_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.browse_btn = tk.Button(row, text=self._t("browse"), command=self._browse,
                  font=("Segoe UI", 9, "bold"),
                  bg=BORDER, fg=FG, activebackground=ACCENT,
                  activeforeground="#fff", relief="flat",
                  padx=16, pady=6, cursor="hand2", bd=0)
        self.browse_btn.pack(side="left", padx=(8, 0))
        opt_row = tk.Frame(picker, bg=CARD)
        opt_row.pack(fill="x", padx=14, pady=(0, 12))
        self.recursive_chk = ttk.Checkbutton(opt_row,
                        text=self._t("recursive"),
                        variable=self.recursive_var,
                        command=self._on_recursive_toggle,
                        style="TCheckbutton")
        self.recursive_chk.pack(side="left")
        self.rename_folders_chk = ttk.Checkbutton(opt_row,
                        text=self._t("rename_folders"),
                        variable=self.rename_folders_var,
                        command=self._on_rename_folders_toggle,
                        style="TCheckbutton")
        self.rename_folders_chk.pack(side="left", padx=(20, 0))

        # ── Action buttons ────────────────────────────────────────────────────
        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", padx=28, pady=(0, 4))

        self.scan_btn = tk.Button(btns, text=self._t("scan"),
                                  command=self._scan,
                                  font=("Segoe UI", 10, "bold"),
                                  bg=BORDER, fg=FG,
                                  activebackground="#3a3a50",
                                  relief="flat", padx=20, pady=8,
                                  cursor="hand2", bd=0)
        self.scan_btn.pack(side="left")

        self.cancel_btn = tk.Button(btns, text=self._t("cancel"),
                                    command=self._cancel_scan,
                                    font=("Segoe UI", 10, "bold"),
                                    bg=self._c("DANGER_BG"), fg=self._c("DANGER_FG"),
                                    activebackground=self._c("DANGER_ACTIVE_BG"),
                                    activeforeground=self._c("DANGER_ACTIVE_FG"),
                                    relief="flat", padx=14, pady=8,
                                    cursor="hand2", bd=0)
        # shown only while scanning

        self.rename_btn = tk.Button(btns, text=self._t("rename_selected"),
                                    command=self._rename,
                                    state="disabled",
                                    font=("Segoe UI", 10, "bold"),
                                    bg=ACCENT, fg="#fff",
                                    activebackground=ACCENT2,
                                    activeforeground="#fff",
                                    relief="flat", padx=20, pady=8,
                                    cursor="hand2", bd=0,
                                    disabledforeground=self._c("DISABLED_FG"))
        self.rename_btn.pack(side="left", padx=(10, 0))

        self.status_lbl = tk.Label(btns, text="",
                                   font=("Segoe UI", 9), bg=BG, fg=MUTED)
        self.status_lbl.pack(side="right")

        # ── Progress bar (fixed-height slot, always reserved) ─────────────────
        prog_frame = tk.Frame(self, bg=BG, height=10)
        prog_frame.pack(fill="x", padx=28, pady=(4, 0))
        prog_frame.pack_propagate(False)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate",
                                        style="TProgressbar", maximum=100)

        # ── Preview table ─────────────────────────────────────────────────────
        tbl_frame = tk.Frame(self, bg=CARD, bd=0,
                             highlightthickness=1, highlightbackground=BORDER)
        tbl_frame.pack(fill="both", expand=True, padx=28, pady=(8, 8))

        # Table header row with hint + Select All / Deselect All
        hdr_row = tk.Frame(tbl_frame, bg=CARD)
        hdr_row.pack(fill="x", padx=14, pady=(10, 2))
        self.table_label = tk.Label(hdr_row,
                                    text=self._t("preview_default"),
                                    font=("Consolas", 8, "bold"),
                                    bg=CARD, fg=MUTED, anchor="w")
        self.table_label.pack(side="left")

        self.table_hint_lbl = tk.Label(hdr_row,
                 text=self._t("table_hint"),
                 font=("Segoe UI", 7), bg=CARD, fg=self._c("HINT"))
        self.table_hint_lbl.pack(side="left", padx=(12, 0))

        self.deselect_all_btn = tk.Button(hdr_row, text=self._t("deselect_all"),
                  command=self._deselect_all,
                  font=("Segoe UI", 8),
                  bg=BORDER, fg=MUTED,
                  activebackground="#3a3a50", activeforeground=FG,
                  relief="flat", padx=8, pady=2,
                  cursor="hand2", bd=0)
        self.deselect_all_btn.pack(side="right", padx=(4, 0))
        self.select_all_btn = tk.Button(hdr_row, text=self._t("select_all"),
                  command=self._select_all,
                  font=("Segoe UI", 8),
                  bg=BORDER, fg=MUTED,
                  activebackground="#3a3a50", activeforeground=FG,
                  relief="flat", padx=8, pady=2,
                  cursor="hand2", bd=0)
        self.select_all_btn.pack(side="right", padx=(0, 4))

        cols = ("check", "original", "renamed", "type", "kind")
        self.tree = ttk.Treeview(tbl_frame, columns=cols,
                                 show="headings", selectmode="browse")
        self.tree.heading("check",    text="")
        self.tree.heading("original", text=self._t("col_original"))
        self.tree.heading("renamed",  text=self._t("col_renamed"))
        self.tree.heading("type",     text=self._t("col_ext"))
        self.tree.heading("kind",     text=self._t("col_type"))
        self.tree.column("check",    width=32,  minwidth=32,  stretch=False, anchor="center")
        self.tree.column("original", width=340, minwidth=160)
        self.tree.column("renamed",  width=340, minwidth=160)
        self.tree.column("type",     width=55,  minwidth=45,  anchor="center")
        self.tree.column("kind",     width=55,  minwidth=45,  anchor="center")

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical",
                            command=self.tree.yview,
                            style="Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y", padx=(0, 6), pady=6)
        self.tree.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        self.tree.tag_configure("checked",   foreground=GREEN)
        self.tree.tag_configure("unchecked", foreground=MUTED)

        # Left-click: toggle checkbox (col #1) or open folder (col #2 = original)
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        # Double-click anywhere also opens folder
        self.tree.bind("<Double-ButtonRelease-1>", self._on_tree_double_click)
        # Right-click context menu
        self._ctx_menu = tk.Menu(self, tearoff=0, bg=CARD, fg=FG,
                                 activebackground=BORDER, activeforeground=FG,
                                 relief="flat", bd=0,
                                 font=("Segoe UI", 9))
        self._ctx_menu.add_command(label=self._t("ctx_open_location"),
                                   command=self._ctx_open_location)
        self._ctx_menu.add_command(label=self._t("ctx_open_file"),
                                   command=self._ctx_open_file)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label=self._t("ctx_toggle"),
                                   command=self._ctx_toggle)
        self._ctx_iid: str | None = None
        self.tree.bind("<ButtonRelease-3>", self._on_tree_right_click)

        # ── Footer ────────────────────────────────────────────────────────────
        self.footer_lbl = tk.Label(self,
                 text=self._t("footer"),
                 font=("Segoe UI", 8), bg=BG, fg=self._c("FOOTER"))
        self.footer_lbl.pack(pady=(4, 10))

    # ── Theme / language toggles ─────────────────────────────────────────────────

    def _toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        self.settings.set("theme", self.theme)
        self._rebuild_ui()

    def _toggle_language(self):
        self.lang = "pt" if self.lang == "en" else "en"
        self.settings.set("language", self.lang)
        self._rebuild_ui()

    def _on_recursive_toggle(self):
        self.settings.set("recursive", self.recursive_var.get())

    def _on_rename_folders_toggle(self):
        self.settings.set("rename_folders", self.rename_folders_var.get())

    def _rebuild_ui(self):
        """Tear down and rebuild the UI in place after a theme/language change,
        preserving any in-progress scan results and folder selection."""
        preview_snapshot = list(self._preview_data)
        checked_snapshot  = list(self._checked)
        folder_value      = self.folder_var.get()

        for child in list(self.winfo_children()):
            child.destroy()

        self.folder_var.set(folder_value)
        self._row_ids = []
        self.configure(bg=self._c("BG"))
        self._build_ui()

        # Restore preview rows (theme/language change shouldn't lose a scan)
        if preview_snapshot:
            self._preview_data = []
            self._checked = []
            self._found_total = 0
            for item, was_checked in zip(preview_snapshot, checked_snapshot):
                self._preview_data.append(item)
                self._checked.append(was_checked)
                p, old_stem, new_stem, ext, item_type = item
                if item_type == 'folder':
                    display_old, display_new, ext_display, kind_display = old_stem, new_stem, "", "📁"
                else:
                    display_old, display_new = old_stem + ext, new_stem + ext
                    ext_display, kind_display = ext.lstrip('.'), "📄"
                iid = self.tree.insert("", "end",
                                       values=((CHECK_ON if was_checked else CHECK_OFF),
                                               display_old, display_new,
                                               ext_display, kind_display),
                                       tags=("checked" if was_checked else "unchecked",))
                self._row_ids.append(iid)
                self._found_total += 1
            n = self._found_total
            self.table_label.config(
                text=self._t("preview_found", n=n, s="s" if n != 1 else ""))
            self._update_rename_btn()

    # ── Browse ─────────────────────────────────────────────────────────────────

    def _browse(self):
        folder = filedialog.askdirectory(title=self._t("select_folder_title"))
        if folder:
            self.folder_var.set(folder)
            self.settings.set("last_folder", folder)
            self._scan()



    # ── Checkbox helpers ───────────────────────────────────────────────────────

    def _on_tree_click(self, event):
        iid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not iid or iid not in self._row_ids:
            return
        # col #2 = "original" filename column → open file
        if col == "#2":
            self._open_file(iid)
        else:
            self._toggle_check(iid)

    def _on_tree_double_click(self, event):
        iid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if iid and iid in self._row_ids and col != "#2":
            # double-click on non-original column also opens folder
            self._open_file_location(iid)

    def _open_file_location(self, iid: str):
        """Open the file's folder with the file selected/highlighted."""
        idx = self._row_ids.index(iid)
        p, _, _, _ = self._preview_data[idx]
        try:
            import subprocess
            if PLATFORM == "win32":
                # Explorer highlights the specific file
                subprocess.Popen(["explorer", "/select,", os.path.normpath(str(p))])
            elif PLATFORM == "darwin":
                # Finder reveals and selects the file
                subprocess.Popen(["open", "-R", str(p)])
            else:
                # Linux: open the parent folder (no universal "select file" standard)
                subprocess.Popen(["xdg-open", str(p.parent)])
        except Exception as e:
            messagebox.showwarning(self._t("open_location_warn_title"),
                                   self._t("open_location_warn_msg", e=e))

    def _open_file(self, iid: str):
        """Open the file with its default application."""
        idx = self._row_ids.index(iid)
        p, _, _, _ = self._preview_data[idx]
        try:
            import subprocess
            if PLATFORM == "win32":
                os.startfile(str(p))
            elif PLATFORM == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            messagebox.showwarning(self._t("open_file_warn_title"),
                                   self._t("open_file_warn_msg", e=e))

    def _on_tree_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and iid in self._row_ids:
            self.tree.selection_set(iid)
            self._ctx_iid = iid
            self._ctx_menu.tk_popup(event.x_root, event.y_root)

    def _ctx_open_location(self):
        if self._ctx_iid:
            self._open_file_location(self._ctx_iid)

    def _ctx_open_file(self):
        if self._ctx_iid:
            self._open_file(self._ctx_iid)

    def _ctx_toggle(self):
        if self._ctx_iid:
            self._toggle_check(self._ctx_iid)

    def _refresh_row(self, idx: int):
        iid     = self._row_ids[idx]
        checked = self._checked[idx]
        p, old_stem, new_stem, ext, item_type = self._preview_data[idx]
        if item_type == 'folder':
            display_old = old_stem
            display_new = new_stem
            ext_display = ""
        else:
            display_old = old_stem + ext
            display_new = new_stem + ext
            ext_display = ext.lstrip('.')
        self.tree.item(iid,
                       values=(CHECK_ON if checked else CHECK_OFF,
                               display_old,
                               display_new,
                               ext_display,
                               "📁" if item_type == 'folder' else "📄"),
                       tags=("checked" if checked else "unchecked",))

    def _select_all(self):
        self._checked = [True] * len(self._checked)
        for i in range(len(self._row_ids)):
            self._refresh_row(i)
        self._update_rename_btn()

    def _deselect_all(self):
        self._checked = [False] * len(self._checked)
        for i in range(len(self._row_ids)):
            self._refresh_row(i)
        self._update_rename_btn()

    def _update_rename_btn(self):
        n = sum(self._checked)
        if n > 0:
            self.rename_btn.config(
                state="normal",
                text=self._t("rename_n", n=n, s="s" if n != 1 else ""))
        else:
            self.rename_btn.config(state="disabled", text=self._t("rename_selected"))

    # ── Scan ───────────────────────────────────────────────────────────────────

    def _scan(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning(self._t("no_folder_title"), self._t("no_folder_msg"))
            return

        self.settings.set("last_folder", folder)

        # Reset all state
        self._cancel_event.clear()
        self._preview_data.clear()
        self._row_ids.clear()
        self._checked.clear()
        self._found_total = 0
        self._scan_total  = 0
        self._scan_queue  = queue.Queue()

        self.tree.delete(*self.tree.get_children())
        self.table_label.config(text=self._t("preview_default"))
        self._set_status(self._t("status_counting"))
        self.scan_btn.config(state="disabled")
        self.rename_btn.config(state="disabled", text=self._t("rename_selected"))
        self.cancel_btn.pack(side="left", padx=(10, 0))
        self.progress["value"] = 0
        self._show_progress(True)
        self._scan_active = True

        threading.Thread(
            target=self._scan_worker,
            args=(folder, self.recursive_var.get(), self.rename_folders_var.get()),
            daemon=True
        ).start()
        self.after(self._POLL_MS, self._poll_scan_queue)

    def _scan_worker(self, folder: str, recursive: bool, rename_folders: bool):
        try:
            scan_folder(folder, recursive, rename_folders, self._cancel_event, self._scan_queue)
        except Exception as e:
            self._scan_queue.put(("__error__", str(e)))
            self._scan_queue.put(None)

    def _poll_scan_queue(self):
        if not self._scan_active:
            return
        batch = []
        try:
            while len(batch) < self._BATCH_SIZE:
                msg = self._scan_queue.get_nowait()
                if msg is None:
                    self._finish_scan(batch)
                    return
                tag = msg[0]
                if tag == "__error__":
                    self._finish_scan(batch, error=msg[1])
                    return
                if tag == "__count__":
                    # Phase 1: asymptotic 0→40% so progress is always visible
                    n = msg[1]
                    self.progress["value"] = 40 * (1 - 1 / (1 + n / 25))
                    self._set_status(self._t("status_counting_n", n=n))
                elif tag == "__total__":
                    self._scan_total = msg[1]
                    self.progress["value"] = 40
                    self._set_status(self._t("status_scanning_n", n=self._scan_total))
                elif tag == "__progress__":
                    _, done, total = msg
                    if total > 0:
                        self.progress["value"] = 40 + (done / total) * 60
                elif tag == "__item__":
                    _, data, done, total = msg
                    if total > 0:
                        self.progress["value"] = 40 + (done / total) * 60
                    batch.append(data)
        except queue.Empty:
            pass
        if batch:
            self._insert_rows(batch)
        self.after(self._POLL_MS, self._poll_scan_queue)

    def _insert_rows(self, batch):
        for item in batch:
            p, old_stem, new_stem, ext, item_type = item
            self._preview_data.append(item)
            self._checked.append(True)
            if item_type == 'folder':
                display_old = old_stem
                display_new = new_stem
                ext_display = ""
                kind_display = "📁"
            else:
                display_old = old_stem + ext
                display_new = new_stem + ext
                ext_display = ext.lstrip('.')
                kind_display = "📄"
            iid = self.tree.insert("", "end",
                                   values=(CHECK_ON, display_old,
                                           display_new, ext_display, kind_display),
                                   tags=("checked",))
            self._row_ids.append(iid)
            self._found_total += 1
        self._set_status(self._t("status_found_n", n=self._found_total))
        self._update_rename_btn()

    def _finish_scan(self, remaining_batch, error=None):
        self._scan_active = False
        self.progress["value"] = 100
        self._show_progress(False)
        self.cancel_btn.pack_forget()
        self.scan_btn.config(state="normal")

        if remaining_batch:
            self._insert_rows(remaining_batch)

        if error:
            messagebox.showerror(self._t("scan_error_title"), self._t("scan_error_msg", e=error))
            self._set_status(self._t("status_scan_error"))
            return

        count     = self._found_total
        cancelled = self._cancel_event.is_set()
        if count:
            suffix = " (cancelled)" if cancelled else ""
            self.table_label.config(
                text=self._t("preview_found", n=count, s="s" if count != 1 else ""))
            self._set_status(self._t("status_n_found", n=count,
                                     s="s" if count != 1 else "", suffix=suffix))
            self._update_rename_btn()
        else:
            self._set_status(
                self._t("status_cancelled_none") if cancelled else self._t("status_none_found"))

    def _cancel_scan(self):
        self._cancel_event.set()
        self._set_status(self._t("status_cancelling"))

    # ── Rename ─────────────────────────────────────────────────────────────────

    def _rename(self):
        snapshot = [(p, old, new, ext, item_type)
                    for (p, old, new, ext, item_type), checked
                    in zip(self._preview_data, self._checked)
                    if checked]
        if not snapshot:
            return

        count = len(snapshot)
        if not messagebox.askyesno(
                self._t("confirm_rename_title"),
                self._t("confirm_rename_msg", n=count, s="s" if count != 1 else ""),
                icon="question"):
            return

        self.rename_btn.config(state="disabled")
        self.scan_btn.config(state="disabled")
        self._set_status(self._t("status_renaming_n", done=0, total=count))
        self.progress["value"] = 0
        self._show_progress(True)

        threading.Thread(target=self._rename_worker,
                         args=(snapshot,), daemon=True).start()

    def _rename_worker(self, snapshot):
        ok     = 0
        errors = []
        total  = len(snapshot)
        for i, (p, old_stem, new_stem, ext, item_type) in enumerate(snapshot):
            try:
                if item_type == 'folder':
                    # For folders, rename the directory itself
                    dest = get_unique_path(str(p.parent), new_stem, '')
                    try:
                        os.rename(str(p), dest)
                    except FileExistsError:
                        dest = get_unique_path(str(p.parent), new_stem + "_r", '')
                        os.rename(str(p), dest)
                else:
                    # For files, use existing safe_rename
                    safe_rename(p, new_stem, ext)
                ok += 1
            except Exception as e:
                errors.append((p.name, str(e)))
            pct = (i + 1) * 100 / total
            self.after(0, self._set_rename_progress, pct, i + 1, total)
        self.after(0, self._finish_rename, ok, errors)

    def _set_rename_progress(self, pct: float, done: int, total: int):
        self.progress["value"] = pct
        self._set_status(self._t("status_renaming_n", done=done, total=total))

    def _finish_rename(self, ok: int, errors: list):
        self._show_progress(False)
        self.scan_btn.config(state="normal")
        self.tree.delete(*self.tree.get_children())
        self._preview_data.clear()
        self._row_ids.clear()
        self._checked.clear()
        self._found_total = 0
        self.table_label.config(text=self._t("preview_default"))
        self.rename_btn.config(state="disabled", text=self._t("rename_selected"))

        if errors:
            err_lines = "\n".join(f"• {n}: {m}" for n, m in errors[:50])
            if len(errors) > 50:
                err_lines += f"\n… and {len(errors) - 50} more."
            messagebox.showwarning(
                self._t("partial_title"),
                self._t("partial_msg", ok=ok, s="s" if ok != 1 else "",
                        e=len(errors), es="s" if len(errors) != 1 else "",
                        lines=err_lines))
            self._set_status(self._t("status_done_errors", n=ok, e=len(errors)))
        else:
            self._set_status(self._t("status_done", n=ok, s="s" if ok != 1 else ""))
            messagebox.showinfo(
                self._t("done_title"),
                self._t("done_msg", n=ok, s="s" if ok != 1 else ""))

    # ── Progress ───────────────────────────────────────────────────────────────

    def _show_progress(self, visible: bool):
        if visible and not self._prog_visible:
            self.progress.pack(fill="x", expand=True)
            self._prog_visible = True
        elif not visible and self._prog_visible:
            self.progress.pack_forget()
            self._prog_visible = False

    def _set_status(self, text: str):
        self.status_lbl.config(text=text)


if __name__ == "__main__":
    app = App()
    app.mainloop()
