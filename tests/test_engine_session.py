from __future__ import annotations

from pathlib import Path

from ageos.engine.registry import ModelSpec
from ageos.engine.session import EngineSession
from ageos.native import Admission, HardwareInfo


GPU_MODEL = ModelSpec(
    name="gpu-model",
    flavor="qwen",
    capability="instruct",
    tier="small",
    backend="llama",
    repo_id="repo/gpu",
    filename="gpu.gguf",
    ram_gb=8,
    vram_gb=6,
    context_tokens=32768,
    placement="gpu",
)
CPU_MODEL = ModelSpec(
    name="cpu-model",
    flavor="mistral",
    capability="instruct",
    tier="small",
    backend="llama",
    repo_id="repo/cpu",
    filename="cpu.gguf",
    ram_gb=8,
    vram_gb=0,
    context_tokens=32768,
)
VLLM_MODEL = ModelSpec(
    name="vllm-model",
    flavor="qwen",
    capability="instruct",
    tier="large",
    backend="vllm",
    repo_id="repo/vllm",
    filename=None,
    ram_gb=16,
    vram_gb=12,
    context_tokens=32768,
    placement="gpu",
)


def test_engine_session_falls_back_when_gpu_admission_denied(monkeypatch) -> None:
    scheduler = FakeScheduler(deny={"gpu-model"})
    _patch_session_dependencies(monkeypatch, [GPU_MODEL, CPU_MODEL])

    with EngineSession("default-instruct", scheduler=scheduler) as session:
        assert session.resolved is not None
        assert session.resolved.model.name == "cpu-model"

    assert scheduler.loaded == ["cpu-model"]
    assert "gpu-model" in scheduler.evicted


def test_engine_session_falls_back_when_gpu_backend_fails(monkeypatch) -> None:
    scheduler = FakeScheduler()
    _patch_session_dependencies(monkeypatch, [VLLM_MODEL, CPU_MODEL], fail_vllm=True)

    with EngineSession("default-instruct", scheduler=scheduler) as session:
        assert session.resolved is not None
        assert session.resolved.model.name == "cpu-model"

    assert scheduler.loaded == ["cpu-model"]
    assert "vllm-model" in scheduler.evicted


class FakeRegistry:
    def __init__(self, candidates: list[ModelSpec]) -> None:
        self.candidates = candidates

    def resolve_candidates(self, *args: object, **kwargs: object) -> list[ModelSpec]:
        return self.candidates


class FakeScheduler:
    def __init__(self, deny: set[str] | None = None) -> None:
        self.deny = deny or set()
        self.loaded: list[str] = []
        self.evicted: list[str] = []

    def resource_limits(self) -> dict[str, int]:
        return {"ram_bytes": 64 * 1024**3, "vram_bytes": 24 * 1024**3}

    def admit_model_job(
        self,
        specialty: str,
        model_name: str,
        niceness: int,
        ram_gb: float,
        vram_gb: float,
    ) -> Admission:
        if model_name in self.deny:
            return Admission(False, "available", "not enough VRAM")
        return Admission(True, "available")

    def status_snapshot(self) -> dict[str, object]:
        return {"models": []}

    def mark_model_loaded(
        self,
        name: str,
        specialty: str,
        backend: str,
        ram_gb: float,
        vram_gb: float,
        pid: int,
        port: int,
    ) -> None:
        self.loaded.append(name)

    def mark_model_unloaded(self, name: str) -> None:
        pass

    def evict_model(self, name: str) -> None:
        self.evicted.append(name)


class FakeDownloader:
    def ensure_model(self, model: ModelSpec) -> Path:
        return Path(f"/models/{model.name}")


class FakeLlamaBackend:
    pid = 1234
    port = 5001

    def start(self, model: ModelSpec, model_path: str, niceness: int = 0) -> None:
        pass


class FailingVllmBackend:
    pid = 1235
    port = 5002

    def start(self, model: ModelSpec, model_path: str, niceness: int = 0) -> None:
        raise RuntimeError("GPU backend failed")


def _patch_session_dependencies(
    monkeypatch,
    candidates: list[ModelSpec],
    *,
    fail_vllm: bool = False,
) -> None:
    import ageos.engine.session as session_module

    monkeypatch.setattr(session_module.ModelRegistry, "load_default", lambda: FakeRegistry(candidates))
    monkeypatch.setattr(
        session_module,
        "detect_hardware",
        lambda: HardwareInfo(
            ram_bytes=64 * 1024**3,
            vram_bytes=24 * 1024**3,
            free_vram_bytes=22 * 1024**3,
            gpu_vendor="nvidia",
            gpu_backend="vllm",
            gpu_backends=("vllm", "cuda-llama"),
        ),
    )
    monkeypatch.setattr(session_module, "HfDownloader", FakeDownloader)
    monkeypatch.setattr(session_module, "LlamaBackend", FakeLlamaBackend)
    if fail_vllm:
        monkeypatch.setattr(session_module, "VllmBackend", FailingVllmBackend)
