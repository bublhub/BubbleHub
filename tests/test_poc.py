from types import SimpleNamespace
from unittest.mock import patch

from ageos.cli import poc


def test_poc_defaults_to_configured_speciality() -> None:
    with (
        patch("ageos.cli.poc.load_inference_config", return_value=SimpleNamespace(default_specialty="default-instruct")),
        patch("ageos.cli.poc.EngineSession") as session_cls,
        patch("builtins.input", side_effect=EOFError),
    ):
        poc.command(
            speciality=None,
            niceness=0,
            flavor=None,
            capability=None,
        )

    session_cls.assert_called_once()
    assert session_cls.call_args.args[0] == "default-instruct"
