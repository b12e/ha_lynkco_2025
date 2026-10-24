"""Per-model feature availability for the Lynk & Co integration.

Most capabilities can be read from the API itself (a BEV has no fuel state, a
Core model has no rear seat heaters, ``permittedToRead`` flags, ...). What the
API cannot tell us is whether a remote *command* actually does anything on a
given car. That knowledge lives in ``models/<TYPE>.json`` files:

* ``models/_default.json`` is the baseline for any car we have never seen: only
  the actions confirmed to work on every tested model are enabled.
* ``models/<GUIDE_TYPE>.json`` (e.g. ``CX11_2023``, ``E335_MORE``) is consulted
  first, then ``models/<MODEL_CODE>.json`` (e.g. ``CX11_A3``). A file only has
  to list what differs from the default.

This module has no Home Assistant imports at module level so it can be unit
tested without a Home Assistant install; see ``tests/test_features.py``.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
DEFAULT_FILE = "_default"
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class ModelFeatures:
    """Resolved feature set for one vehicle."""

    file: str
    name: str
    source: str | None
    actions: dict[str, bool] = field(default_factory=dict)
    entities: dict[str, bool] = field(default_factory=dict)

    @property
    def is_default(self) -> bool:
        """True when no model-specific file matched (unknown car)."""
        return self.file == DEFAULT_FILE

    def action_enabled(self, action: str) -> bool:
        """Whether a remote action (service name) is enabled on this model."""
        return bool(self.actions.get(action, False))

    def entity_enabled(self, key: str) -> bool:
        """Whether a non-inferable entity should be created; unknown keys are enabled."""
        return bool(self.entities.get(key, True))

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "name": self.name,
            "source": self.source,
            "actions": dict(self.actions),
            "entities": dict(self.entities),
        }


def _load_file(name: str) -> dict[str, Any] | None:
    if not _SAFE_NAME.match(name):
        return None
    path = os.path.join(MODELS_DIR, f"{name}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else None


def resolve_features(
    guide_type: str | None,
    model: str | None,
    loader: Callable[[str], dict[str, Any] | None] = _load_file,
) -> ModelFeatures:
    """Resolve features for a car: guide type first, model code second, then default.

    Blocking (reads files); call through the executor from Home Assistant.
    """
    default = loader(DEFAULT_FILE) or {}
    for candidate in (guide_type, model):
        if not candidate:
            continue
        data = loader(candidate)
        if data is None:
            continue
        return ModelFeatures(
            file=candidate,
            name=data.get("name") or default.get("name") or candidate,
            source=data.get("source") or default.get("source"),
            actions={**default.get("actions", {}), **data.get("actions", {})},
            entities={**default.get("entities", {}), **data.get("entities", {})},
        )
    return ModelFeatures(
        file=DEFAULT_FILE,
        name=default.get("name") or "Unknown model",
        source=default.get("source"),
        actions=dict(default.get("actions", {})),
        entities=dict(default.get("entities", {})),
    )


async def async_get_model_features(hass, guide_type: str | None, model: str | None) -> ModelFeatures:
    """Resolve (and cache per guide type / model code) the features for a car."""
    cache: dict[tuple[str | None, str | None], ModelFeatures] = hass.data.setdefault(
        "lynkco_features", {}
    )
    key = (guide_type, model)
    if key not in cache:
        cache[key] = await hass.async_add_executor_job(resolve_features, guide_type, model)
    return cache[key]
