from __future__ import annotations

from ageos.node.client import SchedulerClient


def telemetry_snapshot() -> dict[str, object]:
    return SchedulerClient.local().telemetry_snapshot()
