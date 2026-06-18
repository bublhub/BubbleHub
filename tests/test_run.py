import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import typer

from ageos.cli.run import _resolve_sandbox_paths, run_agent


def test_run_agent_uses_native_inference_only_network() -> None:
    client = Mock()
    client.register_agent.return_value = "agt-test"
    captured_env: dict[str, str] = {}

    def run_sandbox(*_args: object, **_kwargs: object) -> int:
        captured_env.update(os.environ)
        return 0

    client.native.run_sandbox.side_effect = run_sandbox

    with (
        patch("ageos.cli.run.SchedulerClient.local", return_value=client),
        patch("ageos.cli.run.apply_inference_env", return_value="http://127.0.0.1:8000"),
    ):
        with pytest.raises(typer.Exit) as exc:
            run_agent(
                binary="/bin/true",
                extra_args=[],
                niceness=0,
                memory="2G",
                cpu=0,
                speciality="default-instruct",
                workdir=None,
            )

    assert exc.value.exit_code == 0
    _binary, argv = client.native.run_sandbox.call_args.args
    assert Path(argv[-1]).name == "true"
    assert client.native.run_sandbox.call_args.kwargs["isolate_network"] is True
    assert client.native.run_sandbox.call_args.kwargs["root_dir"] is None
    assert client.native.run_sandbox.call_args.kwargs["workdir"] == "/workspace"
    assert client.native.run_sandbox.call_args.kwargs["inference_host"] == "127.0.0.1"
    assert client.native.run_sandbox.call_args.kwargs["inference_port"] == 8000
    assert client.native.run_sandbox.call_args.kwargs["sandbox_inference_port"] == 8000
    assert captured_env["AGEOS_NETWORK"] == "inference-only"
    assert captured_env["AGEOS_SANDBOX_INFERENCE_PORT"] == "8000"


def test_run_agent_resolves_explicit_relative_binary_from_host_cwd() -> None:
    client = Mock()
    client.register_agent.return_value = "agt-test"
    client.native.run_sandbox.return_value = 0

    with (
        patch("ageos.cli.run.SchedulerClient.local", return_value=client),
        patch("ageos.cli.run.apply_inference_env", return_value="http://127.0.0.1:8000"),
    ):
        with pytest.raises(typer.Exit) as exc:
            run_agent(
                binary="examples/basic_agent.py",
                extra_args=[],
                niceness=0,
                memory="2G",
                cpu=0,
                speciality="default-instruct",
                workdir=None,
                root_dir=Path("examples"),
            )

    assert exc.value.exit_code == 0
    _binary, argv = client.native.run_sandbox.call_args.args
    assert Path(argv[-1]) == (Path.cwd() / "examples" / "basic_agent.py").resolve()
    assert client.native.run_sandbox.call_args.kwargs["root_dir"] == str((Path.cwd() / "examples").resolve())


def test_sandbox_paths_default_to_empty_workspace() -> None:
    paths = _resolve_sandbox_paths(None, None)
    assert paths.host_root_dir is None
    assert paths.sandbox_workdir == "/workspace"


def test_sandbox_paths_use_root_dir_as_writable_workdir(tmp_path: Path) -> None:
    paths = _resolve_sandbox_paths(tmp_path, None)
    assert paths.host_root_dir == str(tmp_path.resolve())
    assert paths.sandbox_workdir == str(tmp_path.resolve())


def test_sandbox_paths_reject_workdir_outside_root_dir(tmp_path: Path) -> None:
    outside = tmp_path.parent
    with pytest.raises(Exception):
        _resolve_sandbox_paths(tmp_path, outside)


def test_sandbox_paths_reject_protected_root_dir() -> None:
    with pytest.raises(typer.BadParameter):
        _resolve_sandbox_paths(Path("/usr"), None)


def test_sandbox_paths_reject_ageos_source_tree() -> None:
    with pytest.raises(typer.BadParameter):
        _resolve_sandbox_paths(Path.cwd(), None)


def test_sandbox_paths_allow_examples_workspace() -> None:
    paths = _resolve_sandbox_paths(Path.cwd() / "examples", None)
    assert paths.host_root_dir == str((Path.cwd() / "examples").resolve())


def test_sandbox_paths_allow_nested_examples_workspace() -> None:
    paths = _resolve_sandbox_paths(Path.cwd() / "examples" / "openclaw", None)
    assert paths.host_root_dir == str((Path.cwd() / "examples" / "openclaw").resolve())
