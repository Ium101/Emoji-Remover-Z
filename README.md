# ✦ Emoji Remover Z

> **Strip emojis and styled Unicode text from any filename — safely, visually, in bulk.**

A Windows desktop app built in Python. Scans any folder for files with emoji characters or styled Unicode (bold, italic, script, fullwidth…) in their names, previews every rename before it happens, and lets you opt out individual files with a single click. File contents are **never** touched — only the filename changes.

---

## ✨ Features

- 🔍 **Scans any file type** — not just images or videos, works on every file extension
- 🧹 **Removes emojis** from filenames (🎉🔥🌴🎬 and thousands more)
- 🔤 **Normalises styled Unicode** — converts bold, italic, script, fraktur, fullwidth, double-struck, monospace and sans-serif characters back to plain ASCII (`𝗛𝗲𝗹𝗹𝗼` → `Hello`)
- ☑ **Per-file opt-out** — uncheck any file in the preview list to skip it; Select All / Deselect All buttons included
- 👁 **Live preview** — see exactly what every file will be renamed to before confirming
- 📊 **Real progress bar** — shows genuine percentage while counting and scanning (not a fake spinner)
- 📂 **Click to open** — left-click any filename in the list to open it; right-click for *Open file*, *Open file location*, or *Toggle selection*
- 🔄 **Recursive mode** — optionally scan all subfolders
- 🛡 **Collision-safe** — if the cleaned name already exists, appends `_1`, `_2`, … automatically
- 🚫 **Cancel anytime** — stop a scan mid-way; files already found are kept in the preview
- ⚡ **No data loss** — uses `os.rename` (atomic on the same filesystem); file contents are never read or written

---

## 🖥 Requirements

| | |
|---|---|
| **OS** | Windows 10/11, macOS 12+, or Linux (any modern distro with tkinter) |
| **Python** | 3.12 or 3.14 (to build from source) |
| **Dependencies** | None — pure Python standard library |

> **Linux note:** tkinter is not always bundled with Python. Install it with:
> `sudo apt install python3-tk` (Debian/Ubuntu) or `sudo dnf install python3-tkinter` (Fedora)

---

## 🚀 Getting Started

### Option A — Download the release (recommended)

1. Go to the [**Releases**](../../releases) page
2. Download the binary for your platform:
   - `EmojiRemoverZ.exe` — Windows
   - `EmojiRemoverZ` — Linux
   - `EmojiRemoverZ.app` — macOS *(or the plain binary if no .app is provided)*
3. Run it — no installation needed

### Option B — Build from source

**Windows:**
```bat
git clone https://github.com/Ium101/emoji-remover-z
cd emoji-remover-z
build.bat
```
Executable at `dist\EmojiRemoverZ.exe`

**Linux / macOS:**
```bash
git clone https://github.com/Ium101/emoji-remover-z
cd emoji-remover-z
chmod +x build.sh
./build.sh
```
Executable at `dist/EmojiRemoverZ`

Or manually on any platform:
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name EmojiRemoverZ emoji-remover-z.py
```

---

## 🧭 How to Use

1. **Launch** `EmojiRemoverZ.exe`
2. **Browse** — select the folder containing your files
3. *(Optional)* Check **Include subfolders** to scan recursively
4. Click **⟳ Scan** — the progress bar shows real counting and scanning progress
5. **Review** the preview list — original name on the left, cleaned name on the right
6. **Uncheck** any files you want to skip (click the row or use right-click menu)
7. Click **✦ Rename X Files** to apply — a confirmation dialog appears first

---

## 🔒 Safety

- Only `os.rename()` is called — the file path changes, zero bytes inside the file are touched
- All renames happen on the same filesystem (atomic)
- If source file disappears between scan and rename, the error is caught and reported — other files continue
- If the cleaned name collides with an existing file, a suffix counter is added (`file_1.ext`, `file_2.ext`, …)
- Empty names (e.g. a filename that was only emojis) fall back to `file.ext`

---

## 📋 What Gets Cleaned

| Type | Example input | Output |
|---|---|---|
| Emoji | `🎉 Party Photo.jpg` | `Party Photo.jpg` |
| Emoji with padding | `🔥HOT - stuff🔥.mp4` | `HOT - stuff.mp4` |
| Mathematical bold | `𝗛𝗲𝗹𝗹𝗼 𝗪𝗼𝗿𝗹𝗱.png` | `Hello World.png` |
| Mathematical italic | `𝘝𝘪𝘥𝘦𝘰 𝟮𝟬𝟮𝟰.mp4` | `Video 2024.mp4` |
| Script / fraktur | `𝓗𝓮𝓵𝓵𝓸.docx` | `Hello.docx` |
| Fullwidth | `ｈｅｌｌｏ.txt` | `hello.txt` |
| Mixed | `𝗩𝗶𝗱𝗲𝗼 🎬 𝗧𝗶𝘁𝗹𝗲.mkv` | `Video Title.mkv` |
| Normal file | `photo - vacation.jpg` | *(skipped, unchanged)* |
| Normal file | `IMG_20240101.jpg` | *(skipped, unchanged)* |

---

## 🏗 Project Structure

```
emoji-remover-z/
├── emoji-remover-z.py   # Main application (single file, no dependencies)
├── build.bat            # One-click build script — Windows (Python 3.14)
├── build.sh             # One-click build script — Linux / macOS
└── README.md
```

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

<p align="center">
  Feito pelo Usuário Ium101 do GitHub &nbsp;/&nbsp; Made by User Ium101 from GitHub
</p>
