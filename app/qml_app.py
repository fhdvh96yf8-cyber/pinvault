import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QUrl
from PySide6.QtGui import QIcon

# Tell Windows this is its own app (not python.exe) so taskbar shows our icon
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SternPinball.PinVault.1")
except Exception:
    pass

# Ensure project root is on sys.path so `app` package imports work when running
# this file as a script (python app/qml_app.py)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.qml_backend import Backend
from app.thumb_provider import ThumbImageProvider


def main():
    app = QApplication(sys.argv)
    # Set app icon (taskbar + window chrome)
    _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qml', 'pinvault.svg')
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
