from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from ageos.engine.downloader import HfDownloader
from ageos.engine.llama_backend import LlamaBackend
from ageos.engine.registry import ModelRegistry, ModelSpec
from ageos.engine.selector import select_tier
from ageos.engine.vllm_backend import VllmBackend
from ageos.native import detect_hardware
from ageos.node.client import SchedulerClient


DEFAULT_MAX_OUTPUT_TOKENS = 512


@dataclass(frozen=True)
class ResolvedSession:
    model: ModelSpec
    model_path: str
    attached: bool = False


class EngineSession:
    def __init__(
        self,
        specialty: str,
        niceness: int = 0,
        flavor: str | None = None,
        capability: str | None = None,
        scheduler: SchedulerClient | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.specialty = specialty
        self.niceness = niceness
        self.flavor = flavor
        self.capability = capability
        self.scheduler = scheduler or SchedulerClient.local()
        self.status_callback = status_callback
        self.backend: LlamaBackend | VllmBackend | None = None
        self.resolved: ResolvedSession | None = None

    def __enter__(self) -> "EngineSession":
        registry = ModelRegistry.load_default()
        hardware = detect_hardware()
        limits = self.scheduler.resource_limits()
        max_ram_gb = _limit_gb(limits.get("ram_bytes"), hardware.ram_bytes)
        max_vram_gb = _limit_gb(limits.get("vram_bytes"), hardware.vram_bytes)
        tier = select_tier(hardware)
        model = registry.resolve_specialty(
            self.specialty,
            tier_order=tier.order,
            flavor=self.flavor,
            capability=self.capability,
            max_ram_gb=max_ram_gb,
            max_vram_gb=max_vram_gb,
        )
        self._status(f"Selected model {model.name} ({model.backend})")
        admission = self.scheduler.admit_model_job(
            specialty=self.specialty,
            model_name=model.name,
            niceness=self.niceness,
            ram_gb=model.ram_gb,
            vram_gb=model.vram_gb,
        )
        if not admission.allowed:
            raise RuntimeError(admission.reason)
        attached = self._attach_warm_model(model)
        if attached:
            self._status(f"Reusing warm {model.backend} backend")
            self.resolved = ResolvedSession(model=model, model_path="", attached=True)
            self.scheduler.mark_model_loaded(
                model.name,
                self.specialty,
                model.backend,
                model.ram_gb,
                model.vram_gb,
                _model_pid(self.backend),
                _model_port(self.backend),
            )
            return self
        self._status(f"Ensuring model files for {model.repo_id}")
        model_path = str(HfDownloader().ensure_model(model))
        backend = VllmBackend() if model.backend == "vllm" else LlamaBackend()
        self._status(f"Starting {model.backend} backend")
        backend.start(model, model_path, self.niceness)
        self.backend = backend
        self.resolved = ResolvedSession(model=model, model_path=model_path)
        self.scheduler.mark_model_loaded(
            model.name,
            self.specialty,
            model.backend,
            model.ram_gb,
            model.vram_gb,
            _model_pid(backend),
            _model_port(backend),
        )
        self._status("Backend is ready")
        return self

    def chat(self, messages: list[dict[str, str]], stream: bool = False, max_tokens: int | None = None) -> str:
        if self.backend is None:
            raise RuntimeError("engine session is not started")
        if max_tokens is None:
            max_tokens = default_max_output_tokens()
        return self.backend.chat(messages, stream=stream, max_tokens=max_tokens)

    def embeddings(self, inputs: list[str]) -> list[list[float]]:
        if self.backend is None:
            raise RuntimeError("engine session is not started")
        return self.backend.embeddings(inputs)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.resolved is not None:
            self.scheduler.mark_model_unloaded(self.resolved.model.name)

    def _status(self, message: str) -> None:
        if self.status_callback is not None:
            self.status_callback(message)

    def _attach_warm_model(self, model: ModelSpec) -> bool:
        snapshot = self.scheduler.status_snapshot()
        models = snapshot.get("models", [])
        if not isinstance(models, list):
            return False
        for item in models:
            if not isinstance(item, dict) or item.get("name") != model.name:
                continue
            port = _int_or_zero(item.get("port"))
            pid = _int_or_zero(item.get("pid"))
            if port <= 0:
                self.scheduler.evict_model(model.name)
                return False
            backend = VllmBackend() if model.backend == "vllm" else LlamaBackend()
            try:
                if isinstance(backend, VllmBackend):
                    backend.attach(model, port, pid or None)
                else:
                    backend.attach(port, pid or None)
            except Exception:
                self.scheduler.evict_model(model.name)
                return False
            self.backend = backend
            return True
        return False


def _limit_gb(limit_bytes: object, hardware_bytes: int) -> float:
    limit = _int_or_zero(limit_bytes)
    if limit <= 0:
        limit = hardware_bytes
    return limit / 1024**3


def _int_or_zero(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _model_pid(backend: LlamaBackend | VllmBackend | None) -> int:
    return int(getattr(backend, "pid", 0) or 0)


def _model_port(backend: LlamaBackend | VllmBackend | None) -> int:
    return int(getattr(backend, "port", 0) or 0)


def default_max_output_tokens() -> int:
    value = os.environ.get("AGEOS_MAX_OUTPUT_TOKENS")
    if value is None:
        return DEFAULT_MAX_OUTPUT_TOKENS
    try:
        parsed = int(value)
    except ValueError:
        raise RuntimeError("AGEOS_MAX_OUTPUT_TOKENS must be an integer") from None
    if parsed <= 0:
        raise RuntimeError("AGEOS_MAX_OUTPUT_TOKENS must be greater than zero")
    return parsed
