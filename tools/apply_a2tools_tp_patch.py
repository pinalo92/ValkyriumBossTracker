"""Reaplica el parche TP bajo el nombre en overlays A2Tools Event Timers.

Útil si A2Tools actualiza el plugin y borra el parche.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

PLUGIN = (
    Path.home()
    / "AppData"
    / "Roaming"
    / "com.a2tools.dps-meter"
    / "plugins"
    / "event-timers"
)
ROOT = Path(__file__).resolve().parents[1]
FIELD_MAP = ROOT / "pinalo_boss_tracker" / "data" / "a2tools_field_ids.json"
CATALOG = ROOT / "pinalo_boss_tracker" / "data" / "catalog.json"


def build_tp_map() -> dict[str, int]:
    fmap = json.loads(FIELD_MAP.read_text(encoding="utf-8"))
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    tps = {t["id"]: t for t in cat["teleports"]}

    def n(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", s.lower())

    local = {n(b["name"]): b for b in cat["bosses"]}
    out: dict[str, int] = {}
    for fid, info in fmap.items():
        b = local.get(n(info.get("en", "")))
        if not b:
            continue
        tp = tps.get(b.get("nearest_tp_id") or "")
        if tp and tp.get("map_number") is not None:
            out[str(fid)] = int(tp["map_number"])
    return out


def main() -> None:
    if not PLUGIN.is_dir():
        raise SystemExit(f"No está A2Tools Event Timers en {PLUGIN}")
    bak = PLUGIN / "pinalo-backup"
    bak.mkdir(exist_ok=True)
    for name in ("widget.html", "widget.js", "widget.css", "pins.js"):
        src = PLUGIN / name
        dst = bak / f"{name}.bak"
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)

    tp_map = build_tp_map()
    tp_json = json.dumps(tp_map, separators=(",", ":"))

    html = PLUGIN / "widget.html"
    h = html.read_text(encoding="utf-8")
    if '<div class="tp"></div>' not in h:
        h = h.replace(
            '<div class="name"></div>\n    </div>',
            '<div class="name"></div>\n      <div class="tp"></div>\n    </div>',
        )
        html.write_text(h, encoding="utf-8")

    wjs = PLUGIN / "widget.js"
    w = wjs.read_text(encoding="utf-8")
    w = w.replace(
        "+ '<div class=\"time\"></div><div class=\"sub\"></div><div class=\"name\"></div>';",
        "+ '<div class=\"time\"></div><div class=\"sub\"></div><div class=\"name\"></div><div class=\"tp\"></div>';",
    )
    if "d.tp" not in w:
        w = w.replace(
            'pin.querySelector(".name").textContent = d.showName ? d.name : "";\n'
            '  pin.className =',
            'pin.querySelector(".name").textContent = d.showName ? d.name : "";\n'
            '  const tpEl = pin.querySelector(".tp");\n'
            '  if (tpEl) tpEl.textContent = d.tp || "";\n'
            '  pin.className =',
        )
    wjs.write_text(w, encoding="utf-8")

    css = PLUGIN / "widget.css"
    c = css.read_text(encoding="utf-8")
    if ".tp {" not in c:
        c = c.replace(
            ".name { font-weight: 500; font-size: 11px; opacity: 0.9; }\n",
            ".name { font-weight: 500; font-size: 11px; opacity: 0.9; }\n"
            ".tp {\n"
            "  max-width: 78px;\n"
            "  text-align: center;\n"
            '  font: 700 13px/1.2 "Cascadia Mono", "Consolas", monospace;\n'
            "  color: #7ec8ff;\n"
            "  text-shadow: 0 0 3px #000, 0 1px 2px #000;\n"
            "}\n"
            ".tp:empty { display: none; }\n",
        )
        css.write_text(c, encoding="utf-8")

    pins = PLUGIN / "pins.js"
    p = pins.read_text(encoding="utf-8")
    if "PINALO_TP" not in p:
        raise SystemExit(
            "pins.js no tiene el bloque PINALO_TP; aplica el parche manual "
            "desde el repo o restaura y vuelve a pedir el parche."
        )
    p = re.sub(
        r"const PINALO_TP = \{[^}]*\};",
        f"const PINALO_TP = {tp_json};",
        p,
        count=1,
    )
    pins.write_text(p, encoding="utf-8")
    print(f"OK: TP en overlays A2Tools ({len(tp_map)} bosses). Reinicia A2Tools.")


if __name__ == "__main__":
    main()
