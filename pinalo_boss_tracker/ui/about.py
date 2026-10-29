"""Diálogo About — logo P + versión."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from .. import __version__
from ..resources import package_data_dir
from .brand import BLUE_TP, PURPLE, TEXT_MUTED, font_display, font_ui


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About · Valkyrium")
        self.setModal(True)
        self.setFixedWidth(320)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(20, 20, 20, 16)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = None
        for name in ("guild_logo.png", "app_icon.png"):
            candidate = package_data_dir() / name
            if candidate.is_file():
                icon = candidate
                break
        if icon is not None:
            pm = QPixmap(str(icon)).scaled(
                96,
                96,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo.setPixmap(pm)
        lay.addWidget(logo)

        title = QLabel("VALKYRIUM")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(font_display(20, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{PURPLE};font-weight:700;")
        lay.addWidget(title)

        by = QLabel("by Pinalo")
        by.setAlignment(Qt.AlignmentFlag.AlignCenter)
        by.setFont(font_ui(12))
        by.setStyleSheet(f"color:{BLUE_TP};font-weight:600;")
        lay.addWidget(by)

        official = QLabel("App oficial de Valkyrium")
        official.setAlignment(Qt.AlignmentFlag.AlignCenter)
        official.setFont(font_ui(11, QFont.Weight.DemiBold))
        official.setStyleSheet(f"color:{BLUE_TP};")
        lay.addWidget(official)

        ver = QLabel(f"Boss Tracker · v{__version__}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(f"color:{TEXT_MUTED};")
        lay.addWidget(ver)

        note = QLabel("AION 2 · overlay live · field bosses EU/NA")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        lay.addWidget(note)

        btn = QPushButton("Cerrar")
        btn.setObjectName("primary")
        btn.clicked.connect(self.accept)
        lay.addWidget(btn)
