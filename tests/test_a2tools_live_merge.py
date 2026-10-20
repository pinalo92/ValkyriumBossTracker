from pinalo_boss_tracker.sources.a2tools_feed import _parse_hp
from pinalo_boss_tracker.sources.a2tools_live import A2ToolsLiveBridge, merge_boss_entry


def test_merge_hp_fresher_same_life():
    b = A2ToolsLiveBridge()
    b._bosses["101001"] = {
        "state": "up",
        "upSince": 100,
        "reportedAt": 200,
        "hp": 90,
        "hpAt": 10,
    }
    b._apply_message(
        {
            "type": "boss",
            "boss": "101001",
            "entry": {
                "state": "up",
                "upSince": 100,
                "reportedAt": 150,
                "hp": 85,
                "hpAt": 20,
            },
        }
    )
    assert b._bosses["101001"]["hp"] == 85
    assert b._bosses["101001"]["reportedAt"] == 200


def test_merge_keeps_hp_when_newer_report_has_null():
    have = {
        "state": "up",
        "upSince": 100,
        "reportedAt": 200,
        "hp": 72,
        "hpAt": 50,
    }
    entry = {
        "state": "up",
        "upSince": 100,
        "reportedAt": 300,  # más nuevo (mapa) sin HP
        "hp": None,
    }
    out = merge_boss_entry(have, entry)
    assert out["hp"] == 72
    assert out["reportedAt"] == 300


def test_parse_hp_rounds_like_a2tools():
    assert _parse_hp(72.6) == 73
    assert _parse_hp("40") == 40
    assert _parse_hp(None) is None
    assert _parse_hp(150) == 100
    assert _parse_hp(-3) == 0
