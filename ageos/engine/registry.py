from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ModelSpec:
    name: str
    flavor: str
    capability: str
    tier: str
    backend: str
    repo_id: str
    filename: str | None
    ram_gb: float
    vram_gb: float
    context_tokens: int = 4096


@dataclass(frozen=True)
class Specialty:
    name: str
    capability: str
    flavor: str | None = None
    lora: str | None = None
    min_context_tokens: int | None = None
    model: str | None = None


class ModelRegistry:
    def __init__(self, models: list[ModelSpec], specialties: dict[str, Specialty]) -> None:
        self.models = models
        self.specialties = specialties

    @classmethod
    def load_default(cls) -> "ModelRegistry":
        with resources.files("ageos.config").joinpath("models.yaml").open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        override = Path.home() / ".config" / "ageos" / "models.yaml"
        if override.exists():
            with override.open("r", encoding="utf-8") as handle:
                data = _merge_config(data, yaml.safe_load(handle))
        explicit = os.environ.get("AGEOS_MODELS_CONFIG")
        if explicit:
            with Path(explicit).expanduser().open("r", encoding="utf-8") as handle:
                data = _merge_config(data, yaml.safe_load(handle))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelRegistry":
        models = [ModelSpec(**item) for item in data.get("models", [])]
        specialties = {
            name: Specialty(name=name, **spec)
            for name, spec in data.get("specialties", {}).items()
        }
        return cls(models=models, specialties=specialties)

    def resolve_specialty(
        self,
        name: str,
        tier_order: list[str],
        flavor: str | None = None,
        capability: str | None = None,
        max_ram_gb: float | None = None,
        max_vram_gb: float | None = None,
    ) -> ModelSpec:
        specialty = self.specialties.get(name)
        if specialty is None:
            raise KeyError(f"unknown specialty '{name}'")
        if specialty.model is not None:
            return self._resolve_model_name(
                specialty.model,
                specialty=name,
                max_ram_gb=max_ram_gb,
                max_vram_gb=max_vram_gb,
            )
        target_capability = capability or specialty.capability
        target_flavor = flavor or specialty.flavor
        min_context_tokens = specialty.min_context_tokens
        candidates = [
            model
            for model in self.models
            if model.capability == target_capability
            and (target_flavor is None or model.flavor == target_flavor)
            and (min_context_tokens is None or model.context_tokens >= min_context_tokens)
        ]
        if max_ram_gb is not None:
            candidates = [model for model in candidates if model.ram_gb <= max_ram_gb]
        if max_vram_gb is not None:
            candidates = [model for model in candidates if model.vram_gb <= max_vram_gb]
        if not candidates:
            raise KeyError(f"no model matches specialty '{name}' for available RAM/VRAM")
        rank = {tier: idx for idx, tier in enumerate(tier_order)}
        return sorted(candidates, key=lambda item: rank.get(item.tier, 999))[0]

    def _resolve_model_name(
        self,
        name: str,
        *,
        specialty: str,
        max_ram_gb: float | None = None,
        max_vram_gb: float | None = None,
    ) -> ModelSpec:
        matches = [model for model in self.models if model.name == name]
        if not matches:
            raise KeyError(f"specialty '{specialty}' selects unknown model '{name}'")
        model = matches[0]
        if max_ram_gb is not None and model.ram_gb > max_ram_gb:
            raise KeyError(f"model '{name}' exceeds available RAM for specialty '{specialty}'")
        if max_vram_gb is not None and model.vram_gb > max_vram_gb:
            raise KeyError(f"model '{name}' exceeds available VRAM for specialty '{specialty}'")
        return model

def _merge_config(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return base
    merged = dict(base)
    if "models" in override:
        merged["models"] = override["models"]
    if "specialties" in override:
        specialties = dict(base.get("specialties", {}))
        specialties.update(override["specialties"])
        merged["specialties"] = specialties
    return merged
