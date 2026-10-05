from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


@dataclass(frozen=True)
class TechnicianCandidate:
    id: int
    status: Literal["online", "pausa", "offline"]
    active_assigned_at: tuple[datetime, ...] = ()
    last_assigned_at: datetime | None = None

    @property
    def active_chats(self) -> int:
        return len(self.active_assigned_at)


@dataclass(frozen=True)
class AssignmentDecision:
    status: Literal["assigned", "waiting"]
    technician_id: int | None


def choose_technician(candidates: list[TechnicianCandidate]) -> AssignmentDecision:
    eligible = [candidate for candidate in candidates if candidate.status == "online"]
    if not eligible:
        return AssignmentDecision(status="waiting", technician_id=None)
    free = [candidate for candidate in eligible if candidate.active_chats == 0]
    if free:
        minimum = datetime.min.replace(tzinfo=timezone.utc)
        selected = min(free, key=lambda item: (item.last_assigned_at or minimum, item.id))
        return AssignmentDecision(status="assigned", technician_id=selected.id)
    selected = min(eligible, key=lambda item: (min(item.active_assigned_at), item.id))
    return AssignmentDecision(status="assigned", technician_id=selected.id)


def next_waiting_handoff(waiting: list[dict]) -> dict | None:
    if not waiting:
        return None
    return min(waiting, key=lambda item: (item["created_at"], str(item["id"])))
