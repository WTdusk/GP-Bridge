"""Load and validate reusable Kontakt/VST mapping profiles."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

COMMUNITY_PRESET_URL = "https://github.com/WTdusk/GP-Bridge-Presets"


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    return application_dir() / "GPBridgeData"


def default_preset_dir() -> Path:
    return data_dir() / "Profiles"


def default_export_dir() -> Path:
    return data_dir() / "MIDI"


def list_presets(folder: str | Path) -> list[Path]:
    root = Path(folder).expanduser()
    if not root.exists():
        return []
    return sorted(
        path for path in root.rglob("*.json")
        if path.name.lower() != "catalog.json"
        and not any(part.startswith(".") or part.lower() == "templates"
                    for part in path.relative_to(root).parts[:-1])
    )


def load_preset(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser()
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("preset root must be a JSON object")
    data.setdefault("preset_name", data.get("instrument") or source.stem)
    data["_path"] = str(source)
    return data


def validate_preset(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["preset root must be a JSON object"]
    for key, expected in (("techniques", dict), ("string_channels", dict), ("combinations", list)):
        if not isinstance(data.get(key, expected()), expected):
            errors.append(f"{key} must be an {'object' if expected is dict else 'array'}")
    if errors:
        return errors

    def numeric(value: Any, label: str, low=None, high=None, integer=False) -> None:
        try:
            parsed = float(value)
            if isinstance(value, bool) or not math.isfinite(parsed) or (integer and parsed != int(parsed)):
                raise ValueError
            if integer:
                int(value)  # Use the same conversion as the MIDI writer.
        except (TypeError, ValueError, OverflowError):
            errors.append(f"{label} must be a finite {'integer' if integer else 'number'}")
            return
        if low is not None and parsed < low or high is not None and parsed > high:
            errors.append(f"{label} must be between {low} and {high}")

    event_types = {"keyswitch", "note", "cc", "pitch_bend", "pitchbend", "program_change"}

    def check_rules(rules: Any, label: str) -> None:
        if not isinstance(rules, list):
            errors.append(f"{label}: events must be a list")
            return
        for rule in rules:
            if not isinstance(rule, dict):
                errors.append(f"{label}: event must be an object")
                continue
            kind_value = rule.get("type", "keyswitch")
            kind = kind_value.lower() if isinstance(kind_value, str) else ""
            if kind not in event_types:
                errors.append(f"{label}: unsupported event type {kind}")
                continue
            field_ranges = {"note": (0, 127), "velocity": (0, 127), "controller": (0, 127), "reset_value": (0, 127),
                            "value": (0, 16383 if kind in {"pitch_bend", "pitchbend"} else 127), "program": (0, 127)}
            for key, (low, high) in field_ranges.items():
                if key in rule:
                    numeric(rule[key], f"{label}: {key}", low, high, integer=True)
            for key in ("offset_ticks", "duration_ticks"):
                if key in rule:
                    numeric(rule[key], f"{label}: {key}", 0 if key == "duration_ticks" else None, integer=True)
            if rule.get("reset_at_note_off") and kind != "cc":
                errors.append(f"{label}: reset_at_note_off is only valid for CC events")

    if not isinstance(data.get("techniques", {}), dict):
        errors.append("techniques must be an object")
    for name, spec in data.get("techniques", {}).items():
        rules = spec if isinstance(spec, list) else spec.get("events", []) if isinstance(spec, dict) else None
        if rules is None:
            errors.append(f"technique {name}: expected events list")
            continue
        check_rules(rules, f"technique {name}")
        if isinstance(spec, dict) and isinstance(spec.get("velocity"), dict):
            velocity = spec["velocity"]
            if "factor" in velocity:
                numeric(velocity["factor"], f"technique {name}: velocity factor", 0)
            for key in ("value", "min", "max", "offset"):
                if key in velocity:
                    numeric(velocity[key], f"technique {name}: velocity {key}", integer=True)
    for string, channel in data.get("string_channels", {}).items():
        numeric(channel, f"string {string}: MIDI channel", 1, 16, integer=True)
    for key in ("default_channel", "unassigned_channel", "strum_channel"):
        if key in data:
            numeric(data[key], key, 1, 16, integer=True)
    for key in ("split_tracks",):
        if key in data and not isinstance(data[key], bool):
            errors.append(f"{key} must be a boolean")
    if data.get("sustain_mode", "notated") not in ("notated", "auto"):
        errors.append("sustain_mode must be notated or auto")
    for key, low, high in (("legato_overlap_ticks", 0, 480), ("slide_overlap_ticks", 0, 960), ("legato_max_interval_semitones", 1, 24)):
        if key in data:
            numeric(data[key], key, low, high, integer=True)
    bend = data.get("techniques", {}).get("bend", {}) if isinstance(data.get("techniques"), dict) else {}
    if isinstance(bend, dict):
        for key in ("pitch_bend_range_semitones", "bend_value_divisor", "max_bend_semitones"):
            if key in bend:
                numeric(bend[key], f"bend {key}")
                if not errors and float(bend[key]) <= 0:
                    errors.append(f"bend {key} must be positive")
        value_scale = bend.get("value_scale")
        if value_scale is not None and str(value_scale).lower() not in {
            "divisor", "gp_percent_full_step", "percent_of_full_step", "gp_percent"
        }:
            errors.append("bend value_scale must be divisor or gp_percent_full_step")
    for index, combo in enumerate(data.get("combinations", [])):
        if not isinstance(combo, dict) or not isinstance(combo.get("when"), list) or not combo["when"] or any(not isinstance(name, str) for name in combo["when"]):
            errors.append(f"combination {index}: expected a when list")
            continue
        check_rules(combo.get("events", []), f"combination {index}")
    return errors


def validate_ai_profile(data: dict[str, Any]) -> list[str]:
    errors = validate_preset(data)
    if errors:
        return errors
    if not data.get("library") or not data.get("instrument"):
        errors.append("AI extraction did not identify both library and instrument")
    if not data.get("techniques"):
        errors.append("AI extraction found no documented technique mappings")
    source = data.get("source", {})
    if not isinstance(source, dict):
        return ["profile source must be an object"]
    if source.get("confidence") != "documented":
        errors.append("AI-generated source confidence must be documented; verification requires a Kontakt test")
    if not isinstance(source.get("pages"), list) or not source["pages"]:
        errors.append("profile source must include guide page numbers")
    elif any(not isinstance(page, int) or page < 1 for page in source["pages"]):
        errors.append("profile source pages must be positive integers")
    octave = str(data.get("octave_convention") or source.get("octave_convention") or "").strip().lower()
    if not octave:
        errors.append("profile must state the keyswitch octave convention")
    has_keyswitch = any(
        isinstance(rule, dict) and str(rule.get("type", "keyswitch")).lower() in {"keyswitch", "note"}
        for spec in data.get("techniques", {}).values() if isinstance(spec, dict)
        for rule in spec.get("events", [])
    ) or any(
        isinstance(rule, dict) and str(rule.get("type", "keyswitch")).lower() in {"keyswitch", "note"}
        for combo in data.get("combinations", []) if isinstance(combo, dict)
        for rule in combo.get("events", [])
    )
    if has_keyswitch and any(marker in octave for marker in ("unknown", "ambiguous", "unspecified")):
        errors.append("keyswitch mappings require a confirmed octave convention")
    for name, spec in data.get("techniques", {}).items():
        if not isinstance(spec, dict):
            errors.append(f"technique {name}: AI profiles must include evidence metadata")
            continue
        evidence = spec.get("evidence", "")
        pages = spec.get("source_pages", [])
        if not isinstance(evidence, str) or len(evidence.strip()) < 12 or not isinstance(pages, list) or not pages:
            errors.append(f"technique {name}: missing source quote or page reference")
        elif any(not isinstance(page, int) or page < 1 for page in pages):
            errors.append(f"technique {name}: source pages must be positive integers")
        if spec.get("confidence") != "documented":
            errors.append(f"technique {name}: AI confidence must be documented; verified requires a Kontakt test")
    for combo in data.get("combinations", []):
        pages = combo.get("source_pages")
        if not isinstance(combo.get("evidence"), str) or len(combo["evidence"].strip()) < 12 or not isinstance(pages, list) or not pages:
            errors.append("a technique combination is missing its source quote or page reference")
        elif any(type(page) is not int or page < 1 for page in pages):
            errors.append("combination source pages must be positive integers")
    return errors
