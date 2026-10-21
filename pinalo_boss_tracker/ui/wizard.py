"""Wizard de primera vez: región/servidor → facción → overlay."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..models import AppSettings
from ..servers import REGIONS, display_label, resolve_named_server, servers_for_region
from .brand import BLUE_TP, PURPLE, TEXT_MUTED, font_display


class FirstRunWizard(QDialog):
    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Valkyrium · Bienvenida")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.settings = settings
        self._stack = QStackedWidget()
        self._stack.addWidget(self._page_server())
        self._stack.addWidget(self._page_faction())
        self._stack.addWidget(self._page_overlay())

        lay = QVBoxLayout(self)
        head = QLabel("VALKYRIUM")
        head.setFont(font_display(18))
        head.setStyleSheet(f"color:{PURPLE};font-weight:700;")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("by Pinalo · configuración rápida")
        sub.setStyleSheet(f"color:{BLUE_TP};")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(head)
        lay.addWidget(sub)
        lay.addWidget(self._stack, 1)

        self._step = QLabel("Paso 1 / 3")
        self._step.setStyleSheet(f"color:{TEXT_MUTED};")
        lay.addWidget(self._step)

        self._buttons = QDialogButtonBox()
        self._btn_back = self._buttons.addButton(
            "Atrás", QDialogButtonBox.ButtonRole.ActionRole
        )
        self._btn_next = self._buttons.addButton(
            "Siguiente", QDialogButtonBox.ButtonRole.ActionRole
        )
        self._btn_back.clicked.connect(self._go_back)
        self._btn_next.clicked.connect(self._go_next)
        lay.addWidget(self._buttons)
        self._sync_nav()

    def _page_server(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Región y servidor"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Región"))
        self.cb_region = QComboBox()
        self.cb_region.addItems(REGIONS)
        self.cb_region.setCurrentText(self.settings.region or "EU")
        row.addWidget(self.cb_region, 1)
        lay.addLayout(row)

        lay.addWidget(QLabel("Servidor"))
        self.cb_server = QComboBox()
        self.cb_server.setMinimumWidth(280)
        lay.addWidget(self.cb_server)
        self.cb_region.currentTextChanged.connect(self._refill_servers)
        self._refill_servers(self.cb_region.currentText())

        tip = QLabel(
            "El servidor elige el feed live (vivos/HP de tu mundo).\n"
            "La lista de bosses es la misma; cambia quién está up."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        lay.addWidget(tip)
        lay.addStretch(1)
        return w

    def _refill_servers(self, region: str = "EU"):
        fac = getattr(self, "cb_faction", None)
        faction = fac.currentText() if fac else (self.settings.faction or None)
        # En paso 1 aún no hay facción forzada: mostrar ambos
        rows = servers_for_region(region, None)
        want = (self.settings.server or "Kaisinel").strip().lower()
        self.cb_server.blockSignals(True)
        self.cb_server.clear()
        idx = 0
        for i, s in enumerate(rows):
            self.cb_server.addItem(display_label(s), s.server_id)
            self.cb_server.setItemData(i, s.name, Qt.ItemDataRole.UserRole + 1)
            if s.name.lower() == want and (
                not faction or s.faction == faction
            ):
                idx = i
        self.cb_server.setCurrentIndex(idx)
        self.cb_server.blockSignals(False)

    def _page_faction(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("¿Elyos o Asmodian?"))
        self.cb_faction = QComboBox()
        self.cb_faction.addItems(["elyos", "asmodian"])
        self.cb_faction.setCurrentText(self.settings.faction or "elyos")
        lay.addWidget(self.cb_faction)
        tip = QLabel("Filtra los field bosses del overlay y el follow live.")
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        lay.addWidget(tip)
        lay.addStretch(1)
        return w

    def _page_overlay(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Overlay listo"))
        tips = QLabel(
            "• Arrastra el overlay para moverlo (se recuerda la posición)\n"
            "• Rueda = opacidad · Ctrl+rueda = escala\n"
            "• Clic pin = copiar WB · Clic der. = muerto / favorito\n"
            "• Ctrl+Shift+B = mostrar/ocultar"
        )
        tips.setWordWrap(True)
        tips.setStyleSheet(f"color:{TEXT_MUTED};")
        lay.addWidget(tips)
        lay.addStretch(1)
        return w

    def _sync_nav(self):
        i = self._stack.currentIndex()
        n = self._stack.count()
        self._step.setText(f"Paso {i + 1} / {n}")
        self._btn_back.setEnabled(i > 0)
        self._btn_next.setText("Empezar" if i == n - 1 else "Siguiente")

    def _go_back(self):
        self._stack.setCurrentIndex(max(0, self._stack.currentIndex() - 1))
        self._sync_nav()

    def _go_next(self):
        i = self._stack.currentIndex()
        if i == 0:
            self.settings.region = self.cb_region.currentText()
            name = self.cb_server.currentData(Qt.ItemDataRole.UserRole + 1)
            sid = self.cb_server.currentData()
            self.settings.server = str(name or "Kaisinel")
            if sid:
                self.settings.a2tools_server_id = int(sid)
            hit = resolve_named_server(self.settings.server, self.settings.region)
            if hit:
                self.settings.faction = hit.faction
                if hasattr(self, "cb_faction"):
                    self.cb_faction.setCurrentText(hit.faction)
        elif i == 1:
            self.settings.faction = self.cb_faction.currentText()
        if i >= self._stack.count() - 1:
            self.settings.wizard_done = True
            self.settings.overlay_on_start = True
            self.settings.start_in_tray = True
            self.accept()
            return
        self._stack.setCurrentIndex(i + 1)
        self._sync_nav()
