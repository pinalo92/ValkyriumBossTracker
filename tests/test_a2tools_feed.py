from datetime import datetime, timezone

from pinalo_boss_tracker.sources.a2tools_feed import observations_from_feed


def test_observations_from_sample_feed():
    feed = {
        "server": 1304,
        "updated": 1792448100,
        "bosses": {
            "101007": {
                "state": "up",
                "source": "a2t",
                "confirmed": True,
                "upSince": 1792447927,
                "nextSpawn": None,
                "reportedAt": 1792447930,
            },
            "101011": {
                "state": "dead",
                "source": "meters",
                "confirmed": True,
                "nextSpawn": 1792451079,
                "reportedAt": 1792447502,
                "upSince": None,
            },
            "2001": {
                "state": "dead",
                "source": "a2t",
                "confirmed": True,
                "nextSpawn": 1792450000,
                "reportedAt": 1792440000,
            },
        },
    }
    obs, note = observations_from_feed(feed, faction="elyos")
    by_id = {o.boss_id: o for o in obs}
    assert "blooming_korin" in by_id
    assert by_id["blooming_korin"].reliability.value.startswith("CONFIRMADO")
    assert "lawa" in by_id
    assert by_id["lawa"].predicted_ready_at == datetime.fromtimestamp(
        1792451079, tz=timezone.utc
    )
    assert "CDN" in note
    assert by_id["blooming_korin"].hp is None


def test_hp_from_feed():
    feed = {
        "server": 1304,
        "bosses": {
            "101002": {
                "state": "up",
                "source": "meters",
                "confirmed": True,
                "hp": 50,
                "upSince": 1792447927,
                "reportedAt": 1792447930,
            },
        },
    }
    obs, note = observations_from_feed(
        feed, faction="elyos", source="a2tools-live"
    )
    assert len(obs) == 1
    assert obs[0].boss_id == "rotten_kutar"
    assert obs[0].hp == 50
    assert "live" in note

