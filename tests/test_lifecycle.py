"""The demo world is a bounded episode: it pauses unwatched and starts over cleanly."""

from __future__ import annotations

from app.simulation import engine, lifecycle, physics


def test_a_world_nobody_is_watching_is_paused():
    assert not lifecycle.is_paused(last_request=100.0, now=150.0, idle_pause_seconds=90)
    assert lifecycle.is_paused(last_request=100.0, now=191.0, idle_pause_seconds=90)


def test_a_returning_visitor_gets_a_fresh_board_only_after_a_long_absence():
    assert not lifecycle.needs_idle_reset(last_request=0.0, now=19 * 60, idle_reset_minutes=20)
    assert lifecycle.needs_idle_reset(last_request=0.0, now=21 * 60, idle_reset_minutes=20)


def test_the_episode_cap_never_interrupts_someone_mid_demo():
    long_run = 30 * 60.0  # 30 simulated hours, past a 24 h cap
    # Pressed a button two minutes ago: keep going.
    assert not lifecycle.needs_episode_reset(
        long_run, last_action=0.0, now=2 * 60, episode_sim_hours=24, action_grace_minutes=5
    )
    # Nobody has touched it for ten minutes: start over.
    assert lifecycle.needs_episode_reset(
        long_run, last_action=0.0, now=10 * 60, episode_sim_hours=24, action_grace_minutes=5
    )


def test_a_young_episode_is_never_reset():
    assert not lifecycle.needs_episode_reset(
        10 * 60.0, last_action=0.0, now=10_000.0, episode_sim_hours=24, action_grace_minutes=5
    )


def test_an_episode_that_ran_its_course_returns_to_the_seeded_baseline(db, monkeypatch):
    baseline = engine.reset(db)
    for _ in range(20):
        physics.tick(db)
    assert physics.environment(db).sim_minutes > 0

    monkeypatch.setattr(engine.settings, "auto_reset_enabled", True)
    monkeypatch.setattr(engine.settings, "episode_sim_hours", 1.0)
    monkeypatch.setattr(engine.settings, "action_grace_minutes", 5.0)
    lifecycle.note_request(is_action=True, now=0.0)

    import random

    engine._advance_episode(db, random.Random(1), now=10 * 60.0)
    db.expire_all()
    assert physics.environment(db).sim_minutes == baseline["sim_minutes"]
