# PinVault

A Windows desktop app for browsing and extracting media assets from pinball machine SD card images (`.raw` / forensic disk images).

Built with Python + PySide6 + QML. Uses SleuthKit (`icat`, `fls`, `mmls`) for filesystem forensics and ffmpeg for thumbnail generation and video preview.

---

## Features

- Browse all media files inside a raw SD card image without mounting it
- Thumbnail grid with Small / Medium / Large view
- Multi-select: single click to toggle, Shift+click for range, click+drag lasso
- Right-click or Export button for batch export
- Embedded video preview with H.264 playback
- Persistent thumbnail cache (survives restarts)
- "Hide unthumbnailed" filter for clean browsing

---

## Quick Start (from source)

### Prerequisites

- Python 3.10+ (3.12 recommended)
- Windows 10/11 x64

### Setup

```powershell
git clone https://github.com/YOUR_USERNAME/pinvault.git
cd pinvault

python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -r requirements.txt

# Download SleuthKit + ffmpeg binaries into ./bin
python app/download_bins.py
```

### Run

```powershell
python app/qml_app.py
```

---

## Building a Release (Windows EXE)

```powershell
# One-step build -> dist/PinVault/PinVault.exe
.\build_release.ps1

# Build and also create a ZIP for distribution
.\build_release.ps1 -Zip
```

The output `dist/PinVault/` folder is self-contained and can be zipped and distributed  no Python installation required on the target machine.

---

## Automated Releases (GitHub Actions)

Pushing a version tag triggers a full build and creates a GitHub Release automatically:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

The workflow (`.github/workflows/release.yml`) will:
1. Set up Python 3.12
2. Download the binary tools
3. Build with PyInstaller
4. Attach `PinVault-windows.zip` to the release

---

## Project Structure

```
app/
  qml_app.py          # entry point
  qml_backend.py      # PySide6 backend (signals, threaded scanning)
  app.py              # find_tool(), settings, legacy Qt widgets UI
  thumb_provider.py   # QQuickImageProvider for thumbnail loading
  qml/
    Main.qml          # full UI
    pinvault.svg      # app icon
    placeholder.svg   # thumbnail placeholder
bin/                  # bundled tools (not committed - download via download_bins.py)
  icat.exe, fls.exe, mmls.exe   # SleuthKit
  ffmpeg.exe, ffprobe.exe       # ffmpeg (in subdirectory)
  *.dll                         # Visual C++ runtime + SleuthKit deps
```

---

## User Data Locations

| Data | Location |
|------|----------|
| Settings | `%APPDATA%\PinVault\settings.json` |
| Thumbnail cache | `%LOCALAPPDATA%\PinVault\thumbcache\` |
| Temp extractions | `%TEMP%\tmp_extract_*`, `preview_extract_*` (cleaned on startup) |

---

## Requirements

```
PySide6
```

*(SleuthKit and ffmpeg are bundled binaries, not Python packages)*
