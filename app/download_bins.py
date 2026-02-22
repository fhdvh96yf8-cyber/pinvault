"""Download and extract recommended Windows binaries into ./bin

This script attempts to download prebuilt SleuthKit and ewf-tools binaries
into the project `bin/` folder. It will prompt for confirmation before
downloading anything. Downloads may fail if the exact URLs change; the
script will report failures and leave partial results in `bin/`.

Use with caution and review URLs in this script before running.
"""
import os
import sys
import shutil
import tempfile
import urllib.request
import zipfile
import tarfile
import json

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BIN_DIR = os.path.join(ROOT, "bin")

# Candidates describe a GitHub repo to query and a hint for the asset name
# The downloader will try to find a Windows zip asset that contains the hint.
CANDIDATES = {
    "sleuthkit": {
        "display": "SleuthKit (fls, icat)",
        "repo": "sleuthkit/sleuthkit",
        "asset_hint": "win",
        "type": "zip",
    },
    "ewf-tools": {
        "display": "ewf-tools (libewf/ewfinfo)",
        # try multiple repos that might contain windows builds
        "repos": ["libyal/libewf", "libyal/ewf-tools"],
        "asset_hint": "ewf",
        "type": "zip",
    },
    "7zip": {
        "display": "7-Zip (7z.exe)",
        "special": "7zip",
        "type": "exe",
    },
    "ffmpeg": {
        "display": "FFmpeg (ffmpeg.exe)",
        "repo": "BtbN/FFmpeg-Builds",
        "asset_hint": "win64",
        "type": "zip",
    },
}


def github_latest_asset_url(repo, asset_hint):
    """Return the browser_download_url for the first release asset matching asset_hint and .zip/.exe."""
    api = f"https://api.github.com/repos/{repo}/releases"
    req = urllib.request.Request(api, headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "sd-image-extractor"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except Exception as e:
        raise RuntimeError(f"Failed to query GitHub for {repo}: {e}")

    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected GitHub response for {repo}")

    for release in data:
        assets = release.get("assets", [])
        for asset in assets:
            name = asset.get("name", "").lower()
            url = asset.get("browser_download_url")
            if not url or not name:
                continue
            if asset_hint.lower() in name and (name.endswith('.zip') or 'win' in name):
                return url
    raise RuntimeError(f"No suitable Windows asset found for {repo}")


def github_try_repos(repos, asset_hint):
    last_err = None
    for repo in repos:
        try:
            return github_latest_asset_url(repo, asset_hint)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Tried repos {repos} but failed: {last_err}")


def find_7zip_url():
    """Scrape 7-zip.org homepage for an .exe download link (x64 preferred)."""
    url = "https://www.7-zip.org/"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        raise RuntimeError(f"Failed to fetch 7-zip page: {e}")

    # crude search for hrefs pointing to .exe that contain x64 or 64
    import re
    matches = re.findall(r'href\s*=\s*"([^"]+)"', html)
    candidates = []
    for m in matches:
        if m.lower().endswith('.exe') and ('x64' in m.lower() or '64' in m.lower()):
            candidates.append(m)
    if not candidates:
        # fallback: any .exe
        for m in matches:
            if m.lower().endswith('.exe'):
                candidates.append(m)
    if not candidates:
        raise RuntimeError("No .exe download links found on 7-zip page")

    # make absolute URL if needed
    first = candidates[0]
    if first.startswith('http'):
        return first
    return urllib.request.urljoin(url, first)


def download_file(url, target_path):
    with urllib.request.urlopen(url) as resp, open(target_path, "wb") as out:
        shutil.copyfileobj(resp, out)


def extract_archive(archive_path, dest_dir, kind):
    if kind == "zip":
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(dest_dir)
    elif kind == "tar":
        with tarfile.open(archive_path, "r:*") as t:
            t.extractall(dest_dir)
    else:
        raise ValueError("Unknown archive kind")


def ensure_bin_dir():
    os.makedirs(BIN_DIR, exist_ok=True)


def main():
    # Support --yes / -y flag for non-interactive CI environments
    auto_yes = "--yes" in sys.argv or "-y" in sys.argv

    print("This will attempt to download recommended SleuthKit/ewf binaries into:")
    print("  ", BIN_DIR)
    print("Review the URLs in app/download_bins.py before proceeding.")
    if auto_yes:
        print("Proceeding automatically (--yes flag set).")
    else:
        ans = input("Proceed with download? [y/N]: ").strip().lower()
        if ans != "y":
            print("Aborted by user.")
            sys.exit(1)

    ensure_bin_dir()

    for key, meta in CANDIDATES.items():
        print(f"\n== {meta['display']} ==")
        kind = meta.get("type", "zip")
        url = meta.get("url")
        if not url:
            # handle special cases
            if meta.get('special') == '7zip':
                try:
                    url = find_7zip_url()
                except Exception as e:
                    print("Failed to locate 7-Zip download:", e)
                    print("You can manually download 7z.exe and place it in the 'bin' folder.")
                    continue
            else:
                # Query GitHub releases for a suitable Windows asset; support multiple repos
                repos = meta.get('repos')
                try:
                    if repos:
                        url = github_try_repos(repos, meta.get('asset_hint', 'win'))
                    else:
                        url = github_latest_asset_url(meta['repo'], meta.get('asset_hint', 'win'))
                except Exception as e:
                    print("Failed to locate asset on GitHub:", e)
                    print("You can manually download the required binaries and place them in the 'bin' folder.")
                    continue

        print("Downloading:", url)
        try:
            with tempfile.NamedTemporaryFile(delete=False) as t:
                tmp_path = t.name
            download_file(url, tmp_path)
            print("Downloaded to", tmp_path)
            print("Extracting...")
            extract_archive(tmp_path, BIN_DIR, kind)
            print("Extracted into", BIN_DIR)
        except Exception as e:
            print("Failed:", e)
            print("You can manually download the required binaries and place them in the 'bin' folder.")
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    print("\nDone. Run `python app/check_prereqs.py` to validate the downloaded tools.")


if __name__ == "__main__":
    main()
