import os
import shutil
import subprocess
import sys

# Suppress console windows when spawning child processes in the frozen Windows build
_W32 = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}

TOOLS = ["fls", "icat", "ewfinfo", "7z", "ffmpeg"]

# Local bin folder (next to project root): ../bin relative to this script
BIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bin"))


def _find_local_tool(tool):
    """Look for tool anywhere inside the local bin folder (recursive).

    Matches filenames exactly (with or without .exe on Windows).
    """
    if not os.path.isdir(BIN_DIR):
        return None
    wanted = {tool.lower()}
    if os.name == "nt":
        wanted.add(f"{tool.lower()}.exe")

    for root, dirs, files in os.walk(BIN_DIR):
        for f in files:
            if f.lower() in wanted:
                candidate = os.path.join(root, f)
                if os.access(candidate, os.X_OK) or os.name == 'nt':
                    return candidate
    return None


def check_tool(tool):
    # Prefer a local bundled binary in ./bin
    local = _find_local_tool(tool)
    if local:
        try:
            proc = subprocess.run([local, "--version"], capture_output=True, text=True, timeout=5, **_W32)
            out = proc.stdout.strip() or proc.stderr.strip()
            return True, local, out.splitlines()[0] if out else "(local binary)"
        except Exception:
            return True, local, "(found local binary)"

    # Fall back to PATH
    path = shutil.which(tool)
    if path:
        try:
            proc = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5, **_W32)
            out = proc.stdout.strip() or proc.stderr.strip()
            return True, path, out.splitlines()[0] if out else "(no version output)"
        except Exception:
            return True, path, "(found on PATH)"
    else:
        return False, None, None


if __name__ == "__main__":
    overall_ok = True
    print("Checking for required external tools (SleuthKit, EWF, 7-Zip) and ffmpeg (thumbnails)...")
    for t in TOOLS:
        ok, path, info = check_tool(t)
        if ok:
            print(f"  OK: {t} -> {path} — {info}")
        else:
            print(f"  MISSING: {t} (not found on PATH)")
            overall_ok = False

    if not overall_ok:
        print("\nSome tools are missing. Please install SleuthKit (fls, icat), libewf/ewf-tools (ewfinfo), ffmpeg (optional, used for thumbnails), and optionally 7-Zip, and ensure they are on your PATH.")
        print("If you downloaded Windows binaries, you can add their containing folder to PATH or put them in a 'bin' folder next to this app and run the GUI from this repo.")
        sys.exit(2)
    else:
        print("\nAll required tools found on PATH.")
        sys.exit(0)
