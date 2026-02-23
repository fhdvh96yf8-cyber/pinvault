import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QUrl
from PySide6.QtGui import QIcon

# Tell Windows this is its own app (not python.exe) so taskbar shows our icon
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PinVault.App.1")
except Exception:
    pass

# Ensure project root is on sys.path so `app` package imports work when running
# this file as a script (python app/qml_app.py)
if getattr(sys, 'frozen', False):
    # PyInstaller: sys._MEIPASS is _internal/; datas land at _internal/app/qml/
    SCRIPT_DIR = os.path.join(sys._MEIPASS, 'app')
    PROJECT_ROOT = sys._MEIPASS
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.qml_backend import Backend
from app.thumb_provider import ThumbImageProvider


def _setup_error_log():
    """Redirect stderr to a log file when frozen so crashes leave a trace."""
    if getattr(sys, 'frozen', False):
        log_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'PinVault')
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, 'pinvault_error.log')
        try:
            sys.stderr = open(log_path, 'w', encoding='utf-8', buffering=1)
            sys.stdout = sys.stderr  # also redirect stdout to same file
        except Exception:
            pass


def _install_qt_logger():
    """Route Qt/QML log messages to Python stderr (which in frozen builds → the error log)."""
    from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    def _handler(msg_type, context, message):
        level = {
            QtMsgType.QtDebugMsg:    'DBG',
            QtMsgType.QtInfoMsg:     'INF',
            QtMsgType.QtWarningMsg:  'WRN',
            QtMsgType.QtCriticalMsg: 'CRT',
            QtMsgType.QtFatalMsg:    'FAT',
        }.get(msg_type, '???')
        print(f'[Qt/{level}] {message}', flush=True)
    qInstallMessageHandler(_handler)


def main():
    _setup_error_log()
    _install_qt_logger()
    app = QApplication(sys.argv)
    # Set app icon (taskbar + window chrome)
    _icon_path = os.path.join(SCRIPT_DIR, 'qml', 'pinvault.svg')
    if os.path.exists(_icon_path):
        app.setWindowIcon(QIcon(_icon_path))
    engine = QQmlApplicationEngine()
    # register image provider for on-the-fly rounded thumbnails
    try:
        provider = ThumbImageProvider()
        engine.addImageProvider('thumbs', provider)
    except Exception:
        pass
    backend = Backend()
    # keep verbose off to avoid flooding the console
    backend.verbose = False
    # also print inspectReport signals on Python side so we always see them
    try:
        backend.inspectReport.connect(lambda s: print('[PY inspectReport]', s))
    except Exception:
        pass
    engine.rootContext().setContextProperty('backend', backend)
    qml_path = os.path.join(SCRIPT_DIR, 'qml', 'Main.qml')
    qml_file = QUrl.fromLocalFile(os.path.abspath(qml_path))
    engine.load(qml_file)
    if not engine.rootObjects():
        print('Failed to load QML')
        sys.exit(-1)
    print('QML loaded, backend verbose ON')
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
