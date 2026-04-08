from __future__ import annotations

import re
from typing import List

from core.models import DetectionContext, Issue

from .base import BaseLevelDetector


class InternationalizationDetector(BaseLevelDetector):
    level = "L5"
    name = "internationalization"
    description = "Detect unexpected or mixed-language OCR content."

    def run(self, context: DetectionContext) -> List[Issue]:
        rules = context.rules.get("i18n", {})
        expected_language = context.config.get("expected_language")
        if not expected_language:
            return []

        languages = rules.get("languages", {})
        expected_config = languages.get(expected_language)
        if not expected_config:
            return []

        expected_pattern = re.compile(expected_config.get("script_pattern", r".*"))
        false_positives = set(rules.get("common_false_positives", []))
        other_languages = {
            code: cfg for code, cfg in languages.items() if code != expected_language
        }
        mixed_language_rules = rules.get("mixed_language", {})
        issues: List[Issue] = []

        for item in context.ocr_result.get("texts", []):
            text = (item.get("text") or "").strip()
            if not text or text in false_positives:
                continue

            has_expected = bool(expected_pattern.search(text))
            mixed_languages = []
            for code, cfg in other_languages.items():
                other_pattern = re.compile(cfg.get("script_pattern", r"^$"))
                if other_pattern.search(text):
                    if not has_expected:
                        issues.append(
                            self.issue(
                                issue_type="unexpected_language",
                                severity="warning",
                                element="text_region",
                                expected=f"{expected_language} text",
                                actual=f"{code} text found: '{text[:50]}'",
                                screenshot_region=item.get("box"),
                                suggestion=(
                                    f"Check locale configuration: expected {expected_language}, found {code}"
                                ),
                            )
                        )
                        break
                    mixed_languages.append(code)
            else:
                if mixed_languages and mixed_language_rules.get("enabled", False):
                    issues.append(
                        self.issue(
                            issue_type="mixed_language_text",
                            severity=mixed_language_rules.get("severity", "info"),
                            element="text_region",
                            expected=f"Single-language {expected_language} text",
                            actual=f"Mixed language text found: '{text[:50]}'",
                            screenshot_region=item.get("box"),
                            suggestion="Verify that mixed-language copy is intentional",
                            evidence={"other_languages": mixed_languages},
                        )
                    )

        return issues
