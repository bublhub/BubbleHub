from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from ageos import __version__
from ageos.cli import dashboard as dashboard_cmd
from ageos.cli import poc as poc_cmd
from ageos.cli import prompt as prompt_cmd
from ageos.cli import ps as ps_cmd
from ageos.cli import queue as queue_cmd
from ageos.cli import run as run_cmd
from ageos.cli import serve as serve_cmd
from ageos.cli import shell as shell_cmd
from ageos.engine.registry import ModelRegistry
from ageos.engine.selector import select_tier
from ageos.native import detect_hardware, is_sandboxed
from ageos.node.client import SchedulerClient

HELP_CONTEXT = {"help_option_names": ["-h", "--help"]}
RUN_CONTEXT = {
    **HELP_CONTEXT,
    "allow_extra_args": True,
    "ignore_unknown_options": True,
}

app = typer.Typer(
    name="ageos",
    help="AgeOS local agent runtime, model scheduler, and sandbox CLI.",
    context_settings=HELP_CONTEXT,
    no_args_is_help=True,
)

models_app = typer.Typer(
    help="Inspect and choose local model registry entries.",
    context_settings=HELP_CONTEXT,
    invoke_without_command=True,
)
specialties_app = typer.Typer(
    help="Inspect available AgeOS specialties.",
    context_settings=HELP_CONTEXT,
)

app.command("poc")(poc_cmd.command)
app.command("prompt")(prompt_cmd.command)
app.command("run", context_settings=RUN_CONTEXT)(run_cmd.command)
app.command("shell", context_settings=RUN_CONTEXT)(shell_cmd.command)
app.command("serve")(serve_cmd.command)
app.command("ps")(ps_cmd.command)
app.command("queue")(queue_cmd.command)
app.command("dashboard")(dashboard_cmd.command)
app.add_typer(models_app, name="models")
app.add_typer(specialties_app, name="specialties")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"ageos {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show AgeOS version.",
    ),
) -> None:
    """AgeOS MVP command surface."""


@models_app.callback(invoke_without_command=True)
def models(
    ctx: typer.Context,
    speciality: str = typer.Option(
        "default-instruct",
        "--speciality",
        "--specialty",
        help="Speciality to configure when choosing a base model.",
    ),
) -> None:
    """Choose the base model for a speciality."""

    if ctx.invoked_subcommand is not None:
        return
    _deny_in_sandbox("ageos models")
    _choose_base_model(speciality)


@models_app.command("list")
def models_list(
    speciality: str = typer.Option(
        "default-instruct",
        "--speciality",
        "--specialty",
        help="Speciality whose currently selected model is highlighted.",
    ),
) -> None:
    """List registered models and show the tier this machine will use."""

    registry = ModelRegistry.load_default()
    hardware = detect_hardware()
    tier = select_tier(hardware)
    selected = _selected_model_name(registry, speciality, tier.order, hardware)
    console = Console()
    console.print(
        f"Machine tier: [bold]{tier.name}[/bold] "
        f"(RAM={hardware.ram_bytes // (1024**3)}GiB, "
        f"VRAM={hardware.vram_bytes // (1024**3)}GiB)"
    )
    if selected is not None:
        console.print(f"{speciality} -> [bold green]{selected}[/bold green]")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Use")
    table.add_column("Model")
    table.add_column("Flavor")
    table.add_column("Capability")
    table.add_column("Backend")
    table.add_column("Tier")
    table.add_column("RAM")
    table.add_column("VRAM")
    table.add_column("Ctx")
    table.add_column("Repo")
    for model in registry.models:
        marker = "*" if model.name == selected else ""
        table.add_row(
            marker,
            model.name,
            model.flavor,
            model.capability,
            model.backend,
            model.tier,
            f"{model.ram_gb:g}G",
            f"{model.vram_gb:g}G",
            str(model.context_tokens),
            model.repo_id,
        )
    console.print(table)


@models_app.command("stop")
def models_stop() -> None:
    """Stop all currently loaded warm model backends."""

    _deny_in_sandbox("ageos models stop")
    client = SchedulerClient.local()
    snapshot = client.status_snapshot()
    models = snapshot.get("models", [])
    loaded = [model for model in models if isinstance(model, dict) and model.get("name")]
    if not loaded:
        typer.echo("No loaded models to stop.")
        return
    for model in loaded:
        client.evict_model(str(model["name"]))
    typer.echo(f"Stopped {len(loaded)} loaded model(s).")


@specialties_app.command("list")
def specialties_list() -> None:
    """List specialties available to --speciality."""

    registry = ModelRegistry.load_default()
    for name, specialty in sorted(registry.specialties.items()):
        typer.echo(
            f"{name:20} capability={specialty.capability:9} "
            f"flavor={specialty.flavor or 'auto':8} "
            f"model={specialty.model or 'auto':24} "
            f"lora={specialty.lora or '-'}"
        )


def _choose_base_model(speciality: str) -> None:
    registry = ModelRegistry.load_default()
    hardware = detect_hardware()
    tier = select_tier(hardware)
    selected = _selected_model_name(registry, speciality, tier.order, hardware)
    candidates = registry.resolve_candidates(
        speciality,
        tier_order=tier.order,
        capability="instruct",
        max_ram_gb=hardware.ram_bytes / 1024**3,
        max_vram_gb=hardware.vram_bytes / 1024**3,
        supported_gpu_backends=hardware.gpu_backends,
    )
    if not candidates:
        raise typer.BadParameter("no instruct models fit the current machine")

    default_index = next(
        (index for index, model in enumerate(candidates, start=1) if model.name == selected),
        1,
    )

    console = Console()
    console.print(f"Choose base model for [bold]{speciality}[/bold]:")
    for index, model in enumerate(candidates, start=1):
        marker = "current" if model.name == selected else ""
        console.print(
            f"{index}. {model.name} "
            f"({model.flavor}, {model.backend}, {model.tier}, "
            f"RAM {model.ram_gb:g}G, VRAM {model.vram_gb:g}G, ctx {model.context_tokens}) "
            f"{marker}"
        )

    choice = _prompt_choice(len(candidates), default_index)
    model = candidates[choice - 1]
    _write_speciality_model_override(speciality, model.name, model.capability)
    console.print(
        f"Saved {speciality} -> [bold green]{model.name}[/bold green] "
        f"in {_user_models_config_path()}"
    )


def _prompt_choice(max_choice: int, default: int) -> int:
    while True:
        value = typer.prompt("Model number", default=str(default))
        try:
            choice = int(value)
        except ValueError:
            typer.echo("Enter a number from the list.")
            continue
        if 1 <= choice <= max_choice:
            return choice
        typer.echo(f"Enter a number between 1 and {max_choice}.")


def _selected_model_name(
    registry: ModelRegistry,
    speciality: str,
    tier_order: list[str],
    hardware: object,
) -> str | None:
    try:
        model = registry.resolve_specialty(
            speciality,
            tier_order,
            max_ram_gb=getattr(hardware, "ram_bytes") / 1024**3,
            max_vram_gb=getattr(hardware, "vram_bytes") / 1024**3,
            supported_gpu_backends=getattr(hardware, "gpu_backends", ()),
        )
    except KeyError:
        return None
    return model.name


def _write_speciality_model_override(speciality: str, model_name: str, capability: str) -> None:
    path = _user_models_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _read_user_models_config(path)
    specialties = dict(data.get("specialties", {}))
    current = dict(specialties.get(speciality, {}))
    current["capability"] = capability
    current["model"] = model_name
    current.pop("flavor", None)
    current.pop("min_context_tokens", None)
    specialties[speciality] = current
    data["specialties"] = specialties
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False)


def _read_user_models_config(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data if isinstance(data, dict) else {}


def _user_models_config_path() -> Path:
    return Path.home() / ".config" / "ageos" / "models.yaml"


def _deny_in_sandbox(command: str) -> None:
    if is_sandboxed():
        raise typer.BadParameter(
            f"{command} is only available to the real host user, not from inside an AgeOS sandbox"
        )
