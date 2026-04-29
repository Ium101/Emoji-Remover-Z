# ✦ Emoji Remover Z — v1.0

> First stable release.

## 📦 Download

| File | Description |
|---|---|
| `EmojiRemoverZ.exe` | Standalone Windows executable — no installation needed |
| `Source code (zip)` | Full source, includes `build.bat` to compile yourself |

---

## 🆕 What's in v1.0

### Core features
- **Emoji removal** from any filename — covers all Unicode emoji ranges (emoticons, symbols, flags, pictographs, and more)
- **Styled Unicode normalisation** — bold (`𝗛𝗲𝗹𝗹𝗼`), italic (`𝘏𝘦𝘭𝘭𝘰`), script (`𝓗𝓮𝓵𝓵𝓸`), fraktur, double-struck, fullwidth (`ｈｅｌｌｏ`), monospace, sans-serif variants all converted to plain ASCII
- **Works on every file type** — no extension whitelist; renames any file whose name needs cleaning
- **Recursive folder scanning** with opt-in checkbox

### Preview & control
- Live preview table showing original → cleaned name for every file found
- **Per-file checkboxes** — uncheck any row to exclude it from the rename; Select All / Deselect All
- Rename button updates live to show exactly how many files are selected

### Safety
- Only `os.rename()` is used — file contents are never read or modified
- Collision-safe: automatically appends `_1`, `_2`, … if the target name already exists
- Atomic rename on same filesystem; errors are caught per-file and reported without stopping the rest
- Files that are only emojis fall back to `file.ext` instead of becoming empty names

### UX
- **Real progress bar** — genuine percentage during both counting phase (0→40%) and scanning phase (40→100%), and per-file during rename
- **Cancel button** during scan — already-found files are kept in the preview
- **Click filename to open** the file with its default app; right-click for *Open file*, *Open file location* (Explorer with file selected), or *Toggle selection*
- Dark UI with green progress bar and colour-coded checked/unchecked rows

---

## 🖥 System Requirements

| Platform | Notes |
|---|---|
| **Windows 10/11** | Fully supported; `.exe` is self-contained |
| **macOS 12+** | Fully supported; uses `open` / `open -R` for Finder integration |
| **Linux** | Fully supported; requires `xdg-open` and `python3-tk` (`sudo apt install python3-tk`) |

No runtime dependencies — the binary is fully self-contained.

---

## 🏗 Build from Source

**Windows** — requires Python 3.14:
```bat
build.bat
```

**Linux / macOS** — auto-detects Python 3.14, 3.12, or system Python 3:
```bash
chmod +x build.sh && ./build.sh
```

Or manually on any platform:
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name EmojiRemoverZ emoji-remover-z.py
```

---

<p align="center">
  Feito pelo Usuário Ium101 do GitHub &nbsp;/&nbsp; Made by User Ium101 from GitHub
</p>
