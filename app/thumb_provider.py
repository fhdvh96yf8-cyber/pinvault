import os
import urllib.parse

from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtCore import QSize, Qt
import traceback


class ThumbImageProvider(QQuickImageProvider):
    def __init__(self):
        # provide Pixmap so QML's Image element can request a pixmap path
        super().__init__(QQuickImageProvider.Pixmap)

    def _load_and_mask(self, path: str, requestedSize: QSize):
        raw = path.split('?', 1)[0]
        path = urllib.parse.unquote(raw)
        print('[thumbprov] request id=', raw, '-> path=', path, 'requestedSize=', requestedSize)
        # Normalize a possible leading slash on Windows ("/C:\...")
        if os.name == 'nt' and path.startswith('/') and len(path) > 2 and path[2] == ':':
            path = path[1:]
        if not os.path.exists(path):
            print('[thumbprov] missing file:', path)
            return QImage()

        img = QImage(path)
        if img.isNull():
            print('[thumbprov] QImage failed to load:', path)
            return QImage()
        else:
            print('[thumbprov] loaded image size=', img.width(), 'x', img.height(), 'format=', img.format())

        # ensure ARGB for masking
        if img.format() != QImage.Format_ARGB32 and img.format() != QImage.Format_ARGB32_Premultiplied:
            img = img.convertToFormat(QImage.Format_ARGB32)

        w = img.width()
        h = img.height()

        # rounded mask path
        radius = max(12, int(min(w, h) * 0.12))
        pathp = QPainterPath()
        pathp.addRoundedRect(0.0, 0.0, float(w), float(h), float(radius), float(radius))

        # draw clipped result into destination image with alpha preserved
        result = QImage(w, h, QImage.Format_ARGB32)
        result.fill(0)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setClipPath(pathp)
        painter.drawImage(0, 0, img)
        painter.end()

        # quick diagnostic check: if result is mostly black/transparent, dump a short sample
        try:
            s = result.pixel(0, 0)
            # no-op; just ensure we can access pixels
        except Exception:
            print('[thumbprov] pixel access failed:', traceback.format_exc())

        # convert to premultiplied format which QML expects for proper alpha blending
        prem = result.convertToFormat(QImage.Format_ARGB32_Premultiplied)

        # if a requested size was given, scale the image to improve memory/use
        if requestedSize and not requestedSize.isEmpty():
            prem = prem.scaled(requestedSize.width(), requestedSize.height(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

        return prem

    def requestPixmap(self, id: str, size: QSize, requestedSize: QSize):
        try:
            img = self._load_and_mask(id, requestedSize)
            if img.isNull():
                print('[thumbprov] requestPixmap: returned null image for id=', id)
                return QPixmap(), QSize()
            pix = QPixmap.fromImage(img)
            print('[thumbprov] returning pixmap size=', pix.width(), 'x', pix.height())
            return pix, QSize(pix.width(), pix.height())
        except Exception:
            print('[thumbprov] requestPixmap exception:', traceback.format_exc())
            return QPixmap(), QSize()

    # keep requestImage for compatibility; delegate to pixmap loader
    def requestImage(self, id: str, size: QSize, requestedSize: QSize):
        try:
            img = self._load_and_mask(id, requestedSize)
            if img.isNull():
                return QImage(), QSize()
            return img, QSize(img.width(), img.height())
        except Exception:
            return QImage(), QSize()
