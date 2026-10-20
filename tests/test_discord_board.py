from pinalo_boss_tracker.models import Reliability
from pinalo_boss_tracker.sources.discord_board import parse_board_text


def test_parse_alive_and_dead_lines():
    text = """
Black Tentacle Lawa — UP
Kernon of the West killed — respawn timer
Neikel of the East · may be up
"""
    obs = parse_board_text(text)
    by = {o.boss_id: o for o in obs}
    assert "lawa" in by
    assert by["lawa"].reliability in (
        Reliability.CONFIRMED_ALIVE,
        Reliability.PREDICTED_SPAWN,
    )
    assert "kernon_west" in by
    assert by["kernon_west"].reliability == Reliability.KILL_RECORDED
