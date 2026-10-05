from datetime import datetime, timedelta, timezone

from app.handoff.assignment import (
    TechnicianCandidate,
    choose_technician,
    next_waiting_handoff,
)

NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)


def tech(identifier, status="online", active=(), last=None):
    return TechnicianCandidate(identifier, status, tuple(active), last)


def test_both_free_selects_lowest_id_when_never_assigned():
    assert choose_technician([tech(2), tech(1)]).technician_id == 1


def test_free_technician_wins_over_busy_technician():
    assert choose_technician([tech(1, active=(NOW,)), tech(2)]).technician_id == 2


def test_both_busy_selects_oldest_active_assignment():
    decision = choose_technician([tech(1, active=(NOW,)), tech(2, active=(NOW - timedelta(minutes=5),))])
    assert decision.technician_id == 2


def test_no_online_technician_leaves_handoff_waiting():
    assert choose_technician([tech(1, "offline"), tech(2, "pausa")]).status == "waiting"


def test_paused_and_offline_are_never_selected():
    decision = choose_technician([tech(1, "pausa"), tech(2, "offline"), tech(3)])
    assert decision.technician_id == 3


def test_free_ties_use_oldest_last_assignment_then_id():
    old = NOW - timedelta(hours=2)
    assert choose_technician([tech(2, last=old), tech(1, last=old)]).technician_id == 1
    assert choose_technician([tech(2, last=NOW), tech(3)]).technician_id == 3


def test_next_waiting_handoff_is_fifo_with_id_tiebreak():
    rows = [
        {"id": 3, "created_at": NOW},
        {"id": 2, "created_at": NOW - timedelta(seconds=1)},
        {"id": 1, "created_at": NOW},
    ]
    assert next_waiting_handoff(rows)["id"] == 2
