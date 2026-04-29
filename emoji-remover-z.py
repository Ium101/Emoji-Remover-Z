import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import os
import re
import unicodedata
from pathlib import Path
import threading
import queue
import sys

PLATFORM = sys.platform  # 'win32', 'darwin', 'linux'

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
    (0x2400, 0x24FF),  # Enclosed Alphanumerics
    (0x2500, 0x257F),  # Box Drawing
    (0x2580, 0x259F),  # Block Elements
    (0x25A0, 0x25FF),  # Geometric Shapes
    (0x2600, 0x26FF),  # Miscellaneous Symbols (already in emoji ranges)
    (0x2700, 0x27BF),  # Dingbats (already in emoji ranges)
    (0x2900, 0x297F),  # Supplemental Arrows
    (0x2B00, 0x2BFF),  # Miscellaneous Symbols and Arrows
]

def _is_extra_strip(char: str) -> bool:
    cp = ord(char)
    for start, end in _EXTRA_STRIP_RANGES:
        if start <= cp <= end:
            return True
    return False


def sanitize_for_filesystem(name: str) -> tuple[str, bool]:
    """
    Remove characters that are forbidden or problematic in filenames.
    Only reports was_changed=True if a character was actually removed/replaced.
    Does NOT normalise whitespace unless a removal created adjacent spaces.
    """
    result = []
    actually_changed = False
    for c in name:
        if c in _WIN_FORBIDDEN:
            result.append(' ')
            actually_changed = True
            continue
        cp = ord(c)
        if cp < 32:
            actually_changed = True
            continue
        if _is_extra_strip(c) and not c.isalnum() and c not in ' _-()[]{}.,!@#%^&+=~`\'':
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

def scan_folder(folder: str, recursive: bool,
                cancel_event: threading.Event,
                out_queue: queue.Queue) -> None:
    """
    Phase 1 — walk and collect all supported files, emitting __count__ per file.
    Phase 2 — check each name, emitting __item__ (match) or __progress__ (no match).
    Ends with None sentinel.
    """
    root_path = Path(folder)
    all_files: list[Path] = []

    try:
        for dirpath, dirs, files in os.walk(str(root_path)):
            if cancel_event.is_set():
                out_queue.put(None)
                return
            for fname in files:
                try:
                    p = Path(dirpath) / fname
                    all_files.append(p)
                    out_queue.put(("__count__", len(all_files)))
                except (PermissionError, OSError):
                    continue
            if not recursive:
                dirs.clear()
    except (PermissionError, OSError):
        pass

    total = len(all_files)
    out_queue.put(("__total__", total))

    for i, p in enumerate(all_files):
        if cancel_event.is_set():
            break
        try:
            cleaned, changed = clean_name(p.stem)
            if changed:
                out_queue.put(("__item__", (p, p.stem, cleaned, p.suffix), i + 1, total))
            else:
                out_queue.put(("__progress__", i + 1, total))
        except (PermissionError, OSError):
            out_queue.put(("__progress__", i + 1, total))

    out_queue.put(None)


# ── GUI constants ──────────────────────────────────────────────────────────────

CHECK_ON  = "☑"
CHECK_OFF = "☐"

BG      = "#0f0f13"
CARD    = "#18181f"
BORDER  = "#2a2a35"
ACCENT  = "#ff6b35"
ACCENT2 = "#ff9f1c"
FG      = "#e8e8f0"
MUTED   = "#7a7a90"
GREEN   = "#3ddc84"


# ── Application ────────────────────────────────────────────────────────────────

class App(tk.Tk):
    _BATCH_SIZE = 100
    _POLL_MS    = 50

    def __init__(self):
        super().__init__()
        self.title("Emoji Remover Z")
        self.geometry("960x660")
        self.minsize(720, 500)
        self.configure(bg=BG)
        self.resizable(True, True)

        self.folder_var    = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=False)

        # Scan state — all parallel lists indexed by row
        self._preview_data: list[tuple] = []   # (Path, old_stem, new_stem, ext)
        self._row_ids:      list[str]   = []   # treeview iid
        self._checked:      list[bool]  = []   # True = will be renamed

        self._scan_queue   = queue.Queue()
        self._cancel_event = threading.Event()
        self._scan_active  = False
        self._found_total  = 0
        self._scan_total   = 0
        self._prog_visible = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self._cancel_event.set()
        self.destroy()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
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
                  background=[("selected", "#2a2a45")],
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
        tk.Label(hdr, text="strip emojis & styled text from any filename",
                 font=("Segoe UI", 10), bg=BG, fg=MUTED).pack(side="left", padx=14, pady=4)

        # ── Folder picker ─────────────────────────────────────────────────────
        picker = tk.Frame(self, bg=CARD, bd=0,
                          highlightthickness=1, highlightbackground=BORDER)
        picker.pack(fill="x", padx=28, pady=(0, 12))
        tk.Label(picker, text="FOLDER", font=("Consolas", 8, "bold"),
                 bg=CARD, fg=MUTED).pack(anchor="w", padx=14, pady=(10, 2))
        row = tk.Frame(picker, bg=CARD)
        row.pack(fill="x", padx=14, pady=(0, 12))
        self.path_entry = tk.Entry(row, textvariable=self.folder_var,
                                   font=("Consolas", 10), bg="#0f0f13",
                                   fg=FG, insertbackground=ACCENT,
                                   relief="flat", bd=8,
                                   highlightthickness=1,
                                   highlightbackground=BORDER,
                                   highlightcolor=ACCENT)
        self.path_entry.pack(side="left", fill="x", expand=True, ipady=6)
        tk.Button(row, text="Browse", command=self._browse,
                  font=("Segoe UI", 9, "bold"),
                  bg=BORDER, fg=FG, activebackground=ACCENT,
                  activeforeground="#fff", relief="flat",
                  padx=16, pady=6, cursor="hand2", bd=0).pack(side="left", padx=(8, 0))
        opt_row = tk.Frame(picker, bg=CARD)
        opt_row.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Checkbutton(opt_row,
                        text="Include subfolders (recursive)",
                        variable=self.recursive_var,
                        style="TCheckbutton").pack(side="left")

        # ── Action buttons ────────────────────────────────────────────────────
        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", padx=28, pady=(0, 4))

        self.scan_btn = tk.Button(btns, text="⟳  Scan",
                                  command=self._scan,
                                  font=("Segoe UI", 10, "bold"),
                                  bg=BORDER, fg=FG,
                                  activebackground="#3a3a50",
                                  relief="flat", padx=20, pady=8,
                                  cursor="hand2", bd=0)
        self.scan_btn.pack(side="left")

        self.cancel_btn = tk.Button(btns, text="✕  Cancel",
                                    command=self._cancel_scan,
                                    font=("Segoe UI", 10, "bold"),
                                    bg="#3a2020", fg="#ff6060",
                                    activebackground="#5a2020",
                                    activeforeground="#ff9090",
                                    relief="flat", padx=14, pady=8,
                                    cursor="hand2", bd=0)
        # shown only while scanning

        self.rename_btn = tk.Button(btns, text="✦  Rename Selected",
                                    command=self._rename,
                                    state="disabled",
                                    font=("Segoe UI", 10, "bold"),
                                    bg=ACCENT, fg="#fff",
                                    activebackground=ACCENT2,
                                    activeforeground="#fff",
                                    relief="flat", padx=20, pady=8,
                                    cursor="hand2", bd=0,
                                    disabledforeground="#7a5040")
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
                                    text="PREVIEW  —  files to be renamed",
                                    font=("Consolas", 8, "bold"),
                                    bg=CARD, fg=MUTED, anchor="w")
        self.table_label.pack(side="left")

        tk.Label(hdr_row,
                 text="Click a filename to open it  •  Right-click for more options  •  Only filenames are modified",
                 font=("Segoe UI", 7), bg=CARD, fg="#4a4a60").pack(side="left", padx=(12, 0))

        tk.Button(hdr_row, text="Deselect All",
                  command=self._deselect_all,
                  font=("Segoe UI", 8),
                  bg=BORDER, fg=MUTED,
                  activebackground="#3a3a50", activeforeground=FG,
                  relief="flat", padx=8, pady=2,
                  cursor="hand2", bd=0).pack(side="right", padx=(4, 0))
        tk.Button(hdr_row, text="Select All",
                  command=self._select_all,
                  font=("Segoe UI", 8),
                  bg=BORDER, fg=MUTED,
                  activebackground="#3a3a50", activeforeground=FG,
                  relief="flat", padx=8, pady=2,
                  cursor="hand2", bd=0).pack(side="right", padx=(0, 4))

        cols = ("check", "original", "renamed", "type")
        self.tree = ttk.Treeview(tbl_frame, columns=cols,
                                 show="headings", selectmode="browse")
        self.tree.heading("check",    text="")
        self.tree.heading("original", text="ORIGINAL FILENAME  (click → open file)")
        self.tree.heading("renamed",  text="CLEANED FILENAME")
        self.tree.heading("type",     text="EXT")
        self.tree.column("check",    width=32,  minwidth=32,  stretch=False, anchor="center")
        self.tree.column("original", width=340, minwidth=160)
        self.tree.column("renamed",  width=340, minwidth=160)
        self.tree.column("type",     width=55,  minwidth=45,  anchor="center")

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
        self._ctx_menu.add_command(label="📂  Open file location",
                                   command=self._ctx_open_location)
        self._ctx_menu.add_command(label="▶  Open file",
                                   command=self._ctx_open_file)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="☑  Toggle selection",
                                   command=self._ctx_toggle)
        self._ctx_iid: str | None = None
        self.tree.bind("<ButtonRelease-3>", self._on_tree_right_click)

        # ── Footer ────────────────────────────────────────────────────────────
        tk.Label(self,
                 text="Feito pelo Usuário Ium101 do GitHub  /  Made by User Ium101 from GitHub",
                 font=("Segoe UI", 8), bg=BG, fg="#3a3a50").pack(pady=(4, 10))

    # ── Browse ─────────────────────────────────────────────────────────────────

    def _browse(self):
        folder = filedialog.askdirectory(title="Select folder")
        if folder:
            self.folder_var.set(folder)

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
            messagebox.showwarning("Open location", f"Could not open folder:\n{e}")

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
            messagebox.showwarning("Open file", f"Could not open file:\n{e}")

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
        p, old_stem, new_stem, ext = self._preview_data[idx]
        self.tree.item(iid,
                       values=(CHECK_ON if checked else CHECK_OFF,
                               old_stem + ext,
                               new_stem + ext,
                               ext.lstrip('.')),
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
                text=f"✦  Rename {n} File{'s' if n != 1 else ''}")
        else:
            self.rename_btn.config(state="disabled", text="✦  Rename Selected")

    # ── Scan ───────────────────────────────────────────────────────────────────

    def _scan(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("No folder", "Please select a valid folder first.")
            return

        # Reset all state
        self._cancel_event.clear()
        self._preview_data.clear()
        self._row_ids.clear()
        self._checked.clear()
        self._found_total = 0
        self._scan_total  = 0
        self._scan_queue  = queue.Queue()

        self.tree.delete(*self.tree.get_children())
        self.table_label.config(text="PREVIEW  —  files to be renamed")
        self._set_status("Counting files…")
        self.scan_btn.config(state="disabled")
        self.rename_btn.config(state="disabled", text="✦  Rename Selected")
        self.cancel_btn.pack(side="left", padx=(10, 0))
        self.progress["value"] = 0
        self._show_progress(True)
        self._scan_active = True

        threading.Thread(
            target=self._scan_worker,
            args=(folder, self.recursive_var.get()),
            daemon=True
        ).start()
        self.after(self._POLL_MS, self._poll_scan_queue)

    def _scan_worker(self, folder: str, recursive: bool):
        try:
            scan_folder(folder, recursive, self._cancel_event, self._scan_queue)
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
                    self._set_status(f"Counting… {n} files found")
                elif tag == "__total__":
                    self._scan_total = msg[1]
                    self.progress["value"] = 40
                    self._set_status(f"Scanning {self._scan_total} files…")
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
            p, old_stem, new_stem, ext = item
            self._preview_data.append(item)
            self._checked.append(True)
            iid = self.tree.insert("", "end",
                                   values=(CHECK_ON, old_stem + ext,
                                           new_stem + ext, ext.lstrip('.')),
                                   tags=("checked",))
            self._row_ids.append(iid)
            self._found_total += 1
        self._set_status(f"Scanning… {self._found_total} found")
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
            messagebox.showerror("Scan error", f"An error occurred:\n{error}")
            self._set_status("Scan error")
            return

        count     = self._found_total
        cancelled = self._cancel_event.is_set()
        if count:
            suffix = " (cancelled)" if cancelled else ""
            self.table_label.config(
                text=f"PREVIEW  —  {count} file{'s' if count != 1 else ''} found"
                     "  (click row to toggle)")
            self._set_status(f"{count} file{'s' if count != 1 else ''} found{suffix}")
            self._update_rename_btn()
        else:
            self._set_status(
                "Cancelled — no files found" if cancelled else "No files to rename found")

    def _cancel_scan(self):
        self._cancel_event.set()
        self._set_status("Cancelling…")

    # ── Rename ─────────────────────────────────────────────────────────────────

    def _rename(self):
        snapshot = [(p, old, new, ext)
                    for (p, old, new, ext), checked
                    in zip(self._preview_data, self._checked)
                    if checked]
        if not snapshot:
            return

        count = len(snapshot)
        if not messagebox.askyesno(
                "Confirm rename",
                f"Rename {count} file{'s' if count != 1 else ''}?\n\n"
                "Only filenames will be changed.\n"
                "File contents are never read or modified.",
                icon="question"):
            return

        self.rename_btn.config(state="disabled")
        self.scan_btn.config(state="disabled")
        self._set_status("Renaming…")
        self.progress["value"] = 0
        self._show_progress(True)

        threading.Thread(target=self._rename_worker,
                         args=(snapshot,), daemon=True).start()

    def _rename_worker(self, snapshot):
        ok     = 0
        errors = []
        total  = len(snapshot)
        for i, (p, old_stem, new_stem, ext) in enumerate(snapshot):
            try:
                safe_rename(p, new_stem, ext)
                ok += 1
            except Exception as e:
                errors.append((p.name, str(e)))
            pct = (i + 1) * 100 / total
            self.after(0, self._set_rename_progress, pct, i + 1, total)
        self.after(0, self._finish_rename, ok, errors)

    def _set_rename_progress(self, pct: float, done: int, total: int):
        self.progress["value"] = pct
        self._set_status(f"Renaming… {done}/{total}")

    def _finish_rename(self, ok: int, errors: list):
        self._show_progress(False)
        self.scan_btn.config(state="normal")
        self.tree.delete(*self.tree.get_children())
        self._preview_data.clear()
        self._row_ids.clear()
        self._checked.clear()
        self._found_total = 0
        self.table_label.config(text="PREVIEW  —  files to be renamed")
        self.rename_btn.config(state="disabled", text="✦  Rename Selected")

        if errors:
            err_lines = "\n".join(f"• {n}: {m}" for n, m in errors[:50])
            if len(errors) > 50:
                err_lines += f"\n… and {len(errors) - 50} more."
            messagebox.showwarning(
                "Partial success",
                f"Renamed {ok} file{'s' if ok != 1 else ''} successfully.\n\n"
                f"{len(errors)} error{'s' if len(errors) != 1 else ''}:\n{err_lines}")
            self._set_status(f"Done — {ok} renamed, {len(errors)} error(s)")
        else:
            self._set_status(f"✓ {ok} file{'s' if ok != 1 else ''} renamed successfully")
            messagebox.showinfo(
                "Done",
                f"Successfully renamed {ok} file{'s' if ok != 1 else ''}.\n\n"
                "File contents were not modified.")

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
