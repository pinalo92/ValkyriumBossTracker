from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ..catalog import bosses, format_tp_label, teleports
from ..engine import (
    build_route,
    format_alive_dead,
    format_countdown,
    format_duration,
    format_tp_number,
    format_wb_clipboard,
    mark_killed,
    mark_seen_alive,
    mark_unavailable,
    refresh_observation,
)
from ..models import Reliability
from ..sources.aion2timers_api import (
    bosses_with_nearest_tp,
    fetch_my_field_boss_timers,
    format_tp_guide,
    observations_from_my_timers,
    resolve_personal_token,
)
from ..sources.a2tools_feed import (
    live_feed_age_ms,
    observations_from_feed,
    resolve_server_id,
    sync_from_a2tools,
)
from ..sources.a2tools_live import A2ToolsLiveBridge, faction_follow_ids
from ..sources.discord_board import sync_from_discord
from ..sources.import_json import JsonKillImportAdapter
from ..sources.status import connection_status
from ..storage import (
    add_history,
    kills_today,
    load_observations,
    load_settings,
    load_tp_numbers,
    recent_history,
    save_settings,
    save_tp_number,
    upsert_observation,
)
from .. import __version__
from ..hotkey import GlobalHotkey
from ..paths import app_dir, is_portable
from ..schedule import next_kaira_window
from ..updater import (
    apply_exe_update,
    apply_zip_update,
    check_update,
    is_onefile_build,
    resolve_manifest_url,
)
from .about import AboutDialog
from .next_target import NextTargetPanel
from .pins import PinStrip, PinsOverlay, make_pins_tab, select_pin_bosses
from .brand import (
    BG_CARD,
    BLUE_P,
    BLUE_TP,
    BORDER,
    CSS_UI,
    PURPLE,
    TEXT,
    TEXT_MUTED,
    font_display,
    font_mono,
    font_ui,
)
from .styles import DARK_QSS
from .toast import show_toast
from .web_board import make_web_board
from .wizard import FirstRunWizard


def _app_icon() -> QIcon:
    """Icono Pinalo (P) empaquetado; fallback dibujado si falta el archivo."""
    from ..resources import package_data_dir

    for name in ("app_icon.ico", "app_icon.png"):
        path = package_data_dir() / name
        if path.is_file():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#1f6feb"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(4, 4, 56, 56)
    p.setPen(QColor(BLUE_P))
    p.setFont(font_display(22, QFont.Weight.Bold))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "P")
    p.end()
    return QIcon(pm)


class _LiveHub(QObject):
    """Puente thread-safe: el WSS habla desde otro hilo → señales Qt."""

    feed = Signal(object)
    status = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Valkyrium · by Pinalo — Boss Tracker")
        self.setWindowIcon(_app_icon())
        self.resize(1280, 820)
        self.settings = load_settings()
        self.observations = load_observations()
        self.route_running = True
        self._overlay: PinsOverlay | None = None
        self._overlay_suppressed = False  # True = usuario ocultó a propósito (atajo/menú)
        self._really_quit = False
        self._live_bridge: A2ToolsLiveBridge | None = None
        self._live_pending: dict | None = None
        self._font_tp = font_mono(16, QFont.Weight.Bold)
        self._font_eta = font_mono(14, QFont.Weight.Bold)
        self._font_boss = font_ui(12, QFont.Weight.DemiBold)
        # Modo juego: ventana oculta; solo overlay + bandeja
        self.settings.start_in_tray = True
        self.settings.overlay_on_start = True
        save_settings(self.settings)
        self.setWindowFlag(Qt.WindowType.Tool, True)  # no ocupa sitio en la barra de tareas
        self._build_ui()
        self._setup_tray()
        # Diferir al event loop: RegisterHotKey no debe tocar UI a medias
        self._hotkey = GlobalHotkey(
            lambda: QTimer.singleShot(0, self.toggle_pins_overlay)
        )
        if not self._hotkey.start():
            self.statusBar().showMessage(
                "Atajo Ctrl+Shift+B no disponible (¿ya en uso? cierra otras instancias)",
                8000,
            )
            show_toast(
                "Atajo",
                "Ctrl+Shift+B ocupado — cierra otro Valkyrium",
                ms=4000,
            )
        if not getattr(self.settings, "wizard_done", False):
            wiz = FirstRunWizard(self.settings, self)
            if wiz.exec():
                save_settings(self.settings)
            else:
                self.settings.wizard_done = True
                save_settings(self.settings)
        self.hide()
        self.refresh_all()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._ui_tick)
        self.timer.start(2_000)
        self.discord_timer = QTimer(self)
        self.discord_timer.timeout.connect(self._discord_auto_tick)
        if self.settings.discord_auto_sync:
            self.discord_timer.start(30_000)
        self.a2tools_timer = QTimer(self)
        self.a2tools_timer.timeout.connect(self._a2tools_auto_tick)
        self._live_hub = _LiveHub(self)
        self._live_hub.feed.connect(self._on_a2tools_live_feed)
        self._live_hub.status.connect(self._on_a2tools_live_status)
        # Coalesce WSS → siguiente tick del event loop (HP lo más fresco posible)
        self._live_paint = QTimer(self)
        self._live_paint.setSingleShot(True)
        self._live_paint.timeout.connect(self._flush_a2tools_live_feed)
        # SQLite no en cada %: batch cada 1.5s
        self._hp_persist = QTimer(self)
        self._hp_persist.setSingleShot(True)
        self._hp_persist.timeout.connect(self._persist_dirty_observations)
        self._dirty_boss_ids: set[str] = set()
        if self.settings.a2tools_auto_sync:
            self.a2tools_timer.start(60_000)
            QTimer.singleShot(400, self._start_a2tools_live)
            QTimer.singleShot(800, lambda: self.on_sync_a2tools(silent=True))
        QTimer.singleShot(200, self._apply_startup_mode)
        QTimer.singleShot(4_000, lambda: self.check_for_updates(silent=True))

    def _card(self) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        return f

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        brand = QLabel("VALKYRIUM")
        brand.setObjectName("title")
        by = QLabel("by Pinalo · Boss Tracker · AION 2")
        by.setObjectName("brandMark")
        s = QLabel("Field bosses · overlay live · EU/NA")
        s.setObjectName("subtitle")
        titles.addWidget(brand)
        titles.addWidget(by)
        titles.addWidget(s)
        header.addLayout(titles, 1)

        from ..servers import REGIONS, display_label, servers_for_region

        self.region = QComboBox()
        self.region.addItems(REGIONS)
        self.region.setCurrentText(self.settings.region or "EU")
        self.faction = QComboBox()
        self.faction.addItems(["elyos", "asmodian"])
        self.faction.setCurrentText(self.settings.faction or "elyos")
        self.server = QComboBox()
        self.server.setMinimumWidth(180)
        self.server.setMaximumWidth(260)
        self._refill_server_combo()
        self.region.currentTextChanged.connect(self._on_region_or_faction)
        self.faction.currentTextChanged.connect(self._on_region_or_faction)
        self.server.currentIndexChanged.connect(self._save_prefs)
        header.addWidget(QLabel("Región"))
        header.addWidget(self.region)
        header.addWidget(QLabel("Servidor"))
        header.addWidget(self.server)
        header.addWidget(QLabel("Facción"))
        header.addWidget(self.faction)
        layout.addLayout(header)

        # Claves API ocultas: solo hacen falta si usas sync (no son el flujo principal)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setText(self.settings.aion2timers_api_key or "")
        self.api_key.editingFinished.connect(self._save_prefs)
        self.api_key.hide()
        self.personal_tok = QLineEdit()
        self.personal_tok.setEchoMode(QLineEdit.EchoMode.Password)
        self.personal_tok.setText(self.settings.aion2timers_personal_token or "")
        self.personal_tok.editingFinished.connect(self._save_prefs)
        self.personal_tok.hide()

        tip = QLabel(
            "<b>Lo esencial:</b> Estado + <b>#TP</b>. "
            "Auto: <b>A2Tools</b> (mismo feed que Event Timers de Kaisinel) en "
            "pestaña <b>Ruta / sync</b>. Discord queda como respaldo."
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # ——— Pestaña principal: izquierda IR AHORA · derecha pins + tabla ———
        simple = QWidget()
        slay = QHBoxLayout(simple)
        slay.setSpacing(12)

        self.next_panel = NextTargetPanel()
        self.next_panel.boss_clicked.connect(self._on_pin_clicked)
        slay.addWidget(self.next_panel, 0)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        self.next_lbl = QLabel("Siguiente: —")
        self.next_lbl.setObjectName("nextTarget")
        self.next_lbl.setWordWrap(True)
        self.next_lbl.hide()  # el panel izquierdo lo sustituye

        pins_bar = QHBoxLayout()
        self._pins_page, self.pin_strip = make_pins_tab()
        self.pin_strip_main = PinStrip()
        self.pin_strip_main.boss_clicked.connect(self._on_pin_clicked)
        self.pin_strip_main.boss_mark_dead.connect(self._on_pin_mark_dead)
        self.pin_strip_main.boss_favorite.connect(self._on_pin_favorite)
        self.pin_strip.boss_clicked.connect(self._on_pin_clicked)
        self.pin_strip.boss_mark_dead.connect(self._on_pin_mark_dead)
        self.pin_strip.boss_favorite.connect(self._on_pin_favorite)
        pins_bar.addWidget(self.pin_strip_main, 1)
        self.btn_overlay = QPushButton("Overlay pins")
        self.btn_overlay.setObjectName("primary")
        self.btn_overlay.setToolTip("Ventana siempre encima: IR AHORA + pins con #TP")
        self.btn_overlay.clicked.connect(self.toggle_pins_overlay)
        pins_bar.addWidget(self.btn_overlay, 0, Qt.AlignmentFlag.AlignTop)
        rlay.addLayout(pins_bar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Boss", "Estado", "# TP", "Teletransporte", "Timer"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(40)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        rlay.addWidget(self.table, 1)

        btns = QHBoxLayout()
        self.btn_alive = QPushButton("VIVO")
        self.btn_alive.setObjectName("ok")
        self.btn_kill = QPushButton("MUERTO")
        self.btn_kill.setObjectName("danger")
        self.btn_miss = QPushButton("¿? desconocido")
        self.btn_web_board = QPushButton("Web Kaisinel")
        self.btn_auto_help = QPushButton("Cómo auto (Discord / A2Tools)")
        self.btn_auto_help.setObjectName("primary")
        self.btn_alive.clicked.connect(self.on_mark_alive)
        self.btn_kill.clicked.connect(self.on_mark_kill)
        self.btn_miss.clicked.connect(self.on_mark_miss)
        self.btn_web_board.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        self.btn_auto_help.clicked.connect(self.on_auto_help)
        for b in (
            self.btn_alive,
            self.btn_kill,
            self.btn_miss,
            self.btn_web_board,
            self.btn_auto_help,
        ):
            btns.addWidget(b)
        rlay.addLayout(btns)
        slay.addWidget(right, 1)

        # ——— Web ———
        # ——— Ruta / extras ———
        extras = QWidget()
        el = QVBoxLayout(extras)
        self.status_lbl = QLabel()
        self.status_lbl.setWordWrap(True)
        el.addWidget(self.status_lbl)
        route_btns = QHBoxLayout()
        self.btn_route = QPushButton("Recalcular ruta")
        self.btn_route.setObjectName("primary")
        self.btn_pause = QPushButton("Pausar auto")
        self.btn_compact = QPushButton("Modo compacto")
        self.btn_sync_live = QPushButton("Sync a2p_ (cuenta)")
        self.btn_sync = QPushButton("Sync catálogo")
        self.btn_import = QPushButton("Importar JSON")
        self.btn_tp_num = QPushButton("Nº TP")
        self.btn_tp_list = QPushButton("Lista TP")
        self.btn_route.clicked.connect(self.refresh_route)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_compact.clicked.connect(self.toggle_compact)
        self.btn_sync_live.clicked.connect(self.on_sync_live)
        self.btn_sync.clicked.connect(self.on_sync_tp)
        self.btn_import.clicked.connect(self.on_import)
        self.btn_tp_num.clicked.connect(self.on_set_tp_number)
        self.btn_tp_list.clicked.connect(self.on_show_all_tps)
        for b in (
            self.btn_route,
            self.btn_pause,
            self.btn_compact,
            self.btn_sync_live,
            self.btn_sync,
            self.btn_import,
            self.btn_tp_num,
            self.btn_tp_list,
        ):
            route_btns.addWidget(b)
        el.addLayout(route_btns)
        keys = QHBoxLayout()
        keys.addWidget(QLabel("a2t_"))
        self.api_key.show()
        self.api_key.setPlaceholderText("Developer key opcional")
        keys.addWidget(self.api_key, 1)
        keys.addWidget(QLabel("a2p_"))
        self.personal_tok.show()
        self.personal_tok.setPlaceholderText("Personal token opcional")
        keys.addWidget(self.personal_tok, 1)
        el.addLayout(keys)

        el.addWidget(QLabel("Auto Kaisinel vía A2Tools (Event Timers / CDN)"))
        a2row = QHBoxLayout()
        self.a2_server_id = QLineEdit()
        sid = self.settings.a2tools_server_id or 0
        self.a2_server_id.setPlaceholderText("serverId (vacío = prefs A2Tools / 1304)")
        self.a2_server_id.setText(str(sid) if sid else "")
        self.a2_server_id.setMaximumWidth(220)
        self.a2_server_id.editingFinished.connect(self._save_prefs)
        self.a2_auto = QCheckBox("Auto cada 60s")
        self.a2_auto.setChecked(bool(self.settings.a2tools_auto_sync))
        self.a2_auto.toggled.connect(self._on_a2tools_auto)
        self.btn_a2tools = QPushButton("Sync A2Tools ahora")
        self.btn_a2tools.setObjectName("primary")
        self.btn_a2tools.clicked.connect(lambda: self.on_sync_a2tools(False))
        a2row.addWidget(self.a2_server_id)
        a2row.addWidget(self.a2_auto)
        a2row.addWidget(self.btn_a2tools)
        a2row.addStretch(1)
        el.addLayout(a2row)

        tray_row = QHBoxLayout()
        self.chk_tray = QCheckBox("Arrancar en bandeja (solo overlay en pantalla)")
        self.chk_tray.setChecked(bool(self.settings.start_in_tray))
        self.chk_tray.toggled.connect(self._save_prefs)
        self.chk_overlay_start = QCheckBox("Abrir overlay al iniciar")
        self.chk_overlay_start.setChecked(bool(self.settings.overlay_on_start))
        self.chk_overlay_start.toggled.connect(self._save_prefs)
        tray_row.addWidget(self.chk_tray)
        tray_row.addWidget(self.chk_overlay_start)
        tray_row.addStretch(1)
        el.addLayout(tray_row)
        mode = "portable → " + str(app_dir()) if is_portable() else "AppData → " + str(app_dir())
        self.data_path_lbl = QLabel(f"Datos: {mode} · v{__version__}")
        self.data_path_lbl.setWordWrap(True)
        self.data_path_lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;font-family:{CSS_UI};")
        el.addWidget(self.data_path_lbl)
        upd_row = QHBoxLayout()
        self.update_url = QLineEdit()
        self.update_url.setPlaceholderText(
            "URL manifiesto update JSON (version + zip)"
        )
        self.update_url.setText(self.settings.update_manifest_url or "")
        self.update_url.editingFinished.connect(self._save_prefs)
        self.btn_update = QPushButton("Buscar actualización")
        self.btn_update.clicked.connect(lambda: self.check_for_updates(silent=False))
        upd_row.addWidget(self.update_url, 1)
        upd_row.addWidget(self.btn_update)
        el.addLayout(upd_row)
        tip_hk = QLabel(
            "Atajo: Ctrl+Shift+B · clic pin = #TP · rueda = opacidad · Ctrl+rueda = escala"
        )
        tip_hk.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;font-family:{CSS_UI};")
        tip_hk.setWordWrap(True)
        el.addWidget(tip_hk)

        el.addWidget(QLabel("Respaldo: Discord (tablero aion2timers)"))
        drow = QHBoxLayout()
        self.discord_tok = QLineEdit()
        self.discord_tok.setEchoMode(QLineEdit.EchoMode.Password)
        self.discord_tok.setPlaceholderText("Bot token Discord")
        self.discord_tok.setText(self.settings.discord_bot_token or "")
        self.discord_tok.editingFinished.connect(self._save_prefs)
        self.discord_ch = QLineEdit()
        self.discord_ch.setPlaceholderText("Channel ID del tablero")
        self.discord_ch.setText(self.settings.discord_channel_id or "")
        self.discord_ch.editingFinished.connect(self._save_prefs)
        self.discord_auto = QCheckBox("Auto cada 30s")
        self.discord_auto.setChecked(bool(self.settings.discord_auto_sync))
        self.discord_auto.toggled.connect(self._on_discord_auto)
        self.btn_discord = QPushButton("Sync Discord ahora")
        self.btn_discord.clicked.connect(lambda: self.on_sync_discord(False))
        drow.addWidget(self.discord_tok, 2)
        drow.addWidget(self.discord_ch, 1)
        drow.addWidget(self.discord_auto)
        drow.addWidget(self.btn_discord)
        el.addLayout(drow)
        self.route_view = QTextEdit()
        self.route_view.setReadOnly(True)
        self.route_view.setAcceptRichText(True)
        el.addWidget(self.route_view, 2)
        self.hist_view = QTextEdit()
        self.hist_view.setReadOnly(True)
        el.addWidget(QLabel("Historial"))
        el.addWidget(self.hist_view, 1)

        self.tabs.addTab(simple, "Vivo / Muerto + TP")
        self.tabs.addTab(self._pins_page, "Pins + #TP")
        self.tabs.addTab(
            make_web_board(self.settings.server or "Kaisinel"),
            "Web Kaisinel",
        )
        self.tabs.addTab(extras, "Ruta / sync")

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Listo")

        act_refresh = QAction("Actualizar", self)
        act_refresh.triggered.connect(self.refresh_all)
        self.addAction(act_refresh)

    def _refill_server_combo(self):
        from ..servers import display_label, servers_for_region

        region = self.region.currentText() if hasattr(self, "region") else "EU"
        faction = self.faction.currentText() if hasattr(self, "faction") else None
        rows = servers_for_region(region, faction)
        want_name = (self.settings.server or "Kaisinel").strip().lower()
        want_id = int(self.settings.a2tools_server_id or 0)
        self.server.blockSignals(True)
        self.server.clear()
        pick = 0
        for i, s in enumerate(rows):
            self.server.addItem(display_label(s), s.server_id)
            self.server.setItemData(i, s.name, Qt.ItemDataRole.UserRole + 1)
            if want_id and s.server_id == want_id:
                pick = i
            elif s.name.lower() == want_name:
                pick = i
        self.server.setCurrentIndex(pick)
        self.server.blockSignals(False)

    def _on_region_or_faction(self, *_args):
        self._refill_server_combo()
        self._save_prefs()

    def _save_prefs(self):
        self.settings.region = self.region.currentText()
        self.settings.faction = self.faction.currentText()
        name = self.server.currentData(Qt.ItemDataRole.UserRole + 1)
        sid = self.server.currentData()
        self.settings.server = str(name or "Kaisinel")
        if sid:
            self.settings.a2tools_server_id = int(sid)
        self.settings.aion2timers_api_key = self.api_key.text().strip()
        self.settings.aion2timers_personal_token = self.personal_tok.text().strip()
        if hasattr(self, "discord_tok"):
            self.settings.discord_bot_token = self.discord_tok.text().strip()
            self.settings.discord_channel_id = self.discord_ch.text().strip()
            self.settings.discord_auto_sync = self.discord_auto.isChecked()
        if hasattr(self, "a2_auto"):
            self.settings.a2tools_auto_sync = self.a2_auto.isChecked()
            # serverId ya viene del desplegable; el campo manual es override opcional
            raw = self.a2_server_id.text().strip()
            if raw:
                try:
                    self.settings.a2tools_server_id = int(raw)
                except ValueError:
                    pass
        if hasattr(self, "chk_tray"):
            self.settings.start_in_tray = self.chk_tray.isChecked()
            self.settings.overlay_on_start = self.chk_overlay_start.isChecked()
        if hasattr(self, "update_url"):
            self.settings.update_manifest_url = self.update_url.text().strip()
        save_settings(self.settings)
        self.refresh_all()

    def _on_discord_auto(self, on: bool):
        self.settings.discord_auto_sync = on
        save_settings(self.settings)
        if on:
            self.discord_timer.start(30_000)
            self.on_sync_discord(silent=True)
        else:
            self.discord_timer.stop()

    def _discord_auto_tick(self):
        if self.settings.discord_auto_sync:
            self.on_sync_discord(silent=True)

    def _any_boss_vivo(self) -> bool:
        return any(
            format_alive_dead(o) == "VIVO" for o in self.observations.values()
        )

    def _any_boss_fighting(self) -> bool:
        return any(
            format_alive_dead(o) == "VIVO" and o.hp is not None
            for o in self.observations.values()
        )

    def _ui_tick(self):
        # En combate el WSS ya pinta HP; aquí solo light refresh / UI completa idle
        if self._any_boss_fighting():
            if self.timer.interval() != 500:
                self.timer.setInterval(500)
            # No recargar DB (pisaría HP en memoria); solo reordenar pins si hace falta
            self._refresh_pins(prefer_patch=True)
        else:
            self.refresh_all()
            if self.timer.interval() != 2_000:
                self.timer.setInterval(2_000)

    def _a2tools_poll_ms(self) -> int:
        # Con WSS activo el CDN solo hace de respaldo lento.
        if self._live_bridge and self._live_bridge.connected:
            return 60_000
        age = live_feed_age_ms()
        if age is not None and age < 120_000:
            return 3_000
        if self._any_boss_vivo():
            return 5_000
        return 60_000

    def _retune_a2tools_timer(self):
        if not self.settings.a2tools_auto_sync:
            return
        ms = self._a2tools_poll_ms()
        if self.a2tools_timer.interval() != ms:
            self.a2tools_timer.setInterval(ms)

    def _start_a2tools_live(self):
        if not self.settings.a2tools_auto_sync:
            return
        sid, _ = resolve_server_id(
            self.settings.a2tools_server_id or None,
            self.settings.server or "Kaisinel",
            region=self.settings.region or "EU",
        )
        ids = faction_follow_ids(self.settings.faction or "elyos")
        if self._live_bridge is None:
            self._live_bridge = A2ToolsLiveBridge(
                on_update=lambda feed: self._live_hub.feed.emit(feed),
                on_status=lambda msg: self._live_hub.status.emit(msg),
            )
        self._live_bridge.start(sid, ids)

    def _stop_a2tools_live(self):
        if self._live_bridge is not None:
            self._live_bridge.stop()
            self._live_bridge = None

    def _on_a2tools_live_status(self, msg: str):
        self.statusBar().showMessage(msg, 4_000)
        if hasattr(self, "tray"):
            self._refresh_tray_tooltip()

    def _on_a2tools_live_feed(self, feed: object):
        if not isinstance(feed, dict):
            return
        self._live_pending = feed
        # 0 ms = siguiente vuelta del event loop (agrupa ráfagas sin retrasar HP)
        if not self._live_paint.isActive():
            self._live_paint.start(0)

    def _merge_hp_keep(self, obs, prev) -> None:
        """No borrar HP de combate si el feed llega sin % (misma vida)."""
        if prev is None:
            return
        if (
            obs.hp is None
            and prev.hp is not None
            and format_alive_dead(obs) == "VIVO"
            and format_alive_dead(prev) == "VIVO"
        ):
            obs.hp = prev.hp
            return
        # Si llega HP, siempre gana el del feed (más fiel al meter)
        if obs.hp is not None:
            return

    def _persist_dirty_observations(self):
        ids = list(self._dirty_boss_ids)
        self._dirty_boss_ids.clear()
        for bid in ids:
            obs = self.observations.get(bid)
            if obs is not None:
                upsert_observation(obs)

    def _flush_a2tools_live_feed(self):
        feed = self._live_pending
        self._live_pending = None
        if not isinstance(feed, dict):
            return
        try:
            obs_list, _note = observations_from_feed(
                feed,
                faction=self.settings.faction or "elyos",
                source="a2tools-live-wss",
            )
        except Exception as e:
            self.statusBar().showMessage(f"live: {e}")
            return
        hp_changed = False
        for obs in obs_list:
            prev = self.observations.get(obs.boss_id)
            self._merge_hp_keep(obs, prev)
            state_changed = (
                prev is None
                or prev.reliability != obs.reliability
                or prev.killed_at != obs.killed_at
                or (prev.hp is None) != (obs.hp is None)
            )
            hp_changed = hp_changed or (prev is None or prev.hp != obs.hp)
            self.observations[obs.boss_id] = obs
            if state_changed:
                upsert_observation(obs)
            else:
                # Solo %: memoria + persistencia diferida
                self._dirty_boss_ids.add(obs.boss_id)
        if self._dirty_boss_ids and not self._hp_persist.isActive():
            self._hp_persist.start(1_500)
        # Solo pins (patch in-place si el set no cambia)
        self._refresh_pins(prefer_patch=True)
        self._retune_a2tools_timer()

    def _on_a2tools_auto(self, on: bool):
        self.settings.a2tools_auto_sync = on
        save_settings(self.settings)
        if on:
            self.a2tools_timer.start(self._a2tools_poll_ms())
            self._start_a2tools_live()
            self.on_sync_a2tools(silent=True)
        else:
            self.a2tools_timer.stop()
            self._stop_a2tools_live()

    def _a2tools_auto_tick(self):
        if self.settings.a2tools_auto_sync:
            self.on_sync_a2tools(silent=True)
            self._retune_a2tools_timer()
            # Mantener follow por si cambió facción/server
            if self._live_bridge:
                sid, _ = resolve_server_id(
                    self.settings.a2tools_server_id or None,
                    self.settings.server or "Kaisinel",
                    region=self.settings.region or "EU",
                )
                if sid != self._live_bridge._server:
                    self._stop_a2tools_live()
                    self._start_a2tools_live()
                else:
                    self._live_bridge.set_follow(
                        faction_follow_ids(self.settings.faction or "elyos")
                    )

    def on_sync_a2tools(self, silent: bool = False):
        self._save_prefs()
        sid = self.settings.a2tools_server_id or None
        # Con live fresco no hace falta CDN (evita pisar HP real con null).
        age = live_feed_age_ms()
        allow_cdn = age is None or age >= 120_000
        try:
            obs_list, note, used = sync_from_a2tools(
                server_id=sid,
                server_name=self.settings.server or "Kaisinel",
                faction=self.settings.faction or "elyos",
                allow_cdn=allow_cdn,
                region=self.settings.region or "EU",
            )
            for obs in obs_list:
                prev = self.observations.get(obs.boss_id)
                self._merge_hp_keep(obs, prev)
                upsert_observation(obs)
                self.observations[obs.boss_id] = obs
            add_history("sync_a2tools", detail=note[:200])
            self.refresh_all()
            self._retune_a2tools_timer()
            if not silent:
                QMessageBox.information(self, "A2Tools", note)
            else:
                self.statusBar().showMessage(note)
            if hasattr(self, "a2_server_id") and not self.a2_server_id.text().strip():
                # muestra el id resuelto sin forzar guardarlo
                self.a2_server_id.setPlaceholderText(f"auto → {used}")
        except Exception as e:
            if not silent:
                QMessageBox.warning(self, "A2Tools", str(e))
            else:
                self.statusBar().showMessage(f"A2Tools: {e}")

    def on_auto_help(self):
        QMessageBox.information(
            self,
            "Auto vivos/muertos (sin leer memoria del juego)",
            "Opción A — A2Tools → esta app (recomendada):\n"
            "1. A2Tools instalado + Event Timers (ya lo tienes)\n"
            "2. Advanced → Share field boss timers ON\n"
            "3. Aquí: Ruta / sync → Sync A2Tools (o Auto cada 60s)\n"
            "   Lee el mismo tablero CDN de Kaisinel (serverId 1304)\n"
            "   y rellena Vivo/Muerto + #TP.\n\n"
            "Opción B — Discord → esta app:\n"
            "1. Canal + aion2timers.com/discord-alerts (Kaisinel)\n"
            "2. Bot con Read Message History\n"
            "3. Ruta / sync → Sync Discord + Auto 30s\n\n"
            "La API a2t_ sola NO trae el tablero del servidor.",
        )

    def on_sync_discord(self, silent: bool = False):
        self._save_prefs()
        tok = self.settings.discord_bot_token.strip()
        ch = self.settings.discord_channel_id.strip()
        if not tok or not ch:
            if not silent:
                self.on_auto_help()
            return
        try:
            obs_list, note = sync_from_discord(tok, ch)
            for obs in obs_list:
                upsert_observation(obs)
                self.observations[obs.boss_id] = obs
            add_history("sync_discord", detail=note[:200])
            self.refresh_all()
            if not silent:
                QMessageBox.information(self, "Discord", note)
            else:
                self.statusBar().showMessage(note)
        except Exception as e:
            if not silent:
                QMessageBox.warning(self, "Discord", str(e))
            else:
                self.statusBar().showMessage(f"Discord: {e}")

    def _zone_for_region(self) -> str:
        return {
            "EU": "Europe/Berlin",
            "NA_EAST": "America/New_York",
            "NA_WEST": "America/Los_Angeles",
        }.get(self.settings.region, "Europe/Berlin")

    def on_sync_tp(self):
        self._save_prefs()
        try:
            text = format_tp_guide(
                faction=self.settings.faction,
                api_key=self.settings.aion2timers_api_key or None,
            )
            self.route_view.setPlainText(text)
            _, note = bosses_with_nearest_tp(self.settings.aion2timers_api_key or None)
            self.statusBar().showMessage(note)
            add_history("sync_a2t", detail=note[:200])
        except Exception as e:
            QMessageBox.warning(
                self,
                "Aion2Timers",
                f"No se pudo sincronizar.\n\n{e}\n\n"
                "Crea una developer key a2t_ en aion2.grimvane.app "
                "(Developers) y pégala arriba.",
            )

    def on_open_server_board(self):
        import webbrowser

        srv = self.settings.server or "Kaisinel"
        webbrowser.open("https://www.aion2timers.com/world-boss-timer/")
        QMessageBox.information(
            self,
            "Tablero del servidor",
            f"Tu servidor: {srv} (EU · Elyos · pareja Lumiel)\n\n"
            f"1. Change server → elige {srv}\n"
            "2. Mira Status / Respawn: muertos y cuenta atrás\n"
            "3. Datos del DPS meter + Share kills de ese servidor\n\n"
            "La API no trae ese tablero. Si confirmas una muerte, "
            "Marcar MUERTO aquí para #TP + timer.",
        )

    def on_sync_live(self):
        self._save_prefs()
        tok = resolve_personal_token(self.settings.aion2timers_personal_token or None)
        if not tok:
            QMessageBox.information(
                self,
                "Vivos / muertos",
                "Para ver vivos y muertos de forma automática:\n\n"
                "1. Entra en https://aion2.grimvane.app/timers/\n"
                "2. Cuenta completa → Personal tokens → crea a2p_...\n"
                "3. Pega el token en el campo a2p_ de esta app\n"
                "4. En aion2timers.com elige TU servidor y usa el meter "
                "o marca kills (Share my kills)\n\n"
                "Sin eso: usa Marcar VIVO / MUERTO (el listado Field Boss "
                "del juego es la verdad de tu servidor).\n\n"
                "No leemos memoria del juego ni inventamos un feed global.",
            )
            return
        try:
            remote = fetch_my_field_boss_timers(tok, zone=self._zone_for_region())
            obs_list, note = observations_from_my_timers(remote)
            for obs in obs_list:
                upsert_observation(obs)
                self.observations[obs.boss_id] = obs
            add_history("sync_live", detail=note[:200])
            self.refresh_all()
            QMessageBox.information(self, "Sync vivos/muertos", note)
        except Exception as e:
            QMessageBox.warning(
                self,
                "Sync vivos/muertos",
                f"Falló /me/timers.\n\n{e}\n\n"
                "El token debe ser personal a2p_ (no la developer key a2t_).",
            )

    def _selected_boss_id(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def on_mark_alive(self):
        bid = self._selected_boss_id()
        if not bid:
            return
        boss = bosses()[bid]
        obs = mark_seen_alive(boss)
        upsert_observation(obs)
        self.observations[bid] = obs
        add_history("seen_alive", bid)
        self.refresh_all()

    def on_mark_kill(self):
        bid = self._selected_boss_id()
        if not bid:
            return
        boss = bosses()[bid]
        obs = mark_killed(boss)
        upsert_observation(obs)
        self.observations[bid] = obs
        add_history("kill", bid)
        self.refresh_all()

    def on_mark_miss(self):
        bid = self._selected_boss_id()
        if not bid:
            return
        boss = bosses()[bid]
        obs = mark_unavailable(boss)
        upsert_observation(obs)
        self.observations[bid] = obs
        add_history("unavailable", bid)
        self.refresh_all()

    def on_show_all_tps(self):
        overrides = load_tp_numbers()
        tps = list(teleports(overrides).values())
        tps.sort(
            key=lambda t: (
                t.map_number is None,
                t.map_number if t.map_number is not None else 999,
                t.name,
            )
        )
        known = sum(1 for t in tps if t.map_number is not None)
        lines = [
            f"Kibelisks Verteron: {len([t for t in tps if t.map_id=='verteron'])} "
            f"(#{known} numerados de la Lista general; el resto ¿?)\n"
            "El juego tiene ~61. Manda capturas bajando el scroll para completar #.\n"
        ]
        for t in tps:
            if t.map_id != "verteron":
                continue
            lines.append(format_tp_label(t))
        self.route_view.setPlainText("\n".join(lines))

    def on_set_tp_number(self):
        bid = self._selected_boss_id()
        if not bid:
            QMessageBox.information(self, "Nº TP", "Selecciona un boss en la tabla.")
            return
        boss = bosses()[bid]
        overrides = load_tp_numbers()
        tp = teleports(overrides).get(boss.nearest_tp_id)
        if not tp:
            QMessageBox.warning(self, "Nº TP", "Este boss no tiene TP en el catálogo.")
            return
        hint = tp.name_en or tp.name
        current = tp.map_number if tp.map_number is not None else 0
        num, ok = QInputDialog.getInt(
            self,
            "Número de Kibelisk (mapa del juego)",
            f"Abre el mapa mundial → lista de TP.\n"
            f"Busca: {hint}\n"
            f"Y pon aquí el número que muestra el juego para:\n{tp.name}",
            current,
            1,
            200,
        )
        if not ok:
            return
        save_tp_number(tp.id, num)
        add_history("tp_number", boss_id=bid, detail=f"{tp.id}=#{num}")
        self.refresh_all()

    def on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar kills JSON", "", "JSON (*.json)"
        )
        if not path:
            return
        adapter = JsonKillImportAdapter(Path(path))
        events = adapter.fetch()
        from ..engine import mark_killed as mk

        catalog = bosses()
        n = 0
        for ev in events:
            if ev.boss_id not in catalog:
                continue
            if ev.reliability == Reliability.CONFIRMED_ALIVE:
                obs = mark_seen_alive(catalog[ev.boss_id], source=ev.source)
                obs.updated_at = ev.updated_at
            else:
                obs = mk(catalog[ev.boss_id], when=ev.killed_at, source=ev.source)
            upsert_observation(obs)
            self.observations[ev.boss_id] = obs
            n += 1
        add_history("import", detail=f"{n} eventos")
        QMessageBox.information(self, "Import", f"Importados {n} eventos.")
        self.refresh_all()

    def toggle_pause(self):
        self.route_running = not self.route_running
        self.btn_pause.setText("Reanudar auto" if not self.route_running else "Pausar auto")
        if self.route_running:
            self.timer.start(1_000 if self._any_boss_fighting() else 2_000)
        else:
            self.timer.stop()

    def toggle_compact(self):
        if self.width() > 700:
            self.resize(480, 720)
            self.settings.compact_mode = True
        else:
            self.resize(1280, 820)
            self.settings.compact_mode = False
        save_settings(self.settings)

    def refresh_all(self):
        self.observations = load_observations()
        st = connection_status(
            self.settings.aion2timers_api_key or None,
            self.settings.aion2timers_personal_token or None,
        )
        self.status_lbl.setText(
            f"<b>Conexión</b><br>"
            f"Juego: {st.game}<br>"
            f"Timers web: {st.timers_site}<br>"
            f"DPS meter: {st.dps_meter}<br>"
            f"Catálogo: {st.catalog}<br>"
            f"<i>{st.detail}</i><br>"
            f"Región <b>{self.settings.region}</b> · "
            f"Servidor <b>{self.settings.server or 'Kaisinel'}</b> · "
            f"Facción <b>{self.settings.faction}</b>"
        )
        self._fill_table()
        self._refresh_pins()
        self.refresh_route()
        self._fill_history()
        self.statusBar().showMessage("Actualizado")

    def _refresh_pins(self, prefer_patch: bool = False):
        items = select_pin_bosses(self.settings, self.observations)
        if hasattr(self, "pin_strip_main"):
            if prefer_patch and self.pin_strip_main.patch_pins(items):
                pass
            else:
                self.pin_strip_main.set_pins(items)
        if hasattr(self, "pin_strip"):
            if prefer_patch and self.pin_strip.patch_pins(items):
                pass
            else:
                self.pin_strip.set_pins(items)
        if self._overlay is not None and self._overlay.isVisible():
            if prefer_patch:
                self._overlay.patch_pins(items)
            else:
                self._overlay.update_pins(items)
            self._overlay.update_next(self.settings, self.observations)
        if hasattr(self, "next_panel"):
            self.next_panel.update_from_route(self.settings, self.observations)

    def _live_dot_label(self) -> str:
        bridge = getattr(self, "_live_bridge", None)
        if bridge is not None and bridge.connected:
            return "● conectado"
        age = live_feed_age_ms()
        if age is not None and age < 30_000:
            return "● feed fresco"
        return "○ desconectado"

    def _kaira_menu_label(self) -> str:
        from ..models import utcnow

        now = utcnow()
        start, end = next_kaira_window(self.settings.region or "EU", now)
        if start <= now <= end:
            left = max(0, int((end - now).total_seconds()))
            m, s = divmod(left, 60)
            return f"Kaira · VENTANA {m:02d}:{s:02d}"
        secs = max(0, int((start - now).total_seconds()))
        h, rem = divmod(secs, 3600)
        m, _ = divmod(rem, 60)
        if h > 0:
            return f"Kaira · en {h}h {m:02d}m"
        return f"Kaira · en {m} min"

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(_app_icon())
        self._refresh_tray_tooltip()
        self._tray_menu = QMenu()
        self._tray_menu.aboutToShow.connect(self._rebuild_tray_menu)
        self.tray.setContextMenu(self._tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self._rebuild_tray_menu()

    def _refresh_tray_tooltip(self):
        fac = (self.settings.faction or "elyos").capitalize()
        srv = self.settings.server or "—"
        self.tray.setToolTip(
            f"Valkyrium · {self._live_dot_label()} · {srv} · {fac}"
        )

    def _rebuild_tray_menu(self):
        menu = self._tray_menu
        menu.clear()
        live = self._live_dot_label()
        srv = self.settings.server or "—"
        fac = self.settings.faction or "—"
        reg = self.settings.region or "EU"

        hdr = QWidgetAction(menu)
        panel = QWidget(menu)
        panel.setStyleSheet(
            f"QWidget{{background:{BG_CARD};color:{TEXT};padding:4px;}}"
            f"QLabel{{font-family:{CSS_UI};}}"
        )
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        t1 = QLabel(f"{live}")
        t1.setStyleSheet(
            f"color:{'#5fe08a' if '●' in live else TEXT_MUTED};font-weight:700;font-size:12px;"
        )
        t2 = QLabel(f"{srv} · {reg}")
        t2.setStyleSheet(f"color:{PURPLE};font-weight:600;font-size:12px;")
        t3 = QLabel(f"Facción: {fac}")
        t3.setStyleSheet(f"color:{BLUE_TP};font-size:11px;")
        t4 = QLabel(self._kaira_menu_label())
        t4.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        for w in (t1, t2, t3, t4):
            lay.addWidget(w)
        hdr.setDefaultWidget(panel)
        menu.addAction(hdr)
        menu.addSeparator()

        act_show = QAction("Ajustes (ventana)", self)
        act_show.triggered.connect(self.show_from_tray)
        act_overlay = QAction("Mostrar / ocultar overlay (Ctrl+Shift+B)", self)
        act_overlay.triggered.connect(self.toggle_pins_overlay)
        menu.addAction(act_show)
        menu.addAction(act_overlay)
        menu.addSeparator()
        menu.addAction(self._tray_appearance_action(menu))
        menu.addSeparator()

        kills = kills_today(12)
        kills_menu = menu.addMenu(f"Kills del día ({len(kills)})")
        if not kills:
            kills_menu.addAction("(ninguno aún)").setEnabled(False)
        else:
            catalog = bosses()
            for row in kills:
                bid = row.get("boss_id") or ""
                boss = catalog.get(bid)
                name = boss.name_es if boss else bid or "?"
                ts = (row.get("ts") or "")[11:16]
                kills_menu.addAction(f"{ts}  {name}").setEnabled(False)

        menu.addSeparator()
        act_sync = QAction("Sync A2Tools", self)
        act_sync.triggered.connect(lambda: self.on_sync_a2tools(True))
        act_upd = QAction("Buscar actualización…", self)
        act_upd.triggered.connect(lambda: self.check_for_updates(silent=False))
        act_about = QAction("About · Valkyrium…", self)
        act_about.triggered.connect(self._show_about)
        act_quit = QAction("Salir", self)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_sync)
        menu.addAction(act_upd)
        menu.addAction(act_about)
        menu.addSeparator()
        menu.addAction(act_quit)
        self._refresh_tray_tooltip()

    def _show_about(self):
        AboutDialog(self).exec()

    def _tray_appearance_action(self, parent_menu: QMenu) -> QWidgetAction:
        panel = QWidget(parent_menu)
        panel.setStyleSheet(
            f"QWidget{{background:{BG_CARD};color:{TEXT};font-family:{CSS_UI};}}"
            f"QLabel{{color:{TEXT_MUTED};font-size:11px;}}"
            f"QSlider::groove:horizontal{{height:4px;background:{BORDER};border-radius:2px;}}"
            f"QSlider::handle:horizontal{{width:12px;margin:-5px 0;background:{PURPLE};border-radius:6px;}}"
        )
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        scale0 = float(getattr(self.settings, "overlay_scale", 1.0) or 1.0)
        opac0 = float(getattr(self.settings, "overlay_opacity", 1.0) or 1.0)

        self._lbl_tray_scale = QLabel(f"Escala  {int(round(scale0 * 100))}%")
        self._slider_scale = QSlider(Qt.Orientation.Horizontal)
        self._slider_scale.setRange(50, 180)
        self._slider_scale.setValue(int(round(scale0 * 100)))
        self._slider_scale.valueChanged.connect(self._on_tray_scale)

        self._lbl_tray_opacity = QLabel(f"Opacidad  {int(round(opac0 * 100))}%")
        self._slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self._slider_opacity.setRange(30, 100)
        self._slider_opacity.setValue(int(round(opac0 * 100)))
        self._slider_opacity.valueChanged.connect(self._on_tray_opacity)

        tip = QLabel("En overlay: rueda = opacidad · Ctrl+rueda = escala")
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")

        lay.addWidget(self._lbl_tray_scale)
        lay.addWidget(self._slider_scale)
        lay.addWidget(self._lbl_tray_opacity)
        lay.addWidget(self._slider_opacity)
        lay.addWidget(tip)

        act = QWidgetAction(parent_menu)
        act.setDefaultWidget(panel)
        return act

    def _on_tray_scale(self, value: int):
        scale = max(0.5, min(1.8, value / 100.0))
        self.settings.overlay_scale = scale
        if hasattr(self, "_lbl_tray_scale"):
            self._lbl_tray_scale.setText(f"Escala  {value}%")
        if self._overlay is not None:
            self._overlay.set_appearance(scale=scale)
        self._save_appearance()

    def _on_tray_opacity(self, value: int):
        opacity = max(0.30, min(1.0, value / 100.0))
        self.settings.overlay_opacity = opacity
        if hasattr(self, "_lbl_tray_opacity"):
            self._lbl_tray_opacity.setText(f"Opacidad  {value}%")
        if self._overlay is not None:
            self._overlay.set_appearance(opacity=opacity)
        self._save_appearance()

    def _save_appearance(self):
        save_settings(self.settings)

    def _on_overlay_appearance(self, scale: float, opacity: float):
        self.settings.overlay_scale = scale
        self.settings.overlay_opacity = opacity
        if hasattr(self, "_slider_scale"):
            self._slider_scale.blockSignals(True)
            self._slider_scale.setValue(int(round(scale * 100)))
            self._slider_scale.blockSignals(False)
            self._lbl_tray_scale.setText(f"Escala  {int(round(scale * 100))}%")
        if hasattr(self, "_slider_opacity"):
            self._slider_opacity.blockSignals(True)
            self._slider_opacity.setValue(int(round(opacity * 100)))
            self._slider_opacity.blockSignals(False)
            self._lbl_tray_opacity.setText(f"Opacidad  {int(round(opacity * 100))}%")
        self._save_appearance()
        self.statusBar().showMessage(
            f"Overlay {int(round(scale * 100))}% · opacidad {int(round(opacity * 100))}%",
            2000,
        )

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_from_tray()
        # clic simple: no hace nada (evita quitar el overlay sin querer)

    def _apply_startup_mode(self):
        self.hide()
        self.show_pins_overlay()

    def show_from_tray(self):
        self.setWindowFlag(Qt.WindowType.Tool, False)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self._really_quit = True
        if hasattr(self, "_hotkey"):
            self._hotkey.stop()
        self._stop_a2tools_live()
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None
        self.tray.hide()
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if not self._really_quit and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
            self.setWindowFlag(Qt.WindowType.Tool, True)
            # Reabrir overlay solo si el usuario no lo ocultó a propósito
            if not self._overlay_suppressed and (
                self._overlay is None or not self._overlay.isVisible()
            ):
                self.show_pins_overlay()
            return
        self._stop_a2tools_live()
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None
        super().closeEvent(event)

    def show_pins_overlay(self):
        self._overlay_suppressed = False
        items = select_pin_bosses(self.settings, self.observations)
        if self._overlay is not None:
            self._overlay.update_pins(items)
            self._overlay.update_next(self.settings, self.observations)
            if not self._overlay.isVisible():
                self._overlay.show()
            self._overlay.raise_()
            if hasattr(self, "btn_overlay"):
                self.btn_overlay.setText("Cerrar overlay")
            return
        self._overlay = PinsOverlay(
            scale=float(getattr(self.settings, "overlay_scale", 1.0) or 1.0),
            opacity=float(getattr(self.settings, "overlay_opacity", 1.0) or 1.0),
        )
        self._overlay.closed.connect(self._on_overlay_closed)
        self._overlay.appearance_changed.connect(self._on_overlay_appearance)
        self._overlay.position_changed.connect(self._on_overlay_position)
        self._overlay.strip.boss_clicked.connect(self._on_pin_clicked)
        self._overlay.strip.boss_mark_dead.connect(self._on_pin_mark_dead)
        self._overlay.strip.boss_favorite.connect(self._on_pin_favorite)
        self._overlay.update_pins(items)
        self._overlay.update_next(self.settings, self.observations)
        ox = getattr(self.settings, "overlay_x", None)
        oy = getattr(self.settings, "overlay_y", None)
        if ox is not None and oy is not None:
            self._overlay.move(int(ox), int(oy))
        self._overlay.show()
        self._overlay.raise_()
        if hasattr(self, "btn_overlay"):
            self.btn_overlay.setText("Cerrar overlay")

    def _on_overlay_position(self, x: int, y: int):
        self.settings.overlay_x = int(x)
        self.settings.overlay_y = int(y)
        save_settings(self.settings)

    def _on_overlay_closed(self):
        self._overlay = None
        if hasattr(self, "btn_overlay"):
            self.btn_overlay.setText("Overlay pins")
        # Solo reabrir si se cerró solo (crash/X) — no si el usuario lo ocultó
        if self._overlay_suppressed or self._really_quit:
            return
        if not self.isVisible():
            QTimer.singleShot(300, self.show_pins_overlay)

    def toggle_pins_overlay(self):
        if self._overlay is not None and self._overlay.isVisible():
            self._overlay_suppressed = True
            self._overlay.hide()
            if hasattr(self, "btn_overlay"):
                self.btn_overlay.setText("Overlay pins")
            show_toast("Overlay", "Oculto · Ctrl+Shift+B para mostrar", ms=1600)
            return
        self.show_pins_overlay()
        show_toast("Overlay", "Visible · Ctrl+Shift+B para ocultar", ms=1600)

    def _on_pin_clicked(self, boss_id: str):
        boss = bosses().get(boss_id)
        if boss is None:
            return
        overrides = load_tp_numbers()
        from ..engine import tp_for

        tp = tp_for(boss, overrides)
        text = format_wb_clipboard(boss, tp)
        QGuiApplication.clipboard().setText(text)
        msg = f"Copiado: {text}"
        self.statusBar().showMessage(msg, 4000)
        show_toast("Valkyrium", text, ms=2200)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == boss_id:
                self.table.selectRow(row)
                break

    def _on_pin_favorite(self, boss_id: str):
        favs = list(self.settings.favorite_boss_ids or [])
        boss = bosses().get(boss_id)
        name = boss.name_es if boss else boss_id
        if boss_id in favs:
            favs = [x for x in favs if x != boss_id]
            show_toast("Favorito", f"Quitado: {name}", ms=1800)
        else:
            favs.append(boss_id)
            show_toast("Favorito ★", f"Siempre visible: {name}", ms=1800)
        self.settings.favorite_boss_ids = favs
        save_settings(self.settings)
        self.refresh_all()

    def _on_pin_mark_dead(self, boss_id: str):
        boss = bosses().get(boss_id)
        if boss is None:
            return
        obs = mark_killed(boss, source="manual-overlay")
        self.observations[boss_id] = obs
        upsert_observation(obs)
        add_history("killed", boss_id, "manual-overlay")
        self.refresh_all()
        self.statusBar().showMessage(f"Marcado muerto: {boss.name_es}", 4000)
        show_toast("Muerto", boss.name_es, ms=1800)

    def check_for_updates(self, silent: bool = True):
        import sys

        root = Path(app_dir())
        # En portable app_dir es data/; el exe está un nivel arriba
        portable_root = root.parent if (root.name == "data" and is_portable()) else root
        if is_portable() and (
            (portable_root / "PinaloBossTracker.exe").exists()
            or (portable_root / "ValkyriumBossTracker.exe").exists()
        ):
            pass
        elif is_portable():
            portable_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
        url = resolve_manifest_url(
            portable_root if is_portable() else root,
            self.settings.update_manifest_url or "",
        )
        if not url:
            if not silent:
                QMessageBox.information(
                    self,
                    "Actualizaciones",
                    "No hay URL de manifiesto de actualizaciones.",
                )
            return
        try:
            info = check_update(url, current=__version__)
        except RuntimeError as e:
            if not silent:
                QMessageBox.warning(self, "Actualizaciones", str(e))
            return
        if info is None or not info.available:
            if not silent:
                QMessageBox.information(
                    self,
                    "Actualizaciones",
                    f"Ya estás en la última versión (v{__version__}).",
                )
            return
        if silent:
            show_toast(
                "Actualización",
                f"v{info.version} disponible · menú bandeja → Buscar actualización",
                ms=4500,
            )
            return
        notes = f"\n\n{info.notes}" if info.notes else ""
        ans = QMessageBox.question(
            self,
            "Actualización disponible",
            f"v{info.current} → v{info.version}{notes}\n\n¿Descargar e instalar ahora?",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        onefile = is_onefile_build()
        try:
            if onefile:
                if not info.exe_url:
                    raise RuntimeError("El manifiesto no tiene exe_url para el EXE portable")
                bat = apply_exe_update(info.exe_url, Path(sys.executable))
                workdir = Path(sys.executable).resolve().parent
            else:
                if not info.url:
                    raise RuntimeError("El manifiesto no tiene url (zip)")
                bat = apply_zip_update(info.url, portable_root)
                workdir = portable_root
        except Exception as e:
            QMessageBox.warning(self, "Actualizaciones", f"Fallo al descargar: {e}")
            return
        QMessageBox.information(
            self,
            "Actualizaciones",
            "Descarga lista. Se cerrará la app y se aplicará la actualización.",
        )
        self._really_quit = True
        if hasattr(self, "_hotkey"):
            self._hotkey.stop()
        from PySide6.QtCore import QProcess

        QProcess.startDetached(str(bat), [], str(workdir))
        QApplication.instance().quit()

    def _fill_table(self):
        catalog = bosses()
        tps = teleports(load_tp_numbers())
        rows = []
        for bid, boss in catalog.items():
            if self.settings.faction == "elyos" and boss.faction == "asmodian":
                continue
            if self.settings.faction == "asmodian" and boss.faction == "elyos":
                continue
            obs = refresh_observation(boss, self.observations.get(bid), self.settings)
            tp = tps.get(boss.nearest_tp_id)
            rows.append((boss, obs, tp))

        order = {
            Reliability.CONFIRMED_ALIVE: 0,
            Reliability.PREDICTED_SPAWN: 1,
            Reliability.KILL_RECORDED: 2,
            Reliability.STALE: 3,
            Reliability.UNKNOWN: 4,
        }

        def sort_key(r):
            boss, obs, _tp = r
            ready = 99999.0
            if obs.reliability == Reliability.CONFIRMED_ALIVE:
                ready = 0.0
            elif obs.predicted_ready_at:
                from ..engine import minutes_until

                ready = max(0.0, minutes_until(obs.predicted_ready_at) or 0.0)
            return (order.get(obs.reliability, 9), ready, boss.name_es)

        rows.sort(key=sort_key)

        self.table.setRowCount(len(rows))
        status_bg = {
            "VIVO": QColor("#1f5c3a"),
            "MUERTO": QColor("#5c1f1f"),
            "VENTANA": QColor("#6b4f1d"),
            "¿?": QColor("#1a222d"),
        }
        status_fg = {
            "VIVO": QColor("#3fb950"),
            "MUERTO": QColor("#ff7b72"),
            "VENTANA": QColor("#ffb454"),
            "¿?": QColor("#8b949e"),
        }
        for i, (boss, obs, tp) in enumerate(rows):
            st = format_alive_dead(obs)
            name_item = QTableWidgetItem(boss.name_es)
            name_item.setData(Qt.ItemDataRole.UserRole, boss.id)
            name_item.setFont(self._font_boss)

            estado = QTableWidgetItem(st)
            estado.setFont(self._font_eta)
            estado.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            estado.setForeground(status_fg.get(st, QColor("#8b949e")))

            tp_num = QTableWidgetItem(format_tp_number(tp))
            tp_num.setFont(self._font_tp)
            tp_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tp_num.setForeground(QColor(BLUE_TP))

            tp_name = QTableWidgetItem(tp.name if tp else "—")
            eta = QTableWidgetItem(format_countdown(obs))
            eta.setFont(self._font_eta)

            self.table.setItem(i, 0, name_item)
            self.table.setItem(i, 1, estado)
            self.table.setItem(i, 2, tp_num)
            self.table.setItem(i, 3, tp_name)
            self.table.setItem(i, 4, eta)

            bg = status_bg.get(st)
            if bg:
                for c in range(5):
                    it = self.table.item(i, c)
                    if it:
                        it.setBackground(bg)

    def refresh_route(self):
        route = build_route(self.settings, self.observations)
        catalog = bosses()
        tps = teleports(load_tp_numbers())
        if not route:
            self.next_lbl.setText("Siguiente: sin objetivos — marca muertes o VIVO")
            self.route_view.setHtml("<p>Sin objetivos con los filtros actuales.</p>")
            return

        first = route[0]
        fb = catalog[first.boss_id]
        ftp = tps.get(first.nearest_tp_id)
        fobs = refresh_observation(fb, self.observations.get(fb.id), self.settings)
        self.next_lbl.setText(
            f"{format_alive_dead(fobs)}  ·  {fb.name_es}  ·  "
            f"TP {format_tp_number(ftp)}  {ftp.name if ftp else '—'}  ·  "
            f"{format_countdown(fobs)}"
        )

        html = [
            "<style>"
            f"body{{color:{TEXT};font-family:{CSS_UI};font-size:13px;}}"
            f".n{{color:{BLUE_TP};font-family:'Cascadia Mono';font-size:18px;font-weight:700;}}"
            f".t{{color:#ffb454;font-family:'Cascadia Mono';font-size:15px;font-weight:700;}}"
            ".card{background:#171d25;border:1px solid #2a3441;border-radius:8px;"
            "padding:10px 12px;margin:0 0 10px 0;}"
            ".muted{color:#9aa7b8;font-size:12px;}"
            "</style>",
            "<p class='muted'>Ruta por espera + viaje · #TP = Lista general del mapa</p>",
        ]
        for stop in route:
            boss = catalog[stop.boss_id]
            tp = tps.get(stop.nearest_tp_id)
            obs = refresh_observation(boss, self.observations.get(boss.id), self.settings)
            ready = format_countdown(obs)
            travel = format_duration(stop.est_travel_minutes)
            html.append(
                "<div class='card'>"
                f"<b>{stop.order}. {boss.name_es}</b> · Nv.{boss.level}<br>"
                f"<span class='n'>{format_tp_number(tp)}</span> "
                f"{tp.name if tp else '—'}<br>"
                f"<span class='t'>{ready}</span> · viaje ~{travel}<br>"
                f"<span class='muted'>{boss.zone}</span>"
                "</div>"
            )
        html.append(
            "<p class='muted'>APARICIÓN PREVISTA ≠ confirmado vivo. "
            "Confirma en Field Boss del juego. Marca MUERTO para arrancar el timer.</p>"
        )
        self.route_view.setHtml("".join(html))

    def _fill_history(self):
        rows = recent_history(30)
        lines = []
        for r in rows:
            lines.append(f"{r['ts'][:19]}  {r['event']}  {r.get('boss_id') or ''}  {r.get('detail') or ''}")
        self.hist_view.setPlainText("\n".join(lines) if lines else "Sin eventos aún.")


def run_app():
    import sys

    # QtWebEngine exige crear QApplication antes de algunas importaciones en Windows
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # bandeja: no morir al ocultar la ventana
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_QSS)
    font = font_ui(10)
    app.setFont(font)
    win = MainWindow()
    # Siempre: solo overlay en pantalla + icono en bandeja (ventana oculta)
    win.hide()
    sys.exit(app.exec())
