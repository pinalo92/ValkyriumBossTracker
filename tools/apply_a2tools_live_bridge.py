"""Parche Event Timers: exporta feed+HP live a plugin-data/pinalo-live.json.

PinaloBossTracker lo lee en silencio (sin CDN). Reaplica tras actualizar A2Tools.
"""
from __future__ import annotations

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

EXPORT_FN = """// PINALO_LIVE: silent export of merged feed (incl. live HP) for Pinalo Boss Tracker.
let pinaloLiveAt = 0;
function pinaloExportLive(force) {
  try {
    if (!feed || !feed.bosses || typeof a2?.storage?.set !== "function") return;
    const now = Date.now();
    if (!force && now - pinaloLiveAt < 400) return;
    pinaloLiveAt = now;
    a2.storage.set("pinalo-live", {
      format: "pinalo-live-v1",
      server: feed.server ?? serverId(),
      at: now,
      updated: Math.floor(now / 1000),
      bosses: feed.bosses,
    }).catch(() => {});
  } catch (_) {}
}
"""


def _backup(name: str) -> None:
    bak = PLUGIN / "pinalo-backup"
    bak.mkdir(exist_ok=True)
    src = PLUGIN / name
    dst = bak / f"{name}.live.bak"
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)


def patch_plugin_js(text: str) -> str:
    if "PINALO_LIVE" not in text:
        needle = (
            "// The world boss timers for the player's server: when the window opens, when\n"
            "// the server changes, and every 15 minutes.\n"
            "let feedTimer = 0;\n"
            "// Each boss's newest report, between the feed's and the player's own map's.\n"
        )
        if needle not in text:
            raise SystemExit("plugin.js: no encuentro el ancla feedTimer/mergeOwn")
        text = text.replace(
            needle,
            "// The world boss timers for the player's server: when the window opens, when\n"
            "// the server changes, and every 15 minutes.\n"
            "let feedTimer = 0;\n"
            + EXPORT_FN
            + "// Each boss's newest report, between the feed's and the player's own map's.\n",
            1,
        )

    if "pinaloExportLive(true);\n  render();\n}" not in text:
        # tras readFeed
        old = (
            "    feedTimer = setTimeout(readFeed, live && pinned ? 30_000 : "
            "pinned === \"up\" ? FEED_PINNED_UP_MS : pinned ? FEED_PINNED_MS : FEED_BUSY_MS);\n"
            "  }\n"
            "  render();\n"
            "}\n"
        )
        new = (
            "    feedTimer = setTimeout(readFeed, live && pinned ? 30_000 : "
            "pinned === \"up\" ? FEED_PINNED_UP_MS : pinned ? FEED_PINNED_MS : FEED_BUSY_MS);\n"
            "  }\n"
            "  pinaloExportLive(true);\n"
            "  render();\n"
            "}\n"
        )
        if old not in text:
            raise SystemExit("plugin.js: no encuentro el final de readFeed")
        text = text.replace(old, new, 1)

    if "pinaloExportLive(true);\n  render();\n});\n\n// Whether AION2 is open" not in text:
        old = (
            "  feed = { ...(feed?.server === server ? feed : {}), server, "
            "bosses: mergeOwn(base), at: Date.now(), error: false };\n"
            "  render();\n"
            "});\n\n"
            "// Whether AION2 is open"
        )
        new = (
            "  feed = { ...(feed?.server === server ? feed : {}), server, "
            "bosses: mergeOwn(base), at: Date.now(), error: false };\n"
            "  pinaloExportLive(true);\n"
            "  render();\n"
            "});\n\n"
            "// Whether AION2 is open"
        )
        if old not in text:
            raise SystemExit("plugin.js: no encuentro el handler bossMap")
        text = text.replace(old, new, 1)

    if "pinaloExportLive(false);" not in text:
        old = (
            "    if (typeof updatePins === \"function\") updatePins(now);\n"
            "  }, 1000);"
        )
        new = (
            "    if (typeof updatePins === \"function\") updatePins(now);\n"
            "    pinaloExportLive(false);\n"
            "  }, 1000);"
        )
        if old not in text:
            raise SystemExit("plugin.js: no encuentro setInterval de render")
        text = text.replace(old, new, 1)

    return text


def patch_pins_js(text: str) -> str:
    if "pinaloExportLive" in text and "bossLive" in text:
        # ya parcheado en el handler
        marker = "if (typeof pinaloExportLive === \"function\") pinaloExportLive(true);"
        if marker in text:
            return text
    old = (
        "  bosses = mergeOwn(bosses);\n"
        "  liveUp = true;\n"
        "  feed = { ...base, bosses };\n"
        "  updatePins(Date.now());\n"
        "});"
    )
    new = (
        "  bosses = mergeOwn(bosses);\n"
        "  liveUp = true;\n"
        "  feed = { ...base, bosses };\n"
        "  if (typeof pinaloExportLive === \"function\") pinaloExportLive(true);\n"
        "  updatePins(Date.now());\n"
        "});"
    )
    if old not in text:
        raise SystemExit("pins.js: no encuentro el handler bossLive")
    return text.replace(old, new, 1)


def main() -> None:
    if not PLUGIN.is_dir():
        raise SystemExit(f"No está A2Tools Event Timers en {PLUGIN}")
    _backup("plugin.js")
    _backup("pins.js")

    pjs = PLUGIN / "plugin.js"
    text = pjs.read_text(encoding="utf-8")
    pjs.write_text(patch_plugin_js(text), encoding="utf-8")

    pins = PLUGIN / "pins.js"
    text = pins.read_text(encoding="utf-8")
    pins.write_text(patch_pins_js(text), encoding="utf-8")

    print(
        "OK: bridge live A2Tools → pinalo-live.json. "
        "Reinicia A2Tools (y Pinalo si ya estaba abierto)."
    )


if __name__ == "__main__":
    main()
