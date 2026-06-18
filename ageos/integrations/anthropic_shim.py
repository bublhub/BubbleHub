from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

import requests

from ageos.engine.session import EngineSession


@dataclass
class AgeosAnthropicMessage:
    content: list[dict[str, str]]


class _Messages:
    def __init__(self, specialty: str, niceness: int) -> None:
        self.specialty = specialty
        self.niceness = niceness

    def create(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        **kwargs: Any,
    ) -> AgeosAnthropicMessage:
        del model, kwargs
        converted: list[dict[str, str]] = []
        if system:
            converted.append({"role": "system", "content": system})
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, list):
                text = "\n".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
            else:
                text = str(content)
            converted.append({"role": str(message.get("role", "user")), "content": text})
        api_base = os.environ.get("AGEOS_API_BASE_URL")
        if api_base:
            response = requests.post(
                f"{api_base.rstrip('/')}/v1/chat/completions",
                json={
                    "model": self.specialty,
                    "messages": converted,
                    "ageos_specialty": self.specialty,
                },
                timeout=300,
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]
            return AgeosAnthropicMessage(content=[{"type": "text", "text": answer}])
        with EngineSession(self.specialty, niceness=self.niceness) as session:
            answer = session.chat(converted)
        return AgeosAnthropicMessage(content=[{"type": "text", "text": answer}])


class AgeosAnthropic:
    def __init__(self, speciality: str | None = None, specialty: str | None = None, niceness: int = 0) -> None:
        self.specialty = specialty or speciality or "default-instruct"
        self.niceness = niceness
        self.messages = _Messages(self.specialty, self.niceness)
