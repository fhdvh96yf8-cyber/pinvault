from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThreadPool, QUrl
import subprocess
import sys
import os
import tempfile
import json
import time
import threading
import urllib.parse

# Suppress console windows when spawning child processes in the frozen Windows build
_W32 = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}

from app.app import find_tool, run_fls
try:
    from PIL import Image, ImageDraw
except Exception:
    Image = None

MEDIA_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.jpg', '.jpeg', '.png', '.asset', '.mp3', '.m4a', '.aac', '.wav', '.ogg', '.opus'}


class ScanRunnable(QRunnable):
    def __init__(self, image_path, parent):
        super().__init__()
        self.image_path = image_path
        self.parent = parent

    def run(self):
        did_notify = False
        try:
            assets = []
            # quick sanity: ensure fls is available
            fls_tool = find_tool('fls')
            if not fls_tool:
                try:
                    self.parent.scanError.emit('Required tool "fls" not found; please install SleuthKit or place fls in ./bin')
                except Exception:
                    pass
                return
            # try to detect partitions using mmls
            parts = []
            mmls = find_tool('mmls')
            if mmls:
                try:
                    p = subprocess.run([mmls, self.image_path], capture_output=True, text=True, **_W32)
                    for ln in p.stdout.splitlines():
                        ln = ln.strip()
                        if not ln or 'Unallocated' in ln or 'Meta' in ln or ln.startswith('------'):
                            continue
                        toks = ln.split()
                        nums = [t for t in toks if t.isdigit()]
                        if len(nums) >= 1:
                            start = int(nums[0])
                            parts.append(start)
                except Exception:
                    parts = []
            # include offset 0
            candidates = [0] + parts
            for offset in candidates:
                try:
                    files = run_fls(self.image_path, offset=offset)
                except Exception:
                    continue
                for f in files:
                    ext = os.path.splitext(f.get('path',''))[1].lower()
                    if ext in MEDIA_EXTS:
                        f['offset'] = offset
                        # uid is the stable unique key used in QML for thumbnail matching
                        f['uid'] = f"{offset}_{f.get('inode')}"
                        assets.append(f)
            # set up thumb tracking in parent and emit scan started
            total = len(assets)
            if total == 0:
                try:
                    self.parent.scanStarted.emit(0)
                except Exception:
                    pass
                try:
                    self.parent.scanFinished.emit()
                except Exception:
                    pass
                return
            try:
                # initialize counters so backend can track thumbnail completion
                self.parent._thumbs_total = total
                self.parent._thumbs_done = 0
            except Exception:
                pass
            try:
                if getattr(self.parent, 'verbose', False):
                    print(f"[backend] scanStarted: total={total}")
                self.parent.scanStarted.emit(total)
            except Exception:
                pass
            # emit assets one-by-one; scanProgress is NOT emitted here so the
            # progress bar only tracks thumbnail completion (meaningful work)
            for idx, f in enumerate(assets):
                try:
                    if getattr(self.parent, 'verbose', False):
                        print(f"[backend] assetFound: {f.get('path')} inode={f.get('inode')} offset={f.get('offset')}")
                    self.parent.assetFound.emit(json.dumps(f))
                except Exception:
                    pass
                # also start thumbnailing for this asset from the backend side
                try:
                    self.parent.pool.start(ThumbRunnable(self.parent, f))
                except Exception:
                    pass
        except Exception as e:
                try:
                    if getattr(self.parent, 'verbose', False):
                        print(f"[backend] scanError: {e}")
                    self.parent.scanError.emit(str(e))
                except Exception:
                    pass


class ThumbRunnable(QRunnable):
    def __init__(self, backend, file_info: dict):
        super().__init__()
        self.backend = backend
        self.file_info = file_info

    def run(self):
        try:
            # uid from scan: stable key used in QML for thumbnail matching
            fi_uid = self.file_info.get('uid', '')
            icat = find_tool('icat')
            if not icat:
                try:
                    self.backend.thumbnailReady.emit(fi_uid, '', False, '')
                except Exception:
                    pass
                return
            ffmpeg = find_tool('ffmpeg')
            ffprobe = find_tool('ffprobe')
            tmpdir = tempfile.gettempdir()
            safe   = os.path.basename(self.file_info.get('path', '')).replace(' ', '_')
            inode  = self.file_info.get('inode', 0)
            off    = self.file_info.get('offset', 0)
            # Use a per-run UUID in the temp filename to prevent any race between
            # concurrent threads processing different assets with the same inode on
            # different partitions (offset already differs but belt-and-suspenders).
            import uuid as _uuid
            fn_uid    = _uuid.uuid4().hex[:8]
            tmpfile   = os.path.join(tmpdir, f"tmp_extract_{off}_{inode}_{fn_uid}_{safe}")
            thumbfile = os.path.join(tmpdir, f"thumb_{off}_{inode}_{fn_uid}_{safe}.jpg")

            # --- Persistent thumbnail cache check ---
            try:
                cached = self.backend._thumb_cache_path(self.backend.current_image, inode, off)
                if os.path.exists(cached):
                    meta_path = cached + '.meta'
                    detected_ext = ''
                    has_audio_cached = False
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path) as _m:
                                raw = _m.read().strip()
                            try:
                                meta = json.loads(raw)
                                detected_ext    = meta.get('detected_ext', '')
                                has_audio_cached = meta.get('has_audio', False)
                            except (json.JSONDecodeError, AttributeError):
                                # legacy plain-text format
                                detected_ext = raw
                        except Exception:
                            pass
                    self.backend.thumbnailReady.emit(fi_uid, cached, has_audio_cached, detected_ext)
                    return
            except Exception:
                cached = None

            cmd = [icat]
            if off and off > 0:
                cmd += ['-o', str(off)]
            cmd += [self.backend.current_image, str(inode)]
            with open(tmpfile, 'wb') as out:
                proc = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE, **_W32)
                if proc.returncode != 0:
                    try:
                        self.backend.thumbnailReady.emit(fi_uid, '', False, '')
                    except Exception:
                        pass
                    try:
                        os.remove(tmpfile)
                    except Exception:
                        pass
                    return

            has_audio    = False
            has_video    = False
            detected_ext = ''
            duration     = 0.0
            if ffprobe:
                try:
                    p = subprocess.run(
                        [ffprobe, '-v', 'error', '-show_streams', '-show_format', '-print_format', 'json', tmpfile],
                        capture_output=True, text=True, **_W32
                    )
                    if p.returncode == 0 and p.stdout:
                        info = json.loads(p.stdout)
                        for s in info.get('streams', []):
                            if s.get('codec_type') == 'audio':
                                has_audio = True
                            if s.get('codec_type') == 'video':
                                has_video = True
                                if duration == 0.0:
                                    try:
                                        duration = float(s.get('duration', 0))
                                    except Exception:
                                        pass
                        try:
                            fmt_dur = float(info.get('format', {}).get('duration', 0))
                            if fmt_dur > 0:
                                duration = fmt_dur
                        except Exception:
                            pass
                        orig_ext = os.path.splitext(self.file_info.get('path', ''))[1].lower()
                        if orig_ext == '.asset':
                            if has_video:
                                detected_ext = '.mp4'
                            elif has_audio:
                                detected_ext = '.m4a'
                        if not has_video:
                            try:
                                self.backend.thumbnailReady.emit(fi_uid, '', has_audio, detected_ext)
                            except Exception:
                                pass
                            try:
                                if os.path.exists(tmpfile):
                                    os.remove(tmpfile)
                            except Exception:
                                pass
                            return
                except Exception:
                    pass

            if ffmpeg:
                try:
                    # Choose seek time: skip first 10% of video (min 1s, max 30s)
                    # to avoid solid-black title cards at the very start.
                    if duration > 2.0:
                        seek_time = min(max(duration * 0.10, 1.0), 30.0)
                    else:
                        seek_time = 0.0
                    seek_str = f"{int(seek_time // 3600):02d}:{int((seek_time % 3600) // 60):02d}:{seek_time % 60:06.3f}"

                    def _extract_frame(src, dst, ss):
                        """Extract one frame at seek position ss into dst; return True on success."""
                        return subprocess.run(
                            [ffmpeg, '-y', '-ss', ss, '-i', src, '-frames:v', '1', dst],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_W32
                        ).returncode == 0 and os.path.exists(dst)

                    ok = _extract_frame(tmpfile, thumbfile, seek_str)

                    # If PIL is available, check if the chosen frame is nearly solid
                    # (e.g. solid black leader) and retry at 50% of duration.
                    if ok and Image is not None and duration > 4.0:
                        try:
                            import statistics as _st
                            img = Image.open(thumbfile).convert('L').resize((64, 36))
                            pixels = list(img.getdata())
                            mean   = sum(pixels) / len(pixels)
                            try:
                                stdev = _st.stdev(pixels)
                            except Exception:
                                stdev = 0
                            # solid frame: mean very dark (<20) or very bright (>235) and low variance
                            if stdev < 12 or (mean < 20) or (mean > 235 and stdev < 20):
                                mid_str = f"{int(duration/2 // 3600):02d}:{int((duration/2 % 3600) // 60):02d}:{(duration/2) % 60:06.3f}"
                                ok2 = _extract_frame(tmpfile, thumbfile, mid_str)
                                if not ok2:
                                    ok = ok  # keep original
                        except Exception:
                            pass

                    if ok:
                        try:
                            if hasattr(self.backend, '_thumb_files'):
                                self.backend._thumb_files.add(thumbfile)
                        except Exception:
                            pass
                        try:
                            if cached:
                                import shutil as _shutil
                                _shutil.copy2(thumbfile, cached)
                                with open(cached + '.meta', 'w') as _m:
                                    json.dump({'detected_ext': detected_ext, 'has_audio': has_audio}, _m)
                        except Exception:
                            pass
                        try:
                            self.backend.thumbnailReady.emit(fi_uid, thumbfile, has_audio, detected_ext)
                        except Exception:
                            self.backend.thumbnailReady.emit(fi_uid, '', has_audio, detected_ext)
                    else:
                        self.backend.thumbnailReady.emit(fi_uid, '', has_audio, detected_ext)
                except Exception:
                    self.backend.thumbnailReady.emit(fi_uid, '', has_audio, detected_ext)
            else:
                self.backend.thumbnailReady.emit(fi_uid, '', has_audio, detected_ext)
            try:
                if os.path.exists(tmpfile):
                    os.remove(tmpfile)
            except Exception:
                pass
        except Exception:
            try:
                self.backend.thumbnailReady.emit(
                    self.file_info.get('uid', ''), '', False, ''
                )
            except Exception:
                pass
        finally:
            try:
                if hasattr(self.backend, '_notify_thumbnail_done'):
                    self.backend._notify_thumbnail_done()
            except Exception:
                pass


class PreviewRunnable(QRunnable):
    """Extract a single file to a temp path for in-app preview playback."""
    def __init__(self, backend, file_info: dict):
        super().__init__()
        self.backend = backend
        self.file_info = file_info

    def run(self):
        try:
            uid       = self.file_info.get('uid', '')
            inode     = self.file_info.get('inode')
            off       = self.file_info.get('offset', 0)
            orig_path = self.file_info.get('path', '')
            det_ext   = self.file_info.get('detectedExt', '')
            orig_ext  = os.path.splitext(orig_path)[1].lower()
            ext       = det_ext if det_ext else (orig_ext or '.bin')

            icat = find_tool('icat')
            if not icat or inode is None:
                self.backend.previewReady.emit(uid, '')
                return

            tmpdir  = tempfile.gettempdir()
            outpath = os.path.join(tmpdir, f'preview_extract_{uid}{ext}')

            # return cached extraction if it already exists
            if os.path.exists(outpath) and os.path.getsize(outpath) > 0:
                self.backend._preview_files.add(outpath)
                self.backend.previewReady.emit(uid, outpath)
                return

            cmd = [icat]
            if off and off > 0:
                cmd += ['-o', str(off)]
            cmd += [self.backend.current_image, str(inode)]
            with open(outpath, 'wb') as f:
                proc = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, **_W32)
            if proc.returncode == 0 and os.path.exists(outpath) and os.path.getsize(outpath) > 0:
                self.backend._preview_files.add(outpath)
                self.backend.previewReady.emit(uid, outpath)
            else:
                try:
                    os.remove(outpath)
                except Exception:
                    pass
                self.backend.previewReady.emit(uid, '')
        except Exception:
            try:
                self.backend.previewReady.emit(self.file_info.get('uid', ''), '')
            except Exception:
                pass


class Backend(QObject):
    assetFound = Signal(str)            # json file dict (includes uid)
    thumbnailReady = Signal(str, str, bool, str)  # uid, thumb_path, has_audio, detected_ext
    scanStarted = Signal(int)
    scanProgress = Signal(int)
    scanFinished = Signal()
    scanError = Signal(str)
    inspectReport = Signal(str)
    exportFinished = Signal(str)        # dest path
    exportError = Signal(str)
    previewReady = Signal(str, str)     # uid, local_path (empty string = failed)
    imageCleared = Signal()

    def __init__(self):
        super().__init__()
        self.pool = QThreadPool.globalInstance()
        self.current_image = ''
        # settings stored next to this script
        self.settings_path = os.path.join(os.path.dirname(__file__), '..', 'settings.json')
        # thumbnail tracking
        self._thumbs_total = 0
        self._thumbs_done = 0
        self._thumbs_lock = threading.Lock()
        # track generated thumbnail files so we can clean them up
        self._thumb_files = set()
        # track preview-extracted files so we can clean them up on dismount
        self._preview_files = set()
        # Pillow rounding / baking disabled — QML OpacityMask handles rounding
        self.round_thumbnails = False
        self.bake_thumb_bg = False
        # verbose logging guard (set to True for debug)
        self.verbose = False
        # clean up any leftover temp files from a previous session
        self._startup_cleanup()

    def _thumb_cache_dir(self):
        """Persistent thumbnail cache directory in %LOCALAPPDATA%."""
        d = os.path.join(os.path.expandvars('%LOCALAPPDATA%'), 'PinVault', 'thumbcache')
        os.makedirs(d, exist_ok=True)
        return d

    def _thumb_cache_path(self, image_path: str, inode, offset) -> str:
        """Stable cache filename keyed on image path + inode + offset."""
        import hashlib
        key = f"{image_path}|{inode}|{offset}"
        h = hashlib.sha256(key.encode()).hexdigest()[:20]
        return os.path.join(self._thumb_cache_dir(), f"{h}.jpg")

    def _startup_cleanup(self):
        """Remove leftover tmp_extract_*, thumb_*, and preview_extract_* files from %TEMP%."""
        try:
            tmp = tempfile.gettempdir()
            prefixes = ('tmp_extract_', 'thumb_', 'preview_extract_')
            removed = 0
            for name in os.listdir(tmp):
                if any(name.startswith(p) for p in prefixes):
                    try:
                        os.remove(os.path.join(tmp, name))
                        removed += 1
                    except Exception:
                        pass
            if removed and self.verbose:
                print(f'[backend] startup cleanup: removed {removed} temp files')
        except Exception:
            pass

    def _notify_thumbnail_done(self):
        try:
            with self._thumbs_lock:
                self._thumbs_done += 1
                # emit thumbnail-progress via scanProgress to update UI
                try:
                    self.scanProgress.emit(self._thumbs_done)
                except Exception:
                    pass
                if self._thumbs_total > 0 and self._thumbs_done >= self._thumbs_total:
                    try:
                        self.scanFinished.emit()
                    except Exception:
                        pass
        except Exception:
            pass

    @Slot(str)
    def openImage(self, path: str):
        if getattr(self, 'verbose', False):
            print(f"[backend] openImage called: {path}")
        # Normalize a QML FileDialog URL (file:///) to a local filesystem path
        local_path = path
        try:
            q = QUrl(path)
            if q.isLocalFile():
                local_path = q.toLocalFile()
        except Exception:
            # fallback: strip file:// prefix if present
            if local_path.startswith('file://'):
                local_path = local_path[len('file://'):]
                # on Windows paths may have an extra leading slash
                if local_path.startswith('/') and len(local_path) > 2 and local_path[2] == ':':
                    local_path = local_path[1:]

        self.current_image = local_path
        # cleanup any previous thumbnails before starting a new scan
        try:
            # remove any orphaned thumb files in temp (thumb_*.jpg/png)
            try:
                tmp = tempfile.gettempdir()
                for name in os.listdir(tmp):
                    if name.startswith('thumb_') and (name.endswith('.jpg') or name.endswith('.png')):
                        p = os.path.join(tmp, name)
                        try:
                            os.remove(p)
                        except Exception:
                            pass
            except Exception:
                pass
            self.cleanupThumbnails()
        except Exception:
            pass

        # run scan in background using local path
        r = ScanRunnable(local_path, self)
        self.pool.start(r)

    @Slot()
    def cleanupThumbnails(self):
        """Delete any thumbnails we previously created in tmp dir."""
        try:
            for p in list(self._thumb_files):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
                try:
                    self._thumb_files.discard(p)
                except Exception:
                    pass
        except Exception:
            pass

    @Slot()
    def dismountImage(self):
        """Clear current image and remove all session temp files."""
        self.current_image = ''
        self._thumbs_total = 0
        self._thumbs_done  = 0
        self.cleanupThumbnails()
        for p in list(self._preview_files):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        self._preview_files = set()
        try:
            tmp = tempfile.gettempdir()
            for name in os.listdir(tmp):
                if name.startswith('tmp_extract_') or name.startswith('preview_extract_'):
                    try:
                        os.remove(os.path.join(tmp, name))
                    except Exception:
                        pass
        except Exception:
            pass
        self.imageCleared.emit()

    @Slot(str)
    def extractPreview(self, file_json: str):
        """Async: extract file for in-app preview. Emits previewReady(uid, local_path)."""
        try:
            info = json.loads(file_json)
        except Exception:
            return
        self.pool.start(PreviewRunnable(self, info))

    @Slot(str, str)
    def setSetting(self, key: str, value: str):
        try:
            # load from app settings if available
            from app.app import load_settings, save_settings
            s = load_settings()
            # attempt to coerce booleans and numbers
            if value.lower() in ('true','false'):
                s[key] = (value.lower() == 'true')
            else:
                try:
                    s[key] = int(value)
                except Exception:
                    s[key] = value
            save_settings(s)
        except Exception:
            try:
                # fallback: write a simple json
                import json as _json
                if os.path.exists(self.settings_path):
                    with open(self.settings_path, 'r', encoding='utf-8') as f:
                        cur = _json.load(f)
                else:
                    cur = {}
                cur[key] = value
                with open(self.settings_path, 'w', encoding='utf-8') as f:
                    _json.dump(cur, f, indent=2)
            except Exception:
                pass

    @Slot(result=str)
    def getSettings(self):
        try:
            from app.app import load_settings
            s = load_settings()
            return json.dumps(s)
        except Exception:
            try:
                if os.path.exists(self.settings_path):
                    with open(self.settings_path, 'r', encoding='utf-8') as f:
                        return f.read()
            except Exception:
                pass
        return '{}'

    @Slot(str)
    def requestThumbnail(self, file_json: str):
        try:
            file_info = json.loads(file_json)
        except Exception:
            return
        r = ThumbRunnable(self, file_info)
        self.pool.start(r)

    @Slot(result=str)
    def ping(self):
        return 'pong'

    @Slot(str, result=str)
    def inspectThumbnail(self, payload: str):
        """Inspect a thumbnail or asset. Expects a JSON string with keys: path, thumbUrl.
        Returns a JSON string with file existence and image metadata (width,height,mode).
        """
        try:
            data = json.loads(payload)
        except Exception:
            return json.dumps({'error': 'invalid json'})
        thumb = data.get('thumbUrl') or ''
        path = data.get('path') or ''
        # normalize file:// URL
        t = thumb
        # handle provider URLs like image://thumbs/<encoded-path>
        if t.startswith('image://thumbs/'):
            raw = t[len('image://thumbs/'):]
            # strip query params
            if '?' in raw:
                raw = raw.split('?', 1)[0]
            try:
                decoded = urllib.parse.unquote(raw)
                # normalize possible leading slash on Windows
                if os.name == 'nt' and decoded.startswith('/') and len(decoded) > 2 and decoded[2] == ':':
                    decoded = decoded[1:]
                t = decoded
            except Exception:
                t = ''
        else:
            # normalize file:// URL
            if t.startswith('file:///'):
                t = t[len('file:///'):]
            elif t.startswith('file://'):
                t = t[len('file://'):]
            # strip query params
            if '?' in t:
                t = t.split('?', 1)[0]
        report = {'requestedPath': path, 'thumbPath': t}
        try:
            exists = os.path.exists(t) if t else False
            report['thumbExists'] = exists
            if exists:
                report['sizeBytes'] = os.path.getsize(t)
                try:
                    if Image is not None:
                        with Image.open(t) as im:
                            report['width'], report['height'] = im.size
                            report['mode'] = im.mode
                    else:
                        report['width'] = None
                        report['height'] = None
                        report['mode'] = None
                except Exception as e:
                    report['imageError'] = str(e)
        except Exception as e:
            report['error'] = str(e)
        try:
            s = json.dumps(report)
            # Always print inspect reports triggered by UI clicks so troubleshooting is easy
            print(f"[inspect] {s}")
            try:
                self.inspectReport.emit(s)
            except Exception:
                pass
            return s
        except Exception:
            return json.dumps({'error': 'failed to build report'})

    @Slot(str, str)
    def exportAsset(self, file_json: str, dest_dir: str):
        """Extract an asset to dest_dir and emit exportFinished/exportError.
        Renames .asset files to the proper extension (.mp4 / .m4a) detected earlier.
        """
        def _run():
            try:
                info = json.loads(file_json)
                inode       = info.get('inode')
                off         = info.get('offset', 0)
                orig_path   = info.get('path', '')
                detected_ext = info.get('detectedExt', '')
                icat = find_tool('icat')
                if not icat or inode is None:
                    self.exportError.emit('icat not found or no inode')
                    return
                local_dest = dest_dir
                try:
                    from PySide6.QtCore import QUrl
                    q = QUrl(dest_dir)
                    if q.isLocalFile():
                        local_dest = q.toLocalFile()
                except Exception:
                    if local_dest.startswith('file:///'):
                        local_dest = local_dest[8:]
                    elif local_dest.startswith('file://'):
                        local_dest = local_dest[7:]
                os.makedirs(local_dest, exist_ok=True)
                base = os.path.basename(orig_path).replace(' ', '_') or f'asset_{inode}'
                stem, orig_ext = os.path.splitext(base)
                # If we know the real type, use it; otherwise keep original extension
                if detected_ext and orig_ext.lower() == '.asset':
                    fname = stem + detected_ext
                else:
                    fname = base
                outpath = os.path.join(local_dest, fname)
                cmd = [icat]
                if off and off > 0:
                    cmd += ['-o', str(off)]
                cmd += [self.current_image, str(inode)]
                with open(outpath, 'wb') as f:
                    proc = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, **_W32)
                if proc.returncode == 0 and os.path.exists(outpath):
                    self.exportFinished.emit(outpath)
                else:
                    self.exportError.emit(f'icat rc={proc.returncode}')
            except Exception as e:
                try:
                    self.exportError.emit(str(e))
                except Exception:
                    pass
        threading.Thread(target=_run, daemon=True).start()

    @Slot(str)
    def revealInExplorer(self, file_json: str):
        """Extract asset to temp and reveal in Windows Explorer."""
        def _run():
            try:
                info = json.loads(file_json)
                inode = info.get('inode')
                off   = info.get('offset', 0)
                orig_path = info.get('path', '')
                icat = find_tool('icat')
                if not icat or inode is None:
                    if os.name == 'nt':
                        subprocess.Popen(['explorer', tempfile.gettempdir()], **_W32)
                    return
                tmpdir = tempfile.gettempdir()
                fname = os.path.basename(orig_path).replace(' ', '_') or f'asset_{inode}'
                outpath = os.path.join(tmpdir, f'reveal_{inode}_{fname}')
                if not os.path.exists(outpath):
                    cmd = [icat]
                    if off and off > 0:
                        cmd += ['-o', str(off)]
                    cmd += [self.current_image, str(inode)]
                    with open(outpath, 'wb') as f:
                        subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, **_W32)
                if os.name == 'nt':
                    subprocess.Popen(['explorer', f'/select,{outpath}'], **_W32)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    @Slot(str)
    def openAsset(self, file_json: str):
        """Extract an asset using icat to a temp file and open it with the system default app (Windows: os.startfile).
        Expects a JSON string with keys: path, inode, offset (offset optional).
        """
        try:
            info = None
            try:
                info = json.loads(file_json)
            except Exception:
                # not JSON — maybe a raw path
                info = {'path': file_json}
            inode = info.get('inode')
            off = info.get('offset', 0)
            orig_path = info.get('path', '')
            icat = find_tool('icat')
            if not icat:
                if getattr(self, 'verbose', False):
                    print(f"[backend] openAsset: icat not found, cannot extract {orig_path}")
                return
            tmpdir = tempfile.gettempdir()
            safe = os.path.basename(orig_path).replace(' ', '_') or f"asset_{inode}"
            outpath = os.path.join(tmpdir, f"extracted_{inode}_{safe}")
            cmd = [icat]
            if off and off > 0:
                cmd += ['-o', str(off)]
            if inode is None:
                if getattr(self, 'verbose', False):
                    print(f"[backend] openAsset: no inode provided for {orig_path}")
                return
            cmd += [self.current_image, str(inode)]
            try:
                with open(outpath, 'wb') as out:
                    proc = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE, **_W32)
                    if proc.returncode != 0:
                        try:
                            if getattr(self, 'verbose', False):
                                print(f"[backend] openAsset: icat failed rc={proc.returncode} stderr={proc.stderr.decode('utf-8', errors='ignore')}")
                        except Exception:
                            pass
                        try:
                            if os.path.exists(outpath):
                                os.remove(outpath)
                        except Exception:
                            pass
                        return
            except Exception as e:
                if getattr(self, 'verbose', False):
                    print(f"[backend] openAsset: error extracting: {e}")
                try:
                    if os.path.exists(outpath):
                        os.remove(outpath)
                except Exception:
                    pass
                return
            # attempt to open with default app (Windows)
            try:
                if os.name == 'nt':
                    os.startfile(outpath)
                else:
                    # fallback: use xdg-open or open
                    opener = 'xdg-open' if os.name == 'posix' else None
                    if opener:
                        subprocess.Popen([opener, outpath], **_W32)
            except Exception as e:
                if getattr(self, 'verbose', False):
                    print(f"[backend] openAsset: failed to open extracted file: {e}")
        except Exception:
            pass
