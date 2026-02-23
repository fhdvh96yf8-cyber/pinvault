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
        'app.app',
        'app.qml_backend',
        'app.thumb_provider',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'unittest', 'test', 'xmlrpc',
        # Unused Qt/PySide6 modules — keeps their DLLs out of the bundle
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineQuick', 'PySide6.QtWebEngineWidgets',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
        'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras', 'PySide6.Qt3DLogic',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtGraphs',
        'PySide6.QtDesigner', 'PySide6.QtUiTools', 'PySide6.QtHelp',
        'PySide6.QtBluetooth', 'PySide6.QtNfc',
        'PySide6.QtLocation', 'PySide6.QtPositioning',
        'PySide6.QtSensors', 'PySide6.QtSpatialAudio',
        'PySide6.QtSerialBus', 'PySide6.QtSerialPort',
        'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.QtStateMachine',
        'PySide6.QtVirtualKeyboard', 'PySide6.QtTextToSpeech',
        'PySide6.QtHttpServer', 'PySide6.QtNetworkAuth',
        'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
        'PySide6.QtSql', 'PySide6.QtTest',
        'PySide6.QtDBus', 'PySide6.QtAxContainer',
        'PySide6.QtPrintSupport', 'PySide6.QtOpenGLWidgets',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── Strip unused Qt DLLs that PyInstaller collected anyway ───────────────────
# These patterns match DLL names to exclude from the binary set.
_EXCLUDE_DLL_PREFIXES = (
    # Unused Qt modules — saves ~200 MB
    'qt6webengine', 'qt63d', 'qt6charts', 'qt6designer', 'qt6designercomponents',
    'qt6bluetooth', 'qt6nfc', 'qt6location', 'qt6positioning', 'qt6sensors',
    'qt6serialbus', 'qt6serialport', 'qt6spatialaudio', 'qt6remoteobjects',
    'qt6scxml', 'qt6statemachine', 'qt6datavisualization', 'qt6virtualkeyboard',
    'qt6graphs', 'qt6httpserver', 'qt6pdf', 'qt6networkauthentication',
    'qt6texttospeech', 'qt6test', 'qt6help', 'qt6uitools',
    'qt6printsupport', 'qt6openglwidgets',
    'opengl32sw',       # 20 MB software OpenGL fallback — not needed on modern Windows
    # ffmpeg DLLs are large and get duplicated at the bundle root by PyInstaller's
    # PE scanner.  We filter them here, then re-add them to a.datas below so they
    # land only in bin/ffmpeg.../bin/ where ffmpeg.exe can find them.
    'avfilter-', 'avcodec-62', 'avformat-', 'avdevice-',
    # PySide6 ships its own avcodec-61.dll (different major version) — NOT filtered.
)
a.binaries = TOC([
    (name, path, typecode)
    for (name, path, typecode) in a.binaries
    if not os.path.basename(name).lower().startswith(_EXCLUDE_DLL_PREFIXES)
])

# Re-anchor the filtered ffmpeg DLLs back into the correct subdirectory so that
# ffmpeg.exe (a subprocess call) can load them via the standard DLL search path.
_ffmpeg_bin_src = os.path.join(_bindir, 'ffmpeg-master-latest-win64-lgpl-shared', 'bin')
_ffmpeg_bin_dst = os.path.join('bin', 'ffmpeg-master-latest-win64-lgpl-shared', 'bin')
_reanchor_dlls = ['avfilter-11.dll', 'avcodec-62.dll', 'avformat-62.dll', 'avdevice-62.dll']
for _dll in _reanchor_dlls:
    _src = os.path.join(_ffmpeg_bin_src, _dll)
    if os.path.exists(_src):
        # TOC entry: (dest_relative_to_MEIPASS, source_path, typecode)
        a.datas.append((os.path.join(_ffmpeg_bin_dst, _dll), _src, 'DATA'))
a.binaries = TOC([
    (name, path, typecode)
    for (name, path, typecode) in a.binaries
    if not os.path.basename(name).lower().startswith(_EXCLUDE_DLL_PREFIXES)
])

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Explicitly include Qt6MultimediaQuick.dll ────────────────────────────────
# This DLL registers AudioOutput / MediaPlayer / VideoOutput as QML types.
# PyInstaller's PE scanner never discovers it because no Python code imports it —
# the Qt QML engine loads it dynamically at runtime when those types appear in QML.
_pyside6_dir = os.path.dirname(__import__('PySide6').__file__)
_mmquick_dll = os.path.join(_pyside6_dir, 'Qt6MultimediaQuick.dll')
if os.path.exists(_mmquick_dll):
    a.binaries += TOC([('Qt6MultimediaQuick.dll', _mmquick_dll, 'BINARY')])

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
