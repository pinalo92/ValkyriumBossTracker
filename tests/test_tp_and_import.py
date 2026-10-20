from datetime import datetime, timezone
from pathlib import Path

from pinalo_boss_tracker.catalog import bosses
from pinalo_boss_tracker.engine import distance_tp_to_boss, tp_for
from pinalo_boss_tracker.models import Reliability
from pinalo_boss_tracker.sources.import_json import JsonKillImportAdapter


def test_nearest_tp_exists():
    from pinalo_boss_tracker.catalog import clear_catalog_cache, teleports

    clear_catalog_cache()
    boss = bosses()["lawa"]
    tp = tp_for(boss)
    assert tp is not None
    assert tp.id == "tp_ancient_zumion"
    dist = distance_tp_to_boss(boss)
    assert dist is not None and dist >= 0
    # Captura Lista general: #4 Cuartel Costero → Kernon
    assert teleports()["tp_coastal_camp"].map_number == 4
    assert teleports()["tp_cantas_mushroom"].map_number == 6
    assert teleports()["tp_marsh_outpost"].map_number == 9
    assert teleports()["tp_collapsed_pillar"].map_number == 19
    assert teleports()["tp_verteron_fortress"].map_number == 21
    assert teleports()["tp_zumion_path"].map_number == 23


def test_tp_label_shows_number_when_set():
    from pinalo_boss_tracker.catalog import format_tp_label
    from pinalo_boss_tracker.models import Teleport

    tp = Teleport(
        id="x",
        name="Cuartel Costero",
        map_id="verteron",
        x=0,
        z=0,
        faction="elyos",
        name_en="Coastal Camp",
        map_number=12,
    )
    assert format_tp_label(tp) == "#12 Cuartel Costero"
    assert "¿?" in format_tp_label(Teleport("y", "A", "m", 0, 0, "elyos", "A EN", None))


def test_tp_guide_lists_lawa():
    from pinalo_boss_tracker.sources.aion2timers_api import format_tp_guide

    text = format_tp_guide(faction="elyos")
    assert "Lawa" in text
    assert "TP:" in text


def test_json_import_example():
    path = Path(__file__).resolve().parents[1] / "examples" / "kills.example.json"
    events = JsonKillImportAdapter(path).fetch()
    assert len(events) == 2
    by_id = {e.boss_id: e for e in events}
    assert by_id["kernon_west"].reliability == Reliability.KILL_RECORDED
    assert by_id["lawa"].reliability == Reliability.CONFIRMED_ALIVE
    assert by_id["kernon_west"].killed_at == datetime(2026, 10, 19, 18, 0, tzinfo=timezone.utc)
