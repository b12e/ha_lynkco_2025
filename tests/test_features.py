"""Unit tests for the per-model feature resolution (no Home Assistant needed).

Run with:  python3 -m pytest tests/
"""

import importlib.util
import json
import os
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "lynkco"

spec = importlib.util.spec_from_file_location("lynkco_features", ROOT / "features.py")
features = importlib.util.module_from_spec(spec)
spec.loader.exec_module(features)

ALL_ACTIONS = {
    "lock_door", "unlock_door", "flash_lights", "honk_horn",
    "start_conditioning", "stop_conditioning",
    "open_sunroof", "close_sunroof", "set_charge_limit",
    "start_charging", "stop_charging", "start_ventilate", "stop_ventilate",
    "start_heaters", "stop_heaters", "lock_glovebox", "unlock_glovebox",
    "request_location",
}
BASICS = {
    "lock_door", "unlock_door", "flash_lights", "honk_horn",
    "start_conditioning", "stop_conditioning",
}


def enabled_actions(resolved):
    return {a for a in ALL_ACTIONS if resolved.action_enabled(a)}


def test_model_files_are_valid_json_with_known_keys():
    files = sorted(os.listdir(ROOT / "models"))
    assert "_default.json" in files
    for name in files:
        with open(ROOT / "models" / name, encoding="utf-8") as fh:
            data = json.load(fh)
        assert set(data) <= {"_comment", "name", "source", "actions", "entities"}, name
        assert set(data.get("actions", {})) <= ALL_ACTIONS, name
        assert set(data.get("entities", {})) <= {"sunroof"}, name


def test_default_lists_every_action_and_only_basics_are_on():
    resolved = features.resolve_features(None, None)
    assert resolved.is_default
    assert set(resolved.actions) == ALL_ACTIONS
    assert enabled_actions(resolved) == BASICS
    assert resolved.entity_enabled("sunroof") is False
    assert resolved.entity_enabled("something_new") is True


def test_unknown_codes_fall_back_to_default():
    resolved = features.resolve_features("XY99_MORE", "XY99")
    assert resolved.is_default
    assert enabled_actions(resolved) == BASICS


def test_pre_2025_01_only_gets_basics():
    resolved = features.resolve_features(None, "CX11_A1")
    assert not resolved.is_default
    assert resolved.file == "CX11_A1"
    assert enabled_actions(resolved) == BASICS
    assert resolved.entity_enabled("sunroof") is False
    assert "issues/33" in resolved.source


@pytest.mark.parametrize("model", ["CX11_A3", "DX11"])
def test_2025_models_keep_everything(model):
    resolved = features.resolve_features(None, model)
    assert resolved.file == model
    assert enabled_actions(resolved) == ALL_ACTIONS
    assert resolved.entity_enabled("sunroof") is True


def test_02_has_no_sunroof_but_everything_else():
    resolved = features.resolve_features("E335_MORE", "E335")
    assert resolved.file == "E335"
    assert enabled_actions(resolved) == ALL_ACTIONS - {"open_sunroof", "close_sunroof"}
    assert resolved.entity_enabled("sunroof") is False


def test_guide_type_wins_over_model_code():
    files = {
        "_default": {"name": "d", "actions": {"lock_door": True, "open_sunroof": False}, "entities": {"sunroof": False}},
        "CX11_A3": {"name": "new 01", "actions": {"open_sunroof": True}, "entities": {"sunroof": True}},
        "CX11_2023": {"name": "01 2023", "source": "issue", "actions": {}, "entities": {}},
    }
    resolved = features.resolve_features("CX11_2023", "CX11_A3", loader=files.get)
    assert resolved.file == "CX11_2023"
    assert resolved.name == "01 2023"
    assert resolved.action_enabled("open_sunroof") is False
    assert resolved.action_enabled("lock_door") is True
    assert resolved.entity_enabled("sunroof") is False

    resolved = features.resolve_features("CX11_MORE", "CX11_A3", loader=files.get)
    assert resolved.file == "CX11_A3"
    assert resolved.action_enabled("open_sunroof") is True


def test_unsafe_names_never_touch_the_filesystem():
    assert features.resolve_features("../etc", "../../x").is_default
