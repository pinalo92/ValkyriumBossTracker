"""Carga caras de bosses (cache local data/faces) para los pins."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap

from ..resources import package_data_dir

DATA = package_data_dir()
FACES_DIR = DATA / "faces"
FACES_MAP = DATA / "boss_faces.json"
FIELD_MAP = DATA / "a2tools_field_ids.json"
CATALOG = DATA / "catalog.json"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


@lru_cache(maxsize=1)
def _face_index() -> dict[str, str]:
    """boss_id / field:ID → nombre de fichero."""
    if not FACES_MAP.exists():
        return {}
    try:
        data = json.loads(FACES_MAP.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    for key, meta in data.items():
        if isinstance(meta, dict) and meta.get("file"):
            out[str(key)] = str(meta["file"])
    # Completar por nombre EN del field map ↔ catálogo
    try:
        fmap = json.loads(FIELD_MAP.read_text(encoding="utf-8"))
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    by_en = {_norm(b["name"]): b["id"] for b in cat.get("bosses", [])}
    by_es = {_norm(b["name_es"]): b["id"] for b in cat.get("bosses", [])}
    for fid, meta in fmap.items():
        file_name = out.get(f"field:{fid}")
        if not file_name:
            continue
        lid = by_en.get(_norm(meta.get("en") or "")) or by_es.get(
            _norm(meta.get("es") or "")
        )
        if lid and lid not in out:
            out[lid] = file_name
    return out


@lru_cache(maxsize=128)
def face_pixmap(boss_id: str, field_id: str = "") -> Optional[QPixmap]:
    idx = _face_index()
    file_name = idx.get(boss_id) or (
        idx.get(f"field:{field_id}") if field_id else None
    )
    if not file_name:
        return None
    path = FACES_DIR / file_name
    if not path.exists():
        return None
    pm = QPixmap(str(path))
    if pm.isNull():
        return None
    return pm


def draw_circular_face(
    p: QPainter,
    pixmap: QPixmap,
    cx: float,
    cy: float,
    radius: float,
) -> None:
    """Dibuja el retrato recortado en círculo (cara del boss)."""
    side = int(radius * 2)
    if side < 8:
        return
    scaled = pixmap.scaled(
        side,
        side,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    # Centrar el crop
    x = (scaled.width() - side) // 2
    y = (scaled.height() - side) // 2
    cropped = scaled.copy(x, y, side, side)

    path = QPainterPath()
    path.addEllipse(QRectF(cx - radius, cy - radius, side, side))
    p.save()
    p.setClipPath(path)
    p.drawPixmap(int(cx - radius), int(cy - radius), cropped)
    p.restore()

