#!/usr/bin/env python3
import sys

# Never let Python drop a __pycache__ folder next to the script.
sys.dont_write_bytecode = True

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
import time
import configparser
import atexit
import filecmp
import json
import shutil
import subprocess
import datetime
from urllib.parse import quote
import hashlib
import base64
import io

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
    "unchecked": "[]",          # JSON list of preview rows the user un-ticked
    "history": "[]",            # JSON list of previously used folders / file picks
}


class Settings:
    """Tiny wrapper around configparser for persisting user preferences."""

    SECTION = "settings"

    def __init__(self, path: Path):
        self.path = path
        # interpolation=None: paths may legitimately contain "%".
        self._cfg = configparser.ConfigParser(interpolation=None)
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
        try:
            self._cfg[self.SECTION] = self._data
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


def _cleanup_pycache():
    """Remove the __pycache__ folder next to the script (no-op when frozen)."""
    if getattr(sys, "frozen", False):
        return
    try:
        shutil.rmtree(Path(__file__).resolve().parent / "__pycache__",
                      ignore_errors=True)
    except Exception:
        pass


# ── Translations ────────────────────────────────────────────────────────────────

TRANSLATIONS = {
    "en": {
        "app_title": "Emoji Remover Z",
        "app_subtitle": "strip emojis & styled text from filenames and folders",
        "folder_label": "FOLDER OR FILES",
        "browse_folder": "📁  Browse folder",
        "browse_files": "🖼  Browse files",
        "recursive": "Include subfolders",
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
        "loading_title": "Loading…",
        "renaming_title": "Renaming…",
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
        "no_folder_msg": "Please select a valid folder or files first.",
        "confirm_rename_title": "Confirm rename",
        "confirm_rename_msg": "Rename {n} item{s}?\n\nOnly names will be changed.\nFile and folder contents are never modified.",
        "scan_error_title": "Scan error",
        "scan_error_msg": "An error occurred:\n{e}",
        "partial_title": "Partial success",
        "partial_msg": "Renamed {ok} file{s} successfully.\n\n{e} error{es}:\n{lines}",
        "done_title": "Done",
        "confirm_trash_note": "\n\nIf the cleaned name already exists: an emoji-named folder has its unique files moved into the existing one and then goes to the trash; an emoji-named file that is identical to the existing one goes to the trash. Anything trashed is recoverable.",
        "done_trashed": "{t} duplicate folder{ts} moved to the trash.",
        "done_trashed_files": "{t} duplicate file{ts} moved to the trash.",
        "done_merged": "Files moved into the existing folder before trashing the duplicate: {m}.",
        "done_msg": "Successfully renamed {n} item{s}.\n\nFile and folder contents were not modified.",
        "open_location_warn_title": "Open location",
        "open_location_warn_msg": "Could not open folder:\n{e}",
        "open_file_warn_title": "Open file",
        "open_file_warn_msg": "Could not open file:\n{e}",
        "select_folder_title": "Select folder",
        "select_files_title": "Select files",
        "files_n": "{n} files",
        "tp_places": "PLACES",
        "tp_recent": "RECENT",
        "tp_home": "Home",
        "tp_root": "Computer",
        "tp_up": "↑  Up",
        "tp_hidden": "Hidden files",
        "tp_selected": "{n} selected",
        "tp_select": "Select",
        "tp_cancel": "Cancel",
        "tp_all": "Select all",
        "tp_none": "Clear",
        "tp_empty": "No files in this folder",
        "tp_unreadable": "Can't open this folder",
        "tp_hint": "Click to tick  •  Shift+click for a range  •  Double-click a folder to open it  •  Double-click a file to pick just that one",
        "theme_toggle_dark": "🌙",
        "theme_toggle_light": "☀",
        "lang_name": "EN",
    },
    "pt": {
        "app_title": "Emoji Remover Z",
        "app_subtitle": "remove emojis e texto estilizado de arquivos e pastas",
        "folder_label": "PASTA OU ARQUIVOS",
        "browse_folder": "📁  Procurar pasta",
        "browse_files": "🖼  Procurar arquivos",
        "recursive": "Incluir subpastas",
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
        "loading_title": "Carregando…",
        "renaming_title": "Renomeando…",
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
        "no_folder_msg": "Selecione uma pasta ou arquivos válidos primeiro.",
        "confirm_rename_title": "Confirmar renomeação",
        "confirm_rename_msg": "Renomear {n} item{s}?\n\nApenas os nomes serão alterados.\nO conteúdo de arquivos e pastas nunca é modificado.",
        "scan_error_title": "Erro ao escanear",
        "scan_error_msg": "Ocorreu um erro:\n{e}",
        "partial_title": "Sucesso parcial",
        "partial_msg": "{ok} arquivo{s} renomeado{s} com sucesso.\n\n{e} erro{es}:\n{lines}",
        "done_title": "Concluído",
        "confirm_trash_note": "\n\nSe o nome limpo já existir: a pasta com emoji tem seus arquivos exclusivos movidos para a pasta existente e depois vai para a lixeira; um arquivo com emoji idêntico ao existente vai para a lixeira. Tudo que for para a lixeira é recuperável.",
        "done_trashed": "{t} pasta{ts} duplicada{ts} movida{ts} para a lixeira.",
        "done_trashed_files": "{t} arquivo{ts} duplicado{ts} movido{ts} para a lixeira.",
        "done_merged": "Arquivos movidos para a pasta existente antes de mandar a duplicata para a lixeira: {m}.",
        "done_msg": "{n} item{s} renomeado{s} com sucesso.\n\nO conteúdo de arquivos e pastas não foi modificado.",
        "open_location_warn_title": "Abrir local",
        "open_location_warn_msg": "Não foi possível abrir a pasta:\n{e}",
        "open_file_warn_title": "Abrir arquivo",
        "open_file_warn_msg": "Não foi possível abrir o arquivo:\n{e}",
        "select_folder_title": "Selecionar pasta",
        "select_files_title": "Selecionar arquivos",
        "files_n": "{n} arquivos",
        "tp_places": "LOCAIS",
        "tp_recent": "RECENTES",
        "tp_home": "Pasta pessoal",
        "tp_root": "Computador",
        "tp_up": "↑  Acima",
        "tp_hidden": "Arquivos ocultos",
        "tp_selected": "{n} selecionado(s)",
        "tp_select": "Selecionar",
        "tp_cancel": "Cancelar",
        "tp_all": "Selecionar tudo",
        "tp_none": "Limpar",
        "tp_empty": "Nenhum arquivo nesta pasta",
        "tp_unreadable": "Não foi possível abrir esta pasta",
        "tp_hint": "Clique para marcar  •  Shift+clique para um intervalo  •  Duplo clique em uma pasta para abrir  •  Duplo clique em um arquivo para escolher só ele",
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

# Icon shown in the Type column for files (landscape/horizontal glyph).
FILE_ICON = "🖼"

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

# Parenthesis / brace look-alikes (e.g. U+2768/2769, U+207D/207E, U+FE59/FE5A,
# U+2985/2986) are deliberately NOT converted or flagged: Windows doesn't treat
# them as problems, so neither does this app. Fullwidth parentheses/braces
# (U+FF08/FF09, U+FF5B/FF5D, U+FF5F/FF60) are also excluded from the fullwidth
# block below for the same reason.
_STYLED_KEEP = frozenset('\uFF08\uFF09\uFF3B\uFF3D\uFF5B\uFF5D\uFF5F\uFF60')
for _ch in _STYLED_KEEP:
    _STYLED_TO_ASCII.pop(_ch, None)


def normalize_styled(name: str) -> tuple[str, bool]:
    """Replace bold/italic/styled unicode chars with plain ASCII equivalents."""
    result = [_STYLED_TO_ASCII.get(c, c) for c in name]
    normalized = ''.join(result)
    return normalized, (normalized != name)


# ── Parenthesis / bracket look-alikes are NEVER touched ──────────────────────
# Listed as explicit code-point ranges (not via unicodedata) so Windows, Linux
# and every Python version behave identically. Characters in these ranges are
# neither treated as emojis nor stripped as "problem" symbols.
_PAREN_LIKE_RANGES = [
    (0x2045, 0x2046), (0x207D, 0x207E), (0x208D, 0x208E),
    (0x2329, 0x232A), (0x239B, 0x23AD), (0x23B0, 0x23B1), (0x23DC, 0x23E1),
    (0x2474, 0x2487), (0x249C, 0x24B5),          # parenthesized digits/letters
    (0x2768, 0x2775), (0x27E6, 0x27EF), (0x2983, 0x2998),
    (0x2E22, 0x2E29), (0x3200, 0x3243),
    (0xFE59, 0xFE5E), (0xFF08, 0xFF09), (0xFF3B, 0xFF3B), (0xFF3D, 0xFF3D),
    (0xFF5B, 0xFF5B), (0xFF5D, 0xFF5D), (0xFF5F, 0xFF60),
    (0x1F110, 0x1F12A), (0x1F240, 0x1F248),
]


def _is_paren_like(char: str) -> bool:
    cp = ord(char)
    for start, end in _PAREN_LIKE_RANGES:
        if start <= cp <= end:
            return True
    return False


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
    if _is_paren_like(char):
        return False
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
    if _is_paren_like(char):
        return False
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

def _same_entry(a: str, b: str) -> bool:
    """True if a and b are the very same filesystem entry (e.g. case-only change
    on a case-insensitive filesystem, or trailing dots/spaces Windows ignores)."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def get_unique_path(directory: str, new_name: str, ext: str,
                    ignore: str | None = None) -> str:
    """
    Return a free path for new_name+ext inside directory.
    `ignore` is the item being renamed: if the target 'exists' only because it
    is that same item, it is not a collision.
    """
    def taken(path: str) -> bool:
        if not os.path.lexists(path):
            return False
        return not (ignore is not None and _same_entry(path, ignore))

    base = os.path.join(directory, new_name + ext)
    if not taken(base):
        return base
    counter = 1
    while counter < 100_000:
        candidate = os.path.join(directory, f"{new_name}_{counter}{ext}")
        if not taken(candidate):
            return candidate
        counter += 1
    raise RuntimeError(f"Could not find a unique name for '{new_name}{ext}'")


def safe_rename(src_path: Path, new_stem: str, ext: str) -> str:
    """
    Rename a file or folder IN PLACE (os.rename = a move, never a copy), then
    verify that the old name is really gone and the new one really exists.
    """
    src = str(src_path)
    if not os.path.lexists(src):
        raise FileNotFoundError(f"Source no longer exists: {src_path}")

    dest = get_unique_path(str(src_path.parent), new_stem, ext, ignore=src)
    if dest != src:
        try:
            os.rename(src, dest)
        except FileExistsError:
            dest = get_unique_path(str(src_path.parent), new_stem + "_r", ext,
                                   ignore=src)
            os.rename(src, dest)

    # Verification: never report success unless the rename really happened.
    if not os.path.lexists(dest):
        raise OSError(f"Rename did not take effect (new name missing): {dest}")
    if dest != src and os.path.lexists(src) and not _same_entry(src, dest):
        raise OSError(f"Old name still exists after rename: {src}")
    return dest


# ── Duplicate-folder detection + trash ─────────────────────────────────────────

def _file_index(folder: str):
    """
    {cleaned relative path: [sizes]} for every FILE under `folder`. Each path
    component goes through clean_name(), so an emoji-named copy lines up with
    its already-clean twin whether or not its children were renamed yet.
    Only names and sizes are read, never contents. Symlinks aren't followed.
    Returns None if the folder can't be fully listed.
    """
    index: dict[str, list[int]] = {}
    try:
        for dirpath, _dirs, files in os.walk(folder, followlinks=False):
            rel_dir = os.path.relpath(dirpath, folder)
            parts = [] if rel_dir == "." else [clean_name(x)[0] for x in rel_dir.split(os.sep)]
            for f in files:
                stem, ext = os.path.splitext(f)
                key = "/".join(parts + [clean_name(stem)[0] + ext])
                index.setdefault(key, []).append(os.lstat(os.path.join(dirpath, f)).st_size)
    except OSError:
        return None
    return index


def find_missing_files(src: str, target: str):
    """
    Compare folder `src` (the emoji-named one) with its clean-named twin `target`.

    Returns None if `target` isn't a different, real folder (nothing to merge).
    Otherwise returns the files of `src` that do NOT already exist in `target`
    (same cleaned relative path AND same size) as a list of
    (absolute path in src, cleaned relative path). An empty list means `src` is
    completely redundant: every file in it is already in `target`.
    """
    if not (os.path.isdir(target) and not os.path.islink(target)):
        return None
    if _same_entry(src, target):
        return None
    tgt = _file_index(target)
    if tgt is None:
        return None
    missing = []
    try:
        for dirpath, _dirs, files in os.walk(src, followlinks=False):
            rel_dir = os.path.relpath(dirpath, src)
            parts = [] if rel_dir == "." else [clean_name(x)[0] for x in rel_dir.split(os.sep)]
            for f in files:
                full = os.path.join(dirpath, f)
                stem, ext = os.path.splitext(f)
                key = "/".join(parts + [clean_name(stem)[0] + ext])
                if os.lstat(full).st_size not in tgt.get(key, []):
                    missing.append((full, key))
    except OSError:
        return None
    return missing


def merge_missing_files(missing, target: str) -> int:
    """
    Move files that exist only in the emoji-named folder into the clean-named
    one (a move on the same drive, never a copy, never an overwrite: if a
    different file already has that name the moved one gets a _1 suffix).
    Returns how many files were moved.
    """
    moved = 0
    for full, key in missing:
        parts = key.split("/")
        dest_dir = os.path.join(target, *parts[:-1])
        os.makedirs(dest_dir, exist_ok=True)
        stem, ext = os.path.splitext(parts[-1])
        dest = get_unique_path(dest_dir, stem, ext)
        os.rename(full, dest)
        if os.path.lexists(full) or not os.path.lexists(dest):
            raise OSError(f"Could not move {full} -> {dest}")
        moved += 1
    return moved


def is_duplicate_file(src: str, target: str) -> bool:
    """
    True if `src` (emoji-named) is a leftover copy of `target` (its clean-named
    twin): `target` is a different, regular file with the same size AND the same
    bytes. The contents are only read to confirm the two are identical (never
    modified); a file that merely shares a name is never treated as a duplicate.
    """
    try:
        if (os.path.islink(src) or os.path.islink(target)
                or not os.path.isfile(src) or not os.path.isfile(target)):
            return False
        if _same_entry(src, target):
            return False
        if os.path.getsize(src) != os.path.getsize(target):
            return False
        return filecmp.cmp(src, target, shallow=False)
    except OSError:
        return False


def move_to_trash(path: str) -> None:
    """Send a file/folder to the OS trash (recoverable). Raises OSError on failure."""
    path = os.path.abspath(path)

    if PLATFORM == "win32":
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                        ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                        ("fFlags", ctypes.c_uint), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p),
                        ("lpszProgressTitle", wintypes.LPCWSTR)]

        FO_DELETE = 3
        FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 0x4, 0x10, 0x40, 0x400
        FOF_WANTNUKEWARNING = 0x4000   # still ask if it would be deleted for good, not recycled
        op = SHFILEOPSTRUCTW()
        op.wFunc = FO_DELETE
        op.pFrom = path + "\0"            # list must be double-null terminated
        op.fFlags = (FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
                     | FOF_NOERRORUI | FOF_WANTNUKEWARNING)
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if (rc != 0 or op.fAnyOperationsAborted) and os.path.lexists(path):
            # Second attempt through .NET (same Recycle Bin, different code path)
            env = dict(os.environ, ERZ_TRASH_PATH=path)
            ps = ("Add-Type -AssemblyName Microsoft.VisualBasic;"
                  "$p=$env:ERZ_TRASH_PATH;"
                  "if (Test-Path -LiteralPath $p -PathType Container) {"
                  "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p,"
                  "'OnlyErrorDialogs','SendToRecycleBin')} else {"
                  "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($p,"
                  "'OnlyErrorDialogs','SendToRecycleBin')}")
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                               capture_output=True, text=True, env=env,
                               creationflags=0x08000000)  # CREATE_NO_WINDOW
            if r.returncode != 0 and os.path.lexists(path):
                raise OSError(f"Windows could not move to Recycle Bin "
                              f"(shell code 0x{rc:X}; PowerShell: {r.stderr.strip()[:200]})")

    elif PLATFORM == "darwin":
        script = f'tell application "Finder" to delete POSIX file "{path}"'
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if r.returncode != 0:
            raise OSError(r.stderr.strip() or "Finder could not move to Trash")

    else:
        done = False
        for cmd in (["gio", "trash", path],
                    ["kioclient6", "move", path, "trash:/"],
                    ["kioclient5", "move", path, "trash:/"]):
            if shutil.which(cmd[0]):
                r = subprocess.run(cmd, capture_output=True, text=True)
                if r.returncode == 0 and not os.path.lexists(path):
                    done = True
                    break
        if not done:
            # Freedesktop.org trash spec, home trash (works without gio/kio)
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "Trash"
            files_dir, info_dir = base / "files", base / "info"
            files_dir.mkdir(parents=True, exist_ok=True)
            info_dir.mkdir(parents=True, exist_ok=True)
            name = os.path.basename(path)
            cand, n = name, 1
            while (files_dir / cand).exists() or (info_dir / (cand + ".trashinfo")).exists():
                n += 1
                cand = f"{name}.{n}"
            info = ("[Trash Info]\nPath=" + quote(path) + "\nDeletionDate="
                    + datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + "\n")
            (info_dir / (cand + ".trashinfo")).write_text(info, encoding="utf-8")
            try:
                shutil.move(path, str(files_dir / cand))
            except Exception:
                (info_dir / (cand + ".trashinfo")).unlink(missing_ok=True)
                raise

    if os.path.lexists(path):
        raise OSError(f"Folder is still there after moving to trash: {path}")


# ── Folder scanner ─────────────────────────────────────────────────────────────

def scan_folder(folder, recursive: bool,
                cancel_event: threading.Event,
                out_queue: queue.Queue,
                picked_files: "list[str] | None" = None) -> None:
    """
    Phase 1 — walk and collect all supported files and folders, emitting __count__ per item.
    Phase 2 — check each name, emitting __item__ (match) or __progress__ (no match).
    Ends with None sentinel.
    """
    root_path = Path(folder) if picked_files is None else None
    all_items: list[tuple[Path, str]] = []  # (path, 'file' or 'folder')

    # "Browse files" mode: only the files the user picked are checked —
    # nothing is walked and no folders are involved.
    if picked_files is not None:
        for f in picked_files:
            if cancel_event.is_set():
                out_queue.put(None)
                return
            if os.path.isfile(f):
                all_items.append((Path(f), 'file'))
                out_queue.put(("__count__", len(all_items)))

    try:
        for dirpath, dirs, files in (os.walk(str(root_path))
                                     if root_path is not None else ()):
            if cancel_event.is_set():
                out_queue.put(None)
                return
            # Collect folders first (folders are always renamed too)
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


# ── Source = what gets scanned: one folder, or a hand-picked set of files ──────
# {"kind": "folder" | "files", "paths": [...]}

HISTORY_MAX       = 20     # remembered locations in the dropdown
HISTORY_MAX_PATHS = 300    # bigger file picks still work, just aren't remembered


def make_source(kind: str, paths) -> dict:
    return {"kind": kind,
            "paths": [os.path.normpath(os.path.expanduser(p)) for p in paths]}


def source_key(src: dict) -> tuple:
    return (src["kind"], tuple(os.path.normcase(p) for p in src["paths"]))


def source_valid(src) -> bool:
    if not src or not src.get("paths"):
        return False
    if src["kind"] == "folder":
        return os.path.isdir(src["paths"][0])
    return any(os.path.isfile(p) for p in src["paths"])


def source_dir(src: dict) -> str:
    """The folder a source lives in (the folder itself, or the files' parent)."""
    paths = src["paths"]
    if src["kind"] == "folder":
        return paths[0]
    try:
        return os.path.commonpath([os.path.dirname(p) for p in paths])
    except ValueError:                 # files on different Windows drives
        return os.path.dirname(paths[0])


def native_linux_dialog(kind: str, title: str, start: str):
    """Open the desktop's own file/folder chooser (KDE Plasma's dialog via
    kdialog, GNOME/GTK's via zenity) instead of Tk's dated built-in one.

    kind: "folder" or "files" (multi-select).
    Returns a list of chosen paths ([] if the user cancelled), or None when no
    native chooser is installed / usable, so the caller can fall back to Tk."""
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP", "") + " " +
               os.environ.get("DESKTOP_SESSION", "")).upper()
    order = (["kdialog", "zenity"] if ("KDE" in desktop or "PLASMA" in desktop)
             else ["zenity", "kdialog"])
    start_dir = start.rstrip("/") + "/"
    for tool in order:
        exe = shutil.which(tool)
        if not exe:
            continue
        if tool == "kdialog":
            cmd = [exe, "--title", title]
            if kind == "folder":
                cmd += ["--getexistingdirectory", start_dir]
            else:
                cmd += ["--multiple", "--separate-output",
                        "--getopenfilename", start_dir]
        else:
            cmd = [exe, "--file-selection", f"--title={title}",
                   f"--filename={start_dir}"]
            if kind == "folder":
                cmd.append("--directory")
            else:
                cmd += ["--multiple", "--separator=\n"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True)
        except OSError:
            continue
        if r.returncode == 0:
            return [ln.rstrip("\r") for ln in r.stdout.split("\n") if ln.strip()]
        if r.returncode == 1:          # user pressed Cancel / closed it
            return []
        # any other exit code: this tool is unusable here, try the next one
    return None


class ThumbPicker(tk.Toplevel):
    """Thumbnail-grid multi-file picker (Linux "Browse files").

    A gallery-style browser instead of a list/tree dialog: every file is a
    tile with a preview, folders open on double-click, clicking a tile ticks
    it. Thumbnails come from the desktop's own thumbnail cache
    (~/.cache/thumbnails, filled by Dolphin / Nautilus) and, when Pillow is
    installed, straight from the image files. Without either, a type icon is
    shown instead. Tiles are drawn on demand, so huge folders stay fast.

    show() returns the list of chosen file paths ([] if cancelled)."""

    SIZES = (("S", 96), ("M", 144), ("L", 208))
    _pil_mod = False          # False = not tried yet, None = not installed
    _EXT_ICONS = (
        (("jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff", "avif",
          "heic", "heif", "svg", "ico", "jxl"), "🖼"),
        (("mp4", "mkv", "webm", "avi", "mov", "wmv", "flv", "m4v"), "🎞"),
        (("mp3", "flac", "wav", "ogg", "opus", "m4a", "aac"), "🎵"),
        (("zip", "rar", "7z", "tar", "gz", "xz", "bz2", "zst"), "🗜"),
    )

    def __init__(self, parent, title, start, recent, colors, t):
        super().__init__(parent)
        self.withdraw()
        try:
            self._init(parent, title, start, recent, colors, t)
        except Exception:
            try:
                self.destroy()
            except Exception:
                pass
            raise

    # ── construction ─────────────────────────────────────────────────────────

    def _init(self, parent, title, start, recent, colors, t):
        self._col, self._tr = colors, t
        self.title(title)
        self.configure(bg=colors["BG"])
        self.transient(parent)
        self.minsize(680, 440)
        pw, ph = 980, 660
        try:
            x = parent.winfo_rootx() + max(0, (parent.winfo_width() - pw) // 2)
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - ph) // 2)
            self.geometry(f"{pw}x{ph}+{x}+{y}")
        except tk.TclError:
            self.geometry(f"{pw}x{ph}")

        self.result: list = []
        self._sel: dict = {}            # ticked paths, in tick order
        self._entries: list = []        # (name, path, is_dir) of the open folder
        self._cwd = ""
        self._error = False
        self._size = 144
        self._gen = 0                   # bumps on every folder change
        self._thumbs: dict = {}         # (path, size) -> PhotoImage | None
        self._requested: set = set()
        self._reqq = queue.LifoQueue()  # newest request (= on screen) first
        self._resq = queue.Queue()
        self._redraw_job = None
        self._poll_job = None
        self._last_idx = None
        self._tw = self._th = 1
        self._cols, self._rows, self._x0 = 1, 0, 0
        self._places: list = []
        self._hidden = tk.BooleanVar(value=False)
        self._path_var = tk.StringVar()

        self._build(recent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Return>", self._on_return)
        self.bind("<BackSpace>", self._on_backspace)
        self.bind("<Control-a>", self._on_ctrl_a)

        threading.Thread(target=self._thumb_worker, daemon=True).start()
        self._poll_job = self.after(40, self._poll)
        self._go(start)

    def _btn(self, parent, text, cmd, accent=False, small=False):
        c = self._col
        return tk.Button(parent, text=text, command=cmd,
                         font=("Segoe UI", 8 if small else 9, "bold"),
                         bg=c["ACCENT"] if accent else c["BORDER"],
                         fg="#fff" if accent else c["FG"],
                         activebackground=c["ACCENT2"] if accent else c["ACCENT"],
                         activeforeground="#fff", relief="flat",
                         padx=8 if small else 14, pady=4 if small else 6,
                         cursor="hand2", bd=0,
                         disabledforeground=c["DISABLED_FG"])

    def _build(self, recent):
        c = self._col
        BG, CARD, BORDER, ACCENT = c["BG"], c["CARD"], c["BORDER"], c["ACCENT"]

        # toolbar: up, path, thumbnail size, hidden files
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=14, pady=(12, 8))
        self._btn(bar, self._tr("tp_up"), self._up).pack(side="left")
        self._path_entry = tk.Entry(
            bar, textvariable=self._path_var, font=("Consolas", 10),
            bg=c["ENTRY_BG"], fg=c["FG"], insertbackground=ACCENT,
            relief="flat", bd=6, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT)
        self._path_entry.pack(side="left", fill="x", expand=True, padx=8, ipady=3)
        self._size_btns = {}
        for label, px in self.SIZES:
            b = self._btn(bar, label, lambda px=px: self._set_size(px), small=True)
            b.pack(side="left", padx=(2, 0))
            self._size_btns[px] = b
        ttk.Checkbutton(bar, text=self._tr("tp_hidden"), variable=self._hidden,
                        command=self._reload, style="TCheckbutton"
                        ).pack(side="left", padx=(12, 0))
        self._mark_size()

        # body: places sidebar + thumbnail grid
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=14)
        side = tk.Frame(body, bg=CARD, highlightthickness=1,
                        highlightbackground=BORDER)
        side.pack(side="left", fill="y", padx=(0, 8))
        self._plist = tk.Listbox(
            side, width=26, bg=CARD, fg=c["FG"], selectbackground=c["SEL_BG"],
            selectforeground=c["FG"], highlightthickness=0, bd=0,
            activestyle="none", exportselection=False, font=("Segoe UI", 9))
        self._plist.pack(fill="both", expand=True, padx=4, pady=6)
        self._fill_places(recent)
        self._plist.bind("<<ListboxSelect>>", self._on_place)

        main = tk.Frame(body, bg=CARD, highlightthickness=1,
                        highlightbackground=BORDER)
        main.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(main, bg=CARD, highlightthickness=0, bd=0,
                                yscrollincrement=48)
        vsb = ttk.Scrollbar(main, orient="vertical", command=self.canvas.yview,
                            style="Vertical.TScrollbar")
        self.canvas.configure(
            yscrollcommand=lambda a, b: (vsb.set(a, b), self._schedule_redraw()))
        vsb.pack(side="right", fill="y", padx=(0, 4), pady=4)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._relayout())
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.canvas.bind("<Button-4>", self._wheel)
        self.canvas.bind("<Button-5>", self._wheel)
        self.canvas.bind("<MouseWheel>", self._wheel)

        tk.Label(self, text=self._tr("tp_hint"), font=("Segoe UI", 8), bg=BG,
                 fg=c["HINT"], anchor="w").pack(fill="x", padx=16, pady=(6, 0))
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=14, pady=(6, 12))
        self._status = tk.Label(foot, text="", font=("Segoe UI", 9), bg=BG,
                                fg=c["MUTED"])
        self._status.pack(side="left")
        self._ok_btn = self._btn(foot, self._tr("tp_select"), self._accept,
                                 accent=True)
        self._ok_btn.pack(side="right")
        self._btn(foot, self._tr("tp_cancel"), self._cancel).pack(
            side="right", padx=(0, 8))
        self._btn(foot, self._tr("tp_none"), self._clear, small=True).pack(
            side="right", padx=(0, 14))
        self._btn(foot, self._tr("tp_all"), self._select_all, small=True).pack(
            side="right", padx=(0, 6))
        self._update_status()

    # ── places sidebar ───────────────────────────────────────────────────────

    @staticmethod
    def _xdg_dirs() -> dict:
        out = {}
        try:
            cfg = os.path.join(os.environ.get("XDG_CONFIG_HOME")
                               or os.path.expanduser("~/.config"),
                               "user-dirs.dirs")
            with open(cfg, encoding="utf-8") as f:
                for line in f:
                    m = re.match(r'XDG_(\w+)_DIR="(.*)"', line.strip())
                    if m:
                        out[m.group(1)] = m.group(2).replace(
                            "$HOME", os.path.expanduser("~"))
        except OSError:
            pass
        return out

    def _fill_places(self, recent):
        home = os.path.expanduser("~")
        user = os.path.basename(home)
        xdg = self._xdg_dirs()
        items = [(self._tr("tp_places"), None),
                 ("🏠  " + self._tr("tp_home"), home)]
        for key, fallback in (("DESKTOP", "Desktop"), ("DOCUMENTS", "Documents"),
                              ("DOWNLOAD", "Downloads"), ("PICTURES", "Pictures"),
                              ("VIDEOS", "Videos"), ("MUSIC", "Music")):
            p = xdg.get(key) or os.path.join(home, fallback)
            if os.path.isdir(p) and os.path.normpath(p) != os.path.normpath(home):
                items.append(("📁  " + os.path.basename(p.rstrip("/")), p))
        seen = set()
        for base in (f"/run/media/{user}", f"/media/{user}", "/media", "/mnt"):
            try:
                names = sorted(os.listdir(base))
            except OSError:
                continue
            for n in names:
                p = os.path.join(base, n)
                if n.startswith(".") or p in seen or not os.path.isdir(p):
                    continue
                seen.add(p)
                items.append(("💽  " + n, p))
        items.append(("🖥  " + self._tr("tp_root"), "/"))
        if recent:
            items.append((self._tr("tp_recent"), None))
            for d in recent:
                short = ("~" + d[len(home):]
                         if d == home or d.startswith(home + os.sep) else d)
                items.append(("🕘  " + short, d))
        self._places = [p for _l, p in items]
        for i, (label, p) in enumerate(items):
            self._plist.insert("end", label)
            if p is None:                       # section header
                self._plist.itemconfig(i, fg=self._col["MUTED"],
                                       selectbackground=self._col["CARD"],
                                       selectforeground=self._col["MUTED"])

    def _on_place(self, _e=None):
        sel = self._plist.curselection()
        if sel and self._places[sel[0]]:
            self._go(self._places[sel[0]])

    # ── navigation / listing ─────────────────────────────────────────────────

    def _go(self, path):
        self._cwd = os.path.abspath(os.path.expanduser(path))
        self._path_var.set(self._cwd)
        self._gen += 1
        self._requested.clear()
        self._last_idx = None
        self._read_dir()
        self.canvas.yview_moveto(0)
        self._relayout()

    def _reload(self):
        self._last_idx = None
        self._read_dir()
        self._relayout()

    def _up(self):
        parent = os.path.dirname(self._cwd.rstrip(os.sep)) or os.sep
        if parent != self._cwd:
            self._go(parent)

    def _read_dir(self):
        dirs, files = [], []
        self._error = False
        try:
            with os.scandir(self._cwd) as it:
                for e in it:
                    if e.name.startswith(".") and not self._hidden.get():
                        continue
                    try:
                        isd = e.is_dir()
                    except OSError:
                        isd = False
                    (dirs if isd else files).append((e.name, e.path, isd))
        except OSError:
            self._error = True

        def natural(item):
            parts = re.split(r"(\d+)", item[0].casefold())
            return [int(p) if i % 2 else p for i, p in enumerate(parts)]
        dirs.sort(key=natural)
        files.sort(key=natural)
        self._entries = dirs + files

    # ── drawing (virtualised: only the visible rows exist as canvas items) ───

    def _relayout(self):
        cv = self.canvas
        w, h = max(cv.winfo_width(), 200), max(cv.winfo_height(), 100)
        s = self._size
        self._tw, self._th = s + 28, s + 58
        self._cols = max(1, w // self._tw)
        self._rows = -(-len(self._entries) // self._cols)
        self._x0 = max(0, (w - self._cols * self._tw) // 2)
        cv.configure(scrollregion=(0, 0, w, max(h, self._rows * self._th + 12)))
        self._schedule_redraw()

    def _schedule_redraw(self):
        if self._redraw_job is None:
            self._redraw_job = self.after_idle(self._redraw)

    def _redraw(self):
        self._redraw_job = None
        cv, c = self.canvas, self._col
        cv.delete("all")
        n = len(self._entries)
        if n == 0:
            cv.create_text(cv.winfo_width() // 2, 80, fill=c["MUTED"],
                           font=("Segoe UI", 11),
                           text=self._tr("tp_unreadable" if self._error
                                         else "tp_empty"))
            return
        top, h = cv.canvasy(0), cv.winfo_height()
        r0 = max(0, int(top // self._th) - 1)
        r1 = min(self._rows, int((top + h) // self._th) + 2)
        for r in range(r0, r1):
            for col in range(self._cols):
                i = r * self._cols + col
                if i >= n:
                    break
                self._draw_tile(i, self._x0 + col * self._tw, 6 + r * self._th)

    def _glyph(self, name: str) -> str:
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        for exts, icon in self._EXT_ICONS:
            if ext in exts:
                return icon
        return "📄"

    def _draw_tile(self, i, x, y):
        cv, c, s = self.canvas, self._col, self._size
        name, path, is_dir = self._entries[i]
        sel = path in self._sel
        cx, cy = x + self._tw // 2, y + 8 + s // 2
        if sel:
            cv.create_rectangle(x + 2, y, x + self._tw - 2, y + self._th - 6,
                                fill=c["SEL_BG"], outline=c["ACCENT"], width=2)
        img = None
        if not is_dir:
            key = (path, s)
            if key in self._thumbs:
                img = self._thumbs[key]
            elif key not in self._requested:
                self._requested.add(key)
                self._reqq.put((self._gen, path, s))
        if img is not None:
            cv.create_image(cx, cy, image=img)
        else:
            cv.create_text(cx, cy, text="📁" if is_dir else self._glyph(name),
                           fill=c["ACCENT2"] if is_dir else c["MUTED"],
                           font=("Segoe UI", max(18, int(s * 0.34))))
        per_line = max(8, int((self._tw - 8) / 6.5))
        short = name if len(name) <= per_line * 2 else name[:per_line * 2 - 1] + "…"
        cv.create_text(cx, y + s + 14, text=short, width=self._tw - 8,
                       anchor="n", justify="center", fill=c["FG"],
                       font=("Segoe UI", 8))
        if sel:
            cv.create_oval(x + self._tw - 26, y + 4, x + self._tw - 6, y + 24,
                           fill=c["ACCENT"], outline="")
            cv.create_text(x + self._tw - 16, y + 14, text="✓", fill="#fff",
                           font=("Segoe UI", 9, "bold"))

    # ── mouse / keyboard ─────────────────────────────────────────────────────

    def _index_at(self, e):
        x, y = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        col, row = int((x - self._x0) // self._tw), int((y - 6) // self._th)
        if col < 0 or col >= self._cols or row < 0:
            return None
        i = row * self._cols + col
        return i if i < len(self._entries) else None

    def _on_click(self, e):
        self.canvas.focus_set()
        i = self._index_at(e)
        if i is None:
            return
        _name, path, is_dir = self._entries[i]
        if is_dir:
            return                      # folders open on double-click
        if (e.state & 0x1) and self._last_idx is not None:     # Shift = range
            lo, hi = sorted((self._last_idx, i))
            for j in range(lo, hi + 1):
                if not self._entries[j][2]:
                    self._sel.setdefault(self._entries[j][1])
        elif path in self._sel:
            del self._sel[path]
        else:
            self._sel[path] = None
        self._last_idx = i
        self._update_status()
        self._schedule_redraw()

    def _on_double(self, e):
        i = self._index_at(e)
        if i is None:
            return
        _name, path, is_dir = self._entries[i]
        if is_dir:
            self._go(path)
        else:
            self._sel.setdefault(path)
            if len(self._sel) == 1:     # nothing else ticked: pick just this one
                self._accept()
            else:
                self._update_status()
                self._schedule_redraw()

    def _wheel(self, e):
        up = e.num == 4 or getattr(e, "delta", 0) > 0
        self.canvas.yview_scroll(-3 if up else 3, "units")

    def _on_return(self, _e):
        if self.focus_get() is self._path_entry:
            p = os.path.expanduser(self._path_var.get().strip())
            if os.path.isdir(p):
                self._go(p)
                self.canvas.focus_set()
            return
        self._accept()

    def _on_backspace(self, _e):
        if self.focus_get() is not self._path_entry:
            self._up()

    def _on_ctrl_a(self, _e):
        if self.focus_get() is not self._path_entry:
            self._select_all()

    # ── selection / size ─────────────────────────────────────────────────────

    def _select_all(self):
        for _n, p, d in self._entries:
            if not d:
                self._sel.setdefault(p)
        self._update_status()
        self._schedule_redraw()

    def _clear(self):
        self._sel.clear()
        self._update_status()
        self._schedule_redraw()

    def _update_status(self):
        n = len(self._sel)
        self._status.config(text=self._tr("tp_selected", n=n) if n else "")
        self._ok_btn.config(state="normal" if n else "disabled")

    def _mark_size(self):
        for px, b in self._size_btns.items():
            b.config(bg=self._col["ACCENT"] if px == self._size
                     else self._col["BORDER"],
                     fg="#fff" if px == self._size else self._col["FG"])

    def _set_size(self, px):
        self._size = px
        self._mark_size()
        self._relayout()

    # ── thumbnails (worker thread makes PNG bytes; Tk objects stay on main) ──

    @classmethod
    def _pil(cls):
        if cls._pil_mod is False:
            try:
                from PIL import Image, ImageOps
                cls._pil_mod = (Image, ImageOps)
            except Exception:
                cls._pil_mod = None
        return cls._pil_mod

    @staticmethod
    def _cached_thumb(path: str, size: int):
        """Path of the desktop's own cached thumbnail (freedesktop spec)."""
        try:
            uri = "file://" + quote(os.path.abspath(path), safe="/")
            name = hashlib.md5(uri.encode("utf-8")).hexdigest() + ".png"
            base = (os.environ.get("XDG_CACHE_HOME")
                    or os.path.expanduser("~/.cache"))
            kinds = (("normal", "large", "x-large", "xx-large") if size <= 128
                     else ("large", "x-large", "xx-large", "normal"))
            mtime = os.path.getmtime(path)
            for k in kinds:
                p = os.path.join(base, "thumbnails", k, name)
                if os.path.isfile(p) and os.path.getmtime(p) >= mtime:
                    return p
        except OSError:
            pass
        return None

    def _make_thumb(self, path: str, size: int):
        if not os.path.isfile(path):
            return None
        cache = self._cached_thumb(path, size)
        pil = self._pil()
        if pil:
            Image, ImageOps = pil
            cands = ([cache] if cache else [])
            try:
                if os.path.getsize(path) <= 128 * 1024 * 1024:
                    cands.append(path)
            except OSError:
                pass
            for cand in cands:
                try:
                    im = Image.open(cand)
                    try:
                        im.draft("RGB", (size * 2, size * 2))   # fast JPEG decode
                    except Exception:
                        pass
                    if cand == path:
                        im = ImageOps.exif_transpose(im)
                    im.thumbnail((size, size))
                    if im.mode not in ("L", "LA", "P", "RGB", "RGBA"):
                        im = im.convert("RGBA")
                    buf = io.BytesIO()
                    im.save(buf, "PNG")
                    return ("png", buf.getvalue())
                except Exception:
                    continue
            return None
        if cache:
            with open(cache, "rb") as f:
                return ("png", f.read())
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext in ("png", "gif") and os.path.getsize(path) <= 1_500_000:
            return ("file", path)       # Tk can read these natively
        return None

    def _thumb_worker(self):
        while True:
            item = self._reqq.get()
            if item is None:
                return
            gen, path, size = item
            if gen != self._gen:        # folder changed since it was queued
                continue
            try:
                res = self._make_thumb(path, size)
            except Exception:
                res = None
            self._resq.put((gen, path, size, res))

    def _to_photo(self, res, size):
        kind, data = res
        try:
            if kind == "png":
                img = tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))
            else:
                img = tk.PhotoImage(file=data)
            f = -(-max(img.width(), img.height()) // size)     # ceil
            return img.subsample(f) if f > 1 else img
        except tk.TclError:
            return None

    def _poll(self):
        changed = False
        try:
            for _ in range(10):
                gen, path, size, res = self._resq.get_nowait()
                if gen != self._gen:
                    continue
                if len(self._thumbs) > 1500:
                    self._thumbs.clear()
                    self._requested.clear()
                self._thumbs[(path, size)] = self._to_photo(res, size) if res else None
                changed = True
        except queue.Empty:
            pass
        if changed:
            self._schedule_redraw()
        self._poll_job = self.after(40, self._poll)

    # ── finish ───────────────────────────────────────────────────────────────

    def _accept(self):
        if self._sel:
            self.result = list(self._sel)
            self._close()

    def _cancel(self):
        self.result = []
        self._close()

    def _close(self):
        for attr in ("_redraw_job", "_poll_job"):
            job = getattr(self, attr, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
                setattr(self, attr, None)
        self._reqq.put(None)
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def show(self):
        try:
            self.deiconify()
            try:
                self.wait_visibility()
                self.grab_set()
            except tk.TclError:
                pass
            self.canvas.focus_set()
            self.wait_window(self)
        finally:
            try:
                if self.winfo_exists():
                    self._close()
            except tk.TclError:
                pass
        return self.result


# ── Application ────────────────────────────────────────────────────────────────

class App(tk.Tk):
    _BATCH_SIZE = 100
    _POLL_MS    = 50
    # Loading screens stay up at least this long, so a fast scan shows a clear
    # "Loading…" instead of a one-frame flash. Set to 0 to disable.
    _MIN_LOADING_MS = 700

    def __init__(self):
        super().__init__(className="Emoji_Remover_Z")
        # Stay invisible until the loading screen is ready, so no half-drawn
        # window (empty buttons, default colours) ever flashes on screen.
        self.withdraw()

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

        # Previously used folders / file picks (dropdown), newest first. The
        # most recent one is what gets resumed at startup.
        self._history = self._load_history()
        self._source = None
        if self._history:
            self._source = self._history[0]
        elif self.settings.get("last_folder", ""):
            self._source = make_source("folder", [self.settings.get("last_folder")])
        self._dialog_open = False
        self._shown_label = self._source_label(self._source) if self._source else ""
        self.folder_var    = tk.StringVar(value=self._shown_label)
        self.recursive_var = tk.BooleanVar(value=self.settings.get_bool("recursive", False))

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
        self._renaming     = False
        self._scan_folder  = ""

        # Rows the user un-ticked, remembered across runs (full paths)
        self._unchecked: set[str] = self._load_unchecked()
        self._unchecked_job = None

        # Loading overlay / spinner state
        self._loading_visible = False
        self._loading_since   = 0.0
        self._hide_job        = None
        self._boot            = None      # full-window startup loading screen
        self._boot_since      = 0.0
        self._boot_job        = None
        self._spin_job        = None
        self._spin_angle      = 0

        self.configure(bg=self._c("BG"))

        # 1) Show ONLY a loading screen first (nothing else is built yet, so no
        #    blank buttons can appear)...
        self._create_boot_screen()
        self.deiconify()
        self.update()
        # 2) ...build the real UI behind it, then put the loading screen on top
        #    (widgets created later sit above older ones until lifted).
        self._build_ui()
        self._boot.lift()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 3) Resume the previously used folder (read from the .ini). The loading
        #    screen goes away when that scan is done.
        if source_valid(self._source):
            self._scan()
        else:
            self._end_boot()

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
        self._cancel_after("_hide_job")
        self._cancel_after("_boot_job")
        self._stop_spinner()
        self._flush_unchecked()
        src = self._resolve_source()
        if src and src["kind"] == "folder":
            self.settings.set("last_folder", src["paths"][0])
        self.destroy()
        _cleanup_pycache()

    # ── Remembered un-ticked rows ────────────────────────────────────────────────

    def _load_unchecked(self) -> set:
        try:
            data = json.loads(self.settings.get("unchecked", "[]") or "[]")
            return {x for x in data if isinstance(x, str)}
        except Exception:
            return set()

    def _flush_unchecked(self):
        if self._unchecked_job is not None:
            try:
                self.after_cancel(self._unchecked_job)
            except Exception:
                pass
            self._unchecked_job = None
        self.settings.set("unchecked",
                          json.dumps(sorted(self._unchecked), ensure_ascii=False))

    def _queue_unchecked_save(self):
        """Debounced write so ticking many rows doesn't hammer the disk."""
        if self._unchecked_job is not None:
            try:
                self.after_cancel(self._unchecked_job)
            except Exception:
                pass
        self._unchecked_job = self.after(500, self._flush_unchecked)

    def _sync_unchecked(self):
        """Re-sync the remembered set with every row currently in the table."""
        for item, checked in zip(self._preview_data, self._checked):
            key = str(item[0])
            if checked:
                self._unchecked.discard(key)
            else:
                self._unchecked.add(key)
        self._queue_unchecked_save()

    def _prune_unchecked(self):
        """Forget un-ticked entries under the scanned folder that no longer exist."""
        if not self._scan_folder:
            return
        prefix = os.path.normpath(self._scan_folder).rstrip(os.sep) + os.sep
        stale = {k for k in self._unchecked
                 if k.startswith(prefix) and not os.path.lexists(k)}
        if stale:
            self._unchecked -= stale
            self._queue_unchecked_save()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._actions_visible = False
        self._prog_visible    = False
        self._loading_visible = False

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
        ENTRY_BG = self._c("ENTRY_BG")
        style.configure("Z.TCombobox",
                        fieldbackground=ENTRY_BG, background=BORDER,
                        foreground=FG, arrowcolor=MUTED,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        insertcolor=ACCENT, padding=6)
        style.map("Z.TCombobox",
                  fieldbackground=[("readonly", ENTRY_BG)],
                  foreground=[("readonly", FG)],
                  background=[("active", BORDER), ("pressed", BORDER)],
                  arrowcolor=[("active", ACCENT)],
                  selectbackground=[("!focus", ENTRY_BG)],
                  selectforeground=[("!focus", FG)])
        # The dropdown list itself is a plain Tk listbox -> themed via options.
        self.option_add("*TCombobox*Listbox.background", ENTRY_BG)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", self._c("SEL_BG"))
        self.option_add("*TCombobox*Listbox.selectForeground", FG)
        self.option_add("*TCombobox*Listbox.font", ("Consolas", 10))

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
        # Editable dropdown: type/paste a path, or pick a previously used
        # folder / file selection (remembered in the .ini).
        self.path_combo = ttk.Combobox(
            row, textvariable=self.folder_var, style="Z.TCombobox",
            font=("Consolas", 10),
            values=[self._source_label(h) for h in self._history])
        self.path_combo.pack(side="left", fill="x", expand=True, ipady=4)
        self.path_combo.bind("<<ComboboxSelected>>", self._on_history_pick)
        self.path_combo.bind("<Return>", lambda _e: self._scan())
        btn_kw = dict(font=("Segoe UI", 9, "bold"),
                      bg=BORDER, fg=FG, activebackground=ACCENT,
                      activeforeground="#fff", relief="flat",
                      padx=14, pady=6, cursor="hand2", bd=0)
        self.browse_folder_btn = tk.Button(
            row, text=self._t("browse_folder"),
            command=lambda: self._pick("folder"), **btn_kw)
        self.browse_folder_btn.pack(side="left", padx=(8, 0))
        self.browse_files_btn = tk.Button(
            row, text=self._t("browse_files"),
            command=lambda: self._pick("files"), **btn_kw)
        self.browse_files_btn.pack(side="left", padx=(6, 0))
        opt_row = tk.Frame(picker, bg=CARD)
        opt_row.pack(fill="x", padx=14, pady=(0, 12))
        self.recursive_chk = ttk.Checkbutton(opt_row,
                        text=self._t("recursive"),
                        variable=self.recursive_var,
                        command=self._on_recursive_toggle,
                        style="TCheckbutton")
        self.recursive_chk.pack(side="left")

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
        # rename / select-all / deselect-all stay hidden until there are results
        # (see _set_actions_visible) so no dead buttons show while loading.

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
        hdr_row.configure(height=26)      # fixed height: no jump when buttons appear
        hdr_row.pack_propagate(False)
        self.table_label = tk.Label(hdr_row,
                                    text=self._t("preview_default"),
                                    font=("Consolas", 8, "bold"),
                                    bg=CARD, fg=MUTED, anchor="w")
        self.table_label.pack(side="left")

        self.table_hint_lbl = tk.Label(hdr_row,
                 text=self._t("table_hint"),
                 font=("Segoe UI", 7), bg=CARD, fg=self._c("HINT"), anchor="w")
        self.table_hint_lbl.pack(side="left", padx=(12, 0))

        self.deselect_all_btn = tk.Button(hdr_row, text=self._t("deselect_all"),
                  command=self._deselect_all,
                  font=("Segoe UI", 8),
                  bg=BORDER, fg=MUTED,
                  activebackground="#3a3a50", activeforeground=FG,
                  relief="flat", padx=8, pady=2,
                  cursor="hand2", bd=0)
        self.select_all_btn = tk.Button(hdr_row, text=self._t("select_all"),
                  command=self._select_all,
                  font=("Segoe UI", 8),
                  bg=BORDER, fg=MUTED,
                  activebackground="#3a3a50", activeforeground=FG,
                  relief="flat", padx=8, pady=2,
                  cursor="hand2", bd=0)

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

        # ── Loading overlay (covers the table card while scanning/renaming) ──
        self.loading_frame = tk.Frame(tbl_frame, bg=CARD)
        box = tk.Frame(self.loading_frame, bg=CARD)
        box.place(relx=0.5, rely=0.5, anchor="center")
        self.spinner, self._spinner_arc = self._make_spinner(box, CARD)
        self.spinner.pack()
        self.loading_title_lbl = tk.Label(box, text=self._t("loading_title"),
                                          font=("Segoe UI", 13, "bold"),
                                          bg=CARD, fg=FG)
        self.loading_title_lbl.pack(pady=(12, 2))
        self.loading_detail_lbl = tk.Label(box, text="", font=("Segoe UI", 9),
                                           bg=CARD, fg=MUTED)
        self.loading_detail_lbl.pack()

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

    def _rebuild_ui(self):
        """Tear down and rebuild the UI in place after a theme/language change,
        preserving any in-progress scan results and folder selection."""
        preview_snapshot = list(self._preview_data)
        checked_snapshot  = list(self._checked)
        folder_value      = self.folder_var.get()

        self._cancel_after("_hide_job")
        self._cancel_after("_boot_job")
        self._stop_spinner()
        self._boot = None
        for child in list(self.winfo_children()):
            child.destroy()

        self.folder_var.set(folder_value)
        self._row_ids = []
        self.configure(bg=self._c("BG"))
        self._build_ui()
        # A multi-file label contains translated text -> regenerate it.
        if self._source and self.folder_var.get() == self._shown_label:
            self._show_source()

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
                    ext_display, kind_display = ext.lstrip('.'), FILE_ICON
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

        # A scan/rename may still be running: bring back its busy interface
        if self._scan_active or self._renaming:
            self.scan_btn.config(state="disabled")
            self._show_progress(True)
            self._show_loading(True, "renaming_title" if self._renaming else "loading_title")
            if self._scan_active:
                self.cancel_btn.pack(side="left", padx=(10, 0))

    # ── Source (folder / picked files) + history ───────────────────────────────

    def _source_label(self, src: dict) -> str:
        """Text shown in the dropdown. A folder or a single file is just its
        path (so it can be edited/copied); a multi-file pick is summarised."""
        paths = src["paths"]
        if src["kind"] == "folder" or len(paths) == 1:
            return paths[0]
        names = ", ".join(os.path.basename(p) for p in paths[:3])
        more = ", …" if len(paths) > 3 else ""
        return (f"[{self._t('files_n', n=len(paths))}]  "
                f"{source_dir(src)}{os.sep}  ›  {names}{more}")

    def _show_source(self):
        self._shown_label = self._source_label(self._source)
        self.folder_var.set(self._shown_label)

    def _resolve_source(self):
        """What the dropdown currently means: the remembered source it shows,
        or whatever folder / file path was typed or pasted. None if invalid."""
        text = self.folder_var.get().strip()
        if self._source and text == self._shown_label:
            return self._source
        text = text.strip('"').strip("'")
        if not text:
            return None
        p = os.path.expanduser(text)
        if os.path.isdir(p):
            return make_source("folder", [p])
        if os.path.isfile(p):
            return make_source("files", [p])
        return None

    def _load_history(self) -> list:
        try:
            data = json.loads(self.settings.get("history", "[]") or "[]")
        except Exception:
            return []
        out = []
        for d in data if isinstance(data, list) else []:
            if (isinstance(d, dict) and d.get("kind") in ("folder", "files")
                    and isinstance(d.get("paths"), list)):
                paths = [p for p in d["paths"] if isinstance(p, str) and p]
                if paths:
                    out.append({"kind": d["kind"], "paths": paths})
        return out[:HISTORY_MAX]

    def _remember(self, src: dict):
        """Put a source at the top of the history (de-duplicated) -> .ini."""
        if len(src["paths"]) > HISTORY_MAX_PATHS:
            return
        key = source_key(src)
        self._history = [h for h in self._history if source_key(h) != key]
        self._history.insert(0, src)
        del self._history[HISTORY_MAX:]
        self.settings.set("history", json.dumps(self._history, ensure_ascii=False))
        try:
            self.path_combo["values"] = [self._source_label(h) for h in self._history]
        except tk.TclError:
            pass

    def _on_history_pick(self, _event=None):
        i = self.path_combo.current()
        if 0 <= i < len(self._history):
            self._source = self._history[i]
            self._show_source()
            self._scan()

    # ── Browse: one button for a folder, one for files ───────────────────────

    def _start_dir(self) -> str:
        """Where the chooser opens: the current / last used location."""
        cands = []
        cur = self._resolve_source()
        if cur:
            cands.append(source_dir(cur))
        cands += [source_dir(h) for h in self._history]
        for c in cands:
            while c and not os.path.isdir(c):
                parent = os.path.dirname(c)
                if parent == c:
                    break
                c = parent
            if c and os.path.isdir(c):
                return c
        return os.path.expanduser("~")

    def _pick(self, kind: str):
        if self._dialog_open:
            return
        title = self._t("select_folder_title" if kind == "folder"
                        else "select_files_title")
        start = self._start_dir()
        self._dialog_open = True
        if kind == "files" and PLATFORM.startswith("linux"):
            # Built-in thumbnail-grid browser instead of a list/tree dialog.
            recent = []
            for h in self._history:
                d = source_dir(h)
                if d not in recent and os.path.isdir(d):
                    recent.append(d)
            try:
                res = ThumbPicker(self, title, start, recent[:8],
                                  THEMES.get(self.theme, THEMES["dark"]),
                                  self._t).show()
            except Exception:
                res = None              # fall through to the desktop's chooser
            if res is not None:
                self._pick_done(kind, title, start, res)
                return
        if PLATFORM.startswith("linux"):
            # The desktop's own chooser runs as a separate process; wait for
            # it off the UI thread so the window stays responsive.
            def worker():
                try:
                    res = native_linux_dialog(kind, title, start)
                except Exception:
                    res = None
                try:
                    self.after(0, self._pick_done, kind, title, start, res)
                except Exception:
                    pass                # window was closed meanwhile
            threading.Thread(target=worker, daemon=True).start()
        else:
            self._pick_done(kind, title, start, None)

    def _pick_done(self, kind: str, title: str, start: str, res):
        try:
            if res is None:
                # Windows / macOS (native Tk dialogs) or no kdialog/zenity on Linux
                if kind == "folder":
                    p = filedialog.askdirectory(title=title, initialdir=start)
                    res = [p] if p else []
                else:
                    res = filedialog.askopenfilenames(title=title, initialdir=start)
                    if isinstance(res, str):
                        res = self.tk.splitlist(res)
                    res = list(res)
        finally:
            self._dialog_open = False
        if not res:
            return
        self._source = make_source(kind, res)
        self._show_source()
        self._scan()

    # ── Checkbox helpers ───────────────────────────────────────────────────────

    def _toggle_check(self, iid: str):
        """Flip the checked state of one preview row (green square <-> empty)."""
        if iid not in self._row_ids:
            return
        idx = self._row_ids.index(iid)
        self._checked[idx] = not self._checked[idx]
        key = str(self._preview_data[idx][0])
        if self._checked[idx]:
            self._unchecked.discard(key)
        else:
            self._unchecked.add(key)
        self._queue_unchecked_save()
        self._refresh_row(idx)
        self._update_rename_btn()

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
        if not iid or iid not in self._row_ids:
            return
        if col == "#1":
            # A quick second click on the checkbox must toggle again, not be lost
            self._toggle_check(iid)
        elif col != "#2":
            # double-click on non-original column also opens folder
            self._open_file_location(iid)

    def _open_file_location(self, iid: str):
        """Open the file's folder with the file selected/highlighted."""
        idx = self._row_ids.index(iid)
        p = self._preview_data[idx][0]
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
        p = self._preview_data[idx][0]
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
                               "📁" if item_type == 'folder' else FILE_ICON),
                       tags=("checked" if checked else "unchecked",))

    def _select_all(self):
        self._checked = [True] * len(self._checked)
        for i in range(len(self._row_ids)):
            self._refresh_row(i)
        self._sync_unchecked()
        self._update_rename_btn()

    def _deselect_all(self):
        self._checked = [False] * len(self._checked)
        for i in range(len(self._row_ids)):
            self._refresh_row(i)
        self._sync_unchecked()
        self._update_rename_btn()

    def _set_actions_visible(self, visible: bool):
        """Show/hide Rename + Select All + Deselect All together."""
        if visible == self._actions_visible:
            return
        if visible:
            # "before=" keeps the original pack order, so these claim their
            # space first instead of being squeezed out by the long hint text.
            self.rename_btn.pack(side="left", padx=(10, 0), before=self.status_lbl)
            self.deselect_all_btn.pack(side="right", padx=(4, 0), before=self.table_label)
            self.select_all_btn.pack(side="right", padx=(0, 4), before=self.table_label)
        else:
            for w in (self.rename_btn, self.deselect_all_btn, self.select_all_btn):
                w.pack_forget()
        self._actions_visible = visible

    def _update_rename_btn(self):
        n = sum(self._checked)
        self._set_actions_visible(bool(self._checked)
                                  and not self._scan_active
                                  and not self._renaming)
        if n > 0:
            self.rename_btn.config(
                state="normal",
                text=self._t("rename_n", n=n, s="s" if n != 1 else ""))
        else:
            self.rename_btn.config(state="disabled", text=self._t("rename_selected"))

    # ── Scan ───────────────────────────────────────────────────────────────────

    def _scan(self):
        src = self._resolve_source()
        if not source_valid(src):
            messagebox.showwarning(self._t("no_folder_title"), self._t("no_folder_msg"))
            return

        self._source = src
        self._show_source()
        self._remember(src)
        folder = source_dir(src)
        if src["kind"] == "folder":
            self.settings.set("last_folder", folder)
        self._scan_folder = folder

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
        self._scan_active = True
        self._set_actions_visible(False)
        self._show_loading(True, "loading_title")
        self._set_status(self._t("status_counting"))
        self.scan_btn.config(state="disabled")
        self.rename_btn.config(state="disabled", text=self._t("rename_selected"))
        self.cancel_btn.pack(side="left", padx=(10, 0))
        self.progress["value"] = 0
        self._show_progress(True)
        self._scan_active = True

        threading.Thread(
            target=self._scan_worker,
            args=(src, self.recursive_var.get()),
            daemon=True
        ).start()
        self.after(self._POLL_MS, self._poll_scan_queue)

    def _scan_worker(self, src: dict, recursive: bool):
        try:
            if src["kind"] == "files":
                scan_folder(None, False, self._cancel_event, self._scan_queue,
                            picked_files=src["paths"])
            else:
                scan_folder(src["paths"][0], recursive,
                            self._cancel_event, self._scan_queue)
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
            checked = str(p) not in self._unchecked
            self._checked.append(checked)
            if item_type == 'folder':
                display_old = old_stem
                display_new = new_stem
                ext_display = ""
                kind_display = "📁"
            else:
                display_old = old_stem + ext
                display_new = new_stem + ext
                ext_display = ext.lstrip('.')
                kind_display = FILE_ICON
            iid = self.tree.insert("", "end",
                                   values=((CHECK_ON if checked else CHECK_OFF),
                                           display_old, display_new,
                                           ext_display, kind_display),
                                   tags=("checked" if checked else "unchecked",))
            self._row_ids.append(iid)
            self._found_total += 1
        self._set_status(self._t("status_found_n", n=self._found_total))
        self._update_rename_btn()

    def _finish_scan(self, remaining_batch, error=None):
        self._scan_active = False
        self.progress["value"] = 100
        self._show_progress(False)
        self._show_loading(False)
        self.cancel_btn.pack_forget()
        self.scan_btn.config(state="normal")

        if remaining_batch:
            self._insert_rows(remaining_batch)
        self._update_rename_btn()

        if error:
            messagebox.showerror(self._t("scan_error_title"), self._t("scan_error_msg", e=error))
            self._set_status(self._t("status_scan_error"))
            return

        count     = self._found_total
        cancelled = self._cancel_event.is_set()
        if not cancelled:
            self._prune_unchecked()
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
        # An emoji-named item whose clean twin already exists is a leftover
        # duplicate: folders are merged into the twin, identical files are
        # dropped; either way the leftover goes to the trash (recoverable).
        def _twin_exists(p, new, ext, item_type):
            t = os.path.join(str(p.parent), new + ext)
            check = os.path.isdir if item_type == 'folder' else os.path.isfile
            return check(t) and not _same_entry(str(p), t)
        has_dupes = any(_twin_exists(p, new, ext, it)
                        for p, _old, new, ext, it in snapshot)
        if not messagebox.askyesno(
                self._t("confirm_rename_title"),
                self._t("confirm_rename_msg", n=count, s="s" if count != 1 else "")
                + (self._t("confirm_trash_note") if has_dupes else ""),
                icon="question"):
            return

        self._renaming = True
        self._set_actions_visible(False)
        self.rename_btn.config(state="disabled")
        self.scan_btn.config(state="disabled")
        self._show_loading(True, "renaming_title")
        self._set_status(self._t("status_renaming_n", done=0, total=count))
        self.progress["value"] = 0
        self._show_progress(True)

        threading.Thread(target=self._rename_worker,
                         args=(snapshot,), daemon=True).start()

    def _rename_worker(self, snapshot):
        ok      = 0
        trashed = 0
        trashed_files = 0
        merged  = 0
        errors  = []
        # Rename the DEEPEST items first. Renaming a parent folder changes the
        # path of everything inside it, so children must be handled while their
        # stored paths are still valid; parents are renamed last.
        snapshot = sorted(snapshot, key=lambda it: len(it[0].parts), reverse=True)
        total  = len(snapshot)
        for i, (p, old_stem, new_stem, ext, item_type) in enumerate(snapshot):
            try:
                target = os.path.join(str(p.parent), new_stem + ext)
                missing = (find_missing_files(str(p), target)
                           if item_type == 'folder' else None)
                if item_type == 'file' and is_duplicate_file(str(p), target):
                    # Identical clean-named file already exists: this emoji-named
                    # one is a leftover duplicate -> trash it (recoverable).
                    move_to_trash(str(p))
                    trashed_files += 1
                elif missing is not None:
                    # The clean-named folder already exists, so this one is a
                    # duplicate. Move across anything that only exists here,
                    # then send the (now fully redundant) folder to the trash.
                    try:
                        merged += merge_missing_files(missing, target)
                        if find_missing_files(str(p), target):
                            raise OSError("it still has files that are not in the clean folder")
                        move_to_trash(str(p))
                    except Exception as e:
                        raise OSError(f"could not merge/trash duplicate: {e}")
                    trashed += 1
                else:
                    safe_rename(p, new_stem, ext)   # in-place rename + verification
                    ok += 1
            except Exception as e:
                errors.append((p.name, str(e)))
            pct = (i + 1) * 100 / total
            self.after(0, self._set_rename_progress, pct, i + 1, total)
        self.after(0, self._finish_rename, ok, errors, trashed, merged, trashed_files)

    def _set_rename_progress(self, pct: float, done: int, total: int):
        self.progress["value"] = pct
        self._set_status(self._t("status_renaming_n", done=done, total=total))

    def _finish_rename(self, ok: int, errors: list, trashed: int = 0, merged: int = 0,
                       trashed_files: int = 0):
        self._renaming = False
        self._show_loading(False)
        self._set_actions_visible(False)
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
                        lines=err_lines)
                + (("\n\n" + self._t("done_trashed", t=trashed, ts="s" if trashed != 1 else ""))
                   if trashed else "")
                + (("\n\n" + self._t("done_trashed_files", t=trashed_files,
                                      ts="s" if trashed_files != 1 else ""))
                   if trashed_files else "")
                + (("\n\n" + self._t("done_merged", m=merged, ms="s" if merged != 1 else ""))
                   if merged else ""))
            self._set_status(self._t("status_done_errors", n=ok, e=len(errors)))
        else:
            self._set_status(self._t("status_done", n=ok, s="s" if ok != 1 else ""))
            parts = []
            if ok or not (trashed or trashed_files):
                parts.append(self._t("done_msg", n=ok, s="s" if ok != 1 else ""))
            if trashed:
                parts.append(self._t("done_trashed", t=trashed, ts="s" if trashed != 1 else ""))
            if trashed_files:
                parts.append(self._t("done_trashed_files", t=trashed_files,
                                     ts="s" if trashed_files != 1 else ""))
            if merged:
                parts.append(self._t("done_merged", m=merged, ms="s" if merged != 1 else ""))
            messagebox.showinfo(self._t("done_title"), "\n\n".join(parts))

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
        if self._loading_visible:
            self.loading_detail_lbl.config(text=text)
        if self._boot is not None:
            try:
                self._boot_detail.config(text=text)
            except tk.TclError:
                pass

    # ── Loading overlay / startup screen ───────────────────────────────────────

    def _make_spinner(self, parent, bg):
        cv = tk.Canvas(parent, width=56, height=56, bg=bg,
                       highlightthickness=0, bd=0)
        cv.create_oval(6, 6, 50, 50, outline=self._c("BORDER"), width=5)
        arc = cv.create_arc(6, 6, 50, 50, start=90, extent=100, style="arc",
                            outline=self._c("ACCENT"), width=5)
        return cv, arc

    def _create_boot_screen(self):
        """Full-window loading screen shown the moment the app starts."""
        BG = self._c("BG")
        f = tk.Frame(self, bg=BG)
        f.place(x=0, y=0, relwidth=1, relheight=1)
        box = tk.Frame(f, bg=BG)
        box.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(box, text="✦ EMOJI REMOVER Z", font=("Courier New", 18, "bold"),
                 bg=BG, fg=self._c("ACCENT")).pack(pady=(0, 18))
        self._boot_cv, self._boot_arc = self._make_spinner(box, BG)
        self._boot_cv.pack()
        tk.Label(box, text=self._t("loading_title"), font=("Segoe UI", 13, "bold"),
                 bg=BG, fg=self._c("FG")).pack(pady=(12, 2))
        self._boot_detail = tk.Label(box, text="", font=("Segoe UI", 9),
                                     bg=BG, fg=self._c("MUTED"))
        self._boot_detail.pack()
        self._boot = f
        self._boot_since = time.monotonic()
        self._ensure_spinner()

    def _end_boot(self):
        """Remove the startup screen (after the minimum display time)."""
        if self._boot is None:
            return
        remain = self._MIN_LOADING_MS - (time.monotonic() - self._boot_since) * 1000
        if remain > 0:
            self._cancel_after("_boot_job")
            self._boot_job = self.after(int(remain) + 1, self._end_boot)
            return
        self._boot_job = None
        try:
            self._boot.destroy()
        except tk.TclError:
            pass
        self._boot = None
        self._release_spinner()

    def _cancel_after(self, attr: str):
        job = getattr(self, attr, None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
            setattr(self, attr, None)

    def _show_loading(self, visible: bool, title_key: str = "loading_title"):
        if visible:
            self._cancel_after("_hide_job")
            self.loading_title_lbl.config(text=self._t(title_key))
            if not self._loading_visible:
                self.loading_frame.place(x=0, y=0, relwidth=1, relheight=1)
                self.loading_frame.lift()
                self._loading_visible = True
                self._loading_since = time.monotonic()
                self._ensure_spinner()
        else:
            if self._loading_visible:
                remain = self._MIN_LOADING_MS - (time.monotonic() - self._loading_since) * 1000
                if remain > 0:
                    self._cancel_after("_hide_job")
                    self._hide_job = self.after(int(remain) + 1, self._hide_loading_now)
                else:
                    self._hide_loading_now()
            self._end_boot()

    def _hide_loading_now(self):
        self._hide_job = None
        if self._loading_visible:
            try:
                self.loading_frame.place_forget()
            except tk.TclError:
                pass
            self._loading_visible = False
        self._release_spinner()

    def _spin_targets(self):
        targets = []
        if self._boot is not None:
            targets.append((self._boot_cv, self._boot_arc))
        if self._loading_visible:
            targets.append((self.spinner, self._spinner_arc))
        return targets

    def _spin(self):
        targets = self._spin_targets()
        if not targets:
            self._spin_job = None
            return
        self._spin_angle = (self._spin_angle - 14) % 360
        for cv, arc in targets:
            try:
                cv.itemconfigure(arc, start=self._spin_angle)
            except tk.TclError:
                pass
        self._spin_job = self.after(30, self._spin)

    def _ensure_spinner(self):
        if self._spin_job is None:
            self._spin()

    def _release_spinner(self):
        """Stop the animation once no loading screen is visible any more."""
        if not self._spin_targets():
            self._stop_spinner()

    def _stop_spinner(self):
        if self._spin_job is not None:
            try:
                self.after_cancel(self._spin_job)
            except Exception:
                pass
            self._spin_job = None



def _inspect_folder(folder: str) -> None:
    """Command line helper:  python emoji-remover-z.py --inspect "/some/folder"
    Lists every non-letter, non-ASCII character used in the names inside the
    folder (subfolders included), and whether this app would change it."""
    if not os.path.isdir(folder):
        print(f"Not a folder: {folder}")
        return
    found: dict[str, list] = {}
    names = 0
    for dirpath, dirs, files in os.walk(folder):
        for n in dirs + files:
            names += 1
            for c in n:
                if c.isascii():
                    continue
                cat = unicodedata.category(c)
                if cat[0] == "L" or cat == "Nd":
                    continue          # ordinary letters / digits (accents, kana, CJK…)
                rec = found.setdefault(c, [0, n])
                rec[0] += 1
    print(f"Python {sys.version.split()[0]}  |  Unicode data {unicodedata.unidata_version}"
          f"  |  platform {PLATFORM}")
    print(f"Scanned {names} names in {ascii(folder)}\n")
    if not found:
        print("No unusual characters found.")
        return
    for c, (count, example) in sorted(found.items(), key=lambda kv: ord(kv[0])):
        handled = clean_name(f"a{c}b")[1]
        print(f"U+{ord(c):04X}  {unicodedata.category(c)}  {unicodedata.name(c, '?'):<42} "
              f"x{count:<4} {'WILL be changed' if handled else 'ignored'}   e.g. {ascii(example)}")


if __name__ == "__main__":
    if "--inspect" in sys.argv:
        _i = sys.argv.index("--inspect")
        _inspect_folder(sys.argv[_i + 1] if len(sys.argv) > _i + 1 else ".")
        sys.exit(0)
    atexit.register(_cleanup_pycache)
    app = App()
    app.mainloop()
