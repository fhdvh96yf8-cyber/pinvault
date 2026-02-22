import os
import sys
import shutil
import subprocess
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QFileDialog,
    QLabel,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QInputDialog,
    QMenu,
    QProgressDialog,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QLineEdit,
    QCheckBox,
    QDialogButtonBox,
)
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QListWidget, QListWidgetItem
import json
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPixmap, QIcon
import tempfile
import time

# Toggle verbose app-level logging for diagnostics
APP_VERBOSE = False


def find_tool(tool_name):
    # Prefer a local bundled binary in ./bin (recursive), then fall back to PATH
    BIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bin"))
    wanted = {tool_name.lower()}
    if os.name == 'nt':
        wanted.add(f"{tool_name.lower()}.exe")

    if os.path.isdir(BIN_DIR):
        for root, dirs, files in os.walk(BIN_DIR):
            for f in files:
                if f.lower() in wanted:
                    candidate = os.path.join(root, f)
                    # on Windows we accept the file, on Unix ensure it's executable
                    if os.name == 'nt' or os.access(candidate, os.X_OK):
                        return candidate

    return shutil.which(tool_name)


# settings file — writable user-data location when frozen, local otherwise
def _get_settings_path():
    if getattr(sys, 'frozen', False):
        d = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'PinVault')
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, 'settings.json')
    return os.path.join(os.path.dirname(__file__), 'settings.json')

SETTINGS_PATH = _get_settings_path()


def load_settings():
    defaults = {
        "default_save_dir": "",
        "default_open_dir": "",
        "save_asset_as_mp4": True,
        "hide_unthumbnailed_assets": True,
    }
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            defaults.update(data)
    except Exception:
        pass
    return defaults


def save_settings(s):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass


class SettingsDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = dict(settings)
        from PySide6.QtWidgets import QHBoxLayout

        layout = QVBoxLayout(self)

        # Apply a lightweight modern stylesheet
        self.setStyleSheet('''
            QWidget { font-family: Segoe UI, Arial, sans-serif; font-size: 11pt; }
            QPushButton { background: #2d7; border: none; padding: 8px 12px; border-radius: 6px; }
            QPushButton#danger { background: #e36; }
            QListWidget { background: #111; color: #eee; border-radius: 6px; }
            QTreeWidget { background: #111; color: #eee; }
            QProgressBar { height: 14px; border-radius: 7px; }
            QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6cf, stop:1 #39f); }
            QLabel#status { color: #444; }
        ''')

        layout.addWidget(QLabel("Default save directory:"))
        row = QHBoxLayout()
        self.save_edit = QLineEdit(self.settings.get("default_save_dir", ""))
        row.addWidget(self.save_edit)
        btn = QPushButton("Browse")
        row.addWidget(btn)
        layout.addLayout(row)

        layout.addWidget(QLabel("Default open directory:"))
        row2 = QHBoxLayout()
        self.open_edit = QLineEdit(self.settings.get("default_open_dir", ""))
        row2.addWidget(self.open_edit)
        btn2 = QPushButton("Browse")
        row2.addWidget(btn2)
        layout.addLayout(row2)

        self.chk_asset = QCheckBox("Save .asset files as .mp4 on export")
        self.chk_asset.setChecked(bool(self.settings.get("save_asset_as_mp4", True)))
        layout.addWidget(self.chk_asset)

        self.chk_hide_unthumb = QCheckBox("Hide .asset files that don't produce thumbnails")
        self.chk_hide_unthumb.setChecked(bool(self.settings.get("hide_unthumbnailed_assets", True)))
        layout.addWidget(self.chk_hide_unthumb)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)

        btn.clicked.connect(self.browse_save)
        btn2.clicked.connect(self.browse_open)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

    def browse_save(self):
        d = QFileDialog.getExistingDirectory(self, "Select default save directory", self.save_edit.text() or os.path.expanduser("~"))
        if d:
            self.save_edit.setText(d)

    def browse_open(self):
        d = QFileDialog.getExistingDirectory(self, "Select default open directory", self.open_edit.text() or os.path.expanduser("~"))
        if d:
            self.open_edit.setText(d)

    def accept(self):
        self.settings["default_save_dir"] = self.save_edit.text()
        self.settings["default_open_dir"] = self.open_edit.text()
        self.settings["save_asset_as_mp4"] = bool(self.chk_asset.isChecked())
        self.settings["hide_unthumbnailed_assets"] = bool(self.chk_hide_unthumb.isChecked())
        save_settings(self.settings)
        super().accept()


def run_fls(image_path, offset: int = 0):
    fls = find_tool("fls")
    if not fls:
        raise FileNotFoundError("fls not found on PATH")

    cmd = [fls, "-r"]
    if offset and offset > 0:
        cmd += ["-o", str(offset)]
    cmd.append(image_path)

    if APP_VERBOSE:
        print(f"[app.run_fls] exec: {cmd}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if APP_VERBOSE:
        print(f"[app.run_fls] rc={proc.returncode} stdout_len={len(proc.stdout or '')} stderr_len={len(proc.stderr or '')}")
    if proc.returncode != 0 and not proc.stdout:
        if APP_VERBOSE:
            print(f"[app.run_fls] stderr: {proc.stderr}")
        raise RuntimeError(f"fls failed: {proc.stderr.strip()}")

    lines = proc.stdout.splitlines()
    files = []
    import re
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        # Try to extract inode and filename. Example: 'r/r 5:  zImage' or 'v/v 261939:     $MBR'
        m = re.match(r'.*?\s(\d+):\s+(.*)$', ln)
        if m:
            inode = int(m.group(1))
            filename = m.group(2).strip()
        else:
            # fallback: take last token as filename
            parts = ln.rsplit(None, 1)
            if len(parts) == 2 and parts[0].rstrip(':').isdigit():
                inode = int(parts[0].rstrip(':'))
                filename = parts[1]
            else:
                # skip entries we can't parse
                continue

        if filename.startswith("./"):
            filename = filename[2:]

        files.append({"path": filename, "inode": inode})
    return files


def populate_tree(tree: QTreeWidget, files):
    tree.clear()
    nodes = {}

    for f in files:
        path = f.get("path")
        inode = f.get("inode")
        offset = f.get("offset", 0)
        parts = [p for p in path.split("/") if p != ""]
        parent = None
        path_so_far = ""
        for i, part in enumerate(parts):
            path_so_far = os.path.join(path_so_far, part) if path_so_far else part
            if path_so_far in nodes:
                parent = nodes[path_so_far]
                continue
            # If this is the final part, we may want to skip creating the node
            # for certain asset files when thumbnails cannot be produced and
            # the user has enabled the setting to hide such assets.
            is_final = (i == len(parts) - 1)
            ext = os.path.splitext(part)[1].lower() if is_final else ''
            hide_unthumb = False
            try:
                hide_unthumb = bool(tree.window().settings.get('hide_unthumbnailed_assets', True))
            except Exception:
                hide_unthumb = False

            # If we will create a thumbnail and the user wants to hide unthumbnailed .asset files,
            # attempt to generate the thumbnail first and skip creating the item if none.
            pix = None
            has_audio = False
            if is_final and ext in ('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.jpg', '.jpeg', '.png', '.asset', '.mp3', '.m4a', '.aac', '.wav', '.ogg', '.opus'):
                try:
                    # create_thumbnail now returns (QPixmap|None, has_audio:bool)
                    pix, has_audio = tree.window().create_thumbnail(path, inode, offset)
                except Exception:
                    pix = None
                    has_audio = False
                if ext == '.asset' and hide_unthumb and not pix:
                    # skip adding this .asset entry entirely
                    parent = nodes.get(path_so_far, parent)
                    continue

            if parent is None:
                item = QTreeWidgetItem(tree, [part])
            else:
                item = QTreeWidgetItem(parent, [part])
            # if this is the final part, attach inode and maybe set the icon
            if is_final:
                # store a dict with inode and offset so extraction can use correct partition
                item.setData(0, Qt.UserRole, {"inode": inode, "offset": offset})
                if pix:
                    try:
                        item.setIcon(0, QIcon(pix))
                    except Exception:
                        pass
                # annotate if this asset appears to contain audio
                if has_audio:
                    try:
                        item.setText(0, f"{part} (audio)")
                    except Exception:
                        pass
            nodes[path_so_far] = item
            parent = item


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SD Image Extractor — Prototype")
        self.resize(1100, 720)

        layout = QVBoxLayout(self)

        self.status = QLabel("No image loaded.")
        layout.addWidget(self.status)

        # top toolbar row (simplified)
        btn_row = QWidget()
        from PySide6.QtWidgets import QHBoxLayout, QSpacerItem, QSizePolicy

        brl = QHBoxLayout(btn_row)
        self.btn_open = QPushButton("Open image")
        self.btn_download_selected = QPushButton("Download Selected")
        self.btn_settings = QPushButton("Settings")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search files...")
        self.search_box.setMaximumWidth(320)
        # view and sort controls
        self.view_combo = QComboBox()
        self.view_combo.addItems(["Grid","List","Thumb Small","Thumb Large","Thumb XL"])
        # default to extra large thumbnails / grid
        self.view_combo.setCurrentIndex(0)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Name ↑","Name ↓","Size ↑","Size ↓"])

        brl.addWidget(self.btn_open)
        brl.addWidget(self.view_combo)
        brl.addWidget(self.sort_combo)
        brl.addWidget(self.search_box)
        brl.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        brl.addWidget(self.btn_download_selected)
        brl.addWidget(self.btn_settings)
        layout.addWidget(btn_row)

        # two views: hierarchical tree for list, and icon grid for thumbnails
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Files in image")
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(self.list_widget.IconMode)
        self.list_widget.setResizeMode(self.list_widget.Adjust)
        self.list_widget.setMovement(self.list_widget.Static)
        self.list_widget.setSpacing(12)
        layout.addWidget(self.tree)
        layout.addWidget(self.list_widget)
        # show the preferred view
        self.tree.setVisible(False)
        self.list_widget.setVisible(True)

        self.btn_check.clicked.connect(self.on_check)
        self.btn_open.clicked.connect(self.on_open)
        self.btn_refresh.clicked.connect(self.on_refresh)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.on_tree_context_menu)

        # wire actions
        self.btn_download_selected.clicked.connect(self.extract_selected)
        self.view_combo.currentIndexChanged.connect(lambda _: self._refresh_view())
        self.sort_combo.currentIndexChanged.connect(lambda _: self._refresh_view())
        self.search_box.textChanged.connect(lambda _: self._apply_filter())
        self.btn_settings.clicked.connect(self.open_settings)

        self.current_image = None
        self.settings = load_settings()
        # set view defaults from settings
        if self.settings.get('default_open_dir'):
            self._last_open_dir = self.settings.get('default_open_dir')
        else:
            self._last_open_dir = os.path.expanduser("~")

        # embedded progress bar for thumbnailing / scanning
        from PySide6.QtWidgets import QProgressBar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel("")
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)

        # internal thumbnail progress counters
        self._thumb_total = 0
        self._thumb_done = 0
        self._thumb_start_time = 0.0
        self._thumb_durations = []

    def thumbnail_start(self, total: int):
        try:
            self._thumb_total = int(total)
            self._thumb_done = 0
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(self._thumb_total if self._thumb_total > 0 else 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self._thumb_start_time = time.time()
            self._thumb_durations = []
            self.progress_label.setText(f"Preparing thumbnails: 0/{self._thumb_total}")
            QApplication.processEvents()
        except Exception:
            pass

    def thumbnail_increment(self, step: int = 1):
        try:
            self._thumb_done += step
            if self._thumb_total:
                self.progress_bar.setValue(self._thumb_done)
                pct = int((self._thumb_done / float(self._thumb_total)) * 100)
                # compute ETA from measured durations if available
                eta_str = ''
                if len(self._thumb_durations) > 0:
                    avg = sum(self._thumb_durations) / len(self._thumb_durations)
                    remaining = max(0, self._thumb_total - self._thumb_done)
                    eta = remaining * avg
                    # format ETA as MM:SS
                    mins = int(eta // 60)
                    secs = int(eta % 60)
                    eta_str = f' — ETA {mins:02d}:{secs:02d}'
                self.progress_label.setText(f"Preparing thumbnails: {self._thumb_done}/{self._thumb_total} ({pct}%)" + eta_str)
            else:
                self.progress_label.setText(f"Preparing thumbnails: {self._thumb_done}")
            QApplication.processEvents()
        except Exception:
            pass

    def thumbnail_finish(self):
        try:
            self.progress_bar.setVisible(False)
            self.progress_label.setText("")
            QApplication.processEvents()
        except Exception:
            pass

    def _make_thumb_widget(self, pix: QPixmap, name: str, has_audio: bool, isz: QSize):
        w = QWidget()
        from PySide6.QtWidgets import QVBoxLayout
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6,6,6,6)
        lay.setSpacing(6)
        img = QLabel()
        img.setFixedSize(isz.width(), isz.height())
        if pix:
            try:
                img.setPixmap(pix.scaled(isz, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except Exception:
                pass
        img.setStyleSheet('border-radius:6px; background:#222;')
        caption = QLabel(name + (" (audio)" if has_audio else ""))
        caption.setAlignment(Qt.AlignCenter)
        caption.setWordWrap(True)
        caption.setFixedWidth(isz.width())
        caption.setStyleSheet('color:#eee;')
        lay.addWidget(img, alignment=Qt.AlignCenter)
        lay.addWidget(caption, alignment=Qt.AlignCenter)
        w.setStyleSheet('background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #161616, stop:1 #1b1b1b); border-radius:8px;')
        return w

    def _apply_filter(self):
        txt = self.search_box.text().lower()
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            data = it.data(Qt.UserRole) or {}
            name = data.get('path', it.text()).lower()
            widget = self.list_widget.itemWidget(it)
            visible = (txt in name) if txt else True
            if widget:
                widget.setVisible(visible)
            try:
                it.setHidden(not visible)
            except Exception:
                pass

    def on_check(self):
        from subprocess import run

        try:
            p = run([sys.executable, os.path.join(os.path.dirname(__file__), "check_prereqs.py")])
            if p.returncode == 0:
                QMessageBox.information(self, "Prereqs", "All required tools found on PATH.")
            else:
                self.show_copyable_message("Prereqs", "Some tools are missing. See console for details.")
        except Exception as e:
            self.show_copyable_message("Error", "Failed to run prereq check.", details=str(e))

    def on_open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open image file",
                              getattr(self, '_last_open_dir', os.path.expanduser("~")), "Image files (*.img *.dd *.raw *.E01 *.ewf);;All files (*)")
        if not path:
            return
        self.current_image = path
        self.status.setText(f"Loaded: {path}")
        # Scan partitions for media files and populate view (uses embedded progress bar)
        try:
            media_files = self.scan_all_partitions_for_media(path)
            # enrich with sizes (may be relatively slow) and then populate
            for f in media_files:
                if 'size' not in f:
                    try:
                        f['size'] = self.get_inode_size(f.get('inode'), f.get('offset', 0))
                    except Exception:
                        f['size'] = 0
            self.update_tree(media_files)
        except Exception as e:
            self.show_copyable_message("Scan error", "Failed to scan partitions.", details=str(e))

    def on_refresh(self):
        if not self.current_image:
            QMessageBox.information(self, "No image", "No image loaded. Use 'Open image' first.")
            return
        self.refresh_listing()

    def refresh_listing(self):
        try:
            files = run_fls(self.current_image, offset=getattr(self, 'current_offset', 0))
        except FileNotFoundError:
            self.show_copyable_message("Missing tool", "`fls` not found on PATH. Run 'Check prerequisites' for guidance.", details=f"Image: {self.current_image}")
            return
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            details = f"Image: {self.current_image}\n\nException: {e}\n\nTraceback:\n{tb}"
            self.show_copyable_message("Error", f"Failed to list image: {self.current_image}", details=details)
            return

        self.update_tree(files)


    def show_copyable_message(self, title: str, text: str, details: str = None):
        """Show a message box with a Copy button that copies text+details to the clipboard.

        `details` will be set as the detailed text shown by the dialog and included in the copied text.
        """
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        if details:
            msg.setDetailedText(details)

        copy_btn = msg.addButton("Copy", QMessageBox.ActionRole)
        msg.addButton(QMessageBox.Ok)
        msg.exec()

        if msg.clickedButton() == copy_btn:
            clipboard = QApplication.clipboard()
            to_copy = text
            if details:
                to_copy = to_copy + "\n\n" + details
            clipboard.setText(to_copy)

    def detect_partitions(self, image_path: str):
        """Run mmls and parse basic partition entries into [{'start':int,'desc':str}, ...]."""
        mmls = find_tool("mmls")
        if not mmls:
            raise FileNotFoundError("mmls not found on PATH")
        proc = subprocess.run([mmls, image_path], capture_output=True, text=True)
        if proc.returncode != 0 and not proc.stdout:
            raise RuntimeError(f"mmls failed: {proc.stderr.strip()}")
        parts = []
        for ln in proc.stdout.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            if 'Unallocated' in ln or 'Meta' in ln or ln.startswith('------'):
                continue
            # find numeric tokens
            toks = ln.split()
            nums = [t for t in toks if t.isdigit()]
            if len(nums) >= 1:
                # choose first numeric token as start
                start = int(nums[0])
                # description is remainder tokens after numeric group
                # find index of first numeric token
                try:
                    idx = toks.index(nums[0])
                    desc = ' '.join(toks[idx+3:]) if len(toks) > idx+3 else ' '.join(toks[idx+1:])
                except Exception:
                    desc = ' '.join(toks)
                parts.append({"start": start, "desc": desc})
        return parts

    def get_inode_size(self, inode: int, offset: int = 0):
        """Return file size in bytes using `istat` if available, or 0 on failure."""
        istat = find_tool('istat')
        if not istat:
            # try nested sleuthkit bin
            istat = find_tool('sleuthkit-4.14.0-win32\\bin\\istat')
        if not istat:
            return 0
        try:
            cmd = [istat]
            if offset:
                cmd += ['-o', str(offset)]
            cmd += [self.current_image, str(inode)]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            out = proc.stdout + proc.stderr
            for ln in out.splitlines():
                ln = ln.strip()
                if ln.startswith('Size:'):
                    parts = ln.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        return int(parts[1])
                    # sometimes 'Size: 12345 bytes'
                    for tok in parts:
                        if tok.isdigit():
                            return int(tok)
        except Exception:
            pass
        return 0

    def update_tree(self, files):
        # ensure we have sizes
        for f in files:
            if 'size' not in f:
                try:
                    f['size'] = self.get_inode_size(f.get('inode'), f.get('offset', 0))
                except Exception:
                    f['size'] = 0

        sort = self.sort_combo.currentText() if hasattr(self, 'sort_combo') else 'Name ↑'
        if sort == 'Name ↑':
            files.sort(key=lambda x: x.get('path','').lower())
        elif sort == 'Name ↓':
            files.sort(key=lambda x: x.get('path','').lower(), reverse=True)
        elif sort == 'Size ↑':
            files.sort(key=lambda x: x.get('size', 0))
        elif sort == 'Size ↓':
            files.sort(key=lambda x: x.get('size', 0), reverse=True)

        # Choose view mode and icon size
        view = self.view_combo.currentText() if hasattr(self, 'view_combo') else 'List'
        # compute how many thumbnails we'll attempt (final file entries)
        thumb_exts = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.jpg', '.jpeg', '.png', '.asset', '.mp3', '.m4a', '.aac', '.wav', '.ogg', '.opus'}
        thumb_candidates = 0
        for f in files:
            ext = os.path.splitext(f.get('path',''))[1].lower()
            if ext in thumb_exts:
                thumb_candidates += 1

        # start progress tracking
        try:
            self.thumbnail_start(thumb_candidates)
        except Exception:
            pass

        if view == 'List':
            self.tree.setVisible(True)
            self.list_widget.setVisible(False)
            self.tree.setIconSize(QSize(64,64))
            populate_tree(self.tree, files)
        else:
            # grid/icon view
            self.tree.setVisible(False)
            self.list_widget.setVisible(True)
            # choose icon size from selection
            if view == 'Thumb Small':
                isz = QSize(64,64)
            elif view == 'Thumb Large':
                isz = QSize(128,128)
            elif view == 'Thumb XL' or view == 'Grid':
                isz = QSize(256,256)
            else:
                isz = QSize(256,256)
            self.list_widget.setIconSize(isz)
            # populate flattened icon grid
            self.list_widget.clear()
            for f in files:
                path = f.get('path')
                inode = f.get('inode')
                offset = f.get('offset', 0)
                name = os.path.basename(path)
                item = QListWidgetItem()
                item.setData(Qt.UserRole, {"inode": inode, "offset": offset, "path": path})
                # create thumbnail widget and attach
                try:
                    t0 = time.time()
                    pix, has_audio = self.create_thumbnail(path, inode, offset)
                    dur = time.time() - t0
                    try:
                        self._thumb_durations.append(dur)
                    except Exception:
                        pass
                    # size hint for card
                    item.setSizeHint(QSize(isz.width() + 16, isz.height() + 48))
                    card = self._make_thumb_widget(pix, name, has_audio, isz)
                    self.list_widget.addItem(item)
                    self.list_widget.setItemWidget(item, card)
                except Exception:
                    # fallback: simple item
                    item.setText(name)
                    self.list_widget.addItem(item)
                # increment progress for each thumbnail attempt
                try:
                    self.thumbnail_increment()
                except Exception:
                    pass

        # finish progress
        try:
            self.thumbnail_finish()
        except Exception:
            pass

    def _refresh_view(self):
        # Re-run populate on currently loaded image to apply sort/view
        if not self.current_image:
            return
        try:
            media_files = self.scan_all_partitions_for_media(self.current_image)
            self.update_tree(media_files)
        except Exception:
            pass

    def scan_all_partitions_for_media(self, image_path: str):
        """Scan all detected partitions and return files that look like media (with offsets).

        Returns a list of dicts: {'path':..., 'inode':..., 'offset':...}
        """
        parts = []
        try:
            parts = self.detect_partitions(image_path)
        except Exception:
            parts = []

        results = []
        # include offset 0 as a possibility
        candidates = [0]
        for p in parts:
            # `mmls` reports partition start in sectors; SleuthKit `-o` expects sector offsets.
            candidates.append(p.get('start', 0))

        # include Unity/asset bundles ('.asset') which may contain video/audio blobs
        # also include common audio-only extensions so we detect those files
        media_exts = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.jpg', '.jpeg', '.png', '.asset', '.mp3', '.m4a', '.aac', '.wav', '.ogg', '.opus'}
        for offset in candidates:
            try:
                files = run_fls(image_path, offset=offset)
            except Exception:
                continue
            for f in files:
                ext = os.path.splitext(f.get('path',''))[1].lower()
                if ext in media_exts:
                    f['offset'] = offset
                    results.append(f)
        return results

    def create_thumbnail(self, file_path_in_image: str, inode: int, offset: int):
        """Extract a single file via icat and create a thumbnail QPixmap if possible.

        Returns a tuple: (QPixmap or None, has_audio: bool).
        Requires `icat`. `ffprobe` is used to detect audio streams (optional).
        """
        icat = find_tool('icat')
        if not icat:
            return (None, False)
        # locate ffmpeg/ffprobe
        ffmpeg = find_tool('ffmpeg')
        ffprobe = find_tool('ffprobe')
        tmpdir = tempfile.gettempdir()
        # safe filename
        safe = os.path.basename(file_path_in_image).replace(' ', '_')
        tmpfile = os.path.join(tmpdir, f"tmp_extract_{inode}_{safe}")
        thumbfile = os.path.join(tmpdir, f"thumb_{inode}_{safe}.jpg")
        pix = None
        has_audio = False
        try:
            cmd = [icat]
            if offset and offset > 0:
                cmd += ['-o', str(offset)]
            cmd += [self.current_image, str(inode)]
            with open(tmpfile, 'wb') as out:
                proc = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE)
                if proc.returncode != 0:
                    return (None, False)

            # Probe for audio streams if ffprobe available
            if ffprobe:
                try:
                    p = subprocess.run([ffprobe, '-v', 'error', '-show_streams', '-print_format', 'json', tmpfile], capture_output=True, text=True)
                    if p.returncode == 0 and p.stdout:
                        import json as _json
                        try:
                            info = _json.loads(p.stdout)
                            for s in info.get('streams', []):
                                if s.get('codec_type') == 'audio':
                                    has_audio = True
                                    break
                        except Exception:
                            pass
                except Exception:
                    pass

            # try to extract the first frame (time 0) for asset/video files if ffmpeg present
            if ffmpeg:
                try:
                    cmd2 = [ffmpeg, '-y', '-i', tmpfile, '-ss', '00:00:00', '-frames:v', '1', thumbfile]
                    proc2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if proc2.returncode == 0 and os.path.exists(thumbfile):
                        pix = QPixmap(thumbfile)
                except Exception:
                    pix = None
            else:
                # no ffmpeg — for image files, try to load directly
                ext = os.path.splitext(file_path_in_image)[1].lower()
                if ext in ('.jpg', '.jpeg', '.png'):
                    try:
                        pix = QPixmap(tmpfile)
                    except Exception:
                        pix = None
        finally:
            try:
                if os.path.exists(tmpfile):
                    os.remove(tmpfile)
            except Exception:
                pass
            try:
                if os.path.exists(thumbfile):
                    os.remove(thumbfile)
            except Exception:
                pass
        return (pix, has_audio)

    def on_tree_context_menu(self, pos: QPoint):
        item = self.tree.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        extract_act = menu.addAction("Extract selected")
        action = menu.exec(self.tree.mapToGlobal(pos))
        if action == extract_act:
            self.extract_selected()

    def on_select_all(self):
        self.tree.selectAll()

    def open_settings(self):
        dlg = SettingsDialog(self, self.settings if hasattr(self, 'settings') else load_settings())
        if dlg.exec() == QDialog.Accepted:
            # reload settings and apply defaults
            self.settings = load_settings()
            if self.settings.get('default_open_dir'):
                self._last_open_dir = self.settings.get('default_open_dir')
            QMessageBox.information(self, 'Settings', 'Settings saved.')

    def extract_selected(self):
        items = self.tree.selectedItems()
        if not items:
            QMessageBox.information(self, "No selection", "Select one or more files to extract.")
            return
        # use default save dir from settings if present
        default_dest = self.settings.get('default_save_dir') if hasattr(self, 'settings') else ''
        if default_dest:
            dest = default_dest
        else:
            dest = QFileDialog.getExistingDirectory(self, "Select destination folder", os.path.expanduser("~\\Downloads"))
        if not dest:
            return
        icat = find_tool('icat')
        if not icat:
            self.show_copyable_message('Missing tool', '`icat` not found on PATH. Run prerequisites check.', details='icat not found')
            return
        default_offset = getattr(self, 'current_offset', 0)
        for it in items:
            data = it.data(0, Qt.UserRole)
            name = it.text(0)
            # strip '(audio)' annotation added to tree display when present
            if name.endswith(' (audio)'):
                name = name[:-8]
            if data is None:
                continue
            # stored data may be a dict {inode, offset} or a raw inode
            if isinstance(data, dict):
                inode = data.get('inode')
                item_offset = data.get('offset', default_offset)
            else:
                inode = data
                item_offset = default_offset
            if inode is None:
                continue
            outname = name
            # if file is an .asset and user wants mp4 exports, rename
            if outname.lower().endswith('.asset') and self.settings.get('save_asset_as_mp4'):
                outname = outname[:-6] + '.mp4'
            outpath = os.path.join(dest, outname)
            try:
                with open(outpath, 'wb') as out:
                    if item_offset:
                        cmd = [icat, '-o', str(item_offset), self.current_image, str(inode)]
                    else:
                        cmd = [icat, self.current_image, str(inode)]
                    proc = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE)
                    if proc.returncode != 0:
                        raise RuntimeError(proc.stderr.decode('utf-8', errors='ignore'))
            except Exception as e:
                self.show_copyable_message('Extract error', f'Failed to extract {name}', details=str(e))
                return
        QMessageBox.information(self, 'Done', f'Extracted {len(items)} items to {dest}')


def main():
    app = QApplication([])
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

