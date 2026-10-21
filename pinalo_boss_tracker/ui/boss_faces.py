"""Carga caras de bosses (cache local data/faces) para los pins."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap

from ..resources import package_data_dir

DATA = package_data_dir()
FACES_DIR = DATA / "faces"
FACES_MAP = DATA / "boss_faces.json"
CATALOG = DATA / "catalog.json"


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
    # Completar: field:ID → boss_id del catálogo (por a2tools_field_id; evita
    # colisiones Elyos/Asmo con el mismo nombre).
    try:
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    for b in cat.get("bosses", []):
        fid = str(b.get("a2tools_field_id") or "").strip()
        if not fid:
            continue
        file_name = out.get(f"field:{fid}")
        if not file_name:
            continue
        lid = str(b.get("id") or "")
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

