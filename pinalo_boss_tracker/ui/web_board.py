"""Panel embebido con la web de timers (tablero por servidor).

No scrapea APIs inventadas: muestra la página oficial dentro de la app
para que elijas Kaisinel y veas muertos/vivos sin salir a Chrome.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

BOARD_URL = "https://aion2.grimvane.app/field-boss-timers/"
ALT_URL = "https://www.aion2timers.com/world-boss-timer/"


def make_web_board(server: str = "Kaisinel") -> QWidget:
    root = QWidget()
    lay = QVBoxLayout(root)
    tip = QLabel(
        f"Tablero web · elige servidor <b>{server}</b> arriba en la página. "
        "La API no publica el feed de kills del servidor; esto es la web oficial "
        "dentro de la app."
    )
    tip.setWordWrap(True)
    lay.addWidget(tip)

    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError:
        lay.addWidget(
            QLabel(
                "QtWebEngine no disponible. Usa el botón "
                "'Tablero servidor (web)' del header."
            )
        )
        return root

    view = QWebEngineView()
    view.setUrl(QUrl(BOARD_URL))
    lay.addWidget(view, 1)

    btns = QHBoxLayout()
    b1 = QPushButton("Field Boss Timers")
    b1.clicked.connect(lambda: view.setUrl(QUrl(BOARD_URL)))
    b2 = QPushButton("World Boss Timer (aion2timers)")
    b2.clicked.connect(lambda: view.setUrl(QUrl(ALT_URL)))
    b3 = QPushButton("Recargar")
    b3.clicked.connect(view.reload)
    btns.addWidget(b1)
    btns.addWidget(b2)
    btns.addWidget(b3)
    btns.addStretch(1)
    lay.addLayout(btns)
    return root
