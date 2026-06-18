from types import SimpleNamespace
from unittest.mock import patch

from ageos.integrations.openai_shim import AgeosOpenAI


def test_openai_shim_uses_engine_session_even_when_api_base_is_set(monkeypatch) -> None:
    monkeypatch.setenv("AGEOS_API_BASE_URL", "http://127.0.0.1:8000")

    with patch("ageos.integrations.openai_shim.EngineSession") as session_cls:
        session = session_cls.return_value.__enter__.return_value
        session.chat.return_value = "direct"

        response = AgeosOpenAI(speciality="default-instruct", niceness=3).chat.completions.create(
            model="ageos-local",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=32,
        )

    session_cls.assert_called_once_with("default-instruct", niceness=3)
    session.chat.assert_called_once_with([{"role": "user", "content": "hi"}], max_tokens=32)
    assert response.choices[0].message.content == "direct"


def test_openai_shim_defaults_to_configured_speciality() -> None:
    with (
        patch(
            "ageos.integrations.openai_shim.load_inference_config",
            return_value=SimpleNamespace(default_specialty="default-instruct"),
        ),
        patch("ageos.integrations.openai_shim.EngineSession") as session_cls,
    ):
        session = session_cls.return_value.__enter__.return_value
        session.chat.return_value = "direct"

        AgeosOpenAI().chat.completions.create(
            model="ageos-local",
            messages=[{"role": "user", "content": "hi"}],
        )

    session_cls.assert_called_once_with("default-instruct", niceness=0)
