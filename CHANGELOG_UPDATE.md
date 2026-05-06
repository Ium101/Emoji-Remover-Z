# Emoji Remover Z - Update Summary

## Changes Made

### 1. **Folder Renaming Support**
   - The scanner now detects and processes both **files** and **folders**
   - Folders are collected during the walk phase and cleaned using the same logic as files
   - A new "TYPE" column in the preview table displays 📁 for folders and 📄 for files
   - The rename worker handles folder renaming separately using `os.rename()` for directories
   - Updated UI text to mention "files and folders" throughout

### 2. **Special Characters Added to Removal List**
   Added comprehensive support for removing decorative Unicode characters, including:
   
   #### Punctuation & Box Drawing:
   - General Punctuation block (U+2000–U+206F): bullets, dashes, quotes, etc.
   - Box Drawing (U+2500–U+257F): ┌─┐ ├─┤ └─┘ ╔═╗ etc.
   - Block Elements (U+2580–U+259F): shading blocks
   - Geometric Shapes (U+25A0–U+25FF): ●■▲ etc.
   
   #### Mathematical & Arrows:
   - Mathematical Operators (U+2200–U+22FF): ∀∃∈ etc.
   - Arrows (U+2190–U+21FF): →←↑↓ etc.
   - Supplemental Arrows (U+2900–U+297F)
   - Miscellaneous Symbols and Arrows (U+2B00–U+2BFF)
   
   #### Devanagari Marks:
   - Devanagari diacritics (U+0950–U+097F)
   - Devanagari extended (U+A8E0–U+A8FF)
   
   #### Specific Decorative Characters:
   ```
   ✩ ✧ ⋄ ⋆ ⋅ ☾ ∘ °❉° ︶ ☑ ✕ ❤ 💖 💀 💜
   ╳ ┊ ♡ ♥ ✿ ═ ║ ╝ ╔ ╚ ▒ ░ ≡ ꒦ ꒱ ︵ ︶
   ˗ ˋ ˊ ° • ﾟ 彡 ★ ☆ 々 ᆽ ゝ 々 ➛ ︶ ❀ ︵
   ```

### 3. **Data Structure Updates**
   - `_preview_data` tuples now include a 5th element: `item_type` (either `'file'` or `'folder'`)
   - Updated all functions that reference this tuple structure:
     - `_refresh_row()`: Displays folders without file extension
     - `_insert_rows()`: Adds item type indicator (folder/file emoji)
     - `_rename_worker()`: Routes folder vs file renames appropriately

### 4. **UI/UX Improvements**
   - Updated header subtitle: "strip emojis & styled text from **filenames and folders**"
   - Updated confirm dialog: "Rename {count} item(s)" instead of "Rename {count} files"
   - Updated success message: "renamed {count} items" with note about both files and folders
   - Added "TYPE" column to preview table showing 📁 or 📄 icons

## Testing
- Syntax validation passed ✓
- Script compiles without errors

## Notes
- The removal happens recursively through all subdirectories when "Include subfolders" is checked
- Folder names themselves are cleaned (not parent paths)
- Unique naming logic handles collisions for both files and folders
