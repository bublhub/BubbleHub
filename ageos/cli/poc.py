from __future__ import annotations

import typer
from rich.console import Console

from ageos.engine.session import EngineSession
from ageos.inference import load_inference_config

console = Console()


def command(
    speciality: str | None = typer.Option(None, "--speciality", help="Specialty to test."),
    niceness: int = typer.Option(0, "--niceness", min=-20, max=19, help="AgeOS GPU/memory priority."),
    flavor: str | None = typer.Option(None, "--flavor", help="Force model flavor."),
    capability: str | None = typer.Option(None, "--capability", help="Force capability."),
) -> None:
    """Start a local model REPL for free-text testing."""

    resolved_speciality = speciality or load_inference_config().default_specialty
    console.print(f"[bold]AgeOS POC[/bold] speciality={resolved_speciality} niceness={niceness}")
    with EngineSession(
        resolved_speciality,
        niceness=niceness,
        flavor=flavor,
        capability=capability,
        status_callback=lambda message: console.print(f"[dim]{message}[/dim]"),
    ) as session:
        while True:
            try:
                text = input("ageos> ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break
            if text in {":q", ":quit", "exit", "quit"}:
                break
            if not text:
                continue
            answer = session.chat([{"role": "user", "content": text}])
            console.print(answer)
