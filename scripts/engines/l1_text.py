from __future__ import annotations

from typing import List

from core.models import DetectionContext, Issue
from core.text_utils import compile_patterns, matches_any_pattern, text_similarity

from .base import BaseLevelDetector


class TextConsistencyDetector(BaseLevelDetector):
    level = "L1"
    name = "text_consistency"
    description = "Validate expected text against OCR output."

    def run(self, context: DetectionContext) -> List[Issue]:
        rules = context.rules.get("text-consistency", {})
        strategy = rules.get("default_strategy", "substring")
        fuzzy_threshold = (
            rules.get("match_strategies", {}).get("fuzzy", {}).get("threshold", 0.8)
        )
        severity_overrides = rules.get("severity_overrides", {})
        max_results = rules.get("max_results_per_check", 10)
        ignore_patterns = compile_patterns(rules.get("ignore_patterns", []))
        ignore_texts = set(context.config.get("ignore_texts", []))
        expected_texts = context.config.get("expected_texts", {})
        issues: List[Issue] = []

        for element_name, expected_text in expected_texts.items():
            if expected_text in ignore_texts or matches_any_pattern(expected_text, ignore_patterns):
                continue

            matched = False
            for ocr_item in context.ocr_result.get("texts", []):
                actual_text = ocr_item.get("text", "")
                if strategy == "exact" and expected_text == actual_text:
                    matched = True
                    break
                if strategy == "substring" and expected_text in actual_text:
                    matched = True
                    break
                if strategy == "fuzzy" and text_similarity(expected_text, actual_text) >= fuzzy_threshold:
                    matched = True
                    break

            if not matched:
                nearby_texts = [
                    item.get("text", "") for item in context.ocr_result.get("texts", [])[:max_results]
                ]
                issues.append(
                    self.issue(
                        issue_type="text_missing",
                        severity=severity_overrides.get("text_missing", "error"),
                        element=element_name,
                        expected=expected_text,
                        actual=f"Not found. Nearby texts: {', '.join(nearby_texts)}",
                        suggestion="Check if the element is rendered or if text content changed",
                        evidence={"nearby_texts": nearby_texts},
                    )
                )

        return issues
