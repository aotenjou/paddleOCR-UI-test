"""Core contracts and helpers for PaddleOCR UI test."""

from .a11y import flatten_a11y_tree
from .baseline import BaselineDiff, create_baseline
from .config import (
    SUPPORTED_LEVELS,
    DEFAULT_PROFILES_DIR,
    DEFAULT_RULES_DIR,
    list_available_profiles,
    load_profile,
    load_rules,
    load_runtime_config,
    resolve_run_settings,
)
from .models import DetectionContext, EvidenceBundle, Issue, coerce_issues
from .reporting import ReportWriter, summarize_issues
from .text_utils import build_cross_validation_findings, find_best_match, text_similarity

__all__ = [
    "BaselineDiff",
    "DetectionContext",
    "EvidenceBundle",
    "Issue",
    "ReportWriter",
    "SUPPORTED_LEVELS",
    "DEFAULT_PROFILES_DIR",
    "DEFAULT_RULES_DIR",
    "build_cross_validation_findings",
    "coerce_issues",
    "create_baseline",
    "find_best_match",
    "flatten_a11y_tree",
    "list_available_profiles",
    "load_profile",
    "load_rules",
    "load_runtime_config",
    "resolve_run_settings",
    "summarize_issues",
    "text_similarity",
]
