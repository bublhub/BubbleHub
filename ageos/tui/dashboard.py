from __future__ import annotations

import time

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

from ageos.node.client import SchedulerClient


def run_dashboard(refresh_seconds: float = 1.0) -> None:
    console = Console()
    with Live(_render(), console=console, refresh_per_second=max(1, int(1 / refresh_seconds))) as live:
        try:
            while True:
                live.update(_render())
                time.sleep(refresh_seconds)
        except KeyboardInterrupt:
            return


def _render() -> Group:
    snapshot = SchedulerClient.local().telemetry_snapshot()
    hardware = snapshot["hardware"]  # type: ignore[index]
    limits = snapshot.get("limits", {})
    ram_total = _limit_or_hardware(limits, hardware, "ram_bytes")
    vram_total = _limit_or_hardware(limits, hardware, "vram_bytes")
    models = snapshot["models"]  # type: ignore[index]
    ram_model_bytes = int(sum(float(item.get("ram_gb", 0)) * 1024**3 for item in models))
    vram_model_bytes = int(sum(float(item.get("vram_gb", 0)) * 1024**3 for item in models))

    return Group(
        Panel(_bars(ram_total, ram_model_bytes, "RAM", snapshot["memory_pressure"]), title="AgeOS Memory"),
        Panel(_bars(vram_total, vram_model_bytes, "VRAM", "n/a" if vram_total == 0 else "tracked"), title="AgeOS GPU"),
        _agents_table(snapshot["agents"]),  # type: ignore[index]
        _models_table(models),
        _queue_table(snapshot["queue"]),  # type: ignore[index]
    )


def _limit_or_hardware(limits: object, hardware: object, key: str) -> int:
    if isinstance(limits, dict):
        limit = _int_or_zero(limits.get(key))
        if limit > 0:
            return limit
    if isinstance(hardware, dict):
        return _int_or_zero(hardware.get(key))
    return 0


def _int_or_zero(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _bars(total: int, used: int, label: str, state: object) -> Progress:
    progress = Progress(
        TextColumn(f"{label}"),
        BarColumn(bar_width=50),
        TextColumn("{task.percentage:>3.0f}%"),
        TextColumn(f"state={state}"),
    )
    total_safe = max(total, 1)
    progress.add_task(label, total=total_safe, completed=min(used, total_safe))
    return progress


def _agents_table(agents: list[dict[str, object]]) -> Table:
    table = Table(title="Agents")
    for column in ["agent_id", "binary", "status", "niceness", "specialty"]:
        table.add_column(column)
    for item in agents:
        table.add_row(*(str(item.get(column, "")) for column in ["agent_id", "binary", "status", "niceness", "specialty"]))
    return table


def _models_table(models: list[dict[str, object]]) -> Table:
    table = Table(title="Models Consuming Memory")
    for column in ["name", "backend", "specialty", "ram_gb", "vram_gb", "pid", "port", "refcount"]:
        table.add_column(column)
    for item in models:
        table.add_row(*(str(item.get(column, "")) for column in ["name", "backend", "specialty", "ram_gb", "vram_gb", "pid", "port", "refcount"]))
    return table


def _queue_table(queue: list[dict[str, object]]) -> Table:
    table = Table(title="Waiting Queue")
    for column in ["job_id", "model_name", "niceness", "wait_seconds", "reason"]:
        table.add_column(column)
    if not queue:
        table.add_row("", "", "", "", "No waiting jobs; admitted work appears under models/agents.")
        return table
    for item in queue:
        table.add_row(*(str(item.get(column, "")) for column in ["job_id", "model_name", "niceness", "wait_seconds", "reason"]))
    return table
