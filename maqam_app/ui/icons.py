"""أيقونات رفيعة بيضا (SVG مرسومة في الكود — مافيش ملفات خارجية)."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_STROKE = 'fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'

_PATHS = {
    "open": '<path d="M3 7.5V18a1.5 1.5 0 0 0 1.5 1.5h15A1.5 1.5 0 0 0 21 18V9a1.5 1.5 0 0 0-1.5-1.5H12l-2-2.5H4.5A1.5 1.5 0 0 0 3 6.5z"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "play": '<path d="M8 5.5v13l10.5-6.5z"/>',
    "pause": '<path d="M8.5 5.5v13M15.5 5.5v13"/>',
    "stop": '<rect x="6.5" y="6.5" width="11" height="11" rx="2"/>',
    "midi": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 19v-6M11 19v-6M15 19v-6M19 19v-6"/><path d="M7 5v5M11 5v5M15 5v5"/>',
    "pdf": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "wave": '<path d="M3 12h2M7 8v8M11 5v14M15 9v6M19 7v10M21 12h0"/>',
    "music": '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "drum": '<ellipse cx="12" cy="8" rx="8" ry="3"/><path d="M4 8v8c0 1.7 3.6 3 8 3s8-1.3 8-3V8"/><path d="M8 3l3 4M16 3l-3 4"/>',
    "keys": '<rect x="2.5" y="5" width="19" height="14" rx="2"/><path d="M7 5v14M12 5v14M17 5v14"/><path d="M9.5 5v8M14.5 5v8M4.8 5v8M19.2 5v8" stroke-width="2.6"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
    "analyze": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/><path d="M8 11h1.5l1-2.5 1.5 5 1-2.5H14"/>',
    "volume": '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "download": '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5"/><path d="M5 19h14"/>',
    "zoom": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4M8 11h6M11 8v6"/>',
    "reset": '<path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4v4.5h4.5"/>',
    "loop": '<path d="M17 2.5l3 3-3 3"/><path d="M4 11.5v-1a5 5 0 0 1 5-5h11"/><path d="M7 21.5l-3-3 3-3"/><path d="M20 12.5v1a5 5 0 0 1-5 5H4"/>',
}


def icon(name: str, color: str = "#F2F2F4", size: int = 24) -> QIcon:
    body = _PATHS.get(name, "")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" '
           f'height="{size}"><g {_STROKE.format(c=color)}>{body}</g></svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    ic = QIcon()
    for scale in (1, 2):
        pm = QPixmap(QSize(size * scale, size * scale))
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        renderer.render(p)
        p.end()
        pm.setDevicePixelRatio(scale)
        ic.addPixmap(pm)
    return ic
