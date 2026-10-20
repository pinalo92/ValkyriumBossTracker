from datetime import datetime, timedelta, timezone

from pinalo_boss_tracker.catalog import bosses
from pinalo_boss_tracker.engine import build_route, mark_killed, refresh_observation
from pinalo_boss_tracker.models import AppSettings, Reliability


def test_mark_killed_sets_prediction():
    boss = bosses()["kernon_west"]
    when = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    obs = mark_killed(boss, when=when)
    assert obs.reliability == Reliability.KILL_RECORDED
    assert obs.predicted_ready_at == when + timedelta(minutes=30)


def test_route_prefers_confirmed_alive():
    settings = AppSettings(faction="elyos", region="EU")
    catalog = bosses()
    now = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)
    obs = {}
    # kill far boss long ago so window passed / unknown
    obs["gartua"] = mark_killed(catalog["gartua"], when=now - timedelta(hours=20))
    # recent kill for nearby short timer — still waiting
    obs["kernon_west"] = mark_killed(catalog["kernon_west"], when=now - timedelta(minutes=5))
    # confirmed alive Lawa
    from pinalo_boss_tracker.engine import mark_seen_alive

    obs["lawa"] = mark_seen_alive(catalog["lawa"])
    route = build_route(settings, obs, now=now, max_stops=5)
    assert route
    assert route[0].boss_id == "lawa"


def test_refresh_predicted_window():
    settings = AppSettings()
    boss = bosses()["neikel_east"]
    when = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)
    obs = mark_killed(boss, when=when)
    mid = when + timedelta(minutes=32)
    refreshed = refresh_observation(boss, obs, settings, now=mid)
    assert refreshed.reliability == Reliability.PREDICTED_SPAWN
