# -*- mode: python ; coding: utf-8 -*-
import sys
import os

# Icon path — place emoji_remover_z.ico / .png next to this spec file
_HERE = os.path.dirname(os.path.abspath(SPEC))
_ICON = os.path.join(_HERE, 'emoji_remover_z.ico' if sys.platform == 'win32'
                     else 'emoji_remover_z.png')


a = Analysis(
    ['emoji-remover-z.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Emoji_Remover_Z',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_ICON,
)
