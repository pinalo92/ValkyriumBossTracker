from datetime import datetime, timezone

from pinalo_boss_tracker.models import Reliability
from pinalo_boss_tracker.sources.aion2timers_api import observations_from_my_timers


def test_observations_from_my_timers_up_and_dead():
    payload = [
        {
            "id": "boss-verteron-lawa",
            "name": "Black Tentacle Lawa",
            "zone": "Verteron",
            "location": "Artamia",
            "killed": {"at": "2026-10-19T10:00:00Z"},
            "respawns": {"at": "2026-10-19T14:00:00Z"},
            "up": True,
        },
        {
            "id": "boss-verteron-kernon",
            "name": "Kernon of the West",
            "zone": "Verteron",
            "location": "Cantas",
            "killed": {"at": "2026-10-19T18:00:00Z"},
            "respawns": {"at": "2026-10-19T18:30:00Z"},
            "up": False,
        },
    ]
    obs, note = observations_from_my_timers(payload)
    by_id = {o.boss_id: o for o in obs}
    assert "lawa" in by_id
    assert by_id["lawa"].reliability == Reliability.PREDICTED_SPAWN
    assert "kernon_west" in by_id
    assert by_id["kernon_west"].reliability == Reliability.KILL_RECORDED
    assert by_id["kernon_west"].killed_at == datetime(2026, 10, 19, 18, 0, tzinfo=timezone.utc)
    assert "Sync personal" in note
