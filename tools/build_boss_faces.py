"""Descarga caras de field bosses desde aion2data.com → data/faces/ + mapa JSON."""

from __future__ import annotations

import html as html_lib
import json
import re
import urllib.request
from pathlib import Path

# Emparejamientos manuales cuando el alt de aion2data no coincide 1:1
MANUAL: dict[str, str] = {
    "101016": "/game/monsters/UT_256_MOB_BeritraD_04_V01.webp",  # Sentinel K'nash
}

ROOT = Path(__file__).resolve().parents[1]
FIELD_MAP = ROOT / "pinalo_boss_tracker" / "data" / "a2tools_field_ids.json"
CATALOG = ROOT / "pinalo_boss_tracker" / "data" / "catalog.json"
OUT_MAP = ROOT / "pinalo_boss_tracker" / "data" / "boss_faces.json"
FACES_DIR = ROOT / "pinalo_boss_tracker" / "data" / "faces"
BASE = "https://aion2data.com"
UA = {"User-Agent": "PinaloBossTracker/0.2 (offline face cache)"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def fetch_alt_map() -> dict[str, str]:
    """alt (EN name) → /game/monsters/....webp"""
    req = urllib.request.Request(f"{BASE}/bosses", headers=UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        html = r.read().decode("utf-8", "replace")
    pairs = re.findall(
        r'src="(/game/monsters/(UT_256_MOB_[A-Za-z0-9_]+\.webp))"\s+alt="([^"]+)"',
        html,
    )
    by_alt: dict[str, str] = {}
    for path, _file, alt in pairs:
        clean = html_lib.unescape(alt)
        by_alt.setdefault(clean, path)
    return by_alt


def find_path(en: str, alt_n: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    kn = norm(en)
    if not kn:
        return None
    if kn in alt_n:
        return alt_n[kn]
    # fuzzy: única coincidencia por contención
    cands = [
        (orig, path)
        for a, (orig, path) in alt_n.items()
        if kn in a or a in kn
    ]
    if len(cands) == 1:
        return cands[0]
    # preferir la más corta (menos prefijos tipo Eternal)
    if cands:
        cands.sort(key=lambda t: len(norm(t[0])))
        return cands[0]
    return None


def download(rel: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 200:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = BASE + rel
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
    except Exception as e:
        print("FAIL", url, e)
        return False
    dest.write_bytes(data)
    return True


def main() -> None:
    fmap = json.loads(FIELD_MAP.read_text(encoding="utf-8"))
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    local_by_en = {norm(b["name"]): b["id"] for b in cat["bosses"]}
    local_by_es = {norm(b["name_es"]): b["id"] for b in cat["bosses"]}

    by_alt = fetch_alt_map()
    alt_n = {norm(k): (k, v) for k, v in by_alt.items()}
    print(f"Retratos en aion2data: {len(by_alt)}")

    out: dict[str, dict] = {}
    missing: list[str] = []

    for fid, meta in fmap.items():
        en = meta.get("en") or ""
        es = meta.get("es") or ""
        local_id = local_by_en.get(norm(en)) or local_by_es.get(norm(es))
        hit = find_path(en, alt_n)
        if not hit and str(fid) in MANUAL:
            rel_m = MANUAL[str(fid)]
            hit = (en, rel_m)
        if not hit:
            missing.append(f"{fid} {en}")
            continue
        orig, rel = hit
        file_name = Path(rel).name
        dest = FACES_DIR / file_name
        if not download(rel, dest):
            missing.append(f"{fid} {en} (dl)")
            continue
        entry = {
            "field_id": str(fid),
            "en": en,
            "file": file_name,
            "source": "aion2data",
            "alt": orig,
        }
        if local_id:
            out[local_id] = entry
        out[f"field:{fid}"] = entry

    OUT_MAP.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {len(out)} entradas → {OUT_MAP.relative_to(ROOT)}")
    print(f"Caras en disco: {len(list(FACES_DIR.glob('*.webp')))}")
    if missing:
        print(f"Sin cara ({len(missing)}):")
        for m in missing:
            print(" ", m)


if __name__ == "__main__":
    main()
