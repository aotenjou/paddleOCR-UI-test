from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES_DIR = REPO_ROOT / "rules"
DEFAULT_PROFILES_DIR = REPO_ROOT / "profiles"
SUPPORTED_LEVELS = ("L1", "L2", "L3", "L4", "L5", "L6")

RULE_FILE_MAP = {
    "text-consistency": "text-consistency.json",
    "layout-anomaly": "layout-anomaly.json",
    "dom-ocr-crossval": "dom-ocr-crossval.json",
    "accessibility": "accessibility.json",
    "i18n": "i18n.json",
    "dynamic-content": "dynamic-content.json",
}

DEFAULT_RULES: Dict[str, Dict[str, Any]] = {
    "text-consistency": {
        "version": "1.0",
        "match_strategies": {
            "exact": {"type": "exact"},
            "substring": {"type": "substring"},
            "fuzzy": {"type": "fuzzy", "threshold": 0.8},
        },
        "default_strategy": "substring",
        "severity_overrides": {
            "text_missing": "error",
            "text_mismatch": "error",
            "extra_text": "info",
        },
        "max_results_per_check": 10,
        "ignore_patterns": [],
    },
    "layout-anomaly": {
        "version": "1.0",
        "overflow": {"enabled": True, "severity": "warning"},
        "full_page_text": {
            "enabled": True,
            "width_threshold": 0.95,
            "height_threshold": 0.8,
            "severity": "warning",
        },
        "element_overlap": {
            "enabled": False,
            "iou_threshold": 0.3,
            "severity": "warning",
        },
        "text_truncation": {
            "enabled": False,
            "min_expected_chars": 20,
            "severity": "warning",
        },
        "touch_target_size": {
            "enabled": False,
            "min_width_px": 44,
            "min_height_px": 44,
            "severity": "warning",
        },
    },
    "dom-ocr-crossval": {
        "version": "1.0",
        "fuzzy_match": {
            "enabled": True,
            "threshold": 0.6,
            "warning_threshold": 0.7,
        },
        "count_mismatch": {
            "enabled": True,
            "delta_threshold": 0.3,
            "min_elements": 5,
            "severity": "warning",
        },
        "dom_not_rendered": {"max_results": 10, "severity": "error"},
        "rendered_not_in_dom": {"max_results": 10, "severity": "warning"},
        "ignore_patterns": [r"^[\s\u200b\u200c\u200d]+$"],
    },
    "accessibility": {
        "version": "1.0",
        "missing_alt": {
            "enabled": True,
            "roles": ["image", "graphic", "img"],
            "ignore_values": ["", "image", "icon"],
            "severity": "error",
        },
        "missing_label": {
            "enabled": False,
            "roles": ["button", "textbox", "checkbox", "radio", "combobox"],
            "severity": "error",
        },
        "canvas_rendered_text": {"enabled": False, "severity": "warning"},
        "emoji_as_icon": {
            "enabled": False,
            "emoji_pattern": r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u2600-\u26FF\u2700-\u27BF]",
            "severity": "warning",
        },
    },
    "i18n": {
        "version": "1.0",
        "languages": {
            "zh": {"script_pattern": r"[\u4e00-\u9fff]", "min_word_length": 1},
            "en": {"script_pattern": r"[a-zA-Z]{4,}", "min_word_length": 4},
            "ja": {
                "script_pattern": r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]",
                "min_word_length": 1,
            },
            "ko": {
                "script_pattern": r"[\uac00-\ud7af\u1100-\u11ff]",
                "min_word_length": 1,
            },
        },
        "mixed_language": {"enabled": False, "severity": "info"},
        "common_false_positives": [
            "OK",
            "Login",
            "Sign Up",
            "API",
            "URL",
            "ID",
            "CSS",
            "HTML",
            "JS",
        ],
    },
    "dynamic-content": {
        "version": "1.0",
        "state_transitions": {
            "loading_to_content": {
                "should_disappear": ["Loading...", "loading", "spinner", "请稍候"],
                "should_appear": [],
                "timeout_ms": 5000,
            },
            "content_to_error": {
                "should_disappear": [],
                "should_appear": ["Error", "error", "失败", "异常"],
                "timeout_ms": 10000,
            },
        },
        "content_persistence": {"enabled": False, "critical_texts": []},
        "max_tracked_changes": 5,
    },
}

ALLOWED_RULE_KEYS = {
    "text-consistency": {
        "version",
        "description",
        "agent_hints",
        "match_strategies",
        "default_strategy",
        "severity_overrides",
        "max_results_per_check",
        "ignore_patterns",
    },
    "layout-anomaly": {
        "version",
        "description",
        "agent_hints",
        "overflow",
        "full_page_text",
        "element_overlap",
        "text_truncation",
        "touch_target_size",
    },
    "dom-ocr-crossval": {
        "version",
        "description",
        "agent_hints",
        "fuzzy_match",
        "count_mismatch",
        "dom_not_rendered",
        "rendered_not_in_dom",
        "ignore_patterns",
    },
    "accessibility": {
        "version",
        "description",
        "agent_hints",
        "missing_alt",
        "missing_label",
        "canvas_rendered_text",
        "emoji_as_icon",
    },
    "i18n": {
        "version",
        "description",
        "agent_hints",
        "languages",
        "mixed_language",
        "common_false_positives",
    },
    "dynamic-content": {
        "version",
        "description",
        "agent_hints",
        "state_transitions",
        "content_persistence",
        "max_tracked_changes",
    },
}

PROFILE_ALLOWED_KEYS = {
    "name",
    "description",
    "when_to_use",
    "default_levels",
    "viewport",
    "wait_ms",
    "rule_overrides",
    "expected_elements",
    "ignore_patterns",
}
EXPECTED_ELEMENT_ALLOWED_KEYS = {"role", "name_pattern", "min_count", "max_count"}
RUNTIME_CONFIG_ALLOWED_KEYS = {
    "expected_texts",
    "expected_language",
    "ignore_texts",
    "levels",
    "wait_ms",
    "expected_elements",
    "ignore_patterns",
}


@dataclass
class ResolvedRunSettings:
    config: Dict[str, Any]
    rules: Dict[str, Any]
    levels: List[str]
    viewport: str
    wait_ms: int


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _dedupe_strings(values: Sequence[str]) -> List[str]:
    seen = set()
    results = []
    for value in values:
        if value not in seen:
            seen.add(value)
            results.append(value)
    return results


def _has_nested_path(data: Dict[str, Any], parts: Sequence[str]) -> bool:
    target: Any = data
    for part in parts:
        if not isinstance(target, dict) or part not in target:
            return False
        target = target[part]
    return True


def _set_nested_path(data: Dict[str, Any], parts: Sequence[str], value: Any) -> None:
    target = data
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


def _validate_viewport(viewport: str) -> None:
    if not re.fullmatch(r"\d+x\d+", viewport or ""):
        raise ValueError(f"Invalid viewport format: {viewport}")


def _validate_levels(levels: Sequence[str]) -> None:
    invalid = [level for level in levels if level not in SUPPORTED_LEVELS]
    if invalid:
        raise ValueError(
            f"Unsupported test levels: {', '.join(invalid)}. Expected subset of {', '.join(SUPPORTED_LEVELS)}"
        )


def _validate_expected_elements(expected_elements: Sequence[Dict[str, Any]]) -> None:
    for idx, spec in enumerate(expected_elements):
        unknown = set(spec) - EXPECTED_ELEMENT_ALLOWED_KEYS
        if unknown:
            raise ValueError(
                f"Unknown expected_elements keys at index {idx}: {', '.join(sorted(unknown))}"
            )
        if not spec.get("role"):
            raise ValueError(f"expected_elements[{idx}] must define 'role'")


def list_available_profiles(profiles_dir: Optional[str] = None) -> List[str]:
    target = Path(profiles_dir) if profiles_dir else DEFAULT_PROFILES_DIR
    if not target.exists():
        return []
    return sorted(path.stem for path in target.glob("*.json"))


def load_rules(rules_dir: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    rules_path = Path(rules_dir) if rules_dir else DEFAULT_RULES_DIR
    rules: Dict[str, Dict[str, Any]] = {}
    for section, filename in RULE_FILE_MAP.items():
        loaded: Dict[str, Any] = {}
        filepath = rules_path / filename
        if filepath.exists():
            loaded = json.loads(filepath.read_text(encoding="utf-8"))
            unknown = set(loaded) - ALLOWED_RULE_KEYS[section]
            if unknown:
                raise ValueError(
                    f"Unknown keys in rule file {filename}: {', '.join(sorted(unknown))}"
                )
        rules[section] = _deep_merge(DEFAULT_RULES[section], loaded)
    return rules


def apply_rule_overrides(rules: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    updated = copy.deepcopy(rules)
    for dotted_key, value in (overrides or {}).items():
        parts = dotted_key.split(".")
        if not _has_nested_path(updated, parts):
            raise ValueError(f"Unknown rule override path: {dotted_key}")
        _set_nested_path(updated, parts, value)
    return updated


def load_profile(
    profile_name: str,
    *,
    profiles_dir: Optional[str] = None,
    rules: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    profiles_path = Path(profiles_dir) if profiles_dir else DEFAULT_PROFILES_DIR
    profile_path = profiles_path / f"{profile_name}.json"
    if not profile_path.exists():
        available = list_available_profiles(str(profiles_path))
        raise ValueError(
            f"Unknown profile: {profile_name}. Available: {', '.join(available) if available else 'none'}"
        )

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    unknown = set(profile) - PROFILE_ALLOWED_KEYS
    if unknown:
        raise ValueError(
            f"Unknown keys in profile {profile_name}: {', '.join(sorted(unknown))}"
        )

    if profile.get("default_levels"):
        _validate_levels(profile["default_levels"])
    if profile.get("viewport"):
        _validate_viewport(profile["viewport"])
    if profile.get("expected_elements"):
        _validate_expected_elements(profile["expected_elements"])

    candidate_rules = rules or load_rules()
    if profile.get("rule_overrides"):
        apply_rule_overrides(candidate_rules, profile["rule_overrides"])

    return profile


def load_runtime_config(config_path: Optional[str]) -> Dict[str, Any]:
    if not config_path:
        return {}
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    unknown = set(config) - RUNTIME_CONFIG_ALLOWED_KEYS
    if unknown:
        raise ValueError(
            f"Unknown keys in runtime config: {', '.join(sorted(unknown))}"
        )
    if "levels" in config:
        _validate_levels(config["levels"])
    if "expected_elements" in config:
        _validate_expected_elements(config["expected_elements"])
    return config


def resolve_run_settings(
    *,
    args: Any,
    raw_config: Optional[Dict[str, Any]],
    rules: Dict[str, Any],
    profile: Optional[Dict[str, Any]] = None,
) -> ResolvedRunSettings:
    config = copy.deepcopy(raw_config or {})
    resolved_rules = copy.deepcopy(rules)
    profile = copy.deepcopy(profile or {})

    if profile.get("rule_overrides"):
        resolved_rules = apply_rule_overrides(resolved_rules, profile["rule_overrides"])

    merged_expected_elements = list(profile.get("expected_elements", [])) + list(
        config.get("expected_elements", [])
    )
    if merged_expected_elements:
        _validate_expected_elements(merged_expected_elements)
        config["expected_elements"] = merged_expected_elements

    merged_ignore_patterns = _dedupe_strings(
        list(profile.get("ignore_patterns", [])) + list(config.get("ignore_patterns", []))
    )
    if merged_ignore_patterns:
        config["ignore_patterns"] = merged_ignore_patterns
        for section in ("text-consistency", "dom-ocr-crossval"):
            resolved_rules[section]["ignore_patterns"] = _dedupe_strings(
                list(resolved_rules[section].get("ignore_patterns", []))
                + merged_ignore_patterns
            )

    levels = config.get("levels") or profile.get("default_levels") or ["L1", "L3"]
    if getattr(args, "levels", None):
        levels = [level.strip() for level in args.levels.split(",") if level.strip()]
    _validate_levels(levels)

    viewport = getattr(args, "viewport", None) or profile.get("viewport", "1280x720")
    _validate_viewport(viewport)

    wait_ms = int(config.get("wait_ms", profile.get("wait_ms", getattr(args, "wait", 2000))))

    return ResolvedRunSettings(
        config=config,
        rules=resolved_rules,
        levels=levels,
        viewport=viewport,
        wait_ms=wait_ms,
    )
