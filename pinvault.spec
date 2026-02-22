# -*- mode: python ; coding: utf-8 -*-
"""
PinVault — PyInstaller build spec
Run:  pyinstaller pinvault.spec
Output: dist/PinVault/PinVault.exe  (one-directory build)
"""
import os
import sys

block_cipher = None

# ── Collect bin/ directory (SleuthKit + ffmpeg + support DLLs) ──────────────
_here  = os.path.dirname(os.path.abspath(SPEC))   # project root
_bindir = os.path.join(_here, 'bin')
_bin_datas = []

# File extensions that are dev-only artifacts and not needed at runtime
_SKIP_EXTS  = {'.lib', '.a', '.def', '.h', '.pc', '.pl', '.html', '.css'}
# ffmpeg ships doc/, include/, lib/, presets/ — runtime only needs bin/
_SKIP_DIRS  = {'doc', 'include', 'lib', 'presets'}
# executables we never call
_SKIP_FILES = {'ffplay.exe'}

for _root, _dirs, _files in os.walk(_bindir):
    # Skip backup directories and non-runtime ffmpeg subdirectories
    _dirs[:] = [
        d for d in _dirs
        if not d.startswith('_sleuthkit_backup')
        and not d.startswith('_sleuthkit_static_backup')
        and d.lower() not in _SKIP_DIRS
    ]
    for _f in _files:
        _ext = os.path.splitext(_f)[1].lower()
        if _ext in _SKIP_EXTS or _f.lower() in _SKIP_FILES:
            continue
        _src = os.path.join(_root, _f)
        # dest path relative to _MEIPASS root, preserving subdirectory structure
        _rel = os.path.relpath(os.path.dirname(_src), _here)
        _bin_datas.append((_src, _rel))

# ── Icon (use .ico if it exists next to the SVG, otherwise no icon) ──────────
_ico = os.path.join(_here, 'app', 'qml', 'pinvault.ico')
_icon_arg = _ico if os.path.exists(_ico) else None

a = Analysis(
    [os.path.join(_here, 'app', 'qml_app.py')],
    pathex=[_here],
    binaries=[],
    datas=[
        # QML UI files and SVG assets
        (os.path.join(_here, 'app', 'qml'), os.path.join('app', 'qml')),
        # Python package marker
        (os.path.join(_here, 'app', '__init__.py'), 'app'),
    ] + _bin_datas,
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickControls2',
        'PySide6.QtMultimedia',
        'PySide6.Qt5Compat',
        'app.app',
        'app.qml_backend',
        'app.thumb_provider',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'test', 'xmlrpc'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PinVault',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # no console window in release build
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_arg,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='PinVault',
)
