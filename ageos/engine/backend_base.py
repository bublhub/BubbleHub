from __future__ import annotations

from typing import Protocol

from ageos.engine.registry import ModelSpec


class InferenceBackend(Protocol):
    def start(self, model: ModelSpec, model_path: str, niceness: int = 0) -> None: ...

    def chat(self, messages: list[dict[str, str]], stream: bool = False) -> str: ...

    def embeddings(self, inputs: list[str]) -> list[list[float]]: ...

    def stop(self) -> None: ...
