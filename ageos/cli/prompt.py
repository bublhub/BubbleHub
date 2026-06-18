from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import typer

from ageos.engine.session import EngineSession
from ageos.engine.structured import (
    build_repair_messages,
    build_structured_messages,
    load_example_schema,
    parse_json_output,
)
from ageos.inference import load_inference_config


def command(
    speciality: str | None = typer.Option(None, "--speciality", help="Specialty to route to."),
    structure: Path | None = typer.Option(
        None,
        "--structure",
        exists=True,
        file_okay=True,
        dir_okay=False,
        help="Optional JSON example file for structured output.",
    ),
    text: str = typer.Option(..., "--text", help="Prompt text."),
    niceness: int = typer.Option(0, "--niceness", min=-20, max=19, help="AgeOS GPU/memory priority."),
    output: Path | None = typer.Option(None, "--output", help="Optional output file."),
) -> None:
    """Run one local prompt, optionally using structured JSON output."""

    resolved_speciality = speciality or load_inference_config().default_specialty
    with EngineSession(resolved_speciality, niceness=niceness) as session:
        payload = _run_prompt(
            resolved_speciality,
            structure,
            text,
            lambda messages: session.chat(messages),
        )
    if output:
        output.write_text(payload + "\n", encoding="utf-8")
    else:
        typer.echo(payload)


def _run_prompt(
    speciality: str,
    structure: Path | None,
    text: str,
    chat: Callable[[list[dict[str, str]]], str],
) -> str:
    if structure is None:
        return chat([{"role": "user", "content": text}])

    example = load_example_schema(structure)
    raw = chat(build_structured_messages(example, text))
    try:
        parsed = parse_json_output(raw)
    except Exception:
        repaired = chat(build_repair_messages(example, text, raw))
        parsed = parse_json_output(repaired)
    return json.dumps(parsed, indent=2, sort_keys=True)

